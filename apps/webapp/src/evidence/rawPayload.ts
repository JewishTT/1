/**
 * Raw payloads and the line ↔ observation mapping (§30).
 *
 * THE FEATURE: selecting a line in the raw view jumps to the observation that
 * produced it.
 *
 * That is the whole point of a raw viewer in this system, and it is the reason
 * §30 exists at all — a syntax-highlighted text pane is a `textarea` with extra
 * steps. What makes it evidence is being able to say "this byte range is
 * observation OBS-4471" and act on it.
 *
 * How the mapping works, and why it is deterministic:
 *
 *   1. `buildLineIndex` splits the payload into lines with byte offsets. Every
 *      line number in the UI comes from this index, so line 1 is always the
 *      first line and a count can never drift.
 *   2. A locator is a JSON Pointer (`$.records[3].email`) into the parsed
 *      document, plus the observation id the platform tied to it. Walking the
 *      pointer against the parsed value gives the SPAN of source lines that
 *      pointer's value occupies — which requires knowing where each value was
 *      written, so the parser tracks positions instead of returning plain JSON.
 *   3. `resolveLineToObservation` returns the DEEPEST locator whose span
 *      contains the line. Deepest, because `$` contains every line and
 *      `$.records[3].email` contains one; the analyst means the specific one.
 *
 * §99: a payload with no locators, or a locator that does not resolve, reports
 * "no observation reported for this line". It never guesses the nearest one.
 * §64: the position-tracking parser is written here rather than pulled in —
 * adding a streaming JSON parser for this would be a dependency for a
 * thousand lines of code, and the failure mode of hand-rolling (a wrong offset)
 * is caught by tests rather than by a version bump.
 */

export type RawFormat = "json" | "ndjson" | "text";

export interface RawPayload {
  /** What the viewer should parse it as. */
  format: RawFormat;
  /** The exact bytes the platform returned, unmodified. */
  text: string;
  /** Media type as the platform reported it. Null ⇒ not reported. */
  mediaType: string | null;
  /** Content digest, when the record carries one. */
  digest: string | null;
}

/** One locator: an observation id and where its value lives in the payload. */
export interface RawLocator {
  observationId: string;
  /** JSON Pointer into the parsed document. */
  pointer: string;
  /**
   * 1-based inclusive line span. Present only when the platform reported
   * explicit line numbers; otherwise the span is derived by walking `pointer`.
   */
  lineStart: number | null;
  lineEnd: number | null;
  /** The locator verbatim, for display. */
  raw: string;
}

/* ── Line index ──────────────────────────────────────────────────────── */

export interface LineSpan {
  /** 1-based. */
  number: number;
  /** Byte offset of the line's first character. */
  start: number;
  /** Byte offset one past the line's last character (newline excluded). */
  end: number;
}

export interface LineIndex {
  lines: ReadonlyArray<LineSpan>;
  /** Total bytes. */
  length: number;
}

export function buildLineIndex(text: string): LineIndex {
  const lines: LineSpan[] = [];
  let start = 0;
  let number = 1;
  for (let index = 0; index <= text.length; index += 1) {
    if (index === text.length) {
      if (start <= index) lines.push({ number, start, end: index });
      break;
    }
    if (text.charCodeAt(index) === 10) {
      lines.push({ number, start, end: index });
      number += 1;
      start = index + 1;
    }
  }
  return { lines, length: text.length };
}

/** The text of one line, without its terminator. Null when out of range. */
export function lineText(index: LineIndex, text: string, line: number): string | null {
  const span = index.lines.find((entry) => entry.number === line);
  if (!span) return null;
  return text.slice(span.start, span.end);
}

/* ── Position-tracking JSON parse ────────────────────────────────────── */

/** A parsed value, with the source span it occupies. */
export interface PositionedValue {
  value: unknown;
  /** 1-based inclusive line span of this value in the source text. */
  lineStart: number;
  lineEnd: number;
}

export interface ParseResult {
  /** `null` when the payload is not parseable as the declared format. */
  root: PositionedValue | null;
  /** The parse error, verbatim. Never swallowed — a raw viewer that silently
   *  shows an empty document for malformed JSON is worse than useless. */
  error: string | null;
}

/**
 * A small JSON parser that records line spans.
 *
 * NDJSON is parsed line-by-line and each line's value is given that line's
 * span, which is what makes "line 412 is observation N" trivially true for the
 * format analysts actually receive.
 *
 * The grammar is RFC 8259 for practical purposes: objects, arrays, strings with
 * escapes, numbers, `true`/`false`/`null`. Trailing commas are a parse error,
 * because a payload that has them is malformed and saying so is the point.
 */
