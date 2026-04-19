"""Intake Engine - Converts raw inputs into structured Application Blueprints.

Handles two input types:
1. HTML Mockups → Parsed, analyzed, converted to blueprint
2. Business Requirements (text) → Analyzed and structured into blueprint
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

from bs4 import BeautifulSoup

from forge_core.config import TaskComplexity
from forge_core.events import event_bus
from forge_core.llm.gateway import llm_gateway
from forge_core.llm.prompts.templates import INTAKE_HTML_SYSTEM, INTAKE_REQUIREMENTS_SYSTEM
from forge_core.models import (
    AgentRole,
    APIEndpoint,
    Blueprint,
    BusinessRule,
    Entity,
    EntityField,
    Screen,
    TechStack,
    UIComponent,
    UserFlow,
)

logger = logging.getLogger(__name__)


class IntakeEngine:
    """Parses inputs and produces structured Application Blueprints."""

    async def process_html_mockups(
        self,
        html_files: dict[str, str],
        project_id: str,
        tech_stack: TechStack = TechStack.FLUTTER,
        app_name: str = "MyApp",
    ) -> Blueprint:
        """
        Parse HTML mockup files and generate an application blueprint.

        Args:
            html_files: Dict of filename -> HTML content
            project_id: Project ID for event tracking
            tech_stack: Target technology stack
            app_name: Application name
        """
        await event_bus.emit(
            project_id, "info", f"Analyzing {len(html_files)} HTML mockup files...",
            agent=AgentRole.INTAKE,
        )

        # Step 1: Pre-parse HTML to extract structure
        parsed_screens = {}
        design_tokens = {"colors": set(), "fonts": set(), "font_sizes": set()}

        for filename, html_content in html_files.items():
            parsed = self._preparse_html(html_content, filename)
            parsed_screens[filename] = parsed
            # Collect design tokens
            for color in parsed.get("colors", []):
                design_tokens["colors"].add(color)
            for font in parsed.get("fonts", []):
                design_tokens["fonts"].add(font)

        # Step 2: Send to LLM for deep analysis
        analysis_prompt = self._build_html_analysis_prompt(parsed_screens, tech_stack)

        await event_bus.emit(
            project_id, "info", "Running AI analysis on mockup structure...",
            agent=AgentRole.INTAKE,
        )

        raw_result = await llm_gateway.complete(
            messages=[{"role": "user", "content": analysis_prompt}],
            system_prompt=INTAKE_HTML_SYSTEM,
            complexity=TaskComplexity.HIGH,
            temperature=0.1,
            max_tokens=8192,
        )

        # Step 3: Parse LLM response into Blueprint
        blueprint_data = self._parse_json_response(raw_result)

        await event_bus.emit(
            project_id, "info",
            f"Blueprint generated: {len(blueprint_data.get('screens', []))} screens, "
            f"{len(blueprint_data.get('entities', []))} entities identified",
            agent=AgentRole.INTAKE,
        )

        return self._build_blueprint(blueprint_data, tech_stack, app_name)

    async def process_requirements(
        self,
        requirements_text: str,
        project_id: str,
        tech_stack: TechStack = TechStack.DOTNET,
        backend_stack: Optional[TechStack] = None,
        app_name: str = "MyApp",
    ) -> Blueprint:
        """
        Parse business requirements text and generate an application blueprint.

        Args:
            requirements_text: Raw business requirements text
            project_id: Project ID for event tracking
            tech_stack: Target frontend technology stack
            backend_stack: Target backend technology stack
            app_name: Application name
        """
        await event_bus.emit(
            project_id, "info", "Analyzing business requirements...",
            agent=AgentRole.INTAKE,
        )

        prompt = f"""Analyze these business requirements and generate a complete application blueprint.

Target Technology Stack: {tech_stack.value}
{f'Backend Stack: {backend_stack.value}' if backend_stack else ''}

## Business Requirements:
{requirements_text}

