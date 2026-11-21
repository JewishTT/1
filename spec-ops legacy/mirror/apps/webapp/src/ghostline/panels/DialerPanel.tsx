import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "../../ui/Button";
import { Input, Select } from "../../ui/Input";
import { api } from "../../lib/api";
import type { GlStatusWire } from "../../lib/api";
import {
  Chip,
  classify,
  Empty,
  GlShell,
  ProviderList,
  Refusal,
  RuntimeDot,
  fromStatus,
} from "../panelParts";
import { dialReadiness, outcomeLabel, toCallRow, toPlaybookRow, toVoiceRow } from "../model";
import type {
  GlCallRow,
  GlPanel,
  GlPlaybookRow,
  GlRefusal,
  GlRuntimeRow,
  GlVoiceRow,
} from "../types";

/**
 * Dialer panel (Feature 031) — the donor's `call` verb.
 *
 * Two things the CLI's version does not have, and both are the reason this surface is
 * where it is.
 *
 * **The gate is on screen.** `ghostline call +1555… --campaign demo` trusts the operator
 * to hold a signed authorisation. This platform does not trust, it verifies: the route
 * runs `specops.roe.gate.launch_campaign` before the donor's Twilio service is touched,
 * so an unrostered number comes back 422 and is rendered as a refusal with the rejected
 * number named — not as a failed call, and never as a silent no-op. The roster field is
 * therefore not a formality; it is the thing being checked.
 *
 * **The caller ID is never echoed.** `GHOSTLINE_TWILIO_FROM_NUMBER` is the operator's own
 * PSTN identity, and the donor's README says so. It is read by the platform and used to
 * place calls; it is not served here, and readiness reports only whether it is set.
 *
 * The capture counter is rendered on purpose. An assessment needs to know that a target
 * complied; it does not need the credential, and a panel that showed a captured one-time
 * code would be the wrong shape for this platform. `0` is the honest number and it is on
 * screen so nobody has to take the platform's word for it.
 */
