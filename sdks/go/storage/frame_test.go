package storage

import (
	"bytes"
	"encoding/json"
	"slices"
	"strings"
	"testing"
)

func TestFrameRoundTrip(t *testing.T) {
	for _, text := range []string{"small", strings.Repeat("a", 2<<20), strings.Repeat("你好🙂\"\\\n<>&", 10000)} {
		raw, _ := json.Marshal(map[string]any{"id": "result", "type": "text", "content": text, "number": json.Number("9007199254740993")})
		for _, budget := range []int{256, 64 << 10} {
			frames, err := Frame(raw, budget)
			if err != nil {
				t.Fatal(err)
			}
			for _, f := range frames {
				encoded, err := json.Marshal(f)
				if err != nil || len(encoded) > budget || !json.Valid(encoded) {
					t.Fatalf("encoded frame size=%d budget=%d err=%v", len(encoded), budget, err)
				}
			}
			slices.Reverse(frames)
			got, err := Unframe(frames)
			if err != nil || !bytes.Equal(got, raw) {
				t.Fatalf("round trip differs: %v", err)
			}
		}
	}
}

func TestUnframeRejectsCorruption(t *testing.T) {
	raw, _ := json.Marshal(map[string]any{"id": "result", "type": "text", "content": strings.Repeat("x", 1000)})
	frames, err := Frame(raw, 256)
	if err != nil {
		t.Fatal(err)
	}
	for name, corrupt := range map[string]func([]FrameBlock) []FrameBlock{
		"missing tail":       func(f []FrameBlock) []FrameBlock { return f[:len(f)-1] },
		"duplicate":          func(f []FrameBlock) []FrameBlock { f[1] = f[0]; return f },
		"duplicate sequence": func(f []FrameBlock) []FrameBlock { f[1].Seq = 0; return f },
		"wrong total":        func(f []FrameBlock) []FrameBlock { f[1].Total++; return f },
		"wrong block":        func(f []FrameBlock) []FrameBlock { f[1].BlockID = "other"; return f },
		"out of range":       func(f []FrameBlock) []FrameBlock { f[1].Seq = len(f); return f },
		"negative":           func(f []FrameBlock) []FrameBlock { f[1].Seq = -1; return f },
		"bad JSON":           func(f []FrameBlock) []FrameBlock { f[0].Data = "!"; return f },
		"wrong restored ID": func(f []FrameBlock) []FrameBlock {
			for i := range f {
				f[i].BlockID = "other"
			}
			return f
		},
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := Unframe(corrupt(slices.Clone(frames))); err == nil {
				t.Fatal("accepted corrupt group")
			}
		})
	}
}

func TestFrameRejectsInvalidInput(t *testing.T) {
	for _, raw := range []string{`{}`, `{"id":"b","ref":"part"}`, `{"id":"b","type":"frame"}`, `{"id":"b","type":"text"} {}`, "\xff"} {
		if _, err := Frame(json.RawMessage(raw), 256); err == nil {
			t.Fatalf("accepted %q", raw)
		}
	}
	for _, budget := range []int{-1, 0, 32} {
		if _, err := Frame(json.RawMessage(`{"id":"b","type":"text"}`), budget); err == nil {
			t.Fatalf("accepted budget %d", budget)
		}
	}
	if _, err := Unframe(nil); err == nil {
		t.Fatal("accepted empty group")
	}
}
