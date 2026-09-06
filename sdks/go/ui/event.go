// Package ui implements the AgentUE event protocol and deterministic reducer.
package ui

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
)

type Op string

const (
	OpStart  Op = "start"
	OpSet    Op = "set"
	OpAppend Op = "append"
	OpError  Op = "error"
	OpPing   Op = "ping"
	OpEnd    Op = "end"
)

type Event struct {
	Op        Op             `json:"op"`
	Seq       uint64         `json:"seq"`
	Timestamp *int64         `json:"ts,omitempty"`
	Mask      string         `json:"mask,omitempty"`
	EventType string         `json:"event_type,omitempty"`
	Model     map[string]any `json:"model,omitempty"`
	Meta      map[string]any `json:"meta,omitempty"`
	Block     map[string]any `json:"block,omitempty"`
}

func Parse(data []byte) (Event, error) {
	var event Event
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&event); err != nil {
		return Event{}, fmt.Errorf("decode AgentUE event: %w", err)
	}
	if err := event.Validate(); err != nil {
		return Event{}, err
	}
	return event, nil
}

func Start(model json.RawMessage, seq uint64) (Event, error) {
	var value map[string]any
	if err := json.Unmarshal(model, &value); err != nil {
		return Event{}, fmt.Errorf("decode AgentUE model: %w", err)
	}
	event := Event{Op: OpStart, Seq: seq, Model: value}
	return event, event.Validate()
}

func End(seq uint64) Event { return Event{Op: OpEnd, Seq: seq} }

func Ping(seq uint64) Event { return Event{Op: OpPing, Seq: seq} }

func Failure(seq uint64, code, message string) Event {
	return Event{
		Op: OpError, Seq: seq, Mask: "meta.error",
		Meta: map[string]any{"error": map[string]any{"code": code, "message": message}},
	}
}

func (event Event) Marshal() ([]byte, error) {
	if err := event.Validate(); err != nil {
		return nil, err
	}
	return json.Marshal(event)
}

func (event Event) Validate() error {
	if event.Op != OpStart && event.Model != nil {
		return errors.New("model is only allowed for start event")
	}
	switch event.Op {
	case OpStart:
		if event.Model == nil || event.Meta != nil || event.Block != nil || event.Mask != "" {
			return errors.New("start event requires only model")
		}
		return ValidateModel(event.Model)
	case OpSet:
		if (event.Meta == nil) == (event.Block == nil) {
			return errors.New("set event requires exactly one of meta or block")
		}
		if event.Mask == "" && event.Block == nil {
			return errors.New("set event without mask requires block")
		}
		if event.Mask != "" {
			expected := "meta."
			if event.Block != nil {
				expected = "block."
			}
			if !strings.HasPrefix(event.Mask, expected) || len(event.Mask) == len(expected) {
				return fmt.Errorf("set mask must start with %q", expected)
			}
		}
		if event.Mask == "" {
			return ValidateBlock(event.Block)
		}
		if event.Block != nil {
			return validateBlockFieldPatch(event.Mask, event.Block)
		}
	case OpAppend:
		if event.Block == nil || event.Meta != nil || !strings.HasPrefix(event.Mask, "block.") || event.Mask == "block." {
			return errors.New("append event requires block and a block field mask")
		}
		return validateBlockFieldPatch(event.Mask, event.Block)
	case OpError:
		errorValue, ok := event.Meta["error"].(map[string]any)
		if event.Mask != "meta.error" || !ok || errorValue == nil || event.Block != nil {
			return errors.New("error event requires mask=meta.error and meta.error")
		}
	case OpPing, OpEnd:
		if event.Model != nil || event.Meta != nil || event.Block != nil || event.Mask != "" {
			return fmt.Errorf("%s event does not accept state payloads", event.Op)
		}
	default:
		return fmt.Errorf("unsupported AgentUE operation %q", event.Op)
	}
	return nil
}
