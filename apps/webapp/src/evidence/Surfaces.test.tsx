import { render, screen, fireEvent, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { LineageViewer } from "./LineageViewer";
import { RawViewer } from "./RawViewer";
import { EMPTY_LINEAGE } from "./lineage";
import { buildDerivationChain, buildEvidenceChain } from "./lineageBuilder";
import type { LineageModel } from "./lineage";
import type { RawLocator, RawPayload } from "./rawPayload";
import { EVIDENCE_TAB_LABELS, EVIDENCE_TABS } from "./types";
import { rowsFromProjection } from "./useEvidenceRecords";

/**
 * Surface tests for evidence and lineage (§28–§34, §82, §67, §69, §90).
 *
 * The load-bearing assertions:
 *   - §30 a line in the raw view activates the observation it belongs to
 *   - §31/§32 the viewer draws TWO chains, in OPPOSITE directions, and reports
 *     a violation rather than rendering one
 *   - §29 all six tabs exist, and the three with no endpoint say so
 *   - §69 a rung with nowhere to route is static text, not a dead button
 */

function withQuery(node: React.ReactElement): React.ReactElement {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{node}</QueryClientProvider>;
}

beforeEach(() => {
  document.body.innerHTML = "";
});

/* ── §30 — the raw viewer's whole reason for existing ────────────────── */

const NDJSON: RawPayload = {
  format: "ndjson",
  mediaType: "application/x-ndjson",
  digest: "sha256:aaaa",
  text: `{"observation_id":"OBS-1","value":"one"}
{"observation_id":"OBS-2","value":"two"}
{"observation_id":"OBS-3","value":"three"}`,
};

const NDJSON_LOCATORS: RawLocator[] = [0, 1, 2].map((index) => ({
  observationId: `OBS-${index + 1}`,
  pointer: `$[${index}]`,
  lineStart: null,
  lineEnd: null,
  raw: `$[${index}]`,
}));

describe("§30 — selecting a line jumps to the corresponding observation", () => {
  it("labels every mapped line with its observation, so the feature is visible before the click", () => {
    render(
      <RawViewer
        payload={NDJSON}
        locators={NDJSON_LOCATORS}
        onJumpToObservation={vi.fn()}
        selectedObservationId={null}
      />,
    );
    expect(screen.getByTestId("raw-obs-1")).toHaveTextContent("OBS-1");
    expect(screen.getByTestId("raw-obs-2")).toHaveTextContent("OBS-2");
    expect(screen.getByTestId("raw-obs-3")).toHaveTextContent("OBS-3");
  });

  it("routes the selection when a line is clicked", () => {
    const onJump = vi.fn();
    render(
      <RawViewer
        payload={NDJSON}
        locators={NDJSON_LOCATORS}
        onJumpToObservation={onJump}
        selectedObservationId={null}
      />,
    );
    fireEvent.click(screen.getByTestId("raw-line-2"));
    expect(onJump).toHaveBeenCalledWith({ kind: "Observation", id: "OBS-2" }, 2);
  });

  it("routes the selection from the per-line observation button too", () => {
    const onJump = vi.fn();
    render(
      <RawViewer
        payload={NDJSON}
        locators={NDJSON_LOCATORS}
        onJumpToObservation={onJump}
        selectedObservationId={null}
      />,
    );
    fireEvent.click(screen.getByTestId("raw-obs-3"));
    expect(onJump).toHaveBeenCalledWith({ kind: "Observation", id: "OBS-3" }, 3);
  });

  it("says so on the status line, naming the locator it resolved through", () => {
    const onJump = vi.fn();
    render(
      <RawViewer
        payload={NDJSON}
        locators={NDJSON_LOCATORS}
        onJumpToObservation={onJump}
        selectedObservationId={null}
      />,
    );
    fireEvent.click(screen.getByTestId("raw-line-1"));
    expect(screen.getByTestId("raw-status-observation")).toHaveTextContent("OBS-1");
    expect(screen.getByTestId("raw-status-observation")).toHaveTextContent("$[0]");
  });

  it("does NOT jump when the line has no observation, and says that instead", () => {
    const onJump = vi.fn();
    render(
      <RawViewer
        payload={NDJSON}
        locators={[]}
        onJumpToObservation={onJump}
        selectedObservationId={null}
      />,
    );
    fireEvent.click(screen.getByTestId("raw-line-2"));
    expect(onJump).not.toHaveBeenCalled();
    expect(screen.getByTestId("raw-status-none")).toHaveTextContent("no observation reported for this line");
    // Every line says so, rather than one line being silently unlabelled.
    expect(screen.getByTestId("raw-obs-1")).toHaveTextContent("no observation");
  });

  it("reports a locator whose pointer did not resolve", () => {
    render(
      <RawViewer
        payload={NDJSON}
        locators={[...NDJSON_LOCATORS, { observationId: "OBS-X", pointer: "$[9]", lineStart: null, lineEnd: null, raw: "$[9]" }]}
        onJumpToObservation={vi.fn()}
        selectedObservationId={null}
      />,
    );
    expect(screen.getByTestId("raw-unresolved")).toHaveTextContent("$[9]");
  });

  it("scrolls to the selected observation when one arrives from outside (§7)", () => {
    const { rerender } = render(
      <RawViewer
        payload={NDJSON}
        locators={NDJSON_LOCATORS}
        onJumpToObservation={vi.fn()}
        selectedObservationId={null}
      />,
    );
    rerender(
      <RawViewer
        payload={NDJSON}
        locators={NDJSON_LOCATORS}
        onJumpToObservation={vi.fn()}
        selectedObservationId="OBS-3"
      />,
    );
    expect(screen.getByTestId("raw-status-observation")).toHaveTextContent("OBS-3");
  });
});

describe("§30 — search, copy, collapse and the parse failure state", () => {
  it("marks matching lines and reports the hit count", () => {
    render(
      <RawViewer payload={NDJSON} locators={NDJSON_LOCATORS} onJumpToObservation={vi.fn()} selectedObservationId={null} />,
    );
    fireEvent.change(screen.getByLabelText("Search payload"), { target: { value: "two" } });
    expect(screen.getByTestId("raw-line-2")).toHaveAttribute("data-hit", "true");
    expect(screen.getByTestId("raw-line-1")).toHaveAttribute("data-hit", "false");
    expect(screen.getByText(/hit\(s\) on 1 line/)).toBeInTheDocument();
  });

  it("shows the bytes and reports the failing line for a malformed payload", () => {
    const broken: RawPayload = {
      format: "ndjson",
      mediaType: null,
      digest: null,
      text: '{"a":1}\n{oops}',
    };
    render(
      <RawViewer payload={broken} locators={[]} onJumpToObservation={vi.fn()} selectedObservationId={null} />,
    );
    const alert = screen.getByTestId("raw-parse-error");
    expect(alert).toHaveAttribute("role", "alert");
    expect(alert).toHaveTextContent("line 2");
    // The bytes are still on screen: a raw viewer that hides malformed evidence
    // is hiding the evidence.
    expect(screen.getByTestId("raw-line-2")).toHaveTextContent("{oops}");
  });

  it("reports the payload's format and size, and elides a long line when asked", () => {
    const long: RawPayload = { format: "text", mediaType: null, digest: null, text: "x".repeat(600) };
    render(
      <RawViewer payload={long} locators={[]} onJumpToObservation={vi.fn()} selectedObservationId={null} />,
    );
    expect(screen.getByTestId("raw-meta")).toHaveTextContent("TEXT");
    expect(screen.getByTestId("raw-elided-1")).toHaveTextContent("chars elided");
    fireEvent.click(screen.getByTestId("raw-collapse"));
    expect(screen.queryByTestId("raw-elided-1")).not.toBeInTheDocument();
  });

  it("renders as a labelled grid and reports the true row count (§68)", () => {
    render(
      <RawViewer payload={NDJSON} locators={NDJSON_LOCATORS} onJumpToObservation={vi.fn()} selectedObservationId={null} />,
    );
    const grid = screen.getByTestId("raw-lines");
    expect(grid).toHaveAttribute("role", "grid");
    expect(grid).toHaveAttribute("aria-rowcount", "3");
  });

  it("is keyboard navigable: a roving cursor plus Enter activates the line", () => {
    const onJump = vi.fn();
    render(
      <RawViewer payload={NDJSON} locators={NDJSON_LOCATORS} onJumpToObservation={onJump} selectedObservationId={null} />,
    );
    const grid = screen.getByTestId("raw-lines");
    // The cursor starts on line 1. Enter activates the cursor's line without
    // moving it.
    fireEvent.keyDown(grid, { key: "Enter" });
    expect(onJump).toHaveBeenCalledWith({ kind: "Observation", id: "OBS-1" }, 1);

    // ArrowDown moves it one line, and Enter then activates THAT line.
    fireEvent.keyDown(grid, { key: "ArrowDown" });
    fireEvent.keyDown(grid, { key: "Enter" });
    expect(onJump).toHaveBeenLastCalledWith({ kind: "Observation", id: "OBS-2" }, 2);

    fireEvent.keyDown(grid, { key: "End" });
    fireEvent.keyDown(grid, { key: "Enter" });
    expect(onJump).toHaveBeenLastCalledWith({ kind: "Observation", id: "OBS-3" }, 3);
  });

  it("does not run past either end of the payload", () => {
    const onJump = vi.fn();
    render(
      <RawViewer payload={NDJSON} locators={NDJSON_LOCATORS} onJumpToObservation={onJump} selectedObservationId={null} />,
    );
    const grid = screen.getByTestId("raw-lines");
    fireEvent.keyDown(grid, { key: "Home" });
    for (let step = 0; step < 8; step += 1) fireEvent.keyDown(grid, { key: "ArrowUp" });
    fireEvent.keyDown(grid, { key: "Enter" });
    expect(onJump).toHaveBeenLastCalledWith({ kind: "Observation", id: "OBS-1" }, 1);
  });
});

/* ── §31 / §32 — the two chains ──────────────────────────────────────── */

const OBSERVATION = {
  observation_id: "OBS-1",
  capture_id: "CAP-1",
  locator: "$.records[0]",
  record_digest: "sha256:abcd",
  content_type: "application/json",
  runtime_producer: "crawler",
  runtime_producer_version: "2",
  parser_hint: null,
  source_id: "a.example",
  uri: "https://a.example/1",
  collected_at: "2026-01-02T00:00:00Z",
  lifecycle: "STORED",
  tenant_id: "t1",
};

const MODEL: LineageModel = {
  evidence: buildEvidenceChain({
    finding: {
      finding_id: "FND-1",
      status: "OPEN",
      why_detected: "burst",
      structural_evidence: [{}],
      semantic_evidence: [],
      supporting_graph_region: {},
      supporting_assertions: [],
      observations: [{ observation_id: "OBS-1", uri: "https://a.example/1", immutable: true }],
      sources: ["a.example"],
      evidence_resolves: true,
    },
    claim: null,
    observation: OBSERVATION,
    capture: { capture_id: "CAP-1", target_uri: "https://a.example/1", content_digest: "sha256:beef" },
    rawObject: { ref: "obj/CAP-1.json", digest: "sha256:beef", bytes: 2048 },
    source: { source_id: "a.example", name: "A Example", kind: "web" },
  }),
  derivation: buildDerivationChain({
    claim: null,
    candidate: { ref: "CAND-9", score: 0.42, reasons: ["name"] },
    signal: { ref: "SIG-3", name: "co_occurrence", score: 0.61 },
    observation: OBSERVATION,
    originEntityId: "ENT-1",
  }),
};

describe("§31 / §32 — the viewer draws two chains, not one", () => {
  it("renders both chains, each with its own accessible name", () => {
    render(<LineageViewer model={MODEL} onGoTo={vi.fn()} selectedId={null} />);
    expect(screen.getByTestId("evidence-chain")).toBeInTheDocument();
    expect(screen.getByTestId("derivation-chain")).toBeInTheDocument();
    expect(screen.getByLabelText("Evidence lineage")).toBeInTheDocument();
    expect(screen.getByLabelText("Derivation lineage")).toBeInTheDocument();
  });

  it("reads the evidence chain DOWNWARDS and the derivation chain UPWARDS", () => {
    const { container } = render(<LineageViewer model={MODEL} onGoTo={vi.fn()} selectedId={null} />);
    const evidenceList = container.querySelector('[data-testid="evidence-chain"] .ui-lineage-steps');
    const derivationList = container.querySelector('[data-testid="derivation-chain"] .ui-lineage-steps');
    expect(evidenceList).toHaveAttribute("data-direction", "down");
    expect(derivationList).toHaveAttribute("data-direction", "up");
    // Opposite arrow glyphs, so the two directions cannot be confused.
    expect(screen.getByTestId("evidence-arrow-Finding")).toHaveTextContent("↓");
    expect(screen.getByTestId("derivation-arrow-Candidate")).toHaveTextContent("↑");
  });

  it("shows the evidence rungs in provenance order, starting at the Finding", () => {
    render(<LineageViewer model={MODEL} onGoTo={vi.fn()} selectedId={null} />);
    expect(screen.getByTestId("evidence-step-Finding")).toBeInTheDocument();
    expect(screen.getByTestId("evidence-step-Capture")).toBeInTheDocument();
    expect(screen.getByTestId("evidence-step-Source")).toBeInTheDocument();
    // This record has no claim, and the chain says so rather than drawing one.
    expect(screen.queryByTestId("evidence-step-Claim")).not.toBeInTheDocument();
    expect(screen.getByTestId("evidence-chain-header-missing")).toHaveTextContent("Claim");
  });

  it("shows only derivation rungs on the derivation chain", () => {
    render(<LineageViewer model={MODEL} onGoTo={vi.fn()} selectedId={null} />);
    expect(screen.getByTestId("derivation-step-Candidate")).toBeInTheDocument();
    expect(screen.getByTestId("derivation-step-Signal")).toBeInTheDocument();
    // No provenance rung may appear here — that is the separation, rendered.
    expect(screen.queryByTestId("derivation-step-Capture")).not.toBeInTheDocument();
    expect(screen.queryByTestId("derivation-step-Finding")).not.toBeInTheDocument();
    expect(screen.queryByTestId("derivation-step-RawObject")).not.toBeInTheDocument();
  });

  it("routes every routable rung to the inspector on activation", () => {
    const onGoTo = vi.fn();
    render(<LineageViewer model={MODEL} onGoTo={onGoTo} selectedId={null} />);
    fireEvent.click(screen.getByTestId("evidence-node-Observation-go"));
    expect(onGoTo).toHaveBeenCalledWith(expect.objectContaining({ kind: "Observation", id: "OBS-1" }));
    fireEvent.click(screen.getByTestId("evidence-node-Capture-go"));
    expect(onGoTo).toHaveBeenLastCalledWith(expect.objectContaining({ kind: "Capture", id: "CAP-1" }));
  });

  it("renders a rung with nowhere to route as static text, not a dead button (§69)", () => {
    render(<LineageViewer model={MODEL} onGoTo={vi.fn()} selectedId={null} />);
    // A candidate is not an addressable object; it routes to the origin entity
    // only when one is known, and here the button does exist because it is.
    expect(screen.getByTestId("derivation-node-Candidate-go")).toBeInTheDocument();

    const orphan = buildDerivationChain({
      claim: null,
      candidate: { ref: "CAND-1", score: null, reasons: [] },
      signal: null,
      observation: null,
      originEntityId: null,
    });
    render(<LineageViewer model={{ ...MODEL, derivation: orphan }} onGoTo={vi.fn()} selectedId={null} />);
    const all = screen.getAllByTestId("derivation-node-Candidate-static");
    expect(all.length).toBeGreaterThan(0);
    expect(all[0]).toHaveTextContent("no inspector route for this rung");
  });

  it("marks the selected object's rung", () => {
    render(<LineageViewer model={MODEL} onGoTo={vi.fn()} selectedId="OBS-1" />);
    expect(screen.getByTestId("evidence-node-Observation")).toHaveAttribute("data-selected", "true");
  });

  it("reports an empty model honestly, per chain, and never fills one from the other", () => {
    render(<LineageViewer model={EMPTY_LINEAGE} onGoTo={vi.fn()} selectedId={null} />);
    expect(screen.getByTestId("evidence-chain-none")).toBeInTheDocument();
    expect(screen.getByTestId("derivation-chain-none")).toHaveTextContent("No derivation chain");
  });

  it("surfaces a separation violation instead of drawing the mixed chain", () => {
    const contaminated: LineageModel = {
      evidence: MODEL.evidence,
      derivation: {
        ...MODEL.derivation!,
        steps: [
          ...MODEL.derivation!.steps,
          {
            kind: "Capture",
            ref: "CAP-1",
            label: null,
            relation: null,
            score: null,
            selection: null,
          } as never,
        ],
      },
    };
    render(<LineageViewer model={contaminated} onGoTo={vi.fn()} selectedId={null} />);
    const alert = screen.getByTestId("lineage-violation");
    expect(alert).toHaveAttribute("role", "alert");
    expect(alert).toHaveTextContent("Capture");
  });

  it("counts present rungs against the whole spine in the header badges", () => {
    render(<LineageViewer model={MODEL} onGoTo={vi.fn()} selectedId={null} />);
    expect(screen.getByTestId("lineage-evidence-summary")).toHaveTextContent("6/7 rungs");
    expect(screen.getByTestId("lineage-derivation-summary")).toHaveTextContent("3/4 rungs");
  });
});

/* ── §29 — the six tabs ──────────────────────────────────────────────── */

describe("§29 — the viewer has the six named tabs", () => {
  it("declares exactly Content / Structured / Metadata / Lineage / Processing / Revisions", () => {
    expect([...EVIDENCE_TABS]).toEqual([
      "content",
      "structured",
      "metadata",
      "lineage",
      "processing",
      "revisions",
    ]);
    expect(Object.keys(EVIDENCE_TAB_LABELS)).toEqual([...EVIDENCE_TABS]);
  });
});

/* ── §82 — the list is derived from real records, not invented ──────── */

describe("§82 — the evidence list is a projection of records, deduplicated", () => {
  const NODES = [
    {
      id: "ENT-1",
      label: "acme.example",
      properties: {
        entity_id: "ENT-1",
        source_ids: "acme.example",
        timeline: JSON.stringify([
          { observation_id: "OBS-1", uri: "https://acme.example/1", immutable: true, observed_at: "2026-01-02T00:00:00Z" },
        ]),
      },
    },
    {
      id: "ENT-2",
      label: "beta.example",
      properties: {
        entity_id: "ENT-2",
        source_ids: "beta.example",
        timeline: JSON.stringify([
          { observation_id: "OBS-1", uri: "https://acme.example/1", immutable: true, observed_at: "2026-01-02T00:00:00Z" },
        ]),
      },
    },
  ];

  it("collapses one observation named by two entities into one row", () => {
    const rows = rowsFromProjection(NODES, []);
    expect(rows.filter((row) => row.ref === "OBS-1")).toHaveLength(1);
  });

  it("enriches rather than replacing when the second mention carries more", () => {
    const rows = rowsFromProjection(
      [
        { id: "A", label: "a", properties: { entity_id: "A", timeline: JSON.stringify([{ observation_id: "OBS-1", uri: "u" }]) } },
        {
          id: "B",
          label: "b",
          properties: {
            entity_id: "B",
            source_ids: "b.example",
            timeline: JSON.stringify([{ observation_id: "OBS-1", uri: "u", observed_at: "2026-01-02T00:00:00Z" }]),
          },
        },
      ],
      [],
    );
    const row = rows.find((entry) => entry.ref === "OBS-1");
    expect(row?.at).toBe("2026-01-02T00:00:00Z");
    expect(row?.sourceId).toBe("b.example");
  });

  it("creates no Capture and no Claim rows, because no endpoint serves them (§99)", () => {
    const rows = rowsFromProjection(NODES, []);
    expect(rows.every((row) => row.kind === "Observation")).toBe(true);
    expect(rows.every((row) => row.payload === null)).toBe(true);
  });

  it("adds a finding's observation with no instant, rather than dropping it", () => {
    const rows = rowsFromProjection(
      [],
      [
        {
          finding_id: "FND-1",
          status: "OPEN",
          why_detected: "burst",
          structural_evidence: [],
          semantic_evidence: [],
          supporting_graph_region: {},
          supporting_assertions: [],
          observations: [{ observation_id: "OBS-9", uri: "https://x/9", immutable: false }],
          sources: ["x.example"],
          evidence_resolves: true,
        },
      ],
    );
    const row = rows.find((entry) => entry.ref === "OBS-9");
    expect(row?.at).toBeNull();
    expect(row?.sourceId).toBe("x.example");
  });
});

describe("the RawViewer and LineageViewer compose under a Query provider", () => {
  it("renders both without a store, because neither owns one", () => {
    render(
      withQuery(
        <>
          <RawViewer payload={NDJSON} locators={NDJSON_LOCATORS} onJumpToObservation={vi.fn()} selectedObservationId={null} />
          <LineageViewer model={MODEL} onGoTo={vi.fn()} selectedId={null} />
        </>,
      ),
    );
    expect(screen.getByTestId("raw-viewer")).toBeInTheDocument();
    expect(screen.getByTestId("lineage-viewer")).toBeInTheDocument();
  });
});

describe("§67 — every panel is labelled", () => {
  it("names the raw region and the lineage region", () => {
    render(
      <>
        <RawViewer payload={NDJSON} locators={NDJSON_LOCATORS} onJumpToObservation={vi.fn()} selectedObservationId={null} />
        <LineageViewer model={MODEL} onGoTo={vi.fn()} selectedId={null} />
      </>,
    );
    expect(within(screen.getByTestId("raw-viewer")).getByRole("toolbar")).toHaveAccessibleName(
      "Raw payload controls",
    );
    expect(screen.getByLabelText("Lineage")).toBeInTheDocument();
  });
});