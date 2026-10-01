import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { EmptyState, Skeleton } from "../ui/Feedback";
import { Input } from "../ui/Input";
import { Tabs, TabPanel } from "../ui/Tabs";
import { useWorkspace } from "../workspace/store";
import type { WorkspaceSelection, WorkspaceView } from "../workspace/types";
import { LineageViewer } from "./LineageViewer";
import { RawViewer } from "./RawViewer";
import {
  EVIDENCE_TAB_LABELS,
  EVIDENCE_TAB_SUPPORT,
  EVIDENCE_TABS,
  evidenceCounts,
  filterEvidence,
  sortEvidence,
  type EvidenceQuery,
  type EvidenceRow,
  type EvidenceRowKind,
  type EvidenceSort,
  type EvidenceSortKey,
  type EvidenceTab,
} from "./types";
import { useEvidenceRecords, useSelectedEvidence } from "./useEvidenceRecords";
import "./evidence.css";

/**
 * EvidenceWorkspace (§28, §29, §82).
 *
 * §82 is the load-bearing requirement here, and it is a structural one: this is
 * a PEER of the graph, not a detail panel hanging off it. Concretely that means
 *
 *   - its own query keys and its own loading/error/empty states, because a
 *     detail panel's states are the parent's states and a peer has its own
 *   - its own toolbar with the same control vocabulary and the same density as
 *     the graph toolbar — not a `DataTable` with a caption
 *   - a LIST pane beside a VIEWER pane, both full height. The list is not
 *     collapsed by default and the viewer is not a popover.
 *   - the same six-tab viewer shape the directive names, so evidence has the
 *     same navigable structure as every other surface.
 *
 * §28 puts three record KINDS in the list — Observation, Capture, Claim — and
 * they are three distinct row types rather than one normalised "item". §29's six
 * tabs are Content / Structured / Metadata / Lineage / Processing / Revisions;
 * three of them have no wired endpoint today, and each says so per record rather
 * than rendering an empty pane that could be mistaken for "nothing here".
 *
 * §68: the list is windowed and the selection is read from the store, so
 * selecting a row re-renders the viewer and not the list.
 */

export interface EvidenceWorkspaceProps {
  investigationId?: string | null;
  /** Rows supplied by an outer surface that already holds richer records. */
  rows?: ReadonlyArray<EvidenceRow>;
}

