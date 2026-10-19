import { useCallback, useState } from "react";

import { Input } from "../../ui/Input";
import { api } from "../../lib/api";
import type { CiSubjectWire } from "../../lib/api";
import { subjectInvariant } from "../model";
import type { SubjectRow } from "../types";
import { CiEmpty, CiPanelShell, NamedAbsence, StatusChip } from "./panelParts";

/**
 * Counterintelligence subject board (US4).
 *
 * Open a subject — person / org / account / channel / campaign — and read its
 * tracked invariants: belief-state, narrative-position, bias-profile,
 * coordination-signature, phase-state. Each invariant carries its evidence refs;
 * one without evidence is rendered as UNSUPPORTED, never asserted (FR-008). This
 * is the counterintelligence half of the department — cognitive attack read-out,
 * not pipeline telemetry.
 */
export function CounterintelPanel() {
  const [subjectId, setSubjectId] = useState("");
  const [subject, setSubject] = useState<SubjectRow | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!subjectId.trim()) return;
    setBusy(true);
    setNote(null);
    try {
      const res = await api.getSubject(subjectId.trim());
      setSubject(toSubjectRow(res.subject));
    } catch (err) {
      setSubject(null);
      setNote(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [subjectId]);

  return (
    <CiPanelShell
      title="Counterintelligence subject board"
      scope="investigation-scoped"
      testId="ci-counterintel-panel"
    >
      <div className="ui-ci-col">
        <span className="ui-pane-title">Subject</span>
        <Input
          value={subjectId}
          onChange={(e) => setSubjectId(e.target.value)}
          placeholder="subject id"
          aria-label="Subject id"
          data-testid="ci-subject-input"
        />
        <button
          type="button"
          className="ui-btn"
          data-size="sm"
          disabled={busy}
          onClick={() => void load()}
          data-testid="ci-subject-load"
        >
          Open subject
        </button>
      </div>

      {subject ? (
        <div className="ui-ci-col" data-testid="ci-subject">
          <div className="ui-ci-list-head">
            <span className="ui-pane-title">{subject.display}</span>
            <StatusChip label={subject.kind} tone="neutral" />
          </div>
          <ul className="ui-ci-invariants" data-testid="ci-invariants">
            {subject.invariants.map((inv) => (
              <li
                key={inv.kind}
                data-supported={inv.supported}
                data-testid={`ci-invariant-${inv.kind}`}
              >
                <span className="ui-ci-invariant-kind">{inv.kind}</span>
                <span className="ui-ci-invariant-value">{inv.value}</span>
                {inv.confidence != null ? (
                  <span className="ui-id">confidence {inv.confidence.toFixed(2)}</span>
                ) : null}
                <StatusChip
                  label={inv.supported ? `${inv.evidence_refs.length} evidence` : "unsupported"}
                  tone={inv.supported ? "accent" : "gold"}
                  testId={`ci-invariant-support-${inv.kind}`}
                />
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <CiEmpty>Enter a subject id to read its tracked invariants.</CiEmpty>
      )}

      {note ? (
        <p className="panel-note" data-testid="ci-counterintel-note">
          {note}
        </p>
      ) : null}
      <NamedAbsence
        testId="ci-counterintel-missing"
        missing={[
          "GET /specops/counterintel/subjects/{id} (cognitive operators not yet wired — CognitiveAttack / DIMA / io-coordinated-replies)",
        ]}
      />
    </CiPanelShell>
  );
}

function toSubjectRow(w: CiSubjectWire): SubjectRow {
  return {
    subject_id: w.subject_id,
    kind: w.kind,
    display: w.display,
    invariants: w.invariants.map((inv) =>
      subjectInvariant({
        kind: inv.kind as SubjectRow["invariants"][number]["kind"],
        value: inv.value,
        confidence: inv.confidence ?? null,
        evidence_refs: inv.evidence_refs ?? [],
      }),
    ),
  };
}
