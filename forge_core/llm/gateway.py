"""LLM Gateway - Unified interface for calling multiple LLM providers.

Uses LiteLLM for provider abstraction with intelligent model routing
based on task complexity and cost optimization.
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
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from forge_core.config import MODEL_ROUTING, LLMModel, TaskComplexity, settings

logger = logging.getLogger(__name__)

# Suppress litellm verbosity
litellm.suppress_debug_info = True


class LLMGateway:
    """Central gateway for all LLM calls with routing, caching, and metrics."""

    def __init__(self):
        self._cache: dict[str, str] = {}
        self._metrics: dict[str, list[dict]] = defaultdict(list)
        # _dynamic_routing is set at runtime by the API's LLMConfigStore
        # It maps TaskComplexity -> list[str] (model IDs as strings)
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

    def route_model(self, complexity: TaskComplexity) -> list[str]:
        """Select the best available models for a given task complexity.
        
        Checks _dynamic_routing first (set by API at runtime), then falls
        back to the static MODEL_ROUTING config.
        """
        # Use dynamic routing if set by API
        if self._dynamic_routing is not None:
            tier_models = self._dynamic_routing.get(complexity, self._dynamic_routing.get(TaskComplexity.MEDIUM, []))
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

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((
            litellm.exceptions.RateLimitError,
            litellm.exceptions.APIError,
            litellm.exceptions.Timeout,
            litellm.exceptions.APIConnectionError,
            litellm.exceptions.ServiceUnavailableError,
        )),
        reraise=True,
    )
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
    ) -> str:
        """
        Send a completion request to the appropriate LLM.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Specific model to use (overrides routing)
            complexity: Task complexity for auto-routing
            system_prompt: System message prepended to messages
            temperature: Override default temperature
            max_tokens: Override default max tokens
            use_cache: Whether to use response caching
            json_mode: Request JSON output format

        Returns:
            The LLM's response text
        """
        if model:
            selected_model = model
            fallbacks = None
        else:
            candidates = self.route_model(complexity)
            selected_model = candidates[0]
            fallbacks = candidates[1:] if len(candidates) > 1 else None

        temp = temperature if temperature is not None else settings.temperature
        tokens = max_tokens or settings.max_tokens

        # Build message list
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        # Check cache
        if use_cache:
            cache_key = self._cache_key(selected_model, full_messages)
            if cache_key in self._cache:
                logger.debug(f"Cache hit for model={selected_model}")
                return self._cache[cache_key]

        # Build request kwargs
        def create_kwargs(m):
            k = {
                "model": m,
                "messages": full_messages,
                "temperature": temp,
                "max_tokens": tokens,
            }
            if json_mode:
                k["response_format"] = {"type": "json_object"}
            return k

        # Try models in order
        models_to_try = [selected_model] + (fallbacks or [])
        last_error = None

        for current_model in models_to_try:
            start = time.time()
            try:
                logger.info(f"Attempting LLM call: model={current_model}")
                response = await litellm.acompletion(**create_kwargs(current_model))
                elapsed = time.time() - start

                result = response.choices[0].message.content or ""
                actual_model = getattr(response, "model", current_model)

                # Track metrics
                usage = response.usage
                self._metrics[actual_model].append({
                    "elapsed": elapsed,
                    "input_tokens": getattr(usage, "prompt_tokens", 0),
                    "output_tokens": getattr(usage, "completion_tokens", 0),
                    "timestamp": time.time(),
                })

                logger.info(
                    f"LLM Success: model={actual_model} "
                    f"tokens_in={getattr(usage, 'prompt_tokens', '?')} "
                    f"tokens_out={getattr(usage, 'completion_tokens', '?')} "
                    f"time={elapsed:.2f}s"
                )

                # Cache result
                if use_cache:
                    self._cache[cache_key] = result

                return result

            except Exception as e:
                elapsed = time.time() - start
                last_error = e
                # Don't log full traceback for every fallback attempt
                error_msg = str(e).split('\n')[0][:100]
                logger.warning(f"Model failed: {current_model} after {elapsed:.2f}s. Error: {error_msg}")
                # Continue loop to try next fallback
                continue

        # If we get here, all models (including fallbacks) failed
        logger.error(f"All models in fallback chain failed. Last error: {last_error}")
        raise last_error

    async def complete_with_context(
        self,
        task_description: str,
        context_files: dict[str, str],
        contracts: dict[str, Any],
        system_prompt: str,
        model: Optional[str] = None,
        complexity: TaskComplexity = TaskComplexity.MEDIUM,
    ) -> str:
        """
        High-level completion that bundles task + context files + contracts.
        Used by agents to get contextual code generation.
        """
        # Build a rich context message
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
        )

    def get_metrics(self) -> dict[str, Any]:
        """Return usage metrics for all models."""
        summary = {}
        for model, calls in self._metrics.items():
            total_input = sum(c["input_tokens"] for c in calls)
            total_output = sum(c["output_tokens"] for c in calls)
            total_time = sum(c["elapsed"] for c in calls)
            summary[model] = {
                "total_calls": len(calls),
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "total_time_seconds": round(total_time, 2),
                "avg_time_seconds": round(total_time / len(calls), 2) if calls else 0,
            }
        return summary

    def clear_cache(self):
        self._cache.clear()


# Singleton
llm_gateway = LLMGateway()
