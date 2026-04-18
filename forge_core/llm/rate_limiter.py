"""LLM Rate Limiter - Per-model rate limiting, token budgets, and usage tracking.

Tracks requests per minute (RPM), token consumption across time windows,
and records failover events when limits cause automatic model switching.
"""

from __future__ import annotations

import logging
import time
from collections import deque, defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import Optional

logger = logging.getLogger(__name__)

# ───────────────────────────────────────────────
# Data Structures
# ───────────────────────────────────────────────

@dataclass
class ModelLimits:
    """Per-model configurable limits."""
    rpm: int = 0                  # Requests per minute. 0 = unlimited
    max_input_tokens: int = 0     # Max input tokens per request. 0 = unlimited
    max_tokens_per_minute: int = 0  # Max total tokens (in+out) per minute. 0 = unlimited
    max_tokens_per_day: int = 0   # Max total tokens per day. 0 = unlimited


@dataclass
class WindowStats:
    """Rolling usage stats for a time window."""
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    failures: int = 0
    failovers: int = 0


@dataclass
class FailoverEvent:
    """Records when a model switch happened."""
    timestamp: float
    from_model: str
    to_model: str
    reason: str          # "rpm_limit" | "token_limit" | "api_error" | "timeout"
    context_tokens: int  # How many tokens of context were carried over
    task_hint: str = ""  # Brief description of the task being handled


# ───────────────────────────────────────────────
# Rate Limiter Core
# ───────────────────────────────────────────────

