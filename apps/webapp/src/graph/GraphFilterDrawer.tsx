import { useMemo } from "react";

import { Button, IconButton } from "../ui/Button";
import { EmptyState } from "../ui/Feedback";
import { Input } from "../ui/Input";
import { Tooltip } from "../ui/Overlay";
import {
  ADMISSION_LABELS,
  EVIDENCE_STATE_LABELS,
  GRAPH_FACET_IDS,
  activeFacetIds,
  type GraphFacetId,
  type GraphFacets,
} from "./filters";
import { FACETS_WITHOUT_STORE_HOME } from "./useGraphFacets";
import type { AdmissionState, EdgeFamily, GraphModel, GraphObjectKind } from "./types";

/**
 * The left filter drawer (§22).
 *
 * EIGHT COMBINABLE FACETS, DRAWN FROM THE MODEL. The drawer offers only values
 * that are actually present in the graph — offering a source id the server never
 * returned is a filter that can only ever produce an empty canvas, which is
 * §69's dead end with a different hat on.
 *
 * Each facet is a fieldset with a legend, so the group is announced as a group
 * (§67). Each value is a real checkbox with a visible label: the count beside
 * it is the number of objects that carry the value, and it is the count of the
 * CURRENT model, not a running count under the other facets — combining them
 * into one number is how faceted search stops being explainable.
 */

export interface GraphFilterDrawerProps {
  open: boolean;
  onClose: () => void;
  model: GraphModel;
  facets: GraphFacets;
  onToggle: (facet: GraphFacetId, value: string) => void;
  onQueryChange: (query: string) => void;
  onReset: () => void;
  /** How many objects survive the facets right now. */
  visibleNodeCount: number;
}

const KIND_LABELS: Readonly<Record<GraphObjectKind, string>> = {
  Entity: "Entity",
  Observation: "Observation",
  Claim: "Claim",
  Finding: "Finding",
  Hypothesis: "Hypothesis",
};

const FAMILY_LABELS: Readonly<Record<EdgeFamily, string>> = {
  supports: "supports — finding → observation",
  observes: "observes — entity → observation",
  asserts: "asserts — entity → entity",
  possible: "possible — no merge implied",
};

export function GraphFilterDrawer({
  open,
  onClose,
  model,
  facets,
  onToggle,
  onQueryChange,
  onReset,
  visibleNodeCount,
}: GraphFilterDrawerProps) {
  const present = useMemo(() => presentValues(model), [model]);
  const active = useMemo(() => activeFacetIds(facets), [facets]);

  if (!open) return null;

  return (
    <aside
      className="ui-graph-drawer ui-scroll"
      aria-label="Graph filters"
      data-testid="graph-filter-drawer"
    >
      <header className="ui-graph-drawer-head">
        <h2 className="ui-pane-title">Filters</h2>
        <span className="ui-rail-hint" data-testid="graph-filter-visible">
          {visibleNodeCount}/{model.nodes.length} objects
        </span>
        <IconButton icon="close" label="Close filters" size="sm" onClick={onClose} />
      </header>

      <Input
        label="Text"
        mono
        value={facets.query}
        placeholder="label or id"
        onChange={(event) => onQueryChange(event.target.value)}
      />

      <FacetGroup
        id="kinds"
        legend="Object type"
        active={active}
        values={present.kinds.map((kind) => ({
          value: kind,
          label: KIND_LABELS[kind],
          count: present.kindCounts[kind] ?? 0,
        }))}
        selected={facets.kinds}
        onToggle={(value) => onToggle("kinds", value)}
      />

      <FacetGroup
        id="relations"
        legend="Relation"
        active={active}
        values={present.families.map((family) => ({
          value: family,
          label: FAMILY_LABELS[family],
          count: present.familyCounts[family] ?? 0,
        }))}
        selected={facets.relations}
        onToggle={(value) => onToggle("relations", value)}
        footnote={
          FACETS_WITHOUT_STORE_HOME.includes("relations")
            ? "relation, admission, evidence presence and investigation scope are not in the workspace store yet"
            : undefined
        }
      />

      <FacetGroup
        id="sourceIds"
        legend="Source"
        active={active}
        values={present.sourceIds.map((sourceId) => ({
          value: sourceId,
          label: sourceId,
          count: present.sourceCounts[sourceId] ?? 0,
        }))}
        selected={facets.sourceIds}
        onToggle={(value) => onToggle("sourceIds", value)}
      />

      <FacetGroup
        id="evidenceStates"
        legend="Evidence"
        active={active}
        values={(["anchored", "unanchored"] as const).map((state) => ({
          value: state,
          label: EVIDENCE_STATE_LABELS[state],
          count: state === "anchored" ? present.anchored : present.unanchored,
        }))}
        selected={facets.evidenceStates}
        onToggle={(value) => onToggle("evidenceStates", value)}
      />

      <FacetGroup
        id="admissions"
        legend="Status"
        active={active}
        values={present.admissions.map((state) => ({
          value: state,
          label: ADMISSION_LABELS[state],
          count: present.admissionCounts[state] ?? 0,
        }))}
        selected={facets.admissions}
        onToggle={(value) => onToggle("admissions", value)}
      />

      <fieldset className="ui-field ui-graph-facet" data-testid="facet-timeRange">
        <legend className="ui-field-label">Temporal range</legend>
        <p className="ui-rail-hint">
          Owned by the workspace time range, so the timeline and the graph are
          always on the same window.
        </p>
        <span className="ui-graph-facet-value" data-testid="facet-timeRange-value">
          {facets.timeRange.from ?? "open"} → {facets.timeRange.to ?? "open"}
        </span>
      </fieldset>

      <fieldset className="ui-field ui-graph-facet" data-testid="facet-investigationIds">
        <legend className="ui-field-label">Investigation scope</legend>
        <p className="ui-rail-hint">
          {facets.investigationIds.length === 0
            ? "Every investigation the server returned."
            : `Scoped to ${facets.investigationIds.join(", ")}.`}
        </p>
      </fieldset>

      {present.kinds.length === 0 && present.families.length === 0 ? (
        <EmptyState
          size="sm"
          icon="view-graph"
          title="Nothing to filter"
          description="The canvas has no objects yet, so there are no values to narrow by. Load a graph and the facets fill in from what the server actually returned."
          testId="graph-drawer-empty"
        />
      ) : null}

      <footer className="ui-graph-drawer-foot">
        <Button size="sm" disabled={active.length === 0} onClick={onReset} data-testid="graph-filter-reset">
          Reset filters
        </Button>
        <span className="ui-rail-hint" data-testid="graph-filter-active">
          {active.length === 0 ? "no filters" : active.join(" + ")}
        </span>
      </footer>
    </aside>
  );
}

