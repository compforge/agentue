package runner

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/compforge/agentue/sdks/go/ui"
)

const defaultPingInterval = 15 * time.Second

// Delivery is one event ready for transport. Cursor is empty for synthetic
// start and ping events because they do not identify persisted stream records.
type Delivery struct {
	Cursor string
	Data   json.RawMessage
}

// Replayer turns a persisted event timeline into a complete AgentUE delivery.
// Every delivery starts with a full model and ends with an end event, whether
// the caller starts at the beginning or resumes from a transport cursor.
type Replayer struct {
	Bridge       EventBridge
	PingInterval time.Duration
}

func (replayer Replayer) Stream(
	ctx context.Context,
	taskID string,
	after string,
	deliver func(Delivery) error,
) error {
	if replayer.Bridge == nil {
		return fmt.Errorf("event bridge is required")
	}
	state, err := replayer.Bridge.State(ctx, taskID)
	if err != nil {
		return err
	}

	cursor := after
	lastSeq := uint64(0)
	if after != "" && after != "0-0" {
		snapshot, seq, err := replayer.snapshotThrough(ctx, taskID, after)
		if err != nil {
			return err
		}
		start, err := ui.Start(snapshot, seq)
		if err != nil {
			return err
		}
		data, err := start.Marshal()
		if err != nil {
			return err
		}
		if err := deliver(Delivery{Data: data}); err != nil {
			return err
		}
		lastSeq = seq
	}

	pingInterval := replayer.PingInterval
	if pingInterval <= 0 {
		pingInterval = defaultPingInterval
	}
	lastDelivery := time.Now()
	for {
		events, err := replayer.Bridge.Read(ctx, taskID, cursor)
		if err != nil {
			return err
		}
		for _, stored := range events {
			event, err := ui.Parse(stored.Data)
			if err != nil {
				return fmt.Errorf("parse event at cursor %q: %w", stored.Cursor, err)
			}
			if after != "" && after != "0-0" && event.Op == ui.OpStart {
				cursor = stored.Cursor
				continue
			}
			if err := deliver(Delivery{Cursor: stored.Cursor, Data: stored.Data}); err != nil {
				return err
			}
			cursor = stored.Cursor
			lastSeq = event.Seq
			lastDelivery = time.Now()
			if event.Op == ui.OpEnd {
				return nil
			}
		}

		state, err = replayer.Bridge.State(ctx, taskID)
		if err != nil {
			return err
		}
		if state.Status.Terminal() && cursor == state.LastCursor {
			end, err := ui.End(state.LastSeq).Marshal()
			if err != nil {
				return err
			}
			return deliver(Delivery{Data: end})
		}
		if time.Since(lastDelivery) >= pingInterval {
			ping, err := ui.Ping(lastSeq).Marshal()
			if err != nil {
				return err
			}
			if err := deliver(Delivery{Data: ping}); err != nil {
				return err
			}
			lastDelivery = time.Now()
		}
	}
}

func (replayer Replayer) snapshotThrough(ctx context.Context, taskID, cursor string) (json.RawMessage, uint64, error) {
	stored, err := replayer.Bridge.EventsThrough(ctx, taskID, cursor)
	if err != nil {
		return nil, 0, err
	}
	if len(stored) == 0 || stored[len(stored)-1].Cursor != cursor {
		return nil, 0, fmt.Errorf("%w: cursor %q for task %q", ErrNotFound, cursor, taskID)
	}
	snapshot := map[string]any{}
	lastSeq := uint64(0)
	for _, item := range stored {
		event, err := ui.Parse(item.Data)
		if err != nil {
			return nil, 0, fmt.Errorf("parse event at cursor %q: %w", item.Cursor, err)
		}
		snapshot, err = ui.Apply(snapshot, event)
		if err != nil {
			return nil, 0, fmt.Errorf("apply event at cursor %q: %w", item.Cursor, err)
		}
		if event.Op != ui.OpPing {
			lastSeq = event.Seq
		}
	}
	data, err := ui.MarshalSnapshot(snapshot)
	if err != nil {
		return nil, 0, fmt.Errorf("marshal reconstructed model: %w", err)
	}
	return data, lastSeq, nil
}
