import { useCallback, useEffect, useState } from "react";

import { Button } from "../../ui/Button";
import { Input } from "../../ui/Input";
import { api } from "../../lib/api";
import { Chip, classify, Empty, GlShell, Missing, Refusal } from "../panelParts";
import { outcomeLabel, toCallRow, toPlaybookRow } from "../model";
import { STAGE_LADDER } from "../types";
import type { GlCallRow, GlPlaybookRow, GlRefusal } from "../types";

/**
 * Transcripts panel (Feature 031).
 *
 * The donor's own ledger is SQLite behind `aiosqlite`, a package this platform does not
 * carry, so the exercise record lives in a JSONL ledger with the donor's column shape.
 * What that costs and what it buys are worth stating: there is no audio, because the
 * donor streams call audio through Twilio and stores none — a `/audio` endpoint is a
 * named absence, not a broken link.
 *
 * The transcript is shown the way it was stored: redacted. Every turn carries the kinds
 * of secret removed from it, so an assessor can see that a one-time code was elicited by
 * a CLOSE stage without ever being able to read it back. That is the platform's position
 * stated as a fact about the data rather than as a promise in a policy document.
 *
 * Turns can also be appended by hand, which is how a live call reaches this ledger when
 * the donor's media server owns the socket. It goes through the same redaction, so a
 * turn typed here is indistinguishable from one the donor wrote.
 */
