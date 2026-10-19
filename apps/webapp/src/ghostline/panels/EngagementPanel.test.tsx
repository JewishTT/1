import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { GlBoardWire, GlTaxonomyWire } from "../../lib/api";
import { ApiError } from "../../lib/http";
import { EngagementPanel } from "./EngagementPanel";
import { stageKeyFor, subjectDisposition } from "../engagement";

/**
 * The engagement board (Feature 032).
 *
 * The assertions here are about the two ways this board could be quietly wrong:
 *
 *   1. **Training leaking into the funnel.** If a completed training counted as
 *      engagement, the board would render a plausible-looking funnel that measures two
 *      unrelated things. The test asserts on the rendered DOM — the training block is
 *      outside the funnel element, and its heading is its own.
 *   2. **Anonymisation looking like data loss.** After stripping identity the subject
 *      row must still exist and still be linked, because the pseudonym is what keeps the
 *      history meaningful. A panel that hid the row would look like the retention action
 *      destroyed the evidence, which is the opposite of what it does.
 */

vi.mock("../../lib/api", () => ({
  api: {
    engagementBoard: vi.fn(),
    engagementTaxonomy: vi.fn(),
    anonymizeEngagementCampaign: vi.fn(),
  },
}));

const { api } = await import("../../lib/api");
const mock = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

const TAXONOMY: GlTaxonomyWire = {
  events: [
    {
      kind: "campaign_recipient_submitted_data",
      track: "phishing",
      stage: 6,
      display: "Reached the ask",
      credential_bearing: true,
    },
    {
      kind: "campaign_recipient_training_completed",
      track: "training",
      stage: 0,
      display: "Training completed",
      credential_bearing: false,
    },
  ],
  stages: [
    { key: "dispatched", stage: 1, intent: "a message went out" },
    { key: "engaged", stage: 2, intent: "opened or answered" },
    { key: "conceded", stage: 6, intent: "gave something up" },
    { key: "resisted", stage: 7, intent: "reported or refused" },
  ],
  dont_heritage: [
    "their palette (pc-pink #ff00ff) — the exact set styles/tokens/color.css forbids",
    "their submitted-data storage — their model persists what a subject typed",
  ],
  log_path: "logs/engagement",
};

const BOARD: GlBoardWire = {
  campaigns: [
    {
      campaign_id: "q3",
      channels: ["email"],
      reached: { dispatched: 3, engaged: 2, conceded: 1, resisted: 1 },
      subject_count: 3,
      event_count: 7,
      event_counts: {},
      training: { assigned: 2, completed: 1 },
      resisted: 1,
    },
    {
      campaign_id: "v1",
      channels: ["voice"],
      reached: { dispatched: 1, engaged: 1, conceded: 1, resisted: 0 },
      subject_count: 1,
      event_count: 2,
      event_counts: {},
      training: { assigned: 0, completed: 0 },
      resisted: 0,
    },
  ],
  subjects: [
    {
      subject_ref: "a@corp",
      pseudonym: "anon-abc",
      deepest_stage: 6,
      campaigns: ["q3", "v1"],
      channels: ["email", "voice"],
      events: 9,
      repeat_engaged: 2,
      conceded_campaigns: ["q3", "v1"],
      resisted_campaigns: [],
      trainings_completed: 1,
    },
    {
      subject_ref: null,
      pseudonym: "anon-def",
      deepest_stage: 7,
      campaigns: ["q3"],
      channels: ["email"],
      events: 2,
      repeat_engaged: 1,
      conceded_campaigns: [],
      resisted_campaigns: ["q3"],
      trainings_completed: 0,
    },
  ],
  outcome_split: { conceded: 1, resisted: 1 },
  stages: TAXONOMY.stages,
  missing: [],
};

beforeEach(() => {
  vi.clearAllMocks();
  mock.engagementBoard.mockResolvedValue({
    served: ["/specops/engagement"],
    missing: [],
    scope: "tenant-wide",
    projection: BOARD,
  });
  mock.engagementTaxonomy.mockResolvedValue({
    served: ["/specops/engagement"],
    missing: [],
    scope: "tenant-wide",
    ...TAXONOMY,
  });
});

