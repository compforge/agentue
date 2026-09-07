"""Deterministic AgentUE reducer used for live updates and replay."""

import copy
from collections.abc import Iterable, Mapping
from typing import Any, TypeAlias

from agentue.event import PatchEvent, PatchOp
from agentue.model import PROTOCOL_VERSION, validate_block

PatchInput: TypeAlias = str | Mapping[str, Any] | PatchEvent
_MISSING = object()


def apply_patch(snapshot: dict[str, Any], patch: PatchInput) -> dict[str, Any]:
    """Apply one event to ``snapshot`` and return the resulting state.

    Incremental operations mutate and return ``snapshot``. ``start`` returns a
    new state because its model replaces the previous state completely.
    Multiplexing callers route by ``stream_id`` first; this reducer handles one model.
    """
    event = _coerce_event(patch)

    if event.op is PatchOp.START:
        return copy.deepcopy(event.model or snapshot)
    if event.op is PatchOp.SET:
        return _apply_set(snapshot, event)
    if event.op is PatchOp.ERROR:
        return _set_by_mask(snapshot, "meta.error", event.meta or {})
    if event.op is PatchOp.APPEND:
        return _apply_append(snapshot, event)

    return snapshot


def apply_patches(snapshot: dict[str, Any], patches: Iterable[PatchInput]) -> dict[str, Any]:
    """Apply an ordered event sequence."""
    for patch in patches:
        snapshot = apply_patch(snapshot, patch)
    return snapshot


def _coerce_event(patch: PatchInput) -> PatchEvent:
    if isinstance(patch, PatchEvent):
        return patch
    if isinstance(patch, str):
        return PatchEvent.model_validate_json(patch)
    return PatchEvent.model_validate(dict(patch))


def _apply_set(snapshot: dict[str, Any], event: PatchEvent) -> dict[str, Any]:
    if event.mask is None:
        _upsert_block(snapshot, event.block or {})
        return snapshot

    source = event.meta if event.meta is not None else event.block
    return _set_by_mask(snapshot, event.mask, source or {})


def _apply_append(snapshot: dict[str, Any], event: PatchEvent) -> dict[str, Any]:
    mask = event.mask or ""
    field = mask.removeprefix("block.")
    if not field or "." in field:
        raise ValueError(f"unsupported append mask: {mask!r}; expected 'block.<field>'")

    block_data = event.block or {}
    block_id = block_data.get("id")
    if not isinstance(block_id, str) or not block_id:
        raise ValueError("append block requires a non-empty id")
    if field not in block_data:
        raise ValueError(f"append block does not contain field {field!r}")

    new_value = block_data[field]
    if not isinstance(new_value, (str, list)):
        raise TypeError(f"append field {field!r} must be a string or list")

    blocks = snapshot.setdefault("blocks", [])
    for existing in blocks:
        if existing.get("id") != block_id:
            continue
        _require_inline_block(existing)
        old_value = existing.get(field)
        if old_value is None:
            existing[field] = copy.deepcopy(new_value)
        elif isinstance(old_value, str) and isinstance(new_value, str):
            existing[field] = old_value + new_value
        elif isinstance(old_value, list) and isinstance(new_value, list):
            existing[field] = old_value + copy.deepcopy(new_value)
        else:
            raise TypeError(f"append field {field!r} has incompatible value types")
        return snapshot

    if not isinstance(block_data.get("type"), str) or not block_data["type"]:
        raise ValueError("append for a missing block requires a complete block with type")
    validate_block(block_data)
    blocks.append(copy.deepcopy(block_data))
    return snapshot


def _upsert_block(snapshot: dict[str, Any], block_data: dict[str, Any]) -> None:
    block_id = block_data.get("id")
    if not isinstance(block_id, str) or not block_id:
        raise ValueError("set block requires a non-empty id")
    validate_block(block_data)
    if "ref" in block_data and snapshot.get("version") != PROTOCOL_VERSION:
        raise ValueError("reference blocks require model version 1.1")

    blocks = snapshot.setdefault("blocks", [])
    for index, existing in enumerate(blocks):
        if existing.get("id") == block_id:
            blocks[index] = copy.deepcopy(block_data)
            return
    blocks.append(copy.deepcopy(block_data))


def _set_by_mask(snapshot: dict[str, Any], mask: str, source: dict[str, Any]) -> dict[str, Any]:
    root, separator, relative_path = mask.partition(".")
    if not separator or not relative_path:
        raise ValueError(f"invalid set mask: {mask!r}")
    path = relative_path.split(".")
    value = _read_path(source, path)
    if value is _MISSING:
        raise ValueError(f"payload does not contain masked value: {mask!r}")

    if root == "meta":
        target = snapshot.setdefault("meta", {})
    elif root == "block":
        block_id = source.get("id")
        target = next((block for block in snapshot.get("blocks", []) if block.get("id") == block_id), None)
        if target is None:
            raise ValueError(f"target block does not exist: {block_id!r}")
        _require_inline_block(target)
    else:
        raise ValueError(f"unsupported set mask root: {root!r}")

    _write_path(target, path, value)
    return snapshot


def _require_inline_block(block: dict[str, Any]) -> None:
    # spec: A pure reducer cannot append to unknown external content.
    if "ref" in block:
        raise ValueError(f"unresolved reference block {block.get('id')!r}; materialize before field patches")


def _read_path(source: dict[str, Any], path: list[str]) -> Any:
    current: Any = source
    for part in path:
        if not isinstance(current, dict) or part not in current:
            # Accept the original flat leaf payload shape for compatibility.
            return source.get(path[-1], _MISSING)
        current = current[part]
    return current


def _write_path(target: dict[str, Any], path: list[str], value: Any) -> None:
    current = target
    for part in path[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[path[-1]] = copy.deepcopy(value)
