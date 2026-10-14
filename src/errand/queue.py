import asyncio
import inspect
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, Self, get_args, get_type_hints
from uuid import uuid4

from errand.codec import decode, encode
from errand.job import Handler, Job
from errand.store import Record, Store

logger = logging.getLogger("errand")


class Errand[P, R]:
    """一种差事, 绑定类型名, 处理函数与输入输出类型

    输入输出类型从处理函数的签名读取, `job: Job[P]` 给出输入, 返回值注解给出输出, 缺省为 Any
    """

    def __init__(self, queue: "Queue", kind: str, handler: Handler[P, R]) -> None:
        self.queue = queue
        self.kind = kind
        self.handler = handler
        hints = get_type_hints(handler)
        first = next(iter(inspect.signature(handler).parameters))
        self.payload_type = next(iter(get_args(hints.get(first))), Any)
        self.result_type = hints.get("return", Any)

    def submit(self, payload: P) -> str:
        """提交一件差事并返回它的标识"""

        return self.queue.enqueue(self.kind, encode(payload))

    def get(self, id: str) -> Job[P, R] | None:
        """查询这一种差事的当前快照, 标识不存在或属于其他类型时返回 None"""

        record = self.queue.store.get(id)
        if record is None or record.kind != self.kind:
            return None
        result = None if record.result is None else decode(record.result, self.result_type)
        return Job(record.id, record.kind, decode(record.payload, self.payload_type), record.status, result, record.error)

    async def run(self, record: Record) -> str:
        """还原输入, 办理, 编码结果"""

        job: Job[P] = Job(record.id, record.kind, decode(record.payload, self.payload_type))
        return encode(await self.handler(job))


class Queue:
    """单进程内的持久化异步任务队列

    提交即落盘并立刻起跑, 进程重启后未办完的差事从头重跑, 处理函数需要容忍重跑.
    只能在事件循环所在线程使用, 同一个数据库文件只允许一个进程使用

    参数
    - path: SQLite 数据库文件路径
    """

    def __init__(self, path: str | Path) -> None:
        self.store = Store(path)
        self.errands: dict[str, Errand[Any, Any]] = {}
        self.tasks: set[asyncio.Task[None]] = set()
        self.open = False

    def handler[P, R](self, kind: str) -> Callable[[Handler[P, R]], Errand[P, R]]:
        """注册一种差事的处理函数, 返回用来提交和查询的差事句柄

        处理函数抛出异常即失败, 返回值按 JSON 保存为结果
        """

        def register(handler: Handler[P, R]) -> Errand[P, R]:
            errand = Errand(self, kind, handler)
            self.errands[kind] = errand
            return errand

        return register

    def enqueue(self, kind: str, payload: str) -> str:
        """落盘一件已编码的差事并起跑"""

        if not self.open:
            raise RuntimeError("队列未启动")
        record = Record(uuid4().hex, kind, payload)
        self.store.insert(record)
        self.start(record)
        return record.id

    async def __aenter__(self) -> Self:
        """启动队列并重跑上次未办完的差事"""

        self.open = True
        for record in self.store.running():
            self.start(record)
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        """取消在办的差事, 它们保持 running 状态等待下次启动重跑"""

        self.open = False
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def start(self, record: Record) -> None:
        task = asyncio.create_task(self.run(record), name=f"errand-{record.kind}-{record.id}")
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def run(self, record: Record) -> None:
        """办理一件差事并落下结果, 还原输入, 办理, 编码结果中任何一步出错都记为失败"""

        try:
            result = await self.errands[record.kind].run(record)
        except Exception as error:
            logger.exception("差事失败: id=%s kind=%s", record.id, record.kind)
            self.store.fail(record.id, f"{type(error).__name__}: {error}")
        else:
            self.store.finish(record.id, result)
