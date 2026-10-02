import { useState } from "react";

import { Tabs } from "../ui/Tabs";
import { OperationsWorkspace } from "./OperationsWorkspace";
import { QuarantineWorkspace } from "./QuarantineWorkspace";
import { SourceCatalog } from "./SourceCatalog";

/**
 * OpsCanvas — the Ops workspace view (T130, FR-109, ui-upgrade §8).
 *
 * WHAT THIS IS. The connector. `src/ops/` shipped three finished, separately
 * tested surfaces — `OperationsWorkspace`, `QuarantineWorkspace` and
 * `SourceCatalog` — and none of them was reachable: `/ops` rendered the
 * pre-UI-2.0 `OpsDashboardPage`, and no workspace view mounted any of them. The
 * work was already done and simply unconnected.
 *
 * ONE VIEW, THREE PANELS, AND WHY NOT THREE VIEWS.
 *
 * §48 asks for the five acquisition runtimes to appear "as ITEMS OF ONE
 * ACQUISITION FABRIC", and the three surfaces answer three questions about that
 * same fabric: is it healthy (Operations), what did it refuse (Quarantine), what
 * is registered against it (Catalogue). They share the tenant, the query
 * client and the vocabulary, and splitting them across the workspace switcher
 * would put three tabs on the same subject where one tab with three panels says
 * "one subject". So the switcher gets ONE Ops entry and the view carries the
 * three panels internally.
 *
 * WHERE THE "TENANT-WIDE, NOT THIS CASE" TRUTH LIVES.
 *
 * `src/ops/index.ts` originally argued that this module must NOT be a workspace
 * view, on the grounds that putting a tenant-wide operator surface behind a tab
 * inside an investigation makes an operator read a tenant failure rate as a
 * statement about the case in hand. ui-upgrade §1 settles it the other way —
 * Ops is a view *within* an investigation, not a peer product — so the concern
 * is answered where it actually bites: the label. `OperationsWorkspace` renders
 * "tenant-wide pipeline state · not scoped to one investigation" as its scope
 * line, and this canvas repeats it on the tab bar, so the truth is on screen
 * wherever the numbers are.
 *
 * §69, NO DEAD ENDS: the Operations board's "Check quarantine" affordance was
 * previously unreachable because no host ever passed `onOpenQuarantine`. It is
 * wired here, so the button exists only where the panel behind it does.
 */
export type OpsPanel = "operations" | "quarantine" | "sources";

const PANELS = [
  { value: "operations" as const, label: "Operations", icon: "view-ops" as const },
  { value: "quarantine" as const, label: "Quarantine", icon: "alert" as const },
  { value: "sources" as const, label: "Source fabric", icon: "view-acquisition" as const },
];

export function OpsCanvas({ initialPanel = "operations" }: { initialPanel?: OpsPanel }) {
  const [panel, setPanel] = useState<OpsPanel>(initialPanel);

  return (
    <div className="ui-opscanvas" data-testid="ops-canvas" data-panel={panel}>
      <div className="ui-opscanvas-head">
        <Tabs
          items={PANELS}
          value={panel}
          onValueChange={(value) => setPanel(value as OpsPanel)}
          label="Ops panels"
          orientation="bar"
        />
        <span className="ui-rail-hint">tenant-wide · not scoped to one investigation</span>
      </div>

      {panel === "operations" ? (
        <OperationsWorkspace onOpenQuarantine={() => setPanel("quarantine")} />
      ) : null}
      {panel === "quarantine" ? <QuarantineWorkspace /> : null}
      {panel === "sources" ? <SourceCatalog /> : null}
    </div>
  );
}