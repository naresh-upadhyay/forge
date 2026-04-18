"""FORGE Test Suite - Tests for core system components."""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from forge_core.models import (
    AgentRole,
    Blueprint,
    Entity,
    EntityField,
    Project,
    ProjectStatus,
    Screen,
    TechStack,
    WorkUnit,
    WorkUnitStatus,
    WorkUnitType,
)
from forge_core.workspace.manager import WorkspaceManager
from forge_core.events import EventBus


# ──────────────────────────────────────────────
# Model Tests
# ──────────────────────────────────────────────

class TestModels:
    def test_project_creation(self):
        project = Project(name="TestApp", tech_stack=TechStack.FLUTTER)
        assert project.name == "TestApp"
        assert project.status == ProjectStatus.CREATED
        assert project.progress_percent == 0.0
        assert project.id is not None

    def test_project_progress(self):
        project = Project(name="TestApp", total_work_units=10, completed_work_units=5)
        assert project.progress_percent == 50.0

    def test_project_progress_zero(self):
        project = Project(name="TestApp", total_work_units=0)
        assert project.progress_percent == 0.0

    def test_work_unit_creation(self):
        wu = WorkUnit(
            type=WorkUnitType.UI_COMPONENT,
            title="Login Button",
            description="A reusable login button widget",
        )
        assert wu.status == WorkUnitStatus.PENDING
        assert wu.fix_attempts == 0
        assert wu.wave == 0

    def test_blueprint_creation(self):
        bp = Blueprint(
            name="TestApp",
            tech_stack=TechStack.FLUTTER,
            entities=[
                Entity(
                    name="User",
                    fields=[
                        EntityField(name="id", type="int", is_primary_key=True),
                        EntityField(name="email", type="String"),
                    ],
                )
            ],
            screens=[
                Screen(name="LoginScreen", route="/login"),
                Screen(name="HomeScreen", route="/home"),
            ],
        )
        assert len(bp.entities) == 1
        assert len(bp.screens) == 2
        assert bp.entities[0].fields[0].is_primary_key

    def test_tech_stack_enum(self):
        assert TechStack.FLUTTER.value == "flutter"
        assert TechStack.DOTNET.value == "dotnet"
        assert TechStack.REACT.value == "react"

    def test_work_unit_types(self):
        for wut in WorkUnitType:
            wu = WorkUnit(type=wut, title=f"Test {wut.value}")
            assert wu.type == wut


# ──────────────────────────────────────────────
# Workspace Tests
# ──────────────────────────────────────────────

class TestWorkspace:
    def setup_method(self):
        self.workspace = WorkspaceManager("test-project-123", "Test Project")

    @pytest.mark.asyncio
    async def test_initialize(self, tmp_path):
        self.workspace.root = tmp_path / "test-ws"
        result = await self.workspace.initialize("flutter")
        assert (tmp_path / "test-ws").exists()

    def test_write_and_read_file(self, tmp_path):
        self.workspace.root = tmp_path / "test-ws"
        self.workspace.root.mkdir(parents=True)
        self.workspace.write_file("lib/main.dart", "void main() {}")
        content = self.workspace.read_file("lib/main.dart")
        assert content == "void main() {}"

    def test_branch_operations(self, tmp_path):
        self.workspace.root = tmp_path / "test-ws"
        self.workspace.root.mkdir(parents=True)

        # Write to main
        self.workspace.write_file("main.dart", "original", branch="main")

        # Create branch and write
        self.workspace.create_branch("feature")
        self.workspace.write_file("new.dart", "new code", branch="feature")

        # Feature has new file, main doesn't (in memory)
        assert self.workspace.read_file("new.dart", "feature") == "new code"

        # Merge
        merged = self.workspace.merge_branch("feature", "main")
        assert "new.dart" in merged
        assert self.workspace.read_file("new.dart", "main") == "new code"

    def test_batch_write(self, tmp_path):
        self.workspace.root = tmp_path / "test-ws"
        self.workspace.root.mkdir(parents=True)

        files = {
            "lib/main.dart": "void main() {}",
            "lib/app.dart": "class App {}",
            "test/test.dart": "void test() {}",
        }
        self.workspace.write_files_batch(files)
        assert len(self.workspace.get_file_list()) == 3

    def test_get_all_files(self, tmp_path):
        self.workspace.root = tmp_path / "test-ws"
        self.workspace.root.mkdir(parents=True)

        self.workspace.write_file("a.dart", "A")
        self.workspace.write_file("b.dart", "B")

        all_files = self.workspace.get_all_files()
        assert len(all_files) == 2
        assert all_files["a.dart"] == "A"

    def test_project_tree(self, tmp_path):
        self.workspace.root = tmp_path / "test-ws"
        self.workspace.root.mkdir(parents=True)

        self.workspace.write_file("lib/main.dart", "code")
        self.workspace.write_file("lib/screens/home.dart", "code")

        tree = self.workspace.get_project_tree()
        assert "main.dart" in tree


# ──────────────────────────────────────────────
# Event Bus Tests
# ──────────────────────────────────────────────

