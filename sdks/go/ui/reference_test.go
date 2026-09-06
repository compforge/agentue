package ui

import (
	"encoding/json"
	"os"
	"reflect"
	"testing"
)

func TestBlockReferences(t *testing.T) {
	data, err := os.ReadFile("../../../conformance/cases/block-references.json")
	if err != nil {
		t.Fatal(err)
	}
	var fixture struct {
		InvalidModels []struct {
			Name  string
			Model map[string]any
		} `json:"invalid_models"`
		RejectedUpdates []struct {
			Name    string
			Initial map[string]any
			Event   json.RawMessage
		} `json:"rejected_updates"`
	}
	if err := json.Unmarshal(data, &fixture); err != nil {
		t.Fatal(err)
	}
	for _, tc := range fixture.InvalidModels {
		t.Run(tc.Name, func(t *testing.T) {
			if err := ValidateModel(tc.Model); err == nil {
				t.Fatal("expected invalid model error")
			}
			if err := (Event{Op: OpStart, Seq: 1, Model: tc.Model}).Validate(); err == nil {
				t.Fatal("expected invalid start error")
			}
		})
	}
	for _, tc := range fixture.RejectedUpdates {
		t.Run(tc.Name, func(t *testing.T) {
			snapshot, err := cloneMap(tc.Initial)
			if err != nil {
				t.Fatal(err)
			}
			event, err := Parse(tc.Event)
			if err == nil {
				_, err = Apply(snapshot, event)
			}
			if err == nil {
				t.Fatal("expected invalid update error")
			}
			if !reflect.DeepEqual(snapshot, tc.Initial) {
				t.Fatalf("rejected update mutated snapshot: %#v", snapshot)
			}
		})
	}
}

func TestModelRejectsDuplicateBlockIdentities(t *testing.T) {
	model := map[string]any{"version": ProtocolVersion, "biz": "chat", "meta": map[string]any{}, "blocks": []any{
		map[string]any{"id": "b2", "type": "text"}, map[string]any{"id": "b2", "ref": "x"},
	}}
	if err := ValidateModel(model); err == nil {
		t.Fatal("expected duplicate ID error")
	}
}
