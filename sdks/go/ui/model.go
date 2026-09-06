package ui

import (
	"errors"
	"fmt"
	"strings"
)

const ProtocolVersion = "1.1"

// ValidateBlock accepts an inline block or an opaque {id, ref} reference.
// The application selected by biz owns reference resolution; validation does no I/O.
func ValidateBlock(block map[string]any) error {
	id, _ := block["id"].(string)
	if id == "" {
		return errors.New("block requires a non-empty id")
	}
	if ref, exists := block["ref"]; exists {
		key, ok := ref.(string)
		if !ok || key == "" {
			return errors.New("reference block requires a non-empty ref")
		}
		if len(block) != 2 {
			return errors.New("reference block only accepts id and ref")
		}
		return nil
	}
	typeName, _ := block["type"].(string)
	if typeName == "" {
		return errors.New("inline block requires a non-empty type")
	}
	for _, field := range []string{"parent_id", "group_id"} {
		if value, exists := block[field]; exists && value != nil {
			if _, ok := value.(string); !ok {
				return fmt.Errorf("%s must be a string or null", field)
			}
		}
	}
	return nil
}

// ValidateModel checks the common model envelope and ordered block identities.
func ValidateModel(model map[string]any) error {
	version, _ := model["version"].(string)
	if version != "1.0" && version != ProtocolVersion {
		return errors.New("model version must be 1.0 or 1.1")
	}
	biz, _ := model["biz"].(string)
	if biz == "" {
		return errors.New("model requires a non-empty biz")
	}
	if meta, ok := model["meta"].(map[string]any); !ok || meta == nil {
		return errors.New("model meta must be an object")
	}
	if _, exists := model["blocks"]; !exists {
		return errors.New("model requires blocks")
	}
	blocks, err := blocksOf(model)
	if err != nil {
		return err
	}
	ids := make(map[string]bool, len(blocks))
	for _, block := range blocks {
		if err := ValidateBlock(block); err != nil {
			return err
		}
		if _, exists := block["ref"]; exists && version != ProtocolVersion {
			return errors.New("reference blocks require model version 1.1")
		}
		id := block["id"].(string)
		if ids[id] {
			return fmt.Errorf("duplicate block id: %q", id)
		}
		ids[id] = true
	}
	return nil
}

func validateBlockFieldPatch(mask string, block map[string]any) error {
	if _, exists := block["ref"]; exists {
		return errors.New("reference blocks require whole-block set")
	}
	field := strings.Split(mask, ".")[1]
	if field == "id" || field == "ref" {
		return errors.New("block id and ref cannot be patched; use whole-block set for references")
	}
	return nil
}

func requireInlineBlock(block map[string]any) error {
	// spec: A pure reducer cannot append to unknown external content.
	if _, exists := block["ref"]; exists {
		return fmt.Errorf("unresolved reference block %q; materialize before field patches", block["id"])
	}
	return nil
}
