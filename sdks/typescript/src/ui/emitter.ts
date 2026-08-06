import type {
  AppendEvent,
  EndEvent,
  ErrorEvent,
  PingEvent,
  SetBlockEvent,
  SetMetaEvent,
  StartEvent,
} from "./event.ts";
import { cloneJson, type JsonRecord } from "./json.ts";
import type { BaseBlock, ModelMeta, UIModel } from "./model.ts";

export interface EventOptions {
  eventType?: string;
}

export interface BlockSetOptions extends EventOptions {
  mask?: `block.${string}`;
}

export interface BlockAppendOptions extends EventOptions {
  mask?: `block.${string}`;
}

export interface ErrorOptions {
  traceId?: string;
  detail?: string;
}

export class PatchEmitter {
  private currentOffset: number;

  constructor(startOffset = 0) {
    if (!Number.isInteger(startOffset) || startOffset < 0) {
      throw new Error("startOffset must be a non-negative integer");
    }
    this.currentOffset = startOffset;
  }

  get offset(): number {
    return this.currentOffset;
  }

  start(model: UIModel, seq?: number): StartEvent {
    const nextSeq = seq ?? this.nextOffset();
    if (!Number.isInteger(nextSeq) || nextSeq < this.currentOffset) {
      throw new Error("start seq cannot move the emitter backwards");
    }
    this.currentOffset = nextSeq;
    return { op: "start", seq: nextSeq, model: cloneJson(model) };
  }

  blockSet(block: BaseBlock, options: BlockSetOptions = {}): SetBlockEvent {
    const seq = this.nextOffset();
    const event: SetBlockEvent = options.mask === undefined
      ? { op: "set", seq, block: cloneJson(block) }
      : { op: "set", seq, mask: options.mask, block: cloneJson(block) };
    if (options.eventType !== undefined) event.event_type = options.eventType;
    return event;
  }

  metaSet(
    mask: `meta.${string}`,
    meta: Partial<ModelMeta> & JsonRecord,
    options: EventOptions = {},
  ): SetMetaEvent {
    const event: SetMetaEvent = {
      op: "set",
      seq: this.nextOffset(),
      mask,
      meta: cloneJson(meta),
    };
    if (options.eventType !== undefined) event.event_type = options.eventType;
    return event;
  }

  blockAppend(block: BaseBlock, options: BlockAppendOptions = {}): AppendEvent {
    const event: AppendEvent = {
      op: "append",
      seq: this.nextOffset(),
      mask: options.mask ?? "block.content",
      block: cloneJson(block),
    };
    if (options.eventType !== undefined) event.event_type = options.eventType;
    return event;
  }

  error(code: string, message: string, options: ErrorOptions = {}): ErrorEvent {
    const error: JsonRecord = { code, message };
    if (options.detail !== undefined && options.detail !== message) error.detail = options.detail;
    if (options.traceId !== undefined) error.trace_id = options.traceId;
    return {
      op: "error",
      seq: this.nextOffset(),
      mask: "meta.error",
      meta: { error },
    };
  }

  setStats(stats: JsonRecord): SetMetaEvent {
    return this.metaSet("meta.stats", { stats: cloneJson(stats) });
  }

  ping(): PingEvent {
    return { op: "ping", seq: this.currentOffset, ts: Date.now() };
  }

  end(): EndEvent {
    return { op: "end", seq: this.nextOffset() };
  }

  private nextOffset(): number {
    this.currentOffset += 1;
    return this.currentOffset;
  }
}

export { PatchEmitter as SSEEmitter };
