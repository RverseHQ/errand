import asyncio
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
