import { parsePatchEvent, PatchOp, type PatchInput, type PatchEvent } from "./event.ts";
import { cloneJson, hasOwn, isRecord, type JsonRecord } from "./json.ts";

export type Snapshot = JsonRecord;

export function applyPatch(snapshot: Snapshot, patch: PatchInput): Snapshot {
  const event = parsePatchEvent(patch);

  switch (event.op) {
    case PatchOp.START:
      return cloneJson(event.model);
    case PatchOp.SET:
      return applySet(snapshot, event);
    case PatchOp.APPEND:
      return applyAppend(snapshot, event);
    case PatchOp.ERROR:
      return setByMask(snapshot, "meta.error", event.meta);
    case PatchOp.PING:
    case PatchOp.END:
      return snapshot;
  }
}

export function applyPatches(snapshot: Snapshot, patches: Iterable<PatchInput>): Snapshot {
  for (const patch of patches) snapshot = applyPatch(snapshot, patch);
  return snapshot;
}

function applySet(snapshot: Snapshot, event: Extract<PatchEvent, { op: "set" }>): Snapshot {
  if (event.mask === undefined) {
    upsertBlock(snapshot, event.block);
    return snapshot;
  }
  return setByMask(snapshot, event.mask, "meta" in event ? event.meta : event.block);
}

function applyAppend(snapshot: Snapshot, event: Extract<PatchEvent, { op: "append" }>): Snapshot {
  const field = event.mask.slice("block.".length);
  if (!field || field.includes(".")) {
    throw new Error(`unsupported append mask: ${JSON.stringify(event.mask)}; expected 'block.<field>'`);
  }
  if (!event.block.id) throw new Error("append block requires a non-empty id");
  if (!hasOwn(event.block, field)) throw new Error(`append block does not contain field ${JSON.stringify(field)}`);

  const nextValue = event.block[field];
  if (typeof nextValue !== "string" && !Array.isArray(nextValue)) {
    throw new TypeError(`append field ${JSON.stringify(field)} must be a string or list`);
  }

  const blocks = ensureBlocks(snapshot);
  const existing = blocks.find((block) => block.id === event.block.id);
  if (existing) {
    const currentValue = existing[field];
    if (currentValue === undefined || currentValue === null) {
      existing[field] = cloneJson(nextValue);
    } else if (typeof currentValue === "string" && typeof nextValue === "string") {
      existing[field] = currentValue + nextValue;
    } else if (Array.isArray(currentValue) && Array.isArray(nextValue)) {
      existing[field] = [...currentValue, ...cloneJson(nextValue)];
    } else {
      throw new TypeError(`append field ${JSON.stringify(field)} has incompatible value types`);
    }
    return snapshot;
  }

  if (!event.block.type) throw new Error("append for a missing block requires a complete block with type");
  blocks.push(cloneJson(event.block));
  return snapshot;
}

function upsertBlock(snapshot: Snapshot, block: JsonRecord): void {
  if (typeof block.id !== "string" || !block.id) throw new Error("set block requires a non-empty id");
  if (typeof block.type !== "string" || !block.type) throw new Error("set block requires a non-empty type");

  const blocks = ensureBlocks(snapshot);
  const index = blocks.findIndex((current) => current.id === block.id);
  if (index === -1) blocks.push(cloneJson(block));
  else blocks[index] = cloneJson(block);
}

function setByMask(snapshot: Snapshot, mask: string, source: JsonRecord): Snapshot {
  const separator = mask.indexOf(".");
  if (separator <= 0 || separator === mask.length - 1) throw new Error(`invalid set mask: ${JSON.stringify(mask)}`);

  const root = mask.slice(0, separator);
  const path = mask.slice(separator + 1).split(".");
  const value = readPath(source, path);
  if (!value.found) throw new Error(`payload does not contain masked value: ${JSON.stringify(mask)}`);

  let target: JsonRecord;
  if (root === "meta") {
    if (snapshot.meta === undefined) snapshot.meta = {};
    if (!isRecord(snapshot.meta)) throw new TypeError("snapshot meta must be an object");
    target = snapshot.meta;
  } else if (root === "block") {
    const blockId = source.id;
    const block = ensureBlocks(snapshot).find((candidate) => candidate.id === blockId);
    if (!block) throw new Error(`target block does not exist: ${JSON.stringify(blockId)}`);
    target = block;
  } else {
    throw new Error(`unsupported set mask root: ${JSON.stringify(root)}`);
  }

  writePath(target, path, value.value);
  return snapshot;
}

function readPath(source: JsonRecord, path: string[]): { found: boolean; value?: unknown } {
  let current: unknown = source;
  for (const part of path) {
    if (!isRecord(current) || !hasOwn(current, part)) {
      const leaf = path.at(-1);
      return leaf !== undefined && hasOwn(source, leaf)
        ? { found: true, value: source[leaf] }
        : { found: false };
    }
    current = current[part];
  }
  return { found: true, value: current };
}

function writePath(target: JsonRecord, path: string[], value: unknown): void {
  let current = target;
  for (const part of path.slice(0, -1)) {
    if (!isRecord(current[part])) current[part] = {};
    current = current[part] as JsonRecord;
  }
  const leaf = path.at(-1);
  if (leaf === undefined) throw new Error("set path must not be empty");
  current[leaf] = cloneJson(value);
}

function ensureBlocks(snapshot: Snapshot): JsonRecord[] {
  if (snapshot.blocks === undefined) snapshot.blocks = [];
  if (!Array.isArray(snapshot.blocks)) throw new TypeError("snapshot blocks must be an array");
  for (const block of snapshot.blocks) {
    if (!isRecord(block)) throw new TypeError("snapshot block must be an object");
  }
  return snapshot.blocks as JsonRecord[];
}
