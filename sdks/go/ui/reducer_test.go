package ui

import (
	"encoding/json"
	"os"
	"reflect"
	"testing"
)

type conformanceFixture struct {
	Cases []struct {
		Name     string            `json:"name"`
		Initial  map[string]any    `json:"initial"`
		Events   []json.RawMessage `json:"events"`
		Expected map[string]any    `json:"expected"`
	} `json:"cases"`
}

func TestReducerConformance(t *testing.T) {
	data, err := os.ReadFile("../../../conformance/cases/state-transitions.json")
	if err != nil {
		t.Fatal(err)
	}
	var fixture conformanceFixture
	if err := json.Unmarshal(data, &fixture); err != nil {
		t.Fatal(err)
	}
	for _, testCase := range fixture.Cases {
		t.Run(testCase.Name, func(t *testing.T) {
			snapshot := testCase.Initial
			for _, data := range testCase.Events {
				event, err := Parse(data)
				if err != nil {
					t.Fatal(err)
				}
				snapshot, err = Apply(snapshot, event)
				if err != nil {
					t.Fatal(err)
				}
			}
			if !reflect.DeepEqual(snapshot, testCase.Expected) {
				t.Fatalf("snapshot mismatch\nwant: %#v\n got: %#v", testCase.Expected, snapshot)
			}
		})
	}
}

func TestParseRejectsUnknownFields(t *testing.T) {
	_, err := Parse([]byte(`{"op":"end","seq":1,"unknown":true}`))
	if err == nil {
		t.Fatal("expected unknown field to be rejected")
	}
}
