# AgentUE Protocol 1.1

## 1. Scope

AgentUE defines how an agent-backed application communicates renderable semantic state to a user interface.

It sits between framework-specific agent events and the presentation layer:

```text
agent runtime -> adapter -> AgentUE event stream -> reducer -> semantic UI model -> renderer
```

An adapter decides which runtime signals are useful to a user and expresses them as AgentUE blocks and patches. The protocol does not expose an agent runtime's internal event vocabulary directly, and it does not prescribe how a block is rendered.

The key words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** describe normative requirements.

## 2. Design goals

AgentUE is designed around five properties:

1. **One model for every delivery mode.** Live rendering, persisted history, and replay use the same semantic model.
2. **Stable ordered blocks.** A block has a stable identity and type while remaining extensible for domain-specific data.
3. **Small update vocabulary.** The core protocol separates lifecycle control from `set` and `append` state changes.
4. **Deterministic replay.** Applying the same ordered patch sequence produces the same model.
5. **Transport independence.** JSON event semantics are defined here; transports such as SSE are separate bindings.

## 3. Semantic model

A complete model has this shape:

```json
{
  "version": "1.1",
  "biz": "chat",
  "meta": {
    "task_id": "task-123",
    "error": null
  },
  "blocks": [
    {
      "id": "answer",
      "type": "text",
      "content": "Hello"
    }
  ]
}
```

### 3.1 Model fields

| Field | Type | Requirement | Meaning |
| --- | --- | --- | --- |
| `version` | string | REQUIRED | Semantic model compatibility version. |
| `biz` | string | REQUIRED | Domain identifier that selects domain-specific model rules. |
| `meta` | object | REQUIRED | Extensible model-level metadata. |
| `blocks` | array | REQUIRED | Ordered semantic blocks. |

JSON member names defined by AgentUE use `snake_case`. Domain extensions SHOULD follow the same convention.

### 3.2 Metadata

`meta` is an extension point. AgentUE defines these common fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `error` | object or null | Structured terminal or recoverable error information. |
| `task_id` | string or null | Stable task identity usable by application-level resume or cancel APIs. |
| `trace_id` | string or null | Observability correlation identifier. |
| `stats` | object or null | Domain-defined run statistics. |

An error object contains `code` and `message`, and MAY contain `detail` and `trace_id`.

Applications MAY add metadata fields. A generic consumer MUST preserve fields it does not interpret.

### 3.3 Blocks

An inline block MUST contain:

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | Stable identity, unique within the model. |
| `type` | string | Domain-defined semantic type such as `text`, `tool`, or `artifact`. |

A block MAY contain `parent_id` to express nesting or ownership. Blocks that belong to the same execution or visual group MAY contain `group_id`. These dimensions are independent: `parent_id` is hierarchical, while `group_id` associates peer blocks.

All other inline block fields except the reserved `ref` field are domain-defined. Renderers choose a component from `biz` and the resolved block's `type`; the protocol does not ship executable UI code.

### 3.4 Reference blocks

A model MAY mix inline blocks and reference blocks in the same ordered `blocks` array:

```json
[
  {"id": "b1", "type": "text", "content": "Inline content"},
  {"id": "b2", "ref": "opaque-reference"}
]
```

A reference block MUST contain exactly `id` and `ref`, both non-empty strings. It MUST NOT contain `type`, `content`, `parent_id`, `group_id`, or other inline fields. A block MUST NOT combine a reference and an inline body. Block IDs MUST be unique across both forms; array position, not the reference key, determines order. Multiple blocks MAY use the same reference key; the application resolves each using its model context and block ID.

`ref` is an opaque key. The application selected by `biz` owns its interpretation, association, storage, access, and lifetime. AgentUE MUST NOT interpret it as a URL, prescribe a database layout, or load it from the reducer. When to externalize blocks, including count and byte thresholds, is application policy.

