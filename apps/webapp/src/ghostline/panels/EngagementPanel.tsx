import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { api } from "../../lib/api";
import type {
  GlBoardWire,
  GlCampaignFunnelWire,
  GlSubjectWire,
  GlTaxonomyWire,
} from "../../lib/api";
import { Chip, Missing } from "../panelParts";
import { stageKeyFor } from "../engagement";

/**
 * Engagement board (Feature 032).
 *
 * The surface neither of the department's channels could provide on its own.
 *
 * Before this, email counted `sent / opened / clicked / submitted` into one counter and
 * voice counted `placed / outcome` into another, in different places, in different
 * currencies. An assessor comparing a phishing campaign against a voice drill got two
 * unrelated numbers. This board puts both channels on ONE ladder, so "who engaged
 * further" is finally a comparable question.
 *
 * Three things this panel is careful about, and each is a way it could be quietly wrong:
 *
 * 1. **Training is a separate visual block, not a row in the funnel.** Adding "finished
 *    training" to "clicked the link" produces one number describing neither. The donor
 *    separates them in its stats view and the separation is reproduced here as a
 *    separate field with its own heading, so no eye can add them by accident either.
 * 2. **A subject appears once per campaign, at their deepest rung.** Three clicks by
 *    one person is one engaged person, not three — and the bar lengths have to mean that,
 *    because a funnel that inflates is worse than no funnel.
 * 3. **Anonymised subjects are shown by pseudonym and say so.** The pseudonym is what
 *    keeps a subject's history linked after their identity is stripped, so the row is
 *    still meaningful; it is just no longer naming anyone, and the panel says which.
 */
