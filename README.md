# AgentUE

AgentUE is a lightweight agent devloop kit. It provides small, composable pieces for running agents, delivering live state, and keeping execution outcomes recoverable.

The first release contains two capabilities:

- `agentue.ui`: a stateful event model for live interaction, persisted snapshots, and replay.
- `agentue.runner`: a four-phase task runner with live/execute separation, a Redis bridge, and heartbeat recovery.

```text
                         Redis bridge
                       /              \
request -> live coroutine              execute coroutine -> agent
              |                             |
              +------ AgentUE events <------+
                         |
                    client / log
```

AgentUE does not prescribe an agent implementation, model provider, tool system, web framework, or component library. Applications choose those pieces and use only the AgentUE capabilities they need.

## Install

Install only the UI event capability:

```bash
python -m pip install "agentue[ui]"
```

Install Runner and its Redis support:

```bash
python -m pip install "agentue[runner]"
```

For TypeScript applications, install the dependency-free UI protocol SDK:

```bash
bun add @compforge/agentue
```

The bare `agentue` package is a dependency-free namespace. `agentue[ui]` does not install Redis or Runner dependencies.

## UI event quick start

```python
from agentue.ui import BaseBlock, ModelMeta, PatchEmitter, UIModel, apply_patches

model = UIModel(biz="chat", meta=ModelMeta(), blocks=[])
emitter = PatchEmitter()

events = [
    emitter.start(model),
    emitter.block_append(BaseBlock(id="answer", type="text", content="Hello")),
    emitter.end(),
]

snapshot = apply_patches({}, events)
```

## Repository layout

```text
spec/              Normative UI event and SSE specifications
schema/            Language-neutral JSON Schemas
conformance/       Shared fixtures for SDK implementations
sdks/python/       agentue.ui and agentue.runner
sdks/typescript/   TypeScript UI event protocol SDK
docs/              Runtime design and operating contracts
```

Additional language capabilities can be added under `sdks/` as the kit grows.

See [the UI event specification](spec/protocol.md), [the SSE binding](spec/sse.md), [the Runner design](docs/runner.md), [the Python SDK](sdks/python/README.md), and [the TypeScript SDK](sdks/typescript/README.md).

## License

AgentUE is available under the [MIT License](LICENSE).
