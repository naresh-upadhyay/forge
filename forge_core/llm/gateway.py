"""LLM Gateway - Unified interface for calling multiple LLM providers.

Uses LiteLLM for provider abstraction with intelligent model routing
based on task complexity and cost optimization.

Failover behaviour:
  - Before each attempt the rate limiter is consulted.
  - If RPM or token budget would be exceeded → skip to next fallback immediately.
  - If the API call itself fails with a rate-limit error → the key_pool rotates
    to the next available API key for the same provider and the same model is
    retried (up to MAX_KEY_RETRIES times) before moving to the next model.
  - Any other API error → record failure, try next model.
  - In all cases the FULL message history (context window) is forwarded to the
    replacement model so it can continue exactly where the previous one left off.
  - Failover events are recorded in the rate_limiter log.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from collections import defaultdict
from typing import Any, Optional

import litellm

from forge_core.config import MODEL_ROUTING, LLMModel, TaskComplexity, settings
from forge_core.llm.rate_limiter import rate_limiter
from forge_core.llm.key_pool import key_pool


async def _persist_key_usage(
    provider_id: str,
    label: str,
    tokens_in: int,
    tokens_out: int,
    errors: int = 0,
    api_key: str = "",
) -> None:
    """Fire-and-forget: persist key usage delta to SQLite."""
    try:
        from forge_core.storage import llm_config_storage
        await llm_config_storage.update_key_usage(
            provider_id, label,
            api_key=api_key,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            errors=errors,
        )
    except Exception as exc:
        logger.debug(f"[Gateway] DB key-usage persist failed (non-critical): {exc}")

logger = logging.getLogger(__name__)

# Suppress litellm verbosity
litellm.suppress_debug_info = True

# Sentinel so we can detect "no result yet" vs empty string
_UNSET = object()

# How many times to retry a model with a fresh API key before giving up on it
MAX_KEY_RETRIES = 5

# Map from litellm model-string prefix → provider_id (used by key_pool)
_PROVIDER_BY_PREFIX: dict[str, str] = {
    "claude":       "anthropic",
    "anthropic":    "anthropic",
    "gpt":          "openai",
    "o1":           "openai",
    "openai":       "openai",
    "gemini":       "google",
    "openrouter":   "openrouter",
}


def _provider_for_model(model: str) -> Optional[str]:
    """Identify the key_pool provider_id for a given model string."""
    lower = model.lower()
    for prefix, pid in _PROVIDER_BY_PREFIX.items():
        if lower.startswith(prefix) or f"/{prefix}" in lower:
            return pid
    return None


def _apply_key_to_env(provider_id: str, api_key: str) -> None:
    """Inject a specific API key into the environment for LiteLLM."""
    if provider_id == "anthropic":
        os.environ["ANTHROPIC_API_KEY"] = api_key
    elif provider_id == "openai":
        os.environ["OPENAI_API_KEY"] = api_key
    elif provider_id == "google":
        os.environ["GEMINI_API_KEY"] = api_key
    elif provider_id == "openrouter":
        os.environ["OPENROUTER_API_KEY"] = api_key
    else:
        env_prefix = provider_id.upper().replace("-", "_")
        os.environ[f"{env_prefix}_API_KEY"] = api_key


class LLMGateway:
    """Central gateway for all LLM calls with routing, rate-limiting, caching, and metrics."""

    def __init__(self):
        self._cache: dict[str, str] = {}
        self._metrics: dict[str, list[dict]] = defaultdict(list)
        # _dynamic_routing is set at runtime by the API's LLMConfigStore
        # It maps TaskComplexity → list[str] (model IDs as strings)
        self._dynamic_routing: Optional[dict] = None
        self._configure_keys()

    def _configure_keys(self):
        """Set API keys from key_pool (or settings fallback) into environment for LiteLLM."""
        providers = {
            "anthropic": ("ANTHROPIC_API_KEY",   settings.anthropic_api_key),
            "openai":    ("OPENAI_API_KEY",       settings.openai_api_key),
            "google":    ("GEMINI_API_KEY",       settings.google_api_key),
            "openrouter":("OPENROUTER_API_KEY",   settings.open_router_key),
        }
        for provider_id, (env_var, fallback) in providers.items():
            active = key_pool.get_active_key(provider_id)
            if active:
                os.environ[env_var] = active
            elif fallback:
                os.environ[env_var] = fallback

        if settings.open_base_url:
            os.environ["OPENROUTER_API_BASE"] = settings.open_base_url

    # ─── Model Routing ───────────────────────────

    def route_model(self, complexity: TaskComplexity) -> list[str]:
        """Select the best available models for a given task complexity.

        Checks _dynamic_routing first (set by API at runtime), then falls
        back to the static MODEL_ROUTING config.
        """
        # Use dynamic routing if set by API
        if self._dynamic_routing is not None:
            tier_models = self._dynamic_routing.get(
                complexity,
                self._dynamic_routing.get(TaskComplexity.MEDIUM, [])
            )
            if tier_models:
                return list(tier_models)

        # Static config routing
        candidates = MODEL_ROUTING.get(complexity, MODEL_ROUTING[TaskComplexity.MEDIUM])
        available = [m.value for m in candidates if self._is_model_available(m)]
        if available:
            return available

        # Fallback to any tier
        available = []
        for tier in MODEL_ROUTING.values():
            for m in tier:
                if self._is_model_available(m) and m.value not in available:
                    available.append(m.value)
        if available:
            return available

        raise RuntimeError("No LLM models available. Set at least one API key.")

    def _is_model_available(self, model: LLMModel) -> bool:
        """Check if a model's provider has an API key configured."""
        if "claude" in model.value or "anthropic" in model.value:
            return bool(os.environ.get("ANTHROPIC_API_KEY"))
        elif "gpt" in model.value or "o1" in model.value:
            return bool(os.environ.get("OPENAI_API_KEY"))
        elif "gemini" in model.value:
            return bool(os.environ.get("GEMINI_API_KEY"))
        elif "openrouter" in model.value:
            return bool(os.environ.get("OPENROUTER_API_KEY"))
        return False

    def _cache_key(self, model: str, messages: list[dict], **kwargs) -> str:
        """Generate a cache key for deduplication."""
        content = json.dumps({"model": model, "messages": messages}, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()

    # ─── Primary Completion Entry Point ──────────

    async def complete(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        complexity: TaskComplexity = TaskComplexity.MEDIUM,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        use_cache: bool = True,
        json_mode: bool = False,
        task_hint: str = "",    # short description used in failover log
    ) -> str:
        """
        Send a completion request to the appropriate LLM.

        Failover chain (two-level):
          1. Choose model list from routing.
          2. For each candidate model:
             a. Check rate limits. If exceeded → record failover, skip model.
             b. Attempt up to MAX_KEY_RETRIES times, rotating API keys on 429:
                - On RateLimitError  → key_pool rotates key, retry same model.
                - On other error     → record failure, break inner loop.
             c. On success → record usage, return result.
          3. The full `full_messages` (context window) is forwarded to every
             candidate so no context is lost during failover.

        Args:
            messages:      List of message dicts with 'role' and 'content'
            model:         Specific model to use (overrides routing)
            complexity:    Task complexity for auto-routing
            system_prompt: System message prepended to messages
            temperature:   Override default temperature
            max_tokens:    Override default max tokens
            use_cache:     Whether to use response caching
            json_mode:     Request JSON output format
            task_hint:     Short description for failover log

        Returns:
            The LLM's response text
        """
        if model:
            models_to_try = [model]
        else:
            candidates = self.route_model(complexity)
            models_to_try = candidates

        temp   = temperature if temperature is not None else settings.temperature
        tokens = max_tokens or settings.max_tokens

        # Build full message list (shared across all fallbacks — this IS the context window)
        full_messages: list[dict] = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        # Estimate tokens for rate-limit pre-check
        estimated_tokens = rate_limiter.estimate_tokens(full_messages)

        # Cache check (use first model in chain as key)
        cache_key: Optional[str] = None
        if use_cache:
            cache_key = self._cache_key(models_to_try[0], full_messages)
            if cache_key in self._cache:
                logger.debug(f"Cache hit for model={models_to_try[0]}")
                return self._cache[cache_key]

        def create_kwargs(m: str) -> dict:
            k = {
                "model": m,
                "messages": full_messages,   # ← same context for every fallback
                "temperature": temp,
                "max_tokens": tokens,
            }
            if json_mode:
                k["response_format"] = {"type": "json_object"}
            return k

        last_error: Optional[Exception] = None
        previous_model: Optional[str] = None

        for current_model in models_to_try:

            # ── Rate-limit pre-check ──────────────────────────────
            allowed, reason = rate_limiter.check_and_reserve(current_model, estimated_tokens)
            if not allowed:
                logger.warning(
                    f"[RateLimit] Skipping {current_model}: {reason}. "
                    f"Falling back to next model."
                )
                if previous_model:
                    rate_limiter.record_failover(
                        from_model=previous_model,
                        to_model=current_model,
                        reason=reason.split(" ")[0],   # e.g. "rpm_limit"
                        context_tokens=estimated_tokens,
                        task_hint=task_hint,
                    )
                previous_model = current_model
                continue

            # ── Identify provider for key rotation ───────────────
            provider_id = _provider_for_model(current_model)

            # ── Inner key-rotation retry loop ─────────────────────
            model_succeeded = False
            for key_attempt in range(MAX_KEY_RETRIES):
                # Ensure the active key for this provider is in env
                if provider_id:
                    active_key = key_pool.get_active_key(provider_id)
                    if active_key:
                        _apply_key_to_env(provider_id, active_key)
                    elif key_attempt > 0:
                        # All keys exhausted for this provider
                        logger.warning(
                            f"[KeyPool] {provider_id}: all keys exhausted — "
                            f"skipping model {current_model}"
                        )
                        break

                start = time.time()
                try:
                    logger.info(
                        f"[Gateway] Attempting: model={current_model} "
                        f"key_attempt={key_attempt + 1}/{MAX_KEY_RETRIES}"
                    )
                    response = await litellm.acompletion(**create_kwargs(current_model))
                    elapsed = time.time() - start

                    result = response.choices[0].message.content or ""
                    actual_model = getattr(response, "model", current_model)

                    # Record successful usage
                    usage = response.usage
                    input_tok  = getattr(usage, "prompt_tokens",     0) or estimated_tokens
                    output_tok = getattr(usage, "completion_tokens", 0)

                    rate_limiter.record_success(current_model, input_tok, output_tok, elapsed)

                    # ── Per-key usage tracking ────────────────────────────
                    if provider_id:
                        used_key = os.environ.get(
                            {
                                "anthropic":  "ANTHROPIC_API_KEY",
                                "openai":     "OPENAI_API_KEY",
                                "google":     "GEMINI_API_KEY",
                                "openrouter": "OPENROUTER_API_KEY",
                            }.get(provider_id, ""),
                            "",
                        )
                        label = key_pool.record_key_usage(
                            provider_id, used_key, input_tok, output_tok
                        )
                        if label:
                            asyncio.create_task(
                                _persist_key_usage(
                                    provider_id, label, input_tok, output_tok,
                                    api_key=used_key,
                                )
                            )

                    # Also keep legacy _metrics
                    self._metrics[actual_model].append({
                        "elapsed":       elapsed,
                        "input_tokens":  input_tok,
                        "output_tokens": output_tok,
                        "timestamp":     time.time(),
                    })

                    logger.info(
                        f"[Gateway] Success: model={actual_model} "
                        f"tokens_in={input_tok} tokens_out={output_tok} "
                        f"time={elapsed:.2f}s"
                    )

                    # Log failover if we switched models
                    if previous_model and previous_model != current_model:
                        rate_limiter.record_failover(
                            from_model=previous_model,
                            to_model=current_model,
                            reason="fallback_success",
                            context_tokens=input_tok,
                            task_hint=task_hint,
                        )

                    if use_cache and cache_key:
                        self._cache[cache_key] = result

                    model_succeeded = True
                    return result

                except Exception as e:
                    elapsed = time.time() - start
                    last_error = e

                    # Classify error
                    err_type = type(e).__name__
                    is_rate_limit = False
                    try:
                        import litellm.exceptions as lx
                        if isinstance(e, lx.RateLimitError):
                            err_type = "rpm_limit"
                            is_rate_limit = True
                        elif isinstance(e, (lx.Timeout, lx.APIConnectionError)):
                            err_type = "timeout"
                        elif isinstance(e, lx.ServiceUnavailableError):
                            err_type = "unavailable"
                    except Exception:
                        pass

                    # Also detect rate-limit by status code / message for providers
                    # that don't raise litellm.RateLimitError explicitly
                    if not is_rate_limit:
                        err_str = str(e).lower()
                        if "429" in err_str or "rate limit" in err_str or "quota" in err_str:
                            is_rate_limit = True
                            err_type = "rpm_limit"

                    error_msg = str(e).split('\n')[0][:120]
                    logger.warning(
                        f"[Gateway] Failed: {current_model} "
                        f"(key_attempt {key_attempt + 1}) after {elapsed:.2f}s. "
                        f"Error: {error_msg}"
                    )

                    if is_rate_limit and provider_id:
                        # ── Key rotation ───────────────────────────
                        current_key = os.environ.get(
                            {
                                "anthropic":  "ANTHROPIC_API_KEY",
                                "openai":     "OPENAI_API_KEY",
                                "google":     "GEMINI_API_KEY",
                                "openrouter": "OPENROUTER_API_KEY",
                            }.get(provider_id, ""),
                            "",
                        )
                        # Record the error against the key that just failed
                        err_label = key_pool.record_key_error(provider_id, current_key)
                        if err_label:
                            asyncio.create_task(
                                _persist_key_usage(
                                    provider_id, err_label, 0, 0, errors=1
                                )
                            )

                        new_key = key_pool.mark_rate_limited(provider_id, current_key)
                        if new_key:
                            logger.info(
                                f"[Gateway] Key rotated for {provider_id} — "
                                f"retrying {current_model}"
                            )
                            _apply_key_to_env(provider_id, new_key)
                            rate_limiter.record_failure(current_model, err_type, estimated_tokens)
                            continue   # retry same model with new key
                        else:
                            logger.warning(
                                f"[Gateway] {provider_id}: no more keys — "
                                f"giving up on {current_model}"
                            )
                            rate_limiter.record_failure(current_model, err_type, estimated_tokens)
                            break      # all keys exhausted → try next model
                    else:
                        # Non-rate-limit error — record against key and move on
                        if provider_id:
                            current_key = os.environ.get(
                                {
                                    "anthropic":  "ANTHROPIC_API_KEY",
                                    "openai":     "OPENAI_API_KEY",
                                    "google":     "GEMINI_API_KEY",
                                    "openrouter": "OPENROUTER_API_KEY",
                                }.get(provider_id, ""),
                                "",
                            )
                            err_label = key_pool.record_key_error(provider_id, current_key)
                            if err_label:
                                asyncio.create_task(
                                    _persist_key_usage(
                                        provider_id, err_label, 0, 0, errors=1
                                    )
                                )
                        rate_limiter.record_failure(current_model, err_type, estimated_tokens)
                        break

            if not model_succeeded:
                # Record failover to next model (if one exists)
                next_idx = models_to_try.index(current_model) + 1
                if next_idx < len(models_to_try):
                    rate_limiter.record_failover(
                        from_model=current_model,
                        to_model=models_to_try[next_idx],
                        reason=err_type if 'err_type' in dir() else "error",
                        context_tokens=estimated_tokens,
                        task_hint=task_hint,
                    )
                previous_model = current_model

        # All models exhausted
        logger.error(f"[Gateway] All models failed. Last error: {last_error}")
        raise last_error or RuntimeError("All models in fallback chain failed")

    # ─── High-level Context Completion ───────────

    async def complete_with_context(
        self,
        task_description: str,
        context_files: dict[str, str],
        contracts: dict[str, Any],
        system_prompt: str,
        model: Optional[str] = None,
        complexity: TaskComplexity = TaskComplexity.MEDIUM,
        task_hint: str = "",
    ) -> str:
        """
        High-level completion that bundles task + context files + contracts.
        Used by agents to get contextual code generation.
        The full context is passed on failover so the replacement model gets
        exactly the same information.
        """
        context_parts = []

        if contracts:
            context_parts.append(
                "## Interface Contracts (you MUST conform to these)\n"
                f"```json\n{json.dumps(contracts, indent=2)}\n```"
            )

        if context_files:
            context_parts.append("## Existing Code Context")
            for filepath, content in context_files.items():
                context_parts.append(f"### {filepath}\n```\n{content}\n```")

        context_block = "\n\n".join(context_parts)

        messages = [
            {
                "role": "user",
                "content": f"{context_block}\n\n## Task\n{task_description}",
            }
        ]

        return await self.complete(
            messages=messages,
            model=model,
            complexity=complexity,
            system_prompt=system_prompt,
            task_hint=task_hint or task_description[:80],
        )

    # ─── Metrics ─────────────────────────────────

    def get_metrics(self) -> dict[str, Any]:
        """Return basic usage metrics for all models (legacy format)."""
        summary = {}
        for model, calls in self._metrics.items():
            total_input  = sum(c["input_tokens"]  for c in calls)
            total_output = sum(c["output_tokens"] for c in calls)
            total_time   = sum(c["elapsed"]       for c in calls)
            summary[model] = {
                "total_calls":         len(calls),
                "total_input_tokens":  total_input,
                "total_output_tokens": total_output,
                "total_time_seconds":  round(total_time, 2),
                "avg_time_seconds":    round(total_time / len(calls), 2) if calls else 0,
            }
        return summary

    def get_rich_metrics(self) -> list[dict]:
        """Return rich per-model stats from the rate limiter (minute/day/week)."""
        return rate_limiter.get_all_stats()

    def get_failover_log(self, limit: int = 50) -> list[dict]:
        return rate_limiter.get_failover_log(limit)

    def clear_cache(self):
        self._cache.clear()


# Singleton
llm_gateway = LLMGateway()
