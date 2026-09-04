# Runner

## Language coverage

The Python SDK implements the complete callback lifecycle and heartbeat
recovery described below. The Go SDK currently provides the Redis EventBridge
and resumable delivery primitives; its host application remains the execution
owner and supplies any recovery policy.

## Lifecycle

Runner separates the request-facing live coroutine from background execution:

```text
live:     pre_start -> publish start -> consume Redis Stream -> return at end
execute:              prepare -> stream -> complete -> error? -> end
```

Closing the live consumer does not cancel execute. Redis Streams bridge the two coroutines, so another process can serve the live stream or recover a task.

Call `await runner.start()` from application startup so the shared watchdog and timeout scanner are active even before this process handles a task. `run()` also starts them lazily. Call `await runner.aclose()` during shutdown. Passing a `RedisConnector` transfers its lifecycle to Runner; passing an already connected Redis client leaves client shutdown with the application.

Applications provide only four callbacks:

- `pre_start(context)` creates durable business state needed before execution starts.
- `prepare(context)` prepares the execution input and resources.
- `stream(context)` yields `set` and `append` UI events.
- `complete(completion)` persists the final outcome.

Runner invokes `complete` on every path it controls, including callback failure, cancellation, and graceful shutdown. If an execute process or event loop cannot make progress, another healthy Runner invokes the same callback with `context=None` and the durable `task_id`. The callback must therefore be idempotent and able to reload business state by task ID.

## Heartbeat and recovery

The execute event loop advances an in-process pulse. One shared `python_stdx.asyncio.EventLoopWatchdog` observes that event loop from an independent OS thread, regardless of the number of running tasks. The observer never advances the pulse itself: once the execute loop stalls, the local watchdog detects it and every task's Redis heartbeat updates stop.

Every Runner instance also scans the Redis heartbeat index. A healthy instance claims an expired task, invokes `complete` with `source=heartbeat_timeout`, then appends `error` and `end` control events. The Redis claim prevents concurrent scanners from recovering the same task at the same time; `complete` remains idempotent because a process can recover after another instance has already started recovery.

At least one separate healthy process or event loop is required to recover a process that never resumes. No in-process coroutine can recover its own permanently blocked event loop.

## Event ownership

Runner owns `start`, `error`, `ping`, and `end`. The application `stream` callback yields only `set` and `append`, preserving the distinction between lifecycle control and domain data updates.

Runner calls `complete` before publishing terminal control events. Consumers therefore interpret `end` as “the durable business completion phase has run,” not merely “the agent generator stopped.”
