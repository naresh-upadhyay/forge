"""FORGE API - FastAPI application with REST endpoints and WebSocket for real-time updates."""

from __future__ import annotations

import sys
import asyncio

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import json
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from forge_core.config import settings, MODEL_ROUTING, TaskComplexity, LLMModel
from forge_core.events import event_bus
from forge_core.llm.gateway import llm_gateway
from forge_core.llm.rate_limiter import rate_limiter, ModelLimits
from forge_core.models import BuildEvent, ProjectStatus
from forge_core.orchestrator import orchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("forge.api")


# ──────────────────────────────────────────────
# Runtime LLM Config Store
# ──────────────────────────────────────────────

class LLMConfigStore:
    """In-memory runtime configuration for LLM providers, models and routing."""

    def __init__(self):
        self._providers: dict[str, dict] = {
            "openrouter": {
                "id": "openrouter",
                "name": "OpenRouter",
                "api_key": settings.open_router_key or "",
                "base_url": settings.open_base_url or "https://openrouter.ai/api/v1/",
                "enabled": bool(settings.open_router_key),
            },
            "anthropic": {
                "id": "anthropic",
                "name": "Anthropic",
                "api_key": settings.anthropic_api_key or "",
                "base_url": "https://api.anthropic.com",
                "enabled": bool(settings.anthropic_api_key),
            },
            "openai": {
                "id": "openai",
                "name": "OpenAI",
                "api_key": settings.openai_api_key or "",
                "base_url": "https://api.openai.com/v1",
                "enabled": bool(settings.openai_api_key),
            },
            "google": {
                "id": "google",
                "name": "Google (Gemini)",
                "api_key": settings.google_api_key or "",
                "base_url": "https://generativelanguage.googleapis.com",
                "enabled": bool(settings.google_api_key),
            },
        }

        # Build default models list from LLMModel enum
        self._models: dict[str, dict] = {}
        for m in LLMModel:
            provider = self._detect_provider(m.value)
            self._models[m.value] = {
                "id": m.value,
                "name": m.name.replace("_", " ").title(),
                "model_id": m.value,
                "provider": provider,
                "enabled": True,
                "custom": False,
                "description": "",
                # Rate-limit fields
                "rpm_limit": 0,
                "max_input_tokens": 0,
                "max_tokens_per_minute": 0,
                "max_tokens_per_day": 0,
            }

        # Build default routing from config
        self._routing: dict[str, list[str]] = {}
        for complexity, models in MODEL_ROUTING.items():
            self._routing[complexity.value] = [m.value for m in models]

    def _detect_provider(self, model_id: str) -> str:
        if "claude" in model_id or "anthropic" in model_id:
            return "anthropic"
        elif "gpt" in model_id or "o1" in model_id or "openai" in model_id:
            return "openai"
        elif "gemini" in model_id:
            return "google"
        elif "openrouter" in model_id:
            return "openrouter"
        return "openrouter"

    def _apply_provider_env(self, provider_id: str):
        """Apply a provider's credentials to environment variables for LiteLLM."""
        p = self._providers[provider_id]
        key = p.get("api_key", "")
        url = p.get("base_url", "")
        if provider_id == "openrouter":
            if key: os.environ["OPENROUTER_API_KEY"] = key
            if url: os.environ["OPENROUTER_API_BASE"] = url
        elif provider_id == "anthropic":
            if key: os.environ["ANTHROPIC_API_KEY"] = key
        elif provider_id == "openai":
            if key: os.environ["OPENAI_API_KEY"] = key
        elif provider_id == "google":
            if key: os.environ["GEMINI_API_KEY"] = key
        else:
            # Custom provider: expose via per-provider env vars that LiteLLM
            # can pick up when using openai-compatible format:
            #   model = "openai/<model_name>"
            #   OPENAI_API_KEY + OPENAI_API_BASE
            # We namespace with the provider id so multiple customs don't clash.
            env_prefix = provider_id.upper().replace("-", "_")
            if key: os.environ[f"{env_prefix}_API_KEY"] = key
            if url: os.environ[f"{env_prefix}_API_BASE"] = url
        llm_gateway._configure_keys()

    # --- Providers ---
    def get_providers(self) -> list[dict]:
        return list(self._providers.values())

    def add_provider(self, data: dict) -> dict:
        provider_id = data["id"].lower().strip().replace(" ", "-")
        if provider_id in self._providers:
            raise ValueError(f"Provider '{provider_id}' already exists")
        entry = {
            "id": provider_id,
            "name": data.get("name", provider_id),
            "api_key": data.get("api_key", ""),
            "base_url": data.get("base_url", ""),
            "enabled": bool(data.get("api_key", "")),
            "custom": True,
            "model_prefix": data.get("model_prefix", ""),
            "description": data.get("description", ""),
            "compatible_with": data.get("compatible_with", "openai"),  # openai|anthropic|custom
        }
        self._providers[provider_id] = entry
        self._apply_provider_env(provider_id)
        return entry

    def update_provider(self, provider_id: str, data: dict) -> dict:
        if provider_id not in self._providers:
            raise KeyError(f"Provider '{provider_id}' not found")
        self._providers[provider_id].update(data)
        self._apply_provider_env(provider_id)
        return self._providers[provider_id]

    def delete_provider(self, provider_id: str):
        builtin = {"openrouter", "anthropic", "openai", "google"}
        if provider_id in builtin:
            raise ValueError(f"Cannot delete built-in provider '{provider_id}'")
        if provider_id not in self._providers:
            raise KeyError(f"Provider '{provider_id}' not found")
        del self._providers[provider_id]

    # --- Models ---
    def get_models(self) -> list[dict]:
        return list(self._models.values())

    def add_model(self, data: dict) -> dict:
        model_id = data["model_id"]
        if model_id in self._models:
            raise ValueError(f"Model '{model_id}' already exists")
        entry = {
            "id": model_id,
            "name": data.get("name", model_id),
            "model_id": model_id,
            "provider": data.get("provider", self._detect_provider(model_id)),
            "enabled": data.get("enabled", True),
            "custom": True,
            "description": data.get("description", ""),
            "rpm_limit": data.get("rpm_limit", 0),
            "max_input_tokens": data.get("max_input_tokens", 0),
            "max_tokens_per_minute": data.get("max_tokens_per_minute", 0),
            "max_tokens_per_day": data.get("max_tokens_per_day", 0),
        }
        self._models[model_id] = entry
        return entry

    def update_model(self, model_id: str, data: dict) -> dict:
        if model_id not in self._models:
            raise KeyError(f"Model '{model_id}' not found")
        self._models[model_id].update(data)
        # Sync rate limits to rate_limiter singleton
        m = self._models[model_id]
        rate_limiter.set_limits(model_id, ModelLimits(
            rpm=m.get("rpm_limit", 0),
            max_input_tokens=m.get("max_input_tokens", 0),
            max_tokens_per_minute=m.get("max_tokens_per_minute", 0),
            max_tokens_per_day=m.get("max_tokens_per_day", 0),
        ))
        return self._models[model_id]

    def delete_model(self, model_id: str):
        if model_id not in self._models:
            raise KeyError(f"Model '{model_id}' not found")
        del self._models[model_id]
        # Remove from routing
        for tier in self._routing.values():
            if model_id in tier:
                tier.remove(model_id)

    # --- Routing ---
    def get_routing(self) -> dict[str, list[str]]:
        return dict(self._routing)

    def update_routing(self, routing: dict[str, list[str]]):
        self._routing.update(routing)
        # Rebuild the live MODEL_ROUTING used by the gateway
        import forge_core.config as cfg
        new_routing = {}
        for complexity in TaskComplexity:
            tier_models = self._routing.get(complexity.value, [])
            # Build LLMModel-compatible list (custom strings OK)
            new_routing[complexity] = tier_models
        # Patch gateway to use updated routing
        llm_gateway._dynamic_routing = new_routing


