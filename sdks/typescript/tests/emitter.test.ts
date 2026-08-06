import { describe, expect, test } from "bun:test";

import { PatchEmitter, PROTOCOL_VERSION, serializePatchEvent, type UIModel } from "@compforge/agentue/ui";

const model = (): UIModel => ({
  version: PROTOCOL_VERSION,
  biz: "chat",
  meta: { session_id: "session-1" },
  blocks: [{ id: "stage", type: "stage", stage: "starting" }],
});

describe("PatchEmitter", () => {
  test("preserves domain fields and orders events", () => {
    const emitter = new PatchEmitter();
    const start = emitter.start(model());
    const ping = emitter.ping();
    const append = emitter.blockAppend(
      { id: "answer", type: "text", content: "hello", group_id: "turn-1" },
      { eventType: "message.delta" },
    );
    const end = emitter.end();

    expect(start.seq).toBe(1);
    expect(start.model.meta.session_id).toBe("session-1");
    expect(start.model.blocks[0]?.stage).toBe("starting");
    expect(ping.seq).toBe(1);
    expect(append.seq).toBe(2);
    expect(append.event_type).toBe("message.delta");
    expect(append.block.group_id).toBe("turn-1");
    expect(end.seq).toBe(3);
  });

  test("reconstructed start uses the covered sequence", () => {
    const emitter = new PatchEmitter();
    expect(emitter.start(model(), 8).seq).toBe(8);
    expect(emitter.blockAppend({ id: "answer", type: "text", content: "next" }).seq).toBe(9);
  });

  test("targeted block set can assign null", () => {
    const event = new PatchEmitter(2).blockSet(
      { id: "tool", type: "tool", result: null },
      { mask: "block.result" },
    );
    expect(event.block.result).toBeNull();
  });

  test("error has no implicit tracing dependency", () => {
    const event = new PatchEmitter().error("failed", "Request failed", { detail: "upstream timeout" });
    expect(event.meta.error).toEqual({
      code: "failed",
      message: "Request failed",
      detail: "upstream timeout",
    });
  });

  test("serializes compact JSON", () => {
    expect(serializePatchEvent({ op: "ping", seq: 3, ts: 123 })).toBe('{"op":"ping","seq":3,"ts":123}');
  });
});
