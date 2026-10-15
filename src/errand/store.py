import json
import sqlite3
from datetime import UTC, datetime
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
    error TEXT,
    created_at TEXT,
    finished_at TEXT
)
"""

ADDED = ("created_at", "finished_at")
"""早期版本的表缺少的列, 打开时补上"""

COLUMNS = "id, kind, payload, status, result, error, created_at, finished_at"


class Store:
    """差事的 SQLite 持久化

    参数
    - path: SQLite 数据库文件路径
    """

    def __init__(self, path: str | Path) -> None:
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(SCHEMA)
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(jobs)")}
        for column in ADDED:
            if column not in columns:
                self.db.execute(f"ALTER TABLE jobs ADD COLUMN {column} TEXT")

    def close(self) -> None:
        self.db.close()

    def insert(self, job: Job) -> None:
        self.db.execute(
            "INSERT INTO jobs (id, kind, payload, status, created_at) VALUES (?, ?, ?, ?, ?)",
            (job.id, job.kind, dumps(job.payload), job.status, stamp(job.created_at)),
        )

    def get(self, id: str) -> Job | None:
        row = self.db.execute(f"SELECT {COLUMNS} FROM jobs WHERE id = ?", (id,)).fetchone()
        return None if row is None else restore(row)

    def running(self) -> list[Job]:
        """未到终态的差事, 按提交顺序"""

        rows = self.db.execute(f"SELECT {COLUMNS} FROM jobs WHERE status = ? ORDER BY rowid", (Status.RUNNING,))
        return [restore(row) for row in rows]

    def finish(self, id: str, result: Any) -> None:
        self.db.execute(
            "UPDATE jobs SET status = ?, result = ?, finished_at = ? WHERE id = ?",
            (Status.DONE, dumps(result), stamp(datetime.now(UTC)), id),
        )

    def fail(self, id: str, error: str) -> None:
        self.db.execute(
            "UPDATE jobs SET status = ?, error = ?, finished_at = ? WHERE id = ?",
            (Status.FAILED, error, stamp(datetime.now(UTC)), id),
        )


def restore(row: tuple[Any, ...]) -> Job:
    """把一行记录还原成差事"""

    id, kind, payload, status, result, error, created_at, finished_at = row
    return Job(
        id,
        kind,
        json.loads(payload),
        Status(status),
        None if result is None else json.loads(result),
        error,
        parse(created_at),
        parse(finished_at),
    )


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def stamp(at: datetime | None) -> str | None:
    return None if at is None else at.isoformat()


def parse(at: str | None) -> datetime | None:
    return None if at is None else datetime.fromisoformat(at)
