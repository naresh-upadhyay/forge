"""Workspace Manager - Git-based workspace for project code.

Each project gets its own workspace directory with git version control.
Agents work on branches, the architect merges to main.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Optional

from forge_core.config import settings

logger = logging.getLogger(__name__)


class WorkspaceManager:
    """Manages file-based workspaces for projects with git-like branching."""

    def __init__(self, project_id: str, project_name: str):
        self.project_id = project_id
        self.project_name = self._sanitize_name(project_name)
        self.root = settings.workspace_dir / self.project_id
        self._branches: dict[str, dict[str, str]] = {"main": {}}
        self._current_branch = "main"

    def _sanitize_name(self, name: str) -> str:
        return "".join(c if c.isalnum() or c in "-_ " else "" for c in name).strip().replace(" ", "_").lower()

    async def initialize(self, tech_stack: str) -> str:
        """Create and initialize the workspace directory."""
        self.root.mkdir(parents=True, exist_ok=True)
        logger.info(f"Workspace initialized at {self.root}")
        return str(self.root)

    def create_branch(self, branch_name: str):
        """Create a new branch from current main state."""
        self._branches[branch_name] = dict(self._branches["main"])
        logger.debug(f"Branch created: {branch_name}")

    def switch_branch(self, branch_name: str):
        """Switch to a different branch."""
        if branch_name not in self._branches:
            self.create_branch(branch_name)
        self._current_branch = branch_name

    def write_file(self, filepath: str, content: str, branch: Optional[str] = None):
        """Write a file to the workspace on the specified branch."""
        target_branch = branch or self._current_branch
        if target_branch not in self._branches:
            self.create_branch(target_branch)
        self._branches[target_branch][filepath] = content

        # Also write to disk
        full_path = self.root / filepath
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        logger.debug(f"Wrote file: {filepath} on branch {target_branch}")

    def read_file(self, filepath: str, branch: Optional[str] = None) -> Optional[str]:
        """Read a file from the workspace."""
        target_branch = branch or self._current_branch
        # Try in-memory first
        if target_branch in self._branches and filepath in self._branches[target_branch]:
            return self._branches[target_branch][filepath]
        # Try disk
        full_path = self.root / filepath
        if full_path.exists():
            return full_path.read_text(encoding="utf-8")
        return None

    def merge_branch(self, source_branch: str, target_branch: str = "main") -> list[str]:
        """Merge files from source branch into target. Returns list of merged files."""
        if source_branch not in self._branches:
            logger.warning(f"Branch {source_branch} not found")
            return []

        merged = []
        source_files = self._branches[source_branch]
        if target_branch not in self._branches:
            self._branches[target_branch] = {}

        for filepath, content in source_files.items():
            self._branches[target_branch][filepath] = content
            # Write to disk
            full_path = self.root / filepath
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")
            merged.append(filepath)

        logger.info(f"Merged {len(merged)} files from {source_branch} to {target_branch}")
        return merged

    def write_files_batch(self, files: dict[str, str], branch: Optional[str] = None):
        """Write multiple files at once."""
        for filepath, content in files.items():
            self.write_file(filepath, content, branch)

    def get_all_files(self, branch: Optional[str] = None) -> dict[str, str]:
        """Get all files on a branch."""
        target_branch = branch or self._current_branch
        return dict(self._branches.get(target_branch, {}))

    def get_file_list(self, branch: Optional[str] = None) -> list[str]:
        """Get list of all file paths on a branch."""
        target_branch = branch or self._current_branch
        return list(self._branches.get(target_branch, {}).keys())

    def get_context_files(self, filepaths: list[str], branch: Optional[str] = None) -> dict[str, str]:
        """Get contents of specific files for agent context."""
        result = {}
        for fp in filepaths:
            content = self.read_file(fp, branch)
            if content:
                result[fp] = content
        return result

    def delete_branch(self, branch_name: str):
        """Delete a branch."""
        if branch_name != "main" and branch_name in self._branches:
            del self._branches[branch_name]

    def get_workspace_path(self) -> Path:
        return self.root

    def get_project_tree(self) -> str:
        """Get a text representation of the project file tree."""
        files = sorted(self.get_file_list("main"))
        if not files:
            return "(empty project)"
        lines = []
        for f in files:
            depth = f.count("/")
            indent = "  " * depth
            name = f.split("/")[-1]
            lines.append(f"{indent}{name}")
        return "\n".join(lines)
