import type {
  CaptureRow,
  ClaimRow,
  EntityRow,
  FindingRow,
  ObjectRow,
  ObjectRowKind,
  ObservationRow,
} from "./types";

/**
 * Row projection (§25, §33, §34, §35, §99).
 *
 * Server records in, `ObjectRow`s out. This is the only place that decides what
 * a row says, and it decides it by READING the platform's fields — never by
 * inferring one from another.
 *
 * WHAT IS AVAILABLE, precisely, as of this pass:
 *
 *   Entity       ← `/entities/graph` (SpecOpsGraphNode). The canonical identity,
 *                  aliases, relationships and the materialisation projection are
 *                  all the platform's own.
 *   Observation  ← the observation ids and URIs the entity projection's
 *                  `evidence` / `timeline` arrays and `FindingView.observations`
 *                  name. Deduplicated by observation id across every entity that
 *                  anchors one: an observation two entities both reference is ONE
 *                  record, and listing it twice would overstate the base.
 *   Finding      ← `GET /findings`. The full record, including `why_detected`,
 *                  the supporting assertions, the observations, the sources and
 *                  the structural / semantic signal arrays.
 *   Claim        ← NOT SERVED. `GET /relations` does not exist, so Claim rows
 *                  are 0 and `OBJECT_COVERAGE_MISSING` says so. They are NOT
 *                  manufactured from relationship rows: `entity.relationships`
 *                  carries `{ type, target }` and no `relation_type` /
 *                  `subject_ref` / `object_ref`, so a Claim built from one would
 *                  be a model the platform does not have (§99).
 *   Capture      ← NOT SERVED. There is no capture list endpoint. The same
 *                  reasoning: an observation's `capture_id` is null because the
 *                  projection does not carry one, so there is nothing to key a
 *                  capture on.
 *
 * Both gaps are reported, not papered over. A table that showed two of five
 * kinds with a caption saying "five kinds" would be lying about coverage.
 */

export interface ProjectionEntity {
  entity_id: string;
  label?: string;
  canonical_identity?: Record<string, string>;
  relationships?: Array<Record<string, string>>;
  evidence?: Array<{ evidence_id: string; observation_id: string; immutable: boolean }>;
  timeline?: Array<{
    observation_id: string;
    uri: string;
    immutable: boolean;
    observed_at?: string;
    source_id?: string;
  }>;
  source_ids?: string;
  invariant_status?: string;
  invariant_continuity?: string;
  invariant_first_seen?: string;
  invariant_last_seen?: string;
  invariant_history_depth?: number | string;
}

export interface ObjectModelInput {
  entities: ReadonlyArray<ProjectionEntity>;
  findings: ReadonlyArray<ObjectFinding>;
  /** The investigation the rows belong to. Null ⇒ no rows are built at all. */
  investigationId: string | null;
}

export interface ObjectFinding {
  finding_id: string;
  status: string;
  why_detected: string;
  structural_evidence: Array<Record<string, unknown>>;
  semantic_evidence: Array<Record<string, unknown>>;
  supporting_graph_region: Record<string, unknown>;
  supporting_assertions: string[];
  observations: Array<{ observation_id: string; uri: string; immutable: boolean; observed_at?: string }>;
  sources: string[];
  evidence_resolves: boolean;
}

/** Endpoints this surface needs and the platform does not expose. */
export const OBJECT_COVERAGE_MISSING: ReadonlyArray<string> = [
  "GET /observations (an observation list; rows come from the entity projection's evidence/timeline arrays and from FindingView)",
  "GET /observations/{id}/record (the record's capture id, digest, producer and parser)",
  "GET /relations (Claim rows: relation_type, subject_ref, object_ref, valid_from/valid_to, evidence_grade)",
  "GET /captures and GET /captures/{id} (Capture rows: target_uri, media_type, fetched_at, time_basis)",
  "GET /findings/{id}/notes (analyst notes against a finding — §35 asks for them and nothing serves them)",
];

/* ── The builder ──────────────────────────────────────────────────────── */

export interface BuiltObjects {
  rows: ObjectRow[];
  /** `kind:id` → row, for O(1) selection lookup. */
  index: ReadonlyMap<string, ObjectRow>;
  counts: Record<ObjectRowKind, number>;
}

