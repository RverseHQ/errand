import asyncio
import sqlite3
from contextlib import closing
from datetime import UTC
from pathlib import Path

import pytest

from errand import Job, Queue, Status


async def settle(queue: Queue, id: str) -> Job:
    """等到差事进入终态"""

    async with asyncio.timeout(5):
        while True:
            job = queue.get(id)
            assert job is not None
            if job.status is not Status.RUNNING:
                return job
            await asyncio.sleep(0.01)


def test_runs_and_keeps_result(tmp_path: Path) -> None:
    queue = Queue(tmp_path / "q.db")

    @queue.handler("echo")
    async def echo(job: Job) -> dict:
        return {"id": job.id, "text": job.payload["text"]}

    async def main() -> None:
        async with queue:
            id = queue.submit("echo", {"text": "你好"})
            job = await settle(queue, id)
            assert (job.status, job.result) == (Status.DONE, {"id": id, "text": "你好"})

    asyncio.run(main())


def test_records_failure(tmp_path: Path) -> None:
    queue = Queue(tmp_path / "q.db")

    @queue.handler("boom")
    async def boom(job: Job) -> None:
        raise RuntimeError("boom")

    async def main() -> None:
        async with queue:
            job = await settle(queue, queue.submit("boom", None))
            assert (job.status, job.error) == (Status.FAILED, "RuntimeError: boom")

    asyncio.run(main())


def test_unencodable_result_fails_instead_of_hanging(tmp_path: Path) -> None:
    queue = Queue(tmp_path / "q.db")

    @queue.handler("odd")
    async def odd(job: Job) -> object:
        return object()

    async def main() -> None:
        async with queue:
            job = await settle(queue, queue.submit("odd", None))
            assert job.status is Status.FAILED
            assert job.error is not None and job.error.startswith("TypeError")

    asyncio.run(main())


def test_records_timestamps_in_utc(tmp_path: Path) -> None:
    queue = Queue(tmp_path / "q.db")

    @queue.handler("echo")
    async def echo(job: Job) -> object:
        assert job.created_at is not None and job.finished_at is None
        return job.payload

    async def main() -> None:
        async with queue:
            job = await settle(queue, queue.submit("echo", 1))
            assert job.created_at is not None and job.finished_at is not None
            assert job.created_at.tzinfo is UTC and job.created_at <= job.finished_at

    asyncio.run(main())


def test_upgrades_database_without_timestamps(tmp_path: Path) -> None:
    path = tmp_path / "q.db"
    with closing(sqlite3.connect(path)) as db:
        db.execute(
            "CREATE TABLE jobs (id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,"
            " status TEXT NOT NULL, result TEXT, error TEXT)"
        )
        db.execute("INSERT INTO jobs VALUES ('old', 'echo', '1', 'done', '1', NULL)")
        db.commit()
    queue = Queue(path)

    @queue.handler("echo")
    async def echo(job: Job) -> object:
        return job.payload

    async def main() -> None:
        async with queue:
            assert queue.get("old") == Job("old", "echo", 1, Status.DONE, 1)
            assert (await settle(queue, queue.submit("echo", 2))).created_at is not None

    asyncio.run(main())


def test_interrupted_job_reruns_after_restart(tmp_path: Path) -> None:
    runs: list[str] = []

    def build(block: bool) -> Queue:
        queue = Queue(tmp_path / "q.db")

        @queue.handler("long")
        async def long(job: Job) -> str:
            runs.append(job.id)
            if block:
                await asyncio.sleep(3600)
            return "ok"

        return queue

    async def first() -> str:
        queue = build(block=True)
        async with queue:
            id = queue.submit("long", None)
            while not runs:
                await asyncio.sleep(0.01)
            job = queue.get(id)
            assert job is not None and job.status is Status.RUNNING
        return id

    async def second(id: str) -> None:
        queue = build(block=False)
        async with queue:
            assert (await settle(queue, id)).result == "ok"

    id = asyncio.run(first())
    asyncio.run(second(id))
    assert runs == [id, id]


def test_lists_unfinished_jobs(tmp_path: Path) -> None:
    queue = Queue(tmp_path / "q.db")
    gate = asyncio.Event()

    @queue.handler("wait")
    async def wait(job: Job) -> None:
        await gate.wait()

    @queue.handler("echo")
    async def echo(job: Job) -> object:
        return job.payload

    async def main() -> None:
        async with queue:
            first = queue.submit("wait", {"n": 1})
            done = queue.submit("echo", None)
            second = queue.submit("wait", {"n": 2})
            await settle(queue, done)
            assert [(job.id, job.payload) for job in queue.running()] == [(first, {"n": 1}), (second, {"n": 2})]
            gate.set()
            await settle(queue, second)
            await settle(queue, first)
            assert queue.running() == []

    asyncio.run(main())


def test_rejects_submit_outside_lifespan_and_unknown_kind(tmp_path: Path) -> None:
    queue = Queue(tmp_path / "q.db")

    @queue.handler("echo")
    async def echo(job: Job) -> object:
        return job.payload

    with pytest.raises(RuntimeError):
        queue.submit("echo", None)

    async def main() -> None:
        async with queue:
            with pytest.raises(KeyError):
                queue.submit("nope", None)

    asyncio.run(main())


def test_closes_database_on_exit_and_reopens_on_enter(tmp_path: Path) -> None:
    path = tmp_path / "q.db"
    queue = Queue(path)

    @queue.handler("echo")
    async def echo(job: Job) -> object:
        return job.payload

    async def main() -> None:
        async with queue:
            id = queue.submit("echo", 1)
            await settle(queue, id)
            with pytest.raises(RuntimeError):
                async with queue:
                    pass
        with pytest.raises(RuntimeError):
            queue.get(id)
        for file in tmp_path.iterdir():
            file.unlink()
        async with queue:
            assert queue.get(id) is None
            await settle(queue, queue.submit("echo", 2))

    asyncio.run(main())