_llm_config = LLMConfigStore()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown lifecycle."""
    logger.info(f"FORGE v{settings.app_version} starting...")
    settings.workspace_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Workspace directory: {settings.workspace_dir}")
    await orchestrator.ensure_initialized()
    yield
    logger.info("FORGE shutting down...")


app = FastAPI(
    title="FORGE API",
    description="Factory for Orchestrated Reliable Generation of Enterprise-software",
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────
# Request/Response Models
# ──────────────────────────────────────────────

class CreateProjectRequest(BaseModel):
    name: str
    tech_stack: str = "flutter"
    backend_stack: Optional[str] = None
    description: str = ""


class BuildFromRequirementsRequest(BaseModel):
    requirements: str


class BuildFromHtmlRequest(BaseModel):
    html_files: dict[str, str]


class FeedbackRequest(BaseModel):
    description: str
    feedback_type: str = "general"
    screen_id: Optional[str] = None


class ProjectSummary(BaseModel):
    id: str
    name: str
    status: str
    tech_stack: str
    progress: float
    total_work_units: int
    completed_work_units: int
    created_at: str


# ──────────────────────────────────────────────
# Project Endpoints
# ──────────────────────────────────────────────

@app.post("/api/projects", status_code=201)
async def create_project(req: CreateProjectRequest):
    """Create a new project."""
    project = await orchestrator.create_project(
        name=req.name,
        tech_stack=req.tech_stack,
        backend_stack=req.backend_stack,
        description=req.description,
    )
    return {"id": project.id, "name": project.name, "status": project.status.value}


@app.get("/api/projects")
async def list_projects():
    """List all projects."""
    projects = orchestrator.list_projects()
    return [
        ProjectSummary(
            id=p.id,
            name=p.name,
            status=p.status.value,
            tech_stack=p.tech_stack.value,
            progress=p.progress_percent,
            total_work_units=p.total_work_units,
            completed_work_units=p.completed_work_units,
            created_at=p.created_at.isoformat(),
        ).model_dump()
        for p in projects
    ]


@app.get("/api/projects/{project_id}")
async def get_project(project_id: str):
    """Get detailed project info."""
    project = orchestrator.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    data = project.model_dump(mode="json")
    data["progress"] = project.progress_percent
    return data


@app.get("/api/projects/{project_id}/files")
async def get_project_files(project_id: str):
    """Get all generated files for a project."""
    files = orchestrator.get_project_files(project_id)
    if not files:
        raise HTTPException(404, "No files found")
    return {"files": files, "count": len(files)}


@app.get("/api/projects/{project_id}/tree")
async def get_project_tree(project_id: str):
    """Get the file tree for a project."""
    tree = orchestrator.get_project_tree(project_id)
    return {"tree": tree}


@app.get("/api/projects/{project_id}/file/{filepath:path}")
async def get_single_file(project_id: str, filepath: str):
    """Get a single file's content."""
    files = orchestrator.get_project_files(project_id)
    if filepath not in files:
        raise HTTPException(404, "File not found")
    return {"path": filepath, "content": files[filepath]}


