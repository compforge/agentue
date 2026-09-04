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
