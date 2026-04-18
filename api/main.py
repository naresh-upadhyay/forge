"""FORGE API - FastAPI application with REST endpoints and WebSocket for real-time updates."""

from __future__ import annotations

import sys
import asyncio

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import json
import logging
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from forge_core.config import settings
from forge_core.events import event_bus
from forge_core.llm.gateway import llm_gateway
from forge_core.models import BuildEvent, ProjectStatus
from forge_core.orchestrator import orchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("forge.api")


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
