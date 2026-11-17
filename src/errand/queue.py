import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self
from uuid import uuid4

from errand.job import Handler, Job
from errand.store import Store

logger = logging.getLogger("errand")


def backoff(failures: int) -> float:
    """累计失败 n 次后重试前等待的秒数, 从 1 秒起逐次翻倍, 最长 1 小时"""

    return min(2 ** (failures - 1), 3600)


class Queue:
    """单进程内的持久化异步任务队列

    提交即落盘并立刻起跑, 进程重启后未办完的差事从头重跑, 处理函数需要容忍重跑.
    数据库连接随 async with 打开和关闭, 提交与查询都要在其中进行.
    只能在事件循环所在线程使用, 同一个数据库文件只允许一个进程使用

    参数
    - path: SQLite 数据库文件路径
    """

    def __init__(self, path: str | Path) -> None:
        self.path = path
        self.store: Store | None = None
        self.handlers: dict[str, Handler] = {}
        self.concurrency: dict[str, int] = {}
        self.attempts: dict[str, int] = {}
        self.slots: dict[str, asyncio.Semaphore] = {}
        self.tasks: set[asyncio.Task[None]] = set()
        self.open = False

    def handler(self, kind: str, concurrency: int | None = None, attempts: int = 1) -> Callable[[Handler], Handler]:
        """注册一种差事的处理函数, 抛出异常即失败, 返回值按 JSON 保存为结果

        参数
        - kind: 差事类型
        - concurrency: 同类型最多同时办理的件数, 超出的保持 running 按提交顺序等待, 为空时不限制
        - attempts: 总尝试次数, 含第一次, 还有剩余时失败后保持 running, 退避后从头重跑,
          重启后的重跑不计入次数
        """

        if concurrency is not None and concurrency < 1:
            raise ValueError(f"并发上限至少为 1: {concurrency}")

        if attempts < 1:
            raise ValueError(f"尝试次数至少为 1: {attempts}")

        def register(handler: Handler) -> Handler:
            self.handlers[kind] = handler
            self.attempts[kind] = attempts
            if concurrency is None:
                self.concurrency.pop(kind, None)
            else:
                self.concurrency[kind] = concurrency
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
        job = Job(uuid4().hex, kind, payload, created_at=datetime.now(UTC))
        self.connected().insert(job)
        self.start(job)
        return job.id

    def get(self, id: str) -> Job | None:
        """查询一件差事的当前快照"""

        return self.connected().get(id)

    def running(self) -> list[Job]:
        """未到终态的差事快照, 按提交顺序

        包括被中断后等待下次启动重跑的差事, 不保证每件都正在执行
        """

        return self.connected().running()

    async def __aenter__(self) -> Self:
        """打开数据库并重跑上次未办完的差事"""

        if self.store is not None:
            raise RuntimeError("队列已启动")
        self.store = Store(self.path)
        self.slots = {kind: asyncio.Semaphore(limit) for kind, limit in self.concurrency.items()}
        self.open = True
        for job in self.store.running():
            self.start(job)
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        """取消在办的差事并关闭数据库, 这些差事保持 running 状态等待下次启动重跑"""

        self.open = False
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            self.connected().close()
            self.store = None

    def connected(self) -> Store:
        """当前打开的存储, 不在 async with 中时报错"""

        if self.store is None:
            raise RuntimeError("队列未启动")
        return self.store

    def start(self, job: Job) -> None:
        task = asyncio.create_task(self.run(job), name=f"errand-{job.kind}-{job.id}")
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def run(self, job: Job) -> None:
        """办理一件差事并落下结果, 失败且还有剩余次数时退避重试, 退避期间不占并发名额"""

        handler = self.handlers[job.kind]
        slot = self.slots.get(job.kind)
        while True:
            try:
                if slot is None:
                    result = await handler(job)
                else:
                    async with slot:
                        result = await handler(job)
                self.connected().finish(job.id, result)
                return
            except Exception as error:
                failures = self.connected().count_failure(job.id)
                if failures >= self.attempts[job.kind]:
                    logger.exception("差事失败: id=%s kind=%s failures=%d", job.id, job.kind, failures)
                    self.connected().fail(job.id, f"{type(error).__name__}: {error}")
                    return
                logger.warning("差事失败, 稍后重试: id=%s kind=%s failures=%d", job.id, job.kind, failures, exc_info=True)
            await asyncio.sleep(backoff(failures))
