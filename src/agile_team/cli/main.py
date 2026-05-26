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
def work(
    output_dir: str = typer.Option(".", "--output", "-o", help="Output directory for generated code"),
    repo: str = typer.Option("", "--repo", "-r", help="GitHub repo to push to"),
    test: bool = typer.Option(True, "--test/--no-test", help="Run tests after generating code"),
):
    """Connect to kiwi-flow, pull tasks, execute locally, push results back."""
    import httpx, subprocess, re as _re, os
    from pathlib import Path
    
    API = "https://kiwi-flow.vercel.app/api"
    
    console.print("[bold]Connecting to kiwi-flow...[/bold]")
    
    # Get board and find actionable tasks
    resp = httpx.get(f"{API}/board")
    if resp.status_code != 200:
        console.print("[red]Could not connect to kiwi-flow[/red]")
        raise typer.Exit(1)
    
    board = resp.json()
    actionable = []
    for col, tasks in board.get("columns", {}).items():
        if col in ("code_ready", "test_ready", "deploy_ready"):
            actionable.extend(tasks)
    
    if not actionable:
        console.print("[yellow]No actionable tasks found on kiwi-flow[/yellow]")
        raise typer.Exit(0)
    
    console.print(f"Found {len(actionable)} task(s) ready for work\n")
    
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    all_files = 0
    
    for task_data in actionable[:3]:  # max 3 per run
        task_id = task_data["id"]
        console.print(f"[bold]Working on {task_id}: {task_data['title'][:60]}[/bold]")
        
        # Fetch full task
        task_resp = httpx.get(f"{API}/tasks/{task_id}")
        if task_resp.status_code != 200:
            console.print(f"  [red]Could not fetch task[/red]")
            continue
        
        task = task_resp.json()
        artifacts = task.get("artifacts", [])
        
        # Check for linked GitHub repo from publish comment (latest first)
        repo_name = repo
        if not repo_name:
            for e in reversed(task.get("activity_log", [])):
                msg = e.get("message", "")
                if "github.com/maugomez77/" in msg:
                    import re as _re3
                    match = _re3.search(r'github\.com/maugomez77/([a-zA-Z0-9_-]+)', msg)
                    if match:
                        repo_name = match.group(1)
                        break
        
        if not repo_name:
            repo_name = "sports-api"  # fallback
        repo_url = f"https://github.com/maugomez77/{repo_name}.git"
        
        # Try cloning the repo first
        cloned = False
        try:
            clone_result = subprocess.run(
                ["git", "clone", repo_url, str(out)], 
                capture_output=True, text=True, timeout=15
            )
            if clone_result.returncode == 0:
                console.print(f"  [green]✓ Cloned {repo_url}[/green]")
                cloned = True
        except Exception:
            pass
        
        if cloned:
            # Run tests on cloned repo
            if test:
                console.print(f"  Running npm install...")
                subprocess.run(["npm", "install"], cwd=out, capture_output=True, timeout=60)
                console.print(f"  Running tests...")
                try:
                    result = subprocess.run(["npm", "test"], cwd=out, capture_output=True, text=True, timeout=30)
                    test_output = result.stdout + result.stderr
                    passed = result.returncode == 0
                    icon = "✓" if passed else "✗"
                    console.print(f"  {icon} Tests {'passed' if passed else 'failed'}")
                    
                    httpx.post(f"{API}/tasks/{task_id}/comments", json={
                        "agent": "opencode",
                        "message": f"Tests {'passed' if passed else 'failed'} on cloned repo {repo_url}.\n{test_output[:300]}",
                        "action": "commented"
                    })
                    
                    if passed:
                        httpx.post(f"{API}/tasks/{task_id}/move", json={"status": "test_ready"})
                        
                        # Auto-deploy to Vercel after tests pass
                        console.print(f"  Deploying to Vercel...")
                        try:
                            import re as _re4
                            deploy_result = subprocess.run(
                                ["npx", "vercel", "--prod", "--yes", "--token", os.environ.get("VERCEL_TOKEN", "")],
                                cwd=out, capture_output=True, text=True, timeout=90
                            )
                            combined = deploy_result.stdout + deploy_result.stderr
                            deploy_url = ""
                            for line in combined.split('\n'):
                                match = _re4.search(r'(https://[a-zA-Z0-9_-]+\.vercel\.app)', line)
                                if match:
                                    deploy_url = match.group(1)
                            if deploy_url:
                                console.print(f"  [green]✓ Deployed to {deploy_url}[/green]")
                                httpx.post(f"{API}/tasks/{task_id}/comments", json={
                                    "agent": "opencode",
                                    "message": f"Deployed to {deploy_url}\n\nEndpoint: {deploy_url}/v1/sports",
                                    "action": "commented"
                                })
                                httpx.post(f"{API}/tasks/{task_id}/move", json={"status": "done"})
                            else:
                                console.print(f"  [yellow]Deploy OK but URL not detected. Output: {combined[:200]}[/yellow]")
                        except Exception as e:
                            console.print(f"  [yellow]Deploy error: {e}[/yellow]")
                    else:
                        httpx.post(f"{API}/tasks/{task_id}/move", json={"status": "code_ready"})
                except Exception as e:
                    console.print(f"  [yellow]Test error: {e}[/yellow]")
            all_files += 1  # count the cloned repo
            continue
        
        # Fallback: extract from artifacts
        code_artifacts = [a for a in artifacts if a.get("artifact_type") in ("source_code", "deploy_config")]
        if not code_artifacts:
            console.print(f"  [yellow]No code artifacts yet - need to run Coder on dashboard[/yellow]")
            continue
        
        # Extract files
        files = 0
        for a in code_artifacts:
            content = a.get("content", "")
            for m in _re.finditer(r'```(\w*)\n(.*?)```', content, _re.DOTALL):
                lang = m.group(1) or ""
                code = m.group(2).strip()
                if not code or len(code) < 20:
                    continue
                ext_map = {"js": "src/index.js", "py": "src/main.py", "ts": "src/index.ts",
                          "yml": ".github/workflows/ci.yml", "json": "package.json",
                          "javascript": "src/index.js", "markdown": "README.md"}
                filepath = ext_map.get(lang.lower(), f"src/{lang}_output.txt")
                target = out / filepath
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(code)
                console.print(f"  [green]✓ {target}[/green]")
                files += 1
        
        if files == 0:
            console.print(f"  [yellow]No code blocks found in artifacts[/yellow]")
            continue
        
        all_files += files
        
        # Write task summary
        summary = f"# {task['title']}\n\n**ID:** {task_id}\n**Status:** {task.get('status','?')}\n\nGenerated from kiwi-flow"
        (out / "TASK.md").write_text(summary)
        
        # Run tests
        if test:
            console.print(f"  Running tests...")
            try:
                result = subprocess.run(["npm", "test"], cwd=out, capture_output=True, text=True, timeout=30)
                test_output = result.stdout + result.stderr
                passed = "PASS" in test_output or result.returncode == 0
                icon = "✓" if passed else "✗"
                console.print(f"  {icon} Tests {'passed' if passed else 'failed'}")
                
                # Report back to kiwi-flow
                httpx.post(f"{API}/tasks/{task_id}/comments", json={
                    "agent": "opencode",
                    "message": f"Tests {'passed' if passed else 'failed'}. {test_output[:300]}",
                    "action": "commented"
                })
                
                if passed:
                    httpx.post(f"{API}/tasks/{task_id}/move", json={"status": "test_ready"})
                else:
                    # Feed error back so Coder can fix
                    console.print(f"  [yellow]Reporting failure to kiwi-flow for auto-fix...[/yellow]")
                    httpx.post(f"{API}/tasks/{task_id}/comments", json={
                        "agent": "opencode",
                        "message": f"Tests failed. Sending back to code_ready for auto-fix.\n\n{test_output[:500]}",
                        "action": "commented"
                    })
                    httpx.post(f"{API}/tasks/{task_id}/move", json={"status": "code_ready"})
            except Exception as e:
                console.print(f"  [yellow]Test run failed: {e}[/yellow]")
        
        # Push to GitHub
        if repo:
            try:
                subprocess.run(["git", "init"], cwd=out, capture_output=True)
                subprocess.run(["git", "add", "-A"], cwd=out, capture_output=True)
                subprocess.run(["git", "commit", "-m", f"Generated from {task_id}"], cwd=out, capture_output=True)
                result = subprocess.run(
                    ["gh", "repo", "create", repo, "--source=.", "--push", "--public",
                     "--description", f"Generated from {task_id}: {task['title']}"],
                    cwd=out, capture_output=True, text=True
                )
                if result.returncode == 0:
                    console.print(f"  [green]✓ Pushed to github.com/maugomez77/{repo}[/green]")
                    httpx.post(f"{API}/tasks/{task_id}/comments", json={
                        "agent": "opencode",
                        "message": f"Pushed to github.com/maugomez77/{repo}",
                        "action": "commented"
                    })
            except Exception as e:
                console.print(f"  [yellow]Git push failed: {e}[/yellow]")
    
    console.print(f"\n[green]✓ {all_files} files generated in {out}[/green]")


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
        console.print("[yellow]No file markers or code blocks found.[/yellow]")
    else:
        console.print(f"\n[green]✓ {files_created} file(s) written to {out}[/green]")
    
    # Write all artifacts as docs
    docs_dir = out / "docs" / "artifacts"
    docs_dir.mkdir(parents=True, exist_ok=True)
    for a in task.artifacts:
        ext = "md"
        safe_type = a.artifact_type.value.replace("/", "-")
        name = f"{a.created_by}_{safe_type}_{a.id[:6]}.{ext}"
        (docs_dir / name).write_text(a.content)
    console.print(f"[green]✓ {len(task.artifacts)} artifact(s) archived to {docs_dir}[/green]")
    
    # Write task summary
    summary = f"""# {task.title}
**ID:** {task.id}
**Status:** {task.status.value}
**Priority:** P{task.priority}
**Description:** {task.description}

## Artifacts
"""
    for a in task.artifacts:
        summary += f"\n- **{a.artifact_type.value}** by {a.created_by} ({len(a.content)} chars)"
    
    summary += f"\n\n## Activity Log ({len(task.activity_log)} entries)\n"
    for e in task.activity_log[-20:]:
        ts = e.timestamp.strftime("%Y-%m-%d %H:%M") if e.timestamp else "?"
        summary += f"\n- [{e.action}] {e.agent}: {e.message[:100]}"
    
    (out / "TASK.md").write_text(summary)
    
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
