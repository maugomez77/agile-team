from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from agile_team.shared.models import Board, Task


class StorageBackend(ABC):
    """Abstract storage for board and task state."""

    @abstractmethod
    async def load_board(self) -> Board: ...

    @abstractmethod
    async def save_board(self, board: Board) -> None: ...

    @abstractmethod
    async def load_task(self, task_id: str) -> Optional[Task]: ...

    @abstractmethod
    async def save_task(self, task: Task) -> None: ...

    @abstractmethod
    async def list_task_ids(self) -> list[str]: ...

    @staticmethod
    def _dedup_board(board: Board) -> None:
        seen = set()
        deduped = []
        for t in board.tasks:
            if t.id not in seen:
                seen.add(t.id)
                deduped.append(t)
        board.tasks = deduped


class FileStorage(StorageBackend):
    """Local filesystem storage for CLI / local dev."""

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace)
        self.tasks_dir = self.workspace / "tasks"
        self.board_path = self.workspace / "board.json"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

    async def load_board(self) -> Board:
        if self.board_path.exists():
            return Board(**json.loads(self.board_path.read_text()))
        return Board()

    async def save_board(self, board: Board) -> None:
        self._dedup_board(board)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.board_path.write_text(board.model_dump_json(indent=2))

    async def load_task(self, task_id: str) -> Optional[Task]:
        task_path = self.tasks_dir / task_id / "task.json"
        if task_path.exists():
            return Task(**json.loads(task_path.read_text()))
        return None

    async def save_task(self, task: Task) -> None:
        task_dir = self.tasks_dir / task.id
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "task.json").write_text(task.model_dump_json(indent=2))

    async def list_task_ids(self) -> list[str]:
        if not self.tasks_dir.exists():
            return []
        return [
            d.name for d in self.tasks_dir.iterdir()
            if d.is_dir() and (d / "task.json").exists()
        ]


