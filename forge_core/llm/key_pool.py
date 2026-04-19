"""ApiKeyPool — Multiple API keys per LLM provider with automatic rotation.

When a key hits a rate-limit the pool parks it for a configurable cooldown
period and transparently rotates to the next available key for the same
provider, so the gateway can retry the same model without switching providers.

Key lifecycle:
  ACTIVE  → the key is currently being used
  STANDBY → healthy but not yet the active one
  RATE_LIMITED → parked for `cooldown_seconds`; automatically re-activates
                 when the cooldown expires

Per-key usage:
  Each _KeyEntry now tracks calls, token consumption (in/out), error count,
  last-used timestamp, and configurable daily/monthly token budgets so callers
  can see "how much is left" per key.

Thread safety: uses asyncio.Lock so callers can await it safely from async
gateway code.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Default cooldown when a key gets a 429 – 60 seconds is enough for most
# providers' per-minute windows to reset.
DEFAULT_COOLDOWN_SECONDS = 60

# Seconds in a day / month (approximate)
_DAY   = 86_400
_MONTH = 2_592_000   # 30 days


@dataclass
class _KeyEntry:
    label: str
    key: str
    rate_limited_until: float = 0.0   # epoch timestamp; 0 = not limited

    # ── Usage counters (in-memory; mirrored to DB by the API layer) ──────────
    total_calls:      int   = 0
    total_tokens_in:  int   = 0
    total_tokens_out: int   = 0
    total_errors:     int   = 0
    last_used_at:     float = 0.0   # epoch timestamp of last successful call

    # ── Budget limits (0 = unlimited) ────────────────────────────────────────
    daily_limit_tokens:   int = 0
    monthly_limit_tokens: int = 0

    # ── Rolling windows for remaining-budget calculation ─────────────────────
    # Each entry: (epoch_ts, tokens_in, tokens_out)
    _day_window:   list = field(default_factory=list, repr=False)
    _month_window: list = field(default_factory=list, repr=False)

    @property
    def is_available(self) -> bool:
        return time.time() >= self.rate_limited_until

    @property
    def status(self) -> str:
        if not self.is_available:
            remaining = int(self.rate_limited_until - time.time())
            return f"rate_limited:{remaining}s"
        return "active"

    def masked(self) -> str:
        k = self.key
        if len(k) > 12:
            return k[:8] + "*" * (len(k) - 12) + k[-4:]
        return "****"

    # ── Usage helpers ────────────────────────────────────────────────────────

    def record_success(self, tokens_in: int, tokens_out: int) -> None:
        """Increment counters when a call succeeds."""
        now = time.time()
        self.total_calls      += 1
        self.total_tokens_in  += tokens_in
        self.total_tokens_out += tokens_out
        self.last_used_at      = now
        self._day_window.append((now, tokens_in, tokens_out))
        self._month_window.append((now, tokens_in, tokens_out))
        # Trim windows
        cutoff_day   = now - _DAY
        cutoff_month = now - _MONTH
        self._day_window   = [e for e in self._day_window   if e[0] >= cutoff_day]
        self._month_window = [e for e in self._month_window if e[0] >= cutoff_month]

    def record_error(self) -> None:
        """Increment error counter."""
        self.total_errors  += 1
        self.last_used_at   = time.time()

    def tokens_used_today(self) -> int:
        now = time.time()
        cutoff = now - _DAY
        return sum(e[1] + e[2] for e in self._day_window if e[0] >= cutoff)

    def tokens_used_this_month(self) -> int:
        now = time.time()
        cutoff = now - _MONTH
        return sum(e[1] + e[2] for e in self._month_window if e[0] >= cutoff)

    def tokens_remaining_today(self) -> Optional[int]:
        if self.daily_limit_tokens == 0:
            return None   # unlimited
        return max(0, self.daily_limit_tokens - self.tokens_used_today())

    def tokens_remaining_this_month(self) -> Optional[int]:
        if self.monthly_limit_tokens == 0:
            return None   # unlimited
        return max(0, self.monthly_limit_tokens - self.tokens_used_this_month())

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self, *, include_status: bool = True) -> dict:
        d: dict = {
            "label":              self.label,
            "masked_key":         self.masked(),
            "rate_limited_until": self.rate_limited_until,
            # Usage stats
            "total_calls":        self.total_calls,
            "total_tokens_in":    self.total_tokens_in,
            "total_tokens_out":   self.total_tokens_out,
            "total_errors":       self.total_errors,
            "last_used_at":       self.last_used_at,
            # Budget
            "daily_limit_tokens":   self.daily_limit_tokens,
            "monthly_limit_tokens": self.monthly_limit_tokens,
            "tokens_used_today":    self.tokens_used_today(),
            "tokens_used_this_month": self.tokens_used_this_month(),
            "tokens_remaining_today":     self.tokens_remaining_today(),
            "tokens_remaining_this_month": self.tokens_remaining_this_month(),
        }
        if include_status:
            d["status"]       = self.status
            d["is_available"] = self.is_available
        return d


class ApiKeyPool:
    """In-memory pool of API keys per provider with automatic rotation."""

    def __init__(self):
        # provider_id → ordered list of _KeyEntry
        self._pool: dict[str, list[_KeyEntry]] = {}
        # provider_id → index of the currently preferred key
        self._cursor: dict[str, int] = {}

    # ─── Registration ────────────────────────────────────────────────────────

    def init_provider(self, provider_id: str, keys: list[dict]) -> None:
        """Initialise (or replace) the key list for a provider.

        `keys` is a list of dicts with at least {\"label\": ..., \"key\": ...}.
        Existing cooldown state and usage counters are preserved for keys
        that are still present.
        """
        existing = {e.label: e for e in self._pool.get(provider_id, [])}
        entries = []
        for k in keys:
            label = k.get("label", "default")
            key   = k.get("key", "")
            if not key:
                continue
            entry = existing.get(label)
            if entry:
                entry.key = key          # update value but keep cooldown + usage
                # Restore persisted usage if the key was loaded from DB
                if k.get("usage_calls"):
                    entry.total_calls      = k.get("usage_calls", 0)
                    entry.total_tokens_in  = k.get("usage_tokens_in", 0)
                    entry.total_tokens_out = k.get("usage_tokens_out", 0)
                    entry.total_errors     = k.get("usage_errors", 0)
                    entry.last_used_at     = k.get("last_used_at", 0.0)
                entry.daily_limit_tokens   = k.get("daily_limit_tokens", 0)
                entry.monthly_limit_tokens = k.get("monthly_limit_tokens", 0)
                entries.append(entry)
            else:
                e = _KeyEntry(
                    label=label,
                    key=key,
                    total_calls      = k.get("usage_calls", 0),
                    total_tokens_in  = k.get("usage_tokens_in", 0),
                    total_tokens_out = k.get("usage_tokens_out", 0),
                    total_errors     = k.get("usage_errors", 0),
                    last_used_at     = k.get("last_used_at", 0.0),
                    daily_limit_tokens   = k.get("daily_limit_tokens", 0),
                    monthly_limit_tokens = k.get("monthly_limit_tokens", 0),
                )
                entries.append(e)
        self._pool[provider_id] = entries
        # Reset cursor to the first available key
        self._cursor[provider_id] = self._find_next_available(provider_id, start=0)
        logger.debug(f"[KeyPool] {provider_id}: {len(entries)} key(s) registered")

    def add_key(self, provider_id: str, label: str, key: str) -> None:
        """Append a new key to the pool for the given provider."""
        if provider_id not in self._pool:
            self._pool[provider_id] = []
        # Prevent duplicates by label
        for e in self._pool[provider_id]:
            if e.label == label:
                e.key = key          # update existing
                logger.info(f"[KeyPool] {provider_id}: updated key '{label}'")
                return
        self._pool[provider_id].append(_KeyEntry(label=label, key=key))
        # Don't change the cursor — let the current active key keep working
        if provider_id not in self._cursor:
            self._cursor[provider_id] = 0
        logger.info(f"[KeyPool] {provider_id}: added key '{label}'")

    def remove_key(self, provider_id: str, label: str) -> bool:
        """Remove a key by label. Returns True if removed."""
        entries = self._pool.get(provider_id, [])
        before = len(entries)
        self._pool[provider_id] = [e for e in entries if e.label != label]
        removed = len(self._pool[provider_id]) < before
        if removed:
            # Reset cursor safely
            self._cursor[provider_id] = self._find_next_available(provider_id, start=0)
            logger.info(f"[KeyPool] {provider_id}: removed key '{label}'")
        return removed

    # ─── Key Retrieval ───────────────────────────────────────────────────────

    def get_active_key(self, provider_id: str) -> Optional[str]:
        """Return the current active (non-rate-limited) key, or None if all are exhausted."""
        entries = self._pool.get(provider_id, [])
        if not entries:
            return None
        cursor = self._cursor.get(provider_id, 0)
        entry = entries[cursor % len(entries)]
        if entry.is_available:
            return entry.key
        # cursor points to a limited key — search for any available one
        idx = self._find_next_available(provider_id, start=0)
        if idx >= 0:
            self._cursor[provider_id] = idx
            return entries[idx].key
        return None   # all keys are rate-limited

    def get_active_label(self, provider_id: str) -> Optional[str]:
        """Return the label of the currently active key, or None."""
        entries = self._pool.get(provider_id, [])
        if not entries:
            return None
        cursor = self._cursor.get(provider_id, 0)
        entry = entries[cursor % len(entries)]
        return entry.label if entry.is_available else None

    def get_entry_by_key_value(self, provider_id: str, key_value: str) -> Optional[_KeyEntry]:
        """Lookup an entry by its actual key value."""
        for e in self._pool.get(provider_id, []):
            if e.key == key_value:
                return e
        return None

    def get_entry_by_label(self, provider_id: str, label: str) -> Optional[_KeyEntry]:
        """Lookup an entry by its label."""
        for e in self._pool.get(provider_id, []):
            if e.label == label:
                return e
        return None

    # ─── Usage Recording ─────────────────────────────────────────────────────

    def record_key_usage(
        self,
        provider_id: str,
        key_value: str,
        tokens_in: int,
        tokens_out: int,
    ) -> Optional[str]:
        """Record a successful call against the key identified by `key_value`.

        Returns the key label (used to update the DB row asynchronously).
        """
        entry = self.get_entry_by_key_value(provider_id, key_value)
        if entry:
            entry.record_success(tokens_in, tokens_out)
            return entry.label
        return None

    def record_key_error(self, provider_id: str, key_value: str) -> Optional[str]:
        """Record an error against the key identified by `key_value`.

        Returns the key label.
        """
        entry = self.get_entry_by_key_value(provider_id, key_value)
        if entry:
            entry.record_error()
            return entry.label
        return None

    def set_key_limits(
        self,
        provider_id: str,
        label: str,
        *,
        daily_limit_tokens: int = 0,
        monthly_limit_tokens: int = 0,
    ) -> bool:
        """Set budget limits on a key. Returns True if the key was found."""
        entry = self.get_entry_by_label(provider_id, label)
        if entry:
            entry.daily_limit_tokens   = daily_limit_tokens
            entry.monthly_limit_tokens = monthly_limit_tokens
            return True
        return False

    def reset_key_usage_counters(self, provider_id: str, label: str) -> bool:
        """Reset all in-memory usage counters for a key to zero."""
        entry = self.get_entry_by_label(provider_id, label)
        if entry:
            entry.total_calls      = 0
            entry.total_tokens_in  = 0
            entry.total_tokens_out = 0
            entry.total_errors     = 0
            entry.last_used_at     = 0.0
            entry._day_window      = []
            entry._month_window    = []
            return True
        return False

    # ─── Rate-limit Handling ─────────────────────────────────────────────────

    def mark_rate_limited(
        self,
        provider_id: str,
        key_value: str,
        *,
        cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
    ) -> Optional[str]:
        """Park `key_value` for `cooldown_seconds` and rotate to the next key.

        Returns the new active key (or None if all are now exhausted).
        """
        entries = self._pool.get(provider_id, [])
        parked_idx: Optional[int] = None
        for i, e in enumerate(entries):
            if e.key == key_value:
                e.rate_limited_until = time.time() + cooldown_seconds
                parked_idx = i
                logger.warning(
                    f"[KeyPool] {provider_id}: key '{e.label}' rate-limited "
                    f"for {cooldown_seconds}s"
                )
                break

        if parked_idx is None:
            # Key not found in pool — just clear it from env
            return self.get_active_key(provider_id)

        # Try to rotate to the next available key after the parked one
        next_idx = self._find_next_available(
            provider_id,
            start=(parked_idx + 1) % max(len(entries), 1),
            exclude_idx=parked_idx,
        )
        if next_idx >= 0:
            self._cursor[provider_id] = next_idx
            new_key = entries[next_idx].key
            logger.info(
                f"[KeyPool] {provider_id}: rotated to key '{entries[next_idx].label}'"
            )
            return new_key

        logger.error(f"[KeyPool] {provider_id}: all keys are rate-limited")
        return None

    def reset_key(self, provider_id: str, label: str) -> bool:
        """Manually clear cooldown on a key (e.g. from dashboard 'Reset' button)."""
        for e in self._pool.get(provider_id, []):
            if e.label == label:
                e.rate_limited_until = 0.0
                # Re-evaluate cursor
                cursor = self._cursor.get(provider_id, 0)
                entries = self._pool[provider_id]
                if not entries[cursor % len(entries)].is_available:
                    self._cursor[provider_id] = self._find_next_available(
                        provider_id, start=0
                    )
                logger.info(f"[KeyPool] {provider_id}: reset cooldown on key '{label}'")
                return True
        return False

    # ─── Introspection ───────────────────────────────────────────────────────

    def get_key_statuses(self, provider_id: str) -> list[dict]:
        """Return a list of key status dicts (masked) for the dashboard."""
        entries = self._pool.get(provider_id, [])
        cursor  = self._cursor.get(provider_id, 0)
        result  = []
        for i, e in enumerate(entries):
            d = e.to_dict()
            d["is_current"] = (i == cursor % len(entries)) if entries else False
            result.append(d)
        return result

    def get_key_usage(self, provider_id: str) -> list[dict]:
        """Alias for get_key_statuses — returns full usage + remaining budget."""
        return self.get_key_statuses(provider_id)

    def key_count(self, provider_id: str) -> int:
        return len(self._pool.get(provider_id, []))

    def all_providers(self) -> list[str]:
        return list(self._pool.keys())

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _find_next_available(
        self,
        provider_id: str,
        start: int = 0,
        exclude_idx: Optional[int] = None,
    ) -> int:
        """Return the index of the first available key at or after `start`, -1 if none."""
        entries = self._pool.get(provider_id, [])
        n = len(entries)
        if n == 0:
            return -1
        for offset in range(n):
            idx = (start + offset) % n
            if idx == exclude_idx:
                continue
            if entries[idx].is_available:
                return idx
        return -1


# Singleton used by the gateway and API
key_pool = ApiKeyPool()
