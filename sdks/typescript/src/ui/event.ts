import { hasOwn, isRecord, type JsonRecord } from "./json.ts";
import { parseUIModel, validateBlock, type Block, type ModelMeta, type UIModel } from "./model.ts";

export const PatchOp = {
  START: "start",
  SET: "set",
  APPEND: "append",
  ERROR: "error",
  PING: "ping",
  END: "end",
} as const;

export type PatchOp = (typeof PatchOp)[keyof typeof PatchOp];

interface EventBase {
  seq: number;
  ts?: number;
  event_type?: string;
}

export interface StartEvent extends EventBase {
  op: "start";
  model: UIModel;
}

export interface BlockPatch extends JsonRecord {
  id: string;
  type?: string;
}

export interface SetBlockReplaceEvent extends EventBase {
  op: "set";
  mask?: never;
  block: Block;
}

export interface SetBlockFieldEvent extends EventBase {
  op: "set";
  mask: `block.${string}`;
  block: BlockPatch;
}

export type SetBlockEvent = SetBlockReplaceEvent | SetBlockFieldEvent;

export interface SetMetaEvent extends EventBase {
  op: "set";
  mask: `meta.${string}`;
  meta: Partial<ModelMeta> & JsonRecord;
}

export interface AppendEvent extends EventBase {
  op: "append";
  mask: `block.${string}`;
  block: BlockPatch;
}

export interface ErrorEvent extends EventBase {
  op: "error";
  mask: "meta.error";
  meta: { error: JsonRecord };
}

export interface PingEvent extends EventBase {
  op: "ping";
}

export interface EndEvent extends EventBase {
  op: "end";
}

export type PatchEvent =
  | StartEvent
  | SetBlockEvent
  | SetMetaEvent
  | AppendEvent
  | ErrorEvent
  | PingEvent
  | EndEvent;

export type PatchInput = string | PatchEvent | JsonRecord;

const EVENT_KEYS = new Set(["op", "seq", "ts", "mask", "event_type", "model", "meta", "block"]);
const PATCH_OPS = new Set<string>(Object.values(PatchOp));

export function parsePatchEvent(input: unknown): PatchEvent {
  const value = typeof input === "string" ? parseJson(input) : input;
  if (!isRecord(value)) throw new TypeError("patch event must be an object");

  for (const key of Object.keys(value)) {
    if (!EVENT_KEYS.has(key)) throw new TypeError(`patch event contains unknown field ${JSON.stringify(key)}`);
  }

  const op = value.op;
  if (typeof op !== "string" || !PATCH_OPS.has(op)) {
    throw new TypeError(`unsupported patch operation: ${JSON.stringify(op)}`);
  }
  if (!Number.isInteger(value.seq) || (value.seq as number) < 0) {
    throw new TypeError("patch event seq must be a non-negative integer");
  }
  assertOptionalNumber(value, "ts");
  assertOptionalString(value, "mask");
  assertOptionalString(value, "event_type");
  assertOptionalRecord(value, "model");
  assertOptionalRecord(value, "meta");
  assertOptionalRecord(value, "block");

  if (op !== PatchOp.START && hasOwn(value, "model")) {
    throw new TypeError("model is only allowed for start event");
  }

  switch (op) {
    case PatchOp.START:
      if (!hasOwn(value, "model")) throw new TypeError("start event requires model");
      if (hasOwn(value, "meta") || hasOwn(value, "block")) {
        throw new TypeError("start event only accepts model");
      }
      parseUIModel(value.model);
      break;
    case PatchOp.SET:
      validateSet(value);
      break;
    case PatchOp.APPEND:
      validateAppend(value);
      break;
    case PatchOp.ERROR:
      validateError(value);
      break;
    case PatchOp.PING:
    case PatchOp.END:
      if (hasOwn(value, "meta") || hasOwn(value, "block") || hasOwn(value, "mask")) {
        throw new TypeError(`${op} event does not accept state payloads`);
      }
      break;
  }

  return value as unknown as PatchEvent;
}

export function serializePatchEvent(event: PatchEvent): string {
  return JSON.stringify(parsePatchEvent(event));
}

export function extractPatchOp(eventJson: string): string | undefined {
  try {
    const value: unknown = JSON.parse(eventJson);
    return isRecord(value) && typeof value.op === "string" ? value.op : undefined;
  } catch {
    return undefined;
  }
}

function parseJson(input: string): unknown {
  try {
    return JSON.parse(input) as unknown;
  } catch (error) {
    throw new TypeError(`invalid patch event JSON: ${error instanceof Error ? error.message : String(error)}`);
  }
}

function validateSet(value: JsonRecord): void {
  const hasMeta = hasOwn(value, "meta");
  const hasBlock = hasOwn(value, "block");
  if (hasMeta === hasBlock) throw new TypeError("set event requires exactly one of meta or block");

  const mask = value.mask;
  if (!hasOwn(value, "mask") && !hasBlock) {
    throw new TypeError("set event without mask requires block");
  }
  if (typeof mask === "string") {
    const expected = hasMeta ? "meta." : "block.";
    if (!mask.startsWith(expected)) throw new TypeError(`set mask must start with ${JSON.stringify(expected)}`);
  }
  if (hasBlock) {
    const block = value.block as JsonRecord;
    assertBlockId(block);
    if (!hasOwn(value, "mask")) validateBlock(block);
    else validateBlockFieldPatch(value.mask as string, block);
  }
}

function validateAppend(value: JsonRecord): void {
  if (!hasOwn(value, "block")) throw new TypeError("append event requires block");
  if (hasOwn(value, "meta")) throw new TypeError("append event does not accept meta");
  if (typeof value.mask !== "string" || !value.mask.startsWith("block.")) {
    throw new TypeError("append mask must match 'block.<field>'");
  }
  assertBlockId(value.block as JsonRecord);
  validateBlockFieldPatch(value.mask as string, value.block as JsonRecord);
}

function validateError(value: JsonRecord): void {
  const meta = value.meta;
  if (value.mask !== "meta.error" || !isRecord(meta) || !isRecord(meta.error)) {
    throw new TypeError("error event requires mask='meta.error' and meta.error");
  }
  if (typeof meta.error.code !== "string" || typeof meta.error.message !== "string") {
    throw new TypeError("meta.error requires string code and message");
  }
  if (hasOwn(value, "block")) throw new TypeError("error event does not accept block");
}

function assertBlockId(block: JsonRecord): void {
  if (typeof block.id !== "string" || !block.id) throw new TypeError("block requires a non-empty id");
}

function validateBlockFieldPatch(mask: string, block: JsonRecord): void {
  if (hasOwn(block, "ref")) throw new TypeError("reference blocks require whole-block set");
  const field = mask.split(".")[1];
  if (field === "ref" || field === "id") {
    throw new TypeError("block id and ref cannot be patched; use whole-block set for references");
  }
}

function assertOptionalRecord(value: JsonRecord, key: string): void {
  if (hasOwn(value, key) && !isRecord(value[key])) {
    throw new TypeError(`patch event ${key} must be an object`);
  }
}

function assertOptionalString(value: JsonRecord, key: string): void {
  if (hasOwn(value, key) && typeof value[key] !== "string") {
    throw new TypeError(`patch event ${key} must be a string`);
  }
}

function assertOptionalNumber(value: JsonRecord, key: string): void {
  if (hasOwn(value, key) && (!Number.isInteger(value[key]) || (value[key] as number) < 0)) {
    throw new TypeError(`patch event ${key} must be a non-negative integer`);
  }
}
