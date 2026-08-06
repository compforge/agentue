import { describe, expect, test } from "bun:test";

import { parseUIModel } from "@compforge/agentue/ui";

describe("semantic model validation", () => {
  test("preserves domain extensions", () => {
    const model = {
      version: "1.0",
      biz: "chat",
      meta: { session_id: "session-1" },
      blocks: [{ id: "answer", type: "text", content: "hello" }],
    };
    expect(parseUIModel(model) === model).toBe(true);
  });

  test("rejects invalid common block fields", () => {
    expect(() =>
      parseUIModel({
        version: "1.0",
        biz: "chat",
        meta: {},
        blocks: [{ id: "answer", type: "text", parent_id: 1 }],
      }),
    ).toThrow("parent_id must be a string or null");
  });

  test("validates common error metadata", () => {
    expect(() =>
      parseUIModel({
        version: "1.0",
        biz: "chat",
        meta: { error: { code: "failed" } },
        blocks: [],
      }),
    ).toThrow("requires string code and message");
  });
});
