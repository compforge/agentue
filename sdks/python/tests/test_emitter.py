import json

from agentue.ui import BaseBlock, ModelMeta, PatchEmitter, UIModel, extract_patch_op


def test_emitter_preserves_domain_fields_and_orders_events():
    emitter = PatchEmitter()
    model = UIModel(
        biz="chat",
        meta=ModelMeta(session_id="session-1"),
        blocks=[BaseBlock(id="stage", type="stage", stage="starting")],
    )

    start = json.loads(emitter.start(model))
    ping = json.loads(emitter.ping())
    append = json.loads(
        emitter.block_append(
            BaseBlock(id="answer", type="text", content="hello", group_id="turn-1"),
            event_type="message.delta",
        )
    )
    end = json.loads(emitter.end())

    assert start["seq"] == 1
    assert start["model"]["meta"]["session_id"] == "session-1"
    assert start["model"]["blocks"][0]["stage"] == "starting"
    assert ping["seq"] == 1
    assert append["seq"] == 2
    assert append["event_type"] == "message.delta"
    assert append["block"]["group_id"] == "turn-1"
    assert end["seq"] == 3


def test_reconstructed_start_uses_covered_sequence():
    emitter = PatchEmitter()
    model = UIModel(biz="chat", meta=ModelMeta())

    start = json.loads(emitter.start(model, seq=8))
    append = json.loads(emitter.block_append(BaseBlock(id="answer", type="text", content="next")))

    assert start["seq"] == 8
    assert append["seq"] == 9


def test_targeted_block_set_can_assign_null():
    emitter = PatchEmitter(start_offset=2)

    event = json.loads(
        emitter.block_set(
            BaseBlock(id="tool", type="tool", result=None),
            mask="block.result",
        )
    )

    assert event["block"]["result"] is None


def test_error_has_no_implicit_tracing_dependency():
    event = json.loads(PatchEmitter().error("failed", "Request failed", detail="upstream timeout"))

    assert event["meta"]["error"] == {
        "code": "failed",
        "message": "Request failed",
        "detail": "upstream timeout",
    }


def test_extract_patch_op_is_tolerant():
    assert extract_patch_op('{"op":"set","seq":1}') == "set"
    assert extract_patch_op("not-json") is None
