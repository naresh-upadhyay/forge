# ⚒ FORGE

**Factory for Orchestrated Reliable Generation of Enterprise-software**

FORGE is a multi-agent AI system that builds complete, production-grade applications from either HTML mockups or business requirements. A Master Architect agent coordinates specialized builder, reviewer, tester, and fixer agents — each powered by the best-fit LLM model — to deliver fully integrated, tested code.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     COMMAND LAYER                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ HTML Mockups  │  │ Requirements │  │ Feedback / Fixes │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
│         └──────────┬──────┘                   │             │
│              ┌─────▼──────┐                   │             │
│              │   INTAKE    │                   │             │
│              │   ENGINE    │                   │             │
│              └─────┬──────┘                   │             │
│              ┌─────▼──────────────────────────▼──┐          │
│              │      APPLICATION BLUEPRINT         │          │
│              └─────┬─────────────────────────────┘          │
├────────────────────┼────────────────────────────────────────┤
│              ┌─────▼──────┐   ORCHESTRATION LAYER           │
│              │   MASTER    │                                 │
│              │  ARCHITECT  │◄── Plans, Delegates, Reviews    │
│              └──┬──┬──┬───┘    Never writes code             │
│                 │  │  │                                      │
├─────────────────┼──┼──┼─────────────────────────────────────┤
│           ┌─────▼┐ │ ┌▼─────┐   EXECUTION LAYER             │
│           │Model-│ │ │Front-│                                │
│           │eler  │ │ │end   │   Agents work on branches      │
│           └──────┘ │ └──────┘   Architect merges to main     │
│         ┌──────────▼──┐                                      │
│         │  Backend    │  ┌────────┐  ┌───────┐  ┌──────┐    │
│         │  Builder    │  │Reviewer│  │Tester │  │Fixer │    │
│         └─────────────┘  └────────┘  └───────┘  └──────┘    │
└─────────────────────────────────────────────────────────────┘
```

## Key Design Decisions

1. **The Architect never writes code** — it only plans, delegates, reviews, and integrates. This separation prevents the coordinator from getting lost in implementation details.

2. **Contract-first development** — Before any code is written, the Architect generates interface contracts. Agents code to contracts. This is how parallel work succeeds.

3. **Git-based coordination** — Each agent works on a branch. The Architect merges. Full history, rollback capability, and conflict detection.

4. **Different model for review** — The Reviewer and Fixer are NEVER the same model instance that wrote the code. Fresh eyes catch more bugs.

5. **Intelligent model routing** — Not every task needs the strongest model. Simple CRUD gets Haiku. Complex logic gets Opus. This controls cost.

6. **Surgical fixes** — When feedback comes in, only the relevant files are modified. The Fixer cannot change shared code without Architect approval.

---

## Quick Start

### 1. Install

```bash
cd forge
pip install -e ".[dev]"
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env and add at least one API key:
# FORGE_ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Run via CLI

```bash
# Create a project
python run.py create "TaskManager" --stack flutter

# Build from requirements
python run.py build <PROJECT_ID> --requirements "
Build a task management application with:
- User authentication (email/password)
- Projects with team members
- Tasks with title, description, priority, due date
- Task assignment to team members
- Dashboard showing task statistics
- Notifications for due dates
"

# Build from HTML mockups
python run.py build <PROJECT_ID> --html-dir ./mockups/

# Check status
python run.py status <PROJECT_ID>

# View generated files
python run.py files <PROJECT_ID>
```

### 4. Run via API + Dashboard

```bash
# Terminal 1: Start the API server
python run.py serve
# API available at http://localhost:8000
# Swagger docs at http://localhost:8000/docs

# Terminal 2: Start the React dashboard
cd dashboard
npm install
npm run dev
# Dashboard available at http://localhost:3000
```

### 5. Run with Docker (full stack)

```bash
cd docker
ANTHROPIC_API_KEY=sk-ant-... docker-compose up
# API at http://localhost:8000, Dashboard at http://localhost:3000
```

