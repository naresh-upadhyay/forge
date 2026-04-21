"""Event Bus - Real-time event system for build progress monitoring."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine, Optional

from forge_core.models import AgentRole, BuildEvent

logger = logging.getLogger(__name__)


class EventBus:
    """Async event bus for broadcasting build events to listeners.

    Every emitted event is persisted asynchronously to the build_logs table
    so the live feed survives page refreshes and server restarts.
    """

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
        """Emit a build event to all subscribers and persist to DB."""
        event = BuildEvent(
            project_id=project_id,
            event_type=event_type,
            agent=agent,
            work_unit_id=work_unit_id,
            message=message,
            data=data or {},
        )

        # Store in memory
        self._event_history[project_id].append(event)

        # Persist to DB asynchronously (never let DB failure break the build)
        asyncio.create_task(self._persist_event(event))

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

    async def _persist_event(self, event: BuildEvent) -> None:
        """Background task: save a single event to DB."""
        try:
            from forge_core.storage import storage
            await storage.save_build_event(event)
        except Exception as exc:
            logger.debug(f"[event_bus] DB persist skipped: {exc}")

    def get_history(self, project_id: str) -> list[BuildEvent]:
        """Return in-memory event history (synchronous, fast path)."""
        return self._event_history.get(project_id, [])

    async def get_history_with_db_fallback(self, project_id: str) -> list[BuildEvent]:
        """Return history; falls back to DB when memory is empty (after restart)."""
        mem = self._event_history.get(project_id, [])
        if mem:
            return mem
        try:
            from forge_core.storage import storage
            db_events = await storage.get_build_events(project_id)
            if db_events:
                # Repopulate in-memory cache so future appends work correctly
                self._event_history[project_id] = list(db_events)
                return db_events
        except Exception as exc:
            logger.warning(f"[event_bus] DB history fallback failed: {exc}")
        return []

    def clear_history(self, project_id: str):
        """Clear in-memory event history for a project."""
        self._event_history.pop(project_id, None)

    def cleanup(self, project_id: str):
        """Remove all in-memory resources for a project."""
        self._listeners.pop(project_id, None)
        self._event_history.pop(project_id, None)
        self._queues.pop(project_id, None)


# Singleton
event_bus = EventBus()
