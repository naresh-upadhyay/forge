#!/usr/bin/env python3
"""FORGE CLI - Command-line interface for running builds locally.

Usage:
    python run.py create "MyApp" --stack flutter
    python run.py build <project_id> --requirements "Build a todo app with..."
    python run.py build <project_id> --html-dir ./mockups/
    python run.py status <project_id>
    python run.py files <project_id>
    python run.py serve
"""

from __future__ import annotations

import argparse
import sys
import asyncio
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
import json
import logging
import sys
from pathlib import Path

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from forge_core.config import settings
from forge_core.events import event_bus
from forge_core.models import AgentRole, BuildEvent, ProjectStatus
from forge_core.orchestrator import orchestrator

console = Console()

logging.basicConfig(
    level=logging.WARNING,
    format="%(message)s",
)


# ──────────────────────────────────────────────
# Event Handler for CLI output
# ──────────────────────────────────────────────

AGENT_COLORS = {
    AgentRole.ARCHITECT: "bright_magenta",
    AgentRole.INTAKE: "bright_blue",
    AgentRole.MODELER: "bright_green",
    AgentRole.BACKEND_BUILDER: "bright_red",
    AgentRole.FRONTEND_BUILDER: "bright_yellow",
    AgentRole.REVIEWER: "yellow",
    AgentRole.TESTER: "cyan",
    AgentRole.FIXER: "red",
    AgentRole.DOC_WRITER: "white",
}


async def cli_event_handler(event: BuildEvent):
    """Print build events to terminal in real-time."""
    agent_name = event.agent.value if event.agent else "system"
    color = AGENT_COLORS.get(event.agent, "white") if event.agent else "dim"

    icon = {
        "status_change": "🔄",
        "agent_start": "▶️ ",
        "agent_complete": "✅",
        "review": "🔍",
        "error": "❌",
        "info": "ℹ️ ",
    }.get(event.event_type, "  ")

    console.print(
        f"  {icon} ",
        Text(f"[{agent_name:>18}]", style=color),
        f" {event.message}",
    )


# ──────────────────────────────────────────────
# Commands
# ──────────────────────────────────────────────

async def cmd_create(name: str, stack: str, backend: str | None, description: str):
    """Create a new project."""
    project = await orchestrator.create_project(
        name=name,
        tech_stack=stack,
        backend_stack=backend,
        description=description,
    )
    console.print(Panel(
        f"[bold green]Project Created[/]\n\n"
        f"  ID:    [cyan]{project.id}[/]\n"
        f"  Name:  {project.name}\n"
        f"  Stack: {project.tech_stack.value}\n"
        f"  {'Backend: ' + project.backend_stack.value if project.backend_stack else ''}\n\n"
        f"  [dim]Next: python run.py build {project.id} --requirements \"...\"[/]",
        title="⚒  FORGE",
        border_style="bright_magenta",
    ))
    return project.id


async def cmd_build_requirements(project_id: str, requirements: str):
    """Build a project from requirements text."""
    project = orchestrator.get_project(project_id)
    if not project:
        console.print(f"[red]Project {project_id} not found[/]")
        return

    console.print(Panel(
        f"[bold]Building: {project.name}[/]\n"
        f"Stack: {project.tech_stack.value}\n"
        f"Input: Business requirements ({len(requirements)} chars)",
        title="⚒  FORGE Build",
        border_style="bright_magenta",
    ))
    console.print()

    # Subscribe to events
    event_bus.subscribe(project_id, cli_event_handler)

    try:
        project = await orchestrator.build_from_requirements(project_id, requirements)

        console.print()
        if project.status == ProjectStatus.COMPLETED:
            # Show file tree
            tree = Tree(f"[bold green]✅ Build Complete: {project.name}[/]")
            files = orchestrator.get_project_files(project_id)
            for fp in sorted(files.keys()):
                tree.add(f"[cyan]{fp}[/]")

            console.print(Panel(tree, border_style="green"))
            console.print(f"\n  📁 Files written to: [cyan]{project.workspace_path}[/]")
            console.print(f"  📊 Work units: {project.completed_work_units}/{project.total_work_units} completed")
        else:
            console.print(f"[red]Build ended with status: {project.status.value}[/]")

    except Exception as e:
        console.print(f"[red]Build failed: {e}[/]")


