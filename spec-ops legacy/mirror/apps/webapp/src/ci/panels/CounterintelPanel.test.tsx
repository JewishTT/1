import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../lib/api", () => ({
  api: {
    getSubject: vi.fn(),
  },
}));

import { api } from "../../lib/api";
import type { CiEnvelope, CiSubjectWire } from "../../lib/api";
import { CounterintelPanel } from "./CounterintelPanel";

const demoEnvelope: CiEnvelope<{ subject: CiSubjectWire }> = {
  served: ["/api/v1/specops/counterintel/subjects/{subject_id}"],
  missing: [
    "CognitiveAttack / DIMA-OntoToolkit / io-coordinated-replies / IO-detecting operators are not connected; the current subject registry is a seeded demo fixture.",
  ],
  scope: "fixture-only",
  subject: {
    subject_id: "subj-demo-1",
    kind: "core:Person",
    display: "Demo subject (seeded)",
    invariants: [
      {
        kind: "belief-state",
        value: "fixture hypothesis",
        confidence: 0.62,
        evidence_refs: ["obs-demo-1"],
      },
      {
        kind: "coordination-signature",
        value: "unsupported example",
        confidence: null,
        evidence_refs: [],
      },
    ],
    relations: [],
  },
};

describe("CounterintelPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("distinguishes a served fixture endpoint from unconnected cognitive operators", async () => {
    vi.mocked(api.getSubject).mockResolvedValue(demoEnvelope);
    render(<CounterintelPanel />);

    fireEvent.change(screen.getByRole("textbox", { name: "Subject id" }), {
      target: { value: "subj-demo-1" },
    });
    fireEvent.click(screen.getByTestId("ci-subject-load"));

    expect(await screen.findByTestId("ci-subject")).toBeInTheDocument();
    expect(screen.getByText("Demo subject (seeded)")).toBeInTheDocument();
    expect(screen.getByText("shared demo fixture · not tenant/investigation data")).toBeInTheDocument();
    expect(screen.queryByText(/GET \/specops\/counterintel\/subjects/)).not.toBeInTheDocument();
    expect(screen.getByTestId("ci-counterintel-missing")).toHaveTextContent("CognitiveAttack");
    expect(screen.getByTestId("ci-invariant-support-coordination-signature")).toHaveTextContent("unsupported");
  });
});