export function EngagementPanel() {
  const [board, setBoard] = useState<GlBoardWire | null>(null);
  const [taxonomy, setTaxonomy] = useState<GlTaxonomyWire | null>(null);
  const [missing, setMissing] = useState<string[]>([]);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [boardRes, taxRes] = await Promise.all([
        api.engagementBoard(),
        api.engagementTaxonomy(),
      ]);
      setBoard(boardRes.projection);
      setTaxonomy(taxRes);
      setMissing(boardRes.missing ?? []);
    } catch {
      setBoard(null);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const anonymize = useCallback(
    async (campaignId: string) => {
      setBusy(true);
      setNote(null);
      try {
        const res = await api.anonymizeEngagementCampaign(campaignId);
        setNote(
          `Stripped identity from ${res.anonymized} event(s) in ${campaignId}. Counts are unchanged; ` +
            `the subjects are now reachable only by pseudonym.`,
        );
        await load();
      } catch {
        setNote("anonymisation failed");
      } finally {
        setBusy(false);
      }
    },
    [load],
  );

  const stages = board?.stages ?? taxonomy?.stages ?? [];
  const totals = useMemo(() => {
    const campaigns = board?.campaigns ?? [];
    return {
      subjects: campaigns.reduce((sum, c) => sum + c.subject_count, 0),
      events: campaigns.reduce((sum, c) => sum + c.event_count, 0),
      trainingAssigned: campaigns.reduce((sum, c) => sum + c.training.assigned, 0),
      trainingCompleted: campaigns.reduce((sum, c) => sum + c.training.completed, 0),
      multiChannel: (board?.subjects ?? []).filter((s) => s.channels.length > 1).length,
    };
  }, [board]);

  return (
    <section className="ui-ci-panel" data-testid="gl-engagement-panel">
      <header className="ui-ci-panel-head">
        <span className="ui-pane-title">Engagement board</span>
        <span className="ui-id">tenant-wide · every channel · training tracked separately</span>
        {board ? (
          <Chip
            label={`${board.campaigns.length} campaign(s)`}
            tone={board.campaigns.length > 0 ? "accent" : "gold"}
            testId="gl-engagement-campaign-count"
          />
        ) : null}
      </header>

      {!board || board.campaigns.length === 0 ? (
        <>
          <p className="panel-note" data-testid="gl-engagement-empty">
            No channel has reported an engagement event yet. Both the email channel (Phishing / SAT)
            and the voice channel (GhostLine) write into this log; the board is what they produce.
          </p>
          <Missing
            items={
              missing.length ? missing : [board?.missing?.[0] ?? "GET /specops/engagement/board"]
            }
            testId="gl-engagement-missing"
          />
        </>
      ) : (
        <>
          <div className="ui-ci-metrics" data-testid="gl-engagement-totals">
            <Metric label="subjects" value={totals.subjects} />
            <Metric label="events" value={totals.events} />
            <Metric
              label="both channels"
              value={totals.multiChannel}
              testId="gl-engagement-multichannel"
            />
            <Metric label="campaigns" value={board.campaigns.length} />
          </div>

          {board.campaigns.map((campaign) => (
            <Funnel
              key={campaign.campaign_id}
              campaign={campaign}
              stages={stages}
              onAnonymize={anonymize}
              busy={busy}
            />
          ))}

          {/* The training track, deliberately outside the funnel and under its own
              heading. Its whole purpose is to be visibly NOT part of the ladder. */}
          <div className="ui-gl-training" data-testid="gl-engagement-training">
            <span className="ui-pane-title">Training compliance — a separate track</span>
            <p className="panel-note">
              Counted from training campaigns only and never added into the funnel above. An
              employee who finishes training and one who clicks a link are different observations
              about different things.
            </p>
            <div className="ui-ci-metrics">
              <Metric label="assigned" value={totals.trainingAssigned} />
              <Metric label="completed" value={totals.trainingCompleted} />
            </div>
          </div>

          <div className="ui-ci-col">
            <span className="ui-pane-title">Subjects across every campaign</span>
            <SubjectTable subjects={board.subjects} />
          </div>
        </>
      )}

      {taxonomy && taxonomy.dont_heritage.length > 0 ? (
        <div className="ui-gl-provenance" data-testid="gl-engagement-provenance">
          <div className="ui-gl-provenance-side">
            <span className="op-label">harvested from</span>
            <span className="ui-id">
              donors/phishingclub — the fourteen-event lifecycle, multi-stage depth, the training
              separation, and anonymisation-by-pseudonym.
            </span>
          </div>
          <div className="ui-gl-provenance-side">
            <span className="op-label">deliberately not taken</span>
            <ul className="ui-gl-refusals">
              {taxonomy.dont_heritage.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}

      {note ? (
        <p className="panel-note" data-testid="gl-engagement-note">
          {note}
        </p>
      ) : null}
    </section>
  );
}

function Funnel({
  campaign,
  stages,
  onAnonymize,
  busy,
}: {
  campaign: GlCampaignFunnelWire;
  stages: ReadonlyArray<{ key: string; stage: number; intent: string }>;
  onAnonymize: (campaignId: string) => void;
  busy: boolean;
}) {
  const peak = Math.max(1, ...stages.map((s) => campaign.reached[s.key] ?? 0));
  return (
    <div className="ui-ci-col" data-testid={`gl-funnel-${campaign.campaign_id}`}>
      <div className="ui-ci-list-head">
        <span className="ui-pane-title">{campaign.campaign_id}</span>
        {campaign.channels.map((channel) => (
          <Badge key={channel} tone="analytical" testId={`gl-channel-${channel}`}>
            {channel}
          </Badge>
        ))}
        <span className="ui-id">
          {campaign.subject_count} subject(s) · {campaign.event_count} event(s)
        </span>
        <Button
          size="sm"
          icon="refresh"
          disabled={busy}
          onClick={() => onAnonymize(campaign.campaign_id)}
          title="Strip identity from this campaign's events, keeping every count exact"
          data-testid={`gl-anonymize-${campaign.campaign_id}`}
        >
          Anonymize
        </Button>
      </div>

      <ul className="ui-gl-funnel" data-testid={`gl-funnel-bars-${campaign.campaign_id}`}>
        {stages.map((stage) => {
          const count = campaign.reached[stage.key] ?? 0;
          return (
            <li key={stage.key} data-empty={count === 0} title={stage.intent}>
              <span className="ui-gl-funnel-label">{stage.key}</span>
              <span className="ui-gl-funnel-track">
                <span
                  className="ui-ci-bar"
                  style={{ width: `${Math.round((count / peak) * 100)}%` }}
                />
              </span>
              <span className="op-value">{count}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function SubjectTable({ subjects }: { subjects: ReadonlyArray<GlSubjectWire> }) {
  if (subjects.length === 0) return <p className="panel-note">No subjects yet.</p>;
  return (
    <ul className="ui-gl-subjects" data-testid="gl-engagement-subjects">
      {subjects.map((subject) => {
        const identity = subject.subject_ref ?? subject.pseudonym;
        const key = subjectKeyFor(subject);
        return (
          <li
            key={key}
            data-anonymized={subject.subject_ref === null}
            data-conceded={subject.conceded_campaigns.length > 0}
            data-resisted={subject.resisted_campaigns.length > 0}
            data-testid={`gl-subject-${key}`}
          >
            <span className="ui-gl-subject-id">{identity}</span>
            <span className="ui-gl-subject-channels">
              {subject.channels.map((channel) => (
                <Badge key={channel} tone="analytical">
                  {channel}
                </Badge>
              ))}
            </span>
            <span className="ui-id">
              {subject.campaigns.join(", ")} · depth {stageKeyFor(subject.deepest_stage)} ·{" "}
              {subject.repeat_engaged} campaign(s)
            </span>
            {subject.subject_ref === null ? (
              <Badge
                tone="gold"
                title="Identity stripped; the pseudonym keeps this subject's history linked."
              >
                anonymised
              </Badge>
            ) : null}
            {subject.conceded_campaigns.length > 0 ? (
              <Badge tone="danger">{subject.conceded_campaigns.length} conceded</Badge>
            ) : null}
            {subject.resisted_campaigns.length > 0 ? (
              <Badge tone="accent">{subject.resisted_campaigns.length} resisted</Badge>
            ) : null}
            {/* Training is its own chip, never folded into the badges above. */}
            {subject.trainings_completed > 0 ? (
              <Badge tone="neutral" testId={`gl-subject-trained-${key}`}>
                {subject.trainings_completed} training(s)
              </Badge>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

function Metric({ label, value, testId }: { label: string; value: number; testId?: string }) {
  return (
    <div className="ui-ci-metric">
      <span className="op-label">{label}</span>
      <span className="op-value" data-testid={testId}>
        {value.toLocaleString()}
      </span>
    </div>
  );
}

function subjectKeyFor(subject: GlSubjectWire): string {
  return subject.subject_ref ?? subject.pseudonym ?? "unknown";
}
