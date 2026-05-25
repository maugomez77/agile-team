from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

from agile_team.agents.all import (
    ArchitectAgent,
    CoderAgent,
    DevOpsAgent,
    QAAgent,
    ScrumMasterAgent,
    TechLeadAgent,
)
from agile_team.agents.base import BaseAgent
from agile_team.board.engine import BoardEngine
from agile_team.shared.config import LLMConfig, TeamConfig
from agile_team.shared.models import Artifact, Task, TaskStatus


class AgileOrchestrator:
    """Coordinates all agents and the kanban board."""

    def __init__(self, config: Optional[TeamConfig] = None):
        self.config = config or TeamConfig.default()
        self.workspace = Path(".agile-team")
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.board = BoardEngine(self.workspace)
        self._agents: dict[str, BaseAgent] = {}
        self._init_agents()

    def _init_agents(self) -> None:
        agent_map = {
            "scrum_master": ScrumMasterAgent,
            "tech_lead": TechLeadAgent,
            "architect": ArchitectAgent,
            "coder": CoderAgent,
            "qa": QAAgent,
            "devops": DevOpsAgent,
        }
        for agent_def in self.config.agents:
            agent_name = agent_def.id
            agent_cls = agent_map.get(agent_name)
            if agent_cls and agent_def.enabled:
                llm_cfg = self.config.llm
                self._agents[agent_name] = agent_cls(self.workspace, llm_config=llm_cfg)

    async def run_agent(self, agent_name: str) -> list[tuple[Task, Artifact]]:
        agent = self._agents.get(agent_name)
        if agent is None:
            return []
        return await agent.run_once()

    async def run_pipeline(self, task_id: str | None = None) -> dict:
        """Run the full pipeline on a task or all actionable tasks."""
        results: dict[str, list] = {}

        agent_order = [
            "scrum_master",
            "tech_lead",
            "architect",
            "coder",
            "qa",
            "devops",
        ]

        for name in agent_order:
            agent_results = await self.run_agent(name)
            if agent_results:
                results[name] = agent_results

        return results

    async def start(self, poll_interval: int = 5) -> None:
        """Start all agents in parallel polling loops."""
        tasks = []
        for name, agent in self._agents.items():
            tasks.append(asyncio.create_task(agent.run_loop(poll_interval)))
        await asyncio.gather(*tasks)

    def create_task(self, title: str, description: str = "", priority: int = 0) -> Task:
        return self.board.create_task(title, description, priority)

    def get_status(self) -> dict:
        return {
            "tasks": [t.model_dump() for t in self.board.board.tasks],
            "agents": {
                name: agent._state
                for name, agent in self._agents.items()
            },
        }

    def get_board_view(self) -> str:
        return self.board.get_board_view()
