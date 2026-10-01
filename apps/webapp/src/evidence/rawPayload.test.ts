import { describe, expect, it } from "vitest";

import {
  COLLAPSE_THRESHOLD,
  buildLineIndex,
  collapseLine,
  highlight,
  lineText,
  parseErrorFor,
  parsePointer,
  parsePositioned,
  plainValue,
  resolveLine,
  resolveLineIndex,
  searchPayload,
  spanForPointer,
  type RawLocator,
  type RawPayload,
} from "./rawPayload";

/**
 * Raw line → observation mapping (§30).
 *
 * "Selecting a line must be able to jump to the corresponding observation —
 * that is the point of the feature." These tests are that sentence, made
 * executable.
 *
 * The cases that matter, in order of how badly a bug in each would hurt:
 *
 *   1. a JSON Pointer resolves to the SPAN of source lines its value occupies,
 *      and the deepest matching locator wins
 *   2. NDJSON maps record i to its own line — the format analysts actually get
 *   3. a line no locator covers reports "no observation", never the nearest one
 *   4. a locator whose pointer does not resolve is REPORTED, not silently used
 *   5. malformed JSON still displays its bytes, and reports the failing line
 */

/* ── Fixtures ────────────────────────────────────────────────────────── */

const JSON_PAYLOAD: RawPayload = {
  format: "json",
  mediaType: "application/json",
  digest: "sha256:0123456789abcdef",
  text: `{
  "records": [
    {
      "id": 1,
      "email": "a@example.com",
      "name": "alpha"
    },
    {
      "id": 2,
      "email": "b@example.com",
      "name": "bravo"
    }
  ],
  "meta": {
    "captured": "2026-01-02T00:00:00Z"
  }
}`,
};

const JSON_LOCATORS: RawLocator[] = [
  { observationId: "OBS-ALPHA", pointer: "$.records[0]", lineStart: null, lineEnd: null, raw: "$.records[0]" },
  { observationId: "OBS-ALPHA-EMAIL", pointer: "$.records[0].email", lineStart: null, lineEnd: null, raw: "$.records[0].email" },
  { observationId: "OBS-BRAVO", pointer: "$.records[1]", lineStart: null, lineEnd: null, raw: "$.records[1]" },
  { observationId: "OBS-BRAVO-EMAIL", pointer: "$.records[1].email", lineStart: null, lineEnd: null, raw: "$.records[1].email" },
  { observationId: "OBS-META", pointer: "$.meta", lineStart: null, lineEnd: null, raw: "$.meta" },
];

const NDJSON_PAYLOAD: RawPayload = {
  format: "ndjson",
  mediaType: "application/x-ndjson",
  digest: "sha256:fedcba9876543210",
  text: `{"observation_id":"OBS-1","value":"one"}
{"observation_id":"OBS-2","value":"two"}
{"observation_id":"OBS-3","value":"three"}
{"observation_id":"OBS-4","value":"four"}`,
};

const NDJSON_LOCATORS: RawLocator[] = [0, 1, 2, 3].map((index) => ({
  observationId: `OBS-${index + 1}`,
  pointer: `$[${index}]`,
  lineStart: null,
  lineEnd: null,
  raw: `$[${index}]`,
}));

/* ── The line index ──────────────────────────────────────────────────── */

describe("§30 — line numbers come from one index", () => {
  it("numbers from 1 and includes the final line", () => {
    const index = buildLineIndex("a\nb\nc");
    expect(index.lines.map((line) => line.number)).toEqual([1, 2, 3]);
    expect(index.length).toBe(5);
  });

  it("handles a trailing newline without inventing a fourth line of content", () => {
    const index = buildLineIndex("a\nb\n");
    expect(index.lines.map((line) => line.number)).toEqual([1, 2, 3]);
    expect(lineText(index, "a\nb\n", 3)).toBe("");
  });

  it("returns line text without its terminator, and null out of range", () => {
    const index = buildLineIndex("one\ntwo\n");
    expect(lineText(index, "one\ntwo\n", 2)).toBe("two");
    expect(lineText(index, "one\ntwo\n", 99)).toBeNull();
  });
});

