package ui

import (
	"encoding/json"
	"os"
	"reflect"
	"testing"
)

// +case=`Optional stream addresses isolate equal seq/block IDs and per-stream start/end.`
func TestOptionalStreamAddressing(t *testing.T) {
	data, err := os.ReadFile("../../../conformance/cases/stream-addressing.json")
	if err != nil {
		t.Fatal(err)
	}
	var fixture struct {
		Events   []json.RawMessage         `json:"events"`
		Expected map[string]map[string]any `json:"expected"`
	}
	if err := json.Unmarshal(data, &fixture); err != nil {
		t.Fatal(err)
	}
	streams := map[string]map[string]any{}
	for _, raw := range fixture.Events {
		event, err := Parse(raw)
		if err != nil {
			t.Fatal(err)
		}
		encoded, err := event.Marshal()
		if err != nil {
			t.Fatal(err)
		}
		var before, after map[string]any
		if err := json.Unmarshal(raw, &before); err != nil {
			t.Fatal(err)
		}
		if err := json.Unmarshal(encoded, &after); err != nil {
			t.Fatal(err)
		}
		if !reflect.DeepEqual(before, after) {
			t.Fatalf("round-trip changed event: %s / %s", raw, encoded)
		}
		streams[event.StreamID], err = Apply(streams[event.StreamID], event)
		if err != nil {
			t.Fatal(err)
		}
	}
	if !reflect.DeepEqual(streams, fixture.Expected) {
		t.Fatalf("cross-stream state mismatch: %#v", streams)
	}
}

func TestStreamIDRejectsNonString(t *testing.T) {
	for _, value := range []string{"7", "false", "[]", "{}"} {
		if _, err := Parse([]byte(`{"op":"ping","seq":0,"stream_id":` + value + `}`)); err == nil {
			t.Fatalf("accepted stream_id=%s", value)
		}
	}
}

func TestConstructedEventWithOptionalStreamID(t *testing.T) {
	event := End(3)
	event.StreamID = "message-123"
	raw, err := event.Marshal()
	if err != nil {
		t.Fatal(err)
	}
	decoded, err := Parse(raw)
	if err != nil || decoded.StreamID != event.StreamID || decoded.Seq != 3 {
		t.Fatalf("round trip: %+v %v", decoded, err)
	}
}
