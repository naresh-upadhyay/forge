"""FORGE Storage - Persistent storage for projects and LLM configuration using SQLite."""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite
from forge_core.config import settings
from forge_core.models import Project

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Project Storage
# ──────────────────────────────────────────────

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


# ──────────────────────────────────────────────
# LLM Configuration Storage
# ──────────────────────────────────────────────

class LLMConfigStorage:
    """
    Persists LLM runtime configuration (providers, keys, models, routing)
    to SQLite so that configuration survives server restarts.

    Per-key usage stats (calls, tokens in/out, errors, last_used_at,
    daily_limit, monthly_limit) are stored alongside each key row and
    updated in-place every time the gateway records a successful call or
    an error.
    """

    def __init__(self, db_path: str = "forge.db"):
        if not db_path.startswith("sqlite"):
            self.db_path = db_path
        else:
            self.db_path = db_path.split(":///")[-1]

    # ─── Schema ──────────────────────────────────────────────────────────────

    async def initialize(self):
        """Create all LLM config tables if they don't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            # Provider metadata (excluding keys)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS llm_providers (
                    id          TEXT PRIMARY KEY,
                    name        TEXT NOT NULL,
                    base_url    TEXT DEFAULT '',
                    enabled     INTEGER DEFAULT 1,
                    custom      INTEGER DEFAULT 0,
                    config_json TEXT DEFAULT '{}'
                )
            """)

            # Per-key rows — one row per (provider, label) pair
            # Usage counters are updated live by the gateway via update_key_usage().
            await db.execute("""
                CREATE TABLE IF NOT EXISTS llm_provider_keys (
                    provider_id         TEXT NOT NULL,
                    label               TEXT NOT NULL,
                    api_key             TEXT NOT NULL,
                    usage_calls         INTEGER DEFAULT 0,
                    usage_tokens_in     INTEGER DEFAULT 0,
                    usage_tokens_out    INTEGER DEFAULT 0,
                    usage_errors        INTEGER DEFAULT 0,
                    last_used_at        REAL    DEFAULT 0,
                    daily_limit_tokens  INTEGER DEFAULT 0,
                    monthly_limit_tokens INTEGER DEFAULT 0,
                    created_at          REAL DEFAULT (strftime('%s','now')),
                    PRIMARY KEY (provider_id, label)
                )
            """)

            # Model configuration rows
            await db.execute("""
                CREATE TABLE IF NOT EXISTS llm_models (
                    id          TEXT PRIMARY KEY,
                    name        TEXT NOT NULL,
                    provider    TEXT NOT NULL,
                    enabled     INTEGER DEFAULT 1,
                    custom      INTEGER DEFAULT 0,
                    config_json TEXT DEFAULT '{}'
                )
            """)

            # Routing table — one row per complexity tier
            await db.execute("""
                CREATE TABLE IF NOT EXISTS llm_routing (
                    complexity  TEXT PRIMARY KEY,
                    models_json TEXT NOT NULL
                )
            """)

            await db.commit()
            logger.info("[LLMConfigStorage] Tables ready")

    # ─── Providers ───────────────────────────────────────────────────────────

    async def save_provider(self, provider: dict) -> None:
        """Upsert a single provider (does NOT touch its keys)."""
        pid = provider["id"]
        # Anything that isn't a first-class column goes into config_json
        extra = {
            k: v for k, v in provider.items()
            if k not in ("id", "name", "base_url", "enabled", "custom", "api_keys")
        }
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO llm_providers (id, name, base_url, enabled, custom, config_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name        = excluded.name,
                    base_url    = excluded.base_url,
                    enabled     = excluded.enabled,
                    custom      = excluded.custom,
                    config_json = excluded.config_json
                """,
                (
                    pid,
                    provider.get("name", pid),
                    provider.get("base_url", ""),
                    int(provider.get("enabled", True)),
                    int(provider.get("custom", False)),
                    json.dumps(extra),
                ),
            )
            await db.commit()

    async def delete_provider(self, provider_id: str) -> None:
        """Delete a provider and all its keys."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM llm_providers WHERE id = ?", (provider_id,))
            await db.execute(
                "DELETE FROM llm_provider_keys WHERE provider_id = ?", (provider_id,)
            )
            await db.commit()

    async def load_providers(self) -> dict[str, dict]:
        """Return all saved providers as a dict keyed by provider_id."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT id, name, base_url, enabled, custom, config_json FROM llm_providers"
            ) as cur:
                rows = await cur.fetchall()
        result = {}
        for row in rows:
            pid, name, base_url, enabled, custom, config_json = row
            extra = json.loads(config_json or "{}")
            result[pid] = {
                "id": pid,
                "name": name,
                "base_url": base_url,
                "enabled": bool(enabled),
                "custom": bool(custom),
                **extra,
                # Keys are loaded separately via load_provider_keys()
                "api_keys": [],
            }
        return result

    # ─── Provider Keys ────────────────────────────────────────────────────────

    async def save_provider_key(
        self,
        provider_id: str,
        label: str,
        api_key: str,
        *,
        daily_limit_tokens: int = 0,
        monthly_limit_tokens: int = 0,
    ) -> None:
        """Upsert a key entry (preserves existing usage counters on conflict)."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO llm_provider_keys
                    (provider_id, label, api_key, daily_limit_tokens, monthly_limit_tokens)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(provider_id, label) DO UPDATE SET
                    api_key               = excluded.api_key,
                    daily_limit_tokens    = excluded.daily_limit_tokens,
                    monthly_limit_tokens  = excluded.monthly_limit_tokens
                """,
                (provider_id, label, api_key, daily_limit_tokens, monthly_limit_tokens),
            )
            await db.commit()

    async def update_key_usage(
        self,
        provider_id: str,
        label: str,
        *,
        api_key: str = "",
        tokens_in: int = 0,
        tokens_out: int = 0,
        errors: int = 0,
    ) -> None:
        """Increment usage counters for a key row, creating the row if needed."""
        now = time.time()
        async with aiosqlite.connect(self.db_path) as db:
            # Upsert to handle .env keys that were never explicitly saved
            await db.execute(
                """
                INSERT INTO llm_provider_keys (provider_id, label, api_key,
                    usage_calls, usage_tokens_in, usage_tokens_out, usage_errors, last_used_at)
                VALUES (?, ?, ?, 1, ?, ?, ?, ?)
                ON CONFLICT(provider_id, label) DO UPDATE SET
                    api_key          = CASE WHEN excluded.api_key != '' THEN excluded.api_key ELSE api_key END,
                    usage_calls      = usage_calls + 1,
                    usage_tokens_in  = usage_tokens_in  + excluded.usage_tokens_in,
                    usage_tokens_out = usage_tokens_out + excluded.usage_tokens_out,
                    usage_errors     = usage_errors     + excluded.usage_errors,
                    last_used_at     = excluded.last_used_at
                """,
                (provider_id, label, api_key, tokens_in, tokens_out, errors, now),
            )
            await db.commit()

    async def set_key_limits(
        self,
        provider_id: str,
        label: str,
        api_key: str,
        *,
        daily_limit_tokens: int = 0,
        monthly_limit_tokens: int = 0,
    ) -> None:
        """Upsert the limit columns for a key row, creating the row if needed."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO llm_provider_keys
                    (provider_id, label, api_key, daily_limit_tokens, monthly_limit_tokens)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(provider_id, label) DO UPDATE SET
                    api_key              = excluded.api_key,
                    daily_limit_tokens   = excluded.daily_limit_tokens,
                    monthly_limit_tokens = excluded.monthly_limit_tokens
                """,
                (provider_id, label, api_key, daily_limit_tokens, monthly_limit_tokens),
            )
            await db.commit()

    async def reset_key_usage(self, provider_id: str, label: str) -> None:
        """Zero out all usage counters for a key."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE llm_provider_keys
                SET usage_calls=0, usage_tokens_in=0, usage_tokens_out=0,
                    usage_errors=0, last_used_at=0
                WHERE provider_id = ? AND label = ?
                """,
                (provider_id, label),
            )
            await db.commit()

    async def delete_provider_key(self, provider_id: str, label: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM llm_provider_keys WHERE provider_id = ? AND label = ?",
                (provider_id, label),
            )
            await db.commit()

    async def load_provider_keys(self, provider_id: str) -> list[dict]:
        """Return all keys for a provider with full usage stats."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT label, api_key,
                       usage_calls, usage_tokens_in, usage_tokens_out, usage_errors,
                       last_used_at, daily_limit_tokens, monthly_limit_tokens
                FROM llm_provider_keys
                WHERE provider_id = ?
                ORDER BY created_at
                """,
                (provider_id,),
            ) as cur:
                rows = await cur.fetchall()
        return [
            {
                "label": r[0],
                "key": r[1],
                "usage_calls": r[2],
                "usage_tokens_in": r[3],
                "usage_tokens_out": r[4],
                "usage_errors": r[5],
                "last_used_at": r[6],
                "daily_limit_tokens": r[7],
                "monthly_limit_tokens": r[8],
            }
            for r in rows
        ]

    async def load_all_provider_keys(self) -> dict[str, list[dict]]:
        """Return all keys for all providers, grouped by provider_id."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT provider_id, label, api_key,
                       usage_calls, usage_tokens_in, usage_tokens_out, usage_errors,
                       last_used_at, daily_limit_tokens, monthly_limit_tokens
                FROM llm_provider_keys
                ORDER BY provider_id, created_at
                """
            ) as cur:
                rows = await cur.fetchall()
        result: dict[str, list[dict]] = {}
        for r in rows:
            pid = r[0]
            result.setdefault(pid, []).append({
                "label": r[1],
                "key": r[2],
                "usage_calls": r[3],
                "usage_tokens_in": r[4],
                "usage_tokens_out": r[5],
                "usage_errors": r[6],
                "last_used_at": r[7],
                "daily_limit_tokens": r[8],
                "monthly_limit_tokens": r[9],
            })
        return result

    # ─── Models ──────────────────────────────────────────────────────────────

    async def save_model(self, model: dict) -> None:
        """Upsert a model row."""
        mid = model["id"]
        extra = {
            k: v for k, v in model.items()
            if k not in ("id", "name", "provider", "enabled", "custom")
        }
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO llm_models (id, name, provider, enabled, custom, config_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name        = excluded.name,
                    provider    = excluded.provider,
                    enabled     = excluded.enabled,
                    custom      = excluded.custom,
                    config_json = excluded.config_json
                """,
                (
                    mid,
                    model.get("name", mid),
                    model.get("provider", ""),
                    int(model.get("enabled", True)),
                    int(model.get("custom", False)),
                    json.dumps(extra),
                ),
            )
            await db.commit()

    async def delete_model(self, model_id: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM llm_models WHERE id = ?", (model_id,))
            await db.commit()

    async def load_models(self) -> dict[str, dict]:
        """Return all saved models keyed by model_id."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT id, name, provider, enabled, custom, config_json FROM llm_models"
            ) as cur:
                rows = await cur.fetchall()
        result = {}
        for row in rows:
            mid, name, provider, enabled, custom, config_json = row
            extra = json.loads(config_json or "{}")
            result[mid] = {
                "id": mid,
                "name": name,
                "provider": provider,
                "enabled": bool(enabled),
                "custom": bool(custom),
                **extra,
            }
        return result

    # ─── Routing ─────────────────────────────────────────────────────────────

    async def save_routing(self, routing: dict[str, list[str]]) -> None:
        """Persist the full routing table (replaces all rows)."""
        async with aiosqlite.connect(self.db_path) as db:
            for complexity, models in routing.items():
                await db.execute(
                    """
                    INSERT INTO llm_routing (complexity, models_json)
                    VALUES (?, ?)
                    ON CONFLICT(complexity) DO UPDATE SET models_json = excluded.models_json
                    """,
                    (complexity, json.dumps(models)),
                )
            await db.commit()

    async def load_routing(self) -> dict[str, list[str]]:
        """Return the routing table, or empty dict if not persisted yet."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT complexity, models_json FROM llm_routing"
            ) as cur:
                rows = await cur.fetchall()
        return {r[0]: json.loads(r[1]) for r in rows}


# Singleton instance used by the API layer
llm_config_storage = LLMConfigStorage(settings.database_url)
