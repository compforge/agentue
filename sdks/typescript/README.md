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
} from "@compforge/agentue/ui";

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

Domain-specific model and block fields remain application-owned. The `ui` subpath is independent from other AgentUE
capabilities and does not include an agent runtime, UI components, or the AgentUE Runner.

## Optional stream addressing

Use `new PatchEmitter(0, "message-123")` to tag every emitted event with a
`stream_id`, or continue using `new PatchEmitter()` to omit it. SSE encoding and
decoding preserve this field independently of the transport cursor. Route events
by stream_id before calling the single-model reducer; an end event does not close
other streams. See [logical stream addressing](../../spec/protocol.md#42-optional-logical-stream-addressing).

## Reference blocks

Protocol 1.1 accepts a mixed ordered list of inline `{id, type, ...}` blocks and
reference `{id, ref}` blocks. Existing 1.0 inline snapshots remain readable.
`ref` is an opaque key interpreted by the application selected by `biz`; reference
blocks carry no `type` or body. Whole-block `set` creates or replaces either form.
The application must load and check the referenced block's ID before field-level
`set` or `append`; the pure reducer rejects unresolved targets without loading.
See the [protocol](../../spec/protocol.md#34-reference-blocks) for the full contract.

```ts
import { PROTOCOL_VERSION, type UIModel } from "@compforge/agentue/ui";

const model: UIModel = {
  version: PROTOCOL_VERSION,
  biz: "chat",
  meta: {},
  blocks: [{ id: "b2", ref: "opaque-reference" }],
};
```
