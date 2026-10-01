import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Badge } from "../ui/Badge";
import { Button, IconButton } from "../ui/Button";
import { Input } from "../ui/Input";
import { Tooltip } from "../ui/Overlay";
import type { WorkspaceSelection } from "../workspace/types";
import {
  COLLAPSE_THRESHOLD,
  buildLineIndex,
  collapseLine,
  highlight,
  lineText,
  parseErrorFor,
  resolveLine,
  resolveLineIndex,
  searchPayload,
  type LineResolution,
  type RawLocator,
  type RawPayload,
} from "./rawPayload";
import "./evidence.css";

/**
 * RawViewer (§30).
 *
 * JSON, NDJSON and text. Line numbers, highlighting, search, copy, collapse —
 * and the thing that makes it evidence rather than a text pane:
 *
 *   SELECTING A LINE JUMPS TO THE OBSERVATION.
 *
 * `resolveLineIndex` is computed once per payload and every line carries its
 * observation id. Clicking a line calls `onJumpToObservation` with the platform's
 * id; the workspace writes it to the global selection (§7) and the inspector
 * reads it. The line itself reports which observation it belongs to, so the
 * feature is visible even before you click: a line with a known observation says
 * so on the row.
 *
 * §68: the line list is windowed. A 40,000-line NDJSON payload renders its
 * visible slice plus a spacer, and `aria-rowcount` still reports the true size,
 * so assistive technology is told the whole truth while the DOM holds a screen
 * of it.
 *
 * §67: the line list is a `role="grid"` with a roving tabindex, so a keyboard
 * user can walk lines with the arrow keys and activate one with Enter — without
 * a pointer, and without every line being a tab stop.
 *
 * §99: an unparseable payload says exactly what failed and at which line, and
 * the raw bytes are still shown. A raw viewer that refuses to display malformed
 * evidence is hiding the evidence.
 */

export interface RawViewerProps {
  payload: RawPayload;
  locators: ReadonlyArray<RawLocator>;
  /** Jump to the observation a line belongs to. §30's whole point. */
  onJumpToObservation: (selection: WorkspaceSelection, line: number) => void;
  /** The observation the workspace has selected, so its lines are marked. */
  selectedObservationId: string | null;
  onCopyStateChange?: (copied: boolean) => void;
}

const ROW_HEIGHT = 18;
const VIEWPORT_ROWS = 30;
const OVERSCAN = 10;

