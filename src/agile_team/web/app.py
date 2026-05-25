from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from agile_team.orchestrator import AgileOrchestrator

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Agile Team Dashboard</title>
<style>
  :root { --bg: #1a1a2e; --card: #16213e; --accent: #0f3460; --text: #e0e0e0; --green: #4ecca3; --yellow: #ffd369; --red: #e94560; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'SF Mono', 'Fira Code', monospace; background: var(--bg); color: var(--text); padding: 20px; }
  h1 { color: var(--green); margin-bottom: 20px; }
  .board { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }
  .column { background: var(--card); border-radius: 8px; padding: 15px; min-height: 200px; }
  .column h2 { font-size: 14px; text-transform: uppercase; margin-bottom: 10px; padding-bottom: 8px; border-bottom: 2px solid var(--accent); }
  .task { background: var(--accent); border-radius: 4px; padding: 10px; margin-bottom: 8px; font-size: 12px; cursor: pointer; }
  .task.pending { border-left: 3px solid var(--yellow); }
  .task.done { border-left: 3px solid var(--green); opacity: 0.6; }
  .task.blocked { border-left: 3px solid var(--red); }
  .task .id { color: var(--green); font-weight: bold; }
  .agent-panel { margin-top: 30px; background: var(--card); border-radius: 8px; padding: 15px; }
  .agent-panel h2 { margin-bottom: 10px; }
  .agent-row { display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid var(--accent); }
  .agent-row .status { color: var(--green); }
  .agent-row .idle { color: var(--yellow); }
  #log { margin-top: 20px; background: var(--card); border-radius: 8px; padding: 15px; max-height: 300px; overflow-y: auto; font-size: 12px; }
  #log .entry { padding: 3px 0; border-bottom: 1px solid #1a1a3e; }
  .controls { margin: 20px 0; display: flex; gap: 10px; }
  .controls input, .controls button { padding: 8px 12px; border: none; border-radius: 4px; font-family: inherit; }
  .controls input { background: var(--bg); color: var(--text); border: 1px solid var(--accent); flex: 1; }
  .controls button { background: var(--accent); color: var(--text); cursor: pointer; }
  .controls button:hover { background: var(--green); }
</style>
</head>
<body>
<h1>Agile Team Dashboard</h1>

<div class="controls">
  <input id="taskTitle" placeholder="Task title..." />
  <input id="taskDesc" placeholder="Description (optional)" />
  <button onclick="createTask()">Create Task</button>
  <button onclick="runPipeline()">Run Pipeline</button>
</div>

<div class="board" id="board"></div>

<div class="agent-panel">
  <h2>Agents</h2>
  <div id="agents"></div>
</div>

<div id="log"><h2>Activity Log</h2></div>

<script>
const ws = new WebSocket(`ws://${location.host}/ws`);
let currentState = {};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  currentState = data;
  render();
};

function render() {
  const columns = {
    backlog: [], spec_ready: [], spec_in_progress: [], arch_ready: [], arch_in_progress: [],
    code_ready: [], code_in_progress: [], test_ready: [], test_in_progress: [],
    deploy_ready: [], deploy_in_progress: [], done: [], blocked: []
  };

  (currentState.tasks || []).forEach(t => {
    if (columns[t.status] !== undefined) columns[t.status].push(t);
  });

  document.getElementById('board').innerHTML = Object.entries(columns).map(([col, tasks]) => {
    return `<div class="column"><h2>${col.replace(/_/g, ' ')} (${tasks.length})</h2>` +
      tasks.map(t => {
        let cls = 'task';
        if (t.status === 'done') cls += ' done';
        else if (t.status === 'blocked') cls += ' blocked';
        else if (t.status !== 'backlog') cls += ' pending';
        return `<div class="${cls}"><span class="id">${t.id}</span><br>${t.title}<br><small>P${t.priority}</small></div>`;
      }).join('') + `</div>`;
  }).join('');

  const agents = currentState.agents || {};
  document.getElementById('agents').innerHTML = Object.entries(agents).map(([name, state]) => {
    return `<div class="agent-row"><span>${name}</span><span class="${state.last_run ? 'status' : 'idle'}">${state.tasks_processed || 0} tasks</span></div>`;
  }).join('');
}

function createTask() {
  const title = document.getElementById('taskTitle').value;
  const desc = document.getElementById('taskDesc').value;
  if (!title) return;
  ws.send(JSON.stringify({ action: 'create_task', title, description: desc, priority: 5 }));
  document.getElementById('taskTitle').value = '';
  document.getElementById('taskDesc').value = '';
}

function runPipeline() {
  ws.send(JSON.stringify({ action: 'run_pipeline' }));
}

function addLog(msg) {
  const log = document.getElementById('log');
  const entry = document.createElement('div');
  entry.className = 'entry';
  entry.textContent = new Date().toLocaleTimeString() + ' - ' + msg;
  log.appendChild(entry);
  if (log.children.length > 50) log.removeChild(log.firstChild);
}
</script>
</body>
</html>"""


def create_app(orchestrator: AgileOrchestrator) -> FastAPI:
    app = FastAPI(title="Agile Team Dashboard")

    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        return DASHBOARD_HTML

    @app.get("/api/status")
    async def api_status():
        return orchestrator.get_status()

    @app.post("/api/tasks")
    async def create_task(data: dict):
        task = orchestrator.create_task(
            title=data.get("title", "Untitled"),
            description=data.get("description", ""),
            priority=data.get("priority", 0),
        )
        return task.model_dump()

    @app.post("/api/run")
    async def run_pipeline(data: dict | None = None):
        task_id = data.get("task_id") if data else None
        results = await orchestrator.run_pipeline(task_id)
        return {"status": "ok", "results": {k: len(v) for k, v in results.items()}}

    @app.get("/api/board")
    async def board_view():
        return orchestrator.get_board_view()

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws.accept()
        try:
            while True:
                data = await ws.receive_text()
                msg = json.loads(data)
                action = msg.get("action")

                if action == "create_task":
                    orchestrator.create_task(
                        title=msg.get("title", "Untitled"),
                        description=msg.get("description", ""),
                        priority=msg.get("priority", 0),
                    )
                elif action == "run_pipeline":
                    await orchestrator.run_pipeline()

                await ws.send_json(orchestrator.get_status())
        except WebSocketDisconnect:
            pass

    return app
