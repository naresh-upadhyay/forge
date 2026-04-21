"""FORGE Data Models - The data structures that power the entire system."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────

class ProjectStatus(str, Enum):
    CREATED = "created"
    ANALYZING = "analyzing"
    PLANNING = "planning"
    BUILDING = "building"
    REVIEWING = "reviewing"
    TESTING = "testing"
    FIXING = "fixing"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkUnitStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    REVISION = "revision"
    TESTING = "testing"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkUnitType(str, Enum):
    DATA_MODEL = "data_model"
    API_ENDPOINT = "api_endpoint"
    SERVICE = "service"
    UI_COMPONENT = "ui_component"
    UI_SCREEN = "ui_screen"
    NAVIGATION = "navigation"
    CONFIGURATION = "configuration"
    MIDDLEWARE = "middleware"
    TEST_SUITE = "test_suite"
    DOCUMENTATION = "documentation"
    THEME = "theme"
    STATE_MANAGEMENT = "state_management"


class AgentRole(str, Enum):
    ARCHITECT = "architect"
    MODELER = "modeler"
    BACKEND_BUILDER = "backend_builder"
    FRONTEND_BUILDER = "frontend_builder"
    REVIEWER = "reviewer"
    TESTER = "tester"
    FIXER = "fixer"
    DOC_WRITER = "doc_writer"
    INTAKE = "intake"


class TechStack(str, Enum):
    FLUTTER = "flutter"
    REACT = "react"
    ANGULAR = "angular"
    VUE = "vue"
    DOTNET = "dotnet"
    FASTAPI = "fastapi"
    DJANGO = "django"
    SPRING_BOOT = "spring_boot"
    EXPRESS = "express"
    NEXTJS = "nextjs"


class FeedbackType(str, Enum):
    VISUAL = "visual"
    FUNCTIONAL = "functional"
    PERFORMANCE = "performance"
    GENERAL = "general"


# ──────────────────────────────────────────────
# Blueprint Models
# ──────────────────────────────────────────────

class EntityField(BaseModel):
    name: str
    type: str
    required: bool = True
    default: Optional[str] = None
    description: str = ""
    constraints: list[Any] = Field(default_factory=list)
    is_primary_key: bool = False
    is_foreign_key: bool = False
    references: Optional[str] = None  # "EntityName.field"


class Entity(BaseModel):
    name: str
    description: str = ""
    fields: list[EntityField] = Field(default_factory=list)
    relationships: list[Any] = Field(default_factory=list)


class UIComponent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str
    type: str  # button, input, card, list, form, etc.
    properties: dict[str, Any] = Field(default_factory=dict)
    styles: dict[str, str] = Field(default_factory=dict)
    children: list[UIComponent] = Field(default_factory=list)
    events: list[Any] = Field(default_factory=list)


class Screen(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str
    route: str = ""
    description: str = ""
    components: list[UIComponent] = Field(default_factory=list)
    data_bindings: list[Any] = Field(default_factory=list)
    api_calls: list[Any] = Field(default_factory=list)
    source_file: Optional[str] = None  # original mockup file


class UserFlow(BaseModel):
    name: str
    description: str = ""
    steps: list[Any] = Field(default_factory=list)  # screen IDs in order
    trigger: str = ""


class APIEndpoint(BaseModel):
    path: str
    method: str = "GET"
    description: str = ""
    request_schema: dict[str, Any] = Field(default_factory=dict)
    response_schema: dict[str, Any] = Field(default_factory=dict)
    auth_required: bool = False
    related_entity: Optional[str] = None


class BusinessRule(BaseModel):
    name: str
    description: str
    entity: Optional[str] = None
    conditions: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)


class Blueprint(BaseModel):
    """The single source of truth for what the system is building."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    tech_stack: TechStack = TechStack.FLUTTER
    backend_stack: Optional[TechStack] = None
    entities: list[Entity] = Field(default_factory=list)
    screens: list[Screen] = Field(default_factory=list)
    flows: list[UserFlow] = Field(default_factory=list)
    api_endpoints: list[APIEndpoint] = Field(default_factory=list)
    business_rules: list[BusinessRule] = Field(default_factory=list)
    design_tokens: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ──────────────────────────────────────────────
