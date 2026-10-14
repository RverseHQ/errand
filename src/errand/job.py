from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


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