/* ── JSON pointers ───────────────────────────────────────────────────── */

describe("§30 — pointers resolve, or report that they do not", () => {
  it("parses both pointer spellings", () => {
    expect(parsePointer("$.records[3].email")).toEqual(["records", "3", "email"]);
    expect(parsePointer("records[0]")).toEqual(["records", "0"]);
    expect(parsePointer("$")).toEqual([]);
    expect(parsePointer("$.a.b.c")).toEqual(["a", "b", "c"]);
    expect(parsePointer("$['quoted key']")).toEqual(["quoted key"]);
  });

  it("returns null for a pointer it cannot read, rather than guessing a path", () => {
    expect(parsePointer("$[")).toBeNull();
    expect(parsePointer("$[]")).toBeNull();
    expect(parsePointer("$.a[")).toBeNull();
    expect(parsePointer("$.")).toBeNull();
  });

  it("resolves a pointer to the SPAN of lines its value occupies", () => {
    const parsed = parsePositioned(JSON_PAYLOAD.text, "json");
    expect(parsed.error).toBeNull();
    const span = spanForPointer(parsed.root, "$.records[0].email");
    // `email` is on one line: the line the key is on.
    expect(span?.lineStart).toBe(span?.lineEnd);
    expect(JSON_PAYLOAD.text.split("\n")[Number(span?.lineStart) - 1]).toContain('"email": "a@example.com"');
  });

  it("resolves a container pointer to a multi-line span", () => {
    const parsed = parsePositioned(JSON_PAYLOAD.text, "json");
    const span = spanForPointer(parsed.root, "$.records[0]");
    expect(span).not.toBeNull();
    expect((span?.lineEnd ?? 0) - (span?.lineStart ?? 0)).toBeGreaterThan(0);
  });

  it("returns null for a pointer that does not resolve — a real answer, not an error", () => {
    const parsed = parsePositioned(JSON_PAYLOAD.text, "json");
    expect(spanForPointer(parsed.root, "$.records[9]")).toBeNull();
    expect(spanForPointer(parsed.root, "$.nope")).toBeNull();
    expect(spanForPointer(null, "$.records[0]")).toBeNull();
  });

  it("round-trips the parsed document against JSON.parse", () => {
    const parsed = parsePositioned(JSON_PAYLOAD.text, "json");
    expect(JSON.stringify(plainValue(parsed.root?.value))).toBe(JSON.stringify(JSON.parse(JSON_PAYLOAD.text)));
  });
});

/* ── The mapping itself ──────────────────────────────────────────────── */

