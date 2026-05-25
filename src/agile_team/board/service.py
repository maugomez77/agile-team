from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agile_team.shared.config import TeamConfig
from agile_team.shared.models import ActivityEntry, Artifact, ArtifactType, Board, Task, TaskStatus
from agile_team.shared.storage import StorageBackend, get_storage


class BoardService:
    """Stateless board operations backed by a StorageBackend and TeamConfig."""

    def __init__(self, storage: Optional[StorageBackend] = None, config: Optional[TeamConfig] = None):
        self.storage = storage or get_storage()
        self.config = config or TeamConfig.load()

    async def get_board(self) -> Board:
        return await self.storage.load_board()

    async def get_config(self) -> TeamConfig:
        return self.config

    async def create_task(
        self, title: str, description: str = "", priority: int = 0, parent_id: str = "", **extra_fields
    ) -> Task:
        board = await self.storage.load_board()
        task = Task(
            title=title,
            description=description,
            priority=priority,
        )
        if parent_id:
            task.parent_id = parent_id
        task.activity_log.append(ActivityEntry(
            agent="user",
            action="created",
            message=f"Task created: {title}",
        ))
        board.tasks.append(task)
        await self.storage.save_task(task)
        await self.storage.save_board(board)
        return task

    async def _sync_board_task(self, task: Task) -> None:
        board = await self.storage.load_board()
        found = False
        for i, t in enumerate(board.tasks):
            if t.id == task.id:
                board.tasks[i] = task
                found = True
        if not found:
            board.tasks.append(task)
        await self.storage.save_board(board)

    async def get_task(self, task_id: str) -> Optional[Task]:
        return await self.storage.load_task(task_id)

    async def update_task_status(self, task_id: str, status: str) -> Optional[Task]:
        task = await self.storage.load_task(task_id)
        if task is None:
            return None

        old_status = task.status.value
        task.status = TaskStatus(status)
        task.updated_at = datetime.now(timezone.utc)
        task.activity_log.append(ActivityEntry(
            agent="system",
            action="moved",
            message=f"Moved from {old_status} → {status}",
        ))
        await self.storage.save_task(task)
        await self._sync_board_task(task)
        return task

    async def move_task(self, task_id: str, new_status: str) -> Optional[Task]:
        return await self.update_task_status(task_id, new_status)

    async def add_artifact(self, task_id: str, artifact: Artifact) -> Optional[Task]:
        task = await self.storage.load_task(task_id)
        if task is None:
            return None
        task.artifacts.append(artifact)
        task.activity_log.append(ActivityEntry(
            agent=str(artifact.created_by),
            action="completed",
            message=f"Produced {artifact.artifact_type.value}: {artifact.content[:100]}..." if len(artifact.content) > 100 else f"Produced {artifact.artifact_type.value}",
            artifact_ref=artifact.id,
        ))
        task.updated_at = datetime.now(timezone.utc)
        await self.storage.save_task(task)
        await self._sync_board_task(task)
        return task

    async def add_comment(self, task_id: str, agent: str, message: str, action: str = "commented") -> Optional[Task]:
        task = await self.storage.load_task(task_id)
        if task is None:
            return None
        task.activity_log.append(ActivityEntry(agent=agent, action=action, message=message))
        task.updated_at = datetime.now(timezone.utc)
        await self.storage.save_task(task)
        await self._sync_board_task(task)
        return task

    async def add_feedback(self, task_id: str, note: str) -> Optional[Task]:
        task = await self.storage.load_task(task_id)
        if task is None:
            return None
        task.feedback_notes.append(note)
        task.updated_at = datetime.now(timezone.utc)
        await self.storage.save_task(task)

        board = await self.storage.load_board()
        for i, t in enumerate(board.tasks):
            if t.id == task_id:
                board.tasks[i] = task
                break
        await self.storage.save_board(board)
        return task

    async def get_board_summary(self) -> dict:
        board = await self.storage.load_board()
        columns: dict[str, list] = {}

        closed_sprint_task_ids = set()
        try:
            sprints = await _load_sprints_from_storage(self.storage)
            for sp in sprints:
                if sp.is_closed:
                    for tid in sp.task_ids:
                        closed_sprint_task_ids.add(tid)
        except Exception:
            pass

        for stage in self.config.pipeline:
            columns[stage.id] = []

        seen = set()
        for t in board.tasks:
            if t.id in seen:
                continue
            if t.status.value == "done" and t.id in closed_sprint_task_ids:
                continue
            seen.add(t.id)
            status_key = t.status.value
            if status_key not in columns:
                columns[status_key] = []
            columns[status_key].append(t.model_dump())

        return {
            "columns": columns,
            "total": len(board.tasks),
            "pipeline": [s.model_dump() for s in self.config.pipeline],
            "agents": [a.model_dump() for a in self.config.agents],
            "config": self.config.model_dump(),
        }

    async def get_board_view(self) -> str:
        board = await self.storage.load_board()
        sprints = await _load_sprints_from_storage(self.storage)
        closed_ids = set()
        for sp in sprints:
            if sp.is_closed:
                for tid in sp.task_ids:
                    closed_ids.add(tid)

        lines = ["=" * 80, f"  {self.config.name.upper()} - KANBAN BOARD", "=" * 80]

        for stage in self.config.pipeline:
            tasks = [t for t in board.tasks if t.status.value == stage.id]
            if stage.id == "done":
                tasks = [t for t in tasks if t.id not in closed_ids]
            lines.append(f"\n  [{stage.label}] ({len(tasks)} task(s))")
            lines.append("  " + "-" * 40)
            for t in sorted(tasks, key=lambda x: x.priority, reverse=True):
                icon = "!!" if t.status.value == "blocked" else "  "
                lines.append(f"  {icon} {t.id} | P{t.priority} | {t.title[:60]}")
        return "\n".join(lines)


async def _load_sprints_from_storage(storage) -> list:
    from agile_team.shared.models import Sprint
    import json as _json
    sprints = []
    if hasattr(storage, '_pool'):
        try:
            if storage._pool is None:
                await storage._get_pool()
            async with storage._pool.acquire() as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS agile_sprints (
                        sprint_id TEXT PRIMARY KEY,
                        data JSONB NOT NULL,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
                rows = await conn.fetch("SELECT data FROM agile_sprints ORDER BY created_at DESC")
                for r in rows:
                    data = _json.loads(r["data"]) if isinstance(r["data"], str) else r["data"]
                    sprints.append(Sprint(**data))
        except Exception:
            pass
    return sprints
