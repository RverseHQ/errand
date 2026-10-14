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

- Small core. No runtime dependencies.
- One file, one process. All state lives in a single SQLite database.
- At-least-once. Interrupted jobs rerun from the start on the next launch.
- Failure is a result. A raised exception ends the job as `failed`. Nothing retries.
- JSON in, JSON out. Payloads and results are stored as JSON.
- Event loop only. Call the queue from the thread that runs the loop.

## API

| API | Purpose |
| --- | --- |
| `Queue(path)` | Open or create a queue backed by a SQLite file. |
| `@queue.handler(kind)` | Register an async handler for a kind of job. |
| `queue.submit(kind, payload)` | Persist a job, start it, and return its id. |
| `queue.get(id)` | Read a snapshot of a job, or `None`. |
| `async with queue` | Rerun interrupted jobs on enter. Cancel running jobs on exit. |
| `Job` | `id`, `kind`, `payload`, `status`, `result`, `error`. |
| `Status` | `running`, `done`, `failed`. |

## Usage

### Handlers

```python
from errand import Job, Queue

queue = Queue("errand.db")


@queue.handler("greet")
async def greet(job: Job) -> str:
    return f"hello {job.payload['name']}"
```

### Submitting jobs

```python
import asyncio

from errand import Job, Queue, Status

queue = Queue("errand.db")


@queue.handler("greet")
async def greet(job: Job) -> str:
    return f"hello {job.payload['name']}"


async def main() -> None:
    async with queue:
        id = queue.submit("greet", {"name": "errand"})
        await asyncio.sleep(0)

        job = queue.get(id)

        assert job.status is Status.DONE
        assert job.result == "hello errand"


asyncio.run(main())
```

### Failures

```python
import asyncio

from errand import Job, Queue, Status

queue = Queue("errand.db")


@queue.handler("divide")
async def divide(job: Job) -> float:
    return job.payload["a"] / job.payload["b"]


async def main() -> None:
    async with queue:
        id = queue.submit("divide", {"a": 1, "b": 0})
        await asyncio.sleep(0)

        job = queue.get(id)

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
async def divide(job: Job) -> float | None:
    try:
        return job.payload["a"] / job.payload["b"]
    except ZeroDivisionError:
        return None


async def main() -> None:
    async with queue:
        id = queue.submit("divide", {"a": 1, "b": 0})
        await asyncio.sleep(0)

        job = queue.get(id)

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
    async def work(job: Job) -> None:
        await asyncio.sleep(3600)

    async with queue:
        id = queue.submit("work", None)
        await asyncio.sleep(0)

    assert queue.get(id).status is Status.RUNNING
    return id


async def restart(id: str) -> None:
    queue = Queue("errand.db")

    @queue.handler("work")
    async def work(job: Job) -> str:
        return "finished"

    async with queue:
        await asyncio.sleep(0)

        assert queue.get(id).result == "finished"


asyncio.run(restart(asyncio.run(crash())))
```

### Web services

```python
from contextlib import asynccontextmanager

from errand import Job, Queue
from fastapi import FastAPI, HTTPException

queue = Queue("errand.db")


@queue.handler("summarize")
async def summarize(job: Job) -> str:
    return await llm(job.payload["text"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with queue:
        yield


app = FastAPI(lifespan=lifespan)


@app.post("/tasks")
async def create(text: str) -> str:
    return queue.submit("summarize", {"text": text})


@app.get("/tasks/{id}")
async def read(id: str) -> Job:
    job = queue.get(id)
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