@app.get("/api/projects/{project_id}/events")
async def get_project_events(project_id: str):
    """Get build event history for a project."""
    events = event_bus.get_history(project_id)
    return [e.model_dump(mode="json") for e in events]


@app.get("/api/projects/{project_id}/blueprint")
async def get_project_blueprint(project_id: str):
    """Get the project blueprint."""
    project = orchestrator.get_project(project_id)
    if not project or not project.blueprint:
        raise HTTPException(404, "Blueprint not found")
    return project.blueprint.model_dump(mode="json")


@app.get("/api/projects/{project_id}/work-units")
async def get_work_units(project_id: str):
    """Get all work units for a project."""
    project = orchestrator.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return [wu.model_dump(mode="json") for wu in project.work_units]


# ──────────────────────────────────────────────
# Build Endpoints
# ──────────────────────────────────────────────

@app.post("/api/projects/{project_id}/build/requirements")
async def build_from_requirements(project_id: str, req: BuildFromRequirementsRequest):
    """Start building a project from business requirements (async)."""
    project = orchestrator.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if project.status not in [ProjectStatus.CREATED, ProjectStatus.COMPLETED, ProjectStatus.FAILED]:
        raise HTTPException(409, f"Project is already {project.status.value}")

    # Run build in background
    asyncio.create_task(_run_build_requirements(project_id, req.requirements))

    return {"message": "Build started", "project_id": project_id, "status": "building"}


