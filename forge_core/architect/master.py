"""Master Architect - The brain of FORGE.

The Architect NEVER writes code. It only:
1. Decomposes blueprints into work units
2. Manages dependency ordering and waves
3. Assigns work to agents
4. Reviews and integrates completed work
5. Manages the feedback/fix cycle
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Optional

from forge_core.agents.specialized import (
    FixerAgent,
    IntegrationCheckerAgent,
    ReviewerAgent,
    get_agent,
)
from forge_core.config import TaskComplexity, settings
from forge_core.events import event_bus
from forge_core.llm.gateway import llm_gateway
from forge_core.llm.prompts.templates import ARCHITECT_PLAN_SYSTEM
from forge_core.models import (
    AgentResult,
    AgentRole,
    Blueprint,
    FeedbackItem,
    Project,
    ProjectStatus,
    WorkUnit,
    WorkUnitStatus,
    WorkUnitType,
)
from forge_core.workspace.manager import WorkspaceManager

logger = logging.getLogger(__name__)

# Map work unit types to agent roles
WORK_TYPE_TO_AGENT: dict[WorkUnitType, AgentRole] = {
    WorkUnitType.DATA_MODEL: AgentRole.MODELER,
    WorkUnitType.API_ENDPOINT: AgentRole.BACKEND_BUILDER,
    WorkUnitType.SERVICE: AgentRole.BACKEND_BUILDER,
    WorkUnitType.MIDDLEWARE: AgentRole.BACKEND_BUILDER,
    WorkUnitType.UI_COMPONENT: AgentRole.FRONTEND_BUILDER,
    WorkUnitType.UI_SCREEN: AgentRole.FRONTEND_BUILDER,
    WorkUnitType.NAVIGATION: AgentRole.FRONTEND_BUILDER,
    WorkUnitType.THEME: AgentRole.FRONTEND_BUILDER,
    WorkUnitType.STATE_MANAGEMENT: AgentRole.FRONTEND_BUILDER,
    WorkUnitType.CONFIGURATION: AgentRole.BACKEND_BUILDER,
    WorkUnitType.TEST_SUITE: AgentRole.TESTER,
    WorkUnitType.DOCUMENTATION: AgentRole.DOC_WRITER,
}


class MasterArchitect:
    """The orchestration brain of FORGE."""

    def __init__(self):
        self.reviewer = ReviewerAgent()
        self.fixer = FixerAgent()
        self.integration_checker = IntegrationCheckerAgent()

    async def build_project(self, project: Project, build_controls: dict | None = None) -> Project:
        """
        Execute the full build pipeline for a project.

        Pipeline:
        1. Analyze input → Generate Blueprint
        2. Decompose Blueprint → Work Units with dependency graph
        3. Execute work units wave by wave
        4. Review each completed unit
        5. Fix failed reviews
        6. Integration check
        7. Final delivery
        """
        try:
            # Initialize workspace
            workspace = WorkspaceManager(project.id, project.name)
            project.workspace_path = await workspace.initialize(project.tech_stack.value)
            controls = build_controls or {}

            # ── PHASE 1: Blueprint should already be set ──
            if not project.blueprint:
                raise ValueError("Project has no blueprint. Run intake first.")

            project.status = ProjectStatus.PLANNING
            await event_bus.emit(
                project.id, "status_change",
                "Phase 2: Decomposing blueprint into work units...",
                agent=AgentRole.ARCHITECT,
            )

            # ── PHASE 2: Decompose into Work Units ──
            work_units = await self._decompose_blueprint(project.blueprint, project.id)
            project.work_units = work_units
            project.total_work_units = len(work_units)
            project.total_waves = max(wu.wave for wu in work_units) + 1 if work_units else 0

            await event_bus.emit(
                project.id, "info",
                f"Plan complete: {len(work_units)} work units across {project.total_waves} waves",
                agent=AgentRole.ARCHITECT,
                data={
                    "total_units": len(work_units),
                    "total_waves": project.total_waves,
                    "units_by_type": self._count_by_type(work_units),
                },
            )

            # ── PHASE 3: Execute wave by wave ──
            project.status = ProjectStatus.BUILDING

            for wave in range(project.total_waves):
                project.current_wave = wave
                wave_units = [wu for wu in project.work_units if wu.wave == wave]

                # ── Check for cancel/pause between waves ──────────────────
                signal = controls.get(project.id, "running")
                if signal == "cancel_requested":
                    controls[project.id] = "running"
                    project.status = ProjectStatus.FAILED
                    await event_bus.emit(
                        project.id, "error",
                        "Build cancelled by user.",
                        agent=AgentRole.ARCHITECT,
                    )
                    return project
                if signal == "pause_requested":
                    controls[project.id] = "paused"
                    await event_bus.emit(
                        project.id, "info",
                        "Build paused — waiting for resume signal...",
                        agent=AgentRole.ARCHITECT,
                    )
                    # Wait until resumed or cancelled
                    while controls.get(project.id) in ("paused", "pause_requested"):
                        await asyncio.sleep(2)
                    if controls.get(project.id) == "cancel_requested":
                        project.status = ProjectStatus.FAILED
                        await event_bus.emit(
                            project.id, "error", "Build cancelled during pause.",
                            agent=AgentRole.ARCHITECT,
                        )
                        return project
                    await event_bus.emit(
                        project.id, "info", "Build resumed.", agent=AgentRole.ARCHITECT,
                    )
                await event_bus.emit(
                    project.id, "status_change",
                    f"Wave {wave + 1}/{project.total_waves}: "
                    f"Executing {len(wave_units)} work units...",
                    agent=AgentRole.ARCHITECT,
                    data={"wave": wave, "unit_count": len(wave_units)},
                )

                # Execute wave (with controlled parallelism)
                await self._execute_wave(wave_units, project, workspace)

            # ── PHASE 4: Integration Check ──
            # (skip if no files were generated)
            all_files = workspace.get_all_files("main")
            if all_files:
                project.status = ProjectStatus.TESTING
                await event_bus.emit(
                    project.id, "status_change",
                    "Running integration check...",
                    agent=AgentRole.ARCHITECT,
                )

                all_contracts = {}
                for wu in project.work_units:
                    if wu.contracts:
                        all_contracts[wu.title] = wu.contracts

                integration_result = await self.integration_checker.check_integration(
                    all_files, all_contracts, project.id
                )

                # Guard against non-dict result from LLM
                if isinstance(integration_result, dict) and not integration_result.get("passed", True):
                    issues = integration_result.get("issues", [])
                    await event_bus.emit(
                        project.id, "info",
                        f"Integration issues found: {len(issues)}. Attempting fixes...",
                        agent=AgentRole.ARCHITECT,
                    )
                    await self._fix_integration_issues(issues, project, workspace)

            # ── PHASE 5: Complete ──
            project.status = ProjectStatus.COMPLETED
            project.completed_at = datetime.utcnow()
            project.updated_at = datetime.utcnow()

            file_list = workspace.get_file_list("main")
            await event_bus.emit(
                project.id, "status_change",
                f"Build COMPLETE! {len(file_list)} files generated. "
                f"{project.completed_work_units}/{project.total_work_units} units completed.",
                agent=AgentRole.ARCHITECT,
                data={
                    "total_files": len(file_list),
                    "file_list": file_list,
                    "workspace": str(workspace.get_workspace_path()),
                },
            )

            return project

        except Exception as e:
            project.status = ProjectStatus.FAILED
            logger.error(f"Build failed: {e}", exc_info=True)
            await event_bus.emit(
                project.id, "error",
                f"Build FAILED: {str(e)}",
                agent=AgentRole.ARCHITECT,
            )
            raise

    async def _decompose_blueprint(
        self, blueprint: Blueprint, project_id: str
    ) -> list[WorkUnit]:
        """Use LLM to decompose blueprint into ordered work units."""
        blueprint_json = blueprint.model_dump_json(indent=2)

        prompt = f"""Decompose this application blueprint into executable work units.

