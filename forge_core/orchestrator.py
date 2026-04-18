"""Project Orchestrator - The main entry point for building projects.

This is the top-level coordinator that manages the full lifecycle:
Input → Blueprint → Plan → Build → Review → Test → Fix → Deliver
"""

from __future__ import annotations

import logging
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


class ProjectOrchestrator:
    """Top-level orchestrator for building complete applications."""

    def __init__(self):
        self.architect = MasterArchitect()
        self.projects: dict[str, Project] = {}
        self._initialized = False

    async def ensure_initialized(self):
        """Load projects from storage on first use."""
        if not self._initialized:
            await storage.initialize()
            all_projects = await storage.list_projects()
            for p in all_projects:
                self.projects[p.id] = p
            self._initialized = True
            logger.info(f"Orchestrator loaded {len(self.projects)} projects from storage")

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

    async def build_from_html_mockups(
        self,
        project_id: str,
        html_files: dict[str, str],
    ) -> Project:
        """
        Build a complete application from HTML mockup files.

        Args:
            project_id: ID of the project to build
            html_files: Dict of filename -> HTML content
        """
        project = self.projects.get(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        project.status = ProjectStatus.ANALYZING
        project.input_type = "mockups"
        project.input_files = list(html_files.keys())
        project.input_mockups = html_files
        await storage.save_project(project)

        # Step 1: Intake - Parse mockups into blueprint
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

        # Step 2: Build
        project = await self.architect.build_project(project)
        self.projects[project.id] = project
        await storage.save_project(project)

        return project

    async def build_from_requirements(
        self,
        project_id: str,
        requirements_text: str,
    ) -> Project:
        """
        Build a complete application from business requirements text.

        Args:
            project_id: ID of the project to build
            requirements_text: Raw business requirements
        """
        project = self.projects.get(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        project.status = ProjectStatus.ANALYZING
        project.input_type = "requirements"
        project.input_text = requirements_text

        # Step 1: Intake - Parse requirements into blueprint
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

        # Step 2: Build
        project = await self.architect.build_project(project)
        self.projects[project.id] = project
        await storage.save_project(project)

        return project

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
        """Get all generated files for a project."""
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
