# KiwiFlow 🥝

AI-native agile platform — specs, architecture, fullstack code, tests, CI/CD, and auto-deploy.

**Live:** [kiwi-flow.vercel.app](https://kiwi-flow.vercel.app)

## What it does

KiwiFlow is a multi-agent agile development platform. 12 specialized AI agents collaborate to take a feature from idea to deployed application:

```
Backlog → PM → UX Designer → Tech Lead → Architect → Coder → QA → DevOps → Deployed
```

## Architecture

```
kiwi-flow.vercel.app (FastAPI + PostgreSQL on Vercel)
    │
    ├── Dashboard: Kanban board, task management, AI chat
    ├── Agents: DeepSeek-powered (PM, TL, Architect, Coder, QA, DevOps, SRE, etc.)
    ├── Pipeline editor: Visual config with AI workflow proposals
    ├── Sprints: Open/close sprint management with auto-archiving
    └── Releases: Artifact library and release portal
    │
GitHub Actions Worker (free cloud machine)
    ├── Polls kiwi-flow for actionable tasks
    ├── Clones linked repo → npm install → npm test
    ├── Deploys to Vercel
    ├── Runs Playwright E2E tests (API + UI)
    └── Reports results back to kiwi-flow
```

## Agents

| Agent | Role | Stage |
|---|---|---|
| Product Manager | Requirements, business value | backlog → spec_ready |
| UX Designer | Wireframes, interaction design | spec_ready → arch_ready |
| Tech Lead | Technical specifications | spec_ready → arch_ready |
| Architect | System architecture | arch_ready → code_ready |
| Coder | Fullstack implementation | code_ready → test_ready |
| QA | Testing & validation | test_ready → deploy_ready |
| DevOps | CI/CD & deployment | deploy_ready → done |
| Scrum Master | Process facilitation | backlog → spec_ready |
| Security Engineer | Threat modeling | arch_ready → code_ready |
| Performance Engineer | Load testing | test_ready → deploy_ready |
| SRE | Reliability | deploy_ready → done |
| Release Manager | Release coordination | deploy_ready → done |

## Quick Start

```bash
# Install
pip install -e .

# Initialize workspace
agile-team init

# Create a task
agile-team create "Build payment API" -d "Stripe integration" -p 8

# View board
agile-team board

# Start web dashboard
agile-team web

# Extract code from task and push to GitHub
agile-team apply TASK-ID -o ~/dev/project --repo my-project

# Connect to kiwi-flow, pull tasks, test, deploy
agile-team work -o ~/dev/output --test
```

## API Endpoints

```bash
# Get board
curl https://kiwi-flow.vercel.app/api/board

# Get task
curl https://kiwi-flow.vercel.app/api/tasks/TASK-ID

# Run an agent
curl -X POST https://kiwi-flow.vercel.app/api/tasks/TASK-ID/process/coder

# Add comment
curl -X POST https://kiwi-flow.vercel.app/api/tasks/TASK-ID/comments \
  -H 'Content-Type: application/json' -d '{"agent":"user","message":"Looks good"}'

# Publish to GitHub
curl -X POST https://kiwi-flow.vercel.app/api/tasks/TASK-ID/publish \
  -H 'Content-Type: application/json' -d '{"repo":"my-project"}'

# Deploy to Vercel
curl -X POST https://kiwi-flow.vercel.app/api/tasks/TASK-ID/deploy \
  -H 'Content-Type: application/json' -d '{"repo":"my-project"}'

# AI Chat (with web browsing)
curl -X POST https://kiwi-flow.vercel.app/api/tasks/TASK-ID/chat \
  -H 'Content-Type: application/json' -d '{"message":"What is this about?"}'

# Trigger GitHub Actions worker
curl -X POST https://kiwi-flow.vercel.app/api/tasks/TASK-ID/trigger-worker
```

## Configuration

Everything is driven by `agile-team.json`:

- **Pipeline stages**: Add/remove/edit stages with colors and WIP limits
- **Agents**: Enable/disable, change prompts, set replicas (min/max), routing branches
- **Task fields**: Custom dropdowns for priority, type, assignee
- **LLM**: Provider, model, API key (supports Ollama, DeepSeek, OpenAI-compatible)

Edit via the Pipeline page (`/pipeline`) or directly in the JSON file.

## Key Features

- **Agent teams**: Leads with sub-agents, parallel/review modes
- **Branching routes**: Agents can skip stages (e.g., bug fix goes straight to code_ready)
- **Replicas**: Auto-scale agents per workload (min/max)
- **Epics & subtasks**: Parent/child task relationships, auto-splitting large tasks
- **Readiness heuristics**: 🟢🟡🔴 indicators for open questions, errors, staleness
- **AI workflow proposals**: LLM analyzes pipeline and suggests improvements
- **Versioning & rollback**: Every config change saved, rollback to any version
- **E2E testing**: Playwright tests validate API + UI automatically in CI
- **Self-healing**: Worker reports failures back to dashboard, agents fix and retry
- **Web browsing AI chat**: Chat fetches URLs mentioned by user for real-time data

## Tech Stack

- **Backend**: FastAPI, PostgreSQL (Neon), asyncpg
- **Frontend**: Vanilla HTML/CSS/JS, Server-Sent Events
- **AI**: DeepSeek (chat + reasoner), Ollama (local), provider-agnostic LLM layer
- **CI/CD**: GitHub Actions, Vercel
- **Testing**: pytest (backend), Playwright (E2E), Jest (generated apps)
- **CLI**: Typer, Rich

## Deployments

| App | URL |
|---|---|
| KiwiFlow Dashboard | [kiwi-flow.vercel.app](https://kiwi-flow.vercel.app) |
| Sports API | [sports-6viiq1lfd-mauriciogomez77-8197s-projects.vercel.app/v1/sports](https://sports-6viiq1lfd-mauriciogomez77-8197s-projects.vercel.app/v1/sports) |
| Sports Dashboard | [sports-dashboard-osbt3j1t4-mauriciogomez77-8197s-projects.vercel.app](https://sports-dashboard-osbt3j1t4-mauriciogomez77-8197s-projects.vercel.app) |

## Generated Projects

| Project | Repo |
|---|---|
| Sports API | [github.com/maugomez77/sports-api](https://github.com/maugomez77/sports-api) |
| Sports Dashboard | [github.com/maugomez77/sports-dashboard](https://github.com/maugomez77/sports-dashboard) |
