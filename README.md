# errand

单进程内的持久化异步任务队列。提交即落盘 SQLite 并立刻起跑，重启后把没办完的从头重跑。

它只解决一件事：**接下的活不因重启而丢**。回调、兜底结果、模型并发都归业务和 Loom。

- 处理函数会被至少执行一次，需要容忍重跑
- 抛异常即失败，不重试，需要兜底就在处理函数里自己兜
- 只能在事件循环所在线程使用，同一个数据库文件只允许一个进程使用

## 用法

```python
from errand import Job, Queue

queue = Queue("data/errand.sqlite3")


@queue.handler("analysis")
async def analysis(job: Job) -> dict:
    request = AnalysisTaskRequest.model_validate(job.payload)
    try:
        result = await run_turn(request)
    except Exception:
        result = fallback_result(request)
    await callback(request.callback_url, job.id, result)
    return result


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with queue:
        yield


@app.post("/analysis-tasks")
async def create(body: AnalysisTaskRequest) -> dict:
    return {"task_id": queue.submit("analysis", body.model_dump(mode="json"))}


@app.get("/analysis-tasks/{task_id}")
async def read(task_id: str) -> dict:
    job = queue.get(task_id)
    ...
```

## 开发

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run ty check
```
