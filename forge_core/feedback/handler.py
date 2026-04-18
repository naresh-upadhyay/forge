"""Feedback Handler - Processes user feedback and routes to fixer agents."""

from __future__ import annotations

import logging
from typing import Optional

from forge_core.models import FeedbackItem, FeedbackType, Project

logger = logging.getLogger(__name__)


class FeedbackHandler:
    """Processes and categorizes user feedback."""

    def categorize_feedback(self, description: str) -> FeedbackType:
        """Auto-categorize feedback based on content."""
        desc_lower = description.lower()

        visual_keywords = [
            "color", "font", "size", "spacing", "padding", "margin",
            "align", "layout", "position", "style", "theme", "dark",
            "light", "border", "shadow", "opacity", "visible", "hidden",
            "bigger", "smaller", "width", "height", "image", "icon",
        ]
        functional_keywords = [
            "button", "click", "navigate", "redirect", "submit",
            "login", "logout", "error", "crash", "freeze", "bug",
            "broken", "doesn't work", "not working", "fails",
        ]
        performance_keywords = [
            "slow", "lag", "loading", "performance", "speed",
            "timeout", "memory", "heavy",
        ]

        if any(kw in desc_lower for kw in visual_keywords):
            return FeedbackType.VISUAL
        elif any(kw in desc_lower for kw in functional_keywords):
            return FeedbackType.FUNCTIONAL
        elif any(kw in desc_lower for kw in performance_keywords):
            return FeedbackType.PERFORMANCE
        return FeedbackType.GENERAL

    def identify_affected_screens(
        self, description: str, project: Project
    ) -> list[str]:
        """Identify which screens are affected by the feedback."""
        if not project.blueprint:
            return []

        affected = []
        desc_lower = description.lower()

        for screen in project.blueprint.screens:
            screen_name_lower = screen.name.lower()
            # Check if screen name appears in feedback
            if screen_name_lower in desc_lower or screen_name_lower.replace("screen", "").strip() in desc_lower:
                affected.append(screen.id)

        return affected

    def prioritize_feedback(self, items: list[FeedbackItem]) -> list[FeedbackItem]:
        """Sort feedback items by priority (functional > visual > performance > general)."""
        priority = {
            FeedbackType.FUNCTIONAL: 0,
            FeedbackType.VISUAL: 1,
            FeedbackType.PERFORMANCE: 2,
            FeedbackType.GENERAL: 3,
        }
        return sorted(items, key=lambda x: priority.get(x.type, 99))


feedback_handler = FeedbackHandler()
