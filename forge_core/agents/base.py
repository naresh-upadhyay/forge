"""Base Agent - Foundation class for all FORGE agents.

Every specialized agent inherits from this class, which provides:
- LLM interaction via the gateway
- Structured output parsing
- Error handling and retries
- Event emission for progress tracking
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from forge_core.config import TaskComplexity
from forge_core.events import event_bus
from forge_core.llm.gateway import llm_gateway
from forge_core.models import AgentResult, AgentRole, WorkUnit

logger = logging.getLogger(__name__)


class BaseAgent:
    """Base class for all FORGE agents."""

    role: AgentRole = AgentRole.ARCHITECT
    system_prompt: str = ""
    default_complexity: TaskComplexity = TaskComplexity.MEDIUM

    def __init__(self, model_override: Optional[str] = None):
        self.model = model_override

    async def execute(
        self,
        work_unit: WorkUnit,
        project_id: str,
        context_files: Optional[dict[str, str]] = None,
        extra_context: str = "",
    ) -> AgentResult:
        """
        Execute a work unit and return the result.

        Args:
            work_unit: The work unit to execute
            project_id: Project ID for event tracking
            context_files: Existing code files for context
            extra_context: Additional context string
        """
        await event_bus.emit(
            project_id,
            "agent_start",
            f"Agent {self.role.value} starting: {work_unit.title}",
            agent=self.role,
            work_unit_id=work_unit.id,
        )

        try:
            # Build the task prompt
            prompt = self._build_prompt(work_unit, context_files, extra_context)

            # Call LLM
            raw_response = await llm_gateway.complete(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=self.system_prompt,
                model=self.model,
                complexity=self.default_complexity,
                temperature=0.1,
                max_tokens=8192,
            )

            # Parse response
            parsed = self._parse_response(raw_response)

            result = AgentResult(
                work_unit_id=work_unit.id,
                agent_role=self.role,
                success=True,
                files=parsed.get("files", {}),
                tests=parsed.get("tests", {}),
                message=parsed.get("notes", "Completed successfully"),
            )

            await event_bus.emit(
                project_id,
                "agent_complete",
                f"Agent {self.role.value} completed: {work_unit.title} "
                f"({len(result.files)} files, {len(result.tests)} tests)",
                agent=self.role,
                work_unit_id=work_unit.id,
                data={"file_count": len(result.files), "test_count": len(result.tests)},
            )

            return result

        except Exception as e:
            logger.error(f"Agent {self.role.value} failed on {work_unit.title}: {e}")

            await event_bus.emit(
                project_id,
                "error",
                f"Agent {self.role.value} failed: {str(e)[:200]}",
                agent=self.role,
                work_unit_id=work_unit.id,
            )

            return AgentResult(
                work_unit_id=work_unit.id,
                agent_role=self.role,
                success=False,
                message=str(e),
                errors=[str(e)],
            )

    def _build_prompt(
        self,
        work_unit: WorkUnit,
        context_files: Optional[dict[str, str]],
        extra_context: str,
    ) -> str:
        """Build the task prompt for the LLM."""
        parts = []

        # Task description
        parts.append(f"## Task: {work_unit.title}")
        parts.append(f"\n{work_unit.description}")

        # Interface contracts
        if work_unit.contracts:
            parts.append("\n## Interface Contracts (MUST conform to these)")
            parts.append(f"```json\n{json.dumps(work_unit.contracts, indent=2)}\n```")

        # Input context
        if work_unit.input_context:
            parts.append("\n## Context")
            parts.append(f"```json\n{json.dumps(work_unit.input_context, indent=2)}\n```")

        # Existing code files
        if context_files:
            parts.append("\n## Existing Code (for reference)")
            for filepath, content in list(context_files.items())[:10]:  # Limit context
                parts.append(f"\n### {filepath}")
                # Truncate very long files
                if len(content) > 3000:
                    content = content[:3000] + "\n... (truncated)"
                parts.append(f"```\n{content}\n```")

        # Extra context
        if extra_context:
            parts.append(f"\n## Additional Context\n{extra_context}")

        # Files to create
        if work_unit.input_context.get("files_to_create"):
            parts.append("\n## Files to Create")
            for f in work_unit.input_context["files_to_create"]:
                parts.append(f"- `{f}`")

        parts.append(
            "\n\nReturn ONLY a valid JSON object with 'files', 'tests', and 'notes' keys. "
            "No markdown wrapping, no explanation outside the JSON."
        )

        return "\n".join(parts)

    def _parse_response(self, raw_response: str) -> dict[str, Any]:
        """Parse the LLM response, extracting JSON."""
        # Try direct parse
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            pass

        # Try extracting from code blocks
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw_response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding JSON object
        brace_start = raw_response.find("{")
        brace_end = raw_response.rfind("}") + 1
        if brace_start >= 0 and brace_end > brace_start:
            try:
                return json.loads(raw_response[brace_start:brace_end])
            except json.JSONDecodeError:
                pass

        # Fallback: treat entire response as a single file
        logger.warning(f"Could not parse JSON from {self.role.value} response, using raw output")
        return {
            "files": {"output.txt": raw_response},
            "tests": {},
            "notes": "Warning: Response was not valid JSON, saved as raw text",
        }
