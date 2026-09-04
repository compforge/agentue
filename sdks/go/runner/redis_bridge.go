package runner

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"

	"github.com/redis/go-redis/v9"
)

const (
	defaultKeyPrefix = "agentue:runner"
	defaultTaskTTL   = 24 * time.Hour
	defaultReadBlock = time.Second
	defaultReadCount = 100
)

var initializeScript = redis.NewScript(`
if redis.call('EXISTS', KEYS[1]) == 1 then
  return redis.error_reply('AGENTUE_CONFLICT')
end
local cursor = redis.call('XADD', KEYS[2], '*', 'event', ARGV[4])
redis.call('HSET', KEYS[1],
  'status', ARGV[1],
  'last_seq', ARGV[2],
  'initial_model', ARGV[3],
  'last_event', ARGV[4],
  'last_cursor', cursor)
redis.call('EXPIRE', KEYS[1], ARGV[5])
redis.call('EXPIRE', KEYS[2], ARGV[5])
return cursor
`)

var publishScript = redis.NewScript(`
local status = redis.call('HGET', KEYS[1], 'status')
if not status then
  return redis.error_reply('AGENTUE_NOT_FOUND')
end
local last_seq = tonumber(redis.call('HGET', KEYS[1], 'last_seq'))
local seq = tonumber(ARGV[2])
if seq == last_seq and redis.call('HGET', KEYS[1], 'last_event') == ARGV[3] then
  return redis.call('HGET', KEYS[1], 'last_cursor')
end
if status ~= ARGV[1] then
  return redis.error_reply('AGENTUE_CONFLICT')
end
if seq <= last_seq then
  return redis.error_reply('AGENTUE_CONFLICT')
end
local cursor = redis.call('XADD', KEYS[2], '*', 'event', ARGV[3])
redis.call('HSET', KEYS[1], 'last_seq', ARGV[2], 'last_event', ARGV[3], 'last_cursor', cursor)
redis.call('EXPIRE', KEYS[1], ARGV[4])
redis.call('EXPIRE', KEYS[2], ARGV[4])
return cursor
`)

var markTerminalScript = redis.NewScript(`
local current = redis.call('HGET', KEYS[1], 'status')
if not current then
  return redis.error_reply('AGENTUE_NOT_FOUND')
end
if current ~= ARGV[1] and current ~= ARGV[2] then
  return redis.error_reply('AGENTUE_CONFLICT')
end
redis.call('HSET', KEYS[1], 'status', ARGV[2])
redis.call('EXPIRE', KEYS[1], ARGV[3])
redis.call('EXPIRE', KEYS[2], ARGV[3])
return 'OK'
`)

// RedisEventBridge persists Runner events and liveness without owning the Redis client.
type RedisEventBridge struct {
	client  redis.UniversalClient
	options BridgeOptions
}

func NewRedisEventBridge(client redis.UniversalClient, options BridgeOptions) *RedisEventBridge {
	if options.KeyPrefix == "" {
		options.KeyPrefix = defaultKeyPrefix
	}
	if options.TaskTTL <= 0 {
		options.TaskTTL = defaultTaskTTL
	}
	if options.ReadBlock <= 0 {
		options.ReadBlock = defaultReadBlock
	}
	if options.ReadCount <= 0 {
		options.ReadCount = defaultReadCount
	}
	return &RedisEventBridge{client: client, options: options}
}

func (bridge *RedisEventBridge) Initialize(
	ctx context.Context,
	taskID string,
	initialModel json.RawMessage,
	startEvent json.RawMessage,
	seq uint64,
) error {
	_, err := initializeScript.Run(ctx, bridge.client,
		[]string{bridge.stateKey(taskID), bridge.streamKey(taskID)},
		string(StatusRunning),
		seq,
		string(initialModel),
		string(startEvent),
		bridge.ttlSeconds(),
	).Result()
	if err != nil {
		if containsRedisError(err, "AGENTUE_CONFLICT") {
			return fmt.Errorf("%w: task %q already exists", ErrConflict, taskID)
		}
		return fmt.Errorf("initialize event stream %q: %w", taskID, err)
	}
	return nil
}

func (bridge *RedisEventBridge) Delete(ctx context.Context, taskID string) error {
	if err := bridge.client.Del(ctx, bridge.stateKey(taskID), bridge.streamKey(taskID)).Err(); err != nil {
		return fmt.Errorf("delete event stream %q: %w", taskID, err)
	}
	return nil
}