export function buildObjectModel(input: ObjectModelInput): BuiltObjects {
  const rows: ObjectRow[] = [];
  const index = new Map<string, ObjectRow>();
  const counts = emptyCounts();

  // Without an investigation there is nothing to scope rows to, and a table full
  // of tenant-wide objects presented as this investigation's is a false claim
  // about the record (§99). Callers render the no-investigation state instead.
  if (input.investigationId === null) {
    return { rows, index, counts };
  }

  const observations = buildObservations(input.entities);

  for (const entity of input.entities) {
    const row = entityRow(entity);
    push(rows, index, counts, row);
  }
  for (const observation of observations) {
    push(rows, index, counts, observation);
  }
  for (const finding of input.findings) {
    push(rows, index, counts, findingRow(finding));
  }

  return { rows, index, counts };
}

/** Row key. `kind:id`, so one platform id under two kinds cannot collide. */
export const rowKey = (kind: ObjectRowKind, id: string): string => `${kind}:${id}`;

function push(
  rows: ObjectRow[],
  index: Map<string, ObjectRow>,
  counts: Record<ObjectRowKind, number>,
  row: ObjectRow,
): void {
  const key = rowKey(row.kind, row.id);
  if (index.has(key)) return;
  index.set(key, row);
  rows.push(row);
  counts[row.kind] += 1;
}

export function emptyCounts(): Record<ObjectRowKind, number> {
  return { Entity: 0, Observation: 0, Claim: 0, Finding: 0, Capture: 0 };
}

/* ── Entity ───────────────────────────────────────────────────────────── */

function entityRow(entity: ProjectionEntity): EntityRow {
  const canonical = entity.canonical_identity ?? {};
  const identity = firstIdentity(canonical, entity.label);
  const aliasList = aliasesFrom(canonical, entity.label);
  const relationships = normaliseRelationships(entity.relationships ?? []);
  const instants = [entity.invariant_first_seen, entity.invariant_last_seen].filter(
    (value): value is string => typeof value === "string" && value !== "",
  );

  return {
    kind: "Entity",
    id: entity.entity_id,
    label: identity ?? entity.entity_id,
    sublabel: aliasList.length > 0 ? `${aliasList.length} aliases` : null,
    status: entity.invariant_status ?? null,
    statusWord: "Unknown",
    at: entity.invariant_last_seen ?? null,
    instants,
    sourceIds: sourceIdsFrom(entity.source_ids, aliasList, identity),
    evidenceCount: (entity.evidence ?? []).length,
    // The projection's relationship rows carry no claim id, so a claim count
    // here would be a guess. 0 with the relationship count beside it in the
    // detail pane is the honest pair.
    claimCount: 0,
    searchText: joinSearch([
      entity.entity_id,
      identity,
      aliasList.join(" "),
      Object.entries(canonical)
        .map(([key, value]) => `${key}=${value}`)
        .join(" "),
      entity.invariant_continuity ?? "",
      entity.invariant_status ?? "",
    ]),
    canonical,
    aliases: aliasList,
    relationships,
    continuity: entity.invariant_continuity ?? null,
    firstSeen: entity.invariant_first_seen ?? null,
    lastSeen: entity.invariant_last_seen ?? null,
    historyDepth: numeric(entity.invariant_history_depth),
  };
}

/** The first identity value, in the order `inspector/model.ts` already uses. */
function firstIdentity(canonical: Record<string, string>, fallback?: string): string | null {
  for (const key of ["account", "name", "label", "value"]) {
    const value = canonical[key];
    if (typeof value === "string" && value.trim() !== "") return value.trim();
  }
  return typeof fallback === "string" && fallback.trim() !== "" ? fallback.trim() : null;
}

/**
 * Aliases. Everything in `canonical_identity` that is not the value already used
 * as the name is an alias the platform reported. No alias is invented and none
 * is dropped silently: the count is what the detail pane shows.
 */
function aliasesFrom(canonical: Record<string, string>, label?: string): string[] {
  const name = firstIdentity(canonical, label);
  const out: string[] = [];
  for (const value of Object.values(canonical)) {
    if (typeof value !== "string" || value.trim() === "") continue;
    if (value.trim() === name) continue;
    out.push(value.trim());
  }
  return out;
}

function sourceIdsFrom(raw: string | undefined, aliases: string[], identity: string | null): string[] {
  const out = new Set<string>();
  if (typeof raw === "string" && raw.trim() !== "") out.add(raw.trim());
  for (const candidate of [identity, ...aliases]) {
    const host = hostOf(candidate);
    if (host !== null) out.add(host);
  }
  return [...out].sort();
}

/** The host of a URI or bare domain. Null when the value is unusable. */
export function hostOf(value: string | null | undefined): string | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (trimmed === "") return null;
  try {
    return new URL(trimmed).hostname.replace(/^www\./, "");
  } catch {
    // A bare domain or handle is a legitimate identity value. Treating it as one
    // is not an inference: it is the string the platform stored, lowercased.
    return /^[a-z0-9.-]+\.[a-z]{2,}$/i.test(trimmed) ? trimmed.toLowerCase() : null;
  }
}

