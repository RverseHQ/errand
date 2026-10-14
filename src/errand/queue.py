import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, Self
from uuid import uuid4

from errand.job import Handler, Job
from errand.store import Store

logger = logging.getLogger("errand")


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
        """办理一件差事并落下结果"""

        try:
            self.connected().finish(job.id, await self.handlers[job.kind](job))
        except Exception as error:
            logger.exception("差事失败: id=%s kind=%s", job.id, job.kind)
            self.connected().fail(job.id, f"{type(error).__name__}: {error}")