Generate the complete blueprint JSON following the specified format.
Include ALL entities, screens, API endpoints, business rules, and user flows.
Be thorough - every requirement must be addressed in the blueprint."""

        raw_result = await llm_gateway.complete(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=INTAKE_REQUIREMENTS_SYSTEM,
            complexity=TaskComplexity.HIGH,
            temperature=0.1,
            max_tokens=8192,
        )

        blueprint_data = self._parse_json_response(raw_result)

        screen_count = len(blueprint_data.get("screens", []))
        entity_count = len(blueprint_data.get("entities", []))
        endpoint_count = len(blueprint_data.get("api_endpoints", []))

        await event_bus.emit(
            project_id, "info",
            f"Blueprint generated: {screen_count} screens, {entity_count} entities, "
            f"{endpoint_count} API endpoints",
            agent=AgentRole.INTAKE,
        )

        # Check for ambiguities
        ambiguities = blueprint_data.get("ambiguities", [])
        if ambiguities:
            await event_bus.emit(
                project_id, "info",
                f"Note: {len(ambiguities)} ambiguities identified - proceeding with best assumptions",
                agent=AgentRole.INTAKE,
                data={"ambiguities": ambiguities},
            )

        return self._build_blueprint(
            blueprint_data, tech_stack, app_name, backend_stack=backend_stack
        )

    def _preparse_html(self, html_content: str, filename: str) -> dict[str, Any]:
        """Quick structural parse of HTML to extract key elements."""
        soup = BeautifulSoup(html_content, "html.parser")

        result: dict[str, Any] = {
            "filename": filename,
            "title": "",
            "components": [],
            "colors": [],
            "fonts": [],
            "links": [],
            "forms": [],
            "images": [],
        }

        # Title
        title_tag = soup.find("title")
        if title_tag:
            result["title"] = title_tag.get_text(strip=True)

        # Extract colors from inline styles and style tags
        style_tags = soup.find_all("style")
        all_css = " ".join(tag.get_text() for tag in style_tags)
        # Add inline styles
        for elem in soup.find_all(style=True):
            all_css += " " + (elem.get("style") or "")

        colors = set(re.findall(r"#[0-9a-fA-F]{3,8}", all_css))
        colors.update(re.findall(r"rgb\([^)]+\)", all_css))
        result["colors"] = list(colors)

        # Extract fonts
        fonts = set(re.findall(r"font-family:\s*([^;\"']+)", all_css))
        result["fonts"] = list(fonts)

        # Links / navigation
        for a_tag in soup.find_all("a", href=True):
            result["links"].append({
                "text": a_tag.get_text(strip=True),
                "href": a_tag["href"],
            })

        # Forms
        for form in soup.find_all("form"):
            form_data = {
                "action": form.get("action", ""),
                "method": form.get("method", "GET"),
                "fields": [],
            }
            for inp in form.find_all(["input", "select", "textarea"]):
                form_data["fields"].append({
                    "type": inp.get("type", inp.name),
                    "name": inp.get("name", ""),
                    "placeholder": inp.get("placeholder", ""),
                    "required": inp.has_attr("required"),
                })
            result["forms"].append(form_data)

        # Component inventory
        for tag_name in ["button", "input", "select", "textarea", "table", "nav", "header", "footer", "aside"]:
            for elem in soup.find_all(tag_name):
                result["components"].append({
                    "tag": tag_name,
                    "text": elem.get_text(strip=True)[:100],
                    "classes": elem.get("class", []),
                    "id": elem.get("id", ""),
                })

        # Images
        for img in soup.find_all("img"):
            result["images"].append({
                "src": img.get("src", ""),
                "alt": img.get("alt", ""),
            })

        return result

    def _build_html_analysis_prompt(
        self, parsed_screens: dict[str, dict], tech_stack: TechStack
    ) -> str:
        """Build the analysis prompt with pre-parsed HTML data."""
        screens_info = json.dumps(parsed_screens, indent=2, default=str)
        return f"""Analyze these pre-parsed HTML mockup screens and generate a complete application blueprint.

Target Technology Stack: {tech_stack.value}

## Pre-parsed Screen Data:
{screens_info}

