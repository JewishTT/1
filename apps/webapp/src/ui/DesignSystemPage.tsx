import { useMemo, useState } from "react";

import {
  Badge,
  Button,
  Checkbox,
  DataTable,
  EmptyState,
  ErrorView,
  Icon,
  IconButton,
  Input,
  LoadingView,
  Panel,
  Select,
  Skeleton,
  StatusDot,
  Tabs,
  Textarea,
  Tooltip,
  type DataTableColumn,
  type WorkStatus,
} from "./index";

type DemoRow = {
  id: string;
  kind: string;
  status: WorkStatus;
  updated: string;
};

const SAMPLE_ROWS: DemoRow[] = [
  { id: "DEMO-OBS-0042", kind: "Observation", status: "Running", updated: "2026-10-27 20:12:04" },
  { id: "DEMO-ENT-0108", kind: "Entity", status: "Healthy", updated: "2026-10-27 20:11:51" },
  { id: "DEMO-SRC-0027", kind: "Source", status: "Queued", updated: "2026-10-27 20:10:09" },
  { id: "DEMO-FND-0006", kind: "Finding", status: "Failed", updated: "2026-10-27 19:58:33" },
];

const TABLE_COLUMNS: ReadonlyArray<DataTableColumn<DemoRow>> = [
  { key: "id", header: "Identifier", mono: true, width: "150px", render: (row) => row.id },
  { key: "kind", header: "Kind", render: (row) => row.kind },
  { key: "status", header: "Status", render: (row) => <StatusDot status={row.status} label={row.status} /> },
  { key: "updated", header: "Last observed", mono: true, render: (row) => row.updated },
];

const STATUS_OPTIONS = [
  { value: "all", label: "All statuses" },
  { value: "Healthy", label: "Healthy" },
  { value: "Running", label: "Running" },
  { value: "Queued", label: "Queued" },
  { value: "Failed", label: "Failed" },
];

const TABS = [
  { value: "primitives", label: "Primitives", shortcut: "1" },
  { value: "data", label: "Data & state", shortcut: "2" },
  { value: "feedback", label: "Feedback", shortcut: "3" },
] as const;

