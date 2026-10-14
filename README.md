# errand

进程内的持久化异步任务队列。

一个 SQLite 文件，一个事件循环。没有 broker，没有 worker 进程，没有配置。

## 保证

- 提交即落盘。进程退出，任务不丢。
- 至少执行一次。中断的任务在下次启动时从头重跑。
- 终态唯一。返回即 `done`，抛出即 `failed`。

## 不做

- 重试。失败是结果，不是事件。兜底在处理函数内完成。
- 限流。并发上限属于被限制的资源，不属于队列。
- 调度、优先级、超时、定时。
- 多进程。一个数据库文件，一个进程。
- 跨线程。只在事件循环所在线程调用。

## 原则

写可能有用的最简单的代码。

每一项能力都对应一个已经发生的问题。没有发生的问题，没有代码。

过度设计比过度抽象更昂贵。需求会生长，代码随之重构，而不是预先为它铺路。

## 接口

```python
import asyncio

from errand import Job, Queue

queue = Queue("errand.sqlite3")


@queue.handler("summarize")
async def summarize(job: Job) -> str:
    return await llm(job.payload["text"])


async def main() -> None:
    async with queue:
        id = queue.submit("summarize", {"text": "..."})
        job = queue.get(id)


asyncio.run(main())
```

| | |
|---|---|
| `Queue(path)` | 打开或创建队列 |
| `@queue.handler(kind)` | 注册处理函数，`async (Job) -> JSON` |
| `queue.submit(kind, payload) -> str` | 落盘、起跑、返回标识 |
| `queue.get(id) -> Job \| None` | 读取快照 |
| `async with queue` | 进入时重跑中断的任务，退出时取消在办的任务 |

```
running ──→ done
        └─→ failed
```

## 安装

```bash
uv add git+https://github.com/RverseHQ/errand
```

Python 3.13+。无运行时依赖。

## 开发

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run ty check
```
