"""Event Bus - Real-time event system for build progress monitoring."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine, Optional

from forge_core.models import AgentRole, BuildEvent

logger = logging.getLogger(__name__)


class EventBus:
    """Async event bus for broadcasting build events to listeners."""

    def __init__(self):
        self._listeners: dict[str, list[Callable]] = defaultdict(list)
        self._event_history: dict[str, list[BuildEvent]] = defaultdict(list)
        self._queues: dict[str, asyncio.Queue] = {}

    def subscribe(self, project_id: str, callback: Callable[[BuildEvent], Coroutine]):
        """Subscribe to events for a specific project."""
        self._listeners[project_id].append(callback)

    def unsubscribe(self, project_id: str, callback: Callable):
        """Unsubscribe from project events."""
        if project_id in self._listeners:
            self._listeners[project_id] = [
                cb for cb in self._listeners[project_id] if cb != callback
            ]

    def get_queue(self, project_id: str) -> asyncio.Queue:
        """Get or create an async queue for a project (used by WebSocket)."""
        if project_id not in self._queues:
            self._queues[project_id] = asyncio.Queue()
        return self._queues[project_id]

    async def emit(
        self,
        project_id: str,
        event_type: str,
        message: str,
        agent: Optional[AgentRole] = None,
        work_unit_id: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
    ):
        """Emit a build event to all subscribers."""
        event = BuildEvent(
            project_id=project_id,
            event_type=event_type,
            agent=agent,
            work_unit_id=work_unit_id,
            message=message,
            data=data or {},
        )

        # Store in history
        self._event_history[project_id].append(event)

        # Notify callback listeners
        for callback in self._listeners.get(project_id, []):
            try:
                await callback(event)
            except Exception as e:
                logger.error(f"Event listener error: {e}")

        # Push to queue for WebSocket consumers
        if project_id in self._queues:
            await self._queues[project_id].put(event)

        logger.info(f"[{project_id[:8]}] {event_type}: {message}")

    def get_history(self, project_id: str) -> list[BuildEvent]:
        """Get event history for a project."""
        return self._event_history.get(project_id, [])

    def clear_history(self, project_id: str):
        """Clear event history for a project."""
        self._event_history.pop(project_id, None)

    def cleanup(self, project_id: str):
        """Remove all resources for a project."""
        self._listeners.pop(project_id, None)
        self._event_history.pop(project_id, None)
        self._queues.pop(project_id, None)


# Singleton
event_bus = EventBus()