describe("EngagementPanel", () => {
  it("shows one funnel per campaign, tagged with its channels", async () => {
    render(<EngagementPanel />);
    await waitFor(() => expect(screen.getByTestId("gl-funnel-q3")).toBeInTheDocument());
    expect(screen.getByTestId("gl-funnel-v1")).toBeInTheDocument();
    expect(screen.getByTestId("gl-channel-email")).toBeInTheDocument();
    expect(screen.getByTestId("gl-channel-voice")).toBeInTheDocument();
  });

  it("counts the subjects who engaged on both channels", async () => {
    render(<EngagementPanel />);
    // The number the two channels could never produce on their own.
    await waitFor(() =>
      expect(screen.getByTestId("gl-engagement-multichannel")).toHaveTextContent("1"),
    );
  });

  it("keeps training out of the funnel and under its own heading", async () => {
    render(<EngagementPanel />);
    await waitFor(() => expect(screen.getByTestId("gl-engagement-training")).toBeInTheDocument());

    const training = screen.getByTestId("gl-engagement-training");
    // Not a descendant of either funnel…
    expect(screen.getByTestId("gl-funnel-q3")).not.toContainElement(training);
    expect(screen.getByTestId("gl-funnel-v1")).not.toContainElement(training);
    // …and it says why, in its own words.
    expect(training).toHaveTextContent(/never added into the funnel/i);
    expect(training).toHaveTextContent("2"); // assigned
    expect(training).toHaveTextContent("1"); // completed
  });

  it("draws the ladder with an empty rung marked rather than omitted", async () => {
    render(<EngagementPanel />);
    await waitFor(() => expect(screen.getByTestId("gl-funnel-bars-q3")).toBeInTheDocument());
    // `landed` is absent from this campaign's `reached`; it must render at zero rather
    // than vanish, or the ladder would imply a stage that does not exist.
    const rows = screen.getByTestId("gl-funnel-bars-q3").querySelectorAll("li");
    expect(rows).toHaveLength(4);
    expect(screen.getByTestId("gl-funnel-bars-v1")).toBeInTheDocument();
  });

  it("shows a subject's depth as a word, not a bare integer", async () => {
    render(<EngagementPanel />);
    await waitFor(() => expect(screen.getByTestId("gl-subject-a@corp")).toBeInTheDocument());
    expect(screen.getByTestId("gl-subject-a@corp")).toHaveTextContent("depth conceded");
    expect(screen.getByTestId("gl-subject-a@corp")).toHaveTextContent("q3, v1");
  });

  it("shows an anonymised subject by pseudonym and says it is anonymised", async () => {
    render(<EngagementPanel />);
    const row = await screen.findByTestId("gl-subject-anon-def");
    expect(row).toHaveTextContent("anon-def");
    expect(row).toHaveAttribute("data-anonymized", "true");
    expect(row).toHaveTextContent("anonymised");
  });

  it("reports that anonymisation kept the counts", async () => {
    mock.anonymizeEngagementCampaign.mockResolvedValue({
      served: ["/specops/engagement"],
      missing: [],
      scope: "tenant-wide",
      campaign_id: "q3",
      anonymized: 7,
    });
    render(<EngagementPanel />);
    fireEvent.click(await screen.findByTestId("gl-anonymize-q3"));
    await waitFor(() =>
      expect(screen.getByTestId("gl-engagement-note")).toHaveTextContent(
        /stripped identity from 7 event\(s\)/i,
      ),
    );
    expect(screen.getByTestId("gl-engagement-note")).toHaveTextContent(/counts are unchanged/i);
  });

  it("states what was refused from the donor", async () => {
    render(<EngagementPanel />);
    const provenance = await screen.findByTestId("gl-engagement-provenance");
    expect(provenance).toHaveTextContent("pc-pink");
    expect(provenance).toHaveTextContent("submitted-data");
  });

  it("says which channels feed the log instead of rendering an empty board", async () => {
    mock.engagementBoard.mockResolvedValue({
      served: ["/specops/engagement"],
      missing: [],
      scope: "tenant-wide",
      projection: { ...BOARD, campaigns: [], subjects: [], outcome_split: {} },
    });
    render(<EngagementPanel />);
    const empty = await screen.findByTestId("gl-engagement-empty");
    expect(empty).toHaveTextContent(/Phishing \/ SAT/);
    expect(empty).toHaveTextContent(/GhostLine/);
  });

  it("names the absence when no channel has reported", async () => {
    mock.engagementBoard.mockResolvedValue({
      served: ["/specops/engagement"],
      missing: [],
      scope: "tenant-wide",
      projection: { ...BOARD, campaigns: [], subjects: [], missing: ["GET /x (no events)"] },
    });
    render(<EngagementPanel />);
    expect(await screen.findByTestId("gl-engagement-missing")).toHaveTextContent("no events");
  });
});

describe("stageKeyFor", () => {
  it("names every rung on the ladder", () => {
    expect(stageKeyFor(1)).toBe("dispatched");
    expect(stageKeyFor(6)).toBe("conceded");
    expect(stageKeyFor(7)).toBe("resisted");
  });

  it("never returns an empty label for an unknown depth", () => {
    // A blank label on a bar is a missing answer, and this is the one place a reader is
    // looking at "how far did they get".
    expect(stageKeyFor(0)).not.toBe("");
    expect(stageKeyFor(99)).not.toBe("");
    expect(stageKeyFor(-1)).not.toBe("");
  });
});

describe("subjectDisposition", () => {
  it("reads the majority posture, not the deepest rung", () => {
    expect(
      subjectDisposition({ conceded_campaigns: ["a", "b"], resisted_campaigns: ["c"] }).label,
    ).toBe("conceded");
    expect(
      subjectDisposition({ conceded_campaigns: ["a"], resisted_campaigns: ["b", "c"] }).label,
    ).toBe("resisted");
  });

  it("calls a subject with no signal Unknown rather than healthy", () => {
    expect(subjectDisposition({ conceded_campaigns: [], resisted_campaigns: [] }).status).toBe(
      "Unknown",
    );
  });
});

describe("error handling", () => {
  it("renders an unreadable board as empty rather than throwing", async () => {
    mock.engagementBoard.mockRejectedValue(new ApiError(503, "unavailable", "down"));
    render(<EngagementPanel />);
    expect(await screen.findByTestId("gl-engagement-empty")).toBeInTheDocument();
  });
});
