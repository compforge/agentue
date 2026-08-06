# AgentUE TypeScript SDK

The TypeScript SDK provides the AgentUE UI event protocol without runtime dependencies. It includes typed semantic
models and patch events, runtime event validation, an ordered emitter, a deterministic reducer, and SSE framing.

```bash
bun add @compforge/agentue
```

```ts
import {
  PatchEmitter,
  PROTOCOL_VERSION,
  applyPatches,
  type UIModel,
} from "@compforge/agentue";

const model: UIModel = {
  version: PROTOCOL_VERSION,
  biz: "chat",
  meta: {},
  blocks: [],
};
const emitter = new PatchEmitter();
const events = [
  emitter.start(model),
  emitter.blockAppend({ id: "answer", type: "text", content: "Hello" }),
  emitter.end(),
];

const snapshot = applyPatches({}, events);
```

Domain-specific model and block fields remain application-owned. The SDK does not include an agent runtime, UI
components, or the AgentUE Runner.
