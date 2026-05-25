from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class TaskStatus(StrEnum):
    BACKLOG = "backlog"
    SPEC_READY = "spec_ready"
    SPEC_IN_PROGRESS = "spec_in_progress"
    ARCH_READY = "arch_ready"
    ARCH_IN_PROGRESS = "arch_in_progress"
    CODE_READY = "code_ready"
    CODE_IN_PROGRESS = "code_in_progress"
    TEST_READY = "test_ready"
    TEST_IN_PROGRESS = "test_in_progress"
    DEPLOY_READY = "deploy_ready"
    DEPLOY_IN_PROGRESS = "deploy_in_progress"
    DONE = "done"
    BLOCKED = "blocked"


class ArtifactType(StrEnum):
    SPECIFICATION = "specification"
    ARCHITECTURE = "architecture"
    SOURCE_CODE = "source_code"
    TEST_CODE = "test_code"
    TEST_RESULTS = "test_results"
    DEPLOY_CONFIG = "deploy_config"
    FEEDBACK = "feedback"


class AgentRole(StrEnum):
    SCRUM_MASTER = "scrum_master"
    TECH_LEAD = "tech_lead"
    ARCHITECT = "architect"
    CODER = "coder"
    QA = "qa"
    DEVOPS = "devops"


PIPELINE_STAGES: list[tuple[TaskStatus, AgentRole]] = [
    (TaskStatus.SPEC_READY, AgentRole.TECH_LEAD),
    (TaskStatus.ARCH_READY, AgentRole.ARCHITECT),
    (TaskStatus.CODE_READY, AgentRole.CODER),
    (TaskStatus.TEST_READY, AgentRole.QA),
    (TaskStatus.DEPLOY_READY, AgentRole.DEVOPS),
]

REJECTION_MAP: dict[TaskStatus, TaskStatus] = {
    TaskStatus.ARCH_READY: TaskStatus.SPEC_READY,
    TaskStatus.CODE_READY: TaskStatus.ARCH_READY,
    TaskStatus.TEST_READY: TaskStatus.CODE_READY,
    TaskStatus.DEPLOY_READY: TaskStatus.TEST_READY,
    TaskStatus.DONE: TaskStatus.DEPLOY_READY,
}


class Artifact(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    task_id: str
    artifact_type: ArtifactType
    content: str = ""
    file_path: str = ""
    created_by: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1


class ActivityEntry(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    agent: str = "system"
    action: str = "commented"
    message: str = ""
    artifact_ref: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Task(BaseModel):
    id: str = Field(default_factory=lambda: f"TASK-{uuid.uuid4().hex[:8].upper()}")
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.BACKLOG
    priority: int = 0
    assigned_to: Optional[AgentRole] = None
    artifacts: list[Artifact] = []
    feedback_notes: list[str] = []
    activity_log: list[ActivityEntry] = []
    parent_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    workspace_path: str = ""

    @property
    def task_dir(self) -> Path:
        return Path(self.workspace_path) / self.id if self.workspace_path else Path(self.id)


class Board(BaseModel):
    tasks: list[Task] = []
    columns: dict[str, list[str]] = Field(default_factory=dict)
    active_sprint: Optional[str] = None
    sprint_history: list[dict] = []

    def get_tasks_by_status(self, status: TaskStatus) -> list[Task]:
        return [t for t in self.tasks if t.status == status]

    def get_next_actionable(self) -> list[Task]:
        actionable_statuses = {
            TaskStatus.SPEC_READY,
            TaskStatus.ARCH_READY,
            TaskStatus.CODE_READY,
            TaskStatus.TEST_READY,
            TaskStatus.DEPLOY_READY,
        }
        return sorted(
            (t for t in self.tasks if t.status in actionable_statuses),
            key=lambda t: t.priority,
            reverse=True,
        )


class Sprint(BaseModel):
    id: str = Field(default_factory=lambda: f"SPRINT-{uuid.uuid4().hex[:6].upper()}")
    name: str
    goal: str = ""
    task_ids: list[str] = Field(default_factory=list)
    is_closed: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
