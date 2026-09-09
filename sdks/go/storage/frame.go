// Package storage provides optional physical encodings, not UI protocol types.
// Applications own persistence, ordering, transactions and revision isolation.
package storage

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"strings"
	"unicode/utf8"

	"github.com/compforge/agentue/sdks/go/ui"
)

const FrameType = "frame"

// FrameBlock is a storage-only fragment of a serialized logical block.
// Seq is local to BlockID, unrelated to the UI event sequence. Total detects
// missing fragments; it does not detect mixing different stored revisions.
type FrameBlock struct {
	ID      string `json:"id"`
	Type    string `json:"type"`
	BlockID string `json:"block_id"`
	Seq     int    `json:"seq"`
	Total   int    `json:"total"`
	Data    string `json:"data"`
}

// Frame splits one complete inline block. Every frame's JSON encoding is at
// most maxBytes, including escaping and envelope fields. Callers must reserve
// any additional container overhead themselves. Frames must be reassembled
// before entering a UI reducer or being returned as logical content.
// +spec=`Framing preserves the original JSON bytes, including Unicode and numeric precision; the byte budget applies to encoded frames, not just Data.`
func Frame(block json.RawMessage, maxBytes int) ([]FrameBlock, error) {
	id, err := blockIdentity(block)
	if err != nil {
		return nil, err
	}
	// A fragment contains at least one input byte. Reserving digits for this
	// upper bound keeps Total/Seq growth from requiring a second framing pass.
	prototype := FrameBlock{ID: strings.Repeat("0", 32), Type: FrameType, BlockID: id, Seq: len(block), Total: len(block)}
	envelope, err := json.Marshal(prototype)
	if err != nil {
		return nil, err
	}
	budget := maxBytes - len(envelope)
	if budget <= 0 {
		return nil, fmt.Errorf("frame budget %d cannot hold block %q envelope", maxBytes, id)
	}
	var frames []FrameBlock
	for remaining := string(block); remaining != ""; {
		// JSON encoding only expands valid UTF-8. Search a bounded prefix;
		// never split a rune, even though the reconstructed JSON is opaque here.
		lo, hi, take := 1, min(len(remaining), budget), 0
		for lo <= hi {
			mid := lo + (hi-lo)/2
			end := mid
			for end > 0 && end < len(remaining) && !utf8.RuneStart(remaining[end]) {
				end--
			}
			encoded, _ := json.Marshal(remaining[:end])
			if len(encoded)-2 <= budget {
				take = max(take, end)
				lo = mid + 1
			} else {
				hi = mid - 1
			}
		}
		if take == 0 {
			return nil, fmt.Errorf("frame budget %d cannot hold next character of block %q", maxBytes, id)
		}
		var random [16]byte
		if _, err := rand.Read(random[:]); err != nil {
			return nil, err
		}
		frames = append(frames, FrameBlock{ID: hex.EncodeToString(random[:]), Type: FrameType, BlockID: id, Seq: len(frames), Data: remaining[:take]})
		remaining = remaining[take:]
	}
	for i := range frames {
		frames[i].Total = len(frames)
	}
	return frames, nil
}

// Unframe reassembles one complete group, accepting any input order. It rejects
// missing/duplicate fragments, inconsistent identities and invalid restored JSON.
// No size ceiling is imposed on the restored logical block.
func Unframe(frames []FrameBlock) (json.RawMessage, error) {
	if len(frames) == 0 || frames[0].Total != len(frames) {
		return nil, fmt.Errorf("incomplete frame group")
	}
	id := frames[0].BlockID
	ordered := make([]string, len(frames))
	ids := make(map[string]bool, len(frames))
	for _, f := range frames {
		if f.Type != FrameType || f.ID == "" || ids[f.ID] || f.BlockID != id || f.Total != len(frames) || f.Seq < 0 || f.Seq >= len(frames) || f.Data == "" || !utf8.ValidString(f.Data) {
			return nil, fmt.Errorf("invalid frame %q in block %q", f.ID, id)
		}
		if ordered[f.Seq] != "" {
			return nil, fmt.Errorf("duplicate frame sequence %d in block %q", f.Seq, id)
		}
		ids[f.ID] = true
		ordered[f.Seq] = f.Data
	}
	block := json.RawMessage(strings.Join(ordered, ""))
	restoredID, err := blockIdentity(block)
	if err != nil {
		return nil, err
	}
	if restoredID != id {
		return nil, fmt.Errorf("restored block %q does not match frame group %q", restoredID, id)
	}
	return block, nil
}

func blockIdentity(raw json.RawMessage) (string, error) {
	if !utf8.Valid(raw) {
		return "", fmt.Errorf("block contains invalid UTF-8")
	}
	var block map[string]any
	decoder := json.NewDecoder(strings.NewReader(string(raw)))
	decoder.UseNumber()
	if !json.Valid(raw) {
		return "", fmt.Errorf("invalid block JSON")
	}
	if err := decoder.Decode(&block); err != nil {
		return "", err
	}
	if err := ui.ValidateBlock(block); err != nil {
		return "", err
	}
	if _, ref := block["ref"]; ref || block["type"] == FrameType {
		return "", fmt.Errorf("framing requires a complete non-frame block")
	}
	return block["id"].(string), nil
}
