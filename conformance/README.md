# Conformance fixtures

Files in `cases/` are language-neutral reducer fixtures. Every SDK SHOULD run the same cases.

`state-transitions.json` contains successful transitions. Each case contains:

- `initial`: the model state before applying events
- `events`: ordered AgentUE patch objects
- `expected`: the exact state after reduction

`block-references.json` contains shared `invalid_models` and `rejected_updates`.
Invalid models must fail model/start validation (and the model JSON Schema).
Each rejected update contains `initial` and `event`; every reducer must reject it
without changing `initial`. Cases cover malformed references, unresolved field
patches, and reference/identity mutation. Original 1.0 transition cases remain as
compatibility coverage alongside the new 1.1 mixed-block cases.

The Python, TypeScript, and Go SDKs all run these fixtures from their native test suites.

`stream-addressing.json` interleaves named and unnamed streams. Tests route each
event to a separate single-model reducer, round-trip the optional identifier,
and compare the final model per stream. Equal sequence/block IDs, a stream ending
while another continues, and resuming one stream must not affect other streams.
