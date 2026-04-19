"""Project Orchestrator - The main entry point for building projects.

This is the top-level coordinator that manages the full lifecycle:
Input → Blueprint → Plan → Build → Review → Test → Fix → Deliver
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from forge_core.architect.master import MasterArchitect
from forge_core.events import event_bus
from forge_core.intake.engine import intake_engine
from forge_core.models import (
    AgentRole,
    FeedbackItem,
    FeedbackType,
    Project,
    ProjectStatus,
    TechStack,
)
from forge_core.workspace.manager import WorkspaceManager
from forge_core.storage import storage

logger = logging.getLogger(__name__)

# Statuses that indicate a build is actively running (lost on server restart)
_ACTIVE_BUILD_STATUSES = {
    ProjectStatus.ANALYZING,
    ProjectStatus.PLANNING,
    ProjectStatus.BUILDING,
    ProjectStatus.REVIEWING,
    ProjectStatus.TESTING,
    ProjectStatus.FIXING,
}


class ProjectOrchestrator:
    """Top-level orchestrator for building complete applications."""

    def __init__(self):
        self.architect = MasterArchitect()
        self.projects: dict[str, Project] = {}
        self._initialized = False
        # Build control signals: project_id → "running" | "pause_requested" | "cancel_requested"
        self._build_controls: dict[str, str] = {}

    async def ensure_initialized(self):
        """Load projects from storage on first use. Recover any stuck builds."""
        if not self._initialized:
            await storage.initialize()
            all_projects = await storage.list_projects()
            for p in all_projects:
                self.projects[p.id] = p
                # Recover projects that were mid-build when the server died
                if p.status in _ACTIVE_BUILD_STATUSES:
                    p.status = ProjectStatus.FAILED
                    await storage.save_project(p)
                    await event_bus.emit(
                        p.id, "error",
                        "Build interrupted: server restarted mid-build. Use Resume to continue.",
                        agent=AgentRole.ARCHITECT,
                    )
                    logger.warning(f"Recovered stale build for project {p.id} ({p.name})")
            self._initialized = True
            logger.info(f"Orchestrator loaded {len(self.projects)} projects from storage")

    # ── Control API ────────────────────────────────────────────────

    def control_build(self, project_id: str, action: str) -> dict:
        """Signal a running build: pause | resume | cancel."""
        valid = {"pause", "resume", "cancel"}
        if action not in valid:
            raise ValueError(f"Unknown action '{action}'. Use: {valid}")
        self._build_controls[project_id] = {
            "pause": "pause_requested",
            "resume": "running",
            "cancel": "cancel_requested",
        }[action]
        return {"project_id": project_id, "action": action, "signal": self._build_controls[project_id]}

    def _check_control(self, project_id: str) -> str:
        """Return current control signal for a project."""
        return self._build_controls.get(project_id, "running")

    # ── Project CRUD ───────────────────────────────────────────────

    async def create_project(
        self,
        name: str,
        tech_stack: str = "flutter",
        backend_stack: Optional[str] = None,
        description: str = "",
    ) -> Project:
        """Create a new project."""
        ts = TechStack(tech_stack)
        bs = TechStack(backend_stack) if backend_stack else None

        project = Project(
            name=name,
            description=description,
            tech_stack=ts,
            backend_stack=bs,
        )
        self.projects[project.id] = project
        await storage.save_project(project)

        await event_bus.emit(
            project.id, "status_change",
            f"Project created: {name} ({tech_stack})",
            agent=AgentRole.ARCHITECT,
        )

        return project

    async def delete_project(self, project_id: str, delete_files: bool = False) -> bool:
        """Delete a project and optionally its generated workspace files."""
        project = self.projects.get(project_id)
        if not project:
            return False
        # Cancel any active build first
        if self._check_control(project_id) == "running" and project.status in _ACTIVE_BUILD_STATUSES:
            self._build_controls[project_id] = "cancel_requested"
            await asyncio.sleep(0.1)  # Give the build loop a moment to notice
        if delete_files:
            workspace = WorkspaceManager(project_id, project.name)
            workspace.delete_workspace()
        del self.projects[project_id]
        self._build_controls.pop(project_id, None)
        await storage.delete_project(project_id)
        logger.info(f"Deleted project {project_id} (delete_files={delete_files})")
        return True

    # ── Build Methods ──────────────────────────────────────────────

    async def build_from_html_mockups(
        self,
        project_id: str,
        html_files: dict[str, str],
    ) -> Project:
        """Build a complete application from HTML mockup files."""
        project = self.projects.get(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        project.status = ProjectStatus.ANALYZING
        project.input_type = "mockups"
        project.input_files = list(html_files.keys())
        project.input_mockups = html_files
        self._build_controls[project_id] = "running"
        await storage.save_project(project)

        await event_bus.emit(
            project.id, "status_change",
            "Phase 1: Analyzing HTML mockups...",
            agent=AgentRole.INTAKE,
        )

        blueprint = await intake_engine.process_html_mockups(
            html_files=html_files,
            project_id=project.id,
            tech_stack=project.tech_stack,
            app_name=project.name,
        )
        project.blueprint = blueprint

        project = await self.architect.build_project(project, self._build_controls)
        self.projects[project.id] = project
        await storage.save_project(project)

        return project

    async def build_from_requirements(
        self,
        project_id: str,
        requirements_text: str,
    ) -> Project:
        """Build a complete application from business requirements text."""
        project = self.projects.get(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        project.status = ProjectStatus.ANALYZING
        project.input_type = "requirements"
        project.input_text = requirements_text
        self._build_controls[project_id] = "running"

        await event_bus.emit(
            project.id, "status_change",
            "Phase 1: Analyzing business requirements...",
            agent=AgentRole.INTAKE,
        )

        blueprint = await intake_engine.process_requirements(
            requirements_text=requirements_text,
            project_id=project.id,
            tech_stack=project.tech_stack,
            backend_stack=project.backend_stack,
            app_name=project.name,
        )
        project.blueprint = blueprint

        project = await self.architect.build_project(project, self._build_controls)
        self.projects[project.id] = project
        await storage.save_project(project)

        return project

    async def resume_build(self, project_id: str) -> Project:
        """Resume a failed/cancelled project build from its stored inputs."""
        project = self.projects.get(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")
        if project.status not in {ProjectStatus.FAILED, ProjectStatus.CREATED}:
            raise ValueError(f"Project {project_id} is not in a resumable state (status: {project.status.value})")
        if project.input_type == "mockups" and project.input_mockups:
            return await self.build_from_html_mockups(project_id, project.input_mockups)
        elif project.input_type == "requirements" and project.input_text:
            return await self.build_from_requirements(project_id, project.input_text)
        else:
            raise ValueError(f"Project {project_id} has no stored build inputs to resume from")

    async def submit_feedback(
        self,
        project_id: str,
        description: str,
        feedback_type: str = "general",
        screen_id: Optional[str] = None,
    ) -> Project:
        """Submit feedback on a completed build."""
        project = self.projects.get(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        # Guard: don't process feedback on a project that was never built
        if project.total_work_units == 0:
            raise ValueError(
                f"Project '{project.name}' has no generated code yet. "
                "Start a build first before submitting feedback."
            )

        feedback = FeedbackItem(
            type=FeedbackType(feedback_type),
            screen_id=screen_id,
            description=description,
        )

        workspace = WorkspaceManager(project.id, project.name)
        project = await self.architect.handle_feedback(project, feedback, workspace)
        self.projects[project.id] = project
        await storage.save_project(project)

        return project

    def get_project(self, project_id: str) -> Optional[Project]:
        """Get a project by ID."""
        return self.projects.get(project_id)

    def list_projects(self) -> list[Project]:
        """List all projects."""
        return list(self.projects.values())

    def get_project_files(self, project_id: str) -> dict[str, str]:
        """Get all generated files for a project (disk-backed)."""
        project = self.projects.get(project_id)
        if not project:
            return {}
        workspace = WorkspaceManager(project.id, project.name)
        return workspace.get_all_files("main")

    def get_project_tree(self, project_id: str) -> str:
        """Get the file tree for a project."""
        project = self.projects.get(project_id)
        if not project:
            return ""
        workspace = WorkspaceManager(project.id, project.name)
        return workspace.get_project_tree()

    async def rebuild_from_mockups(self, project_id: str) -> Project:
        """Restart the build process using existing mockups."""
        project = self.projects.get(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        if not project.input_mockups:
            raise ValueError(f"No mockups found for project {project_id}")

        return await self.build_from_html_mockups(project_id, project.input_mockups)


# Singleton
orchestrator = ProjectOrchestrator()
