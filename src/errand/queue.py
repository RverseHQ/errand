import asyncio
import json
import logging
import sqlite3
import threading
import time
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
    attempts INTEGER NOT NULL DEFAULT 0,
    result TEXT,
    error TEXT,
    run_after REAL NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_pending ON jobs (kind, status, run_after);
"""


class Status(StrEnum):
    """差事状态"""

    PENDING = "pending"
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
    status: Status
    attempts: int
    """已经失败的次数"""
    result: Any = None
    """办成后处理函数的 JSON 返回值"""
    error: str | None = None
    """最近一次失败的异常描述"""


type Handler = Callable[[Job], Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class Route:
    """一种差事的办理方式"""

    handler: Handler
    concurrency: int
    attempts: int
    retry_delay: float


class Queue:
    """单进程内的持久化异步任务队列

    提交即落盘, 由同一事件循环里的协程办理, 进程重启后未办完的差事从头重跑,
    语义是至少一次, 处理函数需要容忍重跑. 同一个数据库文件只允许一个进程使用

    参数
    - path: SQLite 数据库文件路径
    """

    def __init__(self, path: str | Path) -> None:
        self.db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        self.lock = threading.Lock()
        self.routes: dict[str, Route] = {}
        self.running: dict[str, set[asyncio.Task[None]]] = {}
        self.loop: asyncio.AbstractEventLoop | None = None
        self.wake: asyncio.Event | None = None
        self.dispatcher: asyncio.Task[None] | None = None

    def handler(
        self, kind: str, *, concurrency: int = 1, attempts: int = 1, retry_delay: float = 1
    ) -> Callable[[Handler], Handler]:
        """注册一种差事的处理函数

        处理函数抛出异常即视为本次失败, 返回值按 JSON 保存为结果

        参数
        - kind: 差事类型
        - concurrency: 同类差事同时办理的上限
        - attempts: 最多尝试次数, 进程中断不计入
        - retry_delay: 首次重试前等待的秒数, 之后每次翻倍, 最长十分钟
        """

        def register(handler: Handler) -> Handler:
            self.routes[kind] = Route(handler, concurrency, attempts, retry_delay)
            self.running[kind] = set()
            return handler

        return register

    def submit(self, kind: str, payload: Any, *, id: str | None = None) -> str:
        """提交一件差事并返回它的标识

        可以在任意线程调用. 指定的标识已经存在时什么也不做, 可用于幂等提交

        参数
        - kind: 已注册的差事类型
        - payload: 可 JSON 序列化的输入
        - id: 差事标识, 默认随机生成
        """

        if kind not in self.routes:
            raise KeyError(f"未注册的差事类型: {kind}")
        id = id or uuid4().hex
        now = time.time()
        with self.lock:
            self.db.execute(
                "INSERT OR IGNORE INTO jobs (id, kind, payload, status, run_after, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (id, kind, dumps(payload), Status.PENDING, now, now, now),
            )
        if self.loop is not None and self.wake is not None:
            self.loop.call_soon_threadsafe(self.wake.set)
        return id

    def get(self, id: str) -> Job | None:
        """查询一件差事的当前快照"""

        with self.lock:
            row = self.db.execute(
                "SELECT id, kind, payload, status, attempts, result, error FROM jobs WHERE id = ?", (id,)
            ).fetchone()
        if row is None:
            return None
        id, kind, payload, status, attempts, result, error = row
        return Job(id, kind, json.loads(payload), Status(status), attempts, loads(result), error)

    async def __aenter__(self) -> Self:
        with self.lock:
            self.db.execute("UPDATE jobs SET status = ? WHERE status = ?", (Status.PENDING, Status.RUNNING))
        self.loop = asyncio.get_running_loop()
        self.wake = asyncio.Event()
        self.dispatcher = asyncio.create_task(self.dispatch(self.wake), name="errand-dispatcher")
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        """停止派发并取消在办的差事, 它们保持 running 状态等待下次启动恢复"""

        tasks = [task for tasks in self.running.values() for task in tasks]
        if self.dispatcher is not None:
            tasks.append(self.dispatcher)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.loop = None
        self.wake = None
        self.dispatcher = None

    async def dispatch(self, wake: asyncio.Event) -> None:
        """有空位就领差事, 没活干就睡到被唤醒或最近一件重试到期"""

        while True:
            wake.clear()
            delay = self.launch(wake)
            try:
                async with asyncio.timeout(delay):
                    await wake.wait()
            except TimeoutError:
                pass

    def launch(self, wake: asyncio.Event) -> float | None:
        """按空位领取到期的差事并起跑, 返回仍有空位的类型里距下一件到期的秒数

        满载的类型不参与计算, 由在办差事结束时唤醒
        """

        now = time.time()
        idle: list[str] = []
        with self.lock:
            for kind, route in self.routes.items():
                running = self.running[kind]
                free = route.concurrency - len(running)
                if free <= 0:
                    continue
                rows = self.db.execute(
                    "UPDATE jobs SET status = ?, updated_at = ? WHERE id IN ("
                    " SELECT id FROM jobs WHERE kind = ? AND status = ? AND run_after <= ?"
                    " ORDER BY run_after LIMIT ?)"
                    " RETURNING id, kind, payload, status, attempts",
                    (Status.RUNNING, now, kind, Status.PENDING, now, free),
                ).fetchall()
                for id, kind, payload, status, attempts in rows:
                    job = Job(id, kind, json.loads(payload), Status(status), attempts)
                    task = asyncio.create_task(self.run(job, route), name=f"errand-{kind}-{id}")
                    running.add(task)
                    task.add_done_callback(running.discard)
                    task.add_done_callback(lambda _: wake.set())
                if len(rows) < free:
                    idle.append(kind)
            (next_run,) = self.db.execute(
                "SELECT MIN(run_after) FROM jobs WHERE status = ? AND kind IN (SELECT value FROM json_each(?))",
                (Status.PENDING, dumps(idle)),
            ).fetchone()
        return None if next_run is None else max(next_run - now, 0)

    async def run(self, job: Job, route: Route) -> None:
        """办理一件差事并落下结果"""

        try:
            result = await route.handler(job)
        except Exception as error:
            attempts = job.attempts + 1
            retry = attempts < route.attempts
            logger.exception("差事失败: id=%s kind=%s attempts=%d retry=%s", job.id, job.kind, attempts, retry)
            now = time.time()
            delay = min(route.retry_delay * 2 ** (attempts - 1), 600)
            with self.lock:
                self.db.execute(
                    "UPDATE jobs SET status = ?, attempts = ?, error = ?, run_after = ?, updated_at = ? WHERE id = ?",
                    (
                        Status.PENDING if retry else Status.FAILED,
                        attempts,
                        f"{type(error).__name__}: {error}",
                        now + delay,
                        now,
                        job.id,
                    ),
                )
        else:
            with self.lock:
                self.db.execute(
                    "UPDATE jobs SET status = ?, result = ?, updated_at = ? WHERE id = ?",
                    (Status.DONE, dumps(result), time.time(), job.id),
                )


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def loads(value: str | None) -> Any:
    return None if value is None else json.loads(value)
