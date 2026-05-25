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
    repo: str = typer.Option("", "--repo", "-r", help="GitHub repo name to create and push to (e.g. sports-api)"),
    repo_private: bool = typer.Option(False, "--private", help="Make the GitHub repo private"),
):
    """Extract and write code files from a task's artifacts to disk, optionally pushing to GitHub."""
    import re, subprocess
    from pathlib import Path
    
    orch = _load_orchestrator()
    task = orch.board.get_task(task_id)
    
    if task is None:
        import httpx
        resp = httpx.get(f"https://kiwi-flow.vercel.app/api/tasks/{task_id}")
        if resp.status_code == 200:
            from agile_team.shared.models import Task
            task = Task(**resp.json())
        else:
            console.print("[red]Task not found[/red]")
            raise typer.Exit(1)
    
    code_artifacts = [a for a in task.artifacts if a.artifact_type.value in ("source_code", "deploy_config")]
    
    if not code_artifacts:
        console.print("[yellow]No code artifacts found. Run Coder or DevOps agent first.[/yellow]")
        raise typer.Exit(0)
    
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    files_created = 0
    
    for artifact in code_artifacts:
        content = artifact.content
        
        # Method 1: explicit file markers
        explicit = list(re.finditer(r'(?:#|//|\-\-)\s*filename:\s*(.+)', content, re.IGNORECASE))
        
        # Method 2: code blocks with optional filename ```lang:path
        code_blocks = list(re.finditer(r'```(\w+)?(?::(\S+))?\n(.*?)```', content, re.DOTALL))
        
        # Method 3: old format with file headers
        old_format = list(re.finditer(r'(?:^|\n)([\w/.-]+\.[\w]+)\n```', content))
        
        for match in explicit:
            filepath = match.group(1).strip()
            rest = content[match.end():]
            end_match = re.search(r'```|^// filename:', rest, re.MULTILINE)
            file_content = rest[:end_match.start()].strip() if end_match else rest.strip()
            if file_content:
                target = out / filepath
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(file_content)
                console.print(f"[green]  ✓ {target}[/green]")
                files_created += 1
        
        if not explicit and code_blocks:
            for block in code_blocks:
                lang = block.group(1) or ''
                filepath = block.group(2) or ''
                code = block.group(3).strip()
                
                if not filepath:
                    ext_map = {'js':'src/index.js','py':'src/main.py','ts':'src/index.ts',
                              'yml':'ci.yml','yaml':'ci.yml','dockerfile':'Dockerfile',
                              'json':'config.json','html':'index.html','css':'styles.css'}
                    for ext, default in ext_map.items():
                        if lang.lower() == ext or (not lang and ext in code[:50].lower()):
                            filepath = default
                            break
                
                if filepath and code:
                    target = out / filepath
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(code)
                    console.print(f"[green]  ✓ {target}[/green]")
                    files_created += 1
    
    if files_created == 0:
        console.print("[yellow]No file markers found. Agents should output with '// filename: path/to/file' markers.[/yellow]")
        raise typer.Exit(0)
    
    console.print(f"\n[green]✓ {files_created} file(s) written to {out}[/green]")
    
    if repo:
        console.print(f"\n[bold]Creating GitHub repo: {repo}[/bold]")
        try:
            subprocess.run(["git", "init"], cwd=out, capture_output=True, check=True)
            subprocess.run(["git", "add", "-A"], cwd=out, capture_output=True, check=True)
            subprocess.run(["git", "commit", "-m", f"Generated from {task_id}: {task.title}"], cwd=out, capture_output=True, check=True)
            
            visibility = "--private" if repo_private else "--public"
            result = subprocess.run(
                ["gh", "repo", "create", repo, "--source=.", "--push", visibility, 
                 "--description", f"Generated from {task_id}: {task.title}"],
                cwd=out, capture_output=True, text=True
            )
            if result.returncode == 0:
                remote = result.stdout.strip().split("\n")[-1] if result.stdout else f"github.com/maugomez77/{repo}"
                console.print(f"[green]✓ Pushed to {remote}[/green]")
            else:
                console.print(f"[yellow]gh repo create warning: {result.stderr.strip()}[/yellow]")
                console.print("[yellow]Repo may already exist. Trying push...[/yellow]")
                subprocess.run(["git", "remote", "add", "origin", f"git@github.com:maugomez77/{repo}.git"], cwd=out, capture_output=True)
                subprocess.run(["git", "push", "-u", "origin", "main"], cwd=out, capture_output=True)
                console.print(f"[green]✓ Pushed to github.com/maugomez77/{repo}[/green]")
        except Exception as e:
            console.print(f"[red]GitHub push failed: {e}[/red]")
            console.print("[yellow]Files are still available locally at {out}[/yellow]")


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
