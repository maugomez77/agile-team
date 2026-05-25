from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from agile_team.orchestrator import AgileOrchestrator
from agile_team.shared.config import TeamConfig
from agile_team.shared.models import Artifact, TaskStatus

app = typer.Typer(name="agile-team", help="Multi-agent agile development team")
console = Console()


def _load_orchestrator(workspace: str = ".agile-team") -> AgileOrchestrator:
    from pathlib import Path
    from agile_team.shared.config import TeamConfig
    config_path = Path(workspace) / "config.json"
    if config_path.exists():
        config = TeamConfig(**json.loads(config_path.read_text()))
    else:
        config = TeamConfig.default()
    return AgileOrchestrator(config)


@app.command()
def init(
    workspace: str = typer.Option(".agile-team", "--workspace", "-w"),
    provider: str = typer.Option("ollama", "--provider", "-p"),
    model: str = typer.Option("llama3.2", "--model", "-m"),
):
    """Initialize a new agile team workspace."""
    ws = Path(workspace)
    config = TeamConfig.default()
    config.llm.provider = provider
    config.llm.model = model

    ws.mkdir(parents=True, exist_ok=True)
    (ws / "config.json").write_text(config.model_dump_json(indent=2))

    orch = AgileOrchestrator(config)
    console.print(f"[green]Workspace initialized at {ws.absolute()}[/green]")
    console.print(f"  LLM: {provider}/{model}")
    console.print(f"  Agents: {', '.join(orch._agents.keys())}")


@app.command()
def create(
    title: str = typer.Argument(..., help="Task title"),
    description: str = typer.Option("", "--description", "-d"),
    priority: int = typer.Option(0, "--priority", "-p", min=0, max=10),
):
    """Create a new task on the board."""
    orch = _load_orchestrator()
    task = orch.create_task(title, description, priority)
    console.print(f"[green]Created {task.id}: {task.title}[/green]")


@app.command()
def board():
    """Display the kanban board."""
    orch = _load_orchestrator()
    console.print(orch.get_board_view())


@app.command()
def run(
    task_id: Optional[str] = typer.Argument(None),
    agent: Optional[str] = typer.Option(None, "--agent", "-a"),
):
    """Run agents (all or a specific one)."""
    orch = _load_orchestrator()

    if agent:
        results = asyncio.run(orch.run_agent(agent))
        console.print(f"[green]{agent} processed {len(results)} task(s)[/green]")
        for task, artifact in results:
            console.print(f"  {task.id}: {artifact.artifact_type.value}")
    else:
        results = asyncio.run(orch.run_pipeline(task_id))
        for name, items in results.items():
            console.print(f"[green]{name}: {len(items)} task(s) processed[/green]")


@app.command()
def start(
    interval: int = typer.Option(5, "--interval", "-i"),
):
    """Start all agents in continuous polling mode."""
    orch = _load_orchestrator()
    console.print("[green]Starting all agents in background...[/green]")
    console.print(f"  Polling every {interval}s. Press Ctrl+C to stop.")
    try:
        asyncio.run(orch.start(interval))
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")


@app.command()
def status():
    """Show system status."""
    orch = _load_orchestrator()
    status = orch.get_status()

    table = Table(title="Agent Status")
    table.add_column("Agent", style="cyan")
    table.add_column("Tasks Processed")
    table.add_column("Last Run")

    for name, state in status["agents"].items():
        table.add_row(
            name,
            str(state.get("tasks_processed", 0)),
            state.get("last_run", "never"),
        )
    console.print(table)
    console.print(f"\nTotal tasks on board: {len(status['tasks'])}")


@app.command()
def apply(
    task_id: str = typer.Argument(..., help="Task ID to apply code from"),
    output_dir: str = typer.Option(".", "--output", "-o", help="Output directory for generated files"),
):
    """Extract and write code files from a task's artifacts to disk."""
    import re
    from pathlib import Path
    
    orch = _load_orchestrator()
    task = orch.board.get_task(task_id)
    
    if task is None:
        console.print(f"[red]Task {task_id} not found in local workspace[/red]")
        console.print("[yellow]Try fetching from remote...[/yellow]")
        import httpx, json as _json
        resp = httpx.get(f"https://kiwi-flow.vercel.app/api/tasks/{task_id}")
        if resp.status_code == 200:
            data = resp.json()
            from agile_team.shared.models import Task
            task = Task(**data)
        else:
            console.print("[red]Task not found remotely either[/red]")
            raise typer.Exit(1)
    
    code_artifacts = [a for a in task.artifacts if a.artifact_type.value in ("source_code", "deploy_config")]
    
    if not code_artifacts:
        console.print("[yellow]No source_code or deploy_config artifacts found. Run the Coder or DevOps agent first.[/yellow]")
        raise typer.Exit(0)
    
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    files_created = 0
    
    for artifact in code_artifacts:
        content = artifact.content
        matches = list(re.finditer(r'(?:#|//|\-\-)\s*filename:\s*(.+)', content, re.IGNORECASE))
        
        if not matches:
            lines = content.strip().split('\n')
            for i, line in enumerate(lines):
                if line.startswith('```') and i + 1 < len(lines):
                    header = lines[i + 1] if i + 1 < len(lines) else ''
                    if header and not header.startswith('```'):
                        matches = [re.match(r'^(?:\w+):\s*(.+)', header)]
                        if matches and matches[0]:
                            matches = [type('m', (), {'group': lambda s, g=matches[0].group(1): g})()]
        
        for match in matches:
            filepath = match.group(1).strip()
            file_start = match.end() if hasattr(match, 'end') else content.find(match.group(0)) + len(match.group(0))
            
            end_match = re.search(r'```', content[file_start:])
            file_content = content[file_start:file_start + end_match.start()] if end_match else content[file_start:]
            file_content = file_content.strip()
            
            if file_content:
                target = out / filepath
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(file_content)
                console.print(f"[green]  Created {target}[/green]")
                files_created += 1
    
    if files_created == 0:
        console.print("[yellow]No file markers found in artifacts. Agents should output code with '// filename: path/to/file' markers.[/yellow]")
    else:
        console.print(f"\n[green]✓ {files_created} file(s) written to {out}[/green]")


@app.command()
def web(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port", "-p"),
):
    """Start the web dashboard."""
    import uvicorn
    from agile_team.web.app import create_app

    orch = _load_orchestrator()
    web_app = create_app(orch)
    console.print(f"[green]Dashboard at http://{host}:{port}[/green]")
    uvicorn.run(web_app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    app()
