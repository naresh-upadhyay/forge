"""FORGE Storage - Persistent storage for projects using SQLite."""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite
from forge_core.config import settings
from forge_core.models import Project

logger = logging.getLogger(__name__)

class StorageManager:
    """Manages persistent storage of Project models using SQLite."""

    def __init__(self, db_path: str = "forge.db"):
        # Resolve path relative to base_dir if it's a local filename
        if not db_path.startswith("sqlite"):
            self.db_path = db_path
        else:
            # Parse from sqlite+aiosqlite:///./forge.db
            self.db_path = db_path.split(":///")[-1]
            
    async def initialize(self):
        """Initialize the database tables."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()
            logger.info(f"Storage initialized at {self.db_path}")

    async def save_project(self, project: Project):
        """Save or update a project in the database."""
        async with aiosqlite.connect(self.db_path) as db:
            project_json = project.model_dump_json()
            await db.execute(
                "INSERT OR REPLACE INTO projects (id, name, status, data, updated_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                (project.id, project.name, project.status.value, project_json)
            )
            await db.commit()

    async def get_project(self, project_id: str) -> Optional[Project]:
        """Load a project from the database."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT data FROM projects WHERE id = ?", (project_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return Project.model_validate_json(row[0])
                return None

    async def list_projects(self) -> List[Project]:
        """Load all projects from the database."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT data FROM projects ORDER BY created_at DESC") as cursor:
                rows = await cursor.fetchall()
                return [Project.model_validate_json(row[0]) for row in rows]

    async def delete_project(self, project_id: str):
        """Delete a project from the database."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            await db.commit()

# Singleton instance
storage = StorageManager(settings.database_url)
