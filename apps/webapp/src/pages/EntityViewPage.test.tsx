import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EntityViewPage, EntityView } from "./EntityViewPage";

const ENTITY: EntityView = {
  entity_id: "ENT-2001",
  canonical_identity: { account: "Yard" },
  current_state: { version: 2 },
  historical_versions: [{ version: 1 }, { version: 2 }],
  aliases: ["Yard", "yard-account"],
  relationships: [{ type: "candidate_of", target: "ENT-2002" }],
  supporting_assertions: ["ASR-9001"],
  evidence: [{ evidence_id: "E-1", observation_id: "OBS-1001", immutable: true }],
  timeline: [
    { observation_id: "OBS-1001", uri: "http://fixtures.local/report.html", immutable: true },
  ],
  structural_signals: [{ signal: "tda_loop", feature_id: "FEAT-42", persistence: 2.3 }],
};

describe("EntityViewPage", () => {
  it("renders identity, aliases, evidence, timeline and signals", () => {
    render(<EntityViewPage entity={ENTITY} />);
    expect(screen.getByTestId("entity-view")).toHaveAttribute("data-entity-id", "ENT-2001");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Yard");
    expect(screen.getByTestId("entity-aliases")).toHaveTextContent("yard-account");
    expect(screen.getByTestId("entity-timeline")).toHaveTextContent("OBS-1001");
    expect(screen.getByTestId("entity-signals")).toHaveTextContent("tda_loop");
  });

  it("confirms evidence integrity against I-1", () => {
    render(<EntityViewPage entity={ENTITY} />);
    expect(screen.getByTestId("evidence-integrity")).toHaveTextContent("immutable observations");
  });

  it("flags broken evidence", () => {
    render(
      <EntityViewPage
        entity={{
          ...ENTITY,
          evidence: [{ evidence_id: "E-1", observation_id: "OBS-1", immutable: false }],
        }}
      />,
    );
    expect(screen.getByTestId("evidence-integrity")).toHaveTextContent("broken");
  });
});
