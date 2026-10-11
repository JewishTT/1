/**
 * Dossier payload types — mirrors `GET /api/v1/dossier/{entity_ref}` exactly.
 *
 * Written against the live response rather than against the Python source, because a type
 * written from an implementation drifts from it silently and then the UI renders `undefined`
 * as a blank cell. Fields that can legitimately be absent are nullable; fields that are
 * always present are not optional, so a shape change fails the compiler here instead of
 * showing an analyst an empty table.
 *
 * `candidate_source_names` is API-layer sugar: the dossier core emits content-addressed
 * source ids and knows nothing about the catalogue, so `routes/dossier.py` resolves them to
 * names at the boundary. The raw ids stay in the payload for anything that needs to address
 * a source directly.
 */

export type CoverageState = "unknown" | "acquired" | "empty" | "conflict" | "refused";

export interface Saturation {
  total: number;
  acquired: number;
  empty: number;
  conflict: number;
  unknown: number;
  refused: number;
  corroborated: number;
  distinct_sources: number;
  ratio: number;
  saturated: boolean;
}

export interface CoverageView {
  plan_known: boolean;
  /** Null when no plan was supplied. Materially weaker than a plan that ran and found
   *  nothing, and rendered as "unknown", never as zero. */
  attributes: Saturation | null;
  traced_facts: number;
  total_facts: number;
  traced_edges: number;
  total_edges: number;
  traced_contacts: number;
  total_contacts: number;
  /** Lifecycle windows with no event, kept out of the timeline because nobody swept them. */
  dormant_windows: number;
  untraced_facts: number;
  untraced_edges: number;
  untraced_contacts: number;
  untraced_conflicts: number;
  untraced_total: number;
  traced_ratio: number;
  is_traceable: boolean;
}

export interface TimelineEntry {
  window_start: string;
  window_end: string;
  state: string;
  event_count: number;
  coverage: CoverageState;
  source_refs: string[];
}

export interface Link {
  source: string;
  target: string;
  kind: string;
  origin: string;
  weight: number | null;
  source_ref: string | null;
}

export interface LinkMap {
  subject: string;
  nodes: string[];
  degree: number;
  edges: Link[];
}

export interface ContactSide {
  value: string;
  sources: string[];
}

export interface ConflictSide {
  value: string;
  sources: string[];
}

export interface Conflict {
  subject: string;
  sides: ConflictSide[];
  sources: string[];
  note: string;
}

export interface Gap {
  attribute: string;
  candidate_sources: string[];
  blocked_sources: string[];
  candidate_source_names: string[];
  blocked_source_names: string[];
}

export interface ContactSet {
  kinds: string[];
  contacts: Array<{ kind: string; value: string; sources: string[] }>;
}

export interface DossierIdentity {
  entity_ref: string;
  type_label: string;
  stream_anchor: string;
  revision: number;
}

export interface Dossier {
  dossier_id: string;
  identity: DossierIdentity;
  is_empty: boolean;
  is_complete: boolean;
  timeline: TimelineEntry[];
  links: LinkMap;
  contacts: ContactSet;
  coverage: CoverageView;
  gaps: Gap[];
  conflicts: Conflict[];
}

/** One source's outcome within a sweep, including the ones that did not answer. */
export interface SourceReport {
  source: string;
  attribute: string;
  outcome: string;
  status: number;
  records: number;
  bytes: number;
  detail: string;
}

export type RefusalReason = "echo" | "shape";

export interface Refusal {
  source: string;
  attribute: string;
  reason: RefusalReason | string;
  detail: string;
}

export interface Discovered {
  entity_ref: string;
  type_label: string;
  canonical: string;
  found_by: string;
  observation_ref: string;
}

export interface EnrichResult {
  query: string;
  entity_ref: string;
  type_label: string;
  sources_called: number;
  known_attributes: string[];
  invariant_error: string;
  dossier: Dossier | null;
  reports: SourceReport[];
  refusals: Refusal[];
  discovered: Discovered[];
}

export interface SubjectSummary {
  entity_ref: string;
  events: number;
  first_seen: string | null;
  last_seen: string | null;
}