class PostgresStorage(StorageBackend):
    """PostgreSQL storage for serverless (Neon / Vercel Postgres)."""

    def __init__(self, database_url: str | None = None):
        raw = database_url or os.environ.get(
            "DATABASE_URL"
        ) or os.environ.get(
            "POSTGRES_URL"
        ) or os.environ.get(
            "POSTGRES_URL_NON_POOLING"
        )
        if not raw:
            raise RuntimeError(
                "No PostgreSQL connection string. "
                "Set DATABASE_URL, POSTGRES_URL, or POSTGRES_URL_NON_POOLING."
            )
        self.database_url = raw.replace("sslmode=require", "ssl=require")
        self._pool: object = None

    async def _get_pool(self):
        if self._pool is None:
            import asyncpg
            self._pool = await asyncpg.create_pool(
                self.database_url,
                min_size=1,
                max_size=5,
                statement_cache_size=0,
            )
            await self._ensure_schema()
        return self._pool

    async def _ensure_schema(self) -> None:
        pool = self._pool
        async with pool.acquire() as conn:  # type: ignore[union-attr]
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS agile_board (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    data JSONB NOT NULL DEFAULT '{}',
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS agile_tasks (
                    task_id TEXT PRIMARY KEY,
                    data JSONB NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await conn.execute("""
                INSERT INTO agile_board (id, data) VALUES (1, '{}')
                ON CONFLICT (id) DO NOTHING
            """)

    async def load_board(self) -> Board:
        pool = await self._get_pool()
        async with pool.acquire() as conn:  # type: ignore[union-attr]
            row = await conn.fetchrow("SELECT data FROM agile_board WHERE id = 1")
            if row and row["data"]:
                data = json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
                return Board(**data)
        return Board()

    async def save_board(self, board: Board) -> None:
        self._dedup_board(board)
        pool = await self._get_pool()
        async with pool.acquire() as conn:  # type: ignore[union-attr]
            await conn.execute(
                "INSERT INTO agile_board (id, data, updated_at) VALUES (1, $1, NOW()) "
                "ON CONFLICT (id) DO UPDATE SET data = $1, updated_at = NOW()",
                board.model_dump_json(indent=2),
            )

    async def load_task(self, task_id: str) -> Optional[Task]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:  # type: ignore[union-attr]
            row = await conn.fetchrow(
                "SELECT data FROM agile_tasks WHERE task_id = $1", task_id
            )
            if row and row["data"]:
                data = json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
                return Task(**data)
        return None

    async def save_task(self, task: Task) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:  # type: ignore[union-attr]
            await conn.execute(
                "INSERT INTO agile_tasks (task_id, data, updated_at) VALUES ($1, $2, NOW()) "
                "ON CONFLICT (task_id) DO UPDATE SET data = $2, updated_at = NOW()",
                task.id,
                task.model_dump_json(indent=2),
            )

    async def list_task_ids(self) -> list[str]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:  # type: ignore[union-attr]
            rows = await conn.fetch("SELECT task_id FROM agile_tasks ORDER BY created_at")
            return [r["task_id"] for r in rows]


class VercelKVStorage(StorageBackend):
    """Vercel KV (Redis) storage — fallback if no PostgreSQL."""

    BOARD_KEY = "agile_team:board"
    TASK_PREFIX = "agile_team:task:"

    def __init__(self):
        self._client: object = None

    @property
    def client(self):
        if self._client is None:
            from vercel_kv import VercelKV
            self._client = VercelKV()
        return self._client

    async def load_board(self) -> Board:
        data = await self.client.get(self.BOARD_KEY)
        if data:
            return Board(**json.loads(data))
        return Board()

    async def save_board(self, board: Board) -> None:
        await self.client.set(self.BOARD_KEY, board.model_dump_json(indent=2))

    async def load_task(self, task_id: str) -> Optional[Task]:
        data = await self.client.get(f"{self.TASK_PREFIX}{task_id}")
        if data:
            return Task(**json.loads(data))
        return None

    async def save_task(self, task: Task) -> None:
        await self.client.set(f"{self.TASK_PREFIX}{task.id}", task.model_dump_json(indent=2))

    async def list_task_ids(self) -> list[str]:
        keys = await self.client.keys(f"{self.TASK_PREFIX}*")
        return [k.replace(self.TASK_PREFIX, "") for k in keys]


class MemoryStorage(StorageBackend):
    """In-memory storage for testing / demo without persistence."""

    def __init__(self):
        self._board = Board()
        self._tasks: dict[str, Task] = {}

    async def load_board(self) -> Board:
        return self._board

    async def save_board(self, board: Board) -> None:
        self._dedup_board(board)
        self._board = board

    async def load_task(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    async def save_task(self, task: Task) -> None:
        self._tasks[task.id] = task
        if task not in self._board.tasks:
            self._board.tasks.append(task)

    async def list_task_ids(self) -> list[str]:
        return list(self._tasks.keys())


def get_storage(workspace: Path | None = None) -> StorageBackend:
    """Factory: returns the right storage backend based on environment.

    Priority:
    1. DATABASE_URL / POSTGRES_URL → PostgresStorage (Vercel + Neon)
    2. KV_URL → VercelKVStorage (Vercel KV / Redis)
    3. workspace directory exists → FileStorage (local dev)
    4. Fallback → MemoryStorage (ephemeral)
    """
    database_url = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("POSTGRES_URL")
        or os.environ.get("POSTGRES_URL_NON_POOLING")
    )
    if database_url:
        return PostgresStorage(database_url)

    kv_url = os.environ.get("KV_URL") or os.environ.get("VERCEL_KV_URL")
    kv_rest_api_url = os.environ.get("KV_REST_API_URL")
    kv_rest_api_token = os.environ.get("KV_REST_API_TOKEN")
    if kv_url or (kv_rest_api_url and kv_rest_api_token):
        return VercelKVStorage()  # type: ignore[return-value]

    if workspace and Path(workspace).exists():
        return FileStorage(workspace)

    if workspace:
        return FileStorage(workspace)

    return MemoryStorage()