@app.post("/api/projects/{project_id}/build/html")
async def build_from_html(project_id: str, req: BuildFromHtmlRequest):
    """Start building a project from HTML mockups (async)."""
    project = orchestrator.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if project.status not in [ProjectStatus.CREATED, ProjectStatus.COMPLETED, ProjectStatus.FAILED]:
        raise HTTPException(409, f"Project is already {project.status.value}")

    asyncio.create_task(_run_build_html(project_id, req.html_files))

    return {"message": "Build started", "project_id": project_id, "status": "building"}


@app.post("/api/projects/{project_id}/rebuild")
async def rebuild_project(project_id: str):
    """Re-trigger a build using stored mockups/requirements."""
    project = orchestrator.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    if project.input_type == "mockups":
        asyncio.create_task(_run_build_html(project_id, project.input_mockups))
    elif project.input_type == "requirements":
        asyncio.create_task(_run_build_requirements(project_id, project.input_text))
    else:
        raise HTTPException(400, "Project does not have enough input data for a rebuild")

    return {"message": "Rebuild started", "project_id": project_id, "status": "building"}


@app.post("/api/projects/{project_id}/build/upload")
async def build_from_upload(
    project_id: str,
    files: list[UploadFile] = File(...),
):
    """Upload HTML mockup files and start building."""
    project = orchestrator.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    html_files = {}
    for f in files:
        content = await f.read()
        html_files[f.filename or "unknown.html"] = content.decode("utf-8", errors="ignore")

    asyncio.create_task(_run_build_html(project_id, html_files))

    return {
        "message": f"Build started with {len(html_files)} files",
        "project_id": project_id,
        "files": list(html_files.keys()),
    }


# ──────────────────────────────────────────────
# Feedback Endpoint
# ──────────────────────────────────────────────

@app.post("/api/projects/{project_id}/feedback")
async def submit_feedback(project_id: str, req: FeedbackRequest):
    """Submit feedback on a completed build."""
    project = orchestrator.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    asyncio.create_task(
        orchestrator.submit_feedback(
            project_id=project_id,
            description=req.description,
            feedback_type=req.feedback_type,
            screen_id=req.screen_id,
        )
    )

    return {"message": "Feedback submitted, fix in progress"}


# ──────────────────────────────────────────────
# System Endpoints
# ──────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "version": settings.app_version}


@app.get("/api/metrics")
async def get_metrics():
    """Get LLM usage metrics."""
    return llm_gateway.get_metrics()


@app.get("/api/config")
async def get_config():
    """Get current system configuration (non-sensitive)."""
    return {
        "app_name": settings.app_name,
        "version": settings.app_version,
        "max_parallel_agents": settings.max_parallel_agents,
        "min_review_score": settings.min_review_score,
        "max_fix_attempts": settings.max_fix_attempts,
        "default_architect_model": settings.default_architect_model.value,
        "default_builder_model": settings.default_builder_model.value,
        "default_reviewer_model": settings.default_reviewer_model.value,
        "has_anthropic_key": bool(settings.anthropic_api_key),
        "has_openai_key": bool(settings.openai_api_key),
        "has_google_key": bool(settings.google_api_key),
    }


# ──────────────────────────────────────────────
# LLM Configuration Endpoints
# ──────────────────────────────────────────────

