import { hasOwn, isRecord, type JsonRecord } from "./json.ts";

export const PROTOCOL_VERSION = "1.0" as const;

export interface BaseBlock {
  id: string;
  type: string;
  parent_id?: string | null;
  group_id?: string | null;
  [key: string]: unknown;
}

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
  version: typeof PROTOCOL_VERSION;
  biz: string;
  meta: Meta;
  blocks: Block[];
  [key: string]: unknown;
}

export function parseUIModel(input: unknown): UIModel {
  if (!isRecord(input)) throw new TypeError("model must be an object");
  if (input.version !== PROTOCOL_VERSION) throw new TypeError(`model version must be ${PROTOCOL_VERSION}`);
  if (typeof input.biz !== "string" || !input.biz) throw new TypeError("model biz must be a non-empty string");
  validateMeta(input.meta);
  if (!Array.isArray(input.blocks)) throw new TypeError("model blocks must be an array");
  for (const block of input.blocks) validateBlock(block);
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

function validateBlock(input: unknown): void {
  if (!isRecord(input)) throw new TypeError("model block must be an object");
  if (typeof input.id !== "string" || !input.id) throw new TypeError("model block requires a non-empty id");
  if (typeof input.type !== "string" || !input.type) throw new TypeError("model block requires a non-empty type");
  assertNullableString(input, "parent_id");
  assertNullableString(input, "group_id");
}

function assertNullableString(input: JsonRecord, key: string): void {
  if (hasOwn(input, key) && input[key] !== null && typeof input[key] !== "string") {
    throw new TypeError(`${key} must be a string or null`);
  }
}