class TestEventBus:
    def setup_method(self):
        self.bus = EventBus()

    @pytest.mark.asyncio
    async def test_emit_and_history(self):
        await self.bus.emit("proj1", "info", "Test event")
        history = self.bus.get_history("proj1")
        assert len(history) == 1
        assert history[0].message == "Test event"

    @pytest.mark.asyncio
    async def test_subscriber_receives_events(self):
        received = []

        async def handler(event):
            received.append(event)

        self.bus.subscribe("proj1", handler)
        await self.bus.emit("proj1", "info", "Hello")
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_queue_for_websocket(self):
        queue = self.bus.get_queue("proj1")
        await self.bus.emit("proj1", "info", "Queued event")
        event = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert event.message == "Queued event"

    @pytest.mark.asyncio
    async def test_cleanup(self):
        await self.bus.emit("proj1", "info", "event")
        self.bus.cleanup("proj1")
        assert self.bus.get_history("proj1") == []


# ──────────────────────────────────────────────
# Intake Engine Tests
# ──────────────────────────────────────────────

class TestIntakeEngine:
    def test_preparse_html(self):
        from forge_core.intake.engine import IntakeEngine
        engine = IntakeEngine()

        html = """
        <html>
        <head><title>Login Page</title>
        <style>
            .btn { color: #FF5733; font-family: Roboto; }
        </style>
        </head>
        <body>
            <header><nav>Menu</nav></header>
            <form action="/login" method="POST">
                <input type="email" name="email" placeholder="Email" required>
                <input type="password" name="password" placeholder="Password">
                <button type="submit">Login</button>
            </form>
            <a href="/register">Register</a>
        </body>
        </html>
        """

        result = engine._preparse_html(html, "login.html")
        assert result["title"] == "Login Page"
        assert len(result["forms"]) == 1
        assert len(result["forms"][0]["fields"]) == 2
        assert "#FF5733" in result["colors"]
        assert len(result["links"]) == 1

    def test_parse_json_response_clean(self):
        from forge_core.intake.engine import IntakeEngine
        engine = IntakeEngine()

        data = {"app_name": "Test", "screens": []}
        result = engine._parse_json_response(json.dumps(data))
        assert result["app_name"] == "Test"

    def test_parse_json_response_markdown_wrapped(self):
        from forge_core.intake.engine import IntakeEngine
        engine = IntakeEngine()

        raw = '```json\n{"app_name": "Test"}\n```'
        result = engine._parse_json_response(raw)
        assert result["app_name"] == "Test"

    def test_parse_json_response_with_text(self):
        from forge_core.intake.engine import IntakeEngine
        engine = IntakeEngine()

        raw = 'Here is the analysis:\n{"app_name": "Test", "screens": []}\nDone!'
        result = engine._parse_json_response(raw)
        assert result["app_name"] == "Test"


# ──────────────────────────────────────────────
# Architect Tests
# ──────────────────────────────────────────────

class TestArchitect:
    def test_parse_work_unit_type(self):
        from forge_core.architect.master import MasterArchitect
        arch = MasterArchitect()

        assert arch._parse_work_unit_type("data_model") == WorkUnitType.DATA_MODEL
        assert arch._parse_work_unit_type("api_endpoint") == WorkUnitType.API_ENDPOINT
        assert arch._parse_work_unit_type("ui_screen") == WorkUnitType.UI_SCREEN
        assert arch._parse_work_unit_type("some_model_thing") == WorkUnitType.DATA_MODEL
        assert arch._parse_work_unit_type("unknown_xyz") == WorkUnitType.SERVICE

    def test_validate_dependencies(self):
        from forge_core.architect.master import MasterArchitect
        arch = MasterArchitect()

        units = [
            WorkUnit(id="wu1", type=WorkUnitType.DATA_MODEL, title="A", depends_on=[]),
            WorkUnit(id="wu2", type=WorkUnitType.SERVICE, title="B", depends_on=["wu1", "wu999"]),
        ]
        arch._validate_dependencies(units)
        # wu999 should be removed since it doesn't exist
        assert units[1].depends_on == ["wu1"]

    def test_count_by_type(self):
        from forge_core.architect.master import MasterArchitect
        arch = MasterArchitect()

        units = [
            WorkUnit(type=WorkUnitType.DATA_MODEL, title="A"),
            WorkUnit(type=WorkUnitType.DATA_MODEL, title="B"),
            WorkUnit(type=WorkUnitType.UI_SCREEN, title="C"),
        ]
        counts = arch._count_by_type(units)
        assert counts["data_model"] == 2
        assert counts["ui_screen"] == 1


# ──────────────────────────────────────────────
# API Tests
# ──────────────────────────────────────────────

class TestAPI:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from api.main import app
        return TestClient(app)

    def test_health(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_create_project(self, client):
        resp = client.post("/api/projects", json={
            "name": "TestApp",
            "tech_stack": "flutter",
            "description": "Test project",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "TestApp"
        assert "id" in data

    def test_list_projects(self, client):
        # Create a project first
        client.post("/api/projects", json={"name": "TestApp"})
        resp = client.get("/api/projects")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_get_project(self, client):
        create_resp = client.post("/api/projects", json={"name": "TestApp"})
        project_id = create_resp.json()["id"]

        resp = client.get(f"/api/projects/{project_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "TestApp"

    def test_get_nonexistent_project(self, client):
        resp = client.get("/api/projects/nonexistent")
        assert resp.status_code == 404

    def test_get_config(self, client):
        resp = client.get("/api/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert "max_parallel_agents" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
