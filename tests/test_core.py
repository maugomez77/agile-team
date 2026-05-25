from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def workspace():
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


class TestBoardEngine:
    def test_create_task(self, workspace):
        from agile_team.board.engine import BoardEngine

        engine = BoardEngine(workspace)
        task = engine.create_task("Test task", "Description", priority=5)

        assert task.title == "Test task"
        assert task.description == "Description"
        assert task.priority == 5
        assert task.status.value == "backlog"
        assert engine.board_path.exists()

    def test_advance_task(self, workspace):
        from agile_team.board.engine import BoardEngine
        from agile_team.shared.models import TaskStatus

        engine = BoardEngine(workspace)
        task = engine.create_task("Test")

        engine.update_task_status(task.id, TaskStatus.SPEC_READY)
        task = engine.get_task(task.id)
        assert task.status == TaskStatus.SPEC_READY

    def test_reject_with_feedback(self, workspace):
        from agile_team.board.engine import BoardEngine
        from agile_team.shared.models import TaskStatus

        engine = BoardEngine(workspace)
        task = engine.create_task("Test")

        engine.update_task_status(task.id, TaskStatus.CODE_READY)
        engine.reject_task(task.id, "Architecture needs revision")

        task = engine.get_task(task.id)
        assert task.status == TaskStatus.ARCH_READY
        assert any("REJECTED" in n for n in task.feedback_notes)

    def test_board_view(self, workspace):
        from agile_team.board.engine import BoardEngine

        engine = BoardEngine(workspace)
        engine.create_task("Task 1", priority=3)
        engine.create_task("Task 2", priority=7)

        view = engine.get_board_view()
        assert "Task 1" in view
        assert "Task 2" in view
        assert "KANBAN BOARD" in view


class TestLLMFactory:
    def test_create_ollama(self):
        from agile_team.llm.base import LLMFactory

        import agile_team.llm.providers.ollama_provider
        import agile_team.llm.providers.deepseek_provider

        provider = LLMFactory.create("ollama", model="llama3.2")
        assert provider.provider_name == "ollama"

    def test_create_deepseek(self):
        from agile_team.llm.base import LLMFactory

        import agile_team.llm.providers.ollama_provider
        import agile_team.llm.providers.deepseek_provider

        provider = LLMFactory.create("deepseek", model="deepseek-chat", api_key="test")
        assert provider.provider_name == "deepseek"

    def test_unknown_provider(self):
        from agile_team.llm.base import LLMFactory

        with pytest.raises(ValueError, match="Unknown provider"):
            LLMFactory.create("nonexistent", model="test")


class TestModels:
    def test_task_creation(self):
        from agile_team.shared.models import Task, TaskStatus

        task = Task(title="Hello", description="World", priority=3)
        assert task.id.startswith("TASK-")
        assert task.status == TaskStatus.BACKLOG
        assert task.priority == 3

    def test_board_next_actionable(self):
        from agile_team.shared.models import Board, Task, TaskStatus

        board = Board()
        t1 = Task(title="Low", priority=1, status=TaskStatus.CODE_READY)
        t2 = Task(title="High", priority=10, status=TaskStatus.SPEC_READY)
        board.tasks = [t1, t2]

        actionable = board.get_next_actionable()
        assert actionable[0].title == "High"

    def test_rejection_map(self):
        from agile_team.shared.models import REJECTION_MAP, TaskStatus

        assert REJECTION_MAP[TaskStatus.CODE_READY] == TaskStatus.ARCH_READY
        assert REJECTION_MAP[TaskStatus.TEST_READY] == TaskStatus.CODE_READY


class TestStorage:
    def test_memory_storage(self):
        from agile_team.shared.models import Task
        from agile_team.shared.storage import MemoryStorage

        storage = MemoryStorage()
        task = Task(title="Test", description="Desc", priority=3)
        import asyncio
        asyncio.run(storage.save_task(task))
        loaded = asyncio.run(storage.load_task(task.id))
        assert loaded is not None
        assert loaded.title == "Test"


class TestBoardService:
    def test_create_and_get_task(self):
        from agile_team.board.service import BoardService
        from agile_team.shared.config import TeamConfig
        from agile_team.shared.storage import MemoryStorage

        import asyncio

        storage = MemoryStorage()
        config = TeamConfig.default()
        service = BoardService(storage, config)

        task = asyncio.run(service.create_task("Feature X", "Description", priority=8))
        assert task.title == "Feature X"

        summary = asyncio.run(service.get_board_summary())
        assert summary["total"] == 1
        assert len(summary["pipeline"]) == 8

    def test_move_task(self):
        from agile_team.board.service import BoardService
        from agile_team.shared.config import TeamConfig
        from agile_team.shared.storage import MemoryStorage

        import asyncio

        storage = MemoryStorage()
        config = TeamConfig.default()
        service = BoardService(storage, config)

        task = asyncio.run(service.create_task("Move me"))
        updated = asyncio.run(service.move_task(task.id, "spec_ready"))
        assert updated.status.value == "spec_ready"


class TestTeamConfig:
    def test_default_config(self):
        from agile_team.shared.config import TeamConfig

        config = TeamConfig.default()
        assert config.name == "Full Agile Team"
        assert len(config.pipeline) == 8
        assert len(config.agents) >= 6

    def test_minimal_config(self):
        from agile_team.shared.config import TeamConfig

        config = TeamConfig.minimal()
        assert len(config.pipeline) == 4
        assert len(config.agents) == 2

    def test_agent_hierarchy(self):
        from agile_team.shared.config import TeamConfig

        config = TeamConfig.default()
        tech_lead = config.get_agent("tech_lead")
        assert tech_lead is not None
        assert tech_lead.is_lead is True
        assert len(tech_lead.team) == 2
        assert tech_lead.total_members == 3

    def test_disabled_agents_filtered(self):
        from agile_team.shared.config import TeamConfig

        config = TeamConfig.load()
        enabled = config.enabled_agents
        disabled_count = sum(1 for a in config.agents if not a.enabled)
        assert len(enabled) + disabled_count == len(config.agents)
