import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from agentue.ui import BaseBlock, PatchEmitter, PatchEvent, ReferenceBlock, UIModel, apply_patch, apply_patches

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = json.loads((ROOT / "conformance/cases/block-references.json").read_text())
SCHEMA = json.loads((ROOT / "schema/v1/model.schema.json").read_text())


@pytest.mark.parametrize("case", FIXTURE["invalid_models"], ids=lambda case: case["name"])
def test_invalid_reference_models(case):
    assert not Draft202012Validator(SCHEMA).is_valid(case["model"])
    with pytest.raises(ValidationError):
        UIModel.model_validate(case["model"])
    with pytest.raises(ValidationError):
        PatchEvent(op="start", seq=1, model=case["model"])


@pytest.mark.parametrize("case", FIXTURE["rejected_updates"], ids=lambda case: case["name"])
def test_reference_update_rejected_without_mutation(case):
    snapshot = copy.deepcopy(case["initial"])
    with pytest.raises((ValueError, TypeError)):
        apply_patch(snapshot, case["event"])
    assert snapshot == case["initial"]


def test_typed_reference_emit_and_materialize():
    reference = ReferenceBlock(id="b2", ref="not/a/url")
    model = UIModel(biz="chat", meta={}, blocks=[reference])
    assert model.version == "1.1"
    assert model.model_dump(exclude_none=True)["blocks"] == [{"id": "b2", "ref": "not/a/url"}]
    emitter = PatchEmitter()
    snapshot = apply_patches({}, [emitter.start(model), emitter.block_set(reference)])
    # The application has loaded the referenced block and checked its ID before replacement.
    snapshot = apply_patches(
        snapshot,
        [
            emitter.block_set(BaseBlock(id="b2", type="text", content="Hello")),
            emitter.block_append(BaseBlock(id="b2", type="text", content=" world")),
        ],
    )
    assert snapshot["blocks"] == [{"id": "b2", "type": "text", "content": "Hello world"}]


def test_model_rejects_duplicate_inline_and_reference_ids():
    with pytest.raises(ValidationError, match="duplicate block id"):
        UIModel(biz="chat", meta={}, blocks=[BaseBlock(id="b2", type="text"), ReferenceBlock(id="b2", ref="x")])


def test_legacy_model_reads_without_changing_its_version():
    model = UIModel.model_validate(
        {
            "version": "1.0",
            "biz": "chat",
            "meta": {},
            "blocks": [
                {"id": "b1", "type": "text", "content": "old data"},
            ],
        }
    )
    snapshot = apply_patch({}, PatchEmitter().start(model))
    assert snapshot["version"] == "1.0"
    assert snapshot["blocks"][0]["content"] == "old data"
