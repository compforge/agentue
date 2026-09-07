"""AgentUE patch event envelope and validation."""

import json
from enum import Enum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agentue.model import UIModel, validate_block


class PatchOp(str, Enum):
    """Operations defined by AgentUE 1.1."""

    START = "start"
    SET = "set"
    APPEND = "append"
    ERROR = "error"
    PING = "ping"
    END = "end"


class PatchEvent(BaseModel):
    """One ordered AgentUE event."""

    model_config = ConfigDict(extra="forbid")

    op: PatchOp
    seq: int = Field(..., ge=0)
    stream_id: str | None = Field(default=None, strict=True)
    ts: int | None = Field(default=None, ge=0)
    mask: str | None = None
    event_type: str | None = None
    model: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None
    block: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_operation(self) -> Self:
        """Keep invalid payload-slot combinations out of event logs."""
        if self.op is PatchOp.START:
            if self.model is None:
                raise ValueError("start event requires model")
            if self.meta is not None or self.block is not None:
                raise ValueError("start event only accepts model")
            UIModel.model_validate(self.model)
            return self

        if self.model is not None:
            raise ValueError("model is only allowed for start event")

        if self.op is PatchOp.SET:
            if (self.meta is None) == (self.block is None):
                raise ValueError("set event requires exactly one of meta or block")
            if self.mask is None and self.block is None:
                raise ValueError("set event without mask requires block")
            if self.mask is not None:
                expected_root = "meta." if self.meta is not None else "block."
                if not self.mask.startswith(expected_root):
                    raise ValueError(f"set mask must start with {expected_root!r}")
            if self.block is not None:
                if self.mask is None:
                    validate_block(self.block)
                else:
                    _validate_block_field_patch(self.mask, self.block)
            return self

        if self.op is PatchOp.APPEND:
            if self.block is None:
                raise ValueError("append event requires block")
            if self.meta is not None:
                raise ValueError("append event does not accept meta")
            if not self.mask or not self.mask.startswith("block."):
                raise ValueError("append mask must match 'block.<field>'")
            _validate_block_field_patch(self.mask, self.block)
            return self

        if self.op is PatchOp.ERROR:
            if self.mask != "meta.error" or not isinstance((self.meta or {}).get("error"), dict):
                raise ValueError("error event requires mask='meta.error' and meta.error")
            if self.block is not None:
                raise ValueError("error event does not accept block")
            return self

        if self.meta is not None or self.block is not None or self.mask is not None:
            raise ValueError(f"{self.op.value} event does not accept state payloads")

        return self

    def to_json(self) -> str:
        """Serialize as compact UTF-8 JSON without transport framing."""
        payload = self.model_dump(mode="json", exclude_none=True)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _validate_block_field_patch(mask: str, block: dict[str, Any]) -> None:
    if "ref" in block:
        raise ValueError("reference blocks require whole-block set")
    if mask.split(".")[1] in ("id", "ref"):
        raise ValueError("block id and ref cannot be patched; use whole-block set for references")


def extract_patch_op(event_json: str) -> str | None:
    """Extract ``op`` without validating or fully materializing a patch event."""
    try:
        payload = json.loads(event_json)
    except json.JSONDecodeError:
        return None
    op = payload.get("op") if isinstance(payload, dict) else None
    return op if isinstance(op, str) else None
