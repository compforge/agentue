"""Semantic model types for AgentUE."""

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, SerializeAsAny, model_validator

PROTOCOL_VERSION = "1.1"


class BaseBlock(BaseModel):
    """Minimum block contract.

    Additional fields are preserved so domain-specific block types can evolve
    independently from the protocol core.
    """

    model_config = ConfigDict(extra="allow")

    id: str = Field(..., min_length=1, description="Block ID, unique within the model")
    type: str = Field(..., min_length=1, description="Domain-defined semantic block type")
    parent_id: str | None = Field(default=None, description="Parent block ID for nesting or ownership")

    @model_validator(mode="before")
    @classmethod
    def reject_reference(cls, value: Any) -> Any:
        if isinstance(value, dict) and "ref" in value:
            raise ValueError("inline blocks cannot contain ref")
        return value


class ReferenceBlock(BaseModel):
    """Opaque key interpreted by biz; contains no inline body or type."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    ref: str = Field(..., min_length=1)


def validate_block(value: dict[str, Any]) -> BaseBlock | ReferenceBlock:
    """Validate either complete block representation without resolving references."""
    if "ref" in value:
        return ReferenceBlock.model_validate(value)
    return BaseBlock.model_validate(value)


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

    version: Literal["1.0", "1.1"] = "1.1"
    biz: str = Field(..., min_length=1, description="Domain identifier")
    meta: SerializeAsAny[ModelMeta]
    blocks: list[SerializeAsAny[BaseBlock] | ReferenceBlock] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_blocks(self) -> Self:
        ids: set[str] = set()
        for block in self.blocks:
            if isinstance(block, ReferenceBlock) and self.version != PROTOCOL_VERSION:
                raise ValueError("reference blocks require model version 1.1")
            if block.id in ids:
                raise ValueError(f"duplicate block id: {block.id!r}")
            ids.add(block.id)
        return self
