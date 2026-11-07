import { useState } from "react";

import { api, type LabArtifactKind, type LabOverviewWire } from "../../lib/api";
import { Input } from "../../ui/Input";
import { sessionTone, shortId } from "../model";
import { useLabAction } from "../useLabAction";
import { LabActionButton, LabChip, LabNote, LabPanelShell } from "./labParts";

export function AitmPanel({
  data,
  refresh,
}: {
  data: LabOverviewWire;
  refresh: () => Promise<void>;
}) {
  const { busy, note, run } = useLabAction(refresh);
  const [mode, setMode] = useState<"reverse_proxy" | "remote_browser">("reverse_proxy");
  const [target, setTarget] = useState("specops-lab.local");
  const [roeId, setRoeId] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [kind, setKind] = useState<LabArtifactKind>("token");
  const [secret, setSecret] = useState("synthetic-token");

  const start = () =>
    run(
      () => api.labStartSession({ mode, target_host: target, roe_id: roeId }),
      "Session started inside the lab boundary. Capture is now available.",
    );

  const capture = (id: string) =>
    run(
      () => api.labCapture(id, { kind, secret, label: "lab session" }),
      "Artifact encrypted and stored. Only the redacted preview is returned.",
    );

  const stop = (id: string) =>
    run(() => api.labStopSession(id), "Session stopped. Captured artifacts remain under retention.");

  return (
    <LabPanelShell
      title="AiTM sessions & captured artifacts"
      status={
        <LabChip
          label="full red-team mode"
          tone="accent"
          testId="lab-full-tier"
        />
      }
      testId="lab-aitm-panel"
    >
      <div className="lab-grid">
        <div className="ui-ci-col">
          <span className="ui-pane-title">Start session</span>
          <label className="ui-field-label" htmlFor="lab-aitm-mode">
            Mode
          </label>
          <select
            id="lab-aitm-mode"
            className="ui-input"
            value={mode}
            onChange={(e) => setMode(e.target.value as typeof mode)}
            data-testid="lab-aitm-mode"
          >
            <option value="reverse_proxy">reverse_proxy</option>
            <option value="remote_browser">remote_browser</option>
          </select>
          <Input label="Target host (RoE-scoped)" value={target} onChange={(e) => setTarget(e.target.value)} />
          <Input
            label="RoE id"
            value={roeId}
            onChange={(e) => setRoeId(e.target.value)}
            placeholder="record a sign-off in the Campaigns panel"
            data-testid="lab-aitm-roe"
          />
          <LabActionButton onClick={() => void start()} disabled={busy} testId="lab-start-session">
            Start RoE-bound session
          </LabActionButton>
        </div>

        <div className="ui-ci-col">
          <span className="ui-pane-title">Credential / session capture</span>
          <label className="ui-field-label" htmlFor="lab-artifact-kind">
            Artifact kind
          </label>
          <select
            id="lab-artifact-kind"
            className="ui-input"
            value={kind}
            onChange={(e) => setKind(e.target.value as LabArtifactKind)}
            data-testid="lab-artifact-kind"
          >
            <option value="token">token</option>
            <option value="cookie">cookie</option>
            <option value="credential">credential</option>
            <option value="header">header</option>
          </select>
          <Input label="Captured value" value={secret} onChange={(e) => setSecret(e.target.value)} />
          <span className="ui-id">
            The value is encrypted before storage; it never appears in a response, audit row or report.
          </span>
          <LabActionButton
            onClick={() => void capture(sessionId || data.sessions[0]?.session_id || "")}
            disabled={busy || !(sessionId || data.sessions[0]?.session_id)}
            testId="lab-capture"
          >
            Capture into selected session
          </LabActionButton>
        </div>
      </div>

      <div className="ui-ci-col" data-testid="lab-sessions">
        {data.sessions.length === 0 ? <p className="panel-note">No session yet.</p> : null}
        {data.sessions.map((session) => {
          const artifacts = data.artifacts.filter((artifact) => artifact.session_id === session.session_id);
          return (
            <div key={session.session_id} className="ui-ci-list-row" data-testid={`lab-session-${session.session_id}`}>
              <span className="ui-ci-list-main">
                <strong>
                  {session.mode} · {shortId(session.session_id)}
                </strong>
                <span className="ui-id">
                  {session.target_host} · RoE {session.roe_status} · expires {session.retention_expires_at}
                </span>
                <span className="ui-id">
                  {artifacts.length} artifact(s):{" "}
                  {artifacts.map((a) => `${a.kind} ${a.redacted_preview}`).join(", ") || "none"}
                </span>
              </span>
              <span className="lab-button-row">
                <LabChip label={session.state} tone={sessionTone(session.state)} />
                <LabActionButton
                  variant="ghost"
                  disabled={busy || session.state !== "running"}
                  onClick={() => {
                    setSessionId(session.session_id);
                  }}
                  testId={`lab-select-session-${session.session_id}`}
                >
                  Select
                </LabActionButton>
                <LabActionButton
                  variant="ghost"
                  disabled={busy || session.state !== "running"}
                  onClick={() => void stop(session.session_id)}
                  testId={`lab-stop-session-${session.session_id}`}
                >
                  Stop
                </LabActionButton>
              </span>
            </div>
          );
        })}
      </div>

      <LabNote note={note} testId="lab-aitm-note" />
    </LabPanelShell>
  );
}
