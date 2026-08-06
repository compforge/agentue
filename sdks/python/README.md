# AgentUE Python SDK

The Python SDK is split into optional capabilities.

## UI events

```bash
python -m pip install "agentue[ui]"
```

`agentue.ui` provides Pydantic models, an ordered patch emitter, a deterministic reducer, and the SSE binding.

```python
from agentue.ui import BaseBlock, ModelMeta, PatchEmitter, UIModel, apply_patches

model = UIModel(biz="chat", meta=ModelMeta())
emitter = PatchEmitter()
events = [
    emitter.start(model),
    emitter.block_append(BaseBlock(id="answer", type="text", content="Hello")),
    emitter.end(),
]
snapshot = apply_patches({}, events)
```

## Runner

```bash
python -m pip install "agentue[runner]"
```

Runner users provide exactly four lifecycle callbacks: `pre_start`, `prepare`, `stream`, and `complete`. Runner owns task spawning, Redis delivery, terminal control events, event-loop heartbeat observation, and timeout recovery.

```python
from agentue.runner import Runner, RunnerCallbacks

runner = Runner(
    redis,
    RunnerCallbacks(
        pre_start=pre_start,
        prepare=prepare,
        stream=stream,
        complete=complete,
    ),
)
await runner.start()

async for event in runner.run(task_id=task_id, data=request, model=model):
    yield event.data
```

Runner yields JSON without transport framing. For SSE, pass `event.data` and `event.cursor` to `agentue.ui.encode_sse`.

See [the Runner design](https://github.com/compforge/agentue/blob/main/docs/runner.md) for lifecycle and recovery requirements.