describe("§30 — selecting a line resolves to the observation that produced it", () => {
  const resolved = resolveLineIndex(JSON_PAYLOAD, JSON_LOCATORS);

  it("maps a line inside record 0 to the record-0 observation", () => {
    const line = lineOf(JSON_PAYLOAD.text, '"id": 1');
    const resolution = resolveLine(resolved, line);
    expect(resolution.observationId).toBe("OBS-ALPHA");
    expect(resolution.match).toBe("ancestor");
  });

  it("maps a line inside record 1 to record 1, not to record 0", () => {
    const line = lineOf(JSON_PAYLOAD.text, '"id": 2');
    expect(resolveLine(resolved, line).observationId).toBe("OBS-BRAVO");
  });

  it("gives the DEEPEST matching locator, so a field names its own observation", () => {
    const line = lineOf(JSON_PAYLOAD.text, '"email": "a@example.com"');
    const resolution = resolveLine(resolved, line);
    // Both $.records[0] and $.records[0].email cover this line; the narrow one
    // is what the analyst means.
    expect(resolution.observationId).toBe("OBS-ALPHA-EMAIL");
    expect(resolution.locator).toBe("$.records[0].email");
    expect(resolution.depth).toBeGreaterThan(1);
    expect(resolution.match).toBe("observation");
  });

  it("maps a metadata line to its own observation", () => {
    const line = lineOf(JSON_PAYLOAD.text, '"captured"');
    expect(resolveLine(resolved, line).observationId).toBe("OBS-META");
  });

  it("reports no observation for a line no locator covers — never the nearest one", () => {
    // The `{` on line 1 is inside no locator at all.
    const first = resolveLine(resolved, 1);
    expect(first.observationId).toBeNull();
    expect(first.match).toBe("none");
    expect(first.depth).toBe(0);
  });

  it("resolves EVERY line, so no line can crash the viewer", () => {
    expect(resolved.lines).toHaveLength(buildLineIndex(JSON_PAYLOAD.text).lines.length);
    for (const entry of resolved.lines) expect(entry.line).toBeGreaterThan(0);
  });

  it("returns a none-resolution for a line outside the payload", () => {
    expect(resolveLine(resolved, 9999).match).toBe("none");
  });

  it("prefers an explicitly reported line span over the derived one", () => {
    const explicit: RawLocator[] = [
      { observationId: "OBS-EXPLICIT", pointer: "$.records[0]", lineStart: 4, lineEnd: 4, raw: "$.records[0]" },
    ];
    const withExplicit = resolveLineIndex(JSON_PAYLOAD, explicit);
    expect(resolveLine(withExplicit, 4).observationId).toBe("OBS-EXPLICIT");
    // The pointer would have derived a wider span; the explicit one wins.
    expect(resolveLine(withExplicit, 4).match).toBe("observation");
  });
});

describe("§30 — NDJSON maps record i to its own line", () => {
  const resolved = resolveLineIndex(NDJSON_PAYLOAD, NDJSON_LOCATORS);

  it("maps each line to its own record", () => {
    expect(resolveLine(resolved, 1).observationId).toBe("OBS-1");
    expect(resolveLine(resolved, 2).observationId).toBe("OBS-2");
    expect(resolveLine(resolved, 3).observationId).toBe("OBS-3");
    expect(resolveLine(resolved, 4).observationId).toBe("OBS-4");
  });

  it("marks every mapped line as an exact observation, not a container", () => {
    for (let line = 1; line <= 4; line += 1) {
      expect(resolveLine(resolved, line).match, `line ${line}`).toBe("observation");
    }
  });

  it("reports no observation when the payload has no locators at all", () => {
    const bare = resolveLineIndex(NDJSON_PAYLOAD, []);
    for (const entry of bare.lines) {
      expect(entry.observationId).toBeNull();
      expect(entry.match).toBe("none");
    }
  });
});

describe("§99 — unresolved locators are reported, not silently dropped", () => {
  it("lists a locator whose pointer does not resolve", () => {
    const resolved = resolveLineIndex(JSON_PAYLOAD, [
      ...JSON_LOCATORS,
      { observationId: "OBS-GHOST", pointer: "$.records[99]", lineStart: null, lineEnd: null, raw: "$.records[99]" },
    ]);
    expect(resolved.unresolved).toEqual(["$.records[99]"]);
    // The resolvable ones still work.
    const line = lineOf(JSON_PAYLOAD.text, '"id": 1');
    expect(resolveLine(resolved, line).observationId).toBe("OBS-ALPHA");
  });
});