# Feedback
# ──────────────────────────────────────────────

class FeedbackItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: FeedbackType = FeedbackType.GENERAL
    screen_id: Optional[str] = None
    description: str
    resolved: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ──────────────────────────────────────────────
# Work Units
# ──────────────────────────────────────────────

class WorkUnit(BaseModel):
    """A single, testable unit of work assigned to an agent."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: WorkUnitType
    title: str
    description: str = ""
    status: WorkUnitStatus = WorkUnitStatus.PENDING
    assigned_agent: Optional[AgentRole] = None
    assigned_model: Optional[str] = None

    # Dependencies
    depends_on: list[str] = Field(default_factory=list)  # work unit IDs
    wave: int = 0  # execution wave (0 = first)

    # Input context
    input_context: dict[str, Any] = Field(default_factory=dict)
    contracts: dict[str, Any] = Field(default_factory=dict)  # interface contracts

    # Output
    output_files: dict[str, str] = Field(default_factory=dict)  # filepath -> content
    output_tests: dict[str, str] = Field(default_factory=dict)

    # Quality
    review_score: Optional[float] = None
    review_feedback: str = ""
    fix_attempts: int = 0
    test_results: Optional[dict[str, Any]] = None

    # Timing
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


# ──────────────────────────────────────────────
# Project
# ──────────────────────────────────────────────

class Project(BaseModel):
    """Top-level project container."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    status: ProjectStatus = ProjectStatus.CREATED
    blueprint: Optional[Blueprint] = None
    work_units: list[WorkUnit] = Field(default_factory=list)
    tech_stack: TechStack = TechStack.FLUTTER
    backend_stack: Optional[TechStack] = None
    workspace_path: Optional[str] = None
    git_branch: str = "main"

    # Input
    input_type: str = "requirements"  # "mockups", "requirements", "hybrid"
    input_files: list[str] = Field(default_factory=list)
    input_mockups: dict[str, str] = Field(default_factory=dict)  # filename -> content
    input_text: str = ""

    # Progress
    total_work_units: int = 0
    completed_work_units: int = 0
    current_wave: int = 0
    total_waves: int = 0

    # Feedback
    feedback_history: list[FeedbackItem] = Field(default_factory=list)

    # Timing
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    @property
    def progress_percent(self) -> float:
        if self.total_work_units == 0:
            return 0.0
        return (self.completed_work_units / self.total_work_units) * 100


# FeedbackItem is defined above Project (before Work Units) to avoid forward-reference errors.


# ──────────────────────────────────────────────
# Agent Communication
# ──────────────────────────────────────────────

class AgentMessage(BaseModel):
    """Message passed between agents and the architect."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    from_agent: AgentRole
    to_agent: AgentRole
    work_unit_id: str
    message_type: str  # "assignment", "completion", "review", "feedback", "fix_request"
    content: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AgentResult(BaseModel):
    """Result returned by an agent after completing a work unit."""
    work_unit_id: str
    agent_role: AgentRole
    success: bool
    files: dict[str, str] = Field(default_factory=dict)  # filepath -> content
    tests: dict[str, str] = Field(default_factory=dict)
    message: str = ""
    errors: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class ReviewResult(BaseModel):
    """Result from the reviewer agent."""
    work_unit_id: str
    score: float  # 1-10
    passed: bool
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    security_issues: list[str] = Field(default_factory=list)
    feedback: str = ""


# ──────────────────────────────────────────────
# Build Events (for real-time dashboard)
# ──────────────────────────────────────────────

class BuildEvent(BaseModel):
    """Event emitted during the build process for real-time monitoring."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    event_type: str  # "status_change", "agent_start", "agent_complete", "review", "error", "info"
    agent: Optional[AgentRole] = None
    work_unit_id: Optional[str] = None
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