export function DialerPanel({ onNavigate }: { onNavigate?: (panel: GlPanel) => void }) {
  const [status, setStatus] = useState<GlStatusWire | null>(null);
  const [playbooks, setPlaybooks] = useState<GlPlaybookRow[]>([]);
  const [voices, setVoices] = useState<GlVoiceRow[]>([]);
  const [calls, setCalls] = useState<GlCallRow[]>([]);

  const [target, setTarget] = useState("");
  const [campaign, setCampaign] = useState("drill");
  const [persona, setPersona] = useState("professional");
  const [roeId, setRoeId] = useState("");
  const [rosterText, setRosterText] = useState("");
  const [playbookId, setPlaybookId] = useState("");

  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState<GlRefusal | null>(null);
  const [note, setNote] = useState<string | null>(null);

  /**
   * Refresh everything this panel reads.
   *
   * `preserveRefusal` exists because of a real bug: after a dialled call is refused,
   * the panel refreshes so the ledger and the runtime are current — and a plain
   * `load()` clears the refusal on the way through, erasing the one thing the
   * operator needed to see. The refresh is still wanted; the erasure is not.
   */
  const load = useCallback(async (preserveRefusal = false) => {
    try {
      const [statusRes, pbRes, voiceRes, callRes] = await Promise.all([
        api.ghostlineStatus(),
        api.listGhostlinePlaybooks(),
        api.listGhostlineVoices(),
        api.listGhostlineCalls(25),
      ]);
      setStatus(statusRes);
      setPlaybooks(pbRes.playbooks.map((p) => toPlaybookRow(p)));
      setVoices(voiceRes.voices.map((v) => toVoiceRow(v)));
      setCalls(callRes.calls.map((c) => toCallRow(c)));
      if (!preserveRefusal) setRefusal(null);
    } catch (err) {
      setRefusal(classify(err));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const { providers, runtime } = useMemo(
    () => (status ? fromStatus(status) : { providers: [], runtime: null as GlRuntimeRow | null }),
    [status],
  );

  const roster = useMemo(
    () =>
      rosterText
        .split(/[\s,]+/)
        .map((s) => s.trim())
        .filter(Boolean),
    [rosterText],
  );

  const readiness = runtime ? dialReadiness(runtime) : { ready: false, reason: "loading status" };
  const onRoster = roster.some((entry) => entry.toLowerCase() === target.trim().toLowerCase());

  const dial = useCallback(async () => {
    setBusy(true);
    setRefusal(null);
    setNote(null);
    try {
      const res = await api.dialGhostline({
        target,
        campaign,
        persona,
        roe_id: roeId,
        approved_roster: roster,
        playbook_id: playbookId || null,
      });
      setNote(
        `Placed ${res.placed.sid} → ${res.placed.to_number} under ${res.authorisation.roe_id}. ` +
          `${res.credentials_captured} credentials captured.`,
      );
      setTarget("");
      await load();
    } catch (err) {
      setRefusal(classify(err));
      // Refresh so the runtime checklist reflects whatever the refusal implies, but
      // keep the refusal: it is the reason the dial did not happen.
      await load(true);
    } finally {
      setBusy(false);
    }
  }, [target, campaign, persona, roeId, roster, playbookId, load]);

  const complete = useCallback(
    async (callId: string, outcome: string) => {
      setBusy(true);
      try {
        await api.completeGhostlineCall(callId, { outcome });
        await load();
      } catch (err) {
        setRefusal(classify(err));
      } finally {
        setBusy(false);
      }
    },
    [load],
  );

  const e164Valid = /^\+[1-9]\d{6,14}$/.test(target.trim());

  return (
    <GlShell
      title="Dialler"
      status={runtime ? <RuntimeDot runtime={runtime} testId="gl-dialer-runtime" /> : null}
      testId="gl-dialer-panel"
    >
      <Refusal refusal={refusal} testId="gl-dialer-refusal" />

      {!readiness.ready ? (
        <div className="ui-gl-refusal" data-kind="setup" data-testid="gl-dialer-not-ready">
          <Chip label="not ready to dial" tone="gold" />
          <span className="ui-gl-refusal-reason">{readiness.reason}</span>
          <Button
            size="sm"
            icon="activity"
            onClick={() => onNavigate?.("runtime")}
            data-testid="gl-goto-runtime"
          >
            Open the runtime
          </Button>
        </div>
      ) : null}

      <div className="ui-gl-split">
        <div className="ui-ci-col">
          <span className="ui-pane-title">Call</span>
          <Input
            label="Target number (E.164)"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            placeholder="+15551234567"
            mono
            data-testid="gl-target"
          />
          {!target || e164Valid ? null : (
            <span className="ui-gl-hint" data-testid="gl-target-invalid">
              Not E.164. Use the full international form, e.g. +15551234567.
            </span>
          )}
          <div className="ui-gl-pair">
            <Input
              label="Campaign"
              value={campaign}
              onChange={(e) => setCampaign(e.target.value)}
              data-testid="gl-campaign"
            />
            <Select
              label="Prosody persona"
              value={persona}
              onValueChange={setPersona}
              options={PERSONA_OPTIONS}
              data-testid="gl-persona"
            />
          </div>
          <Select
            label="Playbook"
            value={playbookId}
            onValueChange={setPlaybookId}
            options={[
              { value: "", label: runtime?.playbookName ?? "use the runtime's playbook" },
              ...playbooks.map((p) => ({ value: p.playbookId, label: p.name })),
            ]}
            data-testid="gl-dial-playbook"
          />
        </div>

        <div className="ui-ci-col">
          <span className="ui-pane-title">Authorisation</span>
          <Input
            label="RoE sign-off id"
            value={roeId}
            onChange={(e) => setRoeId(e.target.value)}
            placeholder="roe-…"
            mono
            hint="Recorded by a supervisor on the Sign-off tab. No id, no dial."
            data-testid="gl-roe-id"
          />
          <span className="ui-field">
            <label className="ui-field-label" htmlFor="gl-roster">
              Supervisor-approved roster$r
            </label>
            <textarea
              id="gl-roster"
              className="ui-gl-textarea"
              rows={3}
              value={rosterText}
              placeholder="+15551234567, +15557654321"
              onChange={(event) => setRosterText(event.target.value)}
              data-testid="gl-roster"
            />
            <span className="ui-field-hint">
              {roster.length} approved target(s). A number outside this list is refused before it
              reaches the provider.
            </span>
          </span>
          {target && !onRoster ? (
            <span className="ui-gl-hint" data-kind="danger" data-testid="gl-target-unrostered">
              This number is not on the roster — the dial will be refused with RosterError.
            </span>
          ) : null}
          <div>
            <Button
              variant="primary"
              size="sm"
              icon="activity"
              disabled={
                busy ||
                !readiness.ready ||
                !e164Valid ||
                roeId.trim().length === 0 ||
                roster.length === 0
              }
              onClick={() => void dial()}
              data-testid="gl-dial"
            >
              Place call (RoE-gated)
            </Button>
          </div>
          <Chip
            label="0 credentials captured"
            tone="neutral"
            title="Structural: the platform never stores an elicited credential. The transcript records that one was given, and not what it was."
            testId="gl-no-capture"
          />
        </div>
      </div>

      <div className="ui-ci-col">
        <span className="ui-pane-title">Recent calls</span>
        {calls.length === 0 ? (
          <Empty>No calls recorded yet.</Empty>
        ) : (
          <ul className="ui-ci-list" data-testid="gl-call-list">
            {calls.map((call) => (
              <li
                key={call.callId}
                className="ui-ci-list-row"
                data-outcome={call.outcome ?? "none"}
              >
                <div className="ui-ci-list-main">
                  <strong>{call.target}</strong>
                  <code className="ui-id">{call.sid ?? call.callId}</code>
                  <span className="ui-id">
                    {call.campaign} · {call.persona} · {call.messageCount} turn(s) · stage{" "}
                    {call.finalStage ?? "—"}
                  </span>
                </div>
                <Chip
                  label={outcomeLabel(call.outcome)}
                  tone={
                    call.outcome === "compromised" ? "danger" : call.outcome ? "gold" : "neutral"
                  }
                  testId={`gl-call-outcome-${call.callId}`}
                />
                {call.outcome === null ? (
                  <span className="ui-gl-complete">
                    <Button
                      size="sm"
                      disabled={busy}
                      onClick={() => void complete(call.callId, "compromised")}
                      data-testid={`gl-complete-compromised-${call.callId}`}
                    >
                      Complied
                    </Button>
                    <Button
                      size="sm"
                      disabled={busy}
                      onClick={() => void complete(call.callId, "abandoned")}
                      data-testid={`gl-complete-abandoned-${call.callId}`}
                    >
                      Did not comply
                    </Button>
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="ui-ci-col">
        <span className="ui-pane-title">What the platform will dial with</span>
        <ProviderList
          providers={providers.filter((p) => p.name !== "tunnel")}
          testId="gl-dialer-providers"
        />
        <span className="ui-id">
          {voices.length} voice(s) registered · {playbooks.filter((p) => p.valid).length}{" "}
          playbook(s) loadable
        </span>
      </div>

      {note ? (
        <p className="panel-note" data-testid="gl-dialer-note">
          {note}
        </p>
      ) : null}
    </GlShell>
  );
}

const PERSONA_OPTIONS = [
  "professional",
  "excited",
  "confident",
  "thoughtful",
  "concerned",
  "urgent",
  "soothing",
].map((value) => ({ value, label: value }));
