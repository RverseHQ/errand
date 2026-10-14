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
            if job.status in (Status.DONE, Status.FAILED):
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
            assert job.status is Status.DONE
            assert job.result == {"id": id, "text": "你好"}

    asyncio.run(main())


def test_retries_then_fails(tmp_path: Path) -> None:
    queue = Queue(tmp_path / "q.db")
    calls: list[int] = []

    @queue.handler("flaky", attempts=3, retry_delay=0.01)
    async def flaky(job: Job) -> None:
        calls.append(job.attempts)
        raise RuntimeError("boom")

    async def main() -> None:
        async with queue:
            job = await settle(queue, queue.submit("flaky", None))
            assert job.status is Status.FAILED
            assert job.attempts == 3
            assert job.error == "RuntimeError: boom"

    asyncio.run(main())
    assert calls == [0, 1, 2]


def test_retry_can_succeed(tmp_path: Path) -> None:
    queue = Queue(tmp_path / "q.db")

    @queue.handler("flaky", attempts=2, retry_delay=0.01)
    async def flaky(job: Job) -> int:
        if job.attempts == 0:
            raise RuntimeError("first")
        return job.attempts

    async def main() -> None:
        async with queue:
            job = await settle(queue, queue.submit("flaky", None))
            assert (job.status, job.result, job.error) == (Status.DONE, 1, "RuntimeError: first")

    asyncio.run(main())


def test_concurrency_is_bounded_per_kind(tmp_path: Path) -> None:
    queue = Queue(tmp_path / "q.db")
    active = 0
    peak = 0

    @queue.handler("slow", concurrency=2)
    async def slow(job: Job) -> None:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.05)
        active -= 1

    async def main() -> None:
        async with queue:
            ids = [queue.submit("slow", i) for i in range(6)]
            for id in ids:
                assert (await settle(queue, id)).status is Status.DONE

    asyncio.run(main())
    assert peak == 2


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
            job = await settle(queue, id)
            assert (job.status, job.attempts, job.result) == (Status.DONE, 0, "ok")

    id = asyncio.run(first())
    asyncio.run(second(id))
    assert runs == [id, id]


def test_submit_is_idempotent_by_id(tmp_path: Path) -> None:
    queue = Queue(tmp_path / "q.db")
    runs = 0

    @queue.handler("once")
    async def once(job: Job) -> None:
        nonlocal runs
        runs += 1

    async def main() -> None:
        async with queue:
            assert queue.submit("once", 1, id="task-1:callback") == "task-1:callback"
            await settle(queue, "task-1:callback")
            queue.submit("once", 2, id="task-1:callback")
            await asyncio.sleep(0.05)
        job = queue.get("task-1:callback")
        assert job is not None and job.payload == 1

    asyncio.run(main())
    assert runs == 1


def test_submit_from_another_thread(tmp_path: Path) -> None:
    queue = Queue(tmp_path / "q.db")

    @queue.handler("echo")
    async def echo(job: Job) -> object:
        return job.payload

    async def main() -> None:
        async with queue:
            id = await asyncio.to_thread(queue.submit, "echo", [1, 2])
            assert (await settle(queue, id)).result == [1, 2]

    asyncio.run(main())


def test_submit_before_start_runs_on_start(tmp_path: Path) -> None:
    queue = Queue(tmp_path / "q.db")

    @queue.handler("echo")
    async def echo(job: Job) -> object:
        return job.payload

    id = queue.submit("echo", "早到")

    async def main() -> None:
        async with queue:
            assert (await settle(queue, id)).result == "早到"

    asyncio.run(main())


def test_rejects_unknown_kind(tmp_path: Path) -> None:
    queue = Queue(tmp_path / "q.db")
    with pytest.raises(KeyError):
        queue.submit("nope", None)
