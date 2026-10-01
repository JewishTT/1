import { Badge, StatusDot } from "./ui/Badge";
import { Button } from "./ui/Button";
import { Input, Select } from "./ui/Input";
import { Icon } from "./ui/Icon";
import { Tooltip } from "./ui/Overlay";
import { useWorkspace } from "./workspace/store";
import { useWorkState } from "./workspace/useWorkState";
import type { WorkspaceObjectKind } from "./workspace/types";

/**
 * The left context rail: filters, the object query box, and the filter summary.
 *
 * It holds *client* state only — the query string, the kind filter, the evidence
 * filter. Object payloads are the views' business. Because the rail is
 * persistent (§24), a filter set here keeps applying while the canvas switches
 * views (§76).
 */

const KIND_OPTIONS: Array<{ value: WorkspaceObjectKind; label: string }> = [
  { value: "Entity", label: "Entity" },
  { value: "Observation", label: "Observation" },
  { value: "Capture", label: "Capture" },
  { value: "Claim", label: "Claim" },
  { value: "Finding", label: "Finding" },
  { value: "Source", label: "Source" },
  { value: "AcquisitionTask", label: "Acquisition task" },
  { value: "AcquisitionRun", label: "Acquisition run" },
];

type KindOption = WorkspaceObjectKind | "all" | "mixed";

export function ContextRail() {
  const railQuery = useWorkspace((state) => state.railQuery);
  const setRailQuery = useWorkspace((state) => state.setRailQuery);
  const railKinds = useWorkspace((state) => state.railKinds);
  const toggleRailKind = useWorkspace((state) => state.toggleRailKind);
  const evidenceFilter = useWorkspace((state) => state.evidenceFilter);
  const setEvidenceFilter = useWorkspace((state) => state.setEvidenceFilter);
  const resetEvidenceFilter = useWorkspace((state) => state.resetEvidenceFilter);
  const timeRange = useWorkspace((state) => state.timeRange);
  const clearTimeRange = useWorkspace((state) => state.clearTimeRange);
  const selection = useWorkspace((state) => state.selection);
  const secondaryCount = useWorkspace((state) => state.secondarySelection.length);
  const setView = useWorkspace((state) => state.setView);

  // A native select can only hold one value; multiple kinds collapse to a
  // summary row that clears the filter, so the control never lies about state.
  const kindValue = railKinds.length === 1 ? railKinds[0] : railKinds.length === 0 ? "all" : "mixed";

  const evidenceActive =
    evidenceFilter.query !== "" || evidenceFilter.sourceIds.length > 0 || evidenceFilter.hideRejected;
  const timeActive = timeRange.from !== null || timeRange.to !== null;

  return (
    <div className="ui-rail ui-root ui-scroll" aria-label="Context filters" data-testid="context-rail">
      <div className="ui-rail-block">
        <Input
          label="Find objects"
          placeholder="id, name, alias…"
          value={railQuery}
          onChange={(event) => setRailQuery(event.target.value)}
          adornment={<Icon name="search" size={13} />}
          mono
          data-testid="rail-query"
        />
      </div>

      <div className="ui-rail-block">
        <Select
          label="Object kind"
          value={kindValue}
          onValueChange={(value: KindOption) => {
            if (value === "all" || value === "mixed") {
              for (const kind of railKinds) toggleRailKind(kind);
              return;
            }
            toggleRailKind(value);
          }}
          options={[
            { value: "all", label: railKinds.length === 0 ? "All kinds" : "Clear kind filter" },
            ...(railKinds.length > 1 ? [{ value: "mixed" as const, label: `${railKinds.length} kinds selected` }] : []),
            ...KIND_OPTIONS,
          ]}
          data-testid="rail-kind"
        />
      </div>

      <div className="ui-rail-block">
        <Input
          label="Evidence query"
          placeholder="uri, digest, backend…"
          mono
          value={evidenceFilter.query}
          onChange={(event) => setEvidenceFilter({ query: event.target.value })}
          data-testid="rail-evidence-query"
        />
        <label className="ui-check">
          <input
            type="checkbox"
            checked={evidenceFilter.hideRejected}
            onChange={(event) => setEvidenceFilter({ hideRejected: event.target.checked })}
            data-testid="rail-hide-rejected"
          />
          <span>Hide rejected evidence</span>
        </label>
        {evidenceActive ? (
          <Button size="sm" variant="ghost" onClick={resetEvidenceFilter} data-testid="rail-clear-evidence">
            Clear evidence filter
          </Button>
        ) : null}
      </div>

      <div className="ui-rail-block">
        <span className="ui-pane-title">Time range</span>
        {timeActive ? (
          <div className="ui-rail-summary" data-testid="rail-time-summary">
            <span className="ui-mono">{timeRange.from ?? "…"} → {timeRange.to ?? "…"}</span>
            <Button size="sm" variant="ghost" onClick={clearTimeRange}>
              Clear
            </Button>
          </div>
        ) : (
          <span className="ui-rail-hint">Whole range</span>
        )}
      </div>

      <div className="ui-rail-block">
        <span className="ui-pane-title">Selection</span>
        {selection ? (
          <div className="ui-rail-selection" data-testid="rail-selection">
            <Badge tone="gold" role="classification">
              {selection.kind}
            </Badge>
            <span className="ui-id ui-truncate">{selection.id}</span>
            {secondaryCount > 0 ? (
              <Tooltip content={`${secondaryCount} supporting object(s) held for comparison`}>
                <span className="ui-rail-secondary">+{secondaryCount}</span>
              </Tooltip>
            ) : null}
          </div>
        ) : (
          <span className="ui-rail-hint">Nothing selected</span>
        )}
      </div>

      <div className="ui-rail-block">
        <span className="ui-pane-title">Investigation</span>
        <RailInvestigationState />
        <Button size="sm" variant="ghost" icon="view-analysis" onClick={() => setView("analysis")}>
          Open analysis
        </Button>
      </div>
    </div>
  );
}

/**
 * The investigation's own state, read from the server (§7: Query, not Zustand).
 * Split out so the rail's filter subscriptions stay narrow — this component
 * re-renders on its own query, not when the rail's query text changes.
 */
function RailInvestigationState() {
  const investigationId = useWorkspace((state) => state.investigationId);
  const work = useWorkState(investigationId);

  if (investigationId === null) {
    return (
      <div className="ui-rail-selection">
        <StatusDot status="Unknown" label="No investigation selected" />
      </div>
    );
  }

  if (work.loading) return <StatusDot status="Queued" label="Loading…" live />;
  if (work.error) return <StatusDot status="Failed" label="Unavailable" />;

  return (
    <div className="ui-rail-selection">
      <StatusDot status={work.state} label={work.rawState ?? work.state} live={work.state === "Running"} />
      <span className="ui-id ui-truncate">{investigationId}</span>
    </div>
  );
}