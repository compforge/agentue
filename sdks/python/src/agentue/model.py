"""Semantic model types for AgentUE."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SerializeAsAny

PROTOCOL_VERSION = "1.0"


class BaseBlock(BaseModel):
    """Minimum block contract.

    Additional fields are preserved so domain-specific block types can evolve
    independently from the protocol core.
    """

    model_config = ConfigDict(extra="allow")

    id: str = Field(..., min_length=1, description="Block ID, unique within the model")
    type: str = Field(..., min_length=1, description="Domain-defined semantic block type")
    parent_id: str | None = Field(default=None, description="Parent block ID for nesting or ownership")


class GroupedBlock(BaseBlock):
    """A block that can be associated with a peer execution or visual group."""

    group_id: str | None = Field(default=None, description="Peer group identity")


class ErrorInfo(BaseModel):
    """Structured error carried by ``meta.error``."""

    model_config = ConfigDict(extra="allow")

    code: str
    message: str
    detail: str | None = None
    trace_id: str | None = None


class ModelMeta(BaseModel):
    """Common metadata plus domain-defined extension fields."""

    model_config = ConfigDict(extra="allow")

    error: ErrorInfo | None = None
    task_id: str | None = None
    trace_id: str | None = None
    stats: dict[str, Any] | None = None


class UIModel(BaseModel):
    """Complete semantic state consumed by a UI renderer."""

    model_config = ConfigDict(extra="allow")

    version: str = PROTOCOL_VERSION
    biz: str = Field(..., min_length=1, description="Domain identifier")
    meta: SerializeAsAny[ModelMeta]
    blocks: list[SerializeAsAny[BaseBlock]] = Field(default_factory=list)
