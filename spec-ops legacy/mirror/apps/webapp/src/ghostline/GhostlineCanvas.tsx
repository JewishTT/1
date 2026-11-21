import { useCallback, useEffect, useState } from "react";

import type { IconName } from "../ui/Icon";
import { Tabs } from "../ui/Tabs";
import { api } from "../lib/api";
import type { GlStatusWire } from "../lib/api";
import { AnalyticsPanel } from "./panels/AnalyticsPanel";
import { DialerPanel } from "./panels/DialerPanel";
import { EngagementPanel } from "./panels/EngagementPanel";
import { PlaybooksPanel } from "./panels/PlaybooksPanel";
import { RuntimePanel } from "./panels/RuntimePanel";
import { SimulatePanel } from "./panels/SimulatePanel";
import { TranscriptsPanel } from "./panels/TranscriptsPanel";
import { VoicesPanel } from "./panels/VoicesPanel";
import type { GlPanel } from "./types";
import "./ghostline.css";

/**
 * GhostlineCanvas — voice-borne social engineering as a department surface (031).
 *
 * Seven tabs, and the ordering is the argument: everything you need *before* a call is
 * above the line, everything that happens *during* one is in the middle, and what it all
 * added up to is at the bottom.
 *
 *   Runtime   the donor, its providers, and the composition (`serve`)
 *   Playbooks what a scenario actually does, stage by stage
 *   Simulate  the donor's own stage machine over a scripted transcript — the reason
 *             this integration is more than a wrapper
 *   Voices    the voice registry (`clone`, plus the premade path a CLI has no shape for)
 *   Dialler   placing a call (`call`), behind the same RoE gate as phishing and emulation
 *   Transcripts what was said, redacted at the point of storage
 *   Analytics the assessment record (`analytics`), served rather than written to a file
 *
 * The gate is visible rather than implied: the Dialler shows the roster, the sign-off id
 * and the capture counter, and a refusal names itself as a refusal. Nothing on this
 * canvas can place a call that the CI/SpecOps department's rules-of-engagement gate
 * would not place, because the gate runs server-side before the donor is reached.
 *
 * THE DECK STRIP above the tabs is not decoration and not a summary widget. It answers
 * the one question an operator has on every panel: *can I run an exercise right now, and
 * if not, what is missing.* Four readouts, live, at the top of the surface — so an
 * operator never has to switch to Runtime to find out that the deployment is not
 * configured. It is fetched here rather than lifted from RuntimePanel because it has to
 * survive every tab switch; a summary that vanishes when you change panel is not a
 * summary.
 *
 * Mirrors `src/ci/CICanvas.tsx`: one canvas, internal panel tabs, a shared vocabulary,
 * and a scope note that travels with every figure on it.
 */

const PANELS: ReadonlyArray<{ value: GlPanel; label: string; icon: IconName }> = [
  { value: "runtime", label: "Runtime", icon: "activity" },
  { value: "playbooks", label: "Playbooks", icon: "list" },
  { value: "simulate", label: "Simulator", icon: "diagram" },
  { value: "voices", label: "Voices", icon: "dot" },
  { value: "dialer", label: "Dialler", icon: "alert" },
  { value: "engagement", label: "Engagement", icon: "view-graph" },
  { value: "transcripts", label: "Transcripts", icon: "view-evidence" },
  { value: "analytics", label: "Analytics", icon: "view-analysis" },
];