class ProviderCreateRequest(BaseModel):
    id: str                          # slug, e.g. "ollama" or "azure-east"
    name: str                        # display name, e.g. "Ollama (Local)"
    base_url: str                    # required endpoint
    api_key: str = ""                # empty for local/no-auth providers
    model_prefix: str = ""           # LiteLLM prefix e.g. "ollama" or "openai"
    compatible_with: str = "openai"  # openai | anthropic | custom
    description: str = ""


class ProviderUpdateRequest(BaseModel):
    name: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    enabled: Optional[bool] = None
    model_prefix: Optional[str] = None
    compatible_with: Optional[str] = None
    description: Optional[str] = None


class ModelCreateRequest(BaseModel):
    model_id: str
    name: str
    provider: str
    enabled: bool = True
    description: str = ""


class ModelUpdateRequest(BaseModel):
    name: Optional[str] = None
    enabled: Optional[bool] = None
    provider: Optional[str] = None
    description: Optional[str] = None


class RoutingUpdateRequest(BaseModel):
    routing: dict[str, list[str]]  # {"low": ["model1", "model2"], ...}


class ModelTestRequest(BaseModel):
    model_id: str
    provider_id: Optional[str] = None


@app.get("/api/llm/providers")
async def get_providers():
    """Get all LLM providers with their key status."""
    providers = _llm_config.get_providers()
    # Mask keys in response
    safe = []
    for p in providers:
        entry = dict(p)
        if entry.get("api_key"):
            key = entry["api_key"]
            entry["api_key_masked"] = key[:8] + "*" * (len(key) - 12) + key[-4:] if len(key) > 12 else "****"
            entry["has_key"] = True
        else:
            entry["api_key_masked"] = ""
            entry["has_key"] = False
        # Never expose raw key
        entry.pop("api_key", None)
        safe.append(entry)
    return safe


@app.post("/api/llm/providers", status_code=201)
async def add_provider(req: ProviderCreateRequest):
    """Add a custom LLM provider."""
    try:
        provider = _llm_config.add_provider(req.model_dump())
        return {"message": "Provider added", "provider": {k: v for k, v in provider.items() if k != "api_key"}}
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.put("/api/llm/providers/{provider_id}")
async def update_provider(provider_id: str, req: ProviderUpdateRequest):
    """Update a provider's API key, endpoint, or enabled status."""
    try:
        data = req.model_dump(exclude_none=True)
        updated = _llm_config.update_provider(provider_id, data)
        return {"message": "Provider updated", "provider_id": provider_id, "enabled": updated.get("enabled")}
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.delete("/api/llm/providers/{provider_id}")
async def delete_provider(provider_id: str):
    """Delete a custom provider (built-in providers cannot be deleted)."""
    try:
        _llm_config.delete_provider(provider_id)
        return {"message": f"Provider '{provider_id}' deleted"}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.get("/api/llm/models")
async def get_models():
    """Get all available LLM models."""
    return _llm_config.get_models()


@app.post("/api/llm/models", status_code=201)
async def add_model(req: ModelCreateRequest):
    """Add a custom LLM model."""
    try:
        model = _llm_config.add_model(req.model_dump())
        return model
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.put("/api/llm/models/{model_id:path}")
async def update_model(model_id: str, req: ModelUpdateRequest):
    """Update an existing LLM model's settings."""
    try:
        updated = _llm_config.update_model(model_id, req.model_dump(exclude_none=True))
        return updated
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.delete("/api/llm/models/{model_id:path}")
async def delete_model(model_id: str):
    """Delete a custom LLM model."""
    try:
        _llm_config.delete_model(model_id)
        return {"message": f"Model '{model_id}' deleted"}
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.get("/api/llm/routing")
async def get_routing():
    """Get the current complexity→model routing table."""
    return _llm_config.get_routing()


