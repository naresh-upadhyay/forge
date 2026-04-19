"""FORGE Configuration - Central settings for the entire system."""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class LLMProvider(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"
    LOCAL = "local"
    OPENROUTER = "openrouter"


class LLMModel(str, Enum):
    # Anthropic
    CLAUDE_OPUS = "claude-opus-4-20250514"
    CLAUDE_SONNET = "claude-sonnet-4-20250514"
    CLAUDE_HAIKU = "claude-haiku-4-5-20251001"
    # OpenAI
    GPT4O = "gpt-4o"
    GPT4O_MINI = "gpt-4o-mini"
    O1 = "o1"
    # Google
    GEMINI_PRO = "gemini/gemini-2.5-pro"
    GEMINI_FLASH = "gemini/gemini-2.5-flash"
    # OpenRouter
    OR_TRINITY = "openrouter/arcee-ai/trinity-large-preview:free"
    OR_NEMOTRON = "openrouter/nvidia/nemotron-3-super-120b-a12b:free"
    OR_GLM = "openrouter/z-ai/glm-4.5-air:free"
    OR_GPT_OSS = "openrouter/openai/gpt-oss-120b:free"
    OR_MINIMAX = "openrouter/minimax/minimax-m2.5:free"
    OR_QWEN_CODER = "openrouter/qwen/qwen3-coder:free"


class TaskComplexity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# Maps complexity levels to preferred models (in order of preference)
MODEL_ROUTING = {
    TaskComplexity.LOW: [LLMModel.OR_NEMOTRON, LLMModel.OR_GPT_OSS, LLMModel.OR_GLM, LLMModel.OR_TRINITY],
    TaskComplexity.MEDIUM: [LLMModel.OR_NEMOTRON, LLMModel.OR_GPT_OSS, LLMModel.OR_GLM, LLMModel.OR_TRINITY],
    TaskComplexity.HIGH: [LLMModel.OR_NEMOTRON, LLMModel.OR_GPT_OSS, LLMModel.OR_GLM, LLMModel.OR_TRINITY],
    TaskComplexity.CRITICAL: [LLMModel.OR_NEMOTRON, LLMModel.OR_GPT_OSS, LLMModel.OR_GLM, LLMModel.OR_TRINITY],
}


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # --- App ---
    app_name: str = "FORGE"
    app_version: str = "1.0.0"
    debug: bool = False
    base_dir: Path = Field(default_factory=lambda: Path(__file__).parent.parent)

    # --- Server ---
    api_host: str = "0.0.0.0"
    api_port: int = 8010
    api_cors_origins: list[str] = ["*"]

    # --- LLM API Keys ---
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    open_router_key: Optional[str] = None
    open_base_url: Optional[str] = None

    # --- LLM Defaults ---
    default_architect_model: LLMModel = LLMModel.OR_NEMOTRON
    default_builder_model: LLMModel = LLMModel.OR_QWEN_CODER
    default_reviewer_model: LLMModel = LLMModel.OR_TRINITY
    default_tester_model: LLMModel = LLMModel.OR_QWEN_CODER
    default_fixer_model: LLMModel = LLMModel.OR_QWEN_CODER
    default_doc_model: LLMModel = LLMModel.OR_GLM
    max_tokens: int = 8192
    temperature: float = 0.1

    # --- Database ---
    database_url: str = "sqlite+aiosqlite:///./forge.db"

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- Workspace ---
    workspace_dir: Path = Field(default_factory=lambda: Path.home() / ".forge" / "workspaces")
    max_parallel_agents: int = 5
    agent_timeout_seconds: int = 300

    # --- Quality ---
    min_review_score: float = 7.0  # 1-10 scale
    max_fix_attempts: int = 3
    require_tests: bool = True

    # --- Docker Sandbox ---
    sandbox_enabled: bool = False
    sandbox_image: str = "forge-sandbox:latest"
    sandbox_timeout: int = 120

    model_config = {"env_prefix": "FORGE_", "env_file": ".env", "extra": "ignore"}

    def get_api_key(self, provider: LLMProvider) -> Optional[str]:
        return {
            LLMProvider.ANTHROPIC: self.anthropic_api_key,
            LLMProvider.OPENAI: self.openai_api_key,
            LLMProvider.GOOGLE: self.google_api_key,
            LLMProvider.OPENROUTER: self.open_router_key,
        }.get(provider)


settings = Settings()
