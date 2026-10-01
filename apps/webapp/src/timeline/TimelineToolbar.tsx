import { useState } from "react";

import { Badge } from "../ui/Badge";
import { Button, IconButton } from "../ui/Button";
import { Icon } from "../ui/Icon";
import { Input } from "../ui/Input";
import { Popover, Tooltip } from "../ui/Overlay";
import type { TimeRange } from "../workspace/types";
import { toggleTimelineValue, type FocusTarget, type TimelineFilter, type WindowComparison } from "./series";
import { LANE_SEMANTICS, type TimelineLane } from "./types";

/**
 * TimelineToolbar (§23, §84).
 *
 * SEVEN ACTIONS, and each is a different QUESTION, not a different button
 * style:
 *
 *   filter   — which kinds of record am I looking at
 *   brush    — which window am I looking at        → writes the store's timeRange
 *   zoom     — how close am I looking
 *   compare  — is this window busier than the one before it
 *   focus    — entity / relation / evidence: which records, and what else came
 *              with them
 *
 * The three focus targets are separate controls rather than a mode selector,
 * because "focus entity" and "focus evidence" take different arguments. A mode
 * selector would make the analyst remember which mode is active before they can
 * type anything.
 *
 * §67: every icon-only control names itself; every popover has an accessible
 * label; the window inputs are real `datetime-local`-shaped text fields, because
 * an analyst comparing two windows needs to type an exact instant.
 */

export interface TimelineToolbarProps {
  filter: TimelineFilter;
  onFilterChange: (filter: TimelineFilter) => void;
  presentLanes: ReadonlyArray<TimelineLane>;
  presentSourceIds: ReadonlyArray<string>;
  presentStatuses: ReadonlyArray<string>;
  timeRange: TimeRange;
  onBrush: (from: string | null, to: string | null) => void;
  onZoom: (factor: number) => void;
  onPan: (fraction: number) => void;
  onResetZoom: () => void;
  /** Current span as a fraction of the full record span. */
  zoom: number;
  canZoom: boolean;
  comparison: WindowComparison;
  onFocus: (target: FocusTarget, ref: string) => void;
  onClearFocus: () => void;
  focus: { label: string; empty: boolean; eventIds: string[] } | null;
  onCompare: () => void;
  secondaryCount: number;
  onClearWindow: () => void;
  counts: Record<TimelineLane, number>;
  /** Records named by the server but carrying no instant. */
  unplaced: number;
  loading: boolean;
  disabled: boolean;
}

