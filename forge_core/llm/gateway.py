"""LLM Gateway - Unified interface for calling multiple LLM providers.

Uses LiteLLM for provider abstraction with intelligent model routing
based on task complexity and cost optimization.

Failover behaviour:
  - Before each attempt the rate limiter is consulted.
  - If RPM or token budget would be exceeded → skip to next fallback immediately.
  - If the API call itself fails → record failure, try next fallback.
  - In both cases the FULL message history (context window) is forwarded to
    the replacement model so it can continue exactly where the previous one left off.
  - Failover events are recorded in the rate_limiter log.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections import defaultdict
from typing import Any, Optional

import litellm

from forge_core.config import MODEL_ROUTING, LLMModel, TaskComplexity, settings
from forge_core.llm.rate_limiter import rate_limiter

logger = logging.getLogger(__name__)

# Suppress litellm verbosity
litellm.suppress_debug_info = True

# Sentinel so we can detect "no result yet" vs empty string
_UNSET = object()


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
        """Set API keys from settings into environment for LiteLLM."""
        import os
        if settings.anthropic_api_key:
            os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key
        if settings.openai_api_key:
            os.environ["OPENAI_API_KEY"] = settings.openai_api_key
        if settings.google_api_key:
            os.environ["GEMINI_API_KEY"] = settings.google_api_key
        if settings.open_router_key:
            os.environ["OPENROUTER_API_KEY"] = settings.open_router_key
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
        import os
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

        Failover chain:
          1. Choose model list from routing.
          2. For each candidate:
             a. Check rate limits. If exceeded → record failover, skip.
             b. Call LiteLLM API.  If error  → record failure/failover, skip.
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

            # ── API call ──────────────────────────────────────────
            start = time.time()
            try:
                logger.info(f"[Gateway] Attempting: model={current_model}")
                response = await litellm.acompletion(**create_kwargs(current_model))
                elapsed = time.time() - start

                result = response.choices[0].message.content or ""
                actual_model = getattr(response, "model", current_model)

                # Record successful usage
                usage = response.usage
                input_tok  = getattr(usage, "prompt_tokens",     0) or estimated_tokens
                output_tok = getattr(usage, "completion_tokens", 0)

                rate_limiter.record_success(current_model, input_tok, output_tok, elapsed)

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

                return result

            except Exception as e:
                elapsed = time.time() - start
                last_error = e

                # Classify error for the log
                err_type = type(e).__name__
                try:
                    import litellm.exceptions as lx
                    if isinstance(e, lx.RateLimitError):
                        err_type = "rpm_limit"
                    elif isinstance(e, (lx.Timeout, lx.APIConnectionError)):
                        err_type = "timeout"
                    elif isinstance(e, lx.ServiceUnavailableError):
                        err_type = "unavailable"
                except Exception:
                    pass

                error_msg = str(e).split('\n')[0][:120]
                logger.warning(
                    f"[Gateway] Failed: {current_model} after {elapsed:.2f}s. "
                    f"Error: {error_msg}"
                )

                rate_limiter.record_failure(current_model, err_type, estimated_tokens)

                # Record failover event if there's a next model to try
                next_idx = models_to_try.index(current_model) + 1
                if next_idx < len(models_to_try):
                    rate_limiter.record_failover(
                        from_model=current_model,
                        to_model=models_to_try[next_idx],
                        reason=err_type,
                        context_tokens=estimated_tokens,
                        task_hint=task_hint,
                    )

                previous_model = current_model
                continue   # Try next model with the SAME full_messages

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
