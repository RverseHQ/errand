import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

import msgspec
from pydantic import BaseModel

from errand import Job, Queue, Status


class Item(BaseModel):
    name: str


@dataclass
class Order:
    id: str
    items: list[Item]


class Envelope(msgspec.Struct):
    order: Order


class Note(TypedDict):
    text: str


def test_payloads_and_results_round_trip_as_declared_types(tmp_path: Path) -> None:
    queue = Queue(tmp_path / "q.db")

    @queue.handler("dataclass")
    async def by_dataclass(job: Job[Order]) -> list[Item]:
        return job.payload.items

    @queue.handler("struct")
    async def by_struct(job: Job[Envelope]) -> Order:
        return job.payload.order

    @queue.handler("pydantic")
    async def by_pydantic(job: Job[Item]) -> Item:
        return Item(name=job.payload.name.upper())

    @queue.handler("typeddict")
    async def by_typeddict(job: Job[Note]) -> str:
        return job.payload["text"]

    @queue.handler("untyped")
    async def untyped(job: Job) -> Any:
        return job.payload

    order = Order("1", [Item(name="a")])

    async def main() -> None:
        async with queue:
            ids = [
                by_dataclass.submit(order),
                by_struct.submit(Envelope(order)),
                by_pydantic.submit(Item(name="b")),
                by_typeddict.submit({"text": "你好"}),
                untyped.submit({"any": [1]}),
            ]
            await asyncio.sleep(0.05)

        assert by_dataclass.get(ids[0]) == Job(ids[0], "dataclass", order, Status.DONE, [Item(name="a")])
        assert by_struct.get(ids[1]) == Job(ids[1], "struct", Envelope(order), Status.DONE, order)
        assert by_pydantic.get(ids[2]) == Job(ids[2], "pydantic", Item(name="b"), Status.DONE, Item(name="B"))
        assert by_typeddict.get(ids[3]) == Job(ids[3], "typeddict", {"text": "你好"}, Status.DONE, "你好")
        assert untyped.get(ids[4]) == Job(ids[4], "untyped", {"any": [1]}, Status.DONE, {"any": [1]})

    asyncio.run(main())


def test_payload_that_no_longer_matches_fails(tmp_path: Path) -> None:
    async def submit() -> str:
        queue = Queue(tmp_path / "q.db")

        @queue.handler("order")
        async def order(job: Job[dict[str, int]]) -> None:
            await asyncio.sleep(3600)

        async with queue:
            id = order.submit({"id": 1})
            await asyncio.sleep(0)
        return id

    async def restart_with_new_schema(id: str) -> None:
        queue = Queue(tmp_path / "q.db")

        @queue.handler("order")
        async def order(job: Job[Order]) -> None:
            return None

        async with queue:
            await asyncio.sleep(0.05)
        job = queue.store.get(id)
        assert job is not None and job.status is Status.FAILED
        assert job.error is not None and job.error.startswith("ValidationError")

    asyncio.run(restart_with_new_schema(asyncio.run(submit())))
