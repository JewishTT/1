import { useState } from "react";

import { Button } from "../ui/Button";
import { DataTable } from "../ui/DataTable";
import { EmptyState } from "../ui/Feedback";
import { Input } from "../ui/Input";
import { Tabs } from "../ui/Tabs";
import type {
  Conflict,
  Discovered,
  Dossier,
  Gap,
  Refusal,
  SourceReport,
  SubjectSummary,
} from "../lib/dossier/types";

interface Props {
  subjects: SubjectSummary[];
  dossier: Dossier | null;
  reports: SourceReport[];
  refusals: Refusal[];
  discovered: Discovered[];
  knownAttributes: string[];
  query: string;
  sweeping: boolean;
  error: string | null;
  invariantError: string;
  onSweep: (subject: string, kind: string) => void;
  onOpen: (entityRef: string) => void;
}

type View = "coverage" | "timeline" | "links" | "sources" | "gaps";

/**
 * Dossier surface — what is known about one subject, and what is not.
 *
 * The organising decision is that absence is a first-class thing to show. A dossier that
 * renders only its facts looks identical for a richly investigated subject and for one that
 * was never swept, which is the failure this screen exists to prevent: an analyst must be
 * able to tell "we asked 54 sources and got this" from "we have not asked yet".
 *
 * So every view leads with its own coverage line, and the three counts that would otherwise
 * be read as quality are rendered with what they actually mean:
 *
 * - `ratio` is share of the *expected surface*, not share of what was found;
 * - `saturated` means no further attempts are queued, not that the subject is complete --
 *   both are shown, and they are different claims;
 * - `dormant_windows` counts lifecycle windows nobody swept. It is deliberately not a row
 *   in the timeline, because a row would read as surveillance that did not happen.
 */
