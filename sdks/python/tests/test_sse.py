import json

import pytest

from agentue.ui import PatchEvent, encode_sse


def test_encode_sse_with_transport_cursor():
    message = encode_sse(PatchEvent(op="ping", seq=3, ts=123), event_id="cursor-1")

    assert message == 'id: cursor-1\ndata: {"op":"ping","seq":3,"ts":123}\n\n'


def test_encode_sse_splits_multiline_data():
    assert encode_sse("line-1\nline-2") == "data: line-1\ndata: line-2\n\n"


def test_encode_sse_rejects_multiline_event_id():
    with pytest.raises(ValueError, match="must not contain newlines"):
        encode_sse('{"op":"ping","seq":0}', event_id="bad\nid")


def test_logical_stream_is_independent_of_transport_cursor():
    raw = encode_sse(PatchEvent(op="ping", seq=3, stream_id="message-123"), event_id="cursor-1")
    assert raw.startswith("id: cursor-1\n")
    payload = json.loads(raw.split("data: ", 1)[1])
    assert payload["stream_id"] == "message-123"
    assert payload["seq"] == 3
