import { Badge, StatusDot } from "../ui/Badge";
import { Button } from "../ui/Button";
import { EmptyState } from "../ui/Feedback";
import { toWorkStatus } from "../ui/status";
import type { ObjectRow } from "./types";

/**
 * ObjectRecordView (T132, §26, §35, §99).
 *
 * The detail pane for one selected row: every field the kind's row type carries,
 * grouped by what the field MEANS rather than by the order the interface
 * declared it.
 *
 * THE RULE THIS COMPONENT EXISTS TO KEEP VISIBLE.
 *
 * §99: a value the platform did not report reads "not reported", never `—`,
 * never `0`, never an empty cell. An empty cell and a zero look identical in a
 * table and mean opposite things; an absent status and a healthy one look the
 * same and mean opposite things. So every accessor below goes through one of two
 * helpers and there is no third path:
 *
 *   <Reported>  a real value, printed as the platform sent it
 *   <Absent>    "not reported", in the unreported style
 *
 * `status` shows BOTH the platform's raw string and the §92 projection, so the
 * mapping from one vocabulary to the other stays auditable rather than becoming a
 * silent translation.
 *
 * KIND-SPECIFIC GROUPS, NOT A GENERIC KEY-VALUE DUMP. A Claim is not an Entity
 * with different data; showing a claim's temporal scope and validation grade in
 * the same section as an entity's aliases would tell the analyst they are the
 * same kind of thing. §99 exists to let the UI show that an observation, a
 * candidate, a claim and an entity are DIFFERENT things, and a flat field list is
 * the one presentation that erases that.
 */

export interface ObjectRecordViewProps {
  row: ObjectRow | null;
  /** Jump to another workspace view — §69: no dead ends. */
  onGoToView?: (view: "graph" | "evidence" | "timeline") => void;
}

/* ── Shared field rendering ───────────────────────────────────────────── */

function Absent({ what }: { what?: string }) {
  return (
    <span className="ui-insp-unreported" data-testid="objects-absent">
      not reported{what !== undefined ? ` · ${what}` : ""}
    </span>
  );
}

function Reported({ children }: { children: React.ReactNode }) {
  return <span className="ui-insp-field-value">{children}</span>;
}

function Field({ label, children, mono = false }: { label: string; children: React.ReactNode; mono?: boolean }) {
  return (
    <div className="ui-insp-field">
      <span className="ui-insp-field-label">{label}</span>
      <span data-mono={mono ? "true" : undefined}>{children}</span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="ui-insp-section" data-testid={`objects-section-${title.toLowerCase().replace(/\s+/g, "-")}`}>
      <h4 className="ui-pane-title">{title}</h4>
      <div className="ui-insp-section-body">{children}</div>
    </section>
  );
}

/** A string, or the honest absence. The single path every string field uses. */
function text(value: string | null | undefined) {
  const trimmed = value === null || value === undefined ? null : value.trim();
  return trimmed === null || trimmed === "" ? <Absent /> : <Reported>{trimmed}</Reported>;
}

function number(value: number | null | undefined) {
  return typeof value === "number" ? <Reported>{value}</Reported> : <Absent />;
}

function list(values: ReadonlyArray<string>, emptyLabel: string) {
  if (values.length === 0) return <Absent what={emptyLabel} />;
  return (
    <span className="ui-insp-refs">
      {values.map((value) => (
        <span key={value} className="ui-obj-ref ui-mono">
          {value}
        </span>
      ))}
    </span>
  );
}

/* ── Identity, shared by every kind ───────────────────────────────────── */

function IdentitySection({ row }: { row: ObjectRow }) {
  return (
    <Section title="Identity">
      <Field label="kind">
        <Badge tone="neutral" role="classification" testId="objects-record-kind">
          {row.kind}
        </Badge>
      </Field>
      <Field label="identifier" mono>
        <Reported>{row.id}</Reported>
      </Field>
      <Field label="label">
        <Reported>{row.label}</Reported>
      </Field>
      <Field label="sub-label" mono>
        {row.sublabel === null ? <Absent /> : <Reported>{row.sublabel}</Reported>}
      </Field>
    </Section>
  );
}