func (bridge *RedisEventBridge) State(ctx context.Context, taskID string) (State, error) {
	values, err := bridge.client.HGetAll(ctx, bridge.stateKey(taskID)).Result()
	if err != nil {
		return State{}, fmt.Errorf("read event stream %q: %w", taskID, err)
	}
	if len(values) == 0 {
		return State{}, fmt.Errorf("%w: task %q", ErrNotFound, taskID)
	}
	lastSeq, err := strconv.ParseUint(values["last_seq"], 10, 64)
	if err != nil {
		return State{}, fmt.Errorf("decode event stream %q sequence: %w", taskID, err)
	}
	return State{
		TaskID: taskID, Status: Status(values["status"]), LastSeq: lastSeq,
		LastCursor: values["last_cursor"], InitialModel: json.RawMessage(values["initial_model"]),
	}, nil
}

func (bridge *RedisEventBridge) Publish(
	ctx context.Context,
	taskID string,
	event json.RawMessage,
	seq uint64,
) (string, error) {
	value, err := publishScript.Run(ctx, bridge.client,
		[]string{bridge.stateKey(taskID), bridge.streamKey(taskID)},
		string(StatusRunning),
		seq,
		string(event),
		bridge.ttlSeconds(),
	).Result()
	if err != nil {
		switch {
		case containsRedisError(err, "AGENTUE_NOT_FOUND"):
			return "", fmt.Errorf("%w: task %q", ErrNotFound, taskID)
		case containsRedisError(err, "AGENTUE_CONFLICT"):
			return "", fmt.Errorf("%w: task %q sequence %d", ErrConflict, taskID, seq)
		default:
			return "", fmt.Errorf("publish event for task %q: %w", taskID, err)
		}
	}
	return text(value), nil
}

func (bridge *RedisEventBridge) EventsThrough(ctx context.Context, taskID, end string) ([]StoredEvent, error) {
	if end == "" {
		end = "+"
	}
	values, err := bridge.client.XRange(ctx, bridge.streamKey(taskID), "-", end).Result()
	if err != nil {
		return nil, fmt.Errorf("range events for task %q: %w", taskID, err)
	}
	return storedEvents(values), nil
}

func (bridge *RedisEventBridge) Read(ctx context.Context, taskID, after string) ([]StoredEvent, error) {
	if after == "" {
		after = "0-0"
	}
	values, err := bridge.client.XRead(ctx, &redis.XReadArgs{
		Streams: []string{bridge.streamKey(taskID), after},
		Count:   bridge.options.ReadCount, Block: bridge.options.ReadBlock,
	}).Result()
	if errors.Is(err, redis.Nil) {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("read events for task %q: %w", taskID, err)
	}
	var result []StoredEvent
	for _, stream := range values {
		result = append(result, storedEvents(stream.Messages)...)
	}
	return result, nil
}

func (bridge *RedisEventBridge) MarkTerminal(ctx context.Context, taskID string, status Status) error {
	if !status.Terminal() {
		return fmt.Errorf("invalid terminal status %q", status)
	}
	_, err := markTerminalScript.Run(ctx, bridge.client,
		[]string{bridge.stateKey(taskID), bridge.streamKey(taskID)},
		string(StatusRunning),
		string(status),
		bridge.ttlSeconds(),
	).Result()
	if err != nil {
		switch {
		case containsRedisError(err, "AGENTUE_NOT_FOUND"):
			return fmt.Errorf("%w: task %q", ErrNotFound, taskID)
		case containsRedisError(err, "AGENTUE_CONFLICT"):
			return fmt.Errorf("%w: task %q is already terminal", ErrConflict, taskID)
		default:
			return fmt.Errorf("mark task %q terminal: %w", taskID, err)
		}
	}
	return nil
}

func (bridge *RedisEventBridge) stateKey(taskID string) string {
	return bridge.options.KeyPrefix + ":" + taskID + ":state"
}

func (bridge *RedisEventBridge) streamKey(taskID string) string {
	return bridge.options.KeyPrefix + ":" + taskID + ":events"
}

func (bridge *RedisEventBridge) ttlSeconds() int64 {
	seconds := int64(bridge.options.TaskTTL / time.Second)
	if seconds < 1 {
		return 1
	}
	return seconds
}

func storedEvents(values []redis.XMessage) []StoredEvent {
	result := make([]StoredEvent, 0, len(values))
	for _, value := range values {
		data, exists := value.Values["event"]
		if !exists {
			continue
		}
		result = append(result, StoredEvent{Cursor: value.ID, Data: json.RawMessage(text(data))})
	}
	return result
}

func text(value any) string {
	switch value := value.(type) {
	case string:
		return value
	case []byte:
		return string(value)
	default:
		return fmt.Sprint(value)
	}
}

func containsRedisError(err error, value string) bool {
	return err != nil && strings.Contains(err.Error(), value)
}
