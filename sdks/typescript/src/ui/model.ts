import { hasOwn, isRecord, type JsonRecord } from "./json.ts";

export const PROTOCOL_VERSION = "1.1" as const;

export interface BaseBlock {
  id: string;
  type: string;
  ref?: never;
  parent_id?: string | null;
  group_id?: string | null;
  [key: string]: unknown;
}

/** An opaque reference interpreted and loaded by the application selected by biz. */
export type ReferenceBlock = {
  id: string;
  ref: string;
  type?: never;
};

export type Block = BaseBlock | ReferenceBlock;

export interface ErrorInfo {
  code: string;
  message: string;
  detail?: string | null;
  trace_id?: string | null;
  [key: string]: unknown;
}

export interface ModelMeta {
  error?: ErrorInfo | null;
  task_id?: string | null;
  trace_id?: string | null;
  stats?: Record<string, unknown> | null;
  [key: string]: unknown;
}

export interface UIModel<
  Block extends BaseBlock = BaseBlock,
  Meta extends ModelMeta = ModelMeta,
> {
  version: "1.0" | typeof PROTOCOL_VERSION;
  biz: string;
  meta: Meta;
  blocks: (Block | ReferenceBlock)[];
  [key: string]: unknown;
}

export function parseUIModel(input: unknown): UIModel {
  if (!isRecord(input)) throw new TypeError("model must be an object");
  if (input.version !== "1.0" && input.version !== PROTOCOL_VERSION) {
    throw new TypeError("model version must be 1.0 or 1.1");
  }
  if (typeof input.biz !== "string" || !input.biz) throw new TypeError("model biz must be a non-empty string");
  validateMeta(input.meta);
  if (!Array.isArray(input.blocks)) throw new TypeError("model blocks must be an array");
  const ids = new Set<string>();
  for (const block of input.blocks) {
    validateBlock(block);
    if (hasOwn(block, "ref") && input.version !== PROTOCOL_VERSION) {
      throw new TypeError("reference blocks require model version 1.1");
    }
    if (ids.has(block.id)) throw new TypeError(`duplicate block id: ${JSON.stringify(block.id)}`);
    ids.add(block.id);
  }
  return input as UIModel;
}

function validateMeta(input: unknown): void {
  if (!isRecord(input)) throw new TypeError("model meta must be an object");
  assertNullableString(input, "task_id");
  assertNullableString(input, "trace_id");
  if (hasOwn(input, "stats") && input.stats !== null && !isRecord(input.stats)) {
    throw new TypeError("model meta.stats must be an object or null");
  }
  if (hasOwn(input, "error") && input.error !== null) validateError(input.error);
}

function validateError(input: unknown): void {
  if (!isRecord(input)) throw new TypeError("model meta.error must be an object or null");
  if (typeof input.code !== "string" || typeof input.message !== "string") {
    throw new TypeError("model meta.error requires string code and message");
  }
  assertNullableString(input, "detail");
  assertNullableString(input, "trace_id");
}

export function validateBlock(input: unknown): asserts input is Block {
  if (!isRecord(input)) throw new TypeError("model block must be an object");
  if (typeof input.id !== "string" || !input.id) throw new TypeError("model block requires a non-empty id");
  if (hasOwn(input, "ref")) {
    if (typeof input.ref !== "string" || !input.ref) throw new TypeError("reference block requires a non-empty ref");
    if (Object.keys(input).some((key) => key !== "id" && key !== "ref")) {
      throw new TypeError("reference block only accepts id and ref");
    }
    return;
  }
  if (typeof input.type !== "string" || !input.type) throw new TypeError("model block requires a non-empty type");
  assertNullableString(input, "parent_id");
  assertNullableString(input, "group_id");
}

function assertNullableString(input: JsonRecord, key: string): void {
  if (hasOwn(input, key) && input[key] !== null && typeof input[key] !== "string") {
    throw new TypeError(`${key} must be a string or null`);
  }
}
