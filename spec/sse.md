# AgentUE SSE Binding 1.0

This document defines how AgentUE JSON events are carried over Server-Sent Events (SSE). The core event semantics remain defined by [the AgentUE protocol](protocol.md).

## 1. Response

An SSE endpoint MUST return:

```http
Content-Type: text/event-stream
Cache-Control: no-cache
```

The response body is UTF-8. Each AgentUE event is encoded as one SSE message whose `data` value is one complete JSON object:

```text
data: {"op":"ping","seq":4,"ts":1770000000000}

```

The blank line terminates the SSE message. A producer MAY split JSON across multiple SSE `data:` lines when required by its SSE library; consumers concatenate those lines with newline characters before parsing JSON.

## 2. Event identity

An implementation MAY include an SSE `id` field:

```text
id: 1740000000000-2
data: {"op":"append","seq":5,"mask":"block.content","block":{"id":"answer","content":"hi"}}

```

The SSE `id` is a transport or storage cursor. It is intentionally separate from AgentUE `seq`:

- `seq` orders model transitions.
- `id` locates a record in a delivery mechanism or event store.

Clients SHOULD send the last successfully applied transport cursor when requesting resume. The request mechanism is application-defined; it may use the standard `Last-Event-ID` header or an explicit API field.

## 3. Lifecycle

Every newly delivered SSE response MUST begin with an AgentUE `start` event, including resumed responses. The response MUST finish with `end`; a terminal error is sent as `error` followed by `end`.

An application SHOULD emit `ping` when the connection is otherwise idle. The interval is deployment-specific and is not part of the protocol.

## 4. Boundaries

The SSE binding is responsible only for framing JSON events. It does not define:

- HTTP endpoint paths or methods
- authentication or authorization
- task creation and cancellation APIs
- event-log retention
- retry policy
- renderer behavior

These concerns belong to the host application.

