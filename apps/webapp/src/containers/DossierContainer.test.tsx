import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DossierContainer } from "./DossierContainer";
import { DossierPage } from "../pages/DossierPage";
import type { Dossier, EnrichResult } from "../lib/dossier/types";

vi.mock("../lib/dossier/api", () => ({
  dossierApi: {
    listSubjects: vi.fn(),
    getDossier: vi.fn(),
    enrich: vi.fn(),
  },
}));

const { dossierApi } = await import("../lib/dossier/api");

function dossier(overrides: Partial<Dossier> = {}): Dossier {
  return {
    dossier_id: "DS-1",
    identity: { entity_ref: "REF-1", type_label: "domain", stream_anchor: "evt-1", revision: 1 },
    is_empty: false,
    is_complete: false,
    timeline: [],
    links: { subject: "REF-1", nodes: [], degree: 0, edges: [] },
    contacts: { kinds: [], contacts: [] },
    coverage: {
      plan_known: true,
      attributes: {
        total: 92,
        acquired: 7,
        empty: 3,
        conflict: 0,
        unknown: 82,
        refused: 0,
        corroborated: 1,
        distinct_sources: 9,
        ratio: 0.109,
        saturated: false,
      },
      traced_facts: 2,
      total_facts: 2,
      traced_edges: 4,
      total_edges: 4,
      traced_contacts: 0,
      total_contacts: 0,
      dormant_windows: 1625,
      untraced_facts: 0,
      untraced_edges: 0,
      untraced_contacts: 0,
      untraced_conflicts: 0,
      untraced_total: 0,
      traced_ratio: 1,
      is_traceable: true,
    },
    gaps: [
      {
        attribute: "abuse_contact",
        candidate_sources: ["SRC-a"],
        blocked_sources: [],
        candidate_source_names: ["ripe_stat"],
        blocked_source_names: [],
      },
    ],
    conflicts: [],
    ...overrides,
  };
}

/**
 * Switch to a tab before asserting on its panel.
 *
 * The tabs render only the active view, so a test that asserts on the Gaps table without
 * opening it is asserting against a component that is not on screen -- it would pass or fail
 * for reasons unrelated to what it claims to check.
 */
function showView(label: RegExp) {
  fireEvent.click(screen.getByRole("tab", { name: label }));
}

function pageProps(overrides: Partial<Parameters<typeof DossierPage>[0]> = {}) {
  return {
    subjects: [],
    dossier: null,
    reports: [],
    refusals: [],
    discovered: [],
    knownAttributes: [],
    query: "",
    sweeping: false,
    error: null,
    invariantError: "",
    onSweep: vi.fn(),
    onOpen: vi.fn(),
    ...overrides,
  };
}

describe("DossierPage — absence is shown, not implied", () => {
  it("says plainly that nothing has been swept yet", () => {
    render(<DossierPage {...pageProps()} />);

    expect(screen.getByTestId("dossier-empty")).toBeInTheDocument();
    expect(screen.getByText(/nothing has been swept/i)).toBeInTheDocument();
  });

  it("does not present an unknown coverage as zero", () => {
    render(
      <DossierPage
        {...pageProps({
          dossier: dossier({
            coverage: { ...dossier().coverage, plan_known: false, attributes: null },
          }),
        })}
      />,
    );

    expect(screen.getByTestId("dossier-coverage-unknown")).toBeInTheDocument();
    expect(screen.getByText(/absence here is not absence in the world/i)).toBeInTheDocument();
  });

  it("separates 'queue is empty' from 'fully known'", () => {
    render(
      <DossierPage
        {...pageProps({
          dossier: dossier({
            coverage: {
              ...dossier().coverage,
              attributes: { ...dossier().coverage.attributes!, saturated: true, unknown: 0 },
            },
          }),
        })}
      />,
    );

    const verdict = screen.getByTestId("dossier-coverage-verdict");
    expect(verdict).toHaveTextContent(/not a claim that the subject is fully known/i);
  });

  it("counts unswept lifecycle windows instead of listing them", () => {
    render(<DossierPage {...pageProps({ dossier: dossier() })} />);

    expect(screen.getByTestId("dossier-coverage-verdict")).toHaveTextContent(
      /1625 lifecycle window\(s\) were not swept/i,
    );
    expect(screen.getByTestId("dossier-coverage-verdict")).toHaveTextContent(
      /counted here rather than shown as findings/i,
    );
  });

  it("shows never-asked attributes as never asked", () => {
    render(<DossierPage {...pageProps({ dossier: dossier() })} />);

    const figures = screen.getByTestId("dossier-coverage-figures");
    expect(figures).toHaveTextContent("Never asked");
    expect(figures).toHaveTextContent("82");
  });
});

describe("DossierPage — refusals and gaps", () => {
  it("names the source that refused and why", () => {
    render(
      <DossierPage
        {...pageProps({
          dossier: dossier(),
          refusals: [
            { source: "ipapi_co_full", attribute: "ip", reason: "echo", detail: "ip=example.com" },
          ],
        })}
      />,
    );

    showView(/Sources/);
    expect(screen.getByTestId("dossier-refusals")).toHaveTextContent("ipapi_co_full");
    expect(screen.getByTestId("dossier-refusals")).toHaveTextContent("ip=example.com");
  });

  it("shows every source outcome, including the ones that failed", () => {
    render(
      <DossierPage
        {...pageProps({
          dossier: dossier(),
          reports: [
            {
              source: "rdap_domain",
              attribute: "registrar",
              outcome: "ok",
              status: 200,
              records: 1,
              bytes: 900,
              detail: "",
            },
            {
              source: "ripe_stat",
              attribute: "abuse_contact",
              outcome: "error",
              status: 0,
              records: 0,
              bytes: 0,
              detail: "ReadTimeout",
            },
          ],
        })}
      />,
    );

    showView(/Sources/);
    const table = screen.getByTestId("dossier-source-table");
    expect(table).toHaveTextContent("rdap_domain");
    expect(table).toHaveTextContent("ripe_stat");
    expect(table).toHaveTextContent("ReadTimeout");
  });

  it("shows source names on gaps, not content-addressed ids", () => {
    render(<DossierPage {...pageProps({ dossier: dossier() })} />);

    showView(/Gaps/);
    expect(screen.getByTestId("dossier-gap-table")).toHaveTextContent("ripe_stat");
    expect(screen.getByTestId("dossier-gap-table")).not.toHaveTextContent("SRC-a");
  });
});

describe("DossierContainer", () => {
  it("loads the subject list without running a sweep", async () => {
    (dossierApi.listSubjects as ReturnType<typeof vi.fn>).mockResolvedValue({
      subjects: [{ entity_ref: "REF-1", events: 8, first_seen: null, last_seen: null }],
    });
    (dossierApi.enrich as ReturnType<typeof vi.fn>).mockResolvedValue({} as EnrichResult);

    render(<DossierContainer />);

    expect(await screen.findByTestId("dossier-subjects")).toHaveTextContent("REF-1");
    expect(dossierApi.enrich).not.toHaveBeenCalled();
  });

  it("surfaces a read failure instead of showing a blank dossier", async () => {
    (dossierApi.listSubjects as ReturnType<typeof vi.fn>).mockResolvedValue({ subjects: [] });
    (dossierApi.getDossier as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("no life-stream for REF-9; it has not been swept"),
    );

    render(<DossierContainer />);
    const button = await screen.findByTestId("dossier-subject-field");
    expect(button).toBeInTheDocument();

    // No dossier is displayed when the read failed: nothing is invented to fill the gap.
    expect(screen.queryByTestId("dossier-coverage")).toBeNull();
  });
});
