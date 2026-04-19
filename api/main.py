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
from forge_core.llm.key_pool import key_pool
from forge_core.models import BuildEvent, ProjectStatus
from forge_core.orchestrator import orchestrator
from forge_core.storage import storage, llm_config_storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("forge.api")


# ──────────────────────────────────────────────
# Runtime LLM Config Store
# ──────────────────────────────────────────────

def _keys_from_env_key(provider_id: str, raw_key: str) -> list[dict]:
    """Wrap a single raw API key string into the canonical key-list format."""
    if not raw_key:
        return []
    return [{"label": "default", "key": raw_key}]


class LLMConfigStore:
    """Runtime configuration for LLM providers, models and routing.

    All mutations are immediately persisted to SQLite so the configuration
    survives server restarts.  On startup `load_from_db()` is called to
    restore the last-saved state before falling back to .env defaults.

    Each provider stores a list of API keys (`api_keys`) instead of a
    single `api_key`. The first non-rate-limited key in the list is always
    the active one; rotation is handled by the `key_pool` singleton.
    """

    def __init__(self):
        # ── Bootstrap providers with keys from .env ──────────────────────────
        def _make_provider(pid, name, raw_key, base_url, **extra):
            keys = _keys_from_env_key(pid, raw_key)
            return {
                "id": pid,
                "name": name,
                "api_keys": keys,          # list of {label, key}
                "base_url": base_url,
                "enabled": bool(keys),
                **extra,
            }

        self._providers: dict[str, dict] = {
            "openrouter": _make_provider(
                "openrouter", "OpenRouter",
                settings.open_router_key or "",
                settings.open_base_url or "https://openrouter.ai/api/v1/",
            ),
            "anthropic": _make_provider(
                "anthropic", "Anthropic",
                settings.anthropic_api_key or "",
                "https://api.anthropic.com",
            ),
            "openai": _make_provider(
                "openai", "OpenAI",
                settings.openai_api_key or "",
                "https://api.openai.com/v1",
            ),
            "google": _make_provider(
                "google", "Google (Gemini)",
                settings.google_api_key or "",
                "https://generativelanguage.googleapis.com",
            ),
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

    # ── DB persistence ───────────────────────────────────────────────────────

    async def load_from_db(self) -> None:
        """Restore providers, keys, models, and routing from SQLite.

        DB values OVERRIDE the .env defaults so that runtime changes
        (e.g. extra keys added via the dashboard) are preserved across
        restarts.
        """
        # ── Providers ────────────────────────────────────────────────────────
        db_providers = await llm_config_storage.load_providers()
        if db_providers:
            for pid, p in db_providers.items():
                if pid in self._providers:
                    # Merge: keep .env fields as fallback but prefer DB values
                    self._providers[pid].update(
                        {k: v for k, v in p.items() if k != "api_keys"}
                    )
                else:
                    self._providers[pid] = p

        # ── Keys (includes persisted usage counters) ──────────────────────────
        all_keys = await llm_config_storage.load_all_provider_keys()
        for pid, key_rows in all_keys.items():
            if pid not in self._providers:
                continue
            p = self._providers[pid]

            # Merge: DB keys win; if a provider has no DB keys, keep .env key
            if key_rows:
                # Build a set of labels already in .env
                env_labels = {k["label"] for k in p.get("api_keys", [])}
                db_labels  = {k["label"] for k in key_rows}

                # For keys present in BOTH: update the value in DB row from env
                merged = []
                for kr in key_rows:
                    if kr["label"] in env_labels:
                        # Prefer env key value (may have been rotated)
                        env_key = next(
                            (k["key"] for k in p["api_keys"] if k["label"] == kr["label"]),
                            kr["key"],
                        )
                        kr = {**kr, "key": env_key}
                    merged.append(kr)
                # For keys only in .env (not yet saved): add them
                for ek in p.get("api_keys", []):
                    if ek["label"] not in db_labels:
                        merged.append(ek)
                p["api_keys"] = merged
            # If no DB keys, keep what .env gave us (already set in __init__)

        # ── Models ───────────────────────────────────────────────────────────
        db_models = await llm_config_storage.load_models()
        for mid, m in db_models.items():
            if mid in self._models:
                self._models[mid].update(m)
            else:
                self._models[mid] = m

        # ── Routing ──────────────────────────────────────────────────────────
        db_routing = await llm_config_storage.load_routing()
        if db_routing:
            self._routing.update(db_routing)

        # ── Apply everything to key_pool + gateway ───────────────────────────
        for pid, p in self._providers.items():
            key_pool.init_provider(pid, p["api_keys"])
        llm_gateway._configure_keys()

        # Apply saved rate limits to the rate_limiter singleton
        for m in self._models.values():
            rpm = m.get("rpm_limit", 0)
            max_in = m.get("max_input_tokens", 0)
            tpm = m.get("max_tokens_per_minute", 0)
            tpd = m.get("max_tokens_per_day", 0)
            if any([rpm, max_in, tpm, tpd]):
                rate_limiter.set_limits(m["id"], ModelLimits(
                    rpm=rpm, max_input_tokens=max_in,
                    max_tokens_per_minute=tpm, max_tokens_per_day=tpd,
                ))

        # Apply routing to gateway
        new_routing = {}
        for complexity in TaskComplexity:
            tier_models = self._routing.get(complexity.value, [])
            new_routing[complexity] = tier_models
        llm_gateway._dynamic_routing = new_routing

        logger.info("[LLMConfigStore] Configuration loaded from DB")

    async def _persist_provider(self, provider_id: str) -> None:
        """Save a single provider (no keys) to DB."""
        p = self._providers.get(provider_id)
        if p:
            await llm_config_storage.save_provider(p)

    async def _persist_key(
        self, provider_id: str, label: str, api_key: str
    ) -> None:
        """Save a single key to DB (preserves existing usage counters)."""
        await llm_config_storage.save_provider_key(provider_id, label, api_key)

    async def _persist_model(self, model_id: str) -> None:
        m = self._models.get(model_id)
        if m:
            await llm_config_storage.save_model(m)

    async def _persist_routing(self) -> None:
        await llm_config_storage.save_routing(self._routing)

    # ── Provider API key helpers ─────────────────────────────────────────────

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

    def _sync_pool_and_env(self, provider_id: str):
        """Push the current api_keys list for a provider into key_pool and refresh env."""
        p = self._providers.get(provider_id, {})
        keys = p.get("api_keys", [])
        key_pool.init_provider(provider_id, keys)
        url = p.get("base_url", "")
        if provider_id == "openrouter" and url:
            os.environ["OPENROUTER_API_BASE"] = url
        elif provider_id not in ("openrouter", "anthropic", "openai", "google"):
            # Custom provider
            env_prefix = provider_id.upper().replace("-", "_")
            if url:
                os.environ[f"{env_prefix}_API_BASE"] = url
        llm_gateway._configure_keys()

    def get_provider_keys(self, provider_id: str) -> list[dict]:
        """Return key statuses (masked) for the dashboard."""
        if provider_id not in self._providers:
            raise KeyError(f"Provider '{provider_id}' not found")
        return key_pool.get_key_statuses(provider_id)

    async def add_provider_key(self, provider_id: str, label: str, api_key: str) -> dict:
        """Add a new API key to a provider's pool."""
        if provider_id not in self._providers:
            raise KeyError(f"Provider '{provider_id}' not found")
        p = self._providers[provider_id]
        # Prevent label duplicates
        existing_labels = {k["label"] for k in p["api_keys"]}
        if label in existing_labels:
            raise ValueError(f"Key with label '{label}' already exists for '{provider_id}'")
        p["api_keys"].append({"label": label, "key": api_key})
        p["enabled"] = True
        key_pool.add_key(provider_id, label, api_key)
        llm_gateway._configure_keys()
        # Persist
        await self._persist_provider(provider_id)
        await self._persist_key(provider_id, label, api_key)
        return {"label": label, "status": "active", "is_current": False}

    async def delete_provider_key(self, provider_id: str, label: str) -> bool:
        """Remove a key by label."""
        if provider_id not in self._providers:
            raise KeyError(f"Provider '{provider_id}' not found")
        p = self._providers[provider_id]
        before = len(p["api_keys"])
        p["api_keys"] = [k for k in p["api_keys"] if k["label"] != label]
        removed = len(p["api_keys"]) < before
        if removed:
            key_pool.remove_key(provider_id, label)
            p["enabled"] = bool(p["api_keys"])
            llm_gateway._configure_keys()
            # Persist
            await self._persist_provider(provider_id)
            await llm_config_storage.delete_provider_key(provider_id, label)
        return removed

    def reset_provider_key(self, provider_id: str, label: str) -> bool:
        """Clear rate-limit cooldown on a key."""
        if provider_id not in self._providers:
            raise KeyError(f"Provider '{provider_id}' not found")
        return key_pool.reset_key(provider_id, label)

    async def set_key_limits(
        self,
        provider_id: str,
        label: str,
        *,
        daily_limit_tokens: int = 0,
        monthly_limit_tokens: int = 0,
    ) -> bool:
        """Set daily/monthly token budget limits on a specific key."""
        if provider_id not in self._providers:
            raise KeyError(f"Provider '{provider_id}' not found")
        ok = key_pool.set_key_limits(
            provider_id, label,
            daily_limit_tokens=daily_limit_tokens,
            monthly_limit_tokens=monthly_limit_tokens,
        )
        if ok:
            # Look up actual key value so the DB row can be created if missing
            entry = key_pool.get_entry_by_label(provider_id, label)
            raw_key = entry.key if entry else ""
            await llm_config_storage.set_key_limits(
                provider_id, label, raw_key,
                daily_limit_tokens=daily_limit_tokens,
                monthly_limit_tokens=monthly_limit_tokens,
            )
        return ok

    async def reset_key_usage(
        self, provider_id: str, label: str
    ) -> bool:
        """Zero out in-memory and DB usage counters for a key."""
        if provider_id not in self._providers:
            raise KeyError(f"Provider '{provider_id}' not found")
        ok = key_pool.reset_key_usage_counters(provider_id, label)
        if ok:
            await llm_config_storage.reset_key_usage(provider_id, label)
        return ok

    # ── Provider CRUD ────────────────────────────────────────────────────────

    def get_providers(self) -> list[dict]:
        """Return providers — api_keys list is excluded (use /keys endpoint)."""
        result = []
        for p in self._providers.values():
            entry = {k: v for k, v in p.items() if k != "api_keys"}
            entry["key_count"] = key_pool.key_count(p["id"])
            result.append(entry)
        return result

    async def add_provider(self, data: dict) -> dict:
        provider_id = data["id"].lower().strip().replace(" ", "-")
        if provider_id in self._providers:
            raise ValueError(f"Provider '{provider_id}' already exists")
        raw_key = data.get("api_key", "")
        keys = _keys_from_env_key(provider_id, raw_key) if raw_key else []
        entry = {
            "id": provider_id,
            "name": data.get("name", provider_id),
            "api_keys": keys,
            "base_url": data.get("base_url", ""),
            "enabled": bool(keys),
            "custom": True,
            "model_prefix": data.get("model_prefix", ""),
            "description": data.get("description", ""),
            "compatible_with": data.get("compatible_with", "openai"),
        }
        self._providers[provider_id] = entry
        self._sync_pool_and_env(provider_id)
        # Persist
        await self._persist_provider(provider_id)
        for k in keys:
            await self._persist_key(provider_id, k["label"], k["key"])
        return {k: v for k, v in entry.items() if k != "api_keys"}

    async def update_provider(self, provider_id: str, data: dict) -> dict:
        if provider_id not in self._providers:
            raise KeyError(f"Provider '{provider_id}' not found")
        # If a new single api_key is supplied, treat it as a key rotation
        raw_key = data.pop("api_key", None)
        if raw_key:
            p = self._providers[provider_id]
            # Replace the "default" key if present, else add it
            found = False
            for k in p["api_keys"]:
                if k["label"] == "default":
                    k["key"] = raw_key
                    found = True
                    break
            if not found:
                p["api_keys"].insert(0, {"label": "default", "key": raw_key})
            data["enabled"] = True
            await self._persist_key(provider_id, "default", raw_key)
        self._providers[provider_id].update(data)
        self._sync_pool_and_env(provider_id)
        # Persist
        await self._persist_provider(provider_id)
        return {k: v for k, v in self._providers[provider_id].items() if k != "api_keys"}

    async def delete_provider(self, provider_id: str) -> None:
        builtin = {"openrouter", "anthropic", "openai", "google"}
        if provider_id in builtin:
            raise ValueError(f"Cannot delete built-in provider '{provider_id}'")
        if provider_id not in self._providers:
            raise KeyError(f"Provider '{provider_id}' not found")
        del self._providers[provider_id]
        await llm_config_storage.delete_provider(provider_id)

    # ── Models ───────────────────────────────────────────────────────────────

    def get_models(self) -> list[dict]:
        return list(self._models.values())

    async def add_model(self, data: dict) -> dict:
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
        await self._persist_model(model_id)
        return entry

    async def update_model(self, model_id: str, data: dict) -> dict:
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
        await self._persist_model(model_id)
        return self._models[model_id]

    async def delete_model(self, model_id: str) -> None:
        if model_id not in self._models:
            raise KeyError(f"Model '{model_id}' not found")
        del self._models[model_id]
        # Remove from routing
        for tier in self._routing.values():
            if model_id in tier:
                tier.remove(model_id)
        await llm_config_storage.delete_model(model_id)

    # ── Routing ──────────────────────────────────────────────────────────────

    def get_routing(self) -> dict[str, list[str]]:
        return dict(self._routing)

    async def update_routing(self, routing: dict[str, list[str]]) -> None:
        self._routing.update(routing)
        # Rebuild the live MODEL_ROUTING used by the gateway
        new_routing = {}
        for complexity in TaskComplexity:
            tier_models = self._routing.get(complexity.value, [])
            new_routing[complexity] = tier_models
        # Patch gateway to use updated routing
        llm_gateway._dynamic_routing = new_routing
        await self._persist_routing()


_llm_config = LLMConfigStore()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown lifecycle."""
    logger.info(f"FORGE v{settings.app_version} starting...")
    settings.workspace_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Workspace directory: {settings.workspace_dir}")
    # Init storage tables (projects + LLM config)
    await storage.initialize()
    await llm_config_storage.initialize()
    # Restore LLM config saved from previous run
    await _llm_config.load_from_db()
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


# ── Provider key management request models ───────────────────────────────────

class ProviderKeyAddRequest(BaseModel):
    label: str
    api_key: str


# ── Provider endpoints ───────────────────────────────────────────────────────

@app.get("/api/llm/providers")
async def get_providers():
    """Get all LLM providers."""
    providers = _llm_config.get_providers()
    return providers           # api_keys list is NOT included; use /keys endpoint


@app.post("/api/llm/providers", status_code=201)
async def add_provider(req: ProviderCreateRequest):
    """Add a custom LLM provider."""
    try:
        provider = await _llm_config.add_provider(req.model_dump())
        return {"message": "Provider added", "provider": provider}
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.put("/api/llm/providers/{provider_id}")
async def update_provider(provider_id: str, req: ProviderUpdateRequest):
    """Update a provider's metadata, primary API key, or enabled status."""
    try:
        data = req.model_dump(exclude_none=True)
        updated = await _llm_config.update_provider(provider_id, data)
        return {"message": "Provider updated", "provider_id": provider_id, "enabled": updated.get("enabled")}
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.delete("/api/llm/providers/{provider_id}")
async def delete_provider(provider_id: str):
    """Delete a custom provider (built-in providers cannot be deleted)."""
    try:
        await _llm_config.delete_provider(provider_id)
        return {"message": f"Provider '{provider_id}' deleted"}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except KeyError as e:
        raise HTTPException(404, str(e))


# ── Per-provider API-key endpoints ───────────────────────────────────────────

@app.get("/api/llm/providers/{provider_id}/keys")
async def get_provider_keys(provider_id: str):
    """List all API keys for a provider (masked) with rotation status."""
    try:
        return _llm_config.get_provider_keys(provider_id)
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.post("/api/llm/providers/{provider_id}/keys", status_code=201)
async def add_provider_key(provider_id: str, req: ProviderKeyAddRequest):
    """Add a new API key to a provider's rotation pool."""
    try:
        entry = await _llm_config.add_provider_key(provider_id, req.label, req.api_key)
        return {"message": "Key added", "key": entry}
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.delete("/api/llm/providers/{provider_id}/keys/{label}")
async def delete_provider_key(provider_id: str, label: str):
    """Remove an API key from a provider's rotation pool."""
    try:
        removed = await _llm_config.delete_provider_key(provider_id, label)
        if not removed:
            raise HTTPException(404, f"Key '{label}' not found for provider '{provider_id}'")
        return {"message": f"Key '{label}' removed from '{provider_id}'"}
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.post("/api/llm/providers/{provider_id}/keys/{label}/reset")
async def reset_provider_key(provider_id: str, label: str):
    """Clear rate-limit cooldown on a specific API key."""
    try:
        ok = _llm_config.reset_provider_key(provider_id, label)
        if not ok:
            raise HTTPException(404, f"Key '{label}' not found for provider '{provider_id}'")
        return {"message": f"Cooldown cleared for key '{label}' on '{provider_id}'"}
    except KeyError as e:
        raise HTTPException(404, str(e))


# ── Provider endpoints ───────────────────────────────────────────────────────

class KeyLimitsRequest(BaseModel):
    daily_limit_tokens: int = 0
    monthly_limit_tokens: int = 0


@app.get("/api/llm/providers/{provider_id}/keys/usage")
async def get_provider_key_usage(provider_id: str):
    """Get per-key usage statistics including tokens used and remaining budget."""
    try:
        return key_pool.get_key_usage(provider_id)
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.put("/api/llm/providers/{provider_id}/keys/{label}/limits")
async def set_key_limits(provider_id: str, label: str, req: KeyLimitsRequest):
    """Set daily/monthly token budget limits on a specific API key."""
    try:
        ok = await _llm_config.set_key_limits(
            provider_id, label,
            daily_limit_tokens=req.daily_limit_tokens,
            monthly_limit_tokens=req.monthly_limit_tokens,
        )
        if not ok:
            raise HTTPException(404, f"Key '{label}' not found for provider '{provider_id}'")
        return {
            "message": f"Limits set for key '{label}' on '{provider_id}'",
            "daily_limit_tokens": req.daily_limit_tokens,
            "monthly_limit_tokens": req.monthly_limit_tokens,
        }
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.post("/api/llm/providers/{provider_id}/keys/{label}/reset-usage")
async def reset_key_usage(provider_id: str, label: str):
    """Reset all usage counters for a specific API key to zero."""
    try:
        ok = await _llm_config.reset_key_usage(provider_id, label)
        if not ok:
            raise HTTPException(404, f"Key '{label}' not found for provider '{provider_id}'")
        return {"message": f"Usage counters reset for key '{label}' on '{provider_id}'"}
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
        model = await _llm_config.add_model(req.model_dump())
        return model
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.put("/api/llm/models/{model_id:path}")
async def update_model(model_id: str, req: ModelUpdateRequest):
    """Update an existing LLM model's settings."""
    try:
        updated = await _llm_config.update_model(model_id, req.model_dump(exclude_none=True))
        return updated
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.delete("/api/llm/models/{model_id:path}")
async def delete_model(model_id: str):
    """Delete a custom LLM model."""
    try:
        await _llm_config.delete_model(model_id)
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
    await _llm_config.update_routing(req.routing)
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
        updated = await _llm_config.update_model(model_id, req.model_dump())
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
