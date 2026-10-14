# errand

单进程内的持久化异步任务队列。提交即落盘 SQLite，在同一个事件循环里办理，重启后接着办。

它只解决一件事：**接下的活不丢，按上限并发地办完，失败按需重试**。不管 HTTP、不管业务结果长什么样、不管模型并发。

## 语义

- 至少一次：进程中断时在办的差事，下次启动从头重跑，处理函数要能容忍重跑
- 并发上限按差事类型配置，模型级的全局并发仍归 Loom 中间件
- 抛异常即失败，`attempts` 次内指数退避重试，进程中断不计入次数
- `submit` 指定的 `id` 已存在时忽略，用来做幂等
- 同一个数据库文件只允许一个进程使用

## 用法

回调本身就是一件需要可靠送达的差事，所以把它登记成另一种类型，而不是在业务里顺手 POST。

```python
from contextlib import asynccontextmanager

from errand import Job, Queue
from fastapi import FastAPI
from niquests import AsyncSession

queue = Queue("data/errand.sqlite3")


@queue.handler("analysis", concurrency=8)
async def analysis(job: Job) -> dict:
    try:
        result = await run_agent(job.payload["input"])
    except Exception:
        result = fallback()
    # 固定 id: 分析被重跑时不会重复回调
    queue.submit("callback", {"url": job.payload["callback_url"], "body": {"task_id": job.id, "result": result}},
                 id=f"{job.id}:callback")
    return result


@queue.handler("callback", concurrency=16, attempts=8, retry_delay=5)
async def callback(job: Job) -> None:
    async with AsyncSession() as session:
        response = await session.post(job.payload["url"], json=job.payload["body"], timeout=30)
        response.raise_for_status()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with queue:
        yield


app = FastAPI(lifespan=lifespan)


@app.post("/analysis-tasks")
def create(body: AnalysisRequest) -> dict:
    return {"task_id": queue.submit("analysis", body.model_dump(mode="json"))}


@app.get("/analysis-tasks/{task_id}")
def read(task_id: str) -> dict:
    job = queue.get(task_id)
    ...
```

## 开发

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run ty check
```
