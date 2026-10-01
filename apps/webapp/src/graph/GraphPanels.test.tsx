import { render, screen, fireEvent, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { EdgeDetails, NodeDetails } from "./GraphDetails";
import { GraphFilterDrawer } from "./GraphFilterDrawer";
import { GraphToolbar } from "./GraphToolbar";
import { EMPTY_GRAPH_FACETS, type GraphFacets } from "./filters";
import { expansionChoices } from "./expansion";
import { LAYOUT_NAMES } from "./layout";
import { buildGraphModel, type GraphInput } from "./model";

/**
 * Surface tests for the graph's panels and toolbar (§15, §17, §22, §67, §69).
 *
 * The Cytoscape canvas itself is not tested here: jsdom has no layout engine, so
 * a canvas there is a black box that swallows every interaction and would only
 * ever assert that the import resolved. What IS tested is everything around it —
 * and everything around it is where the §17 contract and the §69 no-dead-end
 * rule actually live.
 */

const INPUT: GraphInput = {
  entities: [
    {
      entity_id: "ENT-1",
      label: "acme.example",
      evidence: [{ evidence_id: "EV-A", observation_id: "OBS-A", immutable: true }],
      timeline: [{ observation_id: "OBS-A", uri: "https://acme.example/a", immutable: true, observed_at: "2026-01-10T00:00:00Z" }],
      sourceIds: ["acme.example"],
      relationships: [{ target: "ENT-2", type: "works_for" }],
    },
    { entity_id: "ENT-2", label: "beta.example", evidence: [], sourceIds: ["beta.example"] },
  ],
  findings: [],
  correlations: [],
};

const MODEL = buildGraphModel(INPUT);

function withQuery(node: React.ReactElement): React.ReactElement {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{node}</QueryClientProvider>;
}

beforeEach(() => {
  document.body.innerHTML = "";
});

/* ── §17 — the edge panel shows exactly the seven things §17 names ────── */

describe("§17 — selecting an edge shows predicate, participants, scope, status, counts and actions", () => {
  const edge = MODEL.edges.find((candidate) => candidate.predicate === "works_for") ?? MODEL.edges[0];

  function renderPanel() {
    return render(
      <EdgeDetails
        edge={edge ?? null}
        model={MODEL}
        onGoTo={vi.fn()}
        onGoToView={vi.fn()}
        onExpandEdge={vi.fn()}
      />,
    );
  }

  it("shows all seven required facts, each under its own test id", () => {
    if (!edge) throw new Error("fixture produced no edge");
    renderPanel();
    for (const id of [
      "edge-predicate",
      "edge-participants",
      "edge-temporal",
      "edge-status-value",
      "edge-evidence-count",
      "edge-claim-count",
      "edge-actions",
    ]) {
      expect(screen.getByTestId(id), id).toBeInTheDocument();
    }
  });

  it("shows the predicate verbatim, not a prettified restatement of it", () => {
    if (!edge) throw new Error("fixture produced no edge");
    renderPanel();
    expect(screen.getByTestId("edge-predicate")).toHaveTextContent("works_for");
  });

  it("names both participants and says which is which", () => {
    if (!edge) throw new Error("fixture produced no edge");
    renderPanel();
    const participants = screen.getByTestId("edge-participants");
    expect(within(participants).getByTestId("edge-subject")).toBeInTheDocument();
    expect(within(participants).getByTestId("edge-object")).toBeInTheDocument();
  });

  it("reports an unreported status as such, never as an empty row or a guess", () => {
    const bare = { ...edge!, status: null };
    render(
      <EdgeDetails edge={bare} model={MODEL} onGoTo={vi.fn()} onGoToView={vi.fn()} onExpandEdge={vi.fn()} />,
    );
    expect(screen.getByTestId("edge-status-value")).toHaveTextContent("not reported");
    expect(screen.getByTestId("edge-status-unreported")).toBeInTheDocument();
  });

  it("reports an open temporal bound as 'open', not as a missing value", () => {
    if (!edge) throw new Error("fixture produced no edge");
    renderPanel();
    expect(screen.getByTestId("edge-temporal")).toHaveTextContent("open");
  });

  it("offers next steps, and every one of them has a destination (§69)", () => {
    if (!edge) throw new Error("fixture produced no edge");
    renderPanel();
    const actions = screen.getByTestId("edge-actions");
    expect(within(actions).getByTestId("edge-action-expand")).toBeInTheDocument();
    expect(within(actions).getByTestId("edge-action-timeline")).toBeInTheDocument();
  });

  it("routes a participant to the global selection when activated", () => {
    if (!edge) throw new Error("fixture produced no edge");
    const onGoTo = vi.fn();
    render(
      <EdgeDetails edge={edge} model={MODEL} onGoTo={onGoTo} onGoToView={vi.fn()} onExpandEdge={vi.fn()} />,
    );
    fireEvent.click(screen.getByTestId("edge-subject-go"));
    expect(onGoTo).toHaveBeenCalledWith(expect.objectContaining({ kind: "Entity" }));
  });

  it("says so honestly when no edge is selected", () => {
    render(<EdgeDetails edge={null} model={MODEL} onGoTo={vi.fn()} onGoToView={vi.fn()} onExpandEdge={vi.fn()} />);
    expect(screen.getByTestId("graph-edge-empty")).toBeInTheDocument();
  });
});

/* ── §69 — the node panel never dead-ends ────────────────────────────── */

describe("§69 — every selected object offers a next step", () => {
  it("offers expand and comparison for an entity, and reports its own facts", () => {
    const node = MODEL.nodeIndex.get("Entity:ENT-1");
    render(
      <NodeDetailsPanel node={node ?? null} />,
    );
    expect(screen.getByTestId("node-action-expand")).toBeInTheDocument();
    expect(screen.getByTestId("node-action-compare")).toBeInTheDocument();
    expect(screen.getByTestId("node-kind")).toHaveTextContent("Entity");
    expect(screen.getByTestId("node-identifier")).toHaveTextContent("ENT-1");
  });

  it("marks a hypothesis as provisional in words, not only by a dashed border", () => {
    const candidate = buildGraphModel({
      entities: [{ entity_id: "ENT-9", label: "e", evidence: [] }],
      findings: [],
      correlations: [
        {
          edge_id: "E1",
          candidate_a: "ENT-9",
          candidate_b: "CAND-1",
          kind: "possible_match",
          raw_pair_score: 0.3,
          collective_score: 0.3,
          reasons: ["name"],
          state: "OPEN",
          origin_entity: "ENT-9",
        },
      ],
    });
    render(<NodeDetailsPanel node={candidate.nodeIndex.get("Hypothesis:CAND-1") ?? null} />);
    expect(screen.getByTestId("node-provisional")).toHaveTextContent("provisional");
    expect(screen.getByTestId("node-admission")).toHaveTextContent("Provisional");
  });

  it("links a hypothesis back to the entity whose correlation produced it", () => {
    const candidate = buildGraphModel({
      entities: [{ entity_id: "ENT-9", label: "e", evidence: [] }],
      findings: [],
      correlations: [
        {
          edge_id: "E1",
          candidate_a: "ENT-9",
          candidate_b: "CAND-1",
          kind: "possible_match",
          raw_pair_score: 0.3,
          collective_score: 0.3,
          reasons: ["name"],
          state: "OPEN",
          origin_entity: "ENT-9",
        },
      ],
    });
    const node = candidate.nodeIndex.get("Hypothesis:CAND-1") ?? null;
    const onGoTo = vi.fn();
    render(
      <NodeDetails
        node={node}
        model={candidate}
        onGoTo={onGoTo}
        onGoToView={vi.fn()}
        onExpandNode={vi.fn()}
        onToggleSecondary={vi.fn()}
        isSecondary={false}
      />,
    );
    fireEvent.click(screen.getByTestId("node-origin-go"));
    expect(onGoTo).toHaveBeenCalledWith({ kind: "Entity", id: "ENT-9" });
  });
});

function NodeDetailsPanel({ node }: { node: import("./types").GraphNode | null }) {
  return (
    <NodeDetails
      node={node}
      model={MODEL}
      onGoTo={vi.fn()}
      onGoToView={vi.fn()}
      onExpandNode={vi.fn()}
      onToggleSecondary={vi.fn()}
      isSecondary={false}
    />
  );
}

/* ── §22 — the drawer offers only what the model has ─────────────────── */

describe("§22 — the filter drawer", () => {
  function renderDrawer(facets: GraphFacets = EMPTY_GRAPH_FACETS, onToggle = vi.fn()) {
    render(
      <GraphFilterDrawer
        open
        onClose={vi.fn()}
        model={MODEL}
        facets={facets}
        onToggle={onToggle}
        onQueryChange={vi.fn()}
        onReset={vi.fn()}
        visibleNodeCount={MODEL.nodes.length}
      />,
    );
    return onToggle;
  }

  it("renders nothing when closed", () => {
    render(
      <GraphFilterDrawer
        open={false}
        onClose={vi.fn()}
        model={MODEL}
        facets={EMPTY_GRAPH_FACETS}
        onToggle={vi.fn()}
        onQueryChange={vi.fn()}
        onReset={vi.fn()}
        visibleNodeCount={0}
      />,
    );
    expect(screen.queryByTestId("graph-filter-drawer")).not.toBeInTheDocument();
  });

  it("renders all eight facet groups, each as a labelled group", () => {
    renderDrawer();
    for (const id of [
      "kinds",
      "relations",
      "sourceIds",
      "evidenceStates",
      "admissions",
      "timeRange",
      "investigationIds",
    ]) {
      expect(screen.getByTestId(`facet-${id}`), id).toBeInTheDocument();
    }
  });

  it("marks a facet active only when it is narrowing", () => {
    renderDrawer({ ...EMPTY_GRAPH_FACETS, kinds: ["Entity"] });
    expect(screen.getByTestId("facet-kinds")).toHaveAttribute("data-active", "true");
    expect(screen.getByTestId("facet-relations")).toHaveAttribute("data-active", "false");
  });

  it("offers only the kinds the model actually contains", () => {
    renderDrawer();
    expect(screen.getByTestId("facet-kinds-Entity")).toBeInTheDocument();
    expect(screen.getByTestId("facet-kinds-Observation")).toBeInTheDocument();
    // There are no findings and no claims in this fixture.
    expect(screen.queryByTestId("facet-kinds-Finding")).not.toBeInTheDocument();
    expect(screen.queryByTestId("facet-kinds-Claim")).not.toBeInTheDocument();
  });

  it("reports the visible/total counts, so a facet's effect is legible", () => {
    render(
      <GraphFilterDrawer
        open
        onClose={vi.fn()}
        model={MODEL}
        facets={EMPTY_GRAPH_FACETS}
        onToggle={vi.fn()}
        onQueryChange={vi.fn()}
        onReset={vi.fn()}
        visibleNodeCount={2}
      />,
    );
    expect(screen.getByTestId("graph-filter-visible")).toHaveTextContent(`2/${MODEL.nodes.length}`);
  });

  it("reports the temporal range as owned by the workspace, not by the drawer", () => {
    renderDrawer({ ...EMPTY_GRAPH_FACETS, timeRange: { from: "2026-01-01T00:00:00Z", to: null } });
    expect(screen.getByTestId("facet-timeRange-value")).toHaveTextContent("2026-01-01T00:00:00Z");
  });

  it("disables reset until a facet is active, and names the active ones", () => {
    renderDrawer();
    expect(screen.getByTestId("graph-filter-reset")).toBeDisabled();
    expect(screen.getByTestId("graph-filter-active")).toHaveTextContent("no filters");
  });

  it("says so honestly when there is nothing to filter", () => {
    render(
      <GraphFilterDrawer
        open
        onClose={vi.fn()}
        model={buildGraphModel({ entities: [], findings: [], correlations: [] })}
        facets={EMPTY_GRAPH_FACETS}
        onToggle={vi.fn()}
        onQueryChange={vi.fn()}
        onReset={vi.fn()}
        visibleNodeCount={0}
      />,
    );
    expect(screen.getByTestId("graph-drawer-empty")).toBeInTheDocument();
  });
});

/* ── §15 — the toolbar's fourteen actions ────────────────────────────── */

describe("§15 — the toolbar", () => {
  function renderToolbar(overrides: Partial<Parameters<typeof GraphToolbar>[0]> = {}) {
    const props = {
      mode: "select" as const,
      onModeChange: vi.fn(),
      query: "",
      onQueryChange: vi.fn(),
      matchCount: null,
      expansions: expansionChoices(["acme.example"]),
      onExpand: vi.fn(),
      expandedNodeCount: 0,
      onCollapse: vi.fn(),
      onFocus: vi.fn(),
      onFit: vi.fn(),
      layout: "cose" as const,
      onLayoutChange: vi.fn(),
      activeFacets: [],
      onToggleFilterDrawer: vi.fn(),
      filterDrawerOpen: false,
      pathAvailable: false,
      onFindPath: vi.fn(),
      secondaryCount: 0,
      onCompare: vi.fn(),
      temporalActive: false,
      onToggleTemporal: vi.fn(),
      onExport: vi.fn(),
      counts: { entities: 2, observations: 1, findings: 0, hypotheses: 0, edges: 2 },
      coverage: { loaded: ["/entities/graph"], missing: ["/relations"] },
      disabled: false,
      ...overrides,
    };
    return { props, ...render(withQuery(<GraphToolbar {...props} />)) };
  }

  it("renders as a toolbar with an accessible name (§67)", () => {
    renderToolbar();
    const toolbar = screen.getByTestId("graph-toolbar");
    expect(toolbar).toHaveAttribute("role", "toolbar");
    expect(toolbar).toHaveAttribute("aria-label", "Graph controls");
  });

  it("offers both pointer modes and reports which is active", () => {
    renderToolbar();
    expect(screen.getByTestId("graph-mode-select")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("graph-mode-lasso")).toHaveAttribute("aria-pressed", "false");
  });

  it("offers both hop expansions and a constrained menu, and no 'everything'", () => {
    renderToolbar();
    expect(screen.getByTestId("expand.1hop")).toBeInTheDocument();
    expect(screen.getByTestId("expand.2hops")).toBeInTheDocument();
    expect(screen.getByTestId("expand-constraint")).toBeInTheDocument();
    expect(screen.queryByText(/everything/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/show all/i)).not.toBeInTheDocument();
  });

  it("disables collapse until something has been expanded", () => {
    renderToolbar();
    expect(screen.getByTestId("graph-collapse")).toBeDisabled();
  });

  it("disables path until two objects are in play, and explains why", () => {
    renderToolbar();
    expect(screen.getByTestId("graph-path")).toBeDisabled();
  });

  it("enables path once two objects are selected", () => {
    renderToolbar({ pathAvailable: true });
    expect(screen.getByTestId("graph-path")).not.toBeDisabled();
  });

  it("disables compare until the comparison set is non-empty, and counts it", () => {
    renderToolbar();
    expect(screen.getByTestId("graph-compare")).toBeDisabled();
    renderToolbar({ secondaryCount: 2 });
    expect(screen.getAllByTestId("graph-compare")[1]).toHaveTextContent("Compare (2)");
  });

  it("reports temporal mode as pressed state, not as a separate indicator", () => {
    renderToolbar();
    expect(screen.getByTestId("graph-temporal-toggle")).toHaveAttribute("aria-pressed", "false");
  });

  it("counts the active filters on the filter control", () => {
    renderToolbar({ activeFacets: ["kinds", "timeRange"] });
    expect(screen.getByTestId("graph-filter-toggle")).toHaveTextContent("Filters (2)");
  });

  it("reports real counts and the endpoints that are missing", () => {
    renderToolbar();
    expect(screen.getByTestId("graph-count-entities")).toHaveTextContent("2 entity");
    expect(screen.getByTestId("graph-count-observations")).toHaveTextContent("1 obs");
    // The coverage readout names the gap rather than hiding it (§99).
    expect(screen.getByTestId("graph-coverage")).toHaveTextContent("1 endpoints missing");
  });

  it("exposes every layout the layout module declares, so the two cannot drift", () => {
    renderToolbar();
    const select = screen.getByLabelText("Layout");
    const options = within(select).getAllByRole("option").map((option) => option.getAttribute("value"));
    expect(options).toEqual([...LAYOUT_NAMES]);
  });

  it("disables the whole surface when there is nothing to show", () => {
    renderToolbar({ disabled: true });
    expect(screen.getByTestId("graph-mode-select")).toBeDisabled();
    expect(screen.getByTestId("graph-export")).toBeDisabled();
  });

  it("keeps search and filters enabled when the model HAS objects but the facets hide them all", () => {
    // The recovery path from a filtered-to-empty canvas is the search box and
    // the filter drawer, so neither may be disabled while objects exist. This is
    // the case `disabled` must NOT be reached for.
    renderToolbar({ disabled: false, activeFacets: ["kinds"], matchCount: 0 });
    expect(screen.getByTestId("graph-filter-toggle")).not.toBeDisabled();
    expect(screen.getByLabelText("Search objects")).not.toBeDisabled();
  });

  it("does enable search and filters — with nothing loaded they are not disabled either, because they are harmless", () => {
    // `disabled` here means "the model is empty". Search and filter stay live:
    // a disabled search box tells the analyst the graph is broken, when in fact
    // it simply has nothing in it yet.
    renderToolbar({ disabled: true });
    expect(screen.getByLabelText("Search objects")).not.toBeDisabled();
  });
});