import asyncio
import json
import logging
import sqlite3
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Self
from uuid import uuid4

logger = logging.getLogger("errand")

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL,
    result TEXT,
    error TEXT
)
"""


class Status(StrEnum):
    """差事状态"""

    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Job:
    """一条持久化的差事"""

    id: str
    kind: str
    payload: Any
    """提交时的 JSON 输入"""
    status: Status = Status.RUNNING
    result: Any = None
    """办成后处理函数的 JSON 返回值"""
    error: str | None = None
    """失败时的异常描述"""


type Handler = Callable[[Job], Awaitable[Any]]


class Queue:
    """单进程内的持久化异步任务队列

    提交即落盘并立刻起跑, 进程重启后未办完的差事从头重跑, 处理函数需要容忍重跑.
    只能在事件循环所在线程使用, 同一个数据库文件只允许一个进程使用

    参数
    - path: SQLite 数据库文件路径
    """

    def __init__(self, path: str | Path) -> None:
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(SCHEMA)
        self.handlers: dict[str, Handler] = {}
        self.tasks: set[asyncio.Task[None]] = set()
        self.open = False

    def handler(self, kind: str) -> Callable[[Handler], Handler]:
        """注册一种差事的处理函数, 抛出异常即失败, 返回值按 JSON 保存为结果"""

        def register(handler: Handler) -> Handler:
            self.handlers[kind] = handler
            return handler

        return register

    def submit(self, kind: str, payload: Any) -> str:
        """提交一件差事并返回它的标识

        参数
        - kind: 已注册的差事类型
        - payload: 可 JSON 序列化的输入
        """

        if not self.open:
            raise RuntimeError("队列未启动")
        if kind not in self.handlers:
            raise KeyError(f"未注册的差事类型: {kind}")
        job = Job(uuid4().hex, kind, payload)
        self.db.execute(
            "INSERT INTO jobs (id, kind, payload, status) VALUES (?, ?, ?, ?)",
            (job.id, kind, dumps(payload), job.status),
        )
        self.start(job)
        return job.id

    def get(self, id: str) -> Job | None:
        """查询一件差事的当前快照"""

        row = self.db.execute("SELECT id, kind, payload, status, result, error FROM jobs WHERE id = ?", (id,)).fetchone()
        if row is None:
            return None
        id, kind, payload, status, result, error = row
        return Job(id, kind, json.loads(payload), Status(status), loads(result), error)

    async def __aenter__(self) -> Self:
        """启动队列并重跑上次未办完的差事"""

        self.open = True
        rows = self.db.execute("SELECT id, kind, payload FROM jobs WHERE status = ?", (Status.RUNNING,)).fetchall()
        for id, kind, payload in rows:
            self.start(Job(id, kind, json.loads(payload)))
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        """取消在办的差事, 它们保持 running 状态等待下次启动重跑"""

        self.open = False
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def start(self, job: Job) -> None:
        task = asyncio.create_task(self.run(job), name=f"errand-{job.kind}-{job.id}")
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def run(self, job: Job) -> None:
        """办理一件差事并落下结果"""

        try:
            result = await self.handlers[job.kind](job)
        except Exception as error:
            logger.exception("差事失败: id=%s kind=%s", job.id, job.kind)
            self.db.execute(
                "UPDATE jobs SET status = ?, error = ? WHERE id = ?",
                (Status.FAILED, f"{type(error).__name__}: {error}", job.id),
            )
        else:
            self.db.execute(
                "UPDATE jobs SET status = ?, result = ? WHERE id = ?",
                (Status.DONE, dumps(result), job.id),
            )


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def loads(value: str | None) -> Any:
    return None if value is None else json.loads(value)
