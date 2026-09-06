"""Stateful agent-to-UI event models, reducers, emitters, and SSE binding."""

from agentue.apply import PatchInput, apply_patch, apply_patches
from agentue.emitter import PatchEmitter, SSEEmitter
from agentue.event import PatchEvent, PatchOp, extract_patch_op
from agentue.model import PROTOCOL_VERSION, BaseBlock, ErrorInfo, GroupedBlock, ModelMeta, ReferenceBlock, UIModel
from agentue.sse import encode_sse

__all__ = (
    "PROTOCOL_VERSION",
    "BaseBlock",
    "ErrorInfo",
    "GroupedBlock",
    "ModelMeta",
    "ReferenceBlock",
    "PatchEmitter",
    "PatchEvent",
    "PatchInput",
    "PatchOp",
    "SSEEmitter",
    "UIModel",
    "apply_patch",
    "apply_patches",
    "encode_sse",
    "extract_patch_op",
)