---

## How It Works: End-to-End Flow

### Example: HTML Mockups → Flutter App

```
Input: 5 HTML mockup files
  ↓
INTAKE ENGINE
  → Parses HTML DOM, CSS, forms, navigation
  → Extracts: 5 screens, 12 components, 3 entities
  → Generates Application Blueprint
  ↓
MASTER ARCHITECT
  → Decomposes into 24 work units across 5 waves
  → Wave 0: Theme + Data Models (parallel)
  → Wave 1: Shared Widgets (parallel)
  → Wave 2: Individual Screens (5 in parallel)
  → Wave 3: Navigation + State Management
  → Wave 4: Integration Tests
  ↓
EXECUTION (per work unit)
  → Agent writes code on feature branch
  → Reviewer scores code (must be ≥ 7/10)
  → If failed: Fixer patches issues, re-review
  → If passed: Architect merges to main
  ↓
INTEGRATION CHECK
  → Verify all imports resolve
  → Verify contracts are satisfied
  → Verify navigation routes exist
  → Fix any integration issues
  ↓
OUTPUT: Complete Flutter project
  lib/
  ├── main.dart
  ├── theme/app_theme.dart
  ├── models/user.dart, task.dart...
  ├── screens/login_screen.dart, home_screen.dart...
  ├── widgets/custom_button.dart, task_card.dart...
  ├── services/api_service.dart, auth_service.dart...
  └── navigation/app_router.dart
```

### Example: Requirements → .NET Application

```
Input: Business requirements document
  ↓
INTAKE ENGINE
  → Extracts entities, user roles, workflows
  → Identifies API endpoints, business rules
  → Flags ambiguities for best-guess resolution
  → Generates Application Blueprint
  ↓
MASTER ARCHITECT
  → Plans Clean Architecture layers
  → Domain → Application → Infrastructure → API → UI
  → 40+ work units across 6 waves
  ↓
OUTPUT: Complete .NET solution
  src/
  ├── Domain/Entities, ValueObjects, Interfaces
  ├── Application/Services, Commands, Queries
  ├── Infrastructure/Data, Repositories, External
  ├── API/Controllers, Middleware, DTOs
  └── Tests/Unit, Integration
```

---

## API Reference

### Projects

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/projects` | Create a new project |
| GET | `/api/projects` | List all projects |
| GET | `/api/projects/{id}` | Get project details |
| GET | `/api/projects/{id}/blueprint` | Get project blueprint |
| GET | `/api/projects/{id}/work-units` | Get all work units |
| GET | `/api/projects/{id}/files` | Get generated files |
| GET | `/api/projects/{id}/tree` | Get file tree |
| GET | `/api/projects/{id}/events` | Get build events |

### Build

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/projects/{id}/build/requirements` | Build from requirements |
| POST | `/api/projects/{id}/build/html` | Build from HTML mockups |
| POST | `/api/projects/{id}/build/upload` | Upload HTML files and build |

### Feedback

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/projects/{id}/feedback` | Submit feedback for fixes |

### System

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/metrics` | LLM usage metrics |
| GET | `/api/config` | System configuration |
| WS | `/ws/projects/{id}` | Real-time build events |

---

## Configuration

