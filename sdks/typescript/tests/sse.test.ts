import { describe, expect, test } from "bun:test";

import { decodeSse, encodeSse } from "../src/index.ts";

describe("SSE binding", () => {
  test("encodes a transport cursor", () => {
    expect(encodeSse({ op: "ping", seq: 3, ts: 123 }, { eventId: "cursor-1" })).toBe(
      'id: cursor-1\ndata: {"op":"ping","seq":3,"ts":123}\n\n',
    );
  });

  test("splits multiline raw data", () => {
    expect(encodeSse("line-1\nline-2")).toBe("data: line-1\ndata: line-2\n\n");
  });

  test("rejects multiline event IDs", () => {
    expect(() => encodeSse({ op: "ping", seq: 0, ts: 1 }, { eventId: "bad\nid" })).toThrow(
      "must not contain newlines",
    );
  });

  test("decodes multiline JSON data", () => {
    expect(decodeSse('id: cursor-1\ndata: {"op":"ping",\ndata: "seq":3,"ts":123}\n\n')).toEqual({
      eventId: "cursor-1",
      event: { op: "ping", seq: 3, ts: 123 },
    });
  });
});