export function parsePositioned(text: string, format: RawFormat): ParseResult {
  if (format === "text") {
    return { root: { value: text, lineStart: 1, lineEnd: text.split("\n").length }, error: null };
  }
  if (format === "ndjson") {
    return parseNdjson(text);
  }
  try {
    const parser = new PositionedParser(text);
    const root = parser.parseDocument();
    return { root, error: null };
  } catch (cause) {
    return { root: null, error: cause instanceof Error ? cause.message : "payload is not valid JSON" };
  }
}

function parseNdjson(text: string): ParseResult {
  const positioned: PositionedValue[] = [];
  const index = buildLineIndex(text);
  const lines = text.split("\n");

  for (let position = 0; position < lines.length; position += 1) {
    const raw = lines[position];
    if (raw.trim() === "") continue;
    try {
      const parser = new PositionedParser(raw);
      // Each record is positioned at its own line, so record i's span IS line
      // i+1 — which is what makes "this line is that observation" trivially
      // true for the format analysts actually receive.
      const value = parser.parseDocument();
      positioned.push({ value: value.value, lineStart: position + 1, lineEnd: position + 1 });
    } catch (cause) {
      const span = index.lines[position];
      return {
        root: null,
        error: `line ${span?.number ?? position + 1}: ${
          cause instanceof Error ? cause.message : "not valid JSON"
        }`,
      };
    }
  }

  return { root: { value: positioned, lineStart: 1, lineEnd: lines.length }, error: null };
}

/**
 * Unwrap a positioned document to plain JSON.
 *
 * The parsed tree carries a `{ value, lineStart, lineEnd }` wrapper at every
 * node, because that is what makes a pointer resolvable to a line span. Callers
 * who want the document rather than its positions — a test comparing against
 * `JSON.parse`, a consumer diffing two payloads — unwrap it here rather than
 * each reinventing the walk.
 */
export function plainValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(plainValue);
  if (isPositioned(value)) return plainValue(value.value);
  if (typeof value === "object" && value !== null) {
    const out: Record<string, unknown> = {};
    for (const [key, entry] of Object.entries(value as Record<string, unknown>)) out[key] = plainValue(entry);
    return out;
  }
  return value;
}

function isPositioned(value: unknown): value is PositionedValue {
  return (
    typeof value === "object" &&
    value !== null &&
    "value" in value &&
    typeof (value as PositionedValue).lineStart === "number" &&
    typeof (value as PositionedValue).lineEnd === "number"
  );
}

/**
 * A JSON Pointer path: `$.records[3].email` → `["records", "3", "email"]`.
 *
 * The `$` prefix is optional so a locator written either way resolves. A pointer
 * the platform sent in some other syntax returns null rather than a guess.
 */
