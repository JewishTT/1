import { useState } from "react";

import type { IconName } from "../ui/Icon";
import { Tabs } from "../ui/Tabs";
import { CounterintelPanel } from "./panels/CounterintelPanel";
import { EmulationPanel } from "./panels/EmulationPanel";
import { ForensicsPanel } from "./panels/ForensicsPanel";
import { OperationsPanel } from "./panels/OperationsPanel";
import { PhishingPanel } from "./panels/PhishingPanel";
import { SocialPanel } from "./panels/SocialPanel";
import { GhostlineCanvas } from "../ghostline/GhostlineCanvas";
import type { CiPanel } from "./types";
import "./ci.css";

/**
 * CICanvas — the Counterintelligence & Special Operations department (027, T009).
 *
 * Mirrors `src/ops/OpsCanvas.tsx` exactly: ONE canvas, internal panel tabs, a
 * shared tenant/query client/vocabulary, and a scope note that travels with the
 * numbers. The department is a DIFFERENT subject from pipeline health — kill-chain
 * emulation, phishing/SAT, APT forensics, counterintelligence, social-reaction —
 * which is why it is its own canvas and not more tiles on the Ops board (§70).
 *
 * WHERE THE SCOPE TRUTH LIVES: the panel that owns a tenant-wide figure states it
 * on its own surface; this bar repeats "not scoped to one investigation" so the
 * honesty is wherever the operator is looking. §69, no dead ends: a panel whose
 * backing donor/lab is down renders a named absence from inside itself, so the tab
 * exists only where the surface behind it does.
 */

const PANELS: ReadonlyArray<{ value: CiPanel; label: string; icon: IconName }> = [
  { value: "operations", label: "Operations", icon: "activity" },
  { value: "emulation", label: "Kill-chain", icon: "diagram" },
  { value: "phishing", label: "Phishing / SAT", icon: "alert" },
  { value: "forensics", label: "APT forensics", icon: "view-evidence" },
  { value: "detection", label: "Detection", icon: "view-findings" },
  { value: "counterintel", label: "Counterintel", icon: "view-objects" },
  { value: "social", label: "Social reaction", icon: "view-graph" },
  // GhostLine (031): voice-borne social engineering. Last on the bar because it is
  // the one panel whose output is a call placed to a person, and an operator should
  // have read the phishing and detection panels before reaching it.
  { value: "ghostline", label: "GhostLine", icon: "dot" },
];

export function CICanvas({ initialPanel = "operations" }: { initialPanel?: CiPanel }) {
  const [panel, setPanel] = useState<CiPanel>(initialPanel);

  return (
    <div className="ui-cicanvas ui-holo-field" data-testid="ci-canvas" data-panel={panel}>
      <div className="ui-cicanvas-head">
        <Tabs
          items={PANELS}
          value={panel}
          onValueChange={(value) => setPanel(value as CiPanel)}
          label="CI/SpecOps panels"
          orientation="bar"
        />
        <span className="ui-rail-hint">
          lab-isolated · RoE-gated · not scoped to one investigation
        </span>
      </div>

      <div className="ui-cicanvas-body">
        {panel === "operations" ? <OperationsPanel /> : null}
        {panel === "emulation" ? <EmulationPanel /> : null}
        {panel === "phishing" ? <PhishingPanel /> : null}
        {panel === "forensics" ? <ForensicsPanel /> : null}
        {panel === "detection" ? <DetectionPlaceholder /> : null}
        {panel === "counterintel" ? <CounterintelPanel /> : null}
        {panel === "social" ? <SocialPanel /> : null}
        {panel === "ghostline" ? <GhostlineCanvas /> : null}
      </div>
    </div>
  );
}

/**
 * Detection (US7, P3) is the last story; until its router lands it states the gap
 * honestly (§95) rather than rendering a fabricated board. Named, not blank.
 */
function DetectionPlaceholder() {
  return (
    <section className="ui-ci-panel" data-testid="ci-detection-panel">
      <header className="ui-ci-panel-head">
        <span className="ui-pane-title">Detection coverage &amp; evidence-to-detection</span>
      </header>
      <p className="panel-note">
        Not served yet — the detection-chain endpoint (
        <code>GET /specops/findings/{"{id}"}/detection-chain</code>) has not landed. It will trace
        finding → evidence → behavior → ATT&CK technique → required telemetry → candidate rules.
        This panel is intentionally empty rather than showing a fabricated coverage number (§90,
        §99).
      </p>
    </section>
  );
}