interface NormalisedRelationship {
  type: string;
  target: string;
  status: string | null;
}

/**
 * Relationship rows, whether the projection sent them as JSON text, as an array,
 * or as one object. All three are read: guessing a single shape would silently
 * drop every relationship on the other two.
 */
export function normaliseRelationships(
  rows: ReadonlyArray<Record<string, string>>,
): NormalisedRelationship[] {
  const out: NormalisedRelationship[] = [];
  const push = (record: Record<string, unknown>): void => {
    if (typeof record["target"] !== "string" || typeof record["type"] !== "string") return;
    out.push({
      target: record["target"],
      type: record["type"],
      status: typeof record["status"] === "string" ? record["status"] : null,
    });
  };

  for (const row of rows) {
    if (typeof row["target"] === "string" && typeof row["type"] === "string") {
      push(row);
      continue;
    }
    const nested = row["relationships"];
    if (typeof nested !== "string") continue;
    let parsed: unknown;
    try {
      parsed = JSON.parse(nested);
    } catch {
      continue;
    }
    if (!Array.isArray(parsed)) continue;
    for (const entry of parsed) {
      if (typeof entry === "object" && entry !== null) push(entry as Record<string, unknown>);
    }
  }
  return out;
}

/* ── Observation ──────────────────────────────────────────────────────── */

/**
 * Observations from every array that names one, deduplicated by id.
 *
 * Enrichment, not replacement: the second mention of an observation may carry
 * the instant or the producer the first one lacked, and an observation is ONE
 * record, so the row keeps its identity and gains facts.
 */
export function buildObservations(entities: ReadonlyArray<ProjectionEntity>): ObservationRow[] {
  const accumulators = new Map<string, { anchors: string[]; row: ObservationRow }>();

  const consider = (
    observationId: string,
    uri: string | undefined,
    immutable: boolean,
    observedAt: string | undefined,
    anchorEntityId: string,
    fallbackSource: string | null,
  ): void => {
    if (observationId === "") return;
    const at = textOrNull(observedAt);
    const uriText = textOrNull(uri);
    const existing = accumulators.get(observationId);

    if (existing !== undefined) {
      if (!existing.anchors.includes(anchorEntityId)) existing.anchors.push(anchorEntityId);
      if (existing.row.uri === null && uriText !== null) existing.row.uri = uriText;
      if (existing.row.label === existing.row.id && uriText !== null) existing.row.label = uriText;
      if (existing.row.at === null && at !== null) existing.row.at = at;
      if (!existing.row.immutable && immutable) existing.row.immutable = true;
      if (fallbackSource !== null && !existing.row.sourceIds.includes(fallbackSource)) {
        existing.row.sourceIds.push(fallbackSource);
      }
      existing.row.instants = at !== null ? unique([...existing.row.instants, at]) : existing.row.instants;
      return;
    }

    const host = hostOf(uriText) ?? fallbackSource;
    accumulators.set(observationId, {
      anchors: [anchorEntityId],
      row: {
        kind: "Observation",
        id: observationId,
        label: uriText ?? observationId,
        sublabel: null,
        status: null,
        statusWord: "Unknown",
        at,
        instants: at !== null ? [at] : [],
        sourceIds: host !== null ? [host] : [],
        // The projection's `evidence` array is the platform's own count of the
        // records anchoring this entity; an observation's own evidence count is
        // not served, so this is 0 rather than a borrowed number.
        evidenceCount: 0,
        claimCount: 0,
        searchText: "",
        uri: uriText,
        captureId: null,
        locator: null,
        recordDigest: null,
        contentType: null,
        runtimeProducer: null,
        immutable,
        anchorEntityIds: [anchorEntityId],
      },
    });
  };

  for (const entity of entities) {
    const fallback = hostOf(entity.source_ids ?? undefined);
    for (const entry of entity.evidence ?? []) {
      consider(entry.observation_id, undefined, entry.immutable, undefined, entity.entity_id, fallback);
    }
    for (const entry of entity.timeline ?? []) {
      consider(
        entry.observation_id,
        entry.uri,
        entry.immutable,
        entry.observed_at,
        entity.entity_id,
        hostOf(entry.source_id) ?? fallback,
      );
    }
  }

  const out: ObservationRow[] = [];
  for (const entry of accumulators.values()) {
    entry.row.anchorEntityIds = entry.anchors.sort();
    entry.row.sourceIds = [...entry.row.sourceIds].sort();
    entry.row.searchText = joinSearch([
      entry.row.id,
      entry.row.uri ?? "",
      entry.row.locator ?? "",
      entry.row.contentType ?? "",
      entry.row.runtimeProducer ?? "",
      entry.row.sourceIds.join(" "),
    ]);
    out.push(entry.row);
  }
  return out.sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
}