export function parsePointer(pointer: string): string[] | null {
  const trimmed = pointer.trim();
  const body = trimmed.startsWith("$") ? trimmed.slice(1) : trimmed;
  if (body === "") return [];
  const out: string[] = [];
  let cursor = 0;
  while (cursor < body.length) {
    const char = body[cursor];
    if (char === ".") {
      cursor += 1;
      // A trailing dot is a malformed locator, not the root: `$` is the root,
      // and `$.` is a typo. Reporting it beats resolving it to something.
      if (cursor >= body.length) return null;
      continue;
    }
    if (char === "[") {
      const close = body.indexOf("]", cursor);
      if (close === -1) return null;
      const inner = body.slice(cursor + 1, close).replace(/^['"]|['"]$/g, "");
      if (inner === "") return null;
      out.push(inner);
      cursor = close + 1;
      continue;
    }
    // A dotted segment ends at the next `.` OR the next `[` — `records[3]` is
    // the key `records` followed by the index 3, not the key `records[3]`.
    // Getting this wrong makes every array path silently fail to resolve, which
    // is why the parser and the test both insist on the split.
    const nextDot = body.indexOf(".", cursor);
    const nextBracket = body.indexOf("[", cursor);
    const boundary = [nextDot, nextBracket].filter((index) => index !== -1).sort((a, b) => a - b)[0];
    const segment = boundary === undefined ? body.slice(cursor) : body.slice(cursor, boundary);
    if (segment === "") return null;
    out.push(segment);
    cursor = boundary === undefined ? body.length : boundary;
  }
  return out;
}

/**
 * Resolve a pointer against a positioned document, returning the span of source
 * lines its value occupies. Null when the pointer does not resolve — which is a
 * real answer, not an error.
 */
export function spanForPointer(root: PositionedValue | null, pointer: string): { lineStart: number; lineEnd: number } | null {
  if (root === null) return null;
  const path = parsePointer(pointer);
  if (path === null) return null;

  let current: { value: unknown; lineStart: number; lineEnd: number } = root;
  for (const segment of path) {
    if (Array.isArray(current.value)) {
      const position = Number(segment);
      if (!Number.isInteger(position)) return null;
      // NDJSON records, and JSON array elements, are positioned nodes — so the
      // element's OWN `.value` is the next thing to descend into. Reading the
      // wrapper as the value here is what silently breaks every array path.
      const record = (current.value as unknown[])[position] as PositionedValue | undefined;
      if (record === undefined || typeof record.lineStart !== "number") return null;
      current = { value: record.value, lineStart: record.lineStart, lineEnd: record.lineEnd };
      continue;
    }
    if (typeof current.value === "object" && current.value !== null) {
      const record = current.value as Record<string, PositionedValue>;
      const next = record[segment];
      if (next === undefined) return null;
      current = { value: next.value, lineStart: next.lineStart, lineEnd: next.lineEnd };
      continue;
    }
    return null;
  }
  return { lineStart: current.lineStart, lineEnd: current.lineEnd };
}

/* ── The mapping ─────────────────────────────────────────────────────── */

export type LineMatch = "observation" | "ancestor" | "none";

export interface LineResolution {
  /** 1-based line number that was asked about. */
  line: number;
  observationId: string | null;
  /** The locator that matched, verbatim. */
  locator: string | null;
  /** `observation` when the locator's own span covers the line; `ancestor` when a
   *  broader locator does and no narrower one does. */
  match: LineMatch;
  /** How many locators covered this line. Useful for the status line. */
  depth: number;
}

export interface ResolvedLineIndex {
  lines: ReadonlyArray<LineResolution>;
  /** Locators whose pointer did not resolve. Reported, not silently dropped. */
  unresolved: ReadonlyArray<string>;
}

/**
 * Resolve every line of the payload to an observation.
 *
 * Built once per payload and reused by the viewer, so scrolling a large document
 * is not a re-parse. Cost is O(lines × matchingLocators) in the worst case and
 * the locator list is small — the platform emits one locator per observation it
 * extracted, not one per line.
 */
export function resolveLineIndex(payload: RawPayload, locators: ReadonlyArray<RawLocator>): ResolvedLineIndex {
  const index = buildLineIndex(payload.text);
  const parsed = parsePositioned(payload.text, payload.format);
  const unresolved: string[] = [];

  const spans = locators.map((locator) => {
    const explicit =
      locator.lineStart !== null && locator.lineEnd !== null
        ? { lineStart: locator.lineStart, lineEnd: locator.lineEnd }
        : spanForPointer(parsed.root, locator.pointer);
    if (explicit === null) unresolved.push(locator.raw);
    return { locator, span: explicit };
  });

  const resolvable = spans.filter((entry) => entry.span !== null);

  const lines: LineResolution[] = index.lines.map((line) => {
    const covering = resolvable.filter(
      (entry) => entry.span !== null && line.number >= entry.span.lineStart && line.number <= entry.span.lineEnd,
    );
    if (covering.length === 0) {
      return { line: line.number, observationId: null, locator: null, match: "none", depth: 0 };
    }
    // Deepest wins: the narrowest span is the one the analyst means.
    const deepest = covering.reduce((best, entry) => {
      const bestWidth = (best.span?.lineEnd ?? 0) - (best.span?.lineStart ?? 0);
      const width = (entry.span?.lineEnd ?? 0) - (entry.span?.lineStart ?? 0);
      return width < bestWidth ? entry : best;
    });
    const match: LineMatch =
      deepest.span !== null && deepest.span.lineStart === deepest.span.lineEnd ? "observation" : "ancestor";
    return {
      line: line.number,
      observationId: deepest.locator.observationId,
      locator: deepest.locator.raw,
      match,
      depth: covering.length,
    };
  });

  return { lines, unresolved };
}

/** The resolution for one line, for a click. */
export function resolveLine(
  resolved: ResolvedLineIndex,
  line: number,
): LineResolution {
  return (
    resolved.lines.find((entry) => entry.line === line) ?? {
      line,
      observationId: null,
      locator: null,
      match: "none",
      depth: 0,
    }
  );
}

/** Does this payload's format parse? For the viewer's honest error state. */
export function parseErrorFor(payload: RawPayload): string | null {
  if (payload.format === "text") return null;
  return parsePositioned(payload.text, payload.format).error;
}

/* ── A minimal position-tracking JSON parser ─────────────────────────── */

class PositionedParser {
  private index = 0;
  private line = 1;

  constructor(private readonly text: string) {}

  parseDocument(): PositionedValue {
    this.skipWhitespace();
    const value = this.parseValue();
    this.skipWhitespace();
    if (this.index < this.text.length) {
      throw new Error(`unexpected ${JSON.stringify(this.peek())} at line ${this.line}`);
    }
    return value;
  }

  private parseValue(): PositionedValue {
    this.skipWhitespace();
    const lineStart = this.line;
    const value = this.parseScalar();
    return { value, lineStart, lineEnd: this.line };
  }

  private parseScalar(): unknown {
    const char = this.peek();
    if (char === "{") return this.parseObject();
    if (char === "[") return this.parseArray();
    if (char === '"') return this.parseString();
    return this.parseLiteral();
  }

  private parseObject(): Record<string, PositionedValue> {
    this.expect("{");
    const out: Record<string, PositionedValue> = {};
    this.skipWhitespace();
    if (this.peek() === "}") {
      this.advance();
      return out;
    }
    for (;;) {
      this.skipWhitespace();
      const key = this.parseString();
      this.skipWhitespace();
      this.expect(":");
      out[key] = this.parseValue();
      this.skipWhitespace();
      const next = this.peek();
      if (next === ",") {
        this.advance();
        this.skipWhitespace();
        // A trailing comma is malformed JSON; saying so beats silently
        // accepting a payload the platform would reject.
        if (this.peek() === "}") throw new Error(`trailing comma at line ${this.line}`);
        continue;
      }
      if (next === "}") {
        this.advance();
        return out;
      }
      throw new Error(`expected "," or "}" at line ${this.line}, found ${JSON.stringify(next ?? "end of input")}`);
    }
  }

  private parseArray(): unknown[] {
    this.expect("[");
    // Elements are stored POSITIONED, exactly as object members are. Storing the
    // bare value here would make `$.records[0]` unresolvable, because there would
    // be no line span to attach to the element.
    const out: unknown[] = [];
    this.skipWhitespace();
    if (this.peek() === "]") {
      this.advance();
      return out;
    }
    for (;;) {
      out.push(this.parseValue());
      this.skipWhitespace();
      const next = this.peek();
      if (next === ",") {
        this.advance();
        this.skipWhitespace();
        if (this.peek() === "]") throw new Error(`trailing comma at line ${this.line}`);
        continue;
      }
      if (next === "]") {
        this.advance();
        return out;
      }
      throw new Error(`expected "," or "]" at line ${this.line}, found ${JSON.stringify(next ?? "end of input")}`);
    }
  }

  private parseString(): string {
    this.expect('"');
    let out = "";
    for (;;) {
      const char = this.text[this.index];
      if (char === undefined) throw new Error(`unterminated string at line ${this.line}`);
      this.advance();
      if (char === '"') return out;
      if (char !== "\\") {
        out += char;
        continue;
      }
      const escape = this.text[this.index];
      if (escape === undefined) throw new Error(`unterminated escape at line ${this.line}`);
      this.advance();
      switch (escape) {
        case '"':
          out += '"';
          break;
        case "\\":
          out += "\\";
          break;
        case "/":
          out += "/";
          break;
        case "b":
          out += "\b";
          break;
        case "f":
          out += "\f";
          break;
        case "n":
          out += "\n";
          break;
        case "r":
          out += "\r";
          break;
        case "t":
          out += "\t";
          break;
        case "u": {
          const hex = this.text.slice(this.index, this.index + 4);
          if (!/^[0-9a-fA-F]{4}$/.test(hex)) throw new Error(`bad unicode escape at line ${this.line}`);
          out += String.fromCharCode(Number.parseInt(hex, 16));
          for (let step = 0; step < 4; step += 1) this.advance();
          break;
        }
        default:
          throw new Error(`unknown escape \\${escape} at line ${this.line}`);
      }
    }
  }

  private parseLiteral(): unknown {
    const start = this.index;
    while (this.index < this.text.length && /[-+0-9.eE]/.test(this.text[this.index] as string)) {
      this.advance();
    }
    const word = this.text.slice(start, this.index);
    if (word === "true") return true;
    if (word === "false") return false;
    if (word === "null") return null;
    if (/^-?\d+(\.\d+)?([eE][-+]?\d+)?$/.test(word)) return Number(word);
    if (word === "") throw new Error(`unexpected ${JSON.stringify(this.peek())} at line ${this.line}`);
    throw new Error(`unexpected token ${JSON.stringify(word)} at line ${this.line}`);
  }

  private skipWhitespace(): void {
    for (;;) {
      const char = this.text[this.index];
      if (char === undefined) return;
      if (char === "\n") {
        this.line += 1;
        this.advance();
        continue;
      }
      if (char === " " || char === "\t" || char === "\r") {
        this.advance();
        continue;
      }
      return;
    }
  }

  private peek(): string | undefined {
    return this.text[this.index];
  }

  private advance(): void {
    this.index += 1;
  }

  private expect(char: string): void {
    if (this.text[this.index] !== char) {
      throw new Error(`expected ${JSON.stringify(char)} at line ${this.line}`);
    }
    this.advance();
  }
}

/* ── Plain-text highlighting (no dependency, §64) ────────────────────── */

export type TokenKind = "key" | "string" | "number" | "literal" | "punctuation";

export interface HighlightToken {
  kind: TokenKind;
  text: string;
}

/**
 * A token pass for display only.
 *
 * It is deliberately NOT a parser: highlighting must never be able to fail on a
 * payload the platform considers valid, so an unrecognised byte is emitted as
 * `punctuation` rather than dropped. The authoritative parse lives in
 * `parsePositioned` and its error is what the viewer reports.
 */
export function highlight(line: string, format: RawFormat): HighlightToken[] {
  if (format === "text" || line === "") return line === "" ? [] : [{ kind: "punctuation", text: line }];
  const out: HighlightToken[] = [];
  let index = 0;

  while (index < line.length) {
    const char = line[index] as string;

    if (char === '"') {
      let end = index + 1;
      while (end < line.length) {
        if (line[end] === "\\") {
          end += 2;
          continue;
        }
        if (line[end] === '"') break;
        end += 1;
      }
      end = Math.min(end + 1, line.length);
      const isKey = /^\s*:/.test(line.slice(end));
      out.push({ kind: isKey ? "key" : "string", text: line.slice(index, end) });
      index = end;
      continue;
    }

    if (/[-+0-9]/.test(char)) {
      let end = index;
      while (end < line.length && /[-+0-9.eE]/.test(line[end] as string)) end += 1;
      out.push({ kind: "number", text: line.slice(index, end) });
      index = end;
      continue;
    }

    const literal = /^(true|false|null)\b/.exec(line.slice(index));
    if (literal) {
      out.push({ kind: "literal", text: literal[0] });
      index += literal[0].length;
      continue;
    }

    if (char === " " || char === "\t") {
      let end = index;
      while (end < line.length && (line[end] === " " || line[end] === "\t")) end += 1;
      out.push({ kind: "punctuation", text: line.slice(index, end) });
      index = end;
      continue;
    }

    out.push({ kind: "punctuation", text: char });
    index += 1;
  }

  return out;
}

/* ── Search and collapse ─────────────────────────────────────────────── */

export interface SearchHit {
  line: number;
  /** 0-based column of the first match on that line. */
  column: number;
  text: string;
}

export function searchPayload(
  payload: RawPayload,
  query: string,
  caseSensitive = false,
): SearchHit[] {
  const trimmed = query.trim();
  const needle = caseSensitive ? trimmed : trimmed.toLowerCase();
  // An empty or whitespace-only query is not a match-all: it is no query.
  if (needle === "") return [];
  const lines = payload.text.split("\n");
  const hits: SearchHit[] = [];
  lines.forEach((line, offset) => {
    const haystack = caseSensitive ? line : line.toLowerCase();
    let from = 0;
    for (;;) {
      const at = haystack.indexOf(needle, from);
      if (at === -1) break;
      hits.push({ line: offset + 1, column: at, text: line });
      from = at + Math.max(1, needle.length);
    }
  });
  return hits;
}

/**
 * Collapse long lines rather than the whole document.
 *
 * §30 asks for "collapse", and the useful form of it is per-line: an NDJSON
 * payload with one enormous line is unreadable without it, while a document-wide
 * collapse would just hide the thing the analyst came to look at.
 */
export const COLLAPSE_THRESHOLD = 240;

export interface CollapsedLine {
  text: string;
  collapsed: boolean;
  /** How many characters were elided. */
  elided: number;
}

export function collapseLine(line: string, threshold = COLLAPSE_THRESHOLD): CollapsedLine {
  if (line.length <= threshold) return { text: line, collapsed: false, elided: 0 };
  const head = line.slice(0, Math.floor(threshold / 2));
  const tail = line.slice(-Math.floor(threshold / 2));
  return { text: `${head} … ${tail}`, collapsed: true, elided: line.length - threshold };
}