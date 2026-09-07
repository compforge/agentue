import json
from pathlib import Path

from jsonschema import Draft202012Validator

from agentue.ui import PatchEvent, apply_patches

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _load_json(relative_path: str) -> dict:
    return json.loads((REPOSITORY_ROOT / relative_path).read_text())


def test_shared_state_transition_cases():
    fixture = _load_json("conformance/cases/state-transitions.json")
    event_schema = _load_json("schema/v1/patch-event.schema.json")
    model_schema = _load_json("schema/v1/model.schema.json")
    event_validator = Draft202012Validator(event_schema)
    model_validator = Draft202012Validator(model_schema)

    for case in fixture["cases"]:
        for event in case["events"]:
            event_validator.validate(event)
            if event["op"] == "start":
                model_validator.validate(event["model"])

        result = apply_patches(case["initial"], case["events"])

        assert result == case["expected"], case["name"]
        model_validator.validate(result)


def test_optional_stream_addressing():
    fixture = _load_json("conformance/cases/stream-addressing.json")
    validator = Draft202012Validator(_load_json("schema/v1/patch-event.schema.json"))
    streams = {}
    for raw in fixture["events"]:
        validator.validate(raw)
        event = PatchEvent.model_validate(raw)
        encoded = json.loads(event.to_json())
        assert encoded == raw
        stream_id = event.stream_id or ""
        streams[stream_id] = apply_patches(streams.get(stream_id, {}), [encoded])
    assert streams == fixture["expected"]
