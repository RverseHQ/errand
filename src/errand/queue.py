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
    只能在事件循环所在线程使用, 同一个数据库文件只允许一个进程使用

    参数
    - path: SQLite 数据库文件路径
    """

    def __init__(self, path: str | Path) -> None:
        self.store = Store(path)
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
        self.store.insert(job)
        self.start(job)
        return job.id

    def get(self, id: str) -> Job | None:
        """查询一件差事的当前快照"""

        return self.store.get(id)

    async def __aenter__(self) -> Self:
        """启动队列并重跑上次未办完的差事"""

        self.open = True
        for job in self.store.running():
            self.start(job)
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
            self.store.fail(job.id, f"{type(error).__name__}: {error}")
        else:
            self.store.finish(job.id, result)