Based on this structural analysis, generate the complete blueprint JSON.
Identify:
1. All unique screens and their purposes
2. Reusable components across screens
3. Data entities inferred from forms and data displays
4. Navigation flows between screens
5. Design tokens (colors, fonts, spacing)
6. API calls each screen would need"""

    def _parse_json_response(self, raw_response: str) -> dict[str, Any]:
        """Extract and parse JSON from LLM response."""
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

        # Try finding JSON object in text
        brace_start = raw_response.find("{")
        brace_end = raw_response.rfind("}") + 1
        if brace_start >= 0 and brace_end > brace_start:
            try:
                return json.loads(raw_response[brace_start:brace_end])
            except json.JSONDecodeError:
                pass

        logger.error("Failed to parse JSON from LLM response")
        return {"error": "Failed to parse blueprint", "raw": raw_response[:500]}

    def _build_blueprint(
        self,
        data: dict[str, Any],
        tech_stack: TechStack,
        app_name: str,
        backend_stack: Optional[TechStack] = None,
    ) -> Blueprint:
        """Convert parsed JSON data into a Blueprint model."""
        if not isinstance(data, dict):
            logger.error(f"_build_blueprint received non-dict: {type(data)}. Using empty blueprint.")
            data = {}

        # Build entities
        entities = []
        for e in data.get("entities", []):
            if not isinstance(e, dict):
                logger.warning(f"Skipping non-dict entity item: {e!r}")
                continue
            fields = []
            for f in e.get("fields", []):
                fields.append(EntityField(
                    name=f.get("name", ""),
                    type=f.get("type", "String"),
                    required=f.get("required", True),
                    default=f.get("default"),
                    description=f.get("description", ""),
                    constraints=f.get("constraints", []),
                    is_primary_key=f.get("is_primary_key", False),
                    is_foreign_key=f.get("is_foreign_key", False),
                    references=f.get("references"),
                ))
            entities.append(Entity(
                name=e.get("name", ""),
                description=e.get("description", ""),
                fields=fields,
                relationships=e.get("relationships", []),
            ))

        # Build screens
        screens = []
        for s in data.get("screens", []):
            if not isinstance(s, dict):
                logger.warning(f"Skipping non-dict screen item: {s!r}")
                continue
            components = self._parse_components(s.get("components", []))
            screens.append(Screen(
                name=s.get("name", ""),
                route=s.get("route", ""),
                description=s.get("description", ""),
                components=components,
                data_bindings=s.get("data_bindings", []),
                api_calls=s.get("api_calls", []),
                source_file=s.get("source_file"),
            ))

        # Build flows
        flows = [
            UserFlow(
                name=f.get("name", ""),
                description=f.get("description", ""),
                steps=f.get("steps", []),
            )
            for f in data.get("flows", []) if isinstance(f, dict)
        ]

        # Build API endpoints
        endpoints = [
            APIEndpoint(
                path=ep.get("path", ""),
                method=ep.get("method", "GET"),
                description=ep.get("description", ""),
                request_schema=ep.get("request_schema", {}),
                response_schema=ep.get("response_schema", {}),
                auth_required=ep.get("auth_required", False),
                related_entity=ep.get("related_entity"),
            )
            for ep in data.get("api_endpoints", []) if isinstance(ep, dict)
        ]

        # Build business rules
        rules = [
            BusinessRule(
                name=r.get("name", ""),
                description=r.get("description", ""),
                entity=r.get("entity"),
                conditions=r.get("conditions", []),
                actions=r.get("actions", []),
            )
            for r in data.get("business_rules", []) if isinstance(r, dict)
        ]

        return Blueprint(
            name=app_name,
            description=data.get("description", ""),
            tech_stack=tech_stack,
            backend_stack=backend_stack,
            entities=entities,
            screens=screens,
            flows=flows,
            api_endpoints=endpoints,
            business_rules=rules,
            design_tokens=data.get("design_tokens", {}),
        )

    def _parse_components(self, components_data: list[dict]) -> list[UIComponent]:
        """Recursively parse component data into UIComponent models."""
        result = []
        for c in components_data:
            if not isinstance(c, dict):
                logger.warning(f"Skipping non-dict component: {c!r}")
                continue
            children = self._parse_components(c.get("children", []))
            result.append(UIComponent(
                name=c.get("name", ""),
                type=c.get("type", "unknown"),
                properties=c.get("properties", {}),
                styles=c.get("styles", {}),
                children=children,
                events=c.get("events", []),
            ))
        return result


# Singleton
intake_engine = IntakeEngine()