class ModelRateLimiter:
    """
    Central rate-limiter and usage tracker for all LLM models.

    Features:
    - Sliding-window RPM enforcement (1-minute window)
    - Per-request input token budget
    - Per-minute token budget
    - Per-day and per-week cumulative usage tracking
    - Failover event log (ring buffer, last 200 events)
    - Thread-safe with asyncio compatibility (uses a simple lock + deques)
    """

    MINUTE = 60
    DAY    = 86_400
    WEEK   = 604_800

    def __init__(self):
        self._limits: dict[str, ModelLimits] = {}

        # Sliding window: deque of (timestamp, input_tokens, output_tokens)
        self._request_window: dict[str, deque] = defaultdict(deque)

        # Cumulative raw call list for day/week aggregation
        self._all_calls: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=10_000)  # keep last 10K calls per model
        )

        # Failover event log (last 200)
        self._failover_log: deque[FailoverEvent] = deque(maxlen=200)

        self._lock = Lock()

    # ─── Limit Configuration ─────────────────────

    def set_limits(self, model_id: str, limits: ModelLimits):
        """Configure limits for a model."""
        with self._lock:
            self._limits[model_id] = limits
        logger.info(
            f"[RateLimit] {model_id}: rpm={limits.rpm}, "
            f"max_input_tokens={limits.max_input_tokens}, "
            f"max_tpm={limits.max_tokens_per_minute}"
        )

    def get_limits(self, model_id: str) -> ModelLimits:
        return self._limits.get(model_id, ModelLimits())

    def get_all_limits(self) -> dict[str, dict]:
        return {
            mid: {
                "rpm": lim.rpm,
                "max_input_tokens": lim.max_input_tokens,
                "max_tokens_per_minute": lim.max_tokens_per_minute,
                "max_tokens_per_day": lim.max_tokens_per_day,
            }
            for mid, lim in self._limits.items()
        }

    # ─── Pre-call Check ──────────────────────────

    def check_and_reserve(
        self,
        model_id: str,
        estimated_input_tokens: int,
    ) -> tuple[bool, str]:
        """
        Check if a model can accept a new request right now.

        Returns:
            (allowed: bool, reason: str)
        """
        with self._lock:
            now = time.time()
            lim = self._limits.get(model_id, ModelLimits())

            # ── 1. RPM check ──────────────────
            if lim.rpm > 0:
                window = self._request_window[model_id]
                # Purge entries older than 1 minute
                cutoff = now - self.MINUTE
                while window and window[0][0] < cutoff:
                    window.popleft()

                if len(window) >= lim.rpm:
                    # Find when the oldest entry will expire
                    oldest_ts = window[0][0]
                    wait_s = round(oldest_ts + self.MINUTE - now, 1)
                    return False, f"rpm_limit (used {len(window)}/{lim.rpm}, resets in {wait_s}s)"

            # ── 2. Per-request input token check ──
            if lim.max_input_tokens > 0 and estimated_input_tokens > lim.max_input_tokens:
                return False, (
                    f"token_limit (request has ~{estimated_input_tokens} tokens "
                    f"> limit {lim.max_input_tokens})"
                )

            # ── 3. Per-minute token budget ────────
            if lim.max_tokens_per_minute > 0:
                window = self._request_window[model_id]
                cutoff = now - self.MINUTE
                tokens_this_minute = sum(
                    e[1] + e[2] for e in window if e[0] >= cutoff
                )
                if tokens_this_minute + estimated_input_tokens > lim.max_tokens_per_minute:
                    return False, (
                        f"token_per_minute_limit ({tokens_this_minute} used "
                        f"of {lim.max_tokens_per_minute} TPM)"
                    )

            # ── 4. Per-day token budget ───────────
            if lim.max_tokens_per_day > 0:
                calls = self._all_calls[model_id]
                cutoff_day = now - self.DAY
                tokens_today = sum(
                    c["input_tokens"] + c["output_tokens"]
                    for c in calls if c["ts"] >= cutoff_day
                )
                if tokens_today + estimated_input_tokens > lim.max_tokens_per_day:
                    return False, (
                        f"token_per_day_limit ({tokens_today} used "
                        f"of {lim.max_tokens_per_day} today)"
                    )

            # ── Reserve a slot in the minute window ──
            self._request_window[model_id].append((now, estimated_input_tokens, 0))
            return True, "ok"

    # ─── Post-call Recording ─────────────────────

    def record_success(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        elapsed: float,
    ):
        """Record a successful completion."""
        with self._lock:
            now = time.time()
            # Update the last slot in the minute window with real token counts
            window = self._request_window[model_id]
            if window:
                ts, _, _ = window[-1]
                window[-1] = (ts, input_tokens, output_tokens)

            self._all_calls[model_id].append({
                "ts": now,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "elapsed": elapsed,
                "success": True,
            })

    def record_failure(
        self,
        model_id: str,
        error_type: str = "api_error",
        input_tokens: int = 0,
    ):
        """Record a failed completion (API error, timeout, etc.)."""
        with self._lock:
            now = time.time()
            self._all_calls[model_id].append({
                "ts": now,
                "input_tokens": input_tokens,
                "output_tokens": 0,
                "elapsed": 0.0,
                "success": False,
                "error": error_type,
            })
            # Remove the reservation from window (call failed, don't count against RPM)
            window = self._request_window[model_id]
            if window:
                window.pop()

    def record_failover(
        self,
        from_model: str,
        to_model: str,
        reason: str,
        context_tokens: int,
        task_hint: str = "",
    ):
        """Log a model switch event."""
        event = FailoverEvent(
            timestamp=time.time(),
            from_model=from_model,
            to_model=to_model,
            reason=reason,
            context_tokens=context_tokens,
            task_hint=task_hint,
        )
        with self._lock:
            self._failover_log.append(event)
        logger.info(
            f"[Failover] {from_model} → {to_model} | reason={reason} | "
            f"context_tokens={context_tokens}"
        )

    # ─── Stats / Reporting ───────────────────────

    def get_model_stats(self, model_id: str) -> dict:
        """Get full usage stats for a single model."""
        with self._lock:
            now = time.time()
            calls = list(self._all_calls[model_id])
            lim = self._limits.get(model_id, ModelLimits())

            cutoff_min  = now - self.MINUTE
            cutoff_day  = now - self.DAY
            cutoff_week = now - self.WEEK

            def agg(c_list):
                return {
                    "requests": len(c_list),
                    "input_tokens": sum(c["input_tokens"] for c in c_list),
                    "output_tokens": sum(c["output_tokens"] for c in c_list),
                    "failures": sum(1 for c in c_list if not c["success"]),
                }

            per_min  = agg([c for c in calls if c["ts"] >= cutoff_min])
            per_day  = agg([c for c in calls if c["ts"] >= cutoff_day])
            per_week = agg([c for c in calls if c["ts"] >= cutoff_week])
            total    = agg(calls)

            # RPM window current count
            window = self._request_window[model_id]
            live_cutoff = now - self.MINUTE
            rpm_current = sum(1 for e in window if e[0] >= live_cutoff)

            return {
                "model_id": model_id,
                "limits": {
                    "rpm": lim.rpm,
                    "max_input_tokens": lim.max_input_tokens,
                    "max_tokens_per_minute": lim.max_tokens_per_minute,
                    "max_tokens_per_day": lim.max_tokens_per_day,
                },
                "usage": {
                    "per_minute": per_min,
                    "per_day":    per_day,
                    "per_week":   per_week,
                    "total":      total,
                },
                "live": {
                    "rpm_current": rpm_current,
                    "rpm_limit": lim.rpm,
                    "rpm_pct": round(rpm_current / lim.rpm * 100, 1) if lim.rpm else 0,
                },
            }

    def get_all_stats(self) -> list[dict]:
        """Get stats for all tracked models."""
        # Include models that have been called even if no limits set
        tracked = set(self._limits.keys()) | set(self._all_calls.keys())
        return [self.get_model_stats(mid) for mid in sorted(tracked)]

    def get_failover_log(self, limit: int = 50) -> list[dict]:
        """Return recent failover events, newest first."""
        with self._lock:
            events = list(self._failover_log)
        events.reverse()
        return [
            {
                "timestamp": e.timestamp,
                "from_model": e.from_model,
                "to_model": e.to_model,
                "reason": e.reason,
                "context_tokens": e.context_tokens,
                "task_hint": e.task_hint,
                "ago_seconds": round(time.time() - e.timestamp, 0),
            }
            for e in events[:limit]
        ]

    def estimate_tokens(self, messages: list[dict]) -> int:
        """Rough token estimate: ~4 chars per token."""
        total_chars = sum(len(str(m.get("content", ""))) for m in messages)
        return max(1, total_chars // 4)


# Singleton
rate_limiter = ModelRateLimiter()
