import sqlite3
from dataclasses import dataclass
from pathlib import Path

from errand.job import Status

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


@dataclass(frozen=True, slots=True)
class Record:
    """差事的存储形态, 输入与结果是 JSON 文本"""

    id: str
    kind: str
    payload: str
    status: Status = Status.RUNNING
    result: str | None = None
    error: str | None = None


class Store:
    """差事的 SQLite 持久化

    参数
    - path: SQLite 数据库文件路径
    """

    def __init__(self, path: str | Path) -> None:
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(SCHEMA)

    def insert(self, record: Record) -> None:
        self.db.execute(
            "INSERT INTO jobs (id, kind, payload, status) VALUES (?, ?, ?, ?)",
            (record.id, record.kind, record.payload, record.status),
        )

    def get(self, id: str) -> Record | None:
        row = self.db.execute(f"SELECT {COLUMNS} FROM jobs WHERE id = ?", (id,)).fetchone()
        return None if row is None else record(row)

    def running(self) -> list[Record]:
        """未到终态的差事, 按提交顺序"""

        rows = self.db.execute(f"SELECT {COLUMNS} FROM jobs WHERE status = ? ORDER BY rowid", (Status.RUNNING,))
        return [record(row) for row in rows]

    def finish(self, id: str, result: str) -> None:
        self.db.execute("UPDATE jobs SET status = ?, result = ? WHERE id = ?", (Status.DONE, result, id))

    def fail(self, id: str, error: str) -> None:
        self.db.execute("UPDATE jobs SET status = ?, error = ? WHERE id = ?", (Status.FAILED, error, id))


def record(row: tuple[str, str, str, str, str | None, str | None]) -> Record:
    id, kind, payload, status, result, error = row
    return Record(id, kind, payload, Status(status), result, error)
