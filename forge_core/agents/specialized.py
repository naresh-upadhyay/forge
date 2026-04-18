"""Specialized Agent Implementations.

Each agent has a specific role and uses tailored prompts for its domain.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from forge_core.agents.base import BaseAgent
from forge_core.config import TaskComplexity
from forge_core.events import event_bus
from forge_core.llm.gateway import llm_gateway
from forge_core.llm.prompts.templates import (
    BACKEND_BUILDER_SYSTEM,
    FIXER_SYSTEM,
    FRONTEND_BUILDER_SYSTEM,
    INTEGRATION_CHECK_SYSTEM,
    MODELER_SYSTEM,
    REVIEWER_SYSTEM,
    TESTER_SYSTEM,
)
from forge_core.models import AgentResult, AgentRole, ReviewResult, WorkUnit

logger = logging.getLogger(__name__)


class ModelerAgent(BaseAgent):
    """Creates data models, schemas, and database migrations."""
    role = AgentRole.MODELER
    system_prompt = MODELER_SYSTEM
    default_complexity = TaskComplexity.MEDIUM


class BackendBuilderAgent(BaseAgent):
    """Builds API endpoints, services, and business logic."""
    role = AgentRole.BACKEND_BUILDER
    system_prompt = BACKEND_BUILDER_SYSTEM
    default_complexity = TaskComplexity.HIGH


class FrontendBuilderAgent(BaseAgent):
    """Creates UI components and screens."""
    role = AgentRole.FRONTEND_BUILDER
    system_prompt = FRONTEND_BUILDER_SYSTEM
    default_complexity = TaskComplexity.HIGH


class ReviewerAgent(BaseAgent):
    """Reviews code quality, security, and contract compliance."""
    role = AgentRole.REVIEWER
    system_prompt = REVIEWER_SYSTEM
    default_complexity = TaskComplexity.HIGH

    async def review(
        self,
        work_unit: WorkUnit,
        code_files: dict[str, str],
        test_files: dict[str, str],
        project_id: str,
    ) -> ReviewResult:
        """Review code produced by another agent."""
        await event_bus.emit(
            project_id, "review",
            f"Reviewing: {work_unit.title}",
            agent=self.role,
            work_unit_id=work_unit.id,
        )

        # Build review prompt
        review_content = []
        review_content.append(f"## Work Unit: {work_unit.title}")
        review_content.append(f"Description: {work_unit.description}")

        if work_unit.contracts:
            review_content.append("\n## Interface Contracts")
            review_content.append(f"```json\n{json.dumps(work_unit.contracts, indent=2)}\n```")

        review_content.append("\n## Code to Review")
        for filepath, content in code_files.items():
            review_content.append(f"\n### {filepath}")
            review_content.append(f"```\n{content}\n```")

        if test_files:
            review_content.append("\n## Tests")
            for filepath, content in test_files.items():
                review_content.append(f"\n### {filepath}")
                review_content.append(f"```\n{content}\n```")

        if work_unit.input_context.get("acceptance_criteria"):
            review_content.append("\n## Acceptance Criteria")
            for criterion in work_unit.input_context["acceptance_criteria"]:
                review_content.append(f"- {criterion}")

        prompt = "\n".join(review_content)
        prompt += "\n\nReview this code and return ONLY a valid JSON object with your assessment."

        raw_response = await llm_gateway.complete(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=self.system_prompt,
            model=self.model,
            complexity=TaskComplexity.HIGH,
            temperature=0.1,
        )

        parsed = self._parse_response(raw_response)

        score = float(parsed.get("score", 5.0))
        result = ReviewResult(
            work_unit_id=work_unit.id,
            score=score,
            passed=parsed.get("passed", score >= 7.0),
            issues=parsed.get("issues", []),
            suggestions=parsed.get("suggestions", []),
            security_issues=parsed.get("security_issues", []),
            feedback=parsed.get("feedback", ""),
        )

        status = "PASSED" if result.passed else "FAILED"
        await event_bus.emit(
            project_id, "review",
            f"Review {status} (score: {result.score}/10): {work_unit.title}",
            agent=self.role,
            work_unit_id=work_unit.id,
            data={"score": result.score, "passed": result.passed, "issues": len(result.issues)},
        )

        return result


class TesterAgent(BaseAgent):
    """Writes comprehensive tests for code."""
    role = AgentRole.TESTER
    system_prompt = TESTER_SYSTEM
    default_complexity = TaskComplexity.MEDIUM


class FixerAgent(BaseAgent):
    """Fixes identified issues in code without breaking other things."""
    role = AgentRole.FIXER
    system_prompt = FIXER_SYSTEM
    default_complexity = TaskComplexity.CRITICAL

    async def fix(
        self,
        work_unit: WorkUnit,
        code_files: dict[str, str],
        issues: list[str],
        review_feedback: str,
        project_id: str,
    ) -> AgentResult:
        """Fix identified issues in code."""
        await event_bus.emit(
            project_id, "info",
            f"Fixing {len(issues)} issues in: {work_unit.title}",
            agent=self.role,
            work_unit_id=work_unit.id,
        )

        fix_parts = []
        fix_parts.append(f"## Code with Issues: {work_unit.title}")

        if work_unit.contracts:
            fix_parts.append("\n## Interface Contracts (MUST maintain)")
            fix_parts.append(f"```json\n{json.dumps(work_unit.contracts, indent=2)}\n```")

        fix_parts.append("\n## Current Code")
        for filepath, content in code_files.items():
            fix_parts.append(f"\n### {filepath}")
            fix_parts.append(f"```\n{content}\n```")

        fix_parts.append("\n## Issues to Fix")
        for i, issue in enumerate(issues, 1):
            fix_parts.append(f"{i}. {issue}")

        fix_parts.append(f"\n## Reviewer Feedback\n{review_feedback}")
        fix_parts.append(
            "\n\nFix ALL identified issues. Return ONLY valid JSON with "
            "'fixed_files', 'new_tests', 'fixes_applied', and 'notes' keys."
        )

        raw_response = await llm_gateway.complete(
            messages=[{"role": "user", "content": "\n".join(fix_parts)}],
            system_prompt=self.system_prompt,
            model=self.model,
            complexity=TaskComplexity.CRITICAL,
            temperature=0.05,
        )

        parsed = self._parse_response(raw_response)

        return AgentResult(
            work_unit_id=work_unit.id,
            agent_role=self.role,
            success=True,
            files=parsed.get("fixed_files", parsed.get("files", {})),
            tests=parsed.get("new_tests", parsed.get("tests", {})),
            message=f"Applied fixes: {', '.join(parsed.get('fixes_applied', ['see files']))}",
        )


class IntegrationCheckerAgent(BaseAgent):
    """Verifies that code from multiple agents integrates correctly."""
    role = AgentRole.REVIEWER
    system_prompt = INTEGRATION_CHECK_SYSTEM
    default_complexity = TaskComplexity.HIGH

    async def check_integration(
        self,
        all_files: dict[str, str],
        contracts: dict[str, Any],
        project_id: str,
    ) -> dict[str, Any]:
        """Check that all project files integrate correctly."""
        await event_bus.emit(
            project_id, "info",
            f"Running integration check on {len(all_files)} files...",
            agent=self.role,
        )

        parts = []
        parts.append("## All Project Files")
        for filepath, content in list(all_files.items())[:30]:  # Limit for context
            parts.append(f"\n### {filepath}")
            truncated = content[:2000] if len(content) > 2000 else content
            parts.append(f"```\n{truncated}\n```")

        parts.append("\n## Contracts")
        parts.append(f"```json\n{json.dumps(contracts, indent=2)}\n```")
        parts.append("\n\nCheck integration and return ONLY valid JSON.")

        raw_response = await llm_gateway.complete(
            messages=[{"role": "user", "content": "\n".join(parts)}],
            system_prompt=self.system_prompt,
            model=self.model,
            complexity=TaskComplexity.HIGH,
        )

        result = self._parse_response(raw_response)

        passed = result.get("passed", False)
        issue_count = len(result.get("issues", []))

        await event_bus.emit(
            project_id, "info",
            f"Integration check: {'PASSED' if passed else f'FAILED ({issue_count} issues)'}",
            agent=self.role,
            data=result,
        )

        return result


# ──────────────────────────────────────────────
# Agent Registry
# ──────────────────────────────────────────────

AGENT_REGISTRY: dict[AgentRole, type[BaseAgent]] = {
    AgentRole.MODELER: ModelerAgent,
    AgentRole.BACKEND_BUILDER: BackendBuilderAgent,
    AgentRole.FRONTEND_BUILDER: FrontendBuilderAgent,
    AgentRole.REVIEWER: ReviewerAgent,
    AgentRole.TESTER: TesterAgent,
    AgentRole.FIXER: FixerAgent,
}


def get_agent(role: AgentRole, model_override: Optional[str] = None) -> BaseAgent:
    """Get an agent instance by role."""
    agent_class = AGENT_REGISTRY.get(role, BaseAgent)
    return agent_class(model_override=model_override)