export function TimelineToolbar(props: TimelineToolbarProps) {
  const {
    filter,
    onFilterChange,
    presentLanes,
    presentSourceIds,
    presentStatuses,
    timeRange,
    onBrush,
    onZoom,
    onPan,
    onResetZoom,
    zoom,
    canZoom,
    comparison,
    onFocus,
    onClearFocus,
    focus,
    onCompare,
    unplaced,
    disabled,
  } = props;

  const [entityRef, setEntityRef] = useState("");
  const [relationRef, setRelationRef] = useState("");
  const [evidenceRef, setEvidenceRef] = useState("");

  const activeFilterCount =
    filter.lanes.length + filter.sourceIds.length + filter.statuses.length + (filter.query.trim() === "" ? 0 : 1);

  return (
    <div className="ui-timeline-toolbar" role="toolbar" aria-label="Timeline controls" data-testid="timeline-toolbar">
      {/* ── Filter ─────────────────────────────────────────────────── */}
      <Popover
        label="Timeline filters"
        placement="bottom"
        align="start"
        testId="timeline-filter-menu"
        trigger={
          <Button size="sm" variant={activeFilterCount > 0 ? "primary" : "default"} data-testid="timeline-filter">
            Filter{activeFilterCount > 0 ? ` (${activeFilterCount})` : ""}
          </Button>
        }
      >
        <div className="ui-menu">
          <span className="ui-pane-title">Lane</span>
          {presentLanes.map((lane) => (
            <label key={lane} className="ui-check">
              <input
                type="checkbox"
                checked={filter.lanes.includes(lane)}
                onChange={() => onFilterChange({ ...filter, lanes: toggleTimelineValue(filter.lanes, lane) })}
                data-testid={`timeline-filter-lane-${lane}`}
              />
              <span className="ui-mono">{LANE_SEMANTICS[lane].token}</span>
              <span>{LANE_SEMANTICS[lane].label}</span>
            </label>
          ))}

          {presentSourceIds.length > 0 ? (
            <>
              <span className="ui-pane-title">Source</span>
              {presentSourceIds.map((sourceId) => (
                <label key={sourceId} className="ui-check">
                  <input
                    type="checkbox"
                    checked={filter.sourceIds.includes(sourceId)}
                    onChange={() =>
                      onFilterChange({ ...filter, sourceIds: toggleTimelineValue(filter.sourceIds, sourceId) })
                    }
                    data-testid={`timeline-filter-source-${sourceId}`}
                  />
                  <span className="ui-mono">{sourceId}</span>
                </label>
              ))}
            </>
          ) : null}

          {presentStatuses.length > 0 ? (
            <>
              <span className="ui-pane-title">Status</span>
              {presentStatuses.map((status) => (
                <label key={status} className="ui-check">
                  <input
                    type="checkbox"
                    checked={filter.statuses.includes(status)}
                    onChange={() =>
                      onFilterChange({ ...filter, statuses: toggleTimelineValue(filter.statuses, status) })
                    }
                    data-testid={`timeline-filter-status-${status}`}
                  />
                  <span className="ui-mono">{status}</span>
                </label>
              ))}
            </>
          ) : null}

          <Input
            label="Text"
            mono
            value={filter.query}
            placeholder="label or ref"
            onChange={(event) => onFilterChange({ ...filter, query: event.target.value })}
          />

          <Button
            size="sm"
            disabled={activeFilterCount === 0}
            onClick={() => onFilterChange({ lanes: [], sourceIds: [], statuses: [], query: "" })}
            data-testid="timeline-filter-reset"
          >
            Reset filters
          </Button>
        </div>
      </Popover>

      {/* ── Brush ──────────────────────────────────────────────────── */}
      <div className="ui-timeline-brush" role="group" aria-label="Time window">
        <Input
          label="from"
          mono
          value={toLocalInput(timeRange.from)}
          onChange={(event) => onBrush(fromInputToIso(event.target.value), timeRange.to)}
        />
        <Input
          label="to"
          mono
          value={toLocalInput(timeRange.to)}
          onChange={(event) => onBrush(timeRange.from, fromInputToIso(event.target.value))}
        />
        <Tooltip content="Clear the window and show the whole record span">
          <Button
            size="sm"
            disabled={timeRange.from === null && timeRange.to === null}
            onClick={onResetZoom}
            data-testid="timeline-clear-window"
          >
            Clear
          </Button>
        </Tooltip>
      </div>

      {/* ── Zoom ───────────────────────────────────────────────────── */}
      <div className="ui-timeline-toolbar-group" role="group" aria-label="Zoom">
        <Tooltip content="Zoom out one step">
          <IconButton
            icon="chevron-left"
            label="Zoom out"
            size="sm"
            disabled={!canZoom}
            onClick={() => onZoom(1.5)}
            data-testid="timeline-zoom-out"
          />
        </Tooltip>
        <span className="ui-count-value ui-mono" data-testid="timeline-zoom-level">
          {zoom.toFixed(2)}×
        </span>
        <Tooltip content="Zoom in one step">
          <IconButton
            icon="chevron-right"
            label="Zoom in"
            size="sm"
            disabled={!canZoom}
            onClick={() => onZoom(1 / 1.5)}
            data-testid="timeline-zoom-in"
          />
        </Tooltip>
        <Tooltip content="Pan back one window">
          <IconButton
            icon="chevron-left"
            label="Pan back"
            size="sm"
            disabled={!canZoom}
            onClick={() => onPan(-0.5)}
            data-testid="timeline-pan-back"
          />
        </Tooltip>
        <Tooltip content="Pan forward one window">
          <IconButton
            icon="chevron-right"
            label="Pan forward"
            size="sm"
            disabled={!canZoom}
            onClick={() => onPan(0.5)}
            data-testid="timeline-pan-forward"
          />
        </Tooltip>
      </div>

      <div className="ui-timeline-toolbar-sep" role="presentation" />

      {/* ── Compare ────────────────────────────────────────────────── */}
      <div className="ui-timeline-toolbar-group" role="group" aria-label="Compare">
        <Button size="sm" disabled={disabled} onClick={onCompare} data-testid="timeline-compare">
          Compare window
        </Button>
        <Badge
          tone={comparison.delta === null ? "neutral" : comparison.delta === 0 ? "neutral" : "gold"}
          role="classification"
          testId="timeline-compare-delta"
        >
          {comparison.current.count} vs {comparison.previous.count}
          {comparison.delta === null ? "" : ` (${comparison.delta > 0 ? "+" : ""}${comparison.delta})`}
        </Badge>
      </div>

      <div className="ui-timeline-toolbar-sep" role="presentation" />

      {/* ── Focus ──────────────────────────────────────────────────── */}
      <div className="ui-timeline-toolbar-group ui-timeline-focus" role="group" aria-label="Focus">
        <FocusField
          id="entity"
          label="Focus entity"
          hint="ENT-…"
          value={entityRef}
          onChange={setEntityRef}
          onRun={() => onFocus("entity", entityRef)}
          disabled={disabled}
        />
        <FocusField
          id="relation"
          label="Focus relation"
          hint="CLM-…"
          value={relationRef}
          onChange={setRelationRef}
          onRun={() => onFocus("relation", relationRef)}
          disabled={disabled}
        />
        <FocusField
          id="evidence"
          label="Focus evidence"
          hint="OBS-…"
          value={evidenceRef}
          onChange={setEvidenceRef}
          onRun={() => onFocus("evidence", evidenceRef)}
          disabled={disabled}
        />
        {focus !== null ? (
          <Tooltip content={focus.label}>
            <Button
              size="sm"
              variant={focus.empty ? "danger" : "primary"}
              onClick={onClearFocus}
              icon="close"
              data-testid="timeline-clear-focus"
            >
              {focus.empty ? "no match" : `${focus.eventIds.length} focused`}
            </Button>
          </Tooltip>
        ) : null}
      </div>

      <div className="ui-timeline-toolbar-grow" />

      {/* ── State ──────────────────────────────────────────────────── */}
      <div className="ui-timeline-toolbar-state">
        <Icon name="clock" size={12} />
        <span className="ui-rail-hint" data-testid="timeline-unplaced">
          {unplaced === 0
            ? "every record is dated"
            : `${unplaced} record(s) named but not dated — excluded from the axis`}
        </span>
      </div>
    </div>
  );
}

