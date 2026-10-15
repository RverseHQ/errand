from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
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
    created_at: datetime | None = None
    """受理时间, UTC, 加入时间戳之前的旧差事为空"""
    finished_at: datetime | None = None
    """进入终态的时间, UTC"""


type Handler = Callable[[Job], Awaitable[Any]]