/* ── Finding (§35) ────────────────────────────────────────────────────── */

/**
 * A finding as an analytical result.
 *
 * `title` is `why_detected` because `FindingView` has no separate name field:
 * §35 asks for a title and the platform's own account of why the finding fired
 * IS its title. Minting a second one would be a model the platform lacks.
 *
 * `analystNotes` is null, always, and it is typed. §35 asks for analyst notes;
 * no endpoint serves them against a finding, so the detail pane states the
 * missing endpoint rather than showing an empty notes box that reads as "this
 * finding has no notes" — which would be a false claim about the record (§99).
 */
function findingRow(finding: ObjectFinding): FindingRow {
  const observations = (finding.observations ?? []).map((entry) => ({
    observationId: entry.observation_id,
    uri: entry.uri,
    immutable: entry.immutable,
    at: textOrNull(entry.observed_at),
  }));
  const instants = observations.map((entry) => entry.at).filter((value): value is string => value !== null);
  const sources = [...new Set(finding.sources ?? [])].filter((value) => value !== "");
  const entityRefs = entityRefsFrom(finding);
  const claimRefs = (finding.supporting_assertions ?? []).filter((value) => value !== "");

  const sourceIds = unique([
    ...sources,
    ...entityRefs,
    ...observations.map((entry) => hostOf(entry.uri) ?? "").filter((value) => value !== ""),
  ]);

  return {
    kind: "Finding",
    id: finding.finding_id,
    label: finding.why_detected === "" ? finding.finding_id : finding.why_detected,
    sublabel: finding.finding_id,
    status: finding.status ?? null,
    statusWord: "Unknown",
    at: instants.length > 0 ? instants[instants.length - 1] : null,
    instants: unique(instants),
    sourceIds,
    evidenceCount: observations.length,
    claimCount: claimRefs.length,
    searchText: joinSearch([
      finding.finding_id,
      finding.why_detected,
      finding.status ?? "",
      sources.join(" "),
      entityRefs.join(" "),
      claimRefs.join(" "),
      ...observations.map((entry) => `${entry.observationId} ${entry.uri}`),
    ]),
    summary: finding.why_detected,
    evidenceResolves: finding.evidence_resolves === true,
    supportingClaimRefs: claimRefs,
    observationRefs: observations,
    entityRefs,
    sourceRefs: sources,
    structuralSignalCount: (finding.structural_evidence ?? []).length,
    semanticSignalCount: (finding.semantic_evidence ?? []).length,
    analystNotes: null,
  };
}

/**
 * The entities a finding concerns, as far as the record names them.
 *
 * `supporting_graph_region` is a free-form object; its values are only read as
 * entity ids when they LOOK like the ids the projection uses elsewhere in the
 * same payload, and anything else is left alone. Inventing entity references
 * from graph-region keys would be a claim the platform did not make.
 */
function entityRefsFrom(finding: ObjectFinding): string[] {
  const refs = new Set<string>();
  const region = finding.supporting_graph_region ?? {};
  const candidates: string[] = [];
  for (const value of Object.values(region)) {
    if (typeof value === "string") candidates.push(value);
    else if (Array.isArray(value)) {
      for (const entry of value) if (typeof entry === "string") candidates.push(entry);
    }
  }
  for (const candidate of candidates) {
    const trimmed = candidate.trim();
    if (trimmed === "") continue;
    if (trimmed.startsWith("ENT-") || trimmed.startsWith("ent-") || trimmed.startsWith("ENTITY:")) {
      refs.add(trimmed);
    }
  }
  return [...refs].sort();
}

/* ── Claim / Capture ──────────────────────────────────────────────────── */

/**
 * Claim rows. Zero today, and the count is a real zero rather than a placeholder.
 *
 * Exported so the detail pane and the tests can assert the shape a Claim row
 * WILL have, which is the §34 contract: predicate, participants, temporal scope,
 * status, validation, admission, evidence, derivation, projection. Built here so
 * the contract has one home rather than being written twice and drifting.
 */