function StatusSection({ row }: { row: ObjectRow }) {
  return (
    <Section title="Status">
      {/* Both vocabularies, always. The raw string is what the analyst filters
          on; `statusWord` is what the dot's colour means. Showing only the dot
          would make the mapping unauditable. */}
      <Field label="platform status" mono>
        <span className="ui-status" data-tone="dim">
          <StatusDot status={row.statusWord} testId={`objects-status-${row.id}`} />
          <span className="ui-status-label">{row.status ?? "not reported"}</span>
        </span>
      </Field>
      <Field label="projection" mono>
        <Reported>{row.statusWord}</Reported>
      </Field>
      <Field label="first instant" mono>
        {text(row.at)}
      </Field>
      <Field label="all instants" mono>
        {list(row.instants, "the platform reports no instant for this record")}
      </Field>
    </Section>
  );
}

function ProvenanceSection({ row, onGoToView }: { row: ObjectRow; onGoToView?: ObjectRecordViewProps["onGoToView"] }) {
  return (
    <Section title="Provenance">
      <Field label="sources" mono>
        {list(row.sourceIds, "no source registry id is attributed to this record")}
      </Field>
      <Field label="evidence records" mono>
        {number(row.evidenceCount)}
      </Field>
      <Field label="claims" mono>
        {number(row.claimCount)}
      </Field>
      {onGoToView !== undefined ? (
        <div className="ui-insp-next-list">
          <Button size="sm" icon="view-evidence" onClick={() => onGoToView("evidence")} data-testid="objects-goto-evidence">
            Show its evidence
          </Button>
          <Button size="sm" icon="view-timeline" onClick={() => onGoToView("timeline")} data-testid="objects-goto-timeline">
            Show on the timeline
          </Button>
          <Button size="sm" icon="view-graph" onClick={() => onGoToView("graph")} data-testid="objects-goto-graph">
            Show in the graph
          </Button>
        </div>
      ) : null}
    </Section>
  );
}

/* ── Entity (§6, §19) ─────────────────────────────────────────────────── */

function EntitySections({ row, onGoToView }: { row: Extract<ObjectRow, { kind: "Entity" }>; onGoToView?: ObjectRecordViewProps["onGoToView"] }) {
  const canonical = Object.entries(row.canonical);
  return (
    <>
      <Section title="Canonical identity">
        {canonical.length === 0 ? (
          <Field label="canonical">
            <Absent what="the platform sent an empty canonical_identity" />
          </Field>
        ) : (
          canonical.map(([key, value]) => (
            <Field key={key} label={key} mono>
              <Reported>{value}</Reported>
            </Field>
          ))
        )}
        <Field label="aliases" mono>
          {list(row.aliases, "no alias is reported")}
        </Field>
      </Section>

      <Section title="Materialisation">
        <Field label="continuity" mono>
          {text(row.continuity)}
        </Field>
        <Field label="first seen" mono>
          {text(row.firstSeen)}
        </Field>
        <Field label="last seen" mono>
          {text(row.lastSeen)}
        </Field>
        <Field label="history depth" mono>
          {number(row.historyDepth)}
        </Field>
      </Section>

      <Section title="Relationships">
        {row.relationships.length === 0 ? (
          <Absent what="the platform reports no relationship rows" />
        ) : (
          row.relationships.map((relationship, index) => (
            <Field key={`${relationship.type}-${relationship.target}-${index}`} label={relationship.type} mono>
              <Reported>
                {relationship.target}
                {relationship.status === null ? "" : ` · ${relationship.status}`}
              </Reported>
            </Field>
          ))
        )}
      </Section>

      <ProvenanceSection row={row} onGoToView={onGoToView} />
    </>
  );
}

/* ── Observation (§33) ────────────────────────────────────────────────── */