@app.put("/api/llm/routing")
async def update_routing(req: RoutingUpdateRequest):
    """Update the complexity→model routing table at runtime."""
    _llm_config.update_routing(req.routing)
    return {"message": "Routing updated", "routing": _llm_config.get_routing()}


@app.post("/api/llm/test")
async def test_model(req: ModelTestRequest):
    """Test a model with a lightweight completion call."""
    import litellm
    start = time.time()
    try:
        response = await litellm.acompletion(
            model=req.model_id,
            messages=[{"role": "user", "content": "Reply with exactly: OK"}],
            max_tokens=10,
            temperature=0
        )
        elapsed = round(time.time() - start, 2)
        content = response.choices[0].message.content or ""
        return {"success": True, "response": content, "elapsed_seconds": elapsed, "model": req.model_id}
    except Exception as e:
        elapsed = round(time.time() - start, 2)
        return {"success": False, "error": str(e)[:300], "elapsed_seconds": elapsed, "model": req.model_id}


# ──────────────────────────────────────────────
# LLM Limits & Usage Endpoints
# ──────────────────────────────────────────────

class ModelLimitsRequest(BaseModel):
    rpm_limit: int = 0
    max_input_tokens: int = 0
    max_tokens_per_minute: int = 0
    max_tokens_per_day: int = 0


@app.get("/api/llm/limits")
async def get_all_limits():
    """Get rate limits for all models."""
    models = _llm_config.get_models()
    result = []
    for m in models:
        stats = rate_limiter.get_model_stats(m["id"])
        result.append({
            **m,
            "live_stats": stats["live"],
            "usage": stats["usage"],
        })
    return result


@app.put("/api/llm/limits/{model_id:path}")
async def set_model_limits(model_id: str, req: ModelLimitsRequest):
    """Set rate limits for a specific model."""
    try:
        updated = _llm_config.update_model(model_id, req.model_dump())
        return {"message": f"Limits updated for {model_id}", "model": updated}
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.get("/api/llm/usage")
async def get_usage_stats():
    """Get full per-minute/day/week usage stats for all tracked models."""
    return rate_limiter.get_all_stats()


@app.get("/api/llm/failover-events")
async def get_failover_events(limit: int = 50):
    """Get recent automatic model failover events."""
    return rate_limiter.get_failover_log(limit)


@app.get("/api/llm/metrics/rich")
async def get_rich_metrics():
    """Get rich per-model metrics from the gateway (minute/day/week)."""
    return llm_gateway.get_rich_metrics()


# ──────────────────────────────────────────────
# WebSocket for Real-time Build Updates
# ──────────────────────────────────────────────

@app.websocket("/ws/projects/{project_id}")
async def websocket_project_events(websocket: WebSocket, project_id: str):
    """WebSocket endpoint for real-time build event streaming."""
    await websocket.accept()
    queue = event_bus.get_queue(project_id)

    try:
        # Send event history first
        for event in event_bus.get_history(project_id):
            await websocket.send_json(event.model_dump(mode="json"))

        # Stream new events
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_json(event.model_dump(mode="json"))
            except asyncio.TimeoutError:
                # Send keepalive
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for project {project_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")


# ──────────────────────────────────────────────
# Background Build Tasks
# ──────────────────────────────────────────────

async def _run_build_requirements(project_id: str, requirements: str):
    """Background task for requirements-based build."""
    try:
        await orchestrator.build_from_requirements(project_id, requirements)
    except Exception as e:
        logger.error(f"Build failed for {project_id}: {e}", exc_info=True)
        await event_bus.emit(project_id, "error", f"Build failed: {str(e)}")


async def _run_build_html(project_id: str, html_files: dict[str, str]):
    """Background task for HTML mockup-based build."""
    try:
        await orchestrator.build_from_html_mockups(project_id, html_files)
    except Exception as e:
        logger.error(f"Build failed for {project_id}: {e}", exc_info=True)
        await event_bus.emit(project_id, "error", f"Build failed: {str(e)}")


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )
