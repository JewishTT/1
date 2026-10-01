import { toWorkStatus } from "../../ui/status";
import type { WorkspaceObjectKind, WorkspaceSelection } from "../types";
import type { EntityView, FindingView } from "../../lib/api";
import type {
  CaptureRecord,
  ClaimRecord,
  InspectorData,
  InspectorField,
  InspectorModel,
  InspectorSection,
  ObservationRecord,
  SourceRecord,
} from "./types";

/**
 * Object-driven inspector dispatch (§6, §19, §33, §34).
 *
 * `buildInspectorModel` is a pure function of (selection, data). That matters
 * for three reasons:
 *   - §68: the panel re-renders when the *selection* changes, not when any
 *     unrelated server payload lands.
 *   - it is directly testable, which is why the dispatch tests exist.
 *   - §99: because it is pure and field-for-field, it cannot quietly grow a
 *     semantic model of its own. Every branch names a platform record kind.
 *
 * §33 for an Observation: the panel must answer "where did this come from?" —
 * Observation ID, Capture, Source, Locator, Collected at, Content type, Digest,
 * Runtime, Parser, Processing state. All ten, always, in that order.
 *
 * §34 for a Claim: a claim is not a boolean. Predicate, participants, temporal
 * scope, status, validation, admission, evidence, derivation, projection.
 */

/** Sentinel for "the platform did not report this". Never an empty string. */
const NOT_REPORTED = null;

/** Explicitly render an unreported value rather than leaving the row blank. */
function field(
  key: string,
  label: string,
  value: InspectorField["value"],
  extra: Partial<InspectorField> = {},
): InspectorField {
  return { key, label, value, ...extra };
}

function text(value: string | null | undefined): string | null {
  if (value === null || value === undefined) return NOT_REPORTED;
  const trimmed = value.trim();
  return trimmed === "" ? NOT_REPORTED : trimmed;
}

function section(
  id: string,
  title: string,
  order: number,
  fields: InspectorField[],
  references?: InspectorSection["references"],
): InspectorSection {
  return references && references.length > 0 ? { id, title, order, fields, references } : { id, title, order, fields };
}

/* ── Observation (§33) ───────────────────────────────────────────────── */

export function observationSections(
  observation: ObservationRecord,
  capture: CaptureRecord | null,
  source: SourceRecord | null,
): InspectorSection[] {
  const sections: InspectorSection[] = [];

  // §33's ten required fields, in the directive's order, all in one section so
  // "where did this come from?" is answerable by reading downward.
  sections.push(
    section("provenance", "Provenance", 10, [
      field("observation-id", "Observation ID", text(observation.observation_id), { mono: true }),
      field("capture", "Capture", text(observation.capture_id), { mono: true }),
      field(
        "source",
        "Source",
        text(observation.source_id) ?? text(source?.source_id),
        { mono: true },
      ),
      field("locator", "Locator", text(observation.locator), { mono: true }),
      field("collected-at", "Collected at", text(observation.collected_at), { mono: true }),
      field("content-type", "Content type", text(observation.content_type), { mono: true }),
      field("digest", "Digest", text(observation.record_digest), { mono: true }),
      field(
        "runtime",
        "Runtime",
        observation.runtime_producer === null && observation.runtime_producer_version === null
          ? NOT_REPORTED
          : `${observation.runtime_producer ?? "?"} ${observation.runtime_producer_version ?? ""}`.trim(),
        { mono: true },
      ),
      field("parser", "Parser", text(observation.parser_hint), { mono: true }),
      field("processing-state", "Processing state", text(observation.lifecycle), { mono: true }),
    ]),
  );

  if (source) {
    sections.push(
      section("source", "Source", 20, [
        field("source-id", "Source ID", text(source.source_id), { mono: true }),
        field("source-name", "Name", text(source.name)),
        field("source-kind", "Kind", text(source.kind), { mono: true }),
        field("source-tenant", "Tenant", text(source.tenant_id), { mono: true }),
      ]),
    );
  }

  if (capture) {
    sections.push(
      section("capture", "Capture", 30, [
        field("capture-id", "Capture ID", text(capture.capture_id), { mono: true }),
        field("capture-source-family", "Source family", text(capture.source_family), { mono: true }),
        field("capture-target-uri", "Target URI", text(capture.target_uri), { mono: true }),
        field("capture-locator", "Locator", text(capture.locator), { mono: true }),
        field("capture-digest", "Content digest", text(capture.content_digest), { mono: true }),
        field("capture-media-type", "Media type", text(capture.media_type), { mono: true }),
        field("capture-fetched-at", "Fetched at", text(capture.fetched_at), { mono: true }),
        field("capture-time-basis", "Time basis", text(capture.time_basis), { mono: true }),
      ]),
    );
  }

  return sections;
}

/**
 * A Capture on its own. Deliberately *not* routed through `observationSections`:
 * a capture is a different record from an observation, and showing an
 * observation's field list against a capture would be exactly the kind of
 * semantic blur §99 forbids. The fields are the capture's own
 * (domain/capture.py) plus the source it came from.
 */
function captureModel(capture: CaptureRecord, source: SourceRecord | null): InspectorModel {
  return {
    kind: "Capture",
    id: capture.capture_id,
    title: text(capture.target_uri),
    subtitle: capture.capture_id,
    badges: [{ label: "capture", tone: "gold" }],
    sections: [
      section("capture", "Capture", 10, [
        field("capture-id", "Capture ID", text(capture.capture_id), { mono: true }),
        field("capture-source", "Source", text(capture.source_id), { mono: true }),
        field("capture-source-family", "Source family", text(capture.source_family), { mono: true }),
        field("capture-target-uri", "Target URI", text(capture.target_uri), { mono: true }),
        field("capture-locator", "Locator", text(capture.locator), { mono: true }),
        field("capture-digest", "Content digest", text(capture.content_digest), { mono: true }),
        field("capture-media-type", "Media type", text(capture.media_type), { mono: true }),
        field("capture-fetched-at", "Fetched at", text(capture.fetched_at), { mono: true }),
        field("capture-time-basis", "Time basis", text(capture.time_basis), { mono: true }),
      ]),
      ...(source
        ? [
            section("source", "Source", 20, [
              field("source-id", "Source ID", text(source.source_id), { mono: true }),
              field("source-name", "Name", text(source.name)),
              field("source-kind", "Kind", text(source.kind), { mono: true }),
              field("source-tenant", "Tenant", text(source.tenant_id), { mono: true }),
            ]),
          ]
        : []),
    ],
  };
}

function observationModel(
  observation: ObservationRecord,
  capture: CaptureRecord | null,
  source: SourceRecord | null,
): InspectorModel {
  const status = toWorkStatus(observation.lifecycle);
  return {
    kind: "Observation",
    id: observation.observation_id,
    // An observation has no human name in the platform; the URI is its face.
    title: text(observation.uri) ?? text(observation.observation_id),
    subtitle: observation.observation_id,
    badges: [
      { label: "observation", tone: "gold" },
      ...(text(observation.content_type) ? [{ label: observation.content_type as string, tone: "neutral" as const }] : []),
      ...(status !== "Unknown" ? [{ label: status, tone: "neutral" as const }] : []),
    ],
    sections: observationSections(observation, capture, source),
  };
}

/* ── Claim (§34) ─────────────────────────────────────────────────────── */

export function claimSections(claim: ClaimRecord): InspectorSection[] {
  const temporal =
    claim.valid_from === null && claim.valid_to === null
      ? NOT_REPORTED
      : `${claim.valid_from ?? "…"} → ${claim.valid_to ?? "…"}`;

  return [
    section("assertion", "Assertion", 10, [
      // §34: predicate, named as such. Not "relation" — the directive's word.
      field("predicate", "Predicate", text(claim.relation_type), { mono: true }),
      field("subject", "Subject", text(claim.subject_ref), { mono: true }),
      field("object", "Object", text(claim.object_ref), { mono: true }),
      ...claim.role_bindings.map((binding) =>
        field(`role-${binding.role}`, `Role · ${binding.role}`, text(binding.member_ref), { mono: true }),
      ),
      field("claim-id", "Claim ID", text(claim.relation_id), { mono: true }),
    ]),
    section("temporal", "Temporal scope", 20, [
      field("validity", "Valid", temporal, { mono: true }),
      field("observed-at", "Observed at", text(claim.observed_at), { mono: true }),
      field("published-at", "Published at", text(claim.published_at), { mono: true }),
      field("known-from", "Known from", text(claim.known_from), { mono: true }),
      field("known-until", "Known until", text(claim.known_until), { mono: true }),
    ]),
    section("status", "Status & admission", 30, [
      field("status", "Status", text(claim.status), { mono: true }),
      field("supersedes", "Supersedes", text(claim.supersedes), { mono: true }),
      field("contradicts", "Contradicts", claim.contradicts.length === 0 ? NOT_REPORTED : claim.contradicts.join(", "), {
        mono: true,
      }),
      field("investigation", "Investigation", text(claim.investigation_id), { mono: true }),
      field("candidate", "Candidate", text(claim.candidate_id), { mono: true }),
    ]),
    section("validation", "Validation", 40, [
      field("evidence-grade", "Evidence grade", text(claim.evidence_grade), { mono: true }),
      field("confidence", "Confidence", claim.confidence),
    ]),
    section("evidence", "Evidence", 50, [
      field("observations", "Observations", claim.observation_refs.length, {
        linkTo: claim.observation_refs[0]
          ? { kind: "Observation", id: claim.observation_refs[0] }
          : undefined,
      }),
      field("assertions", "Assertions", claim.assertion_refs.length, {
        linkTo: claim.assertion_refs[0]
          ? { kind: "Claim", id: claim.assertion_refs[0] }
          : undefined,
      }),
    ]),
    section("derivation", "Derivation", 60, [
      field("extraction-version", "Extraction version", text(claim.extraction_version), { mono: true }),
      field("normalization-version", "Normalization version", text(claim.normalization_version), { mono: true }),
      field("ontology-version", "Ontology version", text(claim.ontology_version), { mono: true }),
    ]),
  ];
}

function claimModel(claim: ClaimRecord): InspectorModel {
  const contradicted = claim.contradicts.length > 0;
  return {
    kind: "Claim",
    id: claim.relation_id,
    title: `${claim.relation_type}: ${claim.subject_ref} → ${claim.object_ref}`,
    subtitle: claim.relation_id,
    badges: [
      { label: "claim", tone: "gold" },
      ...(text(claim.status) ? [{ label: claim.status, tone: "neutral" as const }] : []),
      // Red only where it is semantic: a recorded contradiction.
      ...(contradicted ? [{ label: "contradicted", tone: "danger" as const }] : []),
    ],
    sections: claimSections(claim),
  };
}

/* ── Entity (§6, §19) ────────────────────────────────────────────────── */

function entityName(entity: EntityView): string | null {
  const identity = entity.canonical_identity ?? {};
  for (const key of ["account", "name", "label", "value"]) {
    const candidate = text(identity[key]);
    if (candidate) return candidate;
  }
  return text(entity.aliases[0]) ?? null;
}

export function entitySections(entity: EntityView): InspectorSection[] {
  const identity = entity.canonical_identity ?? {};
  const invariant = entity.identity_invariant;
  const status = toWorkStatus(invariant?.status ?? null);

  return [
    section("identity", "Identity", 10, [
      field("entity-id", "Entity ID", text(entity.entity_id), { mono: true }),
      ...Object.entries(identity).map(([key, value]) =>
        field(`identity-${key}`, key, text(String(value)), { mono: true }),
      ),
    ]),
    section("aliases", "Aliases", 20,
      entity.aliases.length === 0
        ? [field("aliases-none", "Aliases", NOT_REPORTED)]
        : entity.aliases.map((alias: string, index: number) =>
            field(`alias-${index}`, `#${index + 1}`, text(alias), { mono: true }),
          ),
    ),
    section(
      "identifiers",
      "Identifiers",
      30,
      Object.keys(identity).length === 0
        ? [field("identifiers-none", "Identifiers", NOT_REPORTED)]
        : Object.entries(identity).map(([key, value]) =>
            field(`identifier-${key}`, key, text(String(value)), { mono: true }),
          ),
    ),
    section("relationships", "Relationships", 40,
      entity.relationships.length === 0
        ? [field("relationships-none", "Relationships", NOT_REPORTED)]
        : entity.relationships.map((rel: Record<string, string>, index: number) =>
            field(
              `relationship-${index}`,
              String(rel.kind ?? rel.type ?? `relation ${index + 1}`),
              text(String(rel.target ?? rel.object ?? "")) ?? "—",
              { mono: true },
            ),
          ),
    ),
    section("evidence", "Evidence", 50, [
      field("evidence-count", "Evidence records", entity.evidence.length),
      field("assertions", "Supporting assertions", entity.supporting_assertions.length, {
        linkTo: entity.supporting_assertions[0]
          ? { kind: "Claim", id: entity.supporting_assertions[0] }
          : undefined,
      }),
      field("correlations", "Correlations", entity.correlations?.length ?? 0),
    ]),
    section("observations", "Observations", 60,
      entity.timeline.length === 0
        ? [field("observations-none", "Observations", NOT_REPORTED)]
        : entity.timeline.slice(0, 20).map((entry: EntityView["timeline"][number], index: number) =>
            field(
              `observation-${index}`,
              entry.observed_at ?? entry.observation_id,
              text(entry.uri),
              {
                mono: true,
                linkTo: { kind: "Observation", id: entry.observation_id, label: entry.uri },
              },
            ),
          ),
    ),
    section("resolution", "Resolution", 70, [
      field("materialization", "Materialization", text(invariant?.status ?? null), { mono: true }),
      field("continuity", "Continuity", text(invariant?.continuity ?? null), { mono: true }),
      field("version", "Version", invariant?.version ?? NOT_REPORTED),
      field("history-depth", "History depth", invariant?.history_depth ?? NOT_REPORTED),
      field("identity-digest", "Identity digest", text(invariant?.identity_digest ?? null), { mono: true }),
      field("first-seen", "First seen", text(invariant?.first_seen ?? null), { mono: true }),
      field("last-seen", "Last seen", text(invariant?.last_seen ?? null), { mono: true }),
      field("resolution-state", "State", status === "Unknown" ? NOT_REPORTED : status),
    ]),
  ];
}

function entityModel(entity: EntityView): InspectorModel {
  const invariant = entity.identity_invariant;
  return {
    kind: "Entity",
    id: entity.entity_id,
    title: entityName(entity),
    subtitle: entity.entity_id,
    badges: [
      { label: "entity", tone: "gold" },
      ...(entity.aliases.length > 0
        ? [{ label: `${entity.aliases.length} aliases`, tone: "neutral" as const }]
        : []),
      ...(invariant?.continuity ? [{ label: invariant.continuity, tone: "accent" as const }] : []),
    ],
    sections: entitySections(entity),
  };
}

/* ── Finding (§6) ────────────────────────────────────────────────────── */

function findingModel(finding: FindingView, correlations: number): InspectorModel {
  const status = toWorkStatus(finding.status);
  return {
    kind: "Finding",
    id: finding.finding_id,
    title: text(finding.why_detected),
    subtitle: finding.finding_id,
    badges: [
      { label: "finding", tone: "gold" },
      ...(text(finding.status) ? [{ label: finding.status, tone: "neutral" as const }] : []),
      // Red is legitimate here: rejected evidence is a semantic failure state.
      ...(status === "Blocked" || status === "Failed"
        ? [{ label: status, tone: "danger" as const }]
        : []),
    ],
    sections: [
      section("finding", "Finding", 10, [
        field("finding-id", "Finding ID", text(finding.finding_id), { mono: true }),
        field("status", "Status", text(finding.status), { mono: true }),
        field("why-detected", "Why detected", text(finding.why_detected)),
        field("evidence-resolves", "Evidence resolves", finding.evidence_resolves),
      ]),
      section("evidence", "Evidence", 20, [
        field("observations", "Observations", finding.observations.length, {
          linkTo: finding.observations[0]
            ? { kind: "Observation", id: finding.observations[0].observation_id, label: finding.observations[0].uri }
            : undefined,
        }),
        field("sources", "Sources", finding.sources.length, {
          linkTo: finding.sources[0] ? { kind: "Source", id: finding.sources[0] } : undefined,
        }),
        field("structural-evidence", "Structural signals", finding.structural_evidence.length),
        field("semantic-evidence", "Semantic signals", finding.semantic_evidence.length),
        field("correlations", "Correlations", correlations),
      ]),
      section("support", "Support", 30, [
        field("assertions", "Supporting claims", finding.supporting_assertions.length, {
          linkTo: finding.supporting_assertions[0]
            ? { kind: "Claim", id: finding.supporting_assertions[0] }
            : undefined,
        }),
        field("graph-region", "Graph region entries", Object.keys(finding.supporting_graph_region ?? {}).length),
      ]),
    ],
  };
}

/* ── Investigation ────────────────────────────────────────────────────── */

function investigationModel(investigation: NonNullable<InspectorData["investigation"]>): InspectorModel {
  return {
    kind: "Investigation",
    id: investigation.investigation_id,
    title: text(investigation.name),
    subtitle: investigation.investigation_id,
    badges: [
      { label: "investigation", tone: "gold" },
      ...(text(investigation.state) ? [{ label: investigation.state, tone: "neutral" as const }] : []),
    ],
    sections: [
      section("investigation", "Investigation", 10, [
        field("investigation-id", "Investigation ID", text(investigation.investigation_id), { mono: true }),
        field("name", "Name", text(investigation.name)),
        field("state", "State", text(investigation.state), { mono: true }),
        field("policy", "Policy", text(investigation.policy_id), { mono: true }),
        field("tenant", "Tenant", text(investigation.tenant_id), { mono: true }),
        field("created-at", "Created at", text(investigation.created_at), { mono: true }),
        field("seeds", "Seeds", investigation.seeds.length),
      ]),
      section(
        "scope",
        "Scope & objective",
        20,
        Object.keys(investigation.scope ?? {}).length === 0 &&
          Object.keys(investigation.objective ?? {}).length === 0
          ? [field("scope-none", "Scope", NOT_REPORTED)]
          : [
              ...Object.entries(investigation.objective ?? {}).map(([key, value]) =>
                field(`objective-${key}`, key, text(JSON.stringify(value)), { mono: true }),
              ),
              ...Object.entries(investigation.scope ?? {}).map(([key, value]) =>
                field(`scope-${key}`, key, text(JSON.stringify(value)), { mono: true }),
              ),
            ],
      ),
    ],
  };
}

/* ── Dispatch ─────────────────────────────────────────────────────────── */

/**
 * The single entry point. Given a selection and the fetched bundle, produce
 * the panel model.
 *
 * When the selection is of a kind whose record has not been fetched, the model
 * says so explicitly via `status` rather than rendering an empty panel that
 * could be mistaken for "this object has nothing on it".
 */
export function buildInspectorModel(
  selection: WorkspaceSelection | null,
  data: InspectorData,
): InspectorModel & { unavailable: boolean } {
  if (!selection) {
    return { kind: null, id: null, title: null, subtitle: null, badges: [], sections: [], unavailable: false };
  }

  const byKind: Record<WorkspaceObjectKind, () => InspectorModel | null> = {
    Entity: () => (data.entity && data.entity.entity_id === selection.id ? entityModel(data.entity) : null),
    Observation: () =>
      data.observation && data.observation.observation_id === selection.id
        ? observationModel(data.observation, data.capture, data.source)
        : null,
    Capture: () =>
      data.capture && data.capture.capture_id === selection.id
        ? captureModel(data.capture, data.source)
        : null,
    Claim: () => (data.claim && data.claim.relation_id === selection.id ? claimModel(data.claim) : null),
    Finding: () =>
      data.finding && data.finding.finding_id === selection.id
        ? findingModel(data.finding, data.findingCorrelations.length)
        : null,
    Source: () =>
      data.source && data.source.source_id === selection.id
        ? {
            kind: "Source",
            id: data.source.source_id,
            title: text(data.source.name),
            subtitle: data.source.source_id,
            badges: [{ label: "source", tone: "gold" }],
            sections: [
              section("source", "Source", 10, [
                field("source-id", "Source ID", text(data.source.source_id), { mono: true }),
                field("source-name", "Name", text(data.source.name)),
                field("source-kind", "Kind", text(data.source.kind), { mono: true }),
                field("source-tenant", "Tenant", text(data.source.tenant_id), { mono: true }),
              ]),
            ],
          }
        : null,
    AcquisitionTask: () => null,
    AcquisitionRun: () => null,
    Investigation: () =>
      data.investigation && data.investigation.investigation_id === selection.id
        ? investigationModel(data.investigation)
        : null,
  };

  const model = byKind[selection.kind]();
  if (model) return { ...model, unavailable: false };

  return {
    kind: selection.kind,
    id: selection.id,
    title: selection.label ?? null,
    subtitle: selection.id,
    badges: [{ label: selection.kind.toLowerCase(), tone: "gold" }],
    sections: [],
    unavailable: true,
  };
}

/** Section ids in render order. */
export function sectionOrder(sections: InspectorSection[]): string[] {
  return [...sections].sort((a, b) => a.order - b.order).map((entry) => entry.id);
}

/** Look a section up by id, for the expand/collapse map. */
export function findSection(sections: InspectorSection[], id: string): InspectorSection | undefined {
  return sections.find((entry) => entry.id === id);
}