function ObservationSections({ row, onGoToView }: { row: Extract<ObjectRow, { kind: "Observation" }>; onGoToView?: ObjectRecordViewProps["onGoToView"] }) {
  return (
    <>
      <Section title="Record">
        <Field label="uri" mono>
          {text(row.uri)}
        </Field>
        <Field label="capture" mono>
          {text(row.captureId)}
        </Field>
        <Field label="locator" mono>
          {text(row.locator)}
        </Field>
        <Field label="record digest" mono>
          {text(row.recordDigest)}
        </Field>
        <Field label="content type" mono>
          {text(row.contentType)}
        </Field>
        <Field label="producer" mono>
          {text(row.runtimeProducer)}
        </Field>
        <Field label="immutable">
          {row.immutable ? <Reported>yes</Reported> : <Reported>no</Reported>}
        </Field>
      </Section>

      <Section title="Anchors">
        {list(row.anchorEntityIds, "no entity named this observation")}
      </Section>

      <ProvenanceSection row={row} onGoToView={onGoToView} />
    </>
  );
}

/* ── Claim (§34) ──────────────────────────────────────────────────────── */

function ClaimSections({ row, onGoToView }: { row: Extract<ObjectRow, { kind: "Claim" }>; onGoToView?: ObjectRecordViewProps["onGoToView"] }) {
  return (
    <>
      <Section title="Assertion">
        <Field label="predicate" mono>
          {text(row.predicate)}
        </Field>
        <Field label="subject" mono>
          {text(row.subjectRef)}
        </Field>
        <Field label="object" mono>
          {text(row.objectRef)}
        </Field>
        {row.roleBindings.length === 0 ? (
          <Absent what="no role binding is reported" />
        ) : (
          row.roleBindings.map((binding, index) => (
            <Field key={`${binding.role}-${index}`} label={binding.role} mono>
              <Reported>{binding.memberRef}</Reported>
            </Field>
          ))
        )}
      </Section>

      <Section title="Temporal scope">
        {/* An open bound reads "open", not a missing value: §99. */}
        <Field label="valid from" mono>
          {row.validFrom === null ? <Reported>open</Reported> : <Reported>{row.validFrom}</Reported>}
        </Field>
        <Field label="valid to" mono>
          {row.validTo === null ? <Reported>open</Reported> : <Reported>{row.validTo}</Reported>}
        </Field>
        <Field label="observed at" mono>
          {text(row.observedAt)}
        </Field>
        <Field label="published at" mono>
          {text(row.publishedAt)}
        </Field>
        <Field label="known from" mono>
          {text(row.knownFrom)}
        </Field>
        <Field label="known until" mono>
          {text(row.knownUntil)}
        </Field>
      </Section>

      <Section title="Validation">
        <Field label="evidence grade" mono>
          {text(row.evidenceGrade)}
        </Field>
        <Field label="confidence" mono>
          {row.confidence === null ? <Absent /> : <Reported>{row.confidence.toFixed(2)}</Reported>}
        </Field>
        <Field label="supersedes" mono>
          {text(row.supersedes)}
        </Field>
        <Field label="contradicts" mono>
          {list(row.contradicts, "no contradicting claim is reported")}
        </Field>
      </Section>

      <Section title="Derivation">
        <Field label="extraction" mono>
          {text(row.extractionVersion)}
        </Field>
        <Field label="normalisation" mono>
          {text(row.normalizationVersion)}
        </Field>
        <Field label="ontology" mono>
          {text(row.ontologyVersion)}
        </Field>
        <Field label="observations" mono>
          {list(row.observationRefs, "no observation backs this claim")}
        </Field>
      </Section>

      <ProvenanceSection row={row} onGoToView={onGoToView} />
    </>
  );
}

/* ── Finding (§35) ────────────────────────────────────────────────────── */