/** Living visual reference for the public component-library entry point. */
export function DesignSystemPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]["value"]>("primitives");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [selectedId, setSelectedId] = useState<string | null>("DEMO-OBS-0042");
  const [clickCount, setClickCount] = useState(0);

  const rows = useMemo(
    () =>
      SAMPLE_ROWS.filter((row) => {
        const queryMatches = `${row.id} ${row.kind} ${row.status}`.toLowerCase().includes(query.toLowerCase());
        return queryMatches && (status === "all" || row.status === status);
      }),
    [query, status],
  );

  return (
    <main className="ui-kit-page" data-testid="ui-kit-page">
      <header className="ui-kit-header">
        <div>
          <p className="ui-meta">COGNITIVE UI / DESIGN SYSTEM</p>
          <h1 className="ui-title">Component library</h1>
          <p className="ui-body">A shared source of truth for workbench controls, data states, tokens and keyboard behavior.</p>
        </div>
        <div className="ui-kit-header-meta">
          <Badge tone="neutral" mono>UI 2.0</Badge>
          <Badge tone="accent">Token-backed</Badge>
        </div>
      </header>

      <div className="ui-kit-principles" aria-label="Design system principles">
        <span>01 / Semantic tokens</span>
        <span>02 / Data before decoration</span>
        <span>03 / Keyboard first</span>
        <span>04 / Theme + density aware</span>
      </div>

      <Tabs items={TABS.map((item) => ({ ...item }))} value={tab} onValueChange={setTab} label="Component library sections" orientation="bar" />

      {tab === "primitives" ? (
        <div className="ui-kit-grid">
          <section className="ui-kit-card" aria-labelledby="ui-kit-buttons">
            <div className="ui-kit-card-head">
              <div><p className="ui-meta">01 / ACTIONS</p><h2 id="ui-kit-buttons">Buttons</h2></div>
              <span className="ui-kit-count">4 variants</span>
            </div>
            <div className="ui-kit-button-row">
              <Button variant="primary" onClick={() => setClickCount((count) => count + 1)}>Primary action</Button>
              <Button onClick={() => setClickCount((count) => count + 1)}>Default</Button>
              <Button variant="ghost" onClick={() => setClickCount((count) => count + 1)}>Ghost</Button>
              <Button variant="danger" onClick={() => setClickCount((count) => count + 1)}>Destructive</Button>
            </div>
            <div className="ui-kit-button-row">
              <Button size="sm" icon="search" onClick={() => setTab("data")}>Search</Button>
              <Button size="sm" icon="search" variant="ghost" onClick={() => { setQuery("DEMO-OBS-0042"); setTab("data"); }}>Find ID</Button>
              <Tooltip content="An icon-only control still has an accessible name."><IconButton icon="command" label="Open command palette" /></Tooltip>
              <Button size="sm" disabled>Unavailable</Button>
            </div>
            <p className="ui-kit-note">Interaction count: <strong data-testid="ui-kit-click-count">{clickCount}</strong> · No gradient, glow or animated scale.</p>
          </section>

          <section className="ui-kit-card" aria-labelledby="ui-kit-inputs">
            <div className="ui-kit-card-head">
              <div><p className="ui-meta">02 / INPUT</p><h2 id="ui-kit-inputs">Fields</h2></div>
              <span className="ui-kit-count">Native semantics</span>
            </div>
            <div className="ui-kit-field-stack">
              <Input label="Search inventory" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="ID, kind or status" adornment={<Icon name="search" size={14} />} />
              <Select label="Filter by status" value={status} onValueChange={setStatus} options={STATUS_OPTIONS} />
              <Textarea label="Investigation context" placeholder="Describe the question, scope and known constraints…" rows={3} hint="Preview only: no investigation or server record is created." />
              <Checkbox label="Include rejected evidence" defaultChecked hint="Illustrative preference control; this demo changes no platform data." />
              <Input label="Immutable identifier" value="DEMO-OBS-0042 / 6f83…a19d" mono readOnly hint="IDs, digests, URIs and queries use monospace." />
            </div>
          </section>

          <section className="ui-kit-card" aria-labelledby="ui-kit-badges">
            <div className="ui-kit-card-head">
              <div><p className="ui-meta">03 / CLASSIFICATION</p><h2 id="ui-kit-badges">Badges & status</h2></div>
              <span className="ui-kit-count">Closed vocabulary</span>
            </div>
            <div className="ui-kit-badge-list">
              <Badge tone="neutral">Neutral</Badge>
              <Badge tone="accent">Confirmed</Badge>
              <Badge tone="gold" role="classification">Classification</Badge>
              <Badge tone="analytical">Analytical</Badge>
              <Badge tone="danger">Failed</Badge>
              <Badge tone="strong">Completed</Badge>
            </div>
            <div className="ui-kit-status-list">
              {(["Healthy", "Running", "Queued", "Paused", "Completed", "Failed", "Blocked", "Unknown"] as const).map((item) => (
                <div key={item}><StatusDot status={item} label={item} live={item === "Running"} /></div>
              ))}
            </div>
          </section>

          <Panel
            eyebrow="04 / SELECTION"
            title="Navigation & selected state"
            actions={<Badge tone="neutral">Shared behavior</Badge>}
            variant="flat"
            testId="ui-kit-panel"
          >
            <div className="ui-kit-mini-rail">
              <Button variant="ghost" icon="view-overview" onClick={() => setTab("primitives")}>Overview surface</Button>
              <Button variant="ghost" icon="view-graph" onClick={() => setTab("data")}>Graph / data</Button>
              <Button variant="ghost" icon="view-evidence" onClick={() => setTab("feedback")}>Evidence / state</Button>
            </div>
            <p className="ui-kit-note">Selection is an accent border and token wash, never a glow.</p>
          </Panel>
        </div>
      ) : null}

      {tab === "data" ? (
        <section className="ui-kit-card" aria-labelledby="ui-kit-table">
          <div className="ui-kit-card-head">
            <div><p className="ui-meta">05 / TABULAR DATA</p><h2 id="ui-kit-table">Data table</h2></div>
            <span className="ui-kit-count">{rows.length} visible / {SAMPLE_ROWS.length} demo fixtures</span>
          </div>
          <div className="ui-kit-table-filters">
            <Input label="Filter rows" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search rows" />
            <Select label="State" value={status} onValueChange={setStatus} options={STATUS_OPTIONS} />
            <Button variant="ghost" onClick={() => { setQuery(""); setStatus("all"); }}>Reset filters</Button>
          </div>
          <DataTable caption="Design system sample observations" columns={TABLE_COLUMNS} rows={rows} rowId={(row) => row.id} selectedId={selectedId} onRowSelect={setSelectedId} testId="ui-kit-table" emptyState={<EmptyState title="No matching records" description="Change or clear the filters to continue." />} />
          <p className="ui-kit-note">Selected sample record: <strong data-testid="ui-kit-selected-id">{selectedId ?? "none"}</strong></p>
        </section>
      ) : null}

      {tab === "feedback" ? (
        <div className="ui-kit-grid">
          <section className="ui-kit-card" aria-labelledby="ui-kit-empty">
            <div className="ui-kit-card-head"><div><p className="ui-meta">06 / ABSENCE</p><h2 id="ui-kit-empty">Empty state</h2></div></div>
            <EmptyState icon="view-objects" title="No entities selected" description="Select an entity from the graph or search results to inspect its evidence and relations." action={<Button variant="primary" onClick={() => setTab("primitives")}>Back to controls</Button>} />
          </section>
          <section className="ui-kit-card" aria-labelledby="ui-kit-loading">
            <div className="ui-kit-card-head"><div><p className="ui-meta">07 / LOADING</p><h2 id="ui-kit-loading">Loading state</h2></div></div>
            <Skeleton rows={4} label="Loading sample evidence rows" />
            <LoadingView message="Refreshing evidence projection…" />
          </section>
          <section className="ui-kit-card" aria-labelledby="ui-kit-error">
            <div className="ui-kit-card-head"><div><p className="ui-meta">08 / FAILURE</p><h2 id="ui-kit-error">Error state</h2></div></div>
            <ErrorView error="Source gateway returned a bounded, retryable error." onRetry={() => setClickCount((count) => count + 1)} />
          </section>
        </div>
      ) : null}

      <footer className="ui-kit-footer">
        <span>Design contract: <code>ui-upgrade.md</code></span>
        <span>Palette, type, scale, density and motion come from shared tokens.</span>
      </footer>
    </main>
  );
}
