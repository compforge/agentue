import { describe, expect, test } from "bun:test";

import { applyPatch } from "../src/index.ts";

const emptyModel = () => ({ version: "1.0", biz: "chat", meta: {}, blocks: [] });

describe("applyPatch", () => {
  test("rejects unsupported nested append masks", () => {
    expect(() =>
      applyPatch(emptyModel(), {
        op: "append",
        seq: 1,
        mask: "block.tool.content",
        block: { id: "tool", type: "tool", content: "x" },
      }),
    ).toThrow("unsupported append mask");
  });

  test("rejects append values other than strings and lists", () => {
    expect(() =>
      applyPatch(emptyModel(), {
        op: "append",
        seq: 1,
        mask: "block.progress",
        block: { id: "stage", type: "stage", progress: 1 },
      }),
    ).toThrow("must be a string or list");
  });

  test("requires a targeted block to exist", () => {
    expect(() =>
      applyPatch(emptyModel(), {
        op: "set",
        seq: 1,
        mask: "block.content",
        block: { id: "missing", type: "text", content: "x" },
      }),
    ).toThrow("target block does not exist");
  });

  test("start replaces and clones the existing snapshot", () => {
    const model = { version: "1.0" as const, biz: "chat", meta: {}, blocks: [] };
    const result = applyPatch({ stale: true }, { op: "start", seq: 1, model });
    result.biz = "changed";
    expect(model.biz).toBe("chat");
    expect(result).not.toHaveProperty("stale");
  });
});