Resolution MUST produce one complete inline block with the same `id`. Applications MUST reject mismatched IDs and results containing another `ref`. Resolved `type`, hierarchy, grouping, and body come from that inline block; there is no overlay or field-merging rule. Renderers needing those fields MUST resolve the reference first. A failed resolution MUST NOT be treated as an empty body.

A pure reducer preserves references on `start` and whole-block `set`. Before applying a field-level `set` or `append` to a reference block, the application MUST materialize its current inline body. The reducer MUST reject field patches targeting unresolved references without modifying the snapshot. Metadata and updates to other blocks do not require resolution. Loading content is not an additional patch event and does not advance `seq`.

Applications MUST make resolved content consistent with the snapshot and subsequent patch sequence. An opaque reference alone does not guarantee a historical snapshot: applications that replay old snapshots must retain the referenced content for those snapshots or materialize it before replay. Async consumers must coordinate loading with incoming patches to avoid duplicate appends or lost updates.

### 3.5 Model versions

New models SHOULD use `version: "1.1"`; reference blocks require 1.1. SDK readers also accept existing `version: "1.0"` models containing inline blocks, preserving their version and using the same reducer. SDK emitters default to 1.1 when constructing new models. A producer MUST NOT send references to a consumer that only understands inline blocks; the application can materialize them into a 1.0 model for that consumer. Version support does not supply a reference resolver.

## 4. Patch event

Every event uses the following envelope:

```json
{
  "op": "append",
  "seq": 2,
  "mask": "block.content",
  "event_type": "message.delta",
  "block": {
    "id": "answer",
    "type": "text",
    "content": "Hello"
  }
}
```

| Field | Type | Requirement | Meaning |
| --- | --- | --- | --- |
| `op` | string | REQUIRED | Operation defined in section 5. |
| `seq` | non-negative integer | REQUIRED | Position in the model's ordered event timeline. |
| `ts` | integer | OPTIONAL | Unix time in milliseconds. |
| `mask` | string | OP-SPECIFIC | Field path affected by the operation. |
| `event_type` | string | OPTIONAL | Domain hint for observers or renderers; it does not change reducer semantics. |
| `model` | object | OP-SPECIFIC | Complete model, used by `start`. |
| `meta` | object | OP-SPECIFIC | Metadata patch payload. |
| `block` | object | OP-SPECIFIC | Block patch payload. |

Only `op` and the relevant payload slot determine state transition semantics. Consumers MUST NOT require `event_type` to apply a patch.

### 4.1 Sequence semantics

Persisted, non-heartbeat events in one model timeline MUST have increasing `seq` values. A `ping` carries the latest known `seq`, does not advance the timeline, and can therefore repeat a value.

A reconstructed `start` sent during resume represents all state through its `seq`. The next state-changing event MUST have a greater value. Transport cursors, such as an SSE `id`, are separate from `seq`.

## 5. Operations

AgentUE divides operations by responsibility:

| Operation | Category | Changes state | Meaning |
| --- | --- | --- | --- |
| `start` | control + data | yes | Establishes or replaces the complete model. |
| `set` | data | yes | Creates or replaces a block or a selected field. |
| `append` | data | yes | Appends a string or list delta to a block field. |
| `error` | control + data | yes | Sets `meta.error` and signals failure. |
| `ping` | control | no | Keeps a live delivery active. |
| `end` | control | no | Ends a delivery normally or after an error. |

Every delivery stream MUST begin with `start` and MUST end with `end`. If a terminal failure occurs, `error` MUST appear before `end`.

### 5.1 `start`

`start` MUST contain `model` and MUST NOT contain `meta` or `block`. A consumer replaces its entire local model with this payload.

```json
{
  "op": "start",
  "seq": 1,
  "model": {
    "version": "1.1",
    "biz": "chat",
    "meta": {},
    "blocks": []
  }
}
```

### 5.2 `set`

