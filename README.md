# errand

Minimal durable task queue for Python.

## Design

`errand` is built around a small idea: work that was accepted should not disappear
when the process does. A job is written to SQLite before it starts, runs as a task
on the event loop you already have, and runs again from the beginning if the
process stops first.

The runtime favors a short list of guarantees over a large feature surface. There
is no broker, no worker process, and no configuration. Capabilities are added when
a real workload needs them, and the code is refactored then, not prepared in advance.

- Small core. One runtime dependency, `msgspec`.
- One file, one process. All state lives in a single SQLite database.
- At-least-once. Interrupted jobs rerun from the start on the next launch.
- Failure is a result. A raised exception ends the job as `failed`. Nothing retries.
- Typed at both ends. Payload and result types are read from the handler signature.
- Stored as JSON. dataclass, msgspec, pydantic, `TypedDict` and plain values round-trip.
- Event loop only. Call the queue from the thread that runs the loop.

## API

| API | Purpose |
| --- | --- |
| `Queue(path)` | Open or create a queue backed by a SQLite file. |
| `@queue.handler(kind)` | Register an async handler and return its `Errand`. |
| `errand.submit(payload)` | Persist a job, start it, and return its id. |
| `errand.get(id)` | Read a typed snapshot of a job of this kind, or `None`. |
| `async with queue` | Rerun interrupted jobs on enter. Cancel running jobs on exit. |
| `Job[P, R]` | `id`, `kind`, `payload: P`, `status`, `result: R \| None`, `error`. |
| `Status` | `running`, `done`, `failed`. |

## Usage

### Handlers

```python
from dataclasses import dataclass

from errand import Job, Queue


@dataclass
class Greeting:
    name: str


queue = Queue("errand.db")


@queue.handler("greet")
async def greet(job: Job[Greeting]) -> str:
    return f"hello {job.payload.name}"
```

### Submitting jobs

```python
import asyncio
from dataclasses import dataclass

from errand import Job, Queue, Status


@dataclass
class Greeting:
    name: str


queue = Queue("errand.db")


@queue.handler("greet")
async def greet(job: Job[Greeting]) -> str:
    return f"hello {job.payload.name}"


async def main() -> None:
    async with queue:
        id = greet.submit(Greeting("errand"))
        await asyncio.sleep(0)

        job = greet.get(id)

        assert job.status is Status.DONE
        assert job.result == "hello errand"


asyncio.run(main())
```

### Types

```python
import asyncio
from typing import TypedDict

import msgspec
from pydantic import BaseModel

from errand import Job, Queue


class Order(msgspec.Struct):
    id: str


class Receipt(BaseModel):
    order_id: str


class Note(TypedDict):
    text: str


queue = Queue("errand.db")


@queue.handler("receipt")
async def receipt(job: Job[Order]) -> Receipt:
    return Receipt(order_id=job.payload.id)


@queue.handler("note")
async def note(job: Job[Note]) -> list[str]:
    return job.payload["text"].split()


async def main() -> None:
    async with queue:
        first = receipt.submit(Order("1"))
        second = note.submit({"text": "hello errand"})
        await asyncio.sleep(0)

        assert receipt.get(first).result == Receipt(order_id="1")
        assert note.get(second).result == ["hello", "errand"]
        assert note.get(first) is None


asyncio.run(main())
```

### Failures

```python
import asyncio

from errand import Job, Queue, Status

queue = Queue("errand.db")


@queue.handler("divide")
async def divide(job: Job[tuple[int, int]]) -> float:
    a, b = job.payload
    return a / b


async def main() -> None:
    async with queue:
        id = divide.submit((1, 0))
        await asyncio.sleep(0)

        job = divide.get(id)

        assert job.status is Status.FAILED
        assert job.error == "ZeroDivisionError: division by zero"


asyncio.run(main())
```

### Fallbacks

```python
import asyncio

from errand import Job, Queue, Status

queue = Queue("errand.db")


@queue.handler("divide")
async def divide(job: Job[tuple[int, int]]) -> float | None:
    a, b = job.payload
    try:
        return a / b
    except ZeroDivisionError:
        return None


async def main() -> None:
    async with queue:
        id = divide.submit((1, 0))
        await asyncio.sleep(0)

        job = divide.get(id)

        assert job.status is Status.DONE
        assert job.result is None


asyncio.run(main())
```

### Recovery

```python
import asyncio

from errand import Job, Queue, Status


async def crash() -> str:
    queue = Queue("errand.db")

    @queue.handler("work")
    async def work(job: Job[None]) -> str:
        await asyncio.sleep(3600)
        return "unreachable"

    async with queue:
        id = work.submit(None)
        await asyncio.sleep(0)

    assert work.get(id).status is Status.RUNNING
    return id


async def restart(id: str) -> None:
    queue = Queue("errand.db")

    @queue.handler("work")
    async def work(job: Job[None]) -> str:
        return "finished"

    async with queue:
        await asyncio.sleep(0)

        assert work.get(id).result == "finished"


asyncio.run(restart(asyncio.run(crash())))
```

A payload that no longer matches its type after a schema change fails the job
with a `ValidationError` instead of running with stale data.

### Web services

```python
from contextlib import asynccontextmanager

from errand import Job, Queue
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

queue = Queue("errand.db")


class Article(BaseModel):
    text: str


@queue.handler("summarize")
async def summarize(job: Job[Article]) -> str:
    return await llm(job.payload.text)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with queue:
        yield


app = FastAPI(lifespan=lifespan)


@app.post("/tasks")
async def create(article: Article) -> str:
    return summarize.submit(article)


@app.get("/tasks/{id}")
async def read(id: str) -> Job[Article, str]:
    job = summarize.get(id)
    if job is None:
        raise HTTPException(404)
    return job
```

## Roadmap

Added when a real workload needs them, not before.

Execution:

- retries with backoff
- per-kind concurrency limits
- timeouts

Submission:

- idempotent ids
- delayed jobs
- submission from other threads

Storage:

- timestamps
- retention of finished jobs
