from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agile_team.shared.models import (
    AgentRole,
    Artifact,
    ArtifactType,
    Board,
    PIPELINE_STAGES,
    REJECTION_MAP,
    Task,
    TaskStatus,
)


class BoardEngine:
    """Kanban board with per-task pipelines and feedback loops."""

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace)
        self.board_path = self.workspace / "board.json"
        self.tasks_dir = self.workspace / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.board = self._load_board()

    def _load_board(self) -> Board:
        if self.board_path.exists():
            data = json.loads(self.board_path.read_text())
            return Board(**data)
        return Board()

    def save(self) -> None:
        self.board_path.parent.mkdir(parents=True, exist_ok=True)
        self.board_path.write_text(self.board.model_dump_json(indent=2))

    def create_task(self, title: str, description: str = "", priority: int = 0) -> Task:
        task = Task(
            title=title,
            description=description,
            priority=priority,
            workspace_path=str(self.tasks_dir),
        )
        task.task_dir.mkdir(parents=True, exist_ok=True)
        self._save_task(task)
        self.board.tasks.append(task)
        self.save()
        return task

    def _save_task(self, task: Task) -> None:
        task_path = task.task_dir / "task.json"
        task_path.write_text(task.model_dump_json(indent=2))

    def get_task(self, task_id: str) -> Optional[Task]:
        for t in self.board.tasks:
            if t.id == task_id:
                return t
        return None

    def update_task_status(self, task_id: str, new_status: TaskStatus) -> Optional[Task]:
        task = self.get_task(task_id)
        if task is None:
            return None
        task.status = new_status
        task.updated_at = datetime.now(timezone.utc)
        self._save_task(task)
        self.save()
        return task

    def add_artifact(self, task_id: str, artifact: Artifact) -> Optional[Task]:
        task = self.get_task(task_id)
        if task is None:
            return None
        task.artifacts.append(artifact)
        task.updated_at = datetime.now(timezone.utc)

        artifact_path = task.task_dir / f"{artifact.artifact_type.value}.md"
        if artifact.content and not artifact.file_path:
            artifact.file_path = str(artifact_path)
            artifact_path.write_text(artifact.content)

        self._save_task(task)
        self.save()
        return task

    def add_feedback(self, task_id: str, note: str) -> Optional[Task]:
        task = self.get_task(task_id)
        if task is None:
            return None
        task.feedback_notes.append(note)
        task.updated_at = datetime.now(timezone.utc)
        self._save_task(task)
        self.save()
        return task

    def reject_task(self, task_id: str, reason: str) -> Optional[Task]:
        """Push a task back to the previous stage with feedback."""
        task = self.get_task(task_id)
        if task is None:
            return None

        target_status = REJECTION_MAP.get(task.status)
        if target_status is None:
            return None

        self.add_feedback(task_id, f"[REJECTED] {reason}")

        artifact = Artifact(
            task_id=task_id,
            artifact_type=ArtifactType.FEEDBACK,
            content=reason,
            created_by=AgentRole.SCRUM_MASTER.value,
        )
        task.artifacts.append(artifact)
        task.status = target_status
        task.updated_at = datetime.now(timezone.utc)
        self._save_task(task)
        self.save()
        return task

    def advance_task(self, task_id: str) -> Optional[Task]:
        """Move a task to the next pipeline stage."""
        task = self.get_task(task_id)
        if task is None:
            return None

        status_order = list(TaskStatus)
        current_idx = status_order.index(task.status)
        next_idx = current_idx + 1
        if next_idx >= len(status_order):
            return task

        task.status = status_order[next_idx]
        task.updated_at = datetime.now(timezone.utc)
        self._save_task(task)
        self.save()
        return task

    def get_board_view(self) -> str:
        """Render the kanban board as a formatted string."""
        columns = [
            ("BACKLOG", TaskStatus.BACKLOG),
            ("SPEC", [TaskStatus.SPEC_IN_PROGRESS, TaskStatus.SPEC_READY]),
            ("ARCH", [TaskStatus.ARCH_IN_PROGRESS, TaskStatus.ARCH_READY]),
            ("CODE", [TaskStatus.CODE_IN_PROGRESS, TaskStatus.CODE_READY]),
            ("TEST", [TaskStatus.TEST_IN_PROGRESS, TaskStatus.TEST_READY]),
            ("DEPLOY", [TaskStatus.DEPLOY_IN_PROGRESS, TaskStatus.DEPLOY_READY]),
            ("DONE", TaskStatus.DONE),
        ]

        lines = ["═" * 80, "  KANBAN BOARD", "═" * 80]
        for col_name, statuses in columns:
            if isinstance(statuses, list):
                tasks = [t for t in self.board.tasks if t.status in statuses]
            else:
                tasks = [t for t in self.board.tasks if t.status == statuses]
            lines.append(f"\n  [{col_name}] ({len(tasks)} task(s))")
            lines.append("  " + "─" * 40)
            for t in sorted(tasks, key=lambda x: x.priority, reverse=True):
                icon = "🔴" if t.status == TaskStatus.BLOCKED else "  "
                lines.append(f"  {icon} {t.id} | P{t.priority} | {t.title[:50]}")
                if t.feedback_notes:
                    lines.append(f"       Feedback: {t.feedback_notes[-1][:60]}...")
        return "\n".join(lines)