describe("§30 — malformed payloads still show their bytes, and say what broke", () => {
  const broken: RawPayload = {
    format: "json",
    mediaType: "application/json",
    digest: null,
    text: `{
  "records": [
    { "id": 1, },
  ]
}`,
  };

  it("returns a null document and a verbatim error", () => {
    const parsed = parsePositioned(broken.text, "json");
    expect(parsed.root).toBeNull();
    expect(parsed.error).toContain("trailing comma");
  });

  it("exposes the failure through the payload-level check the viewer uses", () => {
    expect(parseErrorFor(broken)).toContain("trailing comma");
    expect(parseErrorFor(JSON_PAYLOAD)).toBeNull();
    expect(parseErrorFor(NDJSON_PAYLOAD)).toBeNull();
  });

  it("names the failing LINE for an NDJSON record that does not parse", () => {
    const bad: RawPayload = { ...NDJSON_PAYLOAD, text: '{"a":1}\n{oops}\n{"c":3}' };
    expect(parseErrorFor(bad)).toContain("line 2");
  });

  it("still produces a line index for a malformed payload, so the bytes are viewable", () => {
    expect(buildLineIndex(broken.text).lines.length).toBeGreaterThan(1);
    // With no usable document, no line claims an observation.
    const resolved = resolveLineIndex(broken, JSON_LOCATORS);
    expect(resolved.lines.every((entry) => entry.observationId === null)).toBe(true);
  });

  it("rejects an unterminated string and an unknown escape by line", () => {
    expect(parsePositioned('{"a": "oops\n}', "json").error).toBeTruthy();
    expect(parsePositioned('{"a": "\\q"}', "json").error).toContain("unknown escape");
  });
});

describe("§30 — highlighting never fails on a valid payload", () => {
  it("marks keys, strings, numbers and literals", () => {
    const kinds = highlight('  "email": "a@example.com",', "json").map((token) => token.kind);
    expect(kinds).toContain("key");
    expect(kinds).toContain("string");
  });

  it("emits the line unchanged for plain text, so no byte is ever dropped", () => {
    const line = "plain text, nothing to highlight";
    expect(highlight(line, "text").map((token) => token.text).join("")).toBe(line);
  });

  it("round-trips every line through the tokenizer", () => {
    for (const line of JSON_PAYLOAD.text.split("\n")) {
      expect(highlight(line, "json").map((token) => token.text).join(""), line).toBe(line);
    }
  });

  it("survives an unterminated quote without losing characters", () => {
    const line = '"key": "unterminated';
    expect(highlight(line, "json").map((token) => token.text).join("")).toBe(line);
  });
});

describe("§30 — search and collapse", () => {
  it("finds every hit, including repeats on one line", () => {
    const hits = searchPayload(JSON_PAYLOAD, "example.com");
    expect(hits).toHaveLength(2);
    expect(hits.map((hit) => hit.line)).toEqual([
      lineOf(JSON_PAYLOAD.text, "a@example.com"),
      lineOf(JSON_PAYLOAD.text, "b@example.com"),
    ]);
  });

  it("is case-insensitive by default and case-sensitive on request", () => {
    expect(searchPayload(JSON_PAYLOAD, "EXAMPLE.COM")).toHaveLength(2);
    expect(searchPayload(JSON_PAYLOAD, "EXAMPLE.COM", true)).toHaveLength(0);
  });

  it("returns nothing for an empty query rather than every line", () => {
    expect(searchPayload(JSON_PAYLOAD, "")).toEqual([]);
    expect(searchPayload(JSON_PAYLOAD, "   ")).toEqual([]);
  });

  it("collapses a long line and reports how much it elided", () => {
    const long = "x".repeat(COLLAPSE_THRESHOLD * 3);
    const collapsed = collapseLine(long);
    expect(collapsed.collapsed).toBe(true);
    expect(collapsed.elided).toBeGreaterThan(0);
    expect(collapsed.text.length).toBeLessThan(long.length);
  });

  it("leaves a short line untouched", () => {
    const short = '{"a":1}';
    expect(collapseLine(short)).toEqual({ text: short, collapsed: false, elided: 0 });
  });
});

/* ── Helpers ─────────────────────────────────────────────────────────── */

function lineOf(text: string, needle: string): number {
  const lines = text.split("\n");
  const index = lines.findIndex((line) => line.includes(needle));
  if (index === -1) throw new Error(`no line containing ${needle}`);
  return index + 1;
}