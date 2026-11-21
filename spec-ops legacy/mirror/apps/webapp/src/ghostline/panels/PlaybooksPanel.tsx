import { useCallback, useEffect, useState } from "react";

import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { api } from "../../lib/api";
import type { GlPlaybookDetailWire } from "../../lib/api";
import { Chip, Empty, GlShell, Missing, Refusal } from "../panelParts";
import { toPlaybookRow } from "../model";
import type { GlPanel, GlPlaybookRow, GlRefusal, GlStageRow } from "../types";

/**
 * Playbook panel (Feature 031).
 *
 * The donor ships five scenarios as YAML. Reading one before dialling it is the whole
 * point of this panel: a spearphish playbook whose `goto_on_fail` sends the call
 * somewhere its author did not intend is a defect that is cheap to find here and
 * expensive to find on a call.
 *
 * So a playbook renders as its ladder — the twelve stages in canonical order, each
 * carrying what it says, what it waits for, and where it goes — rather than as a form.
 * Branches are drawn as edges, because a linear list actively hides the thing an author
 * most needs to check.
 *
 * Two fields are called out specially. `success_regex` on a stage marked
 * *captures credential* is a stage designed to elicit a secret; showing the pattern is
 * what lets an operator see that before it is used. And every technique on the card is
 * labelled with the mapping source, because GhostLine carries no ATT&CK data and an
 * unattributed technique id would read as a measurement.
 */
