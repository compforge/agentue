package ui

import (
	"encoding/json"
	"errors"
	"fmt"
	"strings"
)

// Apply updates one model. A multiplexing caller routes by StreamID before
// calling Apply; this reducer neither selects streams nor owns their lifecycle.
func Apply(snapshot map[string]any, event Event) (map[string]any, error) {
	if err := event.Validate(); err != nil {
		return nil, err
	}
	switch event.Op {
	case OpStart:
		return cloneMap(event.Model)
	case OpSet:
		if event.Mask == "" {
			return snapshot, upsertBlock(snapshot, event.Block)
		}
		source := event.Meta
		if source == nil {
			source = event.Block
		}
		return snapshot, setByMask(snapshot, event.Mask, source)
	case OpAppend:
		return snapshot, appendByMask(snapshot, event.Mask, event.Block)
	case OpError:
		return snapshot, setByMask(snapshot, event.Mask, event.Meta)
	case OpPing, OpEnd:
		return snapshot, nil
	default:
		return nil, fmt.Errorf("unsupported AgentUE operation %q", event.Op)
	}
}

func ApplyAll(snapshot map[string]any, events []Event) (map[string]any, error) {
	var err error
	for _, event := range events {
		snapshot, err = Apply(snapshot, event)
		if err != nil {
			return nil, err
		}
	}
	return snapshot, nil
}

func MarshalSnapshot(snapshot map[string]any) (json.RawMessage, error) {
	return json.Marshal(snapshot)
}

func upsertBlock(snapshot, block map[string]any) error {
	id, _ := block["id"].(string)
	if err := ValidateBlock(block); err != nil {
		return err
	}
	if _, exists := block["ref"]; exists && snapshot["version"] != ProtocolVersion {
		return errors.New("reference blocks require model version 1.1")
	}
	blocks, err := blocksOf(snapshot)
	if err != nil {
		return err
	}
	copy, err := cloneMap(block)
	if err != nil {
		return err
	}
	for index, current := range blocks {
		if current["id"] == id {
			blocks[index] = copy
			snapshot["blocks"] = mapsToValues(blocks)
			return nil
		}
	}
	blocks = append(blocks, copy)
	snapshot["blocks"] = mapsToValues(blocks)
	return nil
}

func appendByMask(snapshot map[string]any, mask string, block map[string]any) error {
	field := strings.TrimPrefix(mask, "block.")
	if field == "" || strings.Contains(field, ".") {
		return fmt.Errorf("unsupported append mask %q", mask)
	}
	id, _ := block["id"].(string)
	if id == "" {
		return errors.New("append block requires a non-empty id")
	}
	value, exists := block[field]
	if !exists {
		return fmt.Errorf("append block does not contain field %q", field)
	}
	blocks, err := blocksOf(snapshot)
	if err != nil {
		return err
	}
	for _, current := range blocks {
		if current["id"] != id {
			continue
		}
		if err := requireInlineBlock(current); err != nil {
			return err
		}
		switch added := value.(type) {
		case string:
			old, ok := current[field].(string)
			if current[field] != nil && !ok {
				return fmt.Errorf("append field %q has incompatible value types", field)
			}
			current[field] = old + added
		case []any:
			old, ok := current[field].([]any)
			if current[field] != nil && !ok {
				return fmt.Errorf("append field %q has incompatible value types", field)
			}
			current[field] = append(old, added...)
		default:
			return fmt.Errorf("append field %q must be a string or list", field)
		}
		return nil
	}
	return upsertBlock(snapshot, block)
}

func setByMask(snapshot map[string]any, mask string, source map[string]any) error {
	root, relative, ok := strings.Cut(mask, ".")
	if !ok || relative == "" {
		return fmt.Errorf("invalid set mask %q", mask)
	}
	path := strings.Split(relative, ".")
	value, exists := readPath(source, path)
	if !exists {
		return fmt.Errorf("payload does not contain masked value %q", mask)
	}
	var target map[string]any
	switch root {
	case "meta":
		target, _ = snapshot["meta"].(map[string]any)
		if target == nil {
			target = map[string]any{}
			snapshot["meta"] = target
		}
	case "block":
		id, _ := source["id"].(string)
		blocks, err := blocksOf(snapshot)
		if err != nil {
			return err
		}
		for _, block := range blocks {
			if block["id"] == id {
				target = block
				break
			}
		}
		if target == nil {
			return fmt.Errorf("target block does not exist: %q", id)
		}
		if err := requireInlineBlock(target); err != nil {
			return err
		}
	default:
		return fmt.Errorf("unsupported set mask root %q", root)
	}
	writePath(target, path, value)
	return nil
}

func readPath(source map[string]any, path []string) (any, bool) {
	var current any = source
	for _, part := range path {
		object, ok := current.(map[string]any)
		if !ok {
			value, exists := source[path[len(path)-1]]
			return value, exists
		}
		value, exists := object[part]
		if !exists {
			value, exists = source[path[len(path)-1]]
			return value, exists
		}
		current = value
	}
	return current, true
}

func writePath(target map[string]any, path []string, value any) {
	current := target
	for _, part := range path[:len(path)-1] {
		next, _ := current[part].(map[string]any)
		if next == nil {
			next = map[string]any{}
			current[part] = next
		}
		current = next
	}
	current[path[len(path)-1]] = value
}

func blocksOf(snapshot map[string]any) ([]map[string]any, error) {
	raw, exists := snapshot["blocks"]
	if !exists {
		snapshot["blocks"] = []any{}
		return []map[string]any{}, nil
	}
	values, ok := raw.([]any)
	if !ok {
		return nil, errors.New("snapshot blocks must be a list")
	}
	blocks := make([]map[string]any, 0, len(values))
	for _, value := range values {
		block, ok := value.(map[string]any)
		if !ok {
			return nil, errors.New("snapshot block must be an object")
		}
		blocks = append(blocks, block)
	}
	return blocks, nil
}

func mapsToValues(values []map[string]any) []any {
	result := make([]any, len(values))
	for index := range values {
		result[index] = values[index]
	}
	return result
}

func cloneMap(value map[string]any) (map[string]any, error) {
	encoded, err := json.Marshal(value)
	if err != nil {
		return nil, err
	}
	var result map[string]any
	if err := json.Unmarshal(encoded, &result); err != nil {
		return nil, err
	}
	return result, nil
}
