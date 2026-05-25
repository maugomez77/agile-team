import json
import os
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from agile_team.board.service import BoardService
from agile_team.shared.config import TeamConfig
from agile_team.shared.models import TaskStatus
from agile_team.shared.storage import get_storage

import agile_team.llm.providers.ollama_provider  # noqa: F401
import agile_team.llm.providers.deepseek_provider  # noqa: F401

config = TeamConfig.load("agile-team.json")
if not config.llm.api_key:
    config.llm.api_key = (
        os.environ.get("DEEPSEEK_API_KEY", "").strip()
        or os.environ.get("OPENAI_API_KEY", "").strip()
    )
storage = get_storage()
board_service = BoardService(storage, config)

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Agile Team - Kanban Board</title>
<style>
  :root { --bg: #0d1117; --card: #161b22; --border: #30363d; --text: #c9d1d9; --muted: #8b949e;
         --green: #3fb950; --blue: #58a6ff; --yellow: #d29922; --red: #f85149; --purple: #bc8cff; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
         background: var(--bg); color: var(--text); min-height: 100vh; }
  header { background: var(--card); border-bottom: 1px solid var(--border); padding: 12px 24px;
           display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
  header h1 { font-size: 18px; color: var(--green); }
  header .subtitle { color: var(--muted); font-size: 12px; }
  .container { padding: 16px; max-width: 100%; margin: 0 auto; }
  .toolbar { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; align-items: center; }
  .toolbar input, .toolbar select, .toolbar button { padding: 6px 12px; border: 1px solid var(--border);
    border-radius: 6px; background: var(--card); color: var(--text); font-size: 12px; }
  .toolbar input { min-width: 180px; }
  .toolbar input:focus, .toolbar select:focus { border-color: var(--blue); outline: none; }
  .toolbar button { cursor: pointer; font-weight: 500; }
  .toolbar button.primary { background: var(--green); border-color: var(--green); color: #fff; }
  .toolbar button.danger { background: var(--red); border-color: var(--red); color: #fff; }
  .toolbar button:hover { opacity: 0.85; }
  .board { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(180px, 1fr); gap: 10px; overflow-x: auto; padding-bottom: 8px; }
  .column { background: var(--card); border: 1px solid var(--border); border-radius: 8px; min-height: 250px; display: flex; flex-direction: column; }
  .column-header { padding: 10px 12px; border-bottom: 1px solid var(--border); display: flex;
    justify-content: space-between; align-items: center; }
  .column-header h3 { font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }
  .column-header .count { background: var(--border); border-radius: 10px; padding: 1px 7px; font-size: 10px; }
  .column-body { padding: 6px; flex: 1; overflow-y: auto; max-height: 55vh; }
  .task-card { background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
    padding: 10px; margin-bottom: 6px; cursor: pointer; transition: border-color 0.15s; }
  .task-card:hover { border-color: var(--blue); }
  .task-card .task-id { font-size: 10px; color: var(--muted); margin-bottom: 3px; }
  .task-card .task-title { font-size: 12px; font-weight: 500; margin-bottom: 4px; line-height: 1.3; }
  .task-card .task-meta { display: flex; gap: 6px; font-size: 10px; color: var(--muted); flex-wrap: wrap; }
  .task-card .priority-badge { border-radius: 3px; padding: 1px 5px; font-size: 9px; font-weight: bold; }
  .task-card.blocked { border-left: 3px solid var(--red); }
  .modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.6); z-index: 50;
    align-items: center; justify-content: center; }
  .modal-overlay.open { display: flex; }
  .modal { background: var(--card); border: 1px solid var(--border); border-radius: 10px;
    padding: 24px; max-width: 650px; width: 90%; max-height: 80vh; overflow-y: auto; }
  .modal h2 { font-size: 16px; margin-bottom: 16px; color: var(--green); }
  .modal .field { margin-bottom: 10px; }
  .modal .field label { font-size: 10px; color: var(--muted); text-transform: uppercase; display: block; margin-bottom: 3px; }
  .modal .field .value { font-size: 13px; }
  .modal .artifact { background: var(--bg); border: 1px solid var(--border); border-radius: 4px; padding: 8px; margin-bottom: 6px; }
  .modal .artifact .type { color: var(--blue); font-size: 11px; font-weight: 600; }
  .modal .artifact .by { font-size: 10px; color: var(--muted); }
  .modal .artifact .content { font-size: 11px; margin-top: 4px; white-space: pre-wrap; max-height: 300px; overflow-y: auto; }
  .modal .actions { display: flex; gap: 6px; margin-top: 14px; flex-wrap: wrap; }
  .modal .actions button { padding: 5px 10px; border: 1px solid var(--border); border-radius: 4px;
    background: var(--bg); color: var(--text); cursor: pointer; font-size: 11px; }
  .modal .actions button:hover { border-color: var(--blue); }
  .modal .actions button.advance { background: var(--green); border-color: var(--green); color: #fff; }
  .modal .actions button.reject { background: var(--red); border-color: var(--red); color: #fff; }
  .agents { margin-top: 20px; }
  .agent-card { background: var(--card); border: 1px solid var(--border); border-radius: 8px;
    padding: 12px; text-align: center; position: relative; }
  .agent-card.disabled { opacity: 0.3; }
  .agent-card .agent-icon { font-size: 20px; font-weight: bold; margin-bottom: 4px; }
  .agent-card .agent-name { font-size: 12px; font-weight: 500; }
  .agent-card .agent-role { font-size: 10px; color: var(--muted); }
  .agent-card .agent-flow { font-size: 9px; color: var(--blue); margin-top: 4px; }
  .agent-card.lead { border-color: var(--yellow); border-width: 2px; }
  .agent-card.lead .badge { display: inline-block; background: var(--yellow); color: #000;
    font-size: 9px; padding: 1px 5px; border-radius: 3px; margin-top: 3px; }
  .agent-team { margin-top: 8px; padding-top: 8px; border-top: 1px dashed var(--border);
    display: flex; gap: 6px; justify-content: center; flex-wrap: wrap; }
  .agent-team .agent-card { background: var(--bg); padding: 8px; min-width: 90px; }
  .agent-team .agent-card .agent-icon { font-size: 15px; }
  .agent-team .agent-card .agent-name { font-size: 10px; }
  .agent-team .agent-card .agent-role { font-size: 9px; }
  .agent-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 10px; }
  .section-title { font-size: 13px; color: var(--muted); margin: 16px 0 8px; text-transform: uppercase; letter-spacing: 0.5px; }
  .config-panel { margin-top: 0; margin-bottom: 16px; background: var(--card); border: 1px solid var(--border);
    border-radius: 8px; padding: 16px; display: none; }
  .config-panel.open { display: block; }
  .config-panel h3 { font-size: 13px; margin-bottom: 10px; color: var(--yellow); }
  .config-panel pre { font-size: 11px; color: var(--muted); max-height: 300px; overflow: auto; }
  .toast { position: fixed; bottom: 20px; right: 20px; background: var(--green); color: #fff;
    padding: 10px 18px; border-radius: 8px; font-size: 12px; z-index: 100; display: none; }
  .toast.error { background: var(--red); }
  .loading { text-align: center; color: var(--muted); padding: 40px; }
  select.field-input { width: 100%; }
  .pipeline-flow { margin-top: 24px; background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 20px; overflow-x: auto; }
  .pipeline-flow h3 { font-size: 13px; color: var(--muted); margin-bottom: 14px; text-transform: uppercase; letter-spacing: 0.5px; }
  .flow { display: flex; align-items: flex-start; gap: 0; min-width: max-content; padding: 8px 0; }
  .stage-node { text-align: center; min-width: 110px; }
  .stage-node .box { border: 2px solid var(--border); border-radius: 8px; padding: 8px 10px; font-size: 11px; font-weight: 500; background: var(--bg); }
  .stage-arrow { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 0 6px; min-width: 80px; }
  .stage-arrow .line { width: 100%; height: 2px; background: var(--border); position: relative; }
  .stage-arrow .line::after { content: '▶'; position: absolute; right: -4px; top: -8px; font-size: 10px; color: var(--border); }
  .stage-arrow .agents { font-size: 9px; color: var(--blue); margin-top: 4px; text-align: center; line-height: 1.4; }
  .stage-arrow .agents span { display: block; }
  .live-feed { margin-top: 24px; background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
  .live-feed h3 { font-size: 13px; color: var(--muted); margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.5px; }
  .live-entry { display: flex; align-items: flex-start; gap: 10px; padding: 8px 0; border-bottom: 1px solid #1a1a3e; font-size: 11px; }
  .live-entry .status-dot { width: 8px; height: 8px; border-radius: 50%; margin-top: 3px; flex-shrink: 0; }
  .live-entry .status-dot.running { background: var(--yellow); animation: pulse 1.5s infinite; }
  .live-entry .status-dot.done { background: var(--green); }
  .live-entry .status-dot.error { background: var(--red); }
  .live-entry .status-dot.questions { background: var(--purple); }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }
  .live-entry .info { flex: 1; min-width: 0; }
  .live-entry .info .agent { font-weight: 600; color: var(--blue); }
  .live-entry .info .task { color: var(--green); }
  .live-entry .info .msg { color: var(--text); }
  .live-entry .time { color: var(--muted); font-size: 10px; white-space: nowrap; }
</style>
</head>
<body>
<header>
  <div>
    <h1 id="teamName"></h1>
    <span class="subtitle" id="teamDesc"></span>
  </div>
  <div style="display:flex;gap:8px;align-items:center;">
    <span id="lastUpdate" style="font-size:10px;color:var(--muted)"></span>
    <a href="/pipeline" style="font-size:11px;color:var(--green);text-decoration:none;">Pipeline</a>
    <a href="/settings" style="font-size:11px;color:var(--yellow);text-decoration:none;">Settings</a>
    <a href="/sprints" style="font-size:11px;color:var(--blue);text-decoration:none;">Sprints</a>
    <a href="/releases" style="font-size:11px;color:var(--purple);text-decoration:none;">Releases</a>
    <a href="#" onclick="event.preventDefault();toggleConfig()" style="font-size:11px;color:var(--muted);text-decoration:none;">Config</a>
  </div>
</header>

<div class="container">
  <div class="toolbar" id="toolbar"></div>

  <div class="config-panel" id="configPanel">
    <h3>Current Configuration (agile-team.json)</h3>
    <pre id="configJson"></pre>
  </div>

  <div class="board" id="board"><div class="loading">Loading board...</div></div>

  <div class="modal-overlay" id="modalOverlay" onclick="if(event.target===this)closeModal()">
    <div class="modal" id="modal"></div>
  </div>

  <div class="section-title">Agents</div>
  <div class="agent-grid" id="agents"></div>

  <div class="pipeline-flow" id="pipelineFlow">
    <h3>Agent Communication Pipeline</h3>
    <div class="flow" id="flowDiagram"></div>
  </div>

  <div class="live-feed" id="liveFeed">
    <h3>Live Activity</h3>
    <div id="liveEntries"><div style="color:var(--muted);font-size:11px;">No recent activity</div></div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
let state = {columns:{}, pipeline:[], agents:[], config:{}};
let config = null;

async function loadConfig() {
  const resp = await fetch('/api/config');
  config = await resp.json();
  document.getElementById('teamName').textContent = config.name || 'Agile Team';
  document.getElementById('teamDesc').textContent = config.description || '';
  document.getElementById('configJson').textContent = JSON.stringify(config, null, 2);
  renderToolbar();
  renderAgents();
}

function renderToolbar() {
  const fields = (config.task_fields || []);
  let html = '';
  fields.forEach(f => {
    if (f.type === 'select' && f.options) {
      html += `<select id="field_${f.key}" data-key="${f.key}">`;
      f.options.forEach(o => html += `<option value="${o}">${o}</option>`);
      html += '</select>';
    } else {
      html += `<input id="field_${f.key}" placeholder="${f.label}${f.required?'*':''}" data-key="${f.key}">`;
    }
  });
  html += '<button class="primary" onclick="createTask()">+ Create</button>';
  html += '<button class="primary" onclick="processPipeline()" style="background:var(--purple);border-color:var(--purple)">▶ Run Pipeline</button>';
  document.getElementById('toolbar').innerHTML = html;
}

function renderAgents() {
  const agents = (config.agents || []);
  document.getElementById('agents').innerHTML = agents.map(a => renderAgentCard(a, true)).join('');
  renderPipelineFlow();
}

function renderPipelineFlow() {
  const pipeline = config.pipeline || [];
  const agents = config.agents || [];
  const stageMap = {};
  pipeline.forEach(s => stageMap[s.id] = s);
  
  let html = '';
  for (let i = 0; i < pipeline.length; i++) {
    const stage = pipeline[i];
    html += `<div class="stage-node"><div class="box" style="border-color:${stage.color}">${esc(stage.label)}</div></div>`;
    
    if (i < pipeline.length - 1) {
      const nextStage = pipeline[i + 1];
      let transitionAgents = agents.filter(a => {
        if (!a.enabled) return false;
        const outs = a.output_stages || (a.output_stage ? [a.output_stage] : []);
        return a.input_stage === stage.id && outs.includes(nextStage.id);
      });
      
      if (transitionAgents.length === 0) {
        transitionAgents = agents.filter(a => 
          a.enabled && a.input_stage === stage.id && a.output_stage === nextStage.id
        );
      }
      
      const agentNames = transitionAgents.map(a => esc(a.icon + ' ' + a.name)).join('<br>');
      const isBranch = transitionAgents.some(a => (a.output_stages || []).length > 1);
      
      html += `<div class="stage-arrow">
        <div class="line" style="${isBranch ? 'border-bottom:2px dashed var(--yellow);border-top:2px dashed var(--yellow);height:6px;background:none;' : ''}"></div>
        <div class="agents" style="${isBranch ? 'color:var(--yellow)' : ''}">${agentNames || ''}</div>
      </div>`;
    }
  }
  document.getElementById('flowDiagram').innerHTML = html;
}

function renderAgentCard(a, isTop) {
  const cls = (a.enabled ? '' : ' disabled') + ((a.team||[]).length > 0 ? ' lead' : '');
  const modeLabel = a.team_mode ? {parallel:'⚡ Parallel', review:'🔍 Review', pipeline:'⛓ Pipeline'}[a.team_mode] || a.team_mode : '';
  const teamHtml = (a.team||[]).length > 0
    ? `<div class="agent-team">${a.team.map(m => renderAgentCard(m, false)).join('')}</div>`
    : '';
  const stageFlow = (a.input_stage && a.output_stage)
    ? `<div class="agent-flow">${esc(a.input_stage)} → ${esc(a.output_stage)}</div>`
    : '';
  const processBtn = isTop && a.enabled && a.input_stage && a.output_stage
    ? `<button onclick="event.stopPropagation();processAgent('${a.id}')" style="margin-top:6px;padding:3px 8px;font-size:9px;border:1px solid var(--green);border-radius:3px;background:transparent;color:var(--green);cursor:pointer;">▶ Process (${a.min_replicas||1}–${a.max_replicas||1})</button>`
    : '';

  return `<div class="agent-card${cls}">
    <div class="agent-icon">${esc(a.icon||'?')}</div>
    <div class="agent-name">${esc(a.name)}</div>
    <div class="agent-role">${esc(a.role||'')}</div>
    ${stageFlow}
    ${(a.team||[]).length > 0 ? `<div class="badge">Lead · ${a.team.length} members · ${modeLabel}</div>` : ''}
    ${processBtn}
    ${teamHtml}
  </div>`;
}

async function processAgent(agentId) {
  const cols = state.columns || {};
  const agents = config.agents || [];
  const agent = agents.find(a => a.id === agentId);
  if (!agent) return;

  const tasks = cols[agent.input_stage] || [];
  const max = agent.max_replicas || agent.replicas || 1;
  const batch = tasks.slice(0, max);
  
  if (batch.length === 0) { showToast('No tasks to process', true); return; }
  
  showToast(`${agent.name} processing ${batch.length} task(s) with ${replicas} replica(s)...`);
  
  await Promise.all(batch.map(t =>
    fetch('/api/tasks/' + t.id + '/process/' + agentId, {method:'POST'})
      .catch(e => null)
  ));
  
  showToast(`${agent.name} completed ${batch.length} task(s)`);
  refresh();
}

async function processPipeline() {
  const pipeline = state.pipeline || config?.pipeline || [];
  const agents = config.agents || [];
  for (const agent of agents) {
    if (!agent.enabled || !agent.input_stage) continue;
    const cols = state.columns || {};
    const tasks = cols[agent.input_stage] || [];
    if (tasks.length > 0) {
      showToast('Running ' + agent.name + '...');
      for (const t of tasks) {
        try {
          await fetch('/api/tasks/' + t.id + '/process/' + agent.id, {method:'POST'});
        } catch(e) {}
      }
      await refresh();
    }
  }
  showToast('Pipeline complete');
}

async function refresh() {
  const resp = await fetch('/api/board');
  state = await resp.json();
  if (!config) { config = state.config; loadConfig(); }
  
  const children = {};
  const tasks = [];
  Object.values(state.columns || {}).forEach(col => tasks.push(...col));
  tasks.forEach(t => {
    if (t.parent_id) {
      if (!children[t.parent_id]) children[t.parent_id] = [];
      children[t.parent_id].push(t);
    }
  });
  state.children = children;
  
  renderBoard();
  document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString();
}

function renderBoard() {
  const pipeline = state.pipeline || config?.pipeline || [];
  const cols = state.columns || {};
  const board = document.getElementById('board');
  const children = state.children || {};

  board.innerHTML = pipeline.map(stage => {
    const tasks = cols[stage.id] || [];
    
    const rendered = new Set();
    let cards = '';
    
    tasks.forEach(t => {
      if (rendered.has(t.id)) return;
      
      if (children[t.id] && children[t.id].length > 0) {
        const subs = children[t.id].filter(c => c.status === t.status);
        cards += renderTask(t, stage);
        rendered.add(t.id);
        subs.forEach(c => {
          cards += `<div style="margin-left:16px;border-left:2px solid var(--border);padding-left:8px;">${renderTask(c, stage)}</div>`;
          rendered.add(c.id);
        });
      } else if (t.parent_id && tasks.some(p => p.id === t.parent_id)) {
        return;
      } else {
        cards += renderTask(t, stage);
        rendered.add(t.id);
      }
    });
    
    return `<div class="column" data-stage="${stage.id}">
      <div class="column-header">
        <h3 style="color:${stage.color||'var(--text)'}">${esc(stage.label)}</h3>
        <span class="count">${tasks.length}${stage.wip_limit ? '/'+stage.wip_limit : ''}</span>
      </div>
      <div class="column-body">${cards}</div>
    </div>`;
  }).join('');
}

function renderTask(t, stage) {
  const blocked = t.status === 'blocked' ? ' blocked' : '';
  const readiness = getReadiness(t);
  const dot = {green:'🟢', yellow:'🟡', red:'🔴', neutral:'⚪'}[readiness];
  const isEpic = (state.children || {})[t.id]?.length > 0;
  const isChild = !!t.parent_id;
  const typeTag = isEpic ? ' 📦' : isChild ? ' 📎' : '';
  return `<div class="task-card${blocked}" onclick="showTask('${t.id}')" style="border-left: 3px solid var(--${readiness==='red'?'red':readiness==='yellow'?'yellow':readiness==='green'?'green':'border'})">
    <div class="task-id">${dot} ${t.id}${typeTag}</div>
    <div class="task-title">${esc(t.title)}</div>
    <div class="task-meta">
      <span class="priority-badge" style="background:${stage?.color||'#555'};color:#fff">P${t.priority}</span>
      <span>${(t.artifacts||[]).length} art.</span>
      ${isEpic ? '<span>' + state.children[t.id].length + ' subs</span>' : ''}
    </div>
  </div>`;
}

function getReadiness(t) {
  const reasons = [];
  const artifacts = t.artifacts || [];
  const log = t.activity_log || [];
  
  // 1. Blocked
  if (t.status === 'blocked') { reasons.push('Task is blocked'); }
  
  // 2. Agent error
  const lastLog = log[log.length - 1];
  if (lastLog && lastLog.action === 'error') { reasons.push('Last agent run failed with error'); }
  
  // 3. Open questions
  let hasOpenQuestions = false, lastQuestionTime = null;
  artifacts.forEach(a => {
    if ((a.content || '').substring(0, 200).includes('QUESTIONS:')) {
      hasOpenQuestions = true;
      if (a.created_at) lastQuestionTime = new Date(a.created_at);
    }
  });
  if (hasOpenQuestions && lastQuestionTime) {
    const hasResponse = log.some(e => e.action === 'commented' && e.agent === 'user' && new Date(e.timestamp) > lastQuestionTime);
    if (hasResponse) reasons.push('Questions answered');
    else reasons.push('Open questions unanswered');
  }
  
  // 4. Rejected / feedback loop
  const rejected = log.filter(e => e.action === 'moved' && e.message.includes('→'));
  const hasFeedback = (t.feedback_notes || []).length > 0;
  if (hasFeedback && rejected.length > 0 && lastLog && lastLog.action !== 'completed') {
    reasons.push('Has pending feedback from previous agent');
  }
  
  // 5. Stale (no activity in 24h)
  if (log.length > 0) {
    const lastTime = new Date(log[log.length - 1].timestamp);
    const hoursStale = (Date.now() - lastTime) / 3600000;
    if (hoursStale > 24) reasons.push('Stale: no activity for ' + Math.round(hoursStale) + 'h');
  }
  
  // 6. Short/incomplete artifact
  artifacts.forEach(a => {
    if (a.content && a.content.length < 100 && !a.content.includes('QUESTIONS:')) {
      reasons.push('Short artifact: ' + a.artifact_type + ' may be incomplete');
    }
  });
  
  // Determine color
  if (t.status === 'blocked' || (lastLog && lastLog.action === 'error')) return 'red';
  if (reasons.some(r => r.includes('Open questions') || r.includes('pending feedback') || r.includes('Stale') || r.includes('incomplete'))) return 'yellow';
  if (artifacts.length > 0 && t.status !== 'backlog') return 'green';
  return 'neutral';
}

async function showTask(taskId) {
  const resp = await fetch('/api/tasks/' + taskId);
  if (!resp.ok) return;
  const t = await resp.json();
  const pipeline = state.pipeline || config?.pipeline || [];
  const stageIds = pipeline.map(s => s.id);
  const stageLabels = {};
  pipeline.forEach(s => stageLabels[s.id] = s.label);

  const currentIdx = stageIds.indexOf(t.status);
  let nextAgent = null;
  const agents = config.agents || [];
  for (const a of agents) {
    if (a.enabled && a.input_stage === t.status) { nextAgent = a; break; }
  }

  let actions = '';
  if (nextAgent) {
    actions += `<button class="advance" onclick="processTaskAgent('${t.id}','${nextAgent.id}')">▶ ${esc(nextAgent.name)}: Generate ${esc(nextAgent.artifact_type||'output')}</button>`;
  }
  if (currentIdx >= 0 && currentIdx < stageIds.length - 1) {
    const next = stageIds[currentIdx + 1];
    actions += `<button class="advance" onclick="moveTask('${t.id}','${next}')">Advance → ${stageLabels[next]||next}</button>`;
  }
  if (currentIdx > 0) {
    const prev = stageIds[currentIdx - 1];
    actions += `<button class="reject" onclick="moveTask('${t.id}','${prev}')">← Reject to ${stageLabels[prev]||prev}</button>`;
  }
  actions += `<button onclick="moveTask('${t.id}','blocked')">Block</button>`;

  document.getElementById('modal').innerHTML = `
    <h2>${esc(t.id)}: ${esc(t.title)} <a href="/tasks/${t.id}" target="_blank" style="font-size:11px;color:var(--blue);font-weight:normal;margin-left:8px;">↗ Open full page</a></h2>
    <div class="field"><label>Status</label><div class="value">${esc(t.status)}</div></div>
    <div class="field"><label>Description</label><div class="value">${esc(t.description||'(none)')}</div></div>
    <div class="field"><label>Priority</label><div class="value">P${t.priority}</div></div>
    <div class="field"><label>Feedback</label><div class="value">${esc((t.feedback_notes||[]).join(' | ')||'(none)')}</div></div>
    <div class="field"><label>Activity Timeline</label>
      <div style="border-left:2px solid var(--border);padding-left:12px;margin-top:6px;">
        ${(t.activity_log||[]).slice().reverse().map(e => {
          const icon = {created:'+',moved:'→',completed:'✓',commented:'💬',rejected:'✗',blocked:'⊘'}[e.action]||'·';
          const time = e.timestamp ? new Date(e.timestamp).toLocaleTimeString() : '';
          return `<div style="margin-bottom:6px;font-size:11px;">
            <span style="color:var(--blue);font-weight:600;">${icon}</span>
            <span style="color:var(--green);">${esc(e.agent)}</span>
            <span style="color:var(--muted);">${time}</span><br>
            <span style="color:var(--text);">${esc(e.message)}</span>
          </div>`;
        }).join('') || '<div style="font-size:11px;color:var(--muted)">No activity yet</div>'}
      </div>
    </div>
    <div class="field"><label>Artifacts (${(t.artifacts||[]).length})</label>
      ${(t.artifacts||[]).map((a,i) => {
        const full = a.content || '';
        const short = full.substring(0, 500);
        const truncated = full.length > 500;
        const id = 'art_' + t.id + '_' + i;
        const ts = a.created_at ? new Date(a.created_at).toLocaleString() : '';
        return `<div class="artifact">
        <div class="type">${esc(a.artifact_type)} <span class="by">by ${esc(a.created_by)}</span> <span style="font-size:9px;color:var(--muted);">${ts}</span></div>
        <div class="content" id="${id}">${esc(short)}${truncated ? '<span style="color:var(--blue);cursor:pointer;" onclick="document.getElementById(\''+id+'\').innerHTML=document.getElementById(\''+id+'_full\').innerHTML">... [show full]</span>' : ''}</div>
        <div style="display:none" id="${id}_full">${esc(full)}</div>
      </div>`;
      }).join('') || '<div class="value">No artifacts yet</div>'}
    </div>
    <div class="actions">${actions}</div>
    <div style="margin-top:12px;display:flex;flex-direction:column;gap:6px;">
      <textarea id="commentInput" placeholder="Add a comment... (Ctrl+Enter)" style="padding:8px 10px;border:1px solid var(--border);border-radius:4px;background:var(--bg);color:var(--text);font-size:11px;min-height:70px;resize:vertical;font-family:inherit;"></textarea>
      <button onclick="addComment('${t.id}')" style="align-self:flex-end;padding:5px 14px;border:1px solid var(--border);border-radius:4px;background:var(--card);color:var(--text);cursor:pointer;font-size:11px;">Comment</button>
    </div>
  `;
  document.getElementById('modalOverlay').classList.add('open');
}

function closeModal() {
  document.getElementById('modalOverlay').classList.remove('open');
}

async function addComment(taskId) {
  const input = document.getElementById('commentInput');
  const msg = input.value.trim();
  if (!msg) return;
  await fetch('/api/tasks/' + taskId + '/comments', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({agent:'user', message: msg})
  });
  input.value = '';
  showTask(taskId);
}

async function processTaskAgent(taskId, agentId) {
  showToast('Agent working...');
  try {
    const resp = await fetch('/api/tasks/' + taskId + '/process/' + agentId, {method:'POST'});
    const result = await resp.json();
    if (resp.ok) {
      showToast('Agent completed work!');
      refresh();
      showTask(taskId);
    } else {
      showToast(result.error || 'Agent failed', true);
    }
  } catch(e) {
    showToast('Error: ' + e.message, true);
  }
}

async function moveTask(taskId, newStatus) {
  const resp = await fetch('/api/tasks/' + taskId + '/move', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({status: newStatus})
  });
  if (resp.ok) {
    showToast('Moved to ' + newStatus);
    refresh();
    const t = await resp.json();
    if (document.getElementById('modalOverlay').classList.contains('open')) showTask(t.id);
  } else showToast('Failed', true);
}

async function createTask() {
  const fields = config?.task_fields || [];
  const body = {};
  fields.forEach(f => {
    const el = document.getElementById('field_' + f.key);
    if (el) body[f.key] = el.value;
  });
  if (!body.title) { showToast('Title is required', true); return; }
  const resp = await fetch('/api/tasks', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify(body)
  });
  if (resp.ok) {
    showToast('Created!');
    fields.forEach(f => { const el = document.getElementById('field_'+f.key); if(el) el.value = ''; });
    refresh();
  }
}