export function DossierPage({
  subjects,
  dossier,
  reports,
  refusals,
  discovered,
  knownAttributes,
  query,
  sweeping,
  error,
  invariantError,
  onSweep,
  onOpen,
}: Props) {
  const [subject, setSubject] = useState("");
  const [view, setView] = useState<View>("coverage");

  return (
    <section data-testid="dossier-page">
      <h1>Dossier</h1>
      {dossier && (
        <p className="op-label" data-testid="dossier-identity">
          {dossier.identity.entity_ref} · {dossier.identity.type_label} · rev{" "}
          {dossier.identity.revision} · {dossier.is_complete ? "complete" : "incomplete"}
        </p>
      )}

      <form
        className="panel"
        data-testid="dossier-sweep"
        onSubmit={(e) => {
          e.preventDefault();
          const trimmed = subject.trim();
          if (trimmed) onSweep(trimmed, "");
        }}
      >
        <div className="panel-actions">
          <span className="op-label">Sweep</span>
          {dossier && <span className="status-chip">{query || dossier.identity.entity_ref}</span>}
        </div>
        <div data-testid="dossier-subject-field">
          <Input
            label="Subject"
            mono
            placeholder="domain, name, address or free text"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
          />
        </div>
        <p className="panel-note">
          Sources are chosen by the shape of what you type, not by a subject type: a domain reaches
          the domain sources, a name reaches the ones that take free text.
        </p>
        <div className="panel-actions">
          <Button type="submit" variant="primary" disabled={sweeping || subject.trim() === ""}>
            {sweeping ? "Sweeping…" : "Sweep sources"}
          </Button>
        </div>
      </form>

      {error && (
        <p className="panel-note" data-testid="dossier-error">
          {error}
        </p>
      )}
      {invariantError && (
        <p data-testid="dossier-invariant-error">
          The life-stream could not be folded: {invariantError}
        </p>
      )}
      {sweeping && <p data-testid="dossier-sweeping">Calling sources…</p>}

      {!dossier ? (
        <EmptyState
          testId="dossier-empty"
          title="No dossier yet"
          description="Nothing has been swept for this tenant, so there is nothing to show. Sweep a subject above, or open one that was swept earlier."
          action={
            subjects.length > 0 ? (
              <Button variant="ghost" onClick={() => onOpen(subjects[0].entity_ref)}>
                Open {subjects[0].entity_ref}
              </Button>
            ) : undefined
          }
        />
      ) : (
        <>
          <Tabs
            label="dossier views"
            orientation="bar"
            value={view}
            onValueChange={setView}
            items={[
              { value: "coverage", label: "Coverage" },
              { value: "timeline", label: `Timeline (${dossier.timeline.length})` },
              { value: "links", label: `Links (${dossier.links.edges.length})` },
              { value: "sources", label: `Sources (${reports.length})` },
              { value: "gaps", label: `Gaps (${dossier.gaps.length})` },
            ]}
          />

          {view === "coverage" && (
            <div data-testid="dossier-coverage">
              <CoveragePanel dossier={dossier} known={knownAttributes} />
            </div>
          )}

          {view === "timeline" && (
            <DataTable
              caption="Lifecycle windows holding evidence"
              testId="dossier-timeline"
              rows={dossier.timeline}
              rowId={(r) => r.window_start}
              emptyState={
                <EmptyState
                  title="No events recorded"
                  description="The subject has a life-stream with no windows holding evidence. That is a statement about the data, not a placeholder."
                />
              }
              columns={[
                {
                  key: "start",
                  header: "From",
                  mono: true,
                  render: (r) => r.window_start.slice(0, 10),
                },
                { key: "end", header: "To", mono: true, render: (r) => r.window_end.slice(0, 10) },
                {
                  key: "state",
                  header: "State",
                  render: (r) => <span className="status-chip">{r.state}</span>,
                },
                { key: "events", header: "Events", align: "end", render: (r) => r.event_count },
                {
                  key: "sources",
                  header: "Sources cited",
                  render: (r) => (r.source_refs.length > 0 ? `${r.source_refs.length}` : "—"),
                },
              ]}
            />
          )}

          {view === "links" && (
            <div data-testid="dossier-links">
              <DataTable
                caption="Found, not asserted about the subject"
                testId="dossier-link-table"
                rows={dossier.links.edges}
                rowId={(r) => `${r.source}->${r.target}:${r.kind}`}
                emptyState={
                  <EmptyState
                    title="Nothing was found about this subject"
                    description="No source returned a related entity. Sources that found nothing still appear under Sources with their outcome."
                  />
                }
                columns={[
                  {
                    key: "origin",
                    header: "Origin",
                    render: (r) => <span className="op-label">{r.origin}</span>,
                  },
                  { key: "kind", header: "Relation", render: (r) => r.kind },
                  { key: "target", header: "Found", mono: true, render: (r) => r.target },
                  {
                    key: "ref",
                    header: "Evidence",
                    mono: true,
                    render: (r) => r.source_ref ?? "—",
                  },
                ]}
              />
              {discovered.length > 0 && (
                <p className="panel-note" data-testid="dossier-discovered">
                  {discovered.length} entity/discovered referent(s) found while sweeping — these
                  describe what the sources returned, not properties of {query || "the subject"}.
                </p>
              )}
            </div>
          )}

          {view === "sources" && (
            <div data-testid="dossier-sources">
              <DataTable
                caption="Every source called, including the ones that did not answer"
                testId="dossier-source-table"
                rows={reports}
                rowId={(r) => `${r.source}:${r.attribute}`}
                emptyState={
                  <EmptyState
                    title="No sweep has run for this dossier"
                    description="This dossier was rebuilt from an earlier life-stream; the per-source outcomes of that run are not retained."
                  />
                }
                columns={[
                  { key: "source", header: "Source", mono: true, render: (r) => r.source },
                  { key: "for", header: "Asked for", render: (r) => r.attribute },
                  {
                    key: "outcome",
                    header: "Outcome",
                    render: (r) => <span className="status-chip">{r.outcome}</span>,
                  },
                  { key: "records", header: "Records", align: "end", render: (r) => r.records },
                  { key: "detail", header: "Detail", render: (r) => r.detail || "—" },
                ]}
              />
              {refusals.length > 0 && (
                <ul data-testid="dossier-refusals">
                  {refusals.map((r, i) => (
                    <li key={`${r.source}-${i}`}>
                      <span className="status-chip">{r.reason}</span> {r.source} —{" "}
                      <code>{r.detail}</code>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {view === "gaps" && (
            <DataTable
              caption="Attributes nobody has fetched yet"
              testId="dossier-gap-table"
              rows={dossier.gaps}
              rowId={(g: Gap) => g.attribute}
              emptyState={
                <EmptyState
                  title="Nothing left to attempt"
                  description="Every attribute in the expected surface has been resolved. That means the queue is empty — not that the subject is fully known."
                />
              }
              columns={[
                { key: "attr", header: "Attribute", mono: true, render: (g) => g.attribute },
                {
                  key: "candidates",
                  header: "Would ask",
                  render: (g) =>
                    g.candidate_source_names.length > 0 ? g.candidate_source_names.join(", ") : "—",
                },
                {
                  key: "blocked",
                  header: "Blocked",
                  render: (g) =>
                    g.blocked_source_names.length > 0 ? (
                      <span className="status-chip">{g.blocked_source_names.join(", ")}</span>
                    ) : (
                      "—"
                    ),
                },
              ]}
            />
          )}

          {dossier.conflicts.length > 0 && <Conflicts conflicts={dossier.conflicts} />}
        </>
      )}

      {subjects.length > 0 && (
        <section data-testid="dossier-subjects">
          <h2>Swept subjects</h2>
          <DataTable
            caption="Subjects with a persisted life-stream"
            rows={subjects}
            rowId={(s) => s.entity_ref}
            onRowSelect={onOpen}
            selectedId={dossier?.identity.entity_ref ?? null}
            columns={[
              { key: "ref", header: "Referent", mono: true, render: (s) => s.entity_ref },
              { key: "events", header: "Events", align: "end", render: (s) => s.events },
              {
                key: "last",
                header: "Last observed",
                mono: true,
                render: (s) => (s.last_seen ? s.last_seen.slice(0, 19).replace("T", " ") : "—"),
              },
            ]}
          />
        </section>
      )}
    </section>
  );
}

function CoveragePanel({ dossier, known }: { dossier: Dossier; known: string[] }) {
  const coverage = dossier.coverage;
  const attributes = coverage.attributes;
  if (!coverage.plan_known || !attributes) {
    return (
      <EmptyState
        testId="dossier-coverage-unknown"
        title="Coverage unknown"
        description="No capability plan was available for this read, so the platform cannot say what it has or has not looked for. Absence here is not absence in the world."
      />
    );
  }
  return (
    <>
      <div className="panel">
        <div className="panel-actions">
          <span className="op-label">Coverage</span>
          <span className="status-chip">
            {attributes.saturated ? "queue empty" : "in progress"}
          </span>
        </div>
        <div className="tiles" data-testid="dossier-coverage-figures">
          <Tile label="Attributes" value={`${attributes.total}`} />
          <Tile
            label="Resolved"
            value={`${attributes.acquired + attributes.empty + attributes.conflict}/${attributes.total}`}
          />
          <Tile label="Acquired" value={`${attributes.acquired}`} />
          <Tile label="Proven empty" value={`${attributes.empty}`} />
          <Tile label="Conflicting" value={`${attributes.conflict}`} />
          <Tile label="Never asked" value={`${attributes.unknown}`} />
          <Tile label="Sources" value={`${attributes.distinct_sources}`} />
          <Tile label="Corroborated" value={`${attributes.corroborated}`} />
        </div>

        <p className="panel-note" data-testid="dossier-coverage-verdict">
          {attributes.saturated
            ? "Queue empty: nothing further is scheduled. This is not a claim that the subject is fully known."
            : `${attributes.unknown} attribute(s) have never been asked.`}
          {coverage.dormant_windows > 0 &&
            ` ${coverage.dormant_windows} lifecycle window(s) were not swept and are counted here rather than shown as findings.`}
        </p>

        <p className="panel-note" data-testid="dossier-traceability">
          {coverage.traced_facts}/{coverage.total_facts} facts carry a source ·{" "}
          {coverage.untraced_total} item(s) had none and are excluded from the counts above.
        </p>
      </div>

      {known.length > 0 && (
        <div className="panel">
          <div className="panel-actions">
            <span className="op-label">Acquired attributes</span>
            <span className="status-chip">{known.length}</span>
          </div>
          <div className="chip-row" data-testid="dossier-known">
            {known.map((k) => (
              <span key={k} className="status-chip">
                {k}
              </span>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

/**
 * One figure. The label sits above the value in the app's label voice, so the row reads as
 * "Resolved 10/92" without needing a caption per tile.
 */
function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="op-label">{label}</p>
      <p>{value}</p>
    </div>
  );
}

function Conflicts({ conflicts }: { conflicts: Conflict[] }) {
  return (
    <section data-testid="dossier-conflicts">
      <h2>Conflicts</h2>
      <p className="panel-note">
        Sources disagree. Both readings are kept; the platform has no basis for picking one.
      </p>
      <ul>
        {conflicts.map((c) => (
          <li key={c.subject}>
            <code>{c.subject}</code>:{" "}
            {c.sides
              .map((s) => `${s.value} (${s.sources.join(", ") || "unattributed"})`)
              .join(" vs ")}
          </li>
        ))}
      </ul>
    </section>
  );
}