export function GhostlineCanvas({ initialPanel = "runtime" }: { initialPanel?: GlPanel }) {
  const [panel, setPanel] = useState<GlPanel>(initialPanel);
  const [status, setStatus] = useState<GlStatusWire | null>(null);

  const load = useCallback(async () => {
    try {
      setStatus(await api.ghostlineStatus());
    } catch {
      // The deck strip degrades to its last known state rather than to an error
      // banner. It is a summary of a service the operator can also read properly on
      // the Runtime tab; failing loudly here would put an error in front of an
      // operator who is trying to read something else.
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Poll only while the runtime is live: a tunnel can die, and a strip that says
  // "running" over a dead WSS URL is worse than no strip.
  const running = status?.runtime.state === "running";
  useEffect(() => {
    if (!running) return;
    const id = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(id);
  }, [running, load]);

  const engine = status?.donor.stage_engine.ready.length ?? null;
  const edges = status ? status.donor.live_edges.ready.length : null;
  const edgesTotal = status
    ? status.donor.live_edges.ready.length + status.donor.live_edges.absent.length
    : null;
  const blockers = status?.blockers.length ?? null;

  return (
    <div className="ui-cicanvas ui-holo-field" data-testid="gl-canvas" data-panel={panel}>
      <div className="ui-ci-panel-head ui-gl-subhead">
        <span className="ui-pane-title">GhostLine</span>
        <Tabs
          items={PANELS}
          value={panel}
          onValueChange={(value) => setPanel(value as GlPanel)}
          label="GhostLine panels"
          orientation="bar"
        />
        <span className="ui-rail-hint">RoE-gated · credentials never stored</span>
      </div>

      {/* The deck strip: can I run an exercise right now, and if not, what is missing. */}
      <section className="ui-gl-deck ui-holo ui-holo-edge ui-holo-bracket" data-testid="gl-deck">
        <Readout
          label="runtime"
          value={status?.runtime.state ?? "—"}
          tone={
            status?.runtime.state === "running"
              ? "live"
              : status?.runtime.state === "blocked"
                ? "warn"
                : "idle"
          }
          caption={
            blockers
              ? `${blockers} prerequisite${blockers === 1 ? "" : "s"} outstanding`
              : "reading status"
          }
          testId="gl-deck-runtime"
        />
        <Readout
          label="donor"
          value={status?.donor.present ? (status.donor.license ?? "—") : "absent"}
          tone={status?.donor.present ? "live" : "fail"}
          caption={status?.donor.present ? `${status.donor.donor_id} · vendored` : "not vendored"}
          testId="gl-deck-donor"
        />
        <Readout
          label="stage engine"
          value={engine === null ? "—" : `${engine}`}
          tone={engine ? "live" : "fail"}
          caption="donor modules running in-process"
          testId="gl-deck-engine"
        />
        <Readout
          label="live edges"
          value={edges === null || edgesTotal === null ? "—" : `${edges}/${edgesTotal}`}
          tone={edges ? "info" : "warn"}
          caption="need a package and a credential"
          testId="gl-deck-edges"
        />
        <Readout
          label="scenarios"
          value={status ? `${status.counts.playbooks_valid}` : "—"}
          tone={status && status.counts.playbooks_valid > 0 ? "info" : "warn"}
          caption={
            status && status.counts.playbooks > status.counts.playbooks_valid
              ? `${status.counts.playbooks - status.counts.playbooks_valid} rejected by the donor`
              : "loaded from the donor tree"
          }
          testId="gl-deck-scenarios"
        />
        <Readout
          label="recorded calls"
          value={status ? `${status.counts.calls}` : "—"}
          tone={status && status.counts.calls > 0 ? "idle" : "idle"}
          caption={`${status?.counts.voices ?? 0} voice(s) registered`}
          testId="gl-deck-calls"
        />
      </section>

      <div className="ui-cicanvas-body">
        {panel === "runtime" ? <RuntimePanel onNavigate={setPanel} /> : null}
        {panel === "playbooks" ? <PlaybooksPanel onNavigate={setPanel} /> : null}
        {panel === "simulate" ? <SimulatePanel /> : null}
        {panel === "voices" ? <VoicesPanel /> : null}
        {panel === "dialer" ? <DialerPanel onNavigate={setPanel} /> : null}
        {panel === "engagement" ? <EngagementPanel /> : null}
        {panel === "transcripts" ? <TranscriptsPanel /> : null}
        {panel === "analytics" ? <AnalyticsPanel /> : null}
      </div>
    </div>
  );
}

function Readout({
  label,
  value,
  caption,
  tone,
  testId,
}: {
  label: string;
  value: string;
  caption: string;
  tone: "live" | "warn" | "fail" | "info" | "idle";
  testId: string;
}) {
  return (
    <div className="ui-gl-readout" data-tone={tone} data-testid={testId}>
      <span className="ui-gl-readout-label">{label}</span>
      <span className="ui-gl-readout-value">{value}</span>
      <span className="ui-gl-readout-caption">{caption}</span>
    </div>
  );
}