function toggleConfig() {
  document.getElementById('configPanel').classList.toggle('open');
}

function showToast(msg, isError) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.className = 'toast' + (isError ? ' error' : '');
  t.style.display = 'block';
  setTimeout(() => t.style.display = 'none', 2500);
}

function esc(s) { if (!s && s!==0) return ''; const d=document.createElement('div'); d.textContent=String(s); return d.innerHTML; }

loadConfig();
refresh();
setInterval(refresh, 10000);
setInterval(loadActivity, 5000);
loadActivity();

async function loadActivity() {
  try {
    const resp = await fetch('/api/activity');
    const data = await resp.json();
    const entries = data.activity || [];
    const now = new Date();
    
    document.getElementById('liveEntries').innerHTML = entries.slice(0, 20).map(e => {
      const ts = new Date(e.timestamp);
      const age = Math.round((now - ts) / 1000);
      const ageStr = age < 60 ? age + 's ago' : age < 3600 ? Math.round(age/60) + 'm ago' : Math.round(age/3600) + 'h ago';
      
      let statusCls = 'done';
      if (e.action === 'error') statusCls = 'error';
      else if (e.action === 'questions') statusCls = 'questions';
      else if (e.action === 'started') statusCls = 'running';
      
      const icon = {started:'▶', completed:'✓', questions:'💬', error:'✗', moved:'→', created:'+', commented:'💬'}[e.action] || '·';
      
      return `<div class="live-entry">
        <div class="status-dot ${statusCls}"></div>
        <div class="info">
          <span class="agent">${esc(e.agent)}</span>
          <span class="task">on ${esc(e.task_id)}</span>
          <div class="msg">${esc(e.message)}</div>
        </div>
        <div class="time">${ageStr}</div>
      </div>`;
    }).join('') || '<div style="color:var(--muted);font-size:11px;">No recent activity</div>';
  } catch(e) {}
}
</script>
</body>
</html>
"""

app = FastAPI(title="Agile Team Dashboard")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return DASHBOARD_HTML


@app.get("/api/config")
async def get_config():
    return config.model_dump()


@app.post("/api/sprints/{sprint_id}/toggle")
async def toggle_sprint(sprint_id: str):
    sprints = await _load_sprints()
    sprint = next((s for s in sprints if s.id == sprint_id), None)
    if sprint is None:
        return JSONResponse({"error": "not found"}, 404)
    sprint.is_closed = not sprint.is_closed
    if sprint.is_closed:
        sprint.completed_at = datetime.now(timezone.utc)
    else:
        sprint.completed_at = None
    await _save_sprint(sprint)
    return sprint.model_dump()


@app.get("/api/board")
async def get_board():
    summary = await board_service.get_board_summary()
    # Filter done tasks from closed sprints
    try:
        sprints = await _load_sprints()
        closed_ids = set()
        for sp in sprints:
            if sp.is_closed:
                for tid in sp.task_ids:
                    closed_ids.add(tid)
        if closed_ids and "done" in summary["columns"]:
            summary["columns"]["done"] = [
                t for t in summary["columns"]["done"]
                if t["id"] not in closed_ids
            ]
    except Exception:
        pass
    return summary


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    task = await board_service.get_task(task_id)
    if task is None:
        return JSONResponse({"error": "not found"}, 404)
    return task.model_dump()


@app.post("/api/tasks")
async def create_task(request: Request):
    data = await request.json()
    title = (data.get("title") or "").strip()
    if not title:
        return JSONResponse({"error": "title is required"}, 400)
    description = data.get("description", "") or ""
    try:
        priority = int(data.get("priority") or 0)
    except (ValueError, TypeError):
        priority = 0
    task = await board_service.create_task(title, description, priority)
    return task.model_dump()


@app.post("/api/tasks/{task_id}/move")
async def move_task(task_id: str, request: Request):
    data = await request.json()
    task = await board_service.move_task(task_id, data.get("status", ""))
    if task is None:
        return JSONResponse({"error": "not found or invalid status"}, 400)
    return task.model_dump()


@app.post("/api/tasks/{task_id}/comments")
async def add_comment(task_id: str, request: Request):
    data = await request.json()
    task = await board_service.add_comment(
        task_id,
        agent=data.get("agent", "user"),
        message=data.get("message", ""),
        action=data.get("action", "commented"),
    )
    if task is None:
        return JSONResponse({"error": "task not found"}, 404)
    return task.model_dump()


@app.post("/api/tasks/{task_id}/split")
async def split_task(task_id: str, request: Request):
    data = await request.json()
    subtasks_data = data.get("subtasks", [])
    if not subtasks_data:
        return JSONResponse({"error": "subtasks list required"}, 400)

    parent = await board_service.get_task(task_id)
    if parent is None:
        return JSONResponse({"error": "parent task not found"}, 404)

    created = []
    for st in subtasks_data:
        child = await board_service.create_task(
            title=st.get("title", "Subtask"),
            description=st.get("description", ""),
            priority=st.get("priority", parent.priority),
        )
        child.parent_id = task_id
        await board_service.storage.save_task(child)
        await board_service.add_comment(
            child.id, "system",
            f"Split from {task_id}: {parent.title}",
            action="created"
        )
        created.append(child.model_dump())

    await board_service.add_comment(
        task_id, "system",
        f"Split into {len(created)} subtasks",
        action="commented"
    )
    return {"parent": task_id, "subtasks": created, "count": len(created)}


@app.get("/api/tasks/{task_id}/children")
async def get_children(task_id: str):
    board = await board_service.get_board()
    children = [t.model_dump() for t in board.tasks if t.parent_id == task_id]
    return {"parent_id": task_id, "children": children, "count": len(children)}


@app.post("/api/tasks/{task_id}/process/{agent_id}")
async def process_task(task_id: str, agent_id: str):
    from agile_team.agents.runner import run_agent_on_task

    agent_def = config.get_agent(agent_id)
    if agent_def is None or not agent_def.enabled:
        return JSONResponse({"error": f"Agent '{agent_id}' not found or disabled"}, 404)

    task = await board_service.get_task(task_id)
    if task is None:
        return JSONResponse({"error": "task not found"}, 404)

    if task.status.value != agent_def.input_stage:
        return JSONResponse({
            "error": f"Task is in '{task.status.value}' but agent expects '{agent_def.input_stage}'"
        }, 409)

    try:
        import time
        start_time = time.time()

        await board_service.add_comment(
            task_id, agent_def.name,
            f"Started working. Analyzing task...",
            action="started"
        )

        artifact = await run_agent_on_task(task, agent_def, config)

        elapsed = time.time() - start_time
        duration_str = f"{elapsed:.1f}s" if elapsed < 60 else f"{elapsed/60:.1f}m"

        output = artifact.content.strip()

        is_split = output.startswith("SPLIT:") or "SPLIT:" in output[:500] or "**SPLIT:**" in output[:500]
        is_questions = output.startswith("QUESTIONS:") or "QUESTIONS:" in output[:200]

        if is_split or is_questions:
            if is_split:
                import re
                lines = output.split("\n")
                subtask_titles = []
                for line in lines:
                    line = line.strip()
                    match = re.match(r'^[\*\-\d]+[\.\*\)\s]+(.+)', line)
                    if match:
                        title = match.group(1).strip().rstrip('*').strip()
                        clean = re.sub(r'\*\*', '', title).strip()
                        if len(clean) > 10 and len(clean) < 200:
                            skip_words = ['split', 'output_stage', 'questions', 'specification']
                            if not any(clean.lower().startswith(w) for w in skip_words):
                                subtask_titles.append(clean)
                subtask_titles = subtask_titles[:10]
                if subtask_titles:
                    await board_service.add_comment(
                        task_id, agent_def.name,
                        f"Suggested splitting into {len(subtask_titles)} subtasks. Creating them now...",
                        action="commented"
                    )
                    for title in subtask_titles:
                        child = await board_service.create_task(title=title, priority=task.priority)
                        child.parent_id = task_id
                        await board_service.storage.save_task(child)
                        board = await board_service.get_board()
                        if child not in board.tasks:
                            board.tasks.append(child)
                        await board_service.storage.save_board(board)
                    await board_service.add_comment(
                        task_id, "system",
                        f"Created {len(subtask_titles)} subtasks from {agent_def.name}'s suggestion",
                        action="commented"
                    )
                    await board_service.add_artifact(task_id, artifact)
                    task = await board_service.get_task(task_id)
                    return task.model_dump() if task else JSONResponse({"error": "failed"}, 500)

            if "QUESTIONS:" in output[:200]:
                await board_service.add_artifact(task_id, artifact)
                await board_service.add_comment(
                    task_id, agent_def.name,
                    f"Asking clarifying questions ({duration_str}). Please respond via comments before re-processing.",
                    action="questions"
                )
                task = await board_service.get_task(task_id)
                return task.model_dump() if task else JSONResponse({"error": "failed"}, 500)

        output_stages = agent_def.get_output_stages()
        target_stage = output_stages[0] if output_stages else agent_def.output_stage

        import re
        route_match = re.search(r'OUTPUT_STAGE:\s*(\S+)', output)
        if route_match and route_match.group(1) in output_stages:
            target_stage = route_match.group(1)

        await board_service.add_artifact(task_id, artifact)
        task = await board_service.move_task(task_id, target_stage)
        if task is None:
            return JSONResponse({"error": "failed to advance task"}, 500)

        await board_service.add_comment(
            task_id, agent_def.name,
            f"Completed {agent_def.artifact_type} ({duration_str}). Advanced to {target_stage}.",
            action="completed"
        )

        return task.model_dump()
    except Exception as e:
        await board_service.add_comment(
            task_id, agent_def.name,
            f"Error: {str(e)[:200]}",
            action="error"
        )
        return JSONResponse({"error": str(e)[:500]}, 500)


@app.get("/tasks/{task_id}", response_class=HTMLResponse)
async def task_detail_page(task_id: str):
    task = await board_service.get_task(task_id)
    if task is None:
        return HTMLResponse("<h1 style='color:#f85149;font-family:sans-serif;padding:40px'>Task not found</h1>", 404)

    pipeline = config.pipeline
    stage_labels = {s.id: s.label for s in pipeline}
    colors = {s.id: s.color for s in pipeline}

    artifacts_html = ""
    for a in task.artifacts:
        ts = a.created_at.strftime("%Y-%m-%d %H:%M:%S") if a.created_at else ""
        artifacts_html += f"""<div class="artifact">
            <div class="type">{a.artifact_type.value} <span class="by">by {a.created_by}</span> <span class="ts">{ts}</span></div>
            <div class="content">{a.content.replace(chr(10), '<br>')}</div>
        </div>"""

    activity_html = ""
    last_action = None
    for e in reversed(task.activity_log):
        icon = {"created":"+","started":"▶","completed":"✓","questions":"💬","error":"✗","moved":"→","commented":"💬"}.get(e.action, "·")
        ts = e.timestamp.strftime("%Y-%m-%d %H:%M:%S") if e.timestamp else ""
        activity_html += f"""<div class="entry">
            <span class="icon">{icon}</span>
            <span class="agent">{e.agent}</span>
            <span class="ts">{ts}</span>
            <span class="msg">{e.message}</span>
        </div>"""
        if not last_action and e.action in ("questions", "completed", "started", "commented"):
            last_action = e

    readiness = "neutral"
    reasons = []
    
    if task.status.value == "blocked":
        readiness = "red"
        reasons.append("Task is blocked")

    last_log = task.activity_log[-1] if task.activity_log else None
    if last_log and last_log.action == "error":
        readiness = "red"
        reasons.append("Last agent run failed with error")

    has_open_questions = False
    last_question_time = None
    for a in task.artifacts:
        if "QUESTIONS:" in (a.content or "")[:200]:
            has_open_questions = True
            if a.created_at:
                last_question_time = a.created_at

    if has_open_questions and last_question_time:
        has_response = any(
            e.action == "commented" and e.agent == "user" and e.timestamp and e.timestamp > last_question_time
            for e in task.activity_log
        )
        if has_response:
            reasons.append("Questions answered")
        else:
            reasons.append("Open questions unanswered")
            if readiness == "neutral":
                readiness = "yellow"

    if task.feedback_notes and any("REJECTED" in f for f in task.feedback_notes):
        reasons.append("Has pending feedback from previous agent")
        if readiness == "neutral":
            readiness = "yellow"

    if task.activity_log:
        last_ts = task.activity_log[-1].timestamp
        if last_ts:
            hours_stale = (datetime.now(timezone.utc) - last_ts).total_seconds() / 3600
            if hours_stale > 24:
                reasons.append(f"Stale: no activity for {hours_stale:.0f}h")
                if readiness == "neutral":
                    readiness = "yellow"

    for a in task.artifacts:
        if a.content and len(a.content) < 100 and "QUESTIONS:" not in a.content[:100]:
            reasons.append(f"Short {a.artifact_type.value}: may be incomplete")
            if readiness == "neutral":
                readiness = "yellow"

    if readiness == "neutral" and task.artifacts and task.status.value != "backlog":
        readiness = "green"
    if not reasons:
        reasons.append("No issues detected")

    readiness_emoji = {"green": "🟢", "yellow": "🟡", "red": "🔴", "neutral": "⚪"}
    readiness_label = {"green": "Ready", "yellow": "Needs attention", "red": "Blocked", "neutral": "Pending"}

    status_color = colors.get(task.status.value, "#8b949e")

    children = [t for t in (await board_service.get_board()).tasks if t.parent_id == task.id]
    children_html = ""
    if children:
        done_count = sum(1 for c in children if c.status.value == "done")
        children_html = f"""<div class="section">
          <h2>Subtasks ({len(children)}) — {done_count}/{len(children)} done</h2>
          {"".join(f'<div class="entry"><span class="icon">{'🟢' if c.status.value == "done" else '🟡' if c.status.value == "blocked" else '⚪'}</span><span class="agent"><a href="/tasks/{c.id}">{c.id}</a></span><span class="msg">{c.title}</span><span style="color:var(--muted);font-size:10px;margin-left:auto;">{stage_labels.get(c.status.value, c.status.value)}</span></div>' for c in children)}
        </div>"""

    is_epic = any(t.parent_id == task.id for t in (await board_service.get_board()).tasks)
    parent_info = ""
    if task.parent_id:
        parent_task = await board_service.get_task(task.parent_id)
        if parent_task:
            parent_info = f'<div style="font-size:11px;color:var(--muted);margin-bottom:8px;">📎 Part of <a href="/tasks/{task.parent_id}">{task.parent_id}: {parent_task.title}</a></div>'

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{task.id}: {task.title}</title>
<style>
  :root {{ --bg: #0d1117; --card: #161b22; --border: #30363d; --text: #c9d1d9; --muted: #8b949e;
         --green: #3fb950; --blue: #58a6ff; --yellow: #d29922; --red: #f85149; --purple: #bc8cff; }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); padding: 24px; max-width: 960px; margin: 0 auto; }}
  a {{ color: var(--blue); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .back {{ font-size: 12px; margin-bottom: 16px; display: inline-block; }}
  h1 {{ font-size: 22px; margin-bottom: 4px; }}
  .id {{ color: var(--muted); font-size: 12px; }}
  .meta {{ display: flex; gap: 16px; margin: 12px 0; font-size: 13px; flex-wrap: wrap; }}
  .meta .badge {{ padding: 3px 10px; border-radius: 4px; font-weight: 500; }}
  .section {{ margin: 24px 0; }}
  .section h2 {{ font-size: 14px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; padding-bottom: 6px; border-bottom: 1px solid var(--border); }}
  .artifact {{ background: var(--card); border: 1px solid var(--border); border-radius: 6px; padding: 14px; margin-bottom: 10px; }}
  .artifact .type {{ font-size: 12px; font-weight: 600; color: var(--blue); margin-bottom: 6px; }}
  .artifact .by {{ color: var(--green); }}
  .artifact .ts {{ color: var(--muted); font-size: 10px; margin-left: 8px; }}
  .artifact .content {{ font-size: 12px; line-height: 1.6; white-space: pre-wrap; max-height: 600px; overflow-y: auto; }}
  .entry {{ display: flex; gap: 10px; align-items: baseline; padding: 6px 0; border-bottom: 1px solid #1a1a3e; font-size: 12px; }}
  .entry .icon {{ font-size: 14px; width: 20px; text-align: center; }}
  .entry .agent {{ color: var(--green); font-weight: 500; min-width: 100px; }}
  .entry .ts {{ color: var(--muted); font-size: 10px; min-width: 130px; }}
  .entry .msg {{ color: var(--text); }}
  .comment-box {{ display: flex; flex-direction: column; gap: 8px; margin-top: 12px; }}
  .comment-box textarea {{ padding: 10px 12px; border: 1px solid var(--border); border-radius: 6px; background: var(--card); color: var(--text); font-size: 12px; min-height: 100px; resize: vertical; font-family: inherit; }}
  .comment-box textarea:focus {{ border-color: var(--blue); outline: none; }}
  .comment-box button {{ align-self: flex-end; padding: 8px 20px; border: 1px solid var(--green); border-radius: 6px; background: var(--green); color: #fff; cursor: pointer; font-size: 12px; }}
  .desc {{ color: var(--muted); font-size: 13px; line-height: 1.5; }}
</style>
</head>
<body>
<a href="/" class="back">← Back to Board</a>
<h1>{task.title}</h1>
<div class="id">{task.id}{' (Epic)' if is_epic else ''}</div>
{parent_info}
<div class="meta">
  <span class="badge" style="background:{status_color}">{stage_labels.get(task.status.value, task.status.value)}</span>
  <span style="color:var(--muted)">{readiness_emoji[readiness]} {readiness_label[readiness]}</span>
  <span style="color:var(--muted)">Priority: <strong>P{task.priority}</strong></span>
  <span style="color:var(--muted)">Artifacts: <strong>{len(task.artifacts)}</strong></span>
  <span style="color:var(--muted)">Activity: <strong>{len(task.activity_log)} entries</strong></span>
</div>
<div style="font-size:11px;color:var(--muted);margin-bottom:12px;">
  {''.join(f'<span style="margin-right:12px;">• {r}</span>' for r in reasons)}
</div>
<div class="desc">{task.description or '(no description)'}</div>
{children_html}
<div class="section">
  <h2>Artifacts ({len(task.artifacts)})</h2>
  {artifacts_html or '<div style="color:var(--muted);font-size:12px;">No artifacts yet</div>'}
</div>
<div class="section">
  <h2>Activity Timeline ({len(task.activity_log)})</h2>
  {activity_html or '<div style="color:var(--muted);font-size:12px;">No activity yet</div>'}
</div>
<div class="section">
  <h2>Add Comment</h2>
  <div class="comment-box">
    <textarea id="commentInput" placeholder="Write a comment... (Ctrl+Enter to submit)" onkeydown="if(event.key==='Enter'&&event.ctrlKey)addComment()"></textarea>
    <button onclick="addComment()">Comment</button>
  </div>
</div>
<script>
async function addComment() {{
  const input = document.getElementById('commentInput');
  const msg = input.value.trim();
  if (!msg) return;
  await fetch('/api/tasks/{task.id}/comments', {{
    method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{agent:'user', message: msg}})
  }});
  input.value = '';
  location.reload();
}}
</script>
</body>
</html>""")
async def board_text():
    return await board_service.get_board_view()