interface FacetGroupProps {
  id: GraphFacetId;
  legend: string;
  active: readonly GraphFacetId[];
  values: ReadonlyArray<{ value: string; label: string; count: number }>;
  selected: readonly string[];
  onToggle: (value: string) => void;
  footnote?: string;
}

function FacetGroup({ id, legend, active, values, selected, onToggle, footnote }: FacetGroupProps) {
  return (
    <fieldset className="ui-field ui-graph-facet" data-testid={`facet-${id}`} data-active={active.includes(id)}>
      <legend className="ui-field-label">{legend}</legend>
      {values.length === 0 ? (
        <span className="ui-rail-hint">none present in this graph</span>
      ) : (
        <ul className="ui-menu">
          {values.map((entry) => (
            <li key={entry.value}>
              <label className="ui-check ui-graph-facet-row">
                <input
                  type="checkbox"
                  checked={selected.includes(entry.value)}
                  onChange={() => onToggle(entry.value)}
                  data-testid={`facet-${id}-${entry.value}`}
                />
                <span className="ui-graph-facet-label">{entry.label}</span>
                <span className="ui-count-value ui-mono" data-testid={`facet-${id}-${entry.value}-count`}>
                  {entry.count}
                </span>
              </label>
            </li>
          ))}
        </ul>
      )}
      {footnote ? (
        <Tooltip content={footnote}>
          <span className="ui-rail-hint" data-testid={`facet-${id}-footnote`}>
            scope note
          </span>
        </Tooltip>
      ) : null}
    </fieldset>
  );
}

/* ── Which values exist in this model ────────────────────────────────── */

interface PresentValues {
  kinds: GraphObjectKind[];
  kindCounts: Partial<Record<GraphObjectKind, number>>;
  families: EdgeFamily[];
  familyCounts: Partial<Record<EdgeFamily, number>>;
  sourceIds: string[];
  sourceCounts: Record<string, number>;
  admissions: AdmissionState[];
  admissionCounts: Partial<Record<AdmissionState, number>>;
  anchored: number;
  unanchored: number;
}

export function presentValues(model: GraphModel): PresentValues {
  const kindCounts: Partial<Record<GraphObjectKind, number>> = {};
  const sourceCounts: Record<string, number> = {};
  const admissionCounts: Partial<Record<AdmissionState, number>> = {};
  let anchored = 0;

  for (const node of model.nodes) {
    kindCounts[node.kind] = (kindCounts[node.kind] ?? 0) + 1;
    if (node.evidenceCount > 0) anchored += 1;
    if (node.sourceId !== null) sourceCounts[node.sourceId] = (sourceCounts[node.sourceId] ?? 0) + 1;
    if (node.admission !== null) admissionCounts[node.admission] = (admissionCounts[node.admission] ?? 0) + 1;
  }

  const familyCounts: Partial<Record<EdgeFamily, number>> = {};
  for (const edge of model.edges) familyCounts[edge.family] = (familyCounts[edge.family] ?? 0) + 1;

  return {
    // Ordered by the fixed kind vocabulary, not by frequency: a legend whose
    // order changes when the data changes is a legend nobody can learn.
    kinds: (["Entity", "Observation", "Claim", "Finding", "Hypothesis"] as GraphObjectKind[]).filter(
      (kind) => (kindCounts[kind] ?? 0) > 0,
    ),
    kindCounts,
    families: (["observes", "asserts", "supports", "possible"] as EdgeFamily[]).filter(
      (family) => (familyCounts[family] ?? 0) > 0,
    ),
    familyCounts,
    sourceIds: Object.keys(sourceCounts).sort(),
    sourceCounts,
    admissions: (["admitted", "provisional", "rejected", "unknown"] as AdmissionState[]).filter(
      (state) => (admissionCounts[state] ?? 0) > 0,
    ),
    admissionCounts,
    anchored,
    unanchored: model.nodes.length - anchored,
  };
}

/** Facet ids in drawer order — exported so a test can assert nothing is missing. */
export const DRAWER_FACET_ORDER: readonly GraphFacetId[] = GRAPH_FACET_IDS;