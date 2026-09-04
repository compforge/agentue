package runner

import (
	"context"
	"encoding/json"
	"errors"
	"time"
)

var (
	ErrNotFound = errors.New("event stream not found")
	ErrConflict = errors.New("event stream conflict")
)

type Status string

const (
	StatusRunning   Status = "running"
	StatusCompleted Status = "completed"
	StatusFailed    Status = "failed"
)

func (status Status) Terminal() bool {
	return status == StatusCompleted || status == StatusFailed
}

type State struct {
	TaskID       string
	Status       Status
	LastSeq      uint64
	LastCursor   string
	InitialModel json.RawMessage
}

type StoredEvent struct {
	Cursor string
	Data   json.RawMessage
}

type EventBridge interface {
	Initialize(context.Context, string, json.RawMessage, json.RawMessage, uint64) error
	Delete(context.Context, string) error
	State(context.Context, string) (State, error)
	Publish(context.Context, string, json.RawMessage, uint64) (string, error)
	EventsThrough(context.Context, string, string) ([]StoredEvent, error)
	Read(context.Context, string, string) ([]StoredEvent, error)
	MarkTerminal(context.Context, string, Status) error
}

type BridgeOptions struct {
	KeyPrefix string
	TaskTTL   time.Duration
	ReadBlock time.Duration
	ReadCount int64
}
