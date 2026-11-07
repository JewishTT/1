import { useState } from "react";

import { api, type LabOverviewWire } from "../../lib/api";
import { Input } from "../../ui/Input";
import { shortId } from "../model";
import { useLabAction } from "../useLabAction";
import { LabActionButton, LabChip, LabNote, LabPanelShell } from "./labParts";

export function CatalogPanel({
  data,
  refresh,
}: {
  data: LabOverviewWire;
  refresh: () => Promise<void>;
}) {
  const { busy, note, run } = useLabAction(refresh);
  const [name, setName] = useState("Synthetic lure");
  const [stages, setStages] = useState("landing, training");
  const [asset, setAsset] = useState("lab://specops-lab.local/lure/landing.html");
  const [host, setHost] = useState("specops-lab.local");

  const createTemplate = () =>
    run(
      () =>
        api.labCreateTemplate({
          name,
          stages: stages.split(",").map((s) => s.trim()).filter(Boolean),
          assets: asset.trim() ? [asset.trim()] : [],
        }),
      "Template imported into the lab catalog with synthetic provenance.",
    );

  const createSender = () =>
    run(
      () =>
        api.labCreateSender({
          name: "Lab SMTP",
          host,
          tls: true,
          dns_ready: true,
          credential_ref: "vault://lab/smtp",
        }),
      "Sender registered. Readiness is derived from TLS, DNS and the credential ref.",
    );

  return (
    <LabPanelShell
      title="Template & sender catalog"
      status={<LabChip label={`${data.templates.length} templates · ${data.senders.length} senders`} />}
      testId="lab-catalog-panel"
    >
      <div className="lab-grid">
        <div className="ui-ci-col">
          <span className="ui-pane-title">Templates</span>
          <Input label="Template name" value={name} onChange={(e) => setName(e.target.value)} />
          <Input label="Stages (comma separated)" value={stages} onChange={(e) => setStages(e.target.value)} />
          <Input
            label="Lab asset (lab:// only)"
            value={asset}
            onChange={(e) => setAsset(e.target.value)}
            hint="An external URL is refused by the boundary, not fetched."
            data-testid="lab-template-asset"
          />
          <LabActionButton onClick={() => void createTemplate()} disabled={busy} testId="lab-create-template">
            Import template
          </LabActionButton>
        </div>

        <div className="ui-ci-col">
          <span className="ui-pane-title">Senders</span>
          <Input label="Sender host" value={host} onChange={(e) => setHost(e.target.value)} />
          <LabActionButton onClick={() => void createSender()} disabled={busy} testId="lab-create-sender">
            Register sender
          </LabActionButton>
        </div>
      </div>

      <ul className="ui-ci-list" data-testid="lab-templates">
        {data.templates.map((template) => (
          <li key={template.template_id} className="ui-ci-list-row">
            <span className="ui-ci-list-main">
              <strong>{template.name}</strong>
              <span className="ui-id">
                {shortId(template.template_id)} · {template.stages.join(" → ")} · {template.provenance}
              </span>
              <span className="ui-id">{template.assets.join(", ") || "no assets"}</span>
            </span>
            <LabChip label={template.authorized ? "authorized" : "refused"} tone={template.authorized ? "accent" : "danger"} />
          </li>
        ))}
      </ul>

      <ul className="ui-ci-list" data-testid="lab-senders">
        {data.senders.map((sender) => (
          <li key={sender.sender_id} className="ui-ci-list-row">
            <span className="ui-ci-list-main">
              <strong>{sender.name}</strong>
              <span className="ui-id">
                {sender.host} · TLS {sender.tls ? "yes" : "no"} · DNS {sender.dns_ready ? "ready" : "unverified"}
              </span>
              {sender.missing.length > 0 ? <span className="ui-id">{sender.missing.join("; ")}</span> : null}
            </span>
            <LabChip label={sender.ready ? "ready" : "setup required"} tone={sender.ready ? "accent" : "gold"} />
          </li>
        ))}
      </ul>

      <LabNote note={note} testId="lab-catalog-note" />
    </LabPanelShell>
  );
}