function FindingSections({ row, onGoToView }: { row: Extract<ObjectRow, { kind: "Finding" }>; onGoToView?: ObjectRecordViewProps["onGoToView"] }) {
  return (
    <>
      <Section title="Why detected">
        <Field label="summary">{text(row.summary)}</Field>
        <Field label="evidence resolves">
          {row.evidenceResolves ? <Reported>yes</Reported> : <Reported>no</Reported>}
        </Field>
      </Section>

      <Section title="Support">
        <Field label="claims" mono>
          {list(row.supportingClaimRefs, "no claim supports this finding")}
        </Field>
        <Field label="observations" mono>
          {row.observationRefs.length === 0 ? (
            <Absent />
          ) : (
            <span className="ui-insp-refs">
              {row.observationRefs.map((reference) => (
                <span key={reference.observationId} className="ui-obj-ref ui-mono">
                  {reference.observationId}
                  {reference.uri === "" ? "" : ` · ${reference.uri}`}
                </span>
              ))}
            </span>
          )}
        </Field>
        <Field label="entities" mono>
          {list(row.entityRefs, "no entity is named")}
        </Field>
        <Field label="structural signals" mono>
          {number(row.structuralSignalCount)}
        </Field>
        <Field label="semantic signals" mono>
          {number(row.semanticSignalCount)}
        </Field>
      </Section>

      <Section title="Analyst notes">
        {/* Always null today: §35 asks for notes and no endpoint serves them. The
            field exists so the gap is a VALUE rather than a missing section. */}
        {row.analystNotes === null ? (
          <Absent what="GET /findings/{id}/notes is not served" />
        ) : (
          <Reported>{row.analystNotes}</Reported>
        )}
      </Section>

      <ProvenanceSection row={row} onGoToView={onGoToView} />
    </>
  );
}

/* ── Capture (§33) ────────────────────────────────────────────────────── */

function CaptureSections({ row, onGoToView }: { row: Extract<ObjectRow, { kind: "Capture" }>; onGoToView?: ObjectRecordViewProps["onGoToView"] }) {
  return (
    <>
      <Section title="Target">
        <Field label="uri" mono>
          {text(row.targetUri)}
        </Field>
        <Field label="locator" mono>
          {text(row.locator)}
        </Field>
        <Field label="source family" mono>
          {text(row.sourceFamily)}
        </Field>
        <Field label="media type" mono>
          {text(row.mediaType)}
        </Field>
      </Section>

      <Section title="Capture">
        <Field label="content digest" mono>
          {text(row.contentDigest)}
        </Field>
        <Field label="fetched at" mono>
          {text(row.fetchedAt)}
        </Field>
        <Field label="time basis" mono>
          {text(row.timeBasis)}
        </Field>
      </Section>

      <ProvenanceSection row={row} onGoToView={onGoToView} />
    </>
  );
}

/* ── The pane ─────────────────────────────────────────────────────────── */

export function ObjectRecordView({ row, onGoToView }: ObjectRecordViewProps) {
  if (row === null) {
    return (
      <EmptyState
        size="sm"
        icon="view-objects"
        title="No object selected"
        description="Pick a row to read every field the platform reports for it. Fields the platform did not report are named rather than filled in."
        testId="objects-record-empty"
      />
    );
  }

  return (
    <div className="ui-obj-record ui-scroll" data-testid="objects-record" data-kind={row.kind}>
      <IdentitySection row={row} />
      <StatusSection row={row} />
      {row.kind === "Entity" ? <EntitySections row={row} onGoToView={onGoToView} /> : null}
      {row.kind === "Observation" ? <ObservationSections row={row} onGoToView={onGoToView} /> : null}
      {row.kind === "Claim" ? <ClaimSections row={row} onGoToView={onGoToView} /> : null}
      {row.kind === "Finding" ? <FindingSections row={row} onGoToView={onGoToView} /> : null}
      {row.kind === "Capture" ? <CaptureSections row={row} onGoToView={onGoToView} /> : null}
    </div>
  );
}

/** §92 projection, exported so a test can assert the mapping without the pane. */
export { toWorkStatus };