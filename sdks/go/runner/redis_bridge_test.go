package runner

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/compforge/agentue/sdks/go/ui"
	"github.com/redis/go-redis/v9"
)

func TestRedisEventBridgeAcrossInstances(t *testing.T) {
	server := miniredis.RunT(t)
	clientA := redis.NewClient(&redis.Options{Addr: server.Addr()})
	clientB := redis.NewClient(&redis.Options{Addr: server.Addr()})
	t.Cleanup(func() { _ = clientA.Close() })
	t.Cleanup(func() { _ = clientB.Close() })

	options := BridgeOptions{KeyPrefix: "test", ReadBlock: time.Millisecond, TaskTTL: time.Hour}
	bridgeA := NewRedisEventBridge(clientA, options)
	bridgeB := NewRedisEventBridge(clientB, options)
	ctx := context.Background()
	start := mustEvent(t, ui.Event{
		Op: ui.OpStart, Seq: 1,
		Model: map[string]any{"version": "1.0", "biz": "chat", "meta": map[string]any{}, "blocks": []any{}},
	})
	if err := bridgeA.Initialize(ctx, "task-1", json.RawMessage(`{"version":"1.0"}`), start, 1); err != nil {
		t.Fatal(err)
	}

	appendEvent := mustEvent(t, ui.Event{
		Op: ui.OpAppend, Seq: 2, Mask: "block.content",
		Block: map[string]any{"id": "answer", "type": "text", "content": "hello"},
	})
	cursor, err := bridgeA.Publish(ctx, "task-1", appendEvent, 2)
	if err != nil {
		t.Fatal(err)
	}
	duplicateCursor, err := bridgeB.Publish(ctx, "task-1", appendEvent, 2)
	if err != nil {
		t.Fatal(err)
	}
	if duplicateCursor != cursor {
		t.Fatalf("idempotent publish returned cursor %q, want %q", duplicateCursor, cursor)
	}
	if _, err := bridgeB.Publish(ctx, "task-1", mustEvent(t, ui.End(2)), 2); !errors.Is(err, ErrConflict) {
		t.Fatalf("duplicate sequence error = %v, want ErrConflict", err)
	}

	events, err := bridgeB.Read(ctx, "task-1", "0-0")
	if err != nil {
		t.Fatal(err)
	}
	if len(events) != 2 || events[1].Cursor != cursor {
		t.Fatalf("events = %#v, want start and append", events)
	}
	state, err := bridgeB.State(ctx, "task-1")
	if err != nil {
		t.Fatal(err)
	}
	if state.LastSeq != 2 || state.LastCursor != cursor || state.Status != StatusRunning {
		t.Fatalf("unexpected state: %#v", state)
	}
}

func TestReplayerResumesWithSnapshotAcrossInstances(t *testing.T) {
	server := miniredis.RunT(t)
	clientA := redis.NewClient(&redis.Options{Addr: server.Addr()})
	clientB := redis.NewClient(&redis.Options{Addr: server.Addr()})
	t.Cleanup(func() { _ = clientA.Close() })
	t.Cleanup(func() { _ = clientB.Close() })

	options := BridgeOptions{KeyPrefix: "test", ReadBlock: time.Millisecond}
	producer := NewRedisEventBridge(clientA, options)
	consumer := NewRedisEventBridge(clientB, options)
	ctx := context.Background()
	start := mustEvent(t, ui.Event{
		Op: ui.OpStart, Seq: 1,
		Model: map[string]any{"version": "1.0", "biz": "chat", "meta": map[string]any{}, "blocks": []any{}},
	})
	if err := producer.Initialize(ctx, "task-1", json.RawMessage(`{"version":"1.0"}`), start, 1); err != nil {
		t.Fatal(err)
	}
	set := mustEvent(t, ui.Event{
		Op: ui.OpSet, Seq: 2,
		Block: map[string]any{"id": "answer", "type": "text", "content": "hello"},
	})
	resumeCursor, err := producer.Publish(ctx, "task-1", set, 2)
	if err != nil {
		t.Fatal(err)
	}
	appendEvent := mustEvent(t, ui.Event{
		Op: ui.OpAppend, Seq: 3, Mask: "block.content",
		Block: map[string]any{"id": "answer", "type": "text", "content": " world"},
	})
	if _, err := producer.Publish(ctx, "task-1", appendEvent, 3); err != nil {
		t.Fatal(err)
	}
	end := mustEvent(t, ui.End(4))
	if _, err := producer.Publish(ctx, "task-1", end, 4); err != nil {
		t.Fatal(err)
	}
	if err := producer.MarkTerminal(ctx, "task-1", StatusCompleted); err != nil {
		t.Fatal(err)
	}
	if duplicateCursor, err := producer.Publish(ctx, "task-1", end, 4); err != nil || duplicateCursor == "" {
		t.Fatalf("terminal event retry: cursor=%q error=%v", duplicateCursor, err)
	}

	var deliveries []Delivery
	err = (Replayer{Bridge: consumer, PingInterval: time.Millisecond}).Stream(
		ctx, "task-1", resumeCursor,
		func(delivery Delivery) error {
			deliveries = append(deliveries, delivery)
			return nil
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(deliveries) != 3 {
		t.Fatalf("got %d deliveries, want reconstructed start, append, and end", len(deliveries))
	}
	first, err := ui.Parse(deliveries[0].Data)
	if err != nil {
		t.Fatal(err)
	}
	if first.Op != ui.OpStart || first.Seq != 2 || first.Model["blocks"].([]any)[0].(map[string]any)["content"] != "hello" {
		t.Fatalf("unexpected reconstructed start: %#v", first)
	}
	last, err := ui.Parse(deliveries[len(deliveries)-1].Data)
	if err != nil {
		t.Fatal(err)
	}
	if last.Op != ui.OpEnd {
		t.Fatalf("last event = %q, want end", last.Op)
	}
}

func mustEvent(t *testing.T, event ui.Event) json.RawMessage {
	t.Helper()
	data, err := event.Marshal()
	if err != nil {
		t.Fatal(err)
	}
	return data
}
