"""Ordered AgentUE patch construction."""

import time
from collections.abc import Mapping
from typing import Any

from agentue.event import PatchEvent, PatchOp
from agentue.model import BaseBlock, ReferenceBlock, UIModel


class PatchEmitter:
    """Stateful event builder that manages ``seq`` values."""

    def __init__(self, start_offset: int = 0):
        if start_offset < 0:
            raise ValueError("start_offset must be non-negative")
        self._offset = start_offset

    @property
    def offset(self) -> int:
        return self._offset

    def _next_offset(self) -> int:
        self._offset += 1
        return self._offset

    def start(self, model: UIModel, *, seq: int | None = None) -> str:
        """Create the first event in a delivery stream.

        ``seq`` can identify the highest event covered by a reconstructed
        snapshot. Without it, the emitter advances its current offset.
        """
        if seq is None:
            seq = self._next_offset()
        else:
            if seq < self._offset:
                raise ValueError("start seq cannot move the emitter backwards")
            self._offset = seq

        event = PatchEvent(
            op=PatchOp.START,
            seq=seq,
            model=model.model_dump(mode="json", exclude_none=True, serialize_as_any=True),
        )
        return event.to_json()

    def block_set(
        self, block: BaseBlock | ReferenceBlock, mask: str | None = None, *, event_type: str | None = None
    ) -> str:
        """Create or replace a block, or set one of its fields."""
        payload = block.model_dump(
            mode="json",
            exclude_none=mask is None,
            exclude_unset=mask is not None,
            serialize_as_any=True,
        )
        event = PatchEvent(
            op=PatchOp.SET,
            seq=self._next_offset(),
            mask=mask,
            event_type=event_type,
            block=payload,
        )
        return event.to_json()

    def meta_set(self, mask: str, meta: Mapping[str, Any], *, event_type: str | None = None) -> str:
        """Set a metadata field selected by ``mask``."""
        event = PatchEvent(
            op=PatchOp.SET,
            seq=self._next_offset(),
            mask=mask,
            event_type=event_type,
            meta=dict(meta),
        )
        return event.to_json()

    def block_append(
        self,
        block: BaseBlock,
        mask: str = "block.content",
        *,
        event_type: str | None = None,
    ) -> str:
        """Append a string or list field to a block."""
        event = PatchEvent(
            op=PatchOp.APPEND,
            seq=self._next_offset(),
            mask=mask,
            event_type=event_type,
            block=block.model_dump(mode="json", exclude_none=True, serialize_as_any=True),
        )
        return event.to_json()

    def error(
        self,
        code: str,
        message: str,
        *,
        trace_id: str | None = None,
        detail: str | None = None,
    ) -> str:
        """Set ``meta.error`` and signal a failed delivery."""
        error_payload: dict[str, str] = {"code": code, "message": message}
        if detail is not None and detail != message:
            error_payload["detail"] = detail
        if trace_id is not None:
            error_payload["trace_id"] = trace_id
        event = PatchEvent(
            op=PatchOp.ERROR,
            seq=self._next_offset(),
            mask="meta.error",
            meta={"error": error_payload},
        )
        return event.to_json()

    def set_stats(self, stats: Mapping[str, Any]) -> str:
        """Convenience helper for the common ``meta.stats`` extension."""
        return self.meta_set("meta.stats", {"stats": dict(stats)})

    def ping(self) -> str:
        """Create a heartbeat without advancing ``seq``."""
        return PatchEvent(op=PatchOp.PING, seq=self._offset, ts=int(time.time() * 1000)).to_json()

    def end(self) -> str:
        """Create the final event in a delivery stream."""
        return PatchEvent(op=PatchOp.END, seq=self._next_offset()).to_json()


# Compatibility name for applications migrating from an SSE-specific emitter.
SSEEmitter = PatchEmitter
