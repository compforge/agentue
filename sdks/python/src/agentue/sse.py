"""Server-Sent Events framing for AgentUE JSON events."""

from agentue.event import PatchEvent


def encode_sse(event: str | PatchEvent, *, event_id: str | None = None) -> str:
    """Encode one AgentUE event as an SSE message."""
    if event_id is not None and ("\n" in event_id or "\r" in event_id):
        raise ValueError("event_id must not contain newlines")

    payload = event.to_json() if isinstance(event, PatchEvent) else event
    lines: list[str] = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.extend(f"data: {line}" for line in payload.splitlines() or [""])
    return "\n".join(lines) + "\n\n"