## Blueprint
{blueprint_json}

## Technology Stack
Frontend: {blueprint.tech_stack.value}
{f'Backend: {blueprint.backend_stack.value}' if blueprint.backend_stack else ''}

Create work units following these rules:
1. Each unit must be independently testable
2. Order by dependency (models → services → API → UI)
3. Group parallelizable units into the same wave
4. Each unit specifies exact files to create
5. Include interface contracts for each unit

Return the JSON plan."""

        raw_response = await llm_gateway.complete(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=ARCHITECT_PLAN_SYSTEM,
            complexity=TaskComplexity.CRITICAL,
            temperature=0.1,
            max_tokens=8192,
        )

        parsed = self._parse_json(raw_response)
        work_units_data = parsed.get("work_units", [])

        work_units = []
        for wu_data in work_units_data:
            if not isinstance(wu_data, dict):
                logger.warning(f"Skipping non-dict work unit: {wu_data!r}")
                continue
            wu_type = self._parse_work_unit_type(wu_data.get("type", "service"))
            agent_role = WORK_TYPE_TO_AGENT.get(wu_type, AgentRole.BACKEND_BUILDER)

            wu = WorkUnit(
                id=wu_data.get("id", f"wu_{len(work_units):03d}"),
                type=wu_type,
                title=wu_data.get("title", "Untitled"),
                description=wu_data.get("description", ""),
                wave=wu_data.get("wave", 0),
                depends_on=wu_data.get("depends_on", []),
                assigned_agent=agent_role,
                contracts=wu_data.get("contracts", {}),
                input_context={
                    "files_to_create": wu_data.get("files_to_create", []),
                    "acceptance_criteria": wu_data.get("acceptance_criteria", []),
                    "tech_stack": blueprint.tech_stack.value,
                    "backend_stack": blueprint.backend_stack.value if blueprint.backend_stack else None,
                    "design_tokens": blueprint.design_tokens,
                },
            )
            work_units.append(wu)

        # Validate dependency graph
        self._validate_dependencies(work_units)

        return work_units

    async def _execute_wave(
        self,
        wave_units: list[WorkUnit],
        project: Project,
        workspace: WorkspaceManager,
    ):
        """Execute all work units in a wave with controlled parallelism."""
        semaphore = asyncio.Semaphore(settings.max_parallel_agents)

        async def run_unit(wu: WorkUnit):
            async with semaphore:
                await self._execute_single_unit_with_timeout(wu, project, workspace)

        tasks = [run_unit(wu) for wu in wave_units]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _execute_single_unit_with_timeout(
        self,
        work_unit: WorkUnit,
        project: Project,
        workspace: WorkspaceManager,
        timeout_seconds: int = 300,
    ):
        """Wrap _execute_single_unit with a watchdog timeout + one auto-retry."""
        for attempt in range(2):  # 1 initial + 1 auto-retry
            try:
                await asyncio.wait_for(
                    self._execute_single_unit(work_unit, project, workspace),
                    timeout=timeout_seconds,
                )
                return  # Success
            except asyncio.TimeoutError:
                await event_bus.emit(
                    project.id, "error",
                    f"⚠ Watchdog: Work unit '{work_unit.title}' timed out after "
                    f"{timeout_seconds}s {'— auto-retrying...' if attempt == 0 else '— marking failed.'}",
                    agent=AgentRole.ARCHITECT,
                    work_unit_id=work_unit.id,
                )
                logger.warning(
                    f"Work unit '{work_unit.title}' timed out (attempt {attempt + 1}/2)"
                )
                if attempt == 0:
                    # Reset for retry
                    from forge_core.models import WorkUnitStatus
                    work_unit.status = WorkUnitStatus.PENDING
                    work_unit.started_at = None
                else:
                    from forge_core.models import WorkUnitStatus
                    work_unit.status = WorkUnitStatus.FAILED
            except Exception as exc:
                logger.error(f"Unexpected error in work unit '{work_unit.title}': {exc}", exc_info=True)
                return

    async def _execute_single_unit(
        self,
        work_unit: WorkUnit,
        project: Project,
        workspace: WorkspaceManager,
    ):
        """Execute a single work unit through the full lifecycle: build → review → fix."""
        work_unit.status = WorkUnitStatus.IN_PROGRESS
        work_unit.started_at = datetime.utcnow()

        # Get agent for this work unit
        agent = get_agent(work_unit.assigned_agent or AgentRole.BACKEND_BUILDER)

        # Gather context from completed dependencies
        context_files = {}
        for dep_id in work_unit.depends_on:
            dep_unit = next((u for u in project.work_units if u.id == dep_id), None)
            if dep_unit and dep_unit.output_files:
                context_files.update(dep_unit.output_files)

        # Also get relevant files from workspace
        existing_files = workspace.get_all_files("main")
        # Only include relevant files (same directory or imported)
        for fp, content in existing_files.items():
            if len(context_files) < 15:  # Limit context size
                context_files[fp] = content

        # ── BUILD ──
        branch_name = f"wu-{work_unit.id}"
        workspace.create_branch(branch_name)

        result = await agent.execute(
            work_unit=work_unit,
            project_id=project.id,
            context_files=context_files,
        )

        if not result.success:
            work_unit.status = WorkUnitStatus.FAILED
            return

        # Write files to branch
        workspace.write_files_batch(result.files, branch=branch_name)
        workspace.write_files_batch(result.tests, branch=branch_name)

        work_unit.output_files = result.files
        work_unit.output_tests = result.tests

        # ── REVIEW ──
        work_unit.status = WorkUnitStatus.REVIEW
        review = await self.reviewer.review(
            work_unit=work_unit,
            code_files=result.files,
            test_files=result.tests,
            project_id=project.id,
        )

        work_unit.review_score = review.score
        work_unit.review_feedback = review.feedback

        # ── FIX LOOP ──
        if not review.passed and work_unit.fix_attempts < settings.max_fix_attempts:
            work_unit.status = WorkUnitStatus.REVISION

            while not review.passed and work_unit.fix_attempts < settings.max_fix_attempts:
                work_unit.fix_attempts += 1

                await event_bus.emit(
                    project.id, "info",
                    f"Fix attempt {work_unit.fix_attempts}/{settings.max_fix_attempts} "
                    f"for: {work_unit.title}",
                    agent=AgentRole.FIXER,
                    work_unit_id=work_unit.id,
                )

                fix_result = await self.fixer.fix(
                    work_unit=work_unit,
                    code_files=result.files,
                    issues=review.issues,
                    review_feedback=review.feedback,
                    project_id=project.id,
                )

                if fix_result.success and fix_result.files:
                    # Update files
                    result.files.update(fix_result.files)
                    result.tests.update(fix_result.tests)
                    workspace.write_files_batch(fix_result.files, branch=branch_name)
                    workspace.write_files_batch(fix_result.tests, branch=branch_name)
                    work_unit.output_files = result.files
                    work_unit.output_tests = result.tests

                    # Re-review
                    review = await self.reviewer.review(
                        work_unit=work_unit,
                        code_files=result.files,
                        test_files=result.tests,
                        project_id=project.id,
                    )
                    work_unit.review_score = review.score
                    work_unit.review_feedback = review.feedback
                else:
                    break

        # ── MERGE ──
        if review.passed or work_unit.fix_attempts >= settings.max_fix_attempts:
            workspace.merge_branch(branch_name, "main")
            work_unit.status = WorkUnitStatus.COMPLETED
            work_unit.completed_at = datetime.utcnow()
            project.completed_work_units += 1

            status = "PASSED" if review.passed else "MERGED (max fixes reached)"
            await event_bus.emit(
                project.id, "info",
                f"Work unit {status}: {work_unit.title} "
                f"(score: {review.score}/10)",
                agent=AgentRole.ARCHITECT,
                work_unit_id=work_unit.id,
            )
        else:
            work_unit.status = WorkUnitStatus.FAILED

        workspace.delete_branch(branch_name)

    async def _fix_integration_issues(
        self,
        issues: list[dict[str, Any]],
        project: Project,
        workspace: WorkspaceManager,
    ):
        """Attempt to fix integration issues."""
        for issue in issues[:5]:  # Limit fixes
            filepath = issue.get("file", "")
            fix_suggestion = issue.get("fix_suggestion", "")

            if filepath and fix_suggestion:
                content = workspace.read_file(filepath, "main")
                if content:
                    fix_wu = WorkUnit(
                        type=WorkUnitType.SERVICE,
                        title=f"Integration fix: {issue.get('description', '')}",
                        description=f"Fix: {fix_suggestion}\nFile: {filepath}",
                    )

                    fix_result = await self.fixer.fix(
                        work_unit=fix_wu,
                        code_files={filepath: content},
                        issues=[issue.get("description", "")],
                        review_feedback=fix_suggestion,
                        project_id=project.id,
                    )

                    if fix_result.success and fix_result.files:
                        workspace.write_files_batch(fix_result.files, branch="main")

    async def handle_feedback(
        self,
        project: Project,
        feedback: FeedbackItem,
        workspace: WorkspaceManager,
    ) -> Project:
        """Handle user feedback on a completed build."""
        project.feedback_history.append(feedback)
        project.status = ProjectStatus.FIXING

        await event_bus.emit(
            project.id, "info",
            f"Processing feedback: {feedback.description}",
            agent=AgentRole.ARCHITECT,
        )

        # Find relevant work units and files
        relevant_files = {}
        relevant_wu = None

        if feedback.screen_id:
            for wu in project.work_units:
                if feedback.screen_id in wu.title.lower() or feedback.screen_id in wu.description.lower():
                    relevant_wu = wu
                    relevant_files.update(wu.output_files)
                    break

        if not relevant_files:
            # Get all files as context
            relevant_files = workspace.get_all_files("main")

        # Create a fix work unit
        fix_wu = WorkUnit(
            type=WorkUnitType.UI_SCREEN if feedback.type == "visual" else WorkUnitType.SERVICE,
            title=f"Feedback fix: {feedback.description[:60]}",
            description=f"User feedback: {feedback.description}\nType: {feedback.type.value}",
            contracts=relevant_wu.contracts if relevant_wu else {},
        )

        fix_result = await self.fixer.fix(
            work_unit=fix_wu,
            code_files=relevant_files,
            issues=[feedback.description],
            review_feedback=f"User feedback ({feedback.type.value}): {feedback.description}",
            project_id=project.id,
        )

        if fix_result.success and fix_result.files:
            workspace.write_files_batch(fix_result.files, branch="main")
            feedback.resolved = True

            await event_bus.emit(
                project.id, "info",
                f"Feedback resolved: {feedback.description[:60]}",
                agent=AgentRole.ARCHITECT,
            )

        project.status = ProjectStatus.COMPLETED
        project.updated_at = datetime.utcnow()
        return project

    def _parse_work_unit_type(self, type_str: str) -> WorkUnitType:
        """Parse work unit type string to enum."""
        try:
            return WorkUnitType(type_str)
        except ValueError:
            mapping = {
                "model": WorkUnitType.DATA_MODEL,
                "database": WorkUnitType.DATA_MODEL,
                "schema": WorkUnitType.DATA_MODEL,
                "api": WorkUnitType.API_ENDPOINT,
                "endpoint": WorkUnitType.API_ENDPOINT,
                "controller": WorkUnitType.API_ENDPOINT,
                "business_logic": WorkUnitType.SERVICE,
                "component": WorkUnitType.UI_COMPONENT,
                "widget": WorkUnitType.UI_COMPONENT,
                "screen": WorkUnitType.UI_SCREEN,
                "page": WorkUnitType.UI_SCREEN,
                "view": WorkUnitType.UI_SCREEN,
                "routing": WorkUnitType.NAVIGATION,
                "nav": WorkUnitType.NAVIGATION,
                "config": WorkUnitType.CONFIGURATION,
                "setup": WorkUnitType.CONFIGURATION,
                "auth": WorkUnitType.MIDDLEWARE,
                "test": WorkUnitType.TEST_SUITE,
                "docs": WorkUnitType.DOCUMENTATION,
                "style": WorkUnitType.THEME,
                "state": WorkUnitType.STATE_MANAGEMENT,
            }
            for key, value in mapping.items():
                if key in type_str.lower():
                    return value
            return WorkUnitType.SERVICE

    def _validate_dependencies(self, work_units: list[WorkUnit]):
        """Validate that all dependency references are valid."""
        ids = {wu.id for wu in work_units}
        for wu in work_units:
            wu.depends_on = [dep for dep in wu.depends_on if dep in ids]

    def _count_by_type(self, work_units: list[WorkUnit]) -> dict[str, int]:
        """Count work units by type."""
        counts: dict[str, int] = {}
        for wu in work_units:
            counts[wu.type.value] = counts.get(wu.type.value, 0) + 1
        return counts

    def _parse_json(self, raw: str) -> dict[str, Any]:
        """Parse JSON from LLM response."""
        import re
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start:end])
            except json.JSONDecodeError:
                pass
        return {"work_units": [], "error": "Failed to parse architect plan"}