export function PlaybooksPanel({ onNavigate }: { onNavigate?: (panel: GlPanel) => void }) {
  const [rows, setRows] = useState<GlPlaybookRow[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<GlPlaybookRow | null>(null);
  const [invalid, setInvalid] = useState<Record<string, string>>({});
  const [missing, setMissing] = useState<string[]>([]);
  const [refusal, setRefusal] = useState<GlRefusal | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await api.listGhostlinePlaybooks();
      setRows(res.playbooks.map((p) => toPlaybookRow(p)));
      setInvalid(res.invalid ?? {});
      setMissing(res.missing ?? []);
      setRefusal(null);
    } catch (err) {
      setRefusal(classifyLike(err));
      setRows([]);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const open = useCallback(async (playbookId: string) => {
    setSelected(playbookId);
    setDetail(null);
    try {
      const res = await api.getGhostlinePlaybook(playbookId);
      setDetail(toPlaybookRow(res.playbook, res.stages));
    } catch (err) {
      setRefusal(classifyLike(err));
    }
  }, []);

  return (
    <GlShell
      title="Playbook library"
      status={
        rows ? (
          <Chip
            label={`${rows.length} loaded`}
            tone={rows.length > 0 ? "accent" : "gold"}
            testId="gl-playbook-count"
          />
        ) : null
      }
      testId="gl-playbooks-panel"
    >
      <Refusal refusal={refusal} testId="gl-playbooks-refusal" />

      <div className="ui-gl-split">
        <div className="ui-ci-col">
          <span className="ui-pane-title">Scenarios</span>
          {rows === null ? (
            <Empty>Loading the donor's playbook tree…</Empty>
          ) : rows.length === 0 ? (
            <Missing
              testId="gl-playbooks-empty"
              items={[
                "GET /specops/ghostline/playbooks (no playbooks loaded — the donor tree is absent or the donor's Playbook validator is not importable)",
              ]}
            />
          ) : (
            <ul className="ui-ci-list" data-testid="gl-playbook-list">
              {rows.map((row) => (
                <li key={row.playbookId}>
                  <button
                    type="button"
                    className="ui-ci-list-row ui-gl-card"
                    data-active={selected === row.playbookId}
                    data-valid={row.valid}
                    onClick={() => void open(row.playbookId)}
                    data-testid={`gl-playbook-${row.playbookId}`}
                  >
                    <span className="ui-ci-list-main">
                      <strong>{row.name}</strong>
                      <span className="ui-id">
                        v{row.version} · {row.stageCount} stages
                        {row.hasBranching ? " · branching" : " · linear"}
                        {row.culture ? ` · ${row.culture}` : ""}
                      </span>
                      <span className="ui-id">
                        persona {row.personaName || "(default)"}
                        {row.author ? ` · ${row.author}` : ""}
                      </span>
                      {!row.valid ? (
                        <span
                          className="ui-gl-invalid"
                          data-testid={`gl-invalid-${row.playbookId}`}
                        >
                          rejected: {row.invalidReason}
                        </span>
                      ) : null}
                    </span>
                    <span className="ui-gl-techniques">
                      {row.techniques.map((t) => (
                        <Badge
                          key={t.id}
                          tone="analytical"
                          title={`${t.reason} (${row.mappingSource})`}
                        >
                          {t.id}
                        </Badge>
                      ))}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {Object.keys(invalid).length > 0 ? (
            <Missing
              testId="gl-playbooks-invalid"
              items={Object.entries(invalid).map(
                ([id, reason]) =>
                  `playbook ${id} was rejected by the donor's validator — ${reason}`,
              )}
            />
          ) : null}
          <Missing items={missing} testId="gl-playbooks-missing" />
        </div>

        <div className="ui-ci-col">
          <span className="ui-pane-title">{detail ? detail.name : "Stage ladder"}</span>
          {detail ? (
            <>
              {detail.description ? <p className="panel-note">{detail.description}</p> : null}
              <div className="ui-gl-ladder" data-testid="gl-ladder">
                {detail.stages.map((stage) => (
                  <StageCard key={stage.stage} stage={stage} />
                ))}
              </div>
              <div className="ui-gl-actions">
                <Button
                  size="sm"
                  icon="activity"
                  onClick={() => onNavigate?.("simulate")}
                  data-testid="gl-goto-simulate"
                >
                  Dry-run this scenario
                </Button>
              </div>
            </>
          ) : (
            <Empty>Choose a scenario to read its stages, branches and prompts.</Empty>
          )}
        </div>
      </div>
    </GlShell>
  );
}

function StageCard({ stage }: { stage: GlStageRow }) {
  return (
    <article
      className="ui-gl-stage"
      data-role={stage.role}
      data-branch={stage.branching}
      data-captures={stage.capturesCredential}
      data-testid={`gl-stage-${stage.stage}`}
    >
      <header className="ui-gl-stage-head">
        <span className="ui-gl-stage-name">{stage.stage}</span>
        <span className="ui-gl-stage-intent">{stage.intent}</span>
        {stage.persona ? <Chip label={stage.persona} tone="analytical" /> : null}
        {stage.branching ? (
          <Chip
            label={
              stage.gotoOnSuccess
                ? `on match → ${stage.gotoOnSuccess}`
                : `on fail → ${stage.gotoOnFail}`
            }
            tone="gold"
            title="This stage declares a branch, so the ladder is not a straight line."
            testId={`gl-branch-${stage.stage}`}
          />
        ) : null}
        {stage.capturesCredential ? (
          <Chip
            label="elicits a credential"
            tone="danger"
            title="This stage's success pattern matches a secret. Transcripts here are redacted and the credential is never stored."
            testId={`gl-captures-${stage.stage}`}
          />
        ) : null}
      </header>

      {stage.prompt ? (
        <p className="ui-gl-stage-prompt">{stage.prompt}</p>
      ) : (
        <Empty>No prompt.</Empty>
      )}

      <dl className="ui-gl-stage-facts">
        <div>
          <dt>success</dt>
          <dd>
            <code>{stage.successRegex ?? "—"}</code>
          </dd>
        </div>
        <div>
          <dt>cycles</dt>
          <dd>{stage.maxCycles}</dd>
        </div>
        <div>
          <dt>silence</dt>
          <dd>{stage.silentUntil === null ? "not served" : `${stage.silentUntil}s`}</dd>
        </div>
        <div>
          <dt>language</dt>
          <dd>{stage.languageHint ?? "—"}</dd>
        </div>
        <div>
          <dt>triggers</dt>
          <dd data-testid={`gl-triggers-${stage.stage}`}>
            {stage.psychTriggers.length > 0 ? stage.psychTriggers.join(", ") : "not served"}
          </dd>
        </div>
      </dl>

      {stage.checkinLine ? (
        <p className="ui-gl-stage-checkin">on silence: “{stage.checkinLine}”</p>
      ) : null}
    </article>
  );
}

// The playbook panel's failures are reads, not authorisations, so a 404 is an
// absence rather than a gate verdict. Kept local rather than imported so this panel
// does not grow a dependency on the dialer's error contract.
function classifyLike(err: unknown): GlRefusal {
  const status = (err as { status?: number }).status;
  if (status === 404) return { kind: "absent", reason: "that playbook is not loaded" };
  return {
    kind: "setup",
    reason: err instanceof Error ? err.message : String(err),
  };
}

export type { GlPlaybookDetailWire };
