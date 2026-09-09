# Storage framing

Framing bounds physical content without limiting the size or changing the identity
of a logical AgentUE block. It is an optional encoding used by a host's storage
layer, not a new UI operation or a persistence framework.

The Go `storage` package exposes two functions:

- `Frame(block, maxBytes)` returns self-describing frame blocks with distinct IDs.
- `Unframe(frames)` validates and restores one complete inline block, accepting any
  input order and imposing no size limit on the restored content.

The [frame convention](../spec/protocol.md#built-in-technical-type-frame) carries the
original block ID, fragment sequence, total and JSON string data. Splitting preserves
the original JSON bytes and valid UTF-8 boundaries. Every encoded frame, including
its fields and JSON escaping, fits the supplied byte budget. A budget too small for
the envelope and the next character fails explicitly. Callers reserve any enclosing
container overhead before calling `Frame`; there is no fixed protocol byte limit.

## Host responsibilities

The host owns Message/Part IDs, associations, transactions, access control and
cleanup. It must store or replace a complete frame group atomically with the owning
revision. `total` detects missing fragments, not mixing different revisions. Missing
content or failed reassembly is an error, never an empty or partially decoded block.

Store small blocks directly and frame large blocks as needed. Grouping by logical
block lets a host update that block without rewriting every block in its Message.
Root metadata and reference directories need their own bounded-storage policy;
block framing alone cannot guarantee the size of the root record.

The helpers perform no I/O, assign no database schema, and implement no SSE
fragmentation or automatic client-side frame buffering. Ordinary UI events remain
unchanged. A storage consumer restores logical blocks before exposing them to its
API, runtime or renderer.