All settings are configurable via environment variables (prefix: `FORGE_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `FORGE_ANTHROPIC_API_KEY` | — | Anthropic API key |
| `FORGE_OPENAI_API_KEY` | — | OpenAI API key |
| `FORGE_GOOGLE_API_KEY` | — | Google AI API key |
| `FORGE_MAX_PARALLEL_AGENTS` | 5 | Max concurrent agent executions |
| `FORGE_MIN_REVIEW_SCORE` | 7.0 | Minimum review score to pass (1-10) |
| `FORGE_MAX_FIX_ATTEMPTS` | 3 | Max fix attempts before force-merge |
| `FORGE_AGENT_TIMEOUT_SECONDS` | 300 | Agent execution timeout |
| `FORGE_DEFAULT_ARCHITECT_MODEL` | claude-opus | Model for architect decisions |
| `FORGE_DEFAULT_BUILDER_MODEL` | claude-sonnet | Model for code generation |
| `FORGE_DEFAULT_REVIEWER_MODEL` | claude-opus | Model for code review |

### Model Routing

FORGE automatically routes tasks to the most cost-effective model:

| Complexity | Primary Model | Fallback |
|------------|---------------|----------|
| LOW | Claude Haiku | GPT-4o Mini |
| MEDIUM | Claude Sonnet | GPT-4o |
| HIGH | Claude Opus | GPT-4o |
| CRITICAL | Claude Opus | o1 |

---

## Project Structure

```
forge/
├── forge_core/                    # Core engine
│   ├── __init__.py
│   ├── config.py                  # Settings, model routing, enums
│   ├── models.py                  # All data models (Project, Blueprint, WorkUnit, etc.)
│   ├── events.py                  # Real-time async event bus
│   ├── orchestrator.py            # Top-level pipeline (entry point for builds)
│   ├── architect/
│   │   ├── __init__.py
│   │   └── master.py              # Master Architect (plans, delegates, reviews, merges)
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py                # BaseAgent class (LLM calls, parsing, error handling)
│   │   └── specialized.py         # Modeler, BackendBuilder, FrontendBuilder, Reviewer,
│   │                              #   Tester, Fixer, IntegrationChecker agents
│   ├── intake/
│   │   ├── __init__.py
│   │   └── engine.py              # Parses HTML mockups & requirements → Blueprint
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── gateway.py             # LiteLLM gateway with model routing & caching
│   │   └── prompts/
│   │       ├── __init__.py
│   │       └── templates.py       # System prompts for every agent role
│   ├── workspace/
│   │   ├── __init__.py
│   │   └── manager.py             # Git-style branch/merge file workspace
│   └── feedback/
│       ├── __init__.py
│       └── handler.py             # Feedback categorization & routing
├── api/
│   ├── __init__.py
│   └── main.py                    # FastAPI app (REST + WebSocket endpoints)
├── dashboard/                     # React monitoring UI (Vite + React 18)
│   ├── App.jsx                    # Main dashboard component (all pages)
│   ├── index.html                 # HTML entry point
│   ├── package.json               # Node dependencies
│   ├── vite.config.js             # Vite config with API proxy
│   ├── Dockerfile                 # Dashboard container (Node.js)
│   └── src/
│       └── main.jsx               # React mount point
├── docker/
│   ├── Dockerfile                 # API server container (Python)
│   └── docker-compose.yml         # Full stack: API + Redis + Dashboard
├── tests/
│   ├── __init__.py
│   └── test_core.py               # Unit tests for models, workspace, events, API
├── run.py                         # CLI runner (create, build, status, files, serve)
├── pyproject.toml                 # Python dependencies & tool config
├── .env.example                   # Configuration template
└── README.md
```

---

## Extending FORGE

### Adding a New Agent

1. Create a new class in `forge_core/agents/specialized.py`:
```python
class MyCustomAgent(BaseAgent):
    role = AgentRole.CUSTOM
    system_prompt = "Your system prompt here..."
    default_complexity = TaskComplexity.MEDIUM
```

2. Register it in `AGENT_REGISTRY`
3. Map work unit types to it in `WORK_TYPE_TO_AGENT`

### Adding a New Tech Stack

1. Add the stack to `TechStack` enum in `models.py`
2. Create stack-specific prompt templates in `prompts/templates.py`
3. Update the Architect's decomposition logic for stack-specific patterns

### Adding a New LLM Provider

1. Add the model to `LLMModel` enum in `config.py`
2. Update `MODEL_ROUTING` with the new model
3. LiteLLM handles the actual API call — just ensure the provider is supported

---

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=forge_core --cov=api
```

---

## License

MIT
