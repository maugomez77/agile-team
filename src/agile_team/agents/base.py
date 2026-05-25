from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agile_team.llm.base import LLMFactory, LLMProvider
from agile_team.shared.config import LLMConfig
from agile_team.shared.models import (
    AgentRole,
    Artifact,
    ArtifactType,
    Board,
    Task,
    TaskStatus,
)


class BaseAgent(ABC):
    """Base class for all specialized agile team agents."""

    role: AgentRole
    input_status: TaskStatus
    output_status: TaskStatus
    artifact_type: ArtifactType

    def __init__(self, workspace: Path, llm_config: LLMConfig | None = None):
        self.workspace = Path(workspace)
        self.state_path = self.workspace / "agents" / self.role.value / "state.json"
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._llm: Optional[LLMProvider] = None
        self._llm_config = llm_config or LLMConfig()
        self._state = self._load_state()

    def _load_state(self) -> dict:
        if self.state_path.exists():
            return json.loads(self.state_path.read_text())
        return {"last_run": None, "tasks_processed": 0}

    def _save_state(self) -> None:
        self._state["last_run"] = datetime.now(timezone.utc).isoformat()
        self._state["tasks_processed"] = self._state.get("tasks_processed", 0) + 1
        self.state_path.write_text(json.dumps(self._state, indent=2))

    @property
    def llm(self) -> LLMProvider:
        if self._llm is None:
            self._llm = LLMFactory.create(
                provider=self._llm_config.provider,
                model=self._llm_config.model,
                base_url=self._llm_config.base_url,
                api_key=self._llm_config.api_key,
                temperature=self._llm_config.temperature,
                max_tokens=self._llm_config.max_tokens,
            )
        return self._llm

    @property
    def system_prompt(self) -> str:
        return f"You are a {self.role.value}. Complete your assigned task thoroughly and professionally."

    async def generate(self, prompt: str, **kwargs) -> str:
        return await self.llm.generate(prompt, system_prompt=self.system_prompt, **kwargs)

    async def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        return await self.llm.chat(messages, system_prompt=self.system_prompt, **kwargs)

    def _read_artifact(self, task: Task, artifact_type: ArtifactType) -> Optional[str]:
        for a in task.artifacts:
            if a.artifact_type == artifact_type:
                if a.file_path and Path(a.file_path).exists():
                    return Path(a.file_path).read_text()
                return a.content
        return None

    def get_board(self) -> Board:
        board_path = self.workspace / "board.json"
        if board_path.exists():
            return Board(**json.loads(board_path.read_text()))
        return Board()

    @abstractmethod
    async def process(self, task: Task) -> Artifact:
        """Process a task and produce an artifact. Subclasses must implement."""

    async def validate(self, artifact: Artifact) -> bool:
        """Validate own output before passing forward. Override for custom logic."""
        return bool(artifact.content.strip())

    async def run_once(self) -> list[tuple[Task, Artifact]]:
        """Poll for actionable tasks and process them."""
        board = self.get_board()
        results = []

        for task in board.tasks:
            if task.status != self.input_status:
                continue
            if task.assigned_to and task.assigned_to != self.role:
                continue

            try:
                task.status = TaskStatus(f"{self.role.value}_in_progress")
                board_path = self.workspace / "board.json"
                board_path.write_text(board.model_dump_json(indent=2))

                artifact = await self.process(task)

                if await self.validate(artifact):
                    task.artifacts.append(artifact)
                    task.status = self.output_status
                    task.updated_at = datetime.now(timezone.utc)
                    board_path.write_text(board.model_dump_json(indent=2))

                    task_path = Path(task.workspace_path) / task.id / "task.json"
                    if task_path.parent.exists():
                        task_path.write_text(task.model_dump_json(indent=2))
                else:
                    task.status = self.input_status

                self._save_state()
                results.append((task, artifact))
            except Exception as e:
                board = self.get_board()
                for t in board.tasks:
                    if t.id == task.id:
                        t.status = self.input_status
                        t.feedback_notes.append(f"[ERROR] {self.role.value}: {e}")
                        break
                board_path = self.workspace / "board.json"
                board_path.write_text(board.model_dump_json(indent=2))

        return results

    async def run_loop(self, poll_interval: int = 5) -> None:
        """Run continuously, polling for tasks."""
        while True:
            await self.run_once()
            await asyncio.sleep(poll_interval)
