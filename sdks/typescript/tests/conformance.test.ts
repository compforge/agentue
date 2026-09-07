import { describe, expect, test } from "bun:test";

import { applyPatches, parsePatchEvent, parseUIModel, serializePatchEvent, type PatchInput, type Snapshot } from "@compforge/agentue/ui";

interface ConformanceCase {
  name: string;
  initial: Snapshot;
  events: PatchInput[];
  expected: Snapshot;
}

interface ConformanceFixture {
  protocol_version: string;
  cases: ConformanceCase[];
}

const fixture = (await Bun.file(
  new URL("../../../conformance/cases/state-transitions.json", import.meta.url),
).json()) as ConformanceFixture;

describe("shared conformance", () => {
  for (const conformanceCase of fixture.cases) {
    test(conformanceCase.name, () => {
      const result = applyPatches(conformanceCase.initial, conformanceCase.events);
      expect(result).toEqual(conformanceCase.expected);
      expect(parseUIModel(result) === result).toBe(true);
    });
  }
});

test("optional stream addressing isolates interleaved timelines", async () => {
  const addressed = await Bun.file(
    new URL("../../../conformance/cases/stream-addressing.json", import.meta.url),
  ).json() as { events: PatchInput[]; expected: Record<string, Snapshot> };
  const streams = new Map<string, Snapshot>();
  for (const raw of addressed.events) {
    const event = parsePatchEvent(raw);
    expect(JSON.parse(serializePatchEvent(event))).toEqual(raw);
    const id = event.stream_id || "";
    streams.set(id, applyPatches(streams.get(id) ?? {}, [event]));
  }
  expect(Object.fromEntries(streams)).toEqual(addressed.expected);
});
