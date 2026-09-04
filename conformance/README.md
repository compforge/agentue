# Conformance fixtures

Files in `cases/` are language-neutral reducer fixtures. Every SDK SHOULD run the same cases.

Each case contains:

- `initial`: the model state before applying events
- `events`: ordered AgentUE patch objects
- `expected`: the exact state after reduction

Invalid input and model-validation behavior remain covered by SDK-specific tests until a shared error-fixture format is defined.

The Python, TypeScript, and Go SDKs all run these fixtures from their native test suites.