export function RawViewer({
  payload,
  locators,
  onJumpToObservation,
  selectedObservationId,
}: RawViewerProps) {
  const [query, setQuery] = useState("");
  const [caseSensitive, setCaseSensitive] = useState(false);
  const [collapseLong, setCollapseLong] = useState(true);
  const [selectedLine, setSelectedLine] = useState<number | null>(null);
  const [cursorLine, setCursorLine] = useState(0);
  const [offset, setOffset] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  const lineIndex = useMemo(() => buildLineIndex(payload.text), [payload.text]);
  const resolved = useMemo(() => resolveLineIndex(payload, locators), [payload, locators]);
  const hits = useMemo(
    () => searchPayload(payload, query, caseSensitive),
    [payload, query, caseSensitive],
  );
  const hitLines = useMemo(() => new Set(hits.map((hit) => hit.line)), [hits]);
  const parseError = useMemo(() => parseErrorFor(payload), [payload]);

  const total = lineIndex.lines.length;
  const first = Math.max(0, Math.floor(offset / ROW_HEIGHT) - OVERSCAN);
  const last = Math.min(total, first + VIEWPORT_ROWS + OVERSCAN * 2);

  const copy = useCallback(() => {
    void navigator.clipboard?.writeText(payload.text).catch(() => undefined);
  }, [payload.text]);

  const activateLine = useCallback(
    (line: number) => {
      const resolution: LineResolution = resolveLine(resolved, line);
      setSelectedLine(line);
      setCursorLine(Math.max(0, line - 1));
      if (resolution.observationId === null) return;
      onJumpToObservation(
        { kind: "Observation", id: resolution.observationId },
        line,
      );
    },
    [resolved, onJumpToObservation],
  );

  // Arrow-key line navigation with a roving tabindex (§67).
  const onKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      const last = total - 1;
      let next: number | null = null;
      if (event.key === "ArrowDown") next = Math.min(last, cursorLine + 1);
      else if (event.key === "ArrowUp") next = Math.max(0, cursorLine - 1);
      else if (event.key === "PageDown") next = Math.min(last, cursorLine + VIEWPORT_ROWS);
      else if (event.key === "PageUp") next = Math.max(0, cursorLine - VIEWPORT_ROWS);
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = last;
      else if (event.key === "Enter" && cursorLine >= 0) {
        event.preventDefault();
        activateLine(cursorLine + 1);
        return;
      }
      if (next === null) return;
      event.preventDefault();
      setCursorLine(next);
      // Keep the cursor inside the rendered window without a scrollIntoView, so
      // a fast walk does not fight the virtualiser.
      const rowTop = next * ROW_HEIGHT;
      const rowBottom = rowTop + ROW_HEIGHT;
      setOffset((current) => (rowTop < current ? rowTop : rowBottom > current + VIEWPORT_ROWS * ROW_HEIGHT ? rowTop : current));
    },
    [total, cursorLine, activateLine],
  );

  useEffect(() => {
    // Selecting an object from outside the viewer scrolls to its first line.
    if (selectedObservationId === null) return;
    const match = resolved.lines.find((entry) => entry.observationId === selectedObservationId);
    if (match === undefined) return;
    setSelectedLine(match.line);
    setOffset(Math.max(0, (match.line - 1) * ROW_HEIGHT - Math.floor(VIEWPORT_ROWS / 2) * ROW_HEIGHT));
  }, [selectedObservationId, resolved.lines]);

  const selectedResolution = selectedLine === null ? null : resolveLine(resolved, selectedLine);

  return (
    <section className="ui-raw" aria-label="Raw payload" data-testid="raw-viewer" data-format={payload.format}>
      <header className="ui-raw-toolbar" role="toolbar" aria-label="Raw payload controls">
        <Input
          label="Search payload"
          mono
          value={query}
          placeholder="text in the payload"
          adornment={<IconSearch />}
          onChange={(event) => {
            setQuery(event.target.value);
            if (event.target.value !== "") setOffset(0);
          }}
          hint={query === "" ? `${total} lines` : `${hits.length} hit(s) on ${hitLines.size} line(s)`}
        />

        <label className="ui-check">
          <input
            type="checkbox"
            checked={caseSensitive}
            onChange={(event) => setCaseSensitive(event.target.checked)}
            data-testid="raw-case-sensitive"
          />
          Case sensitive
        </label>

        <label className="ui-check">
          <input
            type="checkbox"
            checked={collapseLong}
            onChange={(event) => setCollapseLong(event.target.checked)}
            data-testid="raw-collapse"
          />
          Collapse long lines
        </label>

        <div className="ui-raw-toolbar-grow" />

        <Tooltip content={`Copy the whole payload (${lineIndex.length} bytes)`}>
          <Button size="sm" icon="copy" onClick={copy} data-testid="raw-copy">
            Copy
          </Button>
        </Tooltip>
        <Tooltip content={`Lines longer than ${COLLAPSE_THRESHOLD} characters are elided`}>
          <span className="ui-rail-hint" data-testid="raw-meta">
            {payload.format.toUpperCase()} · {lineIndex.length} B
            {payload.digest === null ? "" : ` · ${payload.digest.slice(0, 12)}`}
          </span>
        </Tooltip>
      </header>

      {parseError !== null ? (
        <div className="ui-raw-error" role="alert" data-testid="raw-parse-error">
          <Badge tone="danger" role="classification">
            parse failed
          </Badge>
          <span className="ui-body" data-testid="raw-parse-error-message">
            {parseError}
          </span>
          <span className="ui-rail-hint">
            The bytes below are shown exactly as received. The line map is unavailable
            for this payload, so no line can be traced to an observation.
          </span>
        </div>
      ) : null}

      {resolved.unresolved.length > 0 ? (
        <p className="ui-raw-note" data-testid="raw-unresolved">
          {resolved.unresolved.length} locator(s) did not resolve against this payload:{" "}
          <span className="ui-mono">{resolved.unresolved.slice(0, 3).join(", ")}</span>
        </p>
      ) : null}

      <div
        className="ui-raw-lines ui-scroll"
        ref={listRef}
        role="grid"
        aria-label="Payload lines"
        aria-rowcount={total}
        tabIndex={0}
        onKeyDown={onKeyDown}
        data-testid="raw-lines"
      >
        <div className="ui-raw-lines-inner" style={{ paddingTop: `${first * ROW_HEIGHT}px` }}>
          {lineIndex.lines.slice(first, last).map((span) => {
            const raw = lineText(lineIndex, payload.text, span.number) ?? "";
            const collapsed = collapseLong ? collapseLine(raw) : { text: raw, collapsed: false, elided: 0 };
            const resolution = resolveLine(resolved, span.number);
            return (
              <div
                key={span.number}
                role="row"
                aria-rowindex={span.number}
                aria-selected={selectedLine === span.number}
                className="ui-raw-line"
                data-selected={selectedLine === span.number}
                data-cursor={cursorLine === span.number - 1}
                data-hit={hitLines.has(span.number)}
                data-observation={resolution.observationId ?? undefined}
                data-testid={`raw-line-${span.number}`}
                onClick={() => activateLine(span.number)}
              >
                <span className="ui-raw-gutter" aria-hidden="true">
                  {span.number}
                </span>
                <span className="ui-raw-code">
                  {highlight(collapsed.text, payload.format).map((token, position) => (
                    <span key={position} data-token={token.kind}>
                      {token.text}
                    </span>
                  ))}
                  {collapsed.collapsed ? (
                    <span className="ui-raw-elided" data-testid={`raw-elided-${span.number}`}>
                      … {collapsed.elided} chars elided
                    </span>
                  ) : null}
                </span>
                {resolution.observationId === null ? (
                  <span className="ui-raw-obs" data-testid={`raw-obs-${span.number}`}>
                    no observation
                  </span>
                ) : (
                  <button
                    type="button"
                    className="ui-raw-obs ui-insp-link"
                    onClick={(event) => {
                      event.stopPropagation();
                      activateLine(span.number);
                    }}
                    title={`Open Observation ${resolution.observationId}`}
                    data-testid={`raw-obs-${span.number}`}
                  >
                    {resolution.observationId}
                  </button>
                )}
              </div>
            );
          })}
        </div>
        <div
          className="ui-raw-spacer"
          style={{ height: `${Math.max(0, (total - (last - first)) * ROW_HEIGHT)}px` }}
          aria-hidden="true"
        />
      </div>

      <footer className="ui-raw-status" data-testid="raw-status">
        {selectedResolution === null ? (
          <span className="ui-rail-hint">Select a line to trace it to its observation.</span>
        ) : (
          <>
            <span className="ui-rail-hint">
              line {selectedResolution.line} ·{" "}
              {selectedResolution.observationId === null ? (
                <span data-testid="raw-status-none">no observation reported for this line</span>
              ) : (
                <span data-testid="raw-status-observation">
                  {selectedResolution.observationId} via <span className="ui-mono">{selectedResolution.locator}</span>
                  {selectedResolution.match === "ancestor" ? " (containing value)" : ""}
                </span>
              )}
            </span>
            {selectedResolution.depth > 1 ? (
              <span className="ui-rail-hint" data-testid="raw-status-depth">
                {selectedResolution.depth} locators cover this line; the narrowest was used.
              </span>
            ) : null}
          </>
        )}
        <IconButton
          icon="close"
          label="Clear the selected line"
          size="sm"
          disabled={selectedLine === null}
          onClick={() => setSelectedLine(null)}
          data-testid="raw-clear-line"
        />
      </footer>
    </section>
  );
}

/** The search glyph, as a token so the toolbar has no icon import churn. */
function IconSearch() {
  return (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M7 2.5a4.5 4.5 0 1 1 0 9 4.5 4.5 0 0 1 0-9M10.5 10.5 13.5 13.5" />
    </svg>
  );
}