export function claimRowFromRecord(record: ClaimProjection): ClaimRow {
  const validityInstants = [record.valid_from, record.valid_to].filter(
    (value): value is string => typeof value === "string" && value !== "",
  );
  const knownInstants = [record.observed_at, record.published_at, record.known_from, record.known_until].filter(
    (value): value is string => typeof value === "string" && value !== "",
  );

  return {
    kind: "Claim",
    id: record.relation_id,
    label: `${record.relation_type}: ${record.subject_ref} → ${record.object_ref}`,
    sublabel: record.relation_id,
    status: record.status ?? null,
    statusWord: "Unknown",
    at: record.observed_at ?? null,
    instants: unique([...validityInstants, ...knownInstants]),
    sourceIds: [],
    evidenceCount: record.observation_refs?.length ?? 0,
    claimCount: record.assertion_refs?.length ?? 0,
    searchText: joinSearch([
      record.relation_id,
      record.relation_type,
      record.subject_ref,
      record.object_ref,
      record.status ?? "",
      record.evidence_grade ?? "",
      ...(record.role_bindings ?? []).map((binding) => `${binding.role}=${binding.member_ref}`),
    ]),
    predicate: record.relation_type,
    subjectRef: record.subject_ref,
    objectRef: record.object_ref,
    roleBindings: (record.role_bindings ?? []).map((binding) => ({
      role: binding.role,
      memberRef: binding.member_ref,
    })),
    validFrom: record.valid_from ?? null,
    validTo: record.valid_to ?? null,
    observedAt: record.observed_at ?? null,
    publishedAt: record.published_at ?? null,
    knownFrom: record.known_from ?? null,
    knownUntil: record.known_until ?? null,
    evidenceGrade: record.evidence_grade ?? null,
    confidence: typeof record.confidence === "number" ? record.confidence : null,
    observationRefs: record.observation_refs ?? [],
    extractionVersion: record.extraction_version ?? null,
    normalizationVersion: record.normalization_version ?? null,
    ontologyVersion: record.ontology_version ?? null,
    contradicts: record.contradicts ?? [],
    supersedes: record.supersedes ?? null,
  };
}

/** The shape `GET /relations` is expected to return. Mirrors `ClaimRecord`. */
export interface ClaimProjection {
  relation_id: string;
  relation_type: string;
  subject_ref: string;
  object_ref: string;
  role_bindings?: Array<{ role: string; member_ref: string }>;
  valid_from?: string | null;
  valid_to?: string | null;
  observed_at?: string | null;
  published_at?: string | null;
  known_from?: string | null;
  known_until?: string | null;
  status?: string | null;
  evidence_grade?: string | null;
  confidence?: number | null;
  assertion_refs?: string[];
  observation_refs?: string[];
  extraction_version?: string | null;
  normalization_version?: string | null;
  ontology_version?: string | null;
  contradicts?: string[];
  supersedes?: string | null;
}

/** Capture rows, for the day `GET /captures` exists. Same reasoning as Claim. */
export function captureRowFromRecord(record: CaptureProjection): CaptureRow {
  return {
    kind: "Capture",
    id: record.capture_id,
    label: record.target_uri ?? record.capture_id,
    sublabel: record.capture_id,
    status: null,
    statusWord: "Unknown",
    at: record.fetched_at ?? null,
    instants: record.fetched_at ? [record.fetched_at] : [],
    sourceIds: record.source_id ? [record.source_id] : [],
    evidenceCount: 0,
    claimCount: 0,
    searchText: joinSearch([
      record.capture_id,
      record.target_uri ?? "",
      record.locator ?? "",
      record.media_type ?? "",
      record.source_family ?? "",
      record.content_digest ?? "",
    ]),
    sourceFamily: record.source_family ?? null,
    targetUri: record.target_uri ?? null,
    locator: record.locator ?? null,
    contentDigest: record.content_digest ?? null,
    mediaType: record.media_type ?? null,
    fetchedAt: record.fetched_at ?? null,
    timeBasis: record.time_basis ?? null,
  };
}

export interface CaptureProjection {
  capture_id: string;
  source_id?: string | null;
  source_family?: string | null;
  target_uri?: string | null;
  locator?: string | null;
  content_digest?: string | null;
  media_type?: string | null;
  fetched_at?: string | null;
  time_basis?: string | null;
}

/* ── Small helpers ────────────────────────────────────────────────────── */

export function textOrNull(value: string | null | undefined): string | null {
  if (value === null || value === undefined) return null;
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

function numeric(value: number | string | null | undefined): number | null {
  if (typeof value === "number") return value;
  if (typeof value === "string" && value.trim() !== "" && !Number.isNaN(Number(value))) {
    return Number(value);
  }
  return null;
}

function unique(values: ReadonlyArray<string>): string[] {
  return [...new Set(values)];
}

export function joinSearch(parts: ReadonlyArray<string | null>): string {
  return parts
    .filter((part): part is string => part !== null && part.trim() !== "")
    .join(" ")
    .toLowerCase();
}
