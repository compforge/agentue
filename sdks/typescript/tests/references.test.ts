import { describe, expect, test } from "bun:test";
import {
  applyPatch, applyPatches, parsePatchEvent, parseUIModel, PatchEmitter, PROTOCOL_VERSION,
  type Block, type ReferenceBlock, type Snapshot, type UIModel,
} from "@compforge/agentue/ui";

const fixture = await Bun.file(new URL("../../../conformance/cases/block-references.json", import.meta.url)).json() as {
  invalid_models: { name: string; model: Snapshot }[];
  rejected_updates: { name: string; initial: Snapshot; event: Snapshot }[];
};

describe("reference blocks", () => {
  test("reference types exclude inline fields", () => {
    // @ts-expect-error A reference cannot also be an inline block.
    const mixed: Block = { id: "b2", ref: "x", type: "text", content: "body" };
    // @ts-expect-error ReferenceBlock only carries id and ref.
    const extra: ReferenceBlock = { id: "b2", ref: "x", content: "body" };
    expect(() => parseUIModel({ version: PROTOCOL_VERSION, biz: "chat", meta: {}, blocks: [mixed] })).toThrow();
    expect(() => parseUIModel({ version: PROTOCOL_VERSION, biz: "chat", meta: {}, blocks: [extra] })).toThrow();
  });
  for (const entry of fixture.invalid_models) {
    test(entry.name, () => {
      expect(() => parseUIModel(entry.model)).toThrow();
      expect(() => parsePatchEvent({ op: "start", seq: 1, model: entry.model })).toThrow();
    });
  }
  for (const entry of fixture.rejected_updates) {
    test(entry.name, () => {
      const snapshot = structuredClone(entry.initial);
      expect(() => applyPatch(snapshot, entry.event)).toThrow();
      expect(snapshot).toEqual(entry.initial);
    });
  }
  test("typed emitter accepts reference blocks and preserves order on materialization", () => {
    const reference: ReferenceBlock = { id: "b2", ref: "not/a/url" };
    const model: UIModel = { version: PROTOCOL_VERSION, biz: "chat", meta: {}, blocks: [reference] };
    const emitter = new PatchEmitter();
    const snapshot = applyPatches({}, [
      emitter.start(model), emitter.blockSet(reference),
      emitter.blockSet({ id: "b2", type: "text", content: "Hello" }),
      emitter.blockAppend({ id: "b2", type: "text", content: " world" }),
    ]);
    expect(snapshot.blocks).toEqual([{ id: "b2", type: "text", content: "Hello world" }]);
  });
  test("inline and reference identities share one scope", () => {
    expect(() => parseUIModel({ version: "1.1", biz: "chat", meta: {}, blocks: [
      { id: "b2", type: "text" }, { id: "b2", ref: "x" },
    ] })).toThrow("duplicate block id");
  });
});
