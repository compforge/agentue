import { describe, expect, test } from "bun:test";

import { extractPatchOp, parsePatchEvent } from "@compforge/agentue/ui";

describe("patch event validation", () => {
  test("start requires a model", () => {
    expect(() => parsePatchEvent({ op: "start", seq: 1 })).toThrow("requires model");
  });

  test("set requires exactly one payload slot", () => {
    expect(() =>
      parsePatchEvent({
        op: "set",
        seq: 1,
        mask: "meta.status",
        meta: { status: "done" },
        block: { id: "x" },
      }),
    ).toThrow("exactly one");
  });

  test("control events reject state payloads", () => {
    expect(() => parsePatchEvent({ op: "ping", seq: 1, meta: { status: "ignored" } })).toThrow(
      "does not accept state payloads",
    );
  });

  test("unknown envelope fields are rejected", () => {
    expect(() => parsePatchEvent({ op: "ping", seq: 1, extra: true })).toThrow("unknown field");
  });

  test("extractPatchOp is tolerant", () => {
    expect(extractPatchOp('{"op":"set","seq":1}')).toBe("set");
    expect(extractPatchOp("not-json")).toBeUndefined();
  });

  test("stream_id must be a string when supplied", () => {
    for (const stream_id of [7, false, [], {}]) {
      expect(() => parsePatchEvent({ op: "ping", seq: 0, stream_id })).toThrow("stream_id");
    }
  });
});
