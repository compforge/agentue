import pytest
from pydantic import ValidationError

from agentue.ui import PatchEvent


def test_start_requires_model():
    with pytest.raises(ValidationError, match="requires model"):
        PatchEvent(op="start", seq=1)


def test_set_requires_exactly_one_payload_slot():
    with pytest.raises(ValidationError, match="exactly one"):
        PatchEvent(op="set", seq=1, mask="meta.status", meta={"status": "done"}, block={"id": "x"})


def test_control_event_rejects_state_payload():
    with pytest.raises(ValidationError, match="does not accept state payloads"):
        PatchEvent(op="ping", seq=1, meta={"status": "ignored"})