function FocusField({
  id,
  label,
  hint,
  value,
  onChange,
  onRun,
  disabled,
}: {
  id: FocusTarget;
  label: string;
  hint: string;
  value: string;
  onChange: (value: string) => void;
  onRun: () => void;
  disabled: boolean;
}) {
  return (
    <span className="ui-timeline-focus-field">
      <Input
        label={label}
        mono
        value={value}
        placeholder={hint}
        adornment={<Icon name="search" size={12} />}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            onRun();
          }
        }}
      />
      <IconButton
        icon="chevron-right"
        label={`Run ${label.toLowerCase()}`}
        size="sm"
        disabled={disabled || value.trim() === ""}
        onClick={onRun}
        data-testid={`timeline-focus-${id}`}
      />
    </span>
  );
}

/** ISO-8601 → the `YYYY-MM-DDTHH:mm` shape a text field accepts. */
function toLocalInput(iso: string | null): string {
  if (iso === null) return "";
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return "";
  return new Date(ms).toISOString().slice(0, 16);
}

/** `YYYY-MM-DDTHH:mm` → ISO-8601 UTC. Empty input clears the bound. */
function fromInputToIso(value: string): string | null {
  if (value.trim() === "") return null;
  const ms = Date.parse(`${value}Z`);
  return Number.isNaN(ms) ? null : new Date(ms).toISOString();
}