Without `mask`, `set` MUST carry a complete inline block or reference block. The reducer replaces the block with the same `id`, or appends it if no matching block exists. Replacement MAY switch between inline and reference forms or change a reference key; an existing block keeps its array position.

```json
{
  "op": "set",
  "seq": 2,
  "block": {
    "id": "stage",
    "type": "stage",
    "stage": "working"
  }
}
```

With `mask`, the first path segment selects the payload slot and target:

- `meta.<path>` reads the value from the corresponding path in `meta`.
- `block.<path>` selects a block by `block.id` and reads the value from the corresponding path in `block`.

```json
{
  "op": "set",
  "seq": 3,
  "mask": "meta.stats",
  "meta": {
    "stats": {"status": "running"}
  }
}
```

```json
{
  "op": "set",
  "seq": 4,
  "mask": "block.tool.status",
  "block": {
    "id": "tool-1",
    "tool": {"status": "completed"}
  }
}
```

`set` MAY assign JSON `null`; null is a value, not an instruction to ignore the patch. Field patches MUST NOT change `block.id` or set `block.ref` (including nested paths). Reference creation, replacement, and materialization use whole-block replacement; an unresolved reference cannot receive a field patch.

### 5.3 `append`

`append` MUST use a `block.<field>` mask and MUST carry `block.id`. The selected value MUST be a string or array.

- Strings are concatenated.
- Arrays are concatenated in event order.
- If the block does not exist, the reducer inserts the supplied block payload. In this case the payload MUST be a complete valid inline block.
- `append` MUST NOT target `block.id` or `block.ref`, or carry a reference block payload. An existing reference MUST be materialized before appending.

```json
{
  "op": "append",
  "seq": 5,
  "mask": "block.content",
  "block": {
    "id": "answer",
    "type": "text",
    "content": "world"
  }
}
```

Deduplication, ranking, numbering, and other domain rules MUST be completed before emitting an append event. The generic reducer only concatenates values.

### 5.4 `error`

`error` is the lifecycle-aware equivalent of setting `meta.error`. It MUST contain `mask: "meta.error"` and an error object in `meta.error`.

```json
{
  "op": "error",
  "seq": 6,
  "mask": "meta.error",
  "meta": {
    "error": {
      "code": "upstream_unavailable",
      "message": "The request could not be completed."
    }
  }
}
```

### 5.5 `ping`

`ping` does not change the model. It SHOULD contain `ts` and repeats the emitter's current `seq`.

### 5.6 `end`

`end` does not change the model. It is always the final protocol event in a delivery stream.

## 6. Replay and snapshots

The reducer is deterministic and independent of storage. For models containing references, the application must also satisfy the resolution consistency rules in section 3.4:

```text
snapshot(n) = reduce(start.model, patches[1..n])
```

An application MAY persist the complete model, the ordered event log, or both.

For resume:

1. Reconstruct or load the model covered by the requested cursor.
2. Send a new `start` containing that complete model and the highest covered `seq`.
3. Continue with events whose `seq` is greater than the reconstructed `start.seq`.
4. Finish with `end`.

The client handles first delivery and resumed delivery identically: `start` always replaces its local model.

## 7. Extension rules

- New `biz` values and block types MAY be introduced without changing the core version.
- New metadata and block fields MAY be introduced compatibly; consumers MUST preserve unknown fields.
- A new operation changes reducer semantics and therefore requires a protocol revision.
- Existing operation semantics MUST NOT be redefined within the same protocol version.
- Incompatible changes to the complete model require a new `version` value.

## 8. Security and size considerations

- Treat all text and URLs as untrusted data; renderers MUST escape or sanitize them for their target platform.
- Block payloads can contain tool output or traces. Producers SHOULD redact secrets before emitting or persisting events.
- Transports and intermediaries impose message-size limits. Producers SHOULD split large string and array fields across multiple `append` events.
- Consumers SHOULD impose application-appropriate limits on event size, block count, and accumulated content.

