import { describe, expect, it } from "vitest";

import { parseStreamChunk } from "./stream";

describe("parseStreamChunk", () => {
  it("parses an event with a JSON payload", () => {
    const parsed = parseStreamChunk('event: entity.updated\ndata: {"entity_id":"E1"}\n\n');
    expect(parsed).toEqual({ event: "entity.updated", data: { entity_id: "E1" } });
  });

  it("skips heartbeats/comments and returns null for empty input", () => {
    expect(parseStreamChunk(": ping\n\n")).toBeNull();
    expect(parseStreamChunk("")).toBeNull();
    expect(parseStreamChunk("   \n  ")).toBeNull();
  });

  it("tolerates CRLF line endings", () => {
    const parsed = parseStreamChunk('event: pipeline.advance\r\ndata: {"n":1}\r\n\r\n');
    expect(parsed?.event).toBe("pipeline.advance");
    expect(parsed?.data).toEqual({ n: 1 });
  });

  it("returns null-compatible data when only an event header is present", () => {
    const parsed = parseStreamChunk("event: __resume__\ndata: {\"replayed\": 0}\n\n");
    expect(parsed?.event).toBe("__resume__");
  });
});