export function EvidenceWorkspace({ investigationId, rows: suppliedRows }: EvidenceWorkspaceProps) {
  const storeInvestigationId = useWorkspace((state) => state.investigationId);
  const activeInvestigation = investigationId !== undefined ? investigationId : storeInvestigationId;

  const selection = useWorkspace((state) => state.selection);
  const select = useWorkspace((state) => state.select);
  const setView = useWorkspace((state) => state.setView);
  // §7: the workspace's own evidence query, not a local copy. Typing in the
  // toolbar narrows the rail and every other evidence surface at once.
  const storeQuery = useWorkspace((state) => state.evidenceFilter.query);
  const setEvidenceFilter = useWorkspace((state) => state.setEvidenceFilter);

  const server = useEvidenceRecords(activeInvestigation);
  const allRows = useMemo(
    () => (suppliedRows !== undefined && suppliedRows.length > 0 ? [...suppliedRows] : server.rows),
    [suppliedRows, server.rows],
  );

  const [tab, setTab] = useState<EvidenceTab>("content");
  const [sort, setSort] = useState<EvidenceSort>({ key: "at", direction: "desc" });
  const [hideUndated, setHideUndated] = useState(false);
  const [kinds, setKinds] = useState<EvidenceRowKind[]>([]);
  const [focusedRowRef, setFocusedRowRef] = useState<string | null>(null);

  // The store query is the base; the local kind filter narrows on top of it.
  const query: EvidenceQuery = useMemo(
    () => ({ text: storeQuery, hideUndated, kinds }),
    [storeQuery, hideUndated, kinds],
  );

  const visibleRows = useMemo(
    () => sortEvidence(filterEvidence(allRows, query), sort),
    [allRows, query, sort],
  );

  // The selected row: the store's selection when it names evidence, otherwise
  // the row the analyst last clicked in this list.
  const selectedRow = useMemo<EvidenceRow | null>(() => {
    if (selection !== null && (selection.kind === "Observation" || selection.kind === "Capture" || selection.kind === "Claim")) {
      return allRows.find((row) => row.kind === selection.kind && row.ref === selection.id) ?? null;
    }
    if (focusedRowRef !== null) {
      const byRef = allRows.find((row) => row.ref === focusedRowRef);
      if (byRef !== undefined) return byRef;
    }
    return visibleRows[0] ?? null;
  }, [selection, allRows, focusedRowRef, visibleRows]);

  const selected = useSelectedEvidence(selectedRow);

  const onSelectRow = useCallback(
    (row: EvidenceRow) => {
      setFocusedRowRef(row.ref);
      select({ kind: row.kind, id: row.ref, label: row.label });
    },
    [select],
  );

  // Keep the list's notion of "selected" in step when the selection arrives from
  // the graph or the timeline — §7, one selection model.
  useEffect(() => {
    if (selection === null) return;
    if (selection.kind === "Observation" || selection.kind === "Capture" || selection.kind === "Claim") {
      setFocusedRowRef(selection.id);
    }
  }, [selection]);

  const counts = useMemo(() => evidenceCounts(visibleRows), [visibleRows]);

  /* ── States (§90, §91) ────────────────────────────────────────────── */

  if (activeInvestigation === null) {
    return (
      <section className="ui-evidence" aria-label="Evidence" data-testid="evidence-workspace">
        <EmptyState
          icon="view-evidence"
          title="No investigation loaded"
          description="Evidence is scoped to one investigation's observations, captures and claims. Choose an investigation to read them."
          testId="evidence-no-investigation"
        />
      </section>
    );
  }

  if (server.loading) {
    return (
      <section className="ui-evidence" aria-label="Evidence" data-testid="evidence-workspace">
        <Skeleton rows={10} label="Loading evidence records" />
      </section>
    );
  }

  if (server.error !== null) {
    return (
      <section className="ui-evidence" aria-label="Evidence" data-testid="evidence-workspace">
        <div className="ui-inspector-error" role="alert" data-testid="evidence-error">
          <p className="ui-pane-title">Evidence did not load</p>
          <p className="ui-body" data-testid="evidence-error-message">
            {server.error}
          </p>
          <p className="ui-body">
            Scope: the entity projection and the finding list for investigation{" "}
            <span className="ui-mono">{activeInvestigation}</span>. The graph and the
            timeline are unaffected, and the workspace selection, filters and time range
            are untouched.
          </p>
          <div className="ui-insp-next-list">
            <Button size="sm" onClick={server.refetch} data-testid="evidence-error-retry">
              Retry
            </Button>
            <Button size="sm" onClick={() => setView("graph")} data-testid="evidence-error-inspect">
              Inspect from the graph
            </Button>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="ui-evidence" aria-label="Evidence" data-testid="evidence-workspace">
      {/* ── Toolbar: the same vocabulary as the graph's (§82) ────────── */}
      <div className="ui-evidence-toolbar" role="toolbar" aria-label="Evidence controls" data-testid="evidence-toolbar">
        <Input
          label="Search evidence"
          mono
          value={storeQuery}
          placeholder="uri, observation id, status"
          onChange={(event) => setEvidenceFilter({ query: event.target.value })}
          hint={`${visibleRows.length}/${allRows.length} records`}
        />

        <div className="ui-evidence-kindgroup" role="group" aria-label="Record kind">
          {(["Observation", "Capture", "Claim"] as const).map((kind) => (
            <Button
              key={kind}
              size="sm"
              variant={kinds.includes(kind) ? "primary" : "default"}
              aria-pressed={kinds.includes(kind)}
              onClick={() =>
                setKinds((prev) => (prev.includes(kind) ? prev.filter((k) => k !== kind) : [...prev, kind]))
              }
              data-testid={`evidence-kind-${kind}`}
              data-count={counts[kind]}
            >
              {kind} ({counts[kind]})
            </Button>
          ))}
        </div>

        <label className="ui-check">
          <input
            type="checkbox"
            checked={hideUndated}
            onChange={(event) => setHideUndated(event.target.checked)}
            data-testid="evidence-hide-undated"
          />
          Hide undated
        </label>

        <div className="ui-evidence-sort" role="group" aria-label="Sort">
          {(["at", "kind", "ref", "sourceId"] as EvidenceSortKey[]).map((key) => (
            <Button
              key={key}
              size="sm"
              variant={sort.key === key ? "primary" : "default"}
              aria-pressed={sort.key === key}
              onClick={() =>
                setSort((prev) =>
                  prev.key === key
                    ? { key, direction: prev.direction === "asc" ? "desc" : "asc" }
                    : { key, direction: key === "at" ? "desc" : "asc" },
                )
              }
              data-testid={`evidence-sort-${key}`}
            >
              {key}
              {sort.key === key ? (sort.direction === "asc" ? " ↑" : " ↓") : ""}
            </Button>
          ))}
        </div>

        <div className="ui-evidence-toolbar-grow" />

        <Tooltipish
          message={`served: ${server.loaded.join(", ")} · not served: ${server.missing.length} endpoint(s)`}
          testId="evidence-coverage"
          label={`${server.missing.length} endpoints missing`}
        />
      </div>

      {/* ── List + viewer (§28) ──────────────────────────────────────── */}
      <div className="ui-evidence-body">
        <EvidenceList
          rows={visibleRows}
          selectedRef={selectedRow?.ref ?? null}
          secondaryRefs={[]}
          onSelect={onSelectRow}
          totalCount={allRows.length}
        />
        <EvidenceViewer
            row={selectedRow}
            tab={tab}
            onTabChange={setTab}
            lineage={selected.lineage}
            onGoTo={select}
            onGoToView={setView}
            selectedId={selection?.id ?? null}
          />
      </div>
    </section>
  );
}

/* ── The list pane ───────────────────────────────────────────────────── */

const ROW_HEIGHT = 24;
const LIST_VIEWPORT_ROWS = 24;
const LIST_OVERSCAN = 8;

interface EvidenceListProps {
  rows: ReadonlyArray<EvidenceRow>;
  selectedRef: string | null;
  secondaryRefs: ReadonlyArray<string>;
  onSelect: (row: EvidenceRow) => void;
  totalCount: number;
}

/**
 * The list. Windowed (§68), keyboard-reachable (§67), and honest about the two
 * row kinds the platform does not serve: the toolbar's counts already say
 * Capture 0 and Claim 0, so the list does not pad itself with placeholders.
 */
function EvidenceList({ rows, selectedRef, onSelect, totalCount }: EvidenceListProps) {
  const [offset, setOffset] = useState(0);
  const first = Math.max(0, Math.floor(offset / ROW_HEIGHT) - LIST_OVERSCAN);
  const last = Math.min(rows.length, first + LIST_VIEWPORT_ROWS + LIST_OVERSCAN * 2);
  const slice = rows.slice(first, last);

  return (
    <div className="ui-evidence-list ui-scroll" data-testid="evidence-list">
      <table className="ui-table" role="grid" aria-rowcount={rows.length} aria-label="Evidence records">
        <thead>
          <tr>
            <th scope="col">when</th>
            <th scope="col">kind</th>
            <th scope="col">record</th>
            <th scope="col">source</th>
          </tr>
        </thead>
        <tbody>
          {slice.map((row) => (
            <tr
              key={`${row.kind}:${row.ref}`}
              data-selected={selectedRef === row.ref}
              tabIndex={0}
              onClick={() => onSelect(row)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelect(row);
                }
              }}
              data-testid={`evidence-row-${row.ref}`}
            >
              <td data-mono="true">{row.at === null ? "undated" : row.at.slice(0, 10)}</td>
              <td>{row.kind}</td>
              <td data-mono="true" className="ui-truncate">
                {row.label}
              </td>
              <td data-mono="true">{row.sourceId ?? "not reported"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div
        className="ui-evidence-spacer"
        style={{ height: `${Math.max(0, rows.length * ROW_HEIGHT - (last - first) * ROW_HEIGHT)}px` }}
        aria-hidden="true"
      />
      <button
        type="button"
        className="ui-evidence-more"
        disabled={last >= rows.length}
        onClick={() => setOffset((value) => value + (LIST_VIEWPORT_ROWS + LIST_OVERSCAN) * ROW_HEIGHT)}
        data-testid="evidence-scroll-more"
      >
        Show more ({Math.max(0, rows.length - last)} of {totalCount})
      </button>
    </div>
  );
}

/* ── The viewer pane (§29) ───────────────────────────────────────────── */

interface EvidenceViewerProps {
  row: EvidenceRow | null;
  tab: EvidenceTab;
  onTabChange: (tab: EvidenceTab) => void;
  lineage: ReturnType<typeof useSelectedEvidence>["lineage"];
  onGoTo: (selection: WorkspaceSelection) => void;
  onGoToView: (view: WorkspaceView) => void;
  selectedId: string | null;
}

function EvidenceViewer({ row, tab, onTabChange, lineage, onGoTo, onGoToView, selectedId }: EvidenceViewerProps) {
  const items = useMemo(
    () => EVIDENCE_TABS.map((value) => ({ value, label: EVIDENCE_TAB_LABELS[value] })),
    [],
  );

  if (row === null) {
    return (
      <div className="ui-evidence-viewer" data-testid="evidence-viewer">
        <EmptyState
          icon="view-evidence"
          title="No record selected"
          description="Pick an observation, capture or claim from the list. The viewer reads the same record the inspector does — the selection is global."
          testId="evidence-viewer-empty"
        />
      </div>
    );
  }

  const supported = EVIDENCE_TAB_SUPPORT[tab];
  const tabSupported = supported === "all" || supported.includes(row.kind);

  return (
    <div className="ui-evidence-viewer" data-testid="evidence-viewer" data-kind={row.kind}>
      <header className="ui-evidence-viewer-head">
        <div className="ui-evidence-viewer-titles">
          <h2 className="ui-title ui-truncate" data-testid="evidence-viewer-title">
            {row.label}
          </h2>
          <span className="ui-id ui-truncate" data-testid="evidence-viewer-ref">
            {row.kind} {row.ref}
          </span>
        </div>
        <div className="ui-evidence-viewer-badges">
          {row.status !== null ? (
            <Badge tone="gold" role="classification" testId="evidence-status">
              {row.status}
            </Badge>
          ) : (
            <Badge tone="neutral" testId="evidence-status-unreported">
              status not reported
            </Badge>
          )}
          <Badge tone="neutral" testId="evidence-source">
            {row.sourceId ?? "source not reported"}
          </Badge>
        </div>
      </header>

      <Tabs items={items} value={tab} onValueChange={onTabChange} label="Record tabs" orientation="bar" />

      <div className="ui-evidence-panel ui-scroll">
        {!tabSupported ? (
          <EmptyState
            size="sm"
            icon="view-evidence"
            title={`${EVIDENCE_TAB_LABELS[tab]} is not served for a ${row.kind}`}
            description="The endpoint that would answer this tab is not wired. Nothing is inferred from another tab to fill it."
            testId={`evidence-tab-unsupported-${tab}`}
          />
        ) : (
          <TabPanel panelId={`evidence-panel-${tab}`}>
            {tab === "content" ? <ContentTab row={row} onGoTo={onGoTo} onGoToView={onGoToView} /> : null}
            {tab === "structured" ? <StructuredTab row={row} /> : null}
            {tab === "metadata" ? <MetadataTab row={row} /> : null}
            {tab === "lineage" ? (
              <LineageViewer model={lineage} onGoTo={onGoTo} selectedId={selectedId} />
            ) : null}
            {tab === "processing" ? <UnwiredTab name="processing" endpoint="GET /observations/{id}/processing" /> : null}
            {tab === "revisions" ? <UnwiredTab name="revisions" endpoint="GET /observations/{id}/revisions" /> : null}
          </TabPanel>
        )}
      </div>
    </div>
  );
}

function ContentTab({
  row,
  onGoTo,
  onGoToView,
}: {
  row: EvidenceRow;
  onGoTo: (selection: WorkspaceSelection) => void;
  onGoToView: (view: WorkspaceView) => void;
}) {
  if (row.payload === null) {
    return (
      <div className="ui-evidence-tab" data-testid="evidence-content-none">
        <EmptyState
          size="sm"
          icon="view-evidence"
          title="No raw payload for this record"
          description="Serving a capture's bytes needs a capture-payload endpoint, and none is wired. The record's identity, URI, content type and immutable flag are on the Metadata tab."
          action={
            <div className="ui-insp-next-list">
              <Button
                size="sm"
                onClick={() => onGoTo({ kind: "Observation", id: row.ref })}
                data-testid="evidence-content-open-observation"
              >
                Open {row.ref} in the inspector
              </Button>
              <Button size="sm" onClick={() => onGoToView("graph")} data-testid="evidence-content-open-graph">
                Show it in the graph
              </Button>
            </div>
          }
          testId="evidence-content-empty"
        />
      </div>
    );
  }

  return (
    <div className="ui-evidence-tab" data-testid="evidence-content">
      <RawViewer
        payload={{
          format: row.payload.format,
          text: row.payload.text,
          mediaType: row.payload.mediaType,
          digest: row.payload.digest,
        }}
        locators={row.payload.locators.map((locator) => ({
          observationId: locator.observationId,
          pointer: locator.pointer,
          lineStart: locator.lineStart,
          lineEnd: locator.lineEnd,
          raw: locator.raw,
        }))}
        selectedObservationId={row.kind === "Observation" ? row.ref : null}
        onJumpToObservation={(selection) => onGoTo(selection)}
      />
    </div>
  );
}

function StructuredTab({ row }: { row: EvidenceRow }) {
  const fields: Array<{ key: string; label: string; value: string; mono?: boolean }> = [
    { key: "kind", label: "record kind", value: row.kind },
    { key: "ref", label: "identifier", value: row.ref, mono: true },
    { key: "contentType", label: "content type", value: row.contentType ?? "not reported", mono: true },
    { key: "source", label: "source", value: row.sourceId ?? "not reported", mono: true },
    { key: "status", label: "status", value: row.status ?? "not reported", mono: true },
    { key: "at", label: "observed", value: row.at ?? "not reported", mono: true },
  ];

  return (
    <div className="ui-evidence-tab" data-testid="evidence-structured">
      {fields.map((field) => (
        <div key={field.key} className="ui-insp-field" data-testid={`evidence-field-${field.key}`}>
          <span className="ui-insp-field-label">{field.label}</span>
          <span className="ui-insp-field-value" data-mono={field.mono ? "true" : undefined}>
            {field.value === "not reported" ? <span className="ui-insp-unreported">not reported</span> : field.value}
          </span>
        </div>
      ))}
      <p className="ui-rail-hint" data-testid="evidence-structured-note">
        A field the platform did not report reads "not reported". It is never defaulted,
        because a default here would be a claim about the record that the record does not
        make.
      </p>
    </div>
  );
}

function MetadataTab({ row }: { row: EvidenceRow }) {
  const fields: Array<{ key: string; label: string; value: string }> = [
    { key: "kind", label: "classification", value: row.kind },
    { key: "immutable", label: "immutable", value: row.status === "IMMUTABLE" ? "yes" : "not reported" },
    { key: "digest", label: "content digest", value: row.payload?.digest ?? "not reported" },
    { key: "media", label: "media type", value: row.payload?.mediaType ?? row.contentType ?? "not reported" },
    { key: "locators", label: "locators", value: String(row.payload?.locators.length ?? 0) },
  ];

  return (
    <div className="ui-evidence-tab" data-testid="evidence-metadata">
      {fields.map((field) => (
        <div key={field.key} className="ui-insp-field" data-testid={`evidence-meta-${field.key}`}>
          <span className="ui-insp-field-label">{field.label}</span>
          <span className="ui-insp-field-value ui-mono">
            {field.value === "not reported" ? <span className="ui-insp-unreported">not reported</span> : field.value}
          </span>
        </div>
      ))}
    </div>
  );
}

/** A tab whose endpoint is not wired. Names the endpoint rather than shrugging. */
function UnwiredTab({ name, endpoint }: { name: string; endpoint: string }) {
  return (
    <div className="ui-evidence-tab" data-testid={`evidence-${name}-unwired`}>
      <EmptyState
        size="sm"
        icon="view-evidence"
        title={`No ${name} for this record`}
        description={`${endpoint} is not wired, so the platform has no ${name} to show. This tab will fill in when it is; nothing is substituted in its place.`}
        testId={`evidence-${name}-empty`}
      />
    </div>
  );
}

/** A one-line disclosure, without the Overlay anchor's extra span. */
function Tooltipish({ message, label, testId }: { message: string; label: string; testId: string }) {
  return (
    <span className="ui-rail-hint" title={message} data-testid={testId}>
      {label}
    </span>
  );
}