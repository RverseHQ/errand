<p align="center">
  <img src="assets/icon.svg" alt="errand" width="128" height="128">
</p>

<h1 align="center">errand</h1>

<p align="center">Minimal durable task queue for Python.</p>

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
- At-least-once. Interrupted jobs rerun from the start on the next launch. Side effects
  a handler made before the interruption, such as a callback, happen again, so make
  them idempotent downstream, for example by keying them on the job id.
- Failure is a result. A raised exception ends the job as `failed` once the attempts its
  handler allows run out, one by default. A retry reruns the job from the start after
  waiting 1s, 2s, 4s and so on, at most an hour. The count of failed attempts survives
  restarts, and a rerun after an interruption does not use one up.
- JSON in, JSON out. Payloads and results are stored as JSON.
- Event loop only. Call the queue from the thread that runs the loop.
- Lifespan owns the connection. The database is open only inside `async with queue`.

### Scope

`errand` is a durable task queue and nothing else. Its primitives are the ones task
queues broadly agree on: register a handler by name, enqueue durably, execute and
record the outcome, redeliver what never finished, inspect jobs, and start and stop
cleanly. It stays minimal and grows only with real need.

Every addition starts from a real need of a service, and the core takes the smallest
shape that meets it. A need is judged in this order:

1. If it is task queue design consensus, and the reason queues share it holds for
   errand, it goes into the core.
2. Otherwise, if the existing API or primitives can express it, the service composes
   it, as in [Composing primitives](#composing-primitives).
3. Otherwise, if only one service needs it, it stays in that service.
4. Otherwise, when several services share it, its leverage is weighed case by case,
   and it may go into the core.

Being composable is not a reason to reject a consensus primitive whose reason holds.
Per-kind concurrency limits can be written as a semaphore in each handler, but every
task queue offers them, and recovery is what releases a backlog all at once, so the
queue bounds it. Timeouts are consensus too, but other queues offer them because a
handler running in a worker process or thread cannot stop itself. A handler on the
event loop can, so timeouts are composed.

## API

| API | Purpose |
| --- | --- |
| `Queue(path)` | Create a queue backed by a SQLite file, opened on enter. |
| `queue.path` | The SQLite file the queue was created with. |
| `@queue.handler(kind, concurrency=None, attempts=1)` | Register an async handler for a kind of job. With a limit, at most that many jobs of the kind run at once and the rest wait in submission order. With more than one attempt, a failed job stays `running`, backs off without holding its slot, and runs again until it succeeds or the attempts run out. |
| `queue.submit(kind, payload)` | Persist a job, start it, and return its id. |
| `queue.get(id)` | Read a snapshot of a job, or `None`. |
| `queue.running()` | List snapshots of unfinished jobs in submission order, including interrupted ones awaiting rerun. |
| `async with queue` | Open the database and rerun interrupted jobs on enter. Cancel running jobs and close the database on exit. |
| `Job` | `id`, `kind`, `payload`, `status`, `result`, `error`, `created_at`, `finished_at`. Times are UTC. |
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

### Retries

A retry reruns the whole job, so give a side effect that needs retrying, such as a
callback, its own kind, and submit it from the handler that produced the result. A
failed callback then does not redo the work before it, and one that never got through
stays in the database as a `failed` job.

```python
import asyncio

from errand import Job, Queue, Status

queue = Queue("errand.db")
calls = 0


@queue.handler("notify", attempts=3)
async def notify(job: Job) -> None:
    global calls
    calls += 1
    if calls == 1:
        raise ConnectionError("peer is restarting")


async def main() -> None:
    async with queue:
        id = queue.submit("notify", {"answer": 42})
        await asyncio.sleep(1.1)

        job = queue.get(id)

        assert job.status is Status.DONE
        assert calls == 2


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

### Composing primitives

Requirements of one service are built from the primitives. This reuses an unfinished
job for an identical request instead of starting another. What counts as identical
is the service's decision.

```python
import asyncio

from errand import Job, Queue

queue = Queue("errand.db")


@queue.handler("summarize")
async def summarize(job: Job) -> str:
    await asyncio.sleep(1)
    return job.payload["text"][:10]


def submit_once(payload: dict) -> str:
    for job in queue.running():
        if job.kind == "summarize" and job.payload == payload:
            return job.id
    return queue.submit("summarize", payload)


async def main() -> None:
    async with queue:
        first = submit_once({"text": "a long document"})
        second = submit_once({"text": "a long document"})

        assert first == second


asyncio.run(main())
```

A timeout is composed the same way. The handler bounds itself with `asyncio.timeout`,
and the `TimeoutError` it raises is an ordinary failure, so `attempts` and the backoff
apply to it, and the limit covers each attempt.

```python
import asyncio

from errand import Job, Queue, Status

queue = Queue("errand.db")


@queue.handler("summarize")
async def summarize(job: Job) -> str:
    async with asyncio.timeout(0.1):
        await asyncio.sleep(3600)
        return job.payload["text"][:10]


async def main() -> None:
    async with queue:
        id = queue.submit("summarize", {"text": "a long document"})
        await asyncio.sleep(0.2)

        assert queue.get(id).status is Status.FAILED


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

- a file lock that enforces one process per database

Submission:

- idempotent ids
- delayed jobs
- submission from other threads

Storage:

- retention of finished jobs
