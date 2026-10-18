import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "../../ui/Button";
import { Select } from "../../ui/Input";
import { api } from "../../lib/api";
import { Chip, Empty, GlShell, Missing, Refusal } from "../panelParts";
import { outcomeLabel, toPlaybookRow, toSimulationRow } from "../model";
import { STAGE_LADDER } from "../types";
import type { GlPanel, GlPlaybookRow, GlRefusal, GlSimulationRow } from "../types";

/**
 * Simulator panel (Feature 031).
 *
 * This is the surface that earns GhostLine its place in the department. The donor's
 * `PlaybookRunner` is pure logic — no I/O, no provider, no phone — so the platform can
 * run the donor's *actual* stage machine over a scripted transcript and show exactly
 * where each utterance would have moved the call.
 *
 * That matters more than it first appears. A `max_cycles: 1` on an URGENCY stage with no
 * `goto_on_fail` sends the call to the next stage whatever the target says; a
 * `success_regex` that can never match makes a stage a dead end. Both are invisible in
 * a YAML file and obvious in a trace. The donor's CLI has no way to show either — it can
 * only place a call and find out.
 *
 * What the panel does NOT do: nothing here dials, nothing is persisted, and the
 * utterances are redacted server-side on the way back out. A transcript is the same kind
 * of text a target would produce, so it is scrubbed before it is displayed — the trace
 * shows that a credential was elicited, never the credential.
 */
export function SimulatePanel() {
  const [playbooks, setPlaybooks] = useState<GlPlaybookRow[]>([]);
  const [playbookId, setPlaybookId] = useState("");
  const [script, setScript] = useState("");
  const [result, setResult] = useState<GlSimulationRow | null>(null);
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState<GlRefusal | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const res = await api.listGhostlinePlaybooks();
        const rows = res.playbooks.map((p) => toPlaybookRow(p));
        setPlaybooks(rows);
        const first = rows.find((p) => p.valid);
        if (first) setPlaybookId(first.playbookId);
      } catch (err) {
        setRefusal({ kind: "setup", reason: err instanceof Error ? err.message : String(err) });
      }
    })();
  }, []);

  const utterances = useMemo(
    () =>
      script
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean),
    [script],
  );

  const run = useCallback(async () => {
    setBusy(true);
    setRefusal(null);
    setResult(null);
    try {
      const res = await api.simulateGhostlinePlaybook(playbookId, utterances);
      setResult(toSimulationRow(res.simulation));
    } catch (err) {
      setRefusal({
        kind: "setup",
        reason: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setBusy(false);
    }
  }, [playbookId, utterances]);

  return (
    <GlShell
      title="Stage machine simulator"
      status={
        result ? (
          <Chip
            label={result.outcome ? outcomeLabel(result.outcome) : "no terminal state"}
            tone={result.outcome === "compromised" ? "danger" : result.outcome ? "gold" : "neutral"}
            testId="gl-sim-outcome"
          />
        ) : null
      }
      testId="gl-simulate-panel"
    >
      <Refusal refusal={refusal} testId="gl-sim-refusal" />

      <p className="panel-note">
        Runs the donor&apos;s own <code>PlaybookRunner</code> over a scripted transcript.
        Nothing is dialled and nothing is written to the ledger. One utterance per line, in
        the order the target would say them.
      </p>

      <div className="ui-ci-col">
        <Select
          label="Playbook"
          value={playbookId}
          onValueChange={setPlaybookId}
          options={[
            { value: "", label: playbooks.length ? "choose a playbook" : "no playbooks loaded" },
            ...playbooks
              .filter((p) => p.valid)
              .map((p) => ({ value: p.playbookId, label: `${p.name} (${p.stageCount} stages)` })),
          ]}
          data-testid="gl-sim-playbook"
        />
        <span className="ui-field">
          <label className="ui-field-label" htmlFor="gl-sim-script">
            Scripted transcript$r
          </label>
          <textarea
            id="gl-sim-script"
            className="ui-gl-textarea"
            rows={7}
            value={script}
            placeholder={"yes, that works\nI am single\nmy code is 482913"}
            onChange={(event) => setScript(event.target.value)}
            data-testid="gl-sim-script"
          />
          <span className="ui-field-hint">
            {utterances.length} utterance(s). Anything credential-shaped is redacted on the
            way back out.
          </span>
        </span>
        <div>
          <Button
            variant="primary"
            size="sm"
            icon="activity"
            disabled={busy || !playbookId || utterances.length === 0}
            onClick={() => void run()}
            data-testid="gl-sim-run"
          >
            Run the stage machine
          </Button>
        </div>
      </div>

      {result ? (
        <div className="ui-ci-col" data-testid="gl-sim-result">
          <div className="ui-ci-list-head">
            <span className="ui-pane-title">
              {result.playbookName} · ends at {result.finalStage ?? "unknown stage"}
            </span>
            <Chip
              label={`${result.credentialsCaptured} credentials captured`}
              tone="neutral"
              title="Structural: the platform records that a credential was elicited and never stores it."
              testId="gl-sim-no-capture"
            />
            {result.redactionKinds.length > 0 ? (
              <Chip label={`redacted: ${result.redactionKinds.join(", ")}`} tone="gold" testId="gl-sim-kinds" />
            ) : null}
          </div>
          {result.outcomeReason ? <p className="panel-note">{result.outcomeReason}</p> : null}
          <ol className="ui-gl-trace" data-testid="gl-sim-trace">
            {result.steps.map((step) => (
              <li
                key={step.index}
                data-held={step.held}
                data-success={step.success}
                data-exited={step.exited}
                data-testid={`gl-sim-step-${step.index}`}
              >
                <div className="ui-gl-trace-head">
                  <span className="ui-gl-trace-utterance">{step.utterance}</span>
                  <span className="ui-gl-trace-arrow">
                    {step.stageBefore} → {step.stageAfter}
                  </span>
                  {step.held ? (
                    <Chip
                      label={`held · ${step.cyclesRemaining} cycle(s) left`}
                      tone="gold"
                      title="The stage did not advance. On the last cycle this becomes a fail branch."
                      testId={`gl-sim-held-${step.index}`}
                    />
                  ) : null}
                  {step.matchedPattern ? <Chip label={step.matchedPattern} tone="accent" /> : null}
                  {step.exited ? <Chip label="terminal" tone="danger" testId={`gl-sim-exit-${step.index}`} /> : null}
                </div>
                {step.nextLine ? <p className="ui-gl-trace-next">{step.nextLine}</p> : null}
              </li>
            ))}
          </ol>
          <Ladder finalStage={result.finalStage} />
          <Missing items={result.missing} testId="gl-sim-missing" />
        </div>
      ) : (
        <Empty>
          No run yet. {STAGE_LADDER.length} stages in the donor&apos;s taxonomy; a run shows
          which of them this scenario actually reaches.
        </Empty>
      )}
    </GlShell>
  );
}

/** Which rung of the twelve-stage ladder the call finished on. */
function Ladder({ finalStage }: { finalStage: string | null }) {
  if (!finalStage) return null;
  return (
    <ol className="ui-gl-rungs" data-testid="gl-sim-rungs">
      {STAGE_LADDER.map((stage) => {
        const reached = STAGE_LADDER.indexOf(stage) <= STAGE_LADDER.indexOf(finalStage);
        return (
          <li key={stage} data-reached={reached} data-current={stage === finalStage}>
            {stage}
          </li>
        );
      })}
    </ol>
  );
}

export type { GlPanel };