export function TranscriptsPanel() {
  const [calls, setCalls] = useState<GlCallRow[] | null>(null);
  const [missing, setMissing] = useState<string[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<GlCallRow | null>(null);
  const [playbooks, setPlaybooks] = useState<GlPlaybookRow[]>([]);
  const [refusal, setRefusal] = useState<GlRefusal | null>(null);
  const [busy, setBusy] = useState(false);

  const [draftRole, setDraftRole] = useState("target");
  const [draftText, setDraftText] = useState("");
  const [draftStage, setDraftStage] = useState("");

  const load = useCallback(async () => {
    try {
      const [callRes, pbRes] = await Promise.all([
        api.listGhostlineCalls(50),
        api.listGhostlinePlaybooks(),
      ]);
      setCalls(callRes.calls.map((c) => toCallRow(c)));
      setMissing(callRes.missing ?? []);
      setPlaybooks(pbRes.playbooks.map((p) => toPlaybookRow(p)));
      setRefusal(null);
    } catch (err) {
      setRefusal(classify(err));
      setCalls([]);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const open = useCallback(
    async (callId: string) => {
      setSelected(callId);
      setDetail(null);
      try {
        const res = await api.getGhostlineCall(callId);
        setDetail(toCallRow(res.call, res.call.messages));
        if (res.call.playbook_id) {
          const match = playbooks.find((p) => p.playbookId === res.call.playbook_id);
          setDraftStage(match ? (match.firstStage ?? "") : "");
        }
      } catch (err) {
        setRefusal(classify(err));
      }
    },
    [playbooks],
  );

  const append = useCallback(async () => {
    if (!selected) return;
    setBusy(true);
    setRefusal(null);
    try {
      await api.logGhostlineTurn(selected, {
        role: draftRole,
        content: draftText,
        stage: draftStage || null,
      });
      setDraftText("");
      await open(selected);
      await load();
    } catch (err) {
      setRefusal(classify(err));
    } finally {
      setBusy(false);
    }
  }, [selected, draftRole, draftText, draftStage, open, load]);

  return (
    <GlShell
      title="Call transcripts"
      status={
        calls ? (
          <Chip
            label={`${calls.length} call(s)`}
            tone={calls.length > 0 ? "accent" : "neutral"}
            testId="gl-transcript-count"
          />
        ) : null
      }
      testId="gl-transcripts-panel"
    >
      <Refusal refusal={refusal} testId="gl-transcripts-refusal" />
      <Missing items={missing} testId="gl-transcripts-missing" />

      <div className="ui-gl-split">
        <div className="ui-ci-col">
          <span className="ui-pane-title">Ledger</span>
          {calls === null ? (
            <Empty>Loading…</Empty>
          ) : calls.length === 0 ? (
            <Empty>No calls yet. Place one from the Dialler, or run a scenario first.</Empty>
          ) : (
            <ul className="ui-ci-list" data-testid="gl-transcript-list">
              {calls.map((call) => (
                <li key={call.callId}>
                  <button
                    type="button"
                    className="ui-ci-list-row ui-gl-card"
                    data-active={selected === call.callId}
                    data-outcome={call.outcome ?? "none"}
                    onClick={() => void open(call.callId)}
                    data-testid={`gl-call-${call.callId}`}
                  >
                    <span className="ui-ci-list-main">
                      <strong>{call.target}</strong>
                      <code className="ui-id">{call.callId}</code>
                      <span className="ui-id">
                        {call.campaign} · {call.messageCount} turn(s) ·{" "}
                        {call.playbookId ?? "no playbook"}
                      </span>
                    </span>
                    <Chip
                      label={outcomeLabel(call.outcome)}
                      tone={
                        call.outcome === "compromised"
                          ? "danger"
                          : call.outcome
                            ? "gold"
                            : "neutral"
                      }
                    />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="ui-ci-col">
          <span className="ui-pane-title">
            {detail ? `Transcript ${detail.callId}` : "Transcript"}
          </span>
          {detail ? (
            <>
              <div className="ui-ci-list-head">
                <Chip
                  label={`${detail.credentialsCaptured} credentials captured`}
                  tone="neutral"
                  testId="gl-detail-no-capture"
                />
                {detail.roeId ? <Chip label={`RoE ${detail.roeId}`} tone="gold" /> : null}
                {detail.finalStage ? (
                  <Chip label={`ended at ${detail.finalStage}`} tone="analytical" />
                ) : null}
              </div>
              <ol className="ui-gl-turns" data-testid="gl-turns">
                {detail.messages.length === 0 ? (
                  <li className="ui-gl-turn-empty">No turns recorded.</li>
                ) : (
                  detail.messages.map((message, index) => (
                    <li
                      key={`${message.timestamp}-${index}`}
                      data-role={message.role}
                      data-testid={`gl-turn-${index}`}
                    >
                      <div className="ui-gl-turn-head">
                        <span className="ui-gl-turn-role">{message.role}</span>
                        {message.stage ? <Chip label={message.stage} tone="analytical" /> : null}
                        {message.redactionKinds.length > 0 ? (
                          <Chip
                            label={`redacted: ${message.redactionKinds.join(", ")}`}
                            tone="gold"
                            title="A credential-shaped span was removed before this turn was stored."
                            testId={`gl-turn-redacted-${index}`}
                          />
                        ) : null}
                        {message.triggerUsed ? (
                          <Chip label={message.triggerUsed} tone="neutral" />
                        ) : null}
                        {message.objectionType ? (
                          <Chip label={`objection: ${message.objectionType}`} tone="gold" />
                        ) : null}
                      </div>
                      <p className="ui-gl-turn-text">{message.content}</p>
                    </li>
                  ))
                )}
              </ol>

              <span className="ui-pane-title">Append a turn</span>
              <div className="ui-gl-pair">
                <Input
                  label="Speaker"
                  value={draftRole}
                  onChange={(e) => setDraftRole(e.target.value)}
                  hint="target · agent · operator"
                  data-testid="gl-turn-role"
                />
                <Input
                  label="Stage"
                  value={draftStage}
                  onChange={(e) => setDraftStage(e.target.value)}
                  hint={STAGE_LADDER.join(" · ")}
                  mono
                  data-testid="gl-turn-stage"
                />
              </div>
              <span className="ui-field">
                <label className="ui-field-label" htmlFor="gl-turn-text">
                  Content$r
                </label>
                <textarea
                  id="gl-turn-text"
                  className="ui-gl-textarea"
                  rows={3}
                  value={draftText}
                  onChange={(event) => setDraftText(event.target.value)}
                  data-testid="gl-turn-content"
                />
                <span className="ui-field-hint">Redacted server-side before it is written.</span>
              </span>
              <div>
                <Button
                  size="sm"
                  icon="plus"
                  disabled={busy || draftText.trim().length === 0}
                  onClick={() => void append()}
                  data-testid="gl-turn-append"
                >
                  Append
                </Button>
              </div>
            </>
          ) : (
            <Empty>Choose a call to read its redacted transcript.</Empty>
          )}
        </div>
      </div>
    </GlShell>
  );
}
