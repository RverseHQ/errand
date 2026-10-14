import asyncio
from pathlib import Path

import pytest

from errand import Errand, Job, Queue, Status


async def settle[P, R](errand: Errand[P, R], id: str) -> Job[P, R]:
    """等到差事进入终态"""

    async with asyncio.timeout(5):
        while True:
            job = errand.get(id)
            assert job is not None
            if job.status is not Status.RUNNING:
                return job
            await asyncio.sleep(0.01)


def test_runs_and_keeps_result(tmp_path: Path) -> None:
    queue = Queue(tmp_path / "q.db")

    @queue.handler("echo")
    async def echo(job: Job[dict[str, str]]) -> dict[str, str]:
        return {"id": job.id, "text": job.payload["text"]}

    async def main() -> None:
        async with queue:
            id = echo.submit({"text": "你好"})
            job = await settle(echo, id)
            assert (job.status, job.result) == (Status.DONE, {"id": id, "text": "你好"})

    asyncio.run(main())


def test_records_failure(tmp_path: Path) -> None:
    queue = Queue(tmp_path / "q.db")

    @queue.handler("boom")
    async def boom(job: Job[None]) -> None:
        raise RuntimeError("boom")

    async def main() -> None:
        async with queue:
            job = await settle(boom, boom.submit(None))
            assert (job.status, job.error) == (Status.FAILED, "RuntimeError: boom")

    asyncio.run(main())


def test_unencodable_result_fails_instead_of_hanging(tmp_path: Path) -> None:
    queue = Queue(tmp_path / "q.db")

    @queue.handler("odd")
    async def odd(job: Job[None]) -> object:
        return object()

    async def main() -> None:
        async with queue:
            job = await settle(odd, odd.submit(None))
            assert job.status is Status.FAILED
            assert job.error is not None and job.error.startswith("TypeError")

    asyncio.run(main())


def test_get_ignores_other_kinds(tmp_path: Path) -> None:
    queue = Queue(tmp_path / "q.db")

    @queue.handler("a")
    async def a(job: Job[int]) -> int:
        return job.payload

    @queue.handler("b")
    async def b(job: Job[int]) -> int:
        return job.payload

    async def main() -> None:
        async with queue:
            id = a.submit(1)
            await settle(a, id)
            assert b.get(id) is None
            assert b.get("missing") is None

    asyncio.run(main())


def test_interrupted_job_reruns_after_restart(tmp_path: Path) -> None:
    runs: list[str] = []

    def build(block: bool) -> Errand[None, str]:
        queue = Queue(tmp_path / "q.db")

        @queue.handler("long")
        async def long(job: Job[None]) -> str:
            runs.append(job.id)
            if block:
                await asyncio.sleep(3600)
            return "ok"

        return long

    async def first() -> str:
        long = build(block=True)
        async with long.queue:
            id = long.submit(None)
            while not runs:
                await asyncio.sleep(0.01)
        job = long.get(id)
        assert job is not None and job.status is Status.RUNNING
        return id

    async def second(id: str) -> None:
        long = build(block=False)
        async with long.queue:
            assert (await settle(long, id)).result == "ok"

    id = asyncio.run(first())
    asyncio.run(second(id))
    assert runs == [id, id]


def test_rejects_submit_outside_lifespan(tmp_path: Path) -> None:
    queue = Queue(tmp_path / "q.db")

    @queue.handler("echo")
    async def echo(job: Job[None]) -> None:
        return None

    with pytest.raises(RuntimeError):
        echo.submit(None)
