import pytest

from agentue.ui import apply_patch


def test_append_rejects_unsupported_mask():
    with pytest.raises(ValueError, match="unsupported append mask"):
        apply_patch(
            {"version": "1.0", "biz": "chat", "meta": {}, "blocks": []},
            {
                "op": "append",
                "seq": 1,
                "mask": "block.tool.content",
                "block": {"id": "tool", "type": "tool", "content": "x"},
            },
        )


def test_append_rejects_non_string_or_list_value():
    with pytest.raises(TypeError, match="must be a string or list"):
        apply_patch(
            {"version": "1.0", "biz": "chat", "meta": {}, "blocks": []},
            {
                "op": "append",
                "seq": 1,
                "mask": "block.progress",
                "block": {"id": "stage", "type": "stage", "progress": 1},
            },
        )


def test_targeted_set_requires_existing_block():
    with pytest.raises(ValueError, match="target block does not exist"):
        apply_patch(
            {"version": "1.0", "biz": "chat", "meta": {}, "blocks": []},
            {
                "op": "set",
                "seq": 1,
                "mask": "block.content",
                "block": {"id": "missing", "content": "x"},
            },
        )
