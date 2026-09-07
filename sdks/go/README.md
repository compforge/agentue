# AgentUE Go SDK

The Go SDK contains two small packages:

- `ui` implements AgentUE events, validation, and deterministic reduction.
- `runner` provides a Redis Streams event bridge and resumable delivery.

The Go `runner` package currently exposes transport and reconstruction building
blocks. The Python SDK additionally provides the four-callback execution owner,
heartbeat scanner, and event-loop watchdog. A Go host therefore owns execution
and recovery policy while reusing AgentUE's event timeline.

The Redis bridge accepts an existing `redis.UniversalClient`; the application
owns connection configuration and shutdown. This keeps AgentUE independent of
the host service's Redis topology while allowing separate producer and consumer
instances to share one task timeline.

```go
bridge := runner.NewRedisEventBridge(redisClient, runner.BridgeOptions{
    KeyPrefix: "myapp:agentue",
    TaskTTL:   24 * time.Hour,
})

replayer := runner.Replayer{Bridge: bridge}
err := replayer.Stream(ctx, taskID, lastEventID, func(event runner.Delivery) error {
    return writeSSE(event.Cursor, event.Data)
})
```

Applications retain ownership of task creation, authorization, durable business
state, and HTTP routing. AgentUE owns the event protocol, Redis delivery state,
and reconstruction of a full `start` model when a client resumes.

## Optional stream addressing

Set `event.StreamID = "message-123"` to address a logical stream, or leave it empty
for single-stream use. When multiplexing, route by StreamID before calling
`ui.Apply`; each stream keeps its own snapshot and sequence.
Runner/Replayer still operates on one stored timeline; a host can attach StreamID
to its deliveries, including reconstructed snapshots, when aggregating them.
See [logical stream addressing](../../spec/protocol.md#42-optional-logical-stream-addressing).

## Reference blocks

Protocol 1.1 accepts a mixed ordered list of inline `{id, type, ...}` blocks and
reference `{id, ref}` blocks. Existing 1.0 inline snapshots remain readable.
`ref` is an opaque key interpreted by the application selected by `biz`; reference
blocks carry no `type` or body. Whole-block `set` creates or replaces either form.
The application must load and check the referenced block's ID before field-level
`set` or `append`; the pure reducer rejects unresolved targets without loading.
See the [protocol](../../spec/protocol.md#34-reference-blocks) for the full contract.

Use `ui.ProtocolVersion` for new models. `ui.ValidateBlock` accepts either block
form; `ui.ValidateModel` checks model versions and unique block IDs. These checks
also run when parsing or applying a `start` event; whole-block `set` validates its
block representation. Blocks remain JSON maps, as in the existing Go API.
