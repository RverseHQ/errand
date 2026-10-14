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
class Job[P = Any, R = Any]:
    """一条持久化的差事"""

    id: str
    kind: str
    payload: P
    """提交时的输入"""
    status: Status = Status.RUNNING
    result: R | None = None
    """办成后处理函数的返回值"""
    error: str | None = None
    """失败时的异常描述"""


type Handler[P, R] = Callable[[Job[P]], Awaitable[R]]
