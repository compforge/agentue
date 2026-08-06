import { describe, expect, test } from "bun:test";

import { applyPatches, parseUIModel, type PatchInput, type Snapshot } from "@compforge/agentue/ui";

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
