import { useState } from "react";

import type { IconName } from "../ui/Icon";
import { Tabs } from "../ui/Tabs";
import { useLabOverview } from "./useLabOverview";
import { LabAbsence, LabChip, LabPanelShell } from "./panels/labParts";
import { LabControlPanel } from "./panels/LabControlPanel";
import { CatalogPanel } from "./panels/CatalogPanel";
import { CampaignsPanel } from "./panels/CampaignsPanel";
import { AitmPanel } from "./panels/AitmPanel";
import { OperationsLabPanel } from "./panels/OperationsLabPanel";
import { EngagementLabPanel } from "./panels/EngagementLabPanel";
import { ReportsPanel } from "./panels/ReportsPanel";
import { AuditPanel } from "./panels/AuditPanel";
import "./lab.css";

export type LabTab =
  | "control"
  | "catalog"
  | "campaigns"
  | "aitm"
  | "operations"
  | "engagement"
  | "reports"
  | "audit";

const PANELS: ReadonlyArray<{ value: LabTab; label: string; icon: IconName }> = [
  { value: "control", label: "Lab control", icon: "view-ops" },
  { value: "catalog", label: "Catalog", icon: "view-objects" },
  { value: "campaigns", label: "Campaigns", icon: "alert" },
  { value: "aitm", label: "AiTM sessions", icon: "diagram" },
  { value: "operations", label: "Operations", icon: "activity" },
  { value: "engagement", label: "Engagement", icon: "view-analysis" },
  { value: "reports", label: "Reports", icon: "view-evidence" },
  { value: "audit", label: "Audit", icon: "list" },
];

/**
 * The Red-Team Lab (Feature 036).
 *
 * A separate canvas from `CICanvas` on purpose: it runs full red-team mode and every
 * action is bound by a confirmed RoE. The banner is persistent so the scope travels
 * with every panel.
 */
export function LabCanvas({ initialTab = "control" }: { initialTab?: LabTab }) {
  const { data, loading, error, refresh } = useLabOverview();
  const [tab, setTab] = useState<LabTab>(initialTab);

  return (
    <div className="ui-cicanvas ui-holo-field lab-canvas" data-testid="lab-canvas" data-panel={tab}>
      <div className="ui-cicanvas-head">
        <Tabs
          items={PANELS}
          value={tab}
          onValueChange={(value) => setTab(value as LabTab)}
          label="Red-Team Lab panels"
          orientation="bar"
        />
        <span className="ui-rail-hint lab-banner" data-testid="lab-banner">
          full red-team · RoE-gated · Phishing Club
        </span>
      </div>

      <div className="ui-cicanvas-body">
        {loading && !data ? (
          <LabPanelShell title="Loading lab" status={<LabChip label="loading" />} testId="lab-loading">
            <p className="panel-note">Reading the lab boundary, readiness and audit chain…</p>
          </LabPanelShell>
        ) : null}

        {error ? (
          <LabPanelShell
            title="Lab unavailable"
            status={<LabChip label="not served" tone="danger" />}
            testId="lab-error"
          >
            <LabAbsence missing={[error]} testId="lab-error-missing" />
            <button type="button" className="ui-btn" onClick={() => void refresh()} data-testid="lab-retry">
              Retry overview
            </button>
          </LabPanelShell>
        ) : null}

        {data ? (
          <>
            {tab === "control" ? <LabControlPanel data={data} refresh={refresh} /> : null}
            {tab === "catalog" ? <CatalogPanel data={data} refresh={refresh} /> : null}
            {tab === "campaigns" ? <CampaignsPanel data={data} refresh={refresh} /> : null}
            {tab === "aitm" ? <AitmPanel data={data} refresh={refresh} /> : null}
            {tab === "operations" ? <OperationsLabPanel data={data} refresh={refresh} /> : null}
            {tab === "engagement" ? <EngagementLabPanel data={data} /> : null}
            {tab === "reports" ? <ReportsPanel data={data} refresh={refresh} /> : null}
            {tab === "audit" ? <AuditPanel data={data} /> : null}
          </>
        ) : null}
      </div>
    </div>
  );
}
