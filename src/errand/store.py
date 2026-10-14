import json
import sqlite3
from pathlib import Path
from typing import Any

from errand.job import Job, Status

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

COLUMNS = "id, kind, payload, status, result, error"


class Store:
    """差事的 SQLite 持久化

    参数
    - path: SQLite 数据库文件路径
    """

    def __init__(self, path: str | Path) -> None:
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(SCHEMA)

    def close(self) -> None:
        self.db.close()

    def insert(self, job: Job) -> None:
        self.db.execute(
            "INSERT INTO jobs (id, kind, payload, status) VALUES (?, ?, ?, ?)",
            (job.id, job.kind, dumps(job.payload), job.status),
        )

    def get(self, id: str) -> Job | None:
        row = self.db.execute(f"SELECT {COLUMNS} FROM jobs WHERE id = ?", (id,)).fetchone()
        return None if row is None else job(row)

    def running(self) -> list[Job]:
        """未到终态的差事, 按提交顺序"""

        rows = self.db.execute(f"SELECT {COLUMNS} FROM jobs WHERE status = ? ORDER BY rowid", (Status.RUNNING,))
        return [job(row) for row in rows]

    def finish(self, id: str, result: Any) -> None:
        self.db.execute("UPDATE jobs SET status = ?, result = ? WHERE id = ?", (Status.DONE, dumps(result), id))

    def fail(self, id: str, error: str) -> None:
        self.db.execute("UPDATE jobs SET status = ?, error = ? WHERE id = ?", (Status.FAILED, error, id))


def job(row: tuple[Any, ...]) -> Job:
    """把一行记录还原成差事"""

    id, kind, payload, status, result, error = row
    return Job(id, kind, json.loads(payload), Status(status), None if result is None else json.loads(result), error)


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)