async def cmd_build_html(project_id: str, html_dir: str):
    """Build a project from HTML mockup files."""
    project = orchestrator.get_project(project_id)
    if not project:
        console.print(f"[red]Project {project_id} not found[/]")
        return

    # Read HTML files from directory
    html_path = Path(html_dir)
    if not html_path.exists():
        console.print(f"[red]Directory not found: {html_dir}[/]")
        return

    html_files = {}
    for f in html_path.glob("*.html"):
        html_files[f.name] = f.read_text(encoding="utf-8", errors="ignore")

    if not html_files:
        console.print(f"[red]No HTML files found in {html_dir}[/]")
        return

    console.print(Panel(
        f"[bold]Building: {project.name}[/]\n"
        f"Stack: {project.tech_stack.value}\n"
        f"Input: {len(html_files)} HTML mockup files",
        title="⚒  FORGE Build",
        border_style="bright_magenta",
    ))
    console.print()

    event_bus.subscribe(project_id, cli_event_handler)

    try:
        project = await orchestrator.build_from_html_mockups(project_id, html_files)

        console.print()
        if project.status == ProjectStatus.COMPLETED:
            tree = Tree(f"[bold green]✅ Build Complete: {project.name}[/]")
            files = orchestrator.get_project_files(project_id)
            for fp in sorted(files.keys()):
                tree.add(f"[cyan]{fp}[/]")
            console.print(Panel(tree, border_style="green"))
            console.print(f"\n  📁 Files: [cyan]{project.workspace_path}[/]")
        else:
            console.print(f"[red]Build ended with status: {project.status.value}[/]")

    except Exception as e:
        console.print(f"[red]Build failed: {e}[/]")


async def cmd_status(project_id: str):
    """Show project status."""
    project = orchestrator.get_project(project_id)
    if not project:
        console.print(f"[red]Project {project_id} not found[/]")
        return

    table = Table(title=f"Project: {project.name}")
    table.add_column("Field", style="cyan")
    table.add_column("Value")

    table.add_row("ID", project.id)
    table.add_row("Status", project.status.value)
    table.add_row("Tech Stack", project.tech_stack.value)
    table.add_row("Progress", f"{project.progress_percent:.0f}%")
    table.add_row("Work Units", f"{project.completed_work_units}/{project.total_work_units}")
    table.add_row("Current Wave", f"{project.current_wave + 1}/{project.total_waves}" if project.total_waves else "N/A")
    table.add_row("Workspace", str(project.workspace_path or "Not initialized"))

    console.print(table)


async def cmd_files(project_id: str):
    """List project files."""
    files = orchestrator.get_project_files(project_id)
    if not files:
        console.print("[yellow]No files generated yet[/]")
        return

    tree = Tree(f"[bold]{project_id}[/]")
    for fp in sorted(files.keys()):
        size = len(files[fp])
        tree.add(f"[cyan]{fp}[/] [dim]({size} chars)[/]")

    console.print(tree)


def cmd_serve():
    """Start the FORGE API server."""
    import uvicorn
    console.print(Panel(
        f"[bold]Starting FORGE API Server[/]\n\n"
        f"  URL: http://{settings.api_host}:{settings.api_port}\n"
        f"  Docs: http://localhost:{settings.api_port}/docs\n\n"
        f"  [dim]Press Ctrl+C to stop[/]",
        title="⚒  FORGE Server",
        border_style="bright_magenta",
    ))
    uvicorn.run(
        "api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="⚒  FORGE - AI-Powered Application Builder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create a Flutter project
  python run.py create "EcommerceApp" --stack flutter

  # Build from requirements
  python run.py build <ID> --requirements "Build a task management app with user auth, projects, tasks, deadlines..."

  # Build from HTML mockups
  python run.py build <ID> --html-dir ./mockups/

  # Start the API server + dashboard
  python run.py serve
        """,
    )

    sub = parser.add_subparsers(dest="command")

    # Create
    create_p = sub.add_parser("create", help="Create a new project")
    create_p.add_argument("name", help="Project name")
    create_p.add_argument("--stack", default="flutter", help="Tech stack (flutter, react, dotnet, etc.)")
    create_p.add_argument("--backend", default=None, help="Backend stack (fastapi, dotnet, express, etc.)")
    create_p.add_argument("--description", default="", help="Project description")

    # Build
    build_p = sub.add_parser("build", help="Build a project")
    build_p.add_argument("project_id", help="Project ID")
    build_g = build_p.add_mutually_exclusive_group(required=True)
    build_g.add_argument("--requirements", "-r", help="Business requirements text")
    build_g.add_argument("--requirements-file", "-rf", help="File with requirements")
    build_g.add_argument("--html-dir", "-hd", help="Directory with HTML mockups")

    # Status
    status_p = sub.add_parser("status", help="Show project status")
    status_p.add_argument("project_id", help="Project ID")

    # Files
    files_p = sub.add_parser("files", help="List generated files")
    files_p.add_argument("project_id", help="Project ID")

    # Serve
    sub.add_parser("serve", help="Start the API server")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "create":
        project_id = asyncio.run(cmd_create(args.name, args.stack, args.backend, args.description))

    elif args.command == "build":
        if args.requirements:
            asyncio.run(cmd_build_requirements(args.project_id, args.requirements))
        elif args.requirements_file:
            req_text = Path(args.requirements_file).read_text(encoding="utf-8")
            asyncio.run(cmd_build_requirements(args.project_id, req_text))
        elif args.html_dir:
            asyncio.run(cmd_build_html(args.project_id, args.html_dir))

    elif args.command == "status":
        asyncio.run(cmd_status(args.project_id))

    elif args.command == "files":
        asyncio.run(cmd_files(args.project_id))

    elif args.command == "serve":
        cmd_serve()


if __name__ == "__main__":
    main()