@app.get("/api/activity")
async def get_activity():
    board = await board_service.get_board()
    entries = []
    for task in board.tasks:
        for entry in task.activity_log:
            entries.append({
                "task_id": task.id,
                "task_title": task.title,
                "agent": entry.agent,
                "action": entry.action,
                "message": entry.message,
                "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
            })
    entries.sort(key=lambda e: e["timestamp"] or "", reverse=True)
    return {"activity": entries[:50]}


@app.get("/sprints", response_class=HTMLResponse)
async def sprints_page():
    sprints = await _load_sprints()
    sprints.sort(key=lambda s: s.created_at, reverse=True)

    rows = ""
    for sp in sprints:
        tasks = []
        board = await board_service.get_board()
        for tid in sp.task_ids:
            for t in board.tasks:
                if t.id == tid:
                    tasks.append(t)
                    break
        done = sum(1 for t in tasks if t.status.value == "done")
        rows += f"""<tr>
            <td><a href="/sprints/{sp.id}">{sp.name}</a></td>
            <td>{sp.goal[:80]}</td>
            <td>{len(sp.task_ids)} tasks ({done} done)</td>
            <td><span style="color:{'var(--green)' if not sp.is_closed else 'var(--red)'}">{'Open' if not sp.is_closed else 'Closed'}</span></td>
            <td>{sp.created_at.strftime('%Y-%m-%d')}</td>
            <td><button onclick="toggleSprint('{sp.id}')" style="background:transparent;border:1px solid var(--border);color:var(--text);border-radius:3px;cursor:pointer;font-size:10px;padding:2px 8px;">{'Close' if not sp.is_closed else 'Reopen'}</button></td>
        </tr>`"""

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><title>Sprints - Agile Team</title>
<style>
  :root {{ --bg: #0d1117; --card: #161b22; --border: #30363d; --text: #c9d1d9; --muted: #8b949e; --green: #3fb950; --blue: #58a6ff; }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family: -apple-system, sans-serif; background: var(--bg); color: var(--text); padding: 24px; max-width: 900px; margin: 0 auto; }}
  a {{ color: var(--blue); text-decoration: none; }}
  h1 {{ font-size: 20px; margin-bottom: 16px; }}
  .actions {{ margin-bottom: 16px; display: flex; gap: 8px; }}
  .actions input, .actions button {{ padding: 8px 14px; border: 1px solid var(--border); border-radius: 6px; background: var(--card); color: var(--text); font-size: 12px; }}
  .actions button {{ background: var(--green); border-color: var(--green); color: #fff; cursor: pointer; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ text-align: left; padding: 8px; border-bottom: 1px solid var(--border); color: var(--muted); text-transform: uppercase; font-size: 10px; }}
  td {{ padding: 10px 8px; border-bottom: 1px solid var(--border); }}
  .back {{ font-size: 12px; margin-bottom: 16px; display: inline-block; }}
</style>
</head>
<body>
<a href="/" class="back">← Back to Board</a>
<h1>Sprints</h1>
<div class="actions">
  <input id="sprintName" placeholder="Sprint name (e.g. Sprint 1)">
  <input id="sprintGoal" placeholder="Sprint goal">
  <button onclick="createSprint()">+ Create Sprint</button>
  <button onclick="archiveDone()" style="background:var(--blue);border-color:var(--blue);">📦 Archive All Done</button>
</div>
<table>
  <tr><th>Name</th><th>Goal</th><th>Tasks</th><th>Status</th><th>Created</th><th></th></tr>
  {rows or '<tr><td colspan="6" style="color:var(--muted)">No sprints yet. Create one or archive done tasks.</td></tr>'}
</table>
<script>
async function createSprint() {{
  const name = document.getElementById('sprintName').value.trim();
  const goal = document.getElementById('sprintGoal').value.trim();
  if (!name) return;
  await fetch('/api/sprints', {{ method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{name, goal}}) }});
  location.reload();
}}
async function archiveDone() {{
  await fetch('/api/sprints/archive-done', {{ method:'POST' }});
  location.reload();
}}
async function toggleSprint(id) {{
  await fetch('/api/sprints/' + id + '/toggle', {{ method:'POST' }});
  location.reload();
}}
</script>
</body>
</html>""")


@app.post("/api/sprints")
async def create_sprint(request: Request):
    from agile_team.shared.models import Sprint
    data = await request.json()
    sprint = Sprint(name=data.get("name", "Sprint"), goal=data.get("goal", ""))
    await _save_sprint(sprint)
    return sprint.model_dump()


@app.post("/api/sprints/archive-done")
async def archive_done():
    from agile_team.shared.models import Sprint
    board = await board_service.get_board()
    done_tasks = [t for t in board.tasks if t.status.value == "done"]
    if not done_tasks:
        return JSONResponse({"error": "no done tasks"}, 400)

    sprint = Sprint(
        name=f"Sprint {len(await _load_sprints()) + 1}",
        goal=f"Archived {len(done_tasks)} completed tasks",
        task_ids=[t.id for t in done_tasks],
    )
    await _save_sprint(sprint)
    return sprint.model_dump()


@app.get("/settings", response_class=HTMLResponse)
async def settings_page():
    fields = config.task_fields
    priority_field = next((f for f in fields if f.key == "priority"), None)
    type_field = next((f for f in fields if f.key == "type"), None)
    assignee_field = next((f for f in fields if f.key == "assignee"), None)

    priority_options = priority_field.options if priority_field else ["P1","P2","P3","P4","P5"]
    type_options = type_field.options if type_field else ["Feature","Bug","Tech Debt","Spike","Docs"]
    assignees = []  # stored in task_fields as assignee options if configured

    priorities_html = "".join(
        f'<div class="row"><span>{p}</span><button onclick="removeOption(\'priority\',\'{p}\')">✕</button></div>'
        for p in priority_options
    )
    types_html = "".join(
        f'<div class="row"><span>{t}</span><button onclick="removeOption(\'type\',\'{t}\')">✕</button></div>'
        for t in type_options
    )

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><title>Settings - Agile Team</title>
<style>
  :root {{ --bg: #0d1117; --card: #161b22; --border: #30363d; --text: #c9d1d9; --muted: #8b949e; --green: #3fb950; --blue: #58a6ff; --red: #f85149; }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family: -apple-system, sans-serif; background: var(--bg); color: var(--text); padding: 24px; max-width: 700px; margin: 0 auto; }}
  a {{ color: var(--blue); text-decoration: none; }}
  h1 {{ font-size: 20px; margin-bottom: 20px; }}
  h2 {{ font-size: 14px; color: var(--muted); margin: 20px 0 10px; text-transform: uppercase; }}
  .section {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; margin-bottom: 16px; }}
  .section h3 {{ font-size: 13px; margin-bottom: 10px; }}
  .row {{ display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid #1a1a3e; font-size: 12px; }}
  .row span {{ flex: 1; }}
  .row button {{ background: transparent; border: 1px solid var(--red); color: var(--red); border-radius: 3px; cursor: pointer; font-size: 10px; padding: 2px 6px; }}
  .row button:hover {{ background: var(--red); color: #fff; }}
  .add-row {{ display: flex; gap: 8px; margin-top: 10px; }}
  .add-row input {{ flex: 1; padding: 6px 10px; border: 1px solid var(--border); border-radius: 4px; background: var(--bg); color: var(--text); font-size: 12px; }}
  .add-row button {{ padding: 6px 14px; border: 1px solid var(--green); border-radius: 4px; background: var(--green); color: #fff; cursor: pointer; font-size: 12px; }}
  .back {{ font-size: 12px; margin-bottom: 16px; display: inline-block; }}
  .toast {{ position: fixed; bottom: 20px; right: 20px; background: var(--green); color: #fff; padding: 10px 18px; border-radius: 8px; font-size: 12px; display: none; }}
</style>
</head>
<body>
<a href="/" class="back">← Back to Board</a>
<h1>Settings</h1>

<div class="section">
  <h3>Priority Levels</h3>
  {priorities_html}
  <div class="add-row">
    <input id="newPriority" placeholder="New priority (e.g. P0 - Critical)">
    <button onclick="addOption('priority')">Add</button>
  </div>
</div>

<div class="section">
  <h3>Task Types</h3>
  {types_html}
  <div class="add-row">
    <input id="newType" placeholder="New type (e.g. Enhancement)">
    <button onclick="addOption('type')">Add</button>
  </div>
</div>

<div class="section">
  <h3>Assignee Catalog</h3>
  <div id="assigneeList">
    <div style="color:var(--muted);font-size:12px;">Assignees are managed per-task. Add names here for the dropdown.</div>
  </div>
  <div class="add-row">
    <input id="newAssignee" placeholder="New assignee name">
    <button onclick="addOption('assignee')">Add</button>
  </div>
</div>

<div class="toast" id="toast"></div>
<script>
const currentPriorities = {priorities_html and str(priority_options) or '[]'};
const currentTypes = {types_html and str(type_options) or '[]'};

async function addOption(field) {{
  const input = document.getElementById(field === 'priority' ? 'newPriority' : field === 'type' ? 'newType' : 'newAssignee');
  const val = input.value.trim();
  if (!val) return;
  await fetch('/api/settings/' + field, {{
    method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{action:'add', value: val}})
  }});
  input.value = '';
  showToast('Added: ' + val);
  setTimeout(() => location.reload(), 500);
}}

async function removeOption(field, value) {{
  await fetch('/api/settings/' + field, {{
    method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{action:'remove', value: value}})
  }});
  showToast('Removed: ' + value);
  setTimeout(() => location.reload(), 500);
}}

function showToast(msg) {{
  const t = document.getElementById('toast');
  t.textContent = msg; t.style.display='block';
  setTimeout(() => t.style.display='none', 2000);
}}
</script>
</body>
</html>""")


@app.post("/api/settings/{field_key}")
async def update_settings_field(field_key: str, request: Request):
    data = await request.json()
    action = data.get("action")
    value = data.get("value", "")

    field = next((f for f in config.task_fields if f.key == field_key), None)
    if field is None:
        return JSONResponse({"error": "field not found"}, 404)

    if action == "add" and value not in field.options:
        field.options.append(value)
    elif action == "remove" and value in field.options:
        field.options.remove(value)

    config.save("agile-team.json")
    return {"field": field_key, "options": field.options, "action": action}


@app.get("/pipeline", response_class=HTMLResponse)
async def pipeline_editor():
    pipeline = config.pipeline
    agents = config.agents

    stages_html = "".join(
        f"""<div class="stage-card" style="border-color:{s.color}">
            <input value="{s.label}" onchange="updateStage('{s.id}','label',this.value)" class="editable">
            <input value="{s.color}" onchange="updateStage('{s.id}','color',this.value)" style="width:80px" class="editable">
            <span>WIP: <input type="number" value="{s.wip_limit}" onchange="updateStage('{s.id}','wip_limit',this.value)" style="width:50px" class="editable"></span>
            <button onclick="deleteStage('{s.id}')" class="del">✕</button>
        </div>"""
        for s in pipeline
    )

    agents_html = ""
    for a in agents:
        outs = a.output_stages if a.output_stages else ([a.output_stage] if a.output_stage else [])
        outs_str = ", ".join(outs)
        agents_html += f"""<div class="agent-card" style="opacity:{1 if a.enabled else 0.4}">
            <div class="header">
                <span class="icon">{a.icon}</span>
                <input value="{a.name}" onchange="updateAgent('{a.id}','name',this.value)" class="editable">
                <span class="badge toggle-badge" style="background:{'var(--green)' if a.enabled else 'var(--red)'};cursor:pointer;" onclick="toggleAgent('{a.id}')">{'ON' if a.enabled else 'OFF'}</span>
            </div>
            <div class="fields">
                <label>Role <input value="{a.role}" onchange="updateAgent('{a.id}','role',this.value)" class="editable"></label>
                <label>Input <select onchange="updateAgent('{a.id}','input_stage',this.value)" class="editable">{''.join(f'<option value="{s.id}" {"selected" if s.id==a.input_stage else ""}>{s.label}</option>' for s in pipeline)}</select></label>
                <label>Output(s) <input value="{outs_str}" onchange="updateAgent('{a.id}','output_stages',this.value)" class="editable" placeholder="stage1, stage2"></label>
                <label>Artifact <input value="{a.artifact_type}" onchange="updateAgent('{a.id}','artifact_type',this.value)" class="editable"></label>
                <label>Replicas <input type="number" value="{a.min_replicas}" onchange="updateAgent('{a.id}','min_replicas',this.value)" style="width:50px" class="editable"> – <input type="number" value="{a.max_replicas}" onchange="updateAgent('{a.id}','max_replicas',this.value)" style="width:50px" class="editable"></label>
                <label>Prompt <textarea onchange="updateAgent('{a.id}','system_prompt',this.value)" class="editable" rows="3">{a.system_prompt}</textarea></label>
            </div>
        </div>"""

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><title>Pipeline Editor - Agile Team</title>
<style>
  :root {{ --bg: #0d1117; --card: #161b22; --border: #30363d; --text: #c9d1d9; --muted: #8b949e; --green: #3fb950; --blue: #58a6ff; --red: #f85149; --yellow: #d29922; }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family: -apple-system, sans-serif; background: var(--bg); color: var(--text); padding: 24px; }}
  a {{ color: var(--blue); text-decoration: none; }}
  h1 {{ font-size: 20px; margin-bottom: 8px; }}
  .layout {{ display: flex; gap: 24px; max-width: 1400px; }}
  .col {{ flex: 1; min-width: 300px; }}
  .col.wide {{ flex: 2; }}
  h2 {{ font-size: 13px; color: var(--muted); text-transform: uppercase; margin: 16px 0 10px; letter-spacing: 0.5px; }}
  .stage-card, .agent-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 12px; margin-bottom: 8px; }}
  .stage-card {{ border-left: 4px solid; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}
  .editable {{ background: var(--bg); border: 1px solid var(--border); border-radius: 3px; color: var(--text); padding: 4px 6px; font-size: 11px; font-family: inherit; }}
  .editable:focus {{ border-color: var(--blue); outline: none; }}
  input.editable {{ height: 24px; }}
  textarea.editable {{ width: 100%; resize: vertical; }}
  select.editable {{ height: 24px; }}
  .del {{ background: transparent; border: 1px solid var(--red); color: var(--red); border-radius: 3px; cursor: pointer; font-size: 10px; padding: 2px 6px; }}
  .agent-card .header {{ display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }}
  .agent-card .icon {{ font-size: 18px; font-weight: bold; }}
  .agent-card .badge {{ font-size: 10px; padding: 2px 8px; border-radius: 4px; color: #fff; }}
  .agent-card .fields {{ display: flex; flex-direction: column; gap: 6px; }}
  .agent-card .fields label {{ font-size: 10px; color: var(--muted); display: flex; flex-direction: column; gap: 2px; }}
  .actions {{ margin: 16px 0; display: flex; gap: 8px; flex-wrap: wrap; }}
  .actions button {{ padding: 8px 16px; border: 1px solid; border-radius: 6px; cursor: pointer; font-size: 12px; }}
  .btn-green {{ background: var(--green); border-color: var(--green); color: #fff; }}
  .btn-blue {{ background: transparent; border-color: var(--blue); color: var(--blue); }}
  .btn-red {{ background: transparent; border-color: var(--red); color: var(--red); }}
  .validation {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 12px; margin-bottom: 16px; }}
  .validation .ok {{ color: var(--green); }}
  .validation .warn {{ color: var(--yellow); }}
  .validation .err {{ color: var(--red); }}
  .back {{ font-size: 12px; margin-bottom: 16px; display: inline-block; }}
  .toast {{ position: fixed; bottom: 20px; right: 20px; background: var(--green); color: #fff; padding: 10px 18px; border-radius: 8px; font-size: 12px; display: none; }}
  .flow {{ display: flex; align-items: center; gap: 0; flex-wrap: wrap; }}
  .pipeline-flow {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }}
  .proposal-card {{ background: var(--bg); border: 1px solid var(--border); border-radius: 6px; padding: 12px; margin-bottom: 10px; }}
  .proposal-card .header {{ display: flex; gap: 8px; align-items: center; margin-bottom: 6px; }}
  .proposal-card .header strong {{ font-size: 12px; }}
  .proposal-card .why {{ font-size: 11px; color: var(--yellow); margin-bottom: 4px; }}
  .proposal-card .details {{ font-size: 10px; color: var(--muted); font-family: monospace; margin-bottom: 8px; }}
  .proposal-card .actions {{ display: flex; gap: 6px; }}
</style>
</head>
<body>
<a href="/" class="back">← Back to Board</a>
<h1>Pipeline Editor</h1>

<div class="validation" id="validation">
  <strong>Pipeline Status:</strong> <span id="valStatus">Checking...</span>
  <div id="valDetails"></div>
</div>

<div class="actions">
  <button class="btn-green" onclick="saveAll()">Save All Changes</button>
  <button class="btn-blue" onclick="addStage()">+ Add Stage</button>
  <button class="btn-blue" onclick="addAgent()">+ Add Agent</button>
  <button class="btn-blue" onclick="aiPropose()" style="background:var(--purple);border-color:var(--purple);color:#fff">🤖 AI Propose Workflow</button>
  <button class="btn-red" onclick="discardChanges()">Refresh Page</button>
  <button class="btn-blue" onclick="showVersions()" style="background:transparent;border-color:var(--yellow);color:var(--yellow)">History</button>
</div>

<div id="versionPanel" style="display:none;background:var(--card);border:1px solid var(--yellow);border-radius:8px;padding:16px;margin-bottom:16px;">
  <h3 style="color:var(--yellow);margin-bottom:10px;">Version History</h3>
  <div id="versionList"></div>
</div>

<div id="aiProposal" style="display:none;background:var(--card);border:1px solid var(--purple);border-radius:8px;padding:16px;margin-bottom:16px;">
  <h3 style="color:var(--purple);margin-bottom:10px;">AI Proposals</h3>
  <div id="aiProposalCards"></div>
</div>

<div class="pipeline-flow" style="margin-bottom:20px;">
  <h2>Pipeline Flow</h2>
  <div id="flowDiagram" class="flow" style="padding:12px 0;min-width:max-content;"></div>
</div>

<div id="liveStatus" style="background:var(--card);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:20px;">
  <h2>Live Pipeline Status</h2>
  <div id="liveStatusContent"><div style="color:var(--muted);font-size:11px;">Loading...</div></div>
</div>

<div class="layout">
  <div class="col">
    <h2>Pipeline Stages ({len(pipeline)})</h2>
    <div id="stages">{stages_html}</div>
  </div>
  <div class="col wide">
    <h2>Agents ({len(agents)})</h2>
    <div id="agents">{agents_html}</div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
let changes = {{}};
let proposalData = null;

async function aiPropose() {{
  showToast('AI analyzing pipeline...');
  const resp = await fetch('/api/pipeline/propose', {{ method:'POST' }});
  const data = await resp.json();
  document.getElementById('aiProposal').style.display = 'block';

  const cards = (data.proposals || []).map(p => `
    <div class="proposal-card" id="${{p.id}}">
      <div class="header">
        <strong>${{escHtml(p.title)}}</strong>
        <span class="badge" style="background:var(--blue);color:#fff;font-size:9px;padding:2px 6px;border-radius:3px;">${{escHtml(p.action)}}</span>
      </div>
      <div class="why">${{escHtml(p.why)}}</div>
      <div class="details">${{escHtml(p.details)}}</div>
      <div class="actions">
        <button class="btn-green" onclick="applyOneProposal('${{p.id}}')">Apply</button>
        <button class="btn-red" onclick="discardProposal('${{p.id}}')">Discard</button>
      </div>
    </div>
  `).join('');

  document.getElementById('aiProposalCards').innerHTML = cards || '<div style="color:var(--muted);">No proposals generated.</div>';
  proposalData = data;
}}

async function applyOneProposal(propId) {{
  const prop = (proposalData?.proposals || []).find(p => p.id === propId);
  if (!prop || !prop.changes) return;
  changes = prop.changes;
  await saveAll();
  document.getElementById(propId).style.opacity = '0.3';
  document.getElementById(propId).querySelector('.actions').innerHTML = '<span style="color:var(--green);font-size:11px;">✓ Applied</span>';
}}

function discardProposal(propId) {{
  document.getElementById(propId).style.display = 'none';
}}

async function toggleAgent(agentId) {{
  if (!changes.agents) changes.agents = {{}};
  if (!changes.agents[agentId]) changes.agents[agentId] = {{}};

  const badge = event.target;
  const isOn = badge.textContent.trim() === 'ON';
  changes.agents[agentId].enabled = !isOn;
  badge.textContent = isOn ? 'OFF' : 'ON';
  badge.style.background = isOn ? 'var(--red)' : 'var(--green)';
  const card = badge.closest('.agent-card');
  card.style.opacity = isOn ? '0.4' : '1';
  await saveAll();
}}

function escHtml(s) {{
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}}

function renderFlow() {{
  const stages = document.querySelectorAll('.stage-card');
  const labels = Array.from(stages).map(s => s.querySelector('input')?.value || '');
  document.getElementById('flowDiagram').innerHTML = labels.map((l,i) =>
    `<span style="padding:4px 10px;border:2px solid var(--border);border-radius:6px;font-size:11px;font-weight:500;">${{l}}</span>` +
    (i < labels.length-1 ? '<span style="color:var(--muted);margin:0 6px;font-size:14px;">→</span>' : '')
  ).join('');
}}
function renderFlow() {{
  const stages = document.querySelectorAll('.stage-card');
  const labels = Array.from(stages).map(s => s.querySelector('input')?.value || '');
  document.getElementById('flowDiagram').innerHTML = labels.map((l,i) =>
    `<span style="padding:4px 10px;border:2px solid var(--border);border-radius:6px;font-size:11px;font-weight:500;">${{l}}</span>` +
    (i < labels.length-1 ? '<span style="color:var(--muted);margin:0 6px;font-size:14px;">→</span>' : '')
  ).join('');
}}

async function showVersions() {{
  const panel = document.getElementById('versionPanel');
  if (panel.style.display === 'block') {{ panel.style.display = 'none'; return; }}
  const resp = await fetch('/api/pipeline/versions');
  const data = await resp.json();
  document.getElementById('versionList').innerHTML = data.versions.map(v =>
    `<div style="display:flex;gap:12px;align-items:center;padding:6px 0;border-bottom:1px solid #1a1a3e;font-size:11px;">
      <span>${{v.id}}</span>
      <span style="color:var(--muted)">${{v.ts}}</span>
      <button onclick="rollback('${{v.id}}')" style="background:transparent;border:1px solid var(--yellow);color:var(--yellow);border-radius:3px;cursor:pointer;font-size:10px;padding:2px 8px;">Rollback</button>
    </div>`
  ).join('') || '<div style="color:var(--muted);font-size:11px;">No versions yet</div>';
  panel.style.display = 'block';
}}

async function rollback(versionId) {{
  if (!confirm('Rollback to version ' + versionId + '?')) return;
  await fetch('/api/pipeline/rollback/' + versionId, {{ method:'POST' }});
  showToast('Rolled back! Reloading...');
  setTimeout(() => location.reload(), 800);
}}

async function discardChanges() {{
  changes = {{}};
  location.reload();
}}
loadLiveStatus();
setInterval(loadLiveStatus, 10000);

async function loadLiveStatus() {{
  try {{
    const resp = await fetch('/api/board');
    const data = await resp.json();
    const cols = data.columns || {{}};
    const agents = data.agents || [];

    let html = '';
    for (const stage of (data.pipeline || [])) {{
      const tasks = cols[stage.id] || [];
      const stageAgents = agents.filter(a => a.enabled && a.input_stage === stage.id);
      if (tasks.length > 0 || stageAgents.length > 0) {{
        html += `<div style="display:flex;gap:12px;align-items:center;padding:6px 0;border-bottom:1px solid #1a1a3e;font-size:11px;">
          <span style="min-width:100px;font-weight:500;color:${{stage.color}}">${{escHtml(stage.label)}}</span>
          <span style="color:var(--muted);">${{tasks.length}} task(s) queued</span>
          <span style="color:var(--blue);">${{stageAgents.map(a => a.icon + ' ' + a.name).join(', ') || 'no agents'}}</span>
          ${{tasks.length > 0 && stageAgents.length > 0 ? '<span style="color:var(--yellow);font-size:10px;">⚠ ready to process</span>' : ''}}
        </div>`;
      }}
    }}
    document.getElementById('liveStatusContent').innerHTML = html || '<div style="color:var(--muted);font-size:11px;">No active work in pipeline</div>';
  }} catch(e) {{}}
}}

function updateStage(id, field, value) {{
  if (!changes.stages) changes.stages = {{}};
  if (!changes.stages[id]) changes.stages[id] = {{}};
  changes.stages[id][field] = value;
}}

function updateAgent(id, field, value) {{
  if (!changes.agents) changes.agents = {{}};
  if (!changes.agents[id]) changes.agents[id] = {{}};
  changes.agents[id][field] = value;
}}

async function saveAll() {{
  if (!changes.stages && !changes.agents) {{ showToast('No changes'); return; }}
  const resp = await fetch('/api/pipeline/save', {{
    method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify(changes)
  }});
  const result = await resp.json();
  if (resp.ok) {{ showToast('Saved!'); changes = {{}}; validatePipeline(); }}
  else showToast(result.error || 'Failed');
}}

function addStage() {{
  const id = 'stage_' + Date.now();
  const label = prompt('Stage label:');
  if (!label) return;
  changes.stages = changes.stages || {{}};
  changes.stages[id] = {{id, label, color: '#8b949e', wip_limit: 0, _action: 'add'}};
  saveAll();
}}

function addAgent() {{
  const id = prompt('Agent ID (e.g. my_agent):');
  if (!id) return;
  const name = prompt('Agent name:') || id;
  changes.agents = changes.agents || {{}};
  changes.agents[id] = {{id, name, icon: name[0].toUpperCase(), _action: 'add', enabled: true}};
  saveAll();
}}

function deleteStage(id) {{
  if (!confirm('Delete stage ' + id + '?')) return;
  changes.stages = changes.stages || {{}};
  changes.stages[id] = {{_action: 'delete'}};
  saveAll();
}}

async function validatePipeline() {{
  try {{
    const resp = await fetch('/api/pipeline/validate');
    const v = await resp.json();
    document.getElementById('valStatus').innerHTML = v.valid
      ? '<span class="ok">✓ Valid</span>'
      : '<span class="warn">⚠ Issues found</span>';
    document.getElementById('valDetails').innerHTML = v.issues.map(i =>
      '<div class="' + (i.severity === 'error' ? 'err' : 'warn') + '">• ' + i.message + '</div>'
    ).join('');
  }} catch(e) {{}}
}}

function showToast(msg) {{
  const t = document.getElementById('toast');
  t.textContent = msg; t.style.display='block';
  setTimeout(() => t.style.display='none', 2000);
}}

validatePipeline();
</script>
</body>
</html>""")


@app.post("/api/pipeline/save")
async def save_pipeline(request: Request):
    from agile_team.shared.config import AgentDefinition, PipelineStage
    data = await request.json()
    stages_changes = data.get("stages", {})
    agents_changes = data.get("agents", {})

    for sid, changes in stages_changes.items():
        if changes.get("_action") == "delete":
            config.pipeline = [s for s in config.pipeline if s.id != sid]
        elif changes.get("_action") == "add":
            config.pipeline.append(PipelineStage(
                id=sid, label=changes.get("label", sid),
                color=changes.get("color", "#8b949e"),
                wip_limit=int(changes.get("wip_limit", 0)),
            ))
        else:
            for s in config.pipeline:
                if s.id == sid:
                    if "label" in changes: s.label = changes["label"]
                    if "color" in changes: s.color = changes["color"]
                    if "wip_limit" in changes: s.wip_limit = int(changes["wip_limit"])
                    break

    for aid, changes in agents_changes.items():
        if changes.get("_action") == "add":
            config.agents.append(AgentDefinition(id=aid, name=changes.get("name", aid), enabled=True))
        else:
            agent = config.get_agent(aid)
            if agent:
                for field in ["name","role","input_stage","artifact_type","system_prompt","team_mode","icon"]:
                    if field in changes:
                        setattr(agent, field, changes[field])
                if "output_stages" in changes:
                    val = changes["output_stages"]
                    agent.output_stages = [s.strip() for s in val.split(",") if s.strip()] if isinstance(val, str) else val
                if "min_replicas" in changes:
                    agent.min_replicas = int(changes["min_replicas"])
                if "max_replicas" in changes:
                    agent.max_replicas = int(changes["max_replicas"])
                if "enabled" in changes:
                    agent.enabled = changes["enabled"] in (True, "true", "True", 1)

    import tempfile, os as _os
    try:
        config.save("agile-team.json")
    except Exception:
        tmp = _os.path.join(tempfile.gettempdir(), "agile-team.json")
        config.save(tmp)
    await _save_config_version()
    return {"status": "saved"}


@app.post("/api/pipeline/propose")
async def ai_propose_pipeline():
    import agile_team.llm.providers.ollama_provider  # noqa
    import agile_team.llm.providers.deepseek_provider  # noqa
    from agile_team.llm.base import LLMFactory

    pipeline_desc = "\n".join(
        f"  Stage: {s.label} (id: {s.id})"
        for s in config.pipeline
    )
    agents_desc = "\n".join(
        f"  Agent: {a.name} (id: {a.id}) | Input: {a.input_stage} | Output: {a.get_output_stages()} | Enabled: {a.enabled}"
        for a in config.agents
    )

    prompt = f"""Analyze this agile pipeline and suggest improvements:

CURRENT PIPELINE:
{pipeline_desc}

CURRENT AGENTS:
{agents_desc}

Suggest 2-4 concrete improvements:
1. Missing agents that would add value
2. Redundant stages that could be merged
3. Better routing/branching options
4. Agent team recommendations

Format each suggestion as:
SUGGESTION: <title>
WHY: <reason>
ACTION: add_agent | add_stage | modify_agent | remove_stage
DETAILS: <json with specific changes>

Be specific with agent names, stage names, and configurations."""

    provider = LLMFactory.create(
        provider=config.llm.provider,
        model=config.llm.model,
        base_url=config.llm.base_url,
        api_key=config.llm.api_key.strip(),
        temperature=0.7,
        max_tokens=2048,
    )

    proposal = await provider.generate(prompt, system_prompt="You are a DevOps architect optimizing agile pipelines.")

    proposals = _parse_proposals(proposal)

    return {"proposal": proposal, "proposals": proposals}


def _parse_proposals(text: str) -> list:
    import re, json as _json
    proposals = []
    suggestions = re.split(r'\*\*SUGGESTION:\*\*|\*\*SUGGESTION:', text)[1:]

    for sug in suggestions:
        lines = sug.strip().split('\n')
        title = lines[0].replace('**', '').replace('*', '').strip() if lines else 'Suggestion'
        action = ""
        why = ""
        details_str = ""

        for line in lines:
            line = line.strip().replace('**', '')
            if line.startswith("WHY:"):
                why = line.replace("WHY:", "").strip()
            if line.startswith("ACTION:"):
                action = line.replace("ACTION:", "").strip()
            if line.startswith("DETAILS:") or line.startswith("```json"):
                details_str = line.replace("DETAILS:", "").replace("```json", "").replace("```", "").strip()

        if not action:
            continue

        details = {}
        try:
            details_str = details_str.replace("'", '"')
            details = _json.loads(details_str) if details_str.startswith("{") else {}
        except Exception:
            pass

        proposals.append({
            "id": f"prop_{len(proposals)}",
            "title": title,
            "why": why,
            "action": action,
            "details": details_str if isinstance(details_str, str) else str(details_str),
            "changes": _proposal_to_changes(action, details),
        })

    return proposals


def _proposal_to_changes(action: str, details: dict) -> dict:
    changes: dict = {"stages": {}, "agents": {}}

    if action == "add_agent":
        agent_id = details.get("agent_name", "new_agent").lower().replace(" ", "_")
        changes["agents"][agent_id] = {
            "_action": "add",
            "name": details.get("agent_name", "New Agent"),
            "input_stage": details.get("input", "backlog"),
            "role": details.get("description", ""),
            "enabled": details.get("enabled", True),
        }
        if "output" in details:
            out = details["output"]
            changes["agents"][agent_id]["output_stages"] = out if isinstance(out, list) else [out]

    elif action == "modify_agent":
        agent_id = details.get("agent_id", "")
        if agent_id:
            changes["agents"][agent_id] = {k: v for k, v in details.items() if k != "agent_id"}

    elif action == "add_stage":
        stage_id = details.get("stage_id", "new_stage").lower().replace(" ", "_")
        changes["stages"][stage_id] = {
            "_action": "add",
            "label": details.get("stage_name", "New Stage"),
            "color": details.get("color", "#8b949e"),
            "wip_limit": details.get("wip_limit", 0),
        }

    elif action == "remove_stage":
        stage_id = details.get("stage_to_remove", "")
        if stage_id:
            changes["stages"][stage_id] = {"_action": "delete"}

    return changes


@app.get("/api/pipeline/validate")
async def validate_pipeline():
    issues = []
    stage_ids = {s.id for s in config.pipeline}

    if not config.pipeline:
        issues.append({"severity": "error", "message": "No pipeline stages defined"})

    for agent in config.enabled_agents:
        if agent.input_stage and agent.input_stage not in stage_ids:
            issues.append({"severity": "error", "message": f"Agent '{agent.name}' input stage '{agent.input_stage}' not found in pipeline"})

        out_stages = agent.get_output_stages()
        for out in out_stages:
            if out not in stage_ids:
                issues.append({"severity": "error", "message": f"Agent '{agent.name}' output stage '{out}' not found in pipeline"})

        if not out_stages:
            issues.append({"severity": "warning", "message": f"Agent '{agent.name}' has no output stage configured"})

    for s in config.pipeline[:-1]:
        has_agent = any(
            a.enabled and a.input_stage == s.id
            for a in config.agents
        )
        if not has_agent and s.id != "done" and s.id != "blocked":
            issues.append({"severity": "warning", "message": f"Stage '{s.label}' has no enabled agents assigned to process it"})

    return {
        "valid": len([i for i in issues if i["severity"] == "error"]) == 0,
        "issues": issues if issues else [{"severity": "ok", "message": "Pipeline is fully connected and valid"}]
    }


@app.get("/api/pipeline/versions")
async def list_versions():
    versions = await _load_config_versions()
    return {"versions": [{"id": v[0], "ts": v[1]} for v in versions]}


@app.post("/api/pipeline/rollback/{version_id}")
async def rollback_pipeline(version_id: str):
    versions = await _load_config_versions()
    target = None
    for v_id, v_ts, v_data in versions:
        if v_id == version_id:
            target = v_data
            break
    if target is None:
        return JSONResponse({"error": "version not found"}, 404)

    global config
    import json as _json
    from agile_team.shared.config import TeamConfig
    config = TeamConfig(**_json.loads(target))
    config.save("agile-team.json")
    await _save_config_version()
    return {"status": "rolled back", "version": version_id}


async def _save_config_version() -> None:
    import time
    pool = board_service.storage
    if hasattr(pool, '_pool'):
        if pool._pool is None:
            await pool._get_pool()
        v_id = str(int(time.time() * 1000))
        async with pool._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS agile_config_versions (
                    version_id TEXT PRIMARY KEY,
                    data JSONB NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await conn.execute(
                "INSERT INTO agile_config_versions (version_id, data) VALUES ($1, $2)",
                v_id, config.model_dump_json(indent=2),
            )


async def _load_config_versions() -> list:
    pool = board_service.storage
    if hasattr(pool, '_pool') and pool._pool:
        async with pool._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS agile_config_versions (
                    version_id TEXT PRIMARY KEY,
                    data JSONB NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            rows = await conn.fetch("SELECT version_id, created_at, data FROM agile_config_versions ORDER BY created_at DESC LIMIT 20")
            return [(r["version_id"], str(r["created_at"]), r["data"]) for r in rows]
    return []
@app.get("/sprints/{sprint_id}", response_class=HTMLResponse)
async def sprint_detail(sprint_id: str):
    sprints = await _load_sprints()
    sprint = next((s for s in sprints if s.id == sprint_id), None)
    if sprint is None:
        return HTMLResponse("<h1>Sprint not found</h1>", 404)

    board = await board_service.get_board()
    task_rows = ""
    for tid in sprint.task_ids:
        task = next((t for t in board.tasks if t.id == tid), None)
        if task:
            task_rows += f'<tr><td><a href="/tasks/{task.id}">{task.id}</a></td><td>{task.title}</td><td>{task.status.value}</td></tr>'

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><title>{sprint.name}</title>
<style>
  :root {{ --bg: #0d1117; --card: #161b22; --border: #30363d; --text: #c9d1d9; --muted: #8b949e; --green: #3fb950; --blue: #58a6ff; }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family: -apple-system, sans-serif; background: var(--bg); color: var(--text); padding: 24px; max-width: 900px; margin: 0 auto; }}
  a {{ color: var(--blue); text-decoration: none; }}
  h1 {{ font-size: 20px; margin-bottom: 4px; }}
  .meta {{ color: var(--muted); font-size: 12px; margin-bottom: 16px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ text-align: left; padding: 8px; border-bottom: 1px solid var(--border); color: var(--muted); font-size: 10px; }}
  td {{ padding: 8px; border-bottom: 1px solid var(--border); }}
  .back {{ font-size: 12px; margin-bottom: 16px; display: inline-block; }}
</style>
</head>
<body>
<a href="/sprints" class="back">← Back to Sprints</a>
<h1>{sprint.name}</h1>
<div class="meta">{sprint.goal} · {len(sprint.task_ids)} tasks · Created {sprint.created_at.strftime('%Y-%m-%d')}</div>
<table>
  <tr><th>Task ID</th><th>Title</th><th>Status</th></tr>
  {task_rows or '<tr><td colspan="3">No tasks</td></tr>'}
</table>
</body>
</html>""")


@app.get("/releases", response_class=HTMLResponse)
async def releases_portal():
    board = await board_service.get_board()
    sprints = await _load_sprints()

    total_tasks = len(board.tasks)
    done_tasks = sum(1 for t in board.tasks if t.status.value == "done")
    all_artifacts = []
    for t in board.tasks:
        for a in t.artifacts:
            all_artifacts.append({"task_id": t.id, "task_title": t.title, **a.model_dump()})

    by_type = {}
    for a in all_artifacts:
        t = a["artifact_type"]
        if t not in by_type:
            by_type[t] = []
        by_type[t].append(a)

    artifact_sections = ""
    for atype, items in sorted(by_type.items()):
        artifact_sections += f'<div class="section"><h2>{atype} ({len(items)})</h2>'
        for a in items[:20]:
            ts = a.get("created_at", "")
            artifact_sections += f'<div class="item"><a href="/tasks/{a["task_id"]}">{a["task_id"]}</a> <span class="by">by {a["created_by"]}</span> <span class="ts">{ts}</span></div>'
        artifact_sections += '</div>'

    sprint_rows = ""
    for sp in sorted(sprints, key=lambda s: s.created_at, reverse=True):
        done_in_sprint = 0
        for tid in sp.task_ids:
            for t in board.tasks:
                if t.id == tid and t.status.value == "done":
                    done_in_sprint += 1
                    break
        sprint_rows += f"""<div class="item">
            <a href="/sprints/{sp.id}"><strong>{sp.name}</strong></a>
            <span class="by">{sp.goal[:80]}</span>
            <span class="ts">{len(sp.task_ids)} tasks · {done_in_sprint} done · {sp.created_at.strftime('%Y-%m-%d')}</span>
        </div>"""

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><title>Releases - Agile Team</title>
<style>
  :root {{ --bg: #0d1117; --card: #161b22; --border: #30363d; --text: #c9d1d9; --muted: #8b949e; --green: #3fb950; --blue: #58a6ff; --yellow: #d29922; --purple: #bc8cff; }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family: -apple-system, sans-serif; background: var(--bg); color: var(--text); padding: 24px; max-width: 1100px; margin: 0 auto; }}
  a {{ color: var(--blue); text-decoration: none; }}
  h1 {{ font-size: 20px; margin-bottom: 4px; }}
  .back {{ font-size: 12px; margin-bottom: 20px; display: inline-block; }}
  .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-bottom: 24px; }}
  .stat {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 14px; text-align: center; }}
  .stat .num {{ font-size: 28px; font-weight: bold; color: var(--green); }}
  .stat .label {{ font-size: 10px; color: var(--muted); text-transform: uppercase; margin-top: 4px; }}
  .section {{ margin-bottom: 24px; }}
  .section h2 {{ font-size: 13px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 10px; padding-bottom: 6px; border-bottom: 1px solid var(--border); }}
  .item {{ display: flex; gap: 12px; align-items: baseline; padding: 6px 0; border-bottom: 1px solid #1a1a3e; font-size: 12px; }}
  .item .by {{ color: var(--green); }}
  .item .ts {{ color: var(--muted); font-size: 10px; margin-left: auto; }}
</style>
</head>
<body>
<a href="/" class="back">← Back to Board</a>
<h1>Release Portal</h1>

<div class="stats">
  <div class="stat"><div class="num">{total_tasks}</div><div class="label">Total Tasks</div></div>
  <div class="stat"><div class="num">{done_tasks}</div><div class="label">Completed</div></div>
  <div class="stat"><div class="num">{len(all_artifacts)}</div><div class="label">Artifacts</div></div>
  <div class="stat"><div class="num">{len(sprints)}</div><div class="label">Sprints</div></div>
  <div class="stat"><div class="num">{len([a for a in config.enabled_agents])}</div><div class="label">Active Agents</div></div>
</div>

<div class="section">
  <h2>Sprints ({len(sprints)})</h2>
  {sprint_rows or '<div class="item" style="color:var(--muted)">No sprints yet. <a href="/sprints">Create one →</a></div>'}
</div>

<div class="section">
  <h2>Artifact Library ({len(all_artifacts)})</h2>
  {artifact_sections or '<div class="item" style="color:var(--muted)">No artifacts produced yet.</div>'}
</div>
</body>
</html>""")


async def _load_sprints() -> list:
    from agile_team.shared.models import Sprint
    import json as _json
    pool = board_service.storage
    if hasattr(pool, '_pool') and pool._pool:
        async with pool._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS agile_sprints (
                    sprint_id TEXT PRIMARY KEY,
                    data JSONB NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            rows = await conn.fetch("SELECT data FROM agile_sprints ORDER BY created_at DESC")
            return [Sprint(**_json.loads(r["data"]) if isinstance(r["data"], str) else r["data"]) for r in rows]
    return []


async def _save_sprint(sprint) -> None:
    pool = board_service.storage
    if hasattr(pool, '_pool') and pool._pool:
        async with pool._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO agile_sprints (sprint_id, data) VALUES ($1, $2) "
                "ON CONFLICT (sprint_id) DO UPDATE SET data = $2",
                sprint.id, sprint.model_dump_json(indent=2),
            )
