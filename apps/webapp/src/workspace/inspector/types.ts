import type { Correlation, EntityView, FindingView, InvestigationView } from "../../lib/api";
import type { WorkspaceObjectKind } from "../types";

/**
 * Inspector record shapes (§33, §34).
 *
 * Field names mirror the platform's own domain records so nothing is renamed
 * on the way to the screen (§98):
 *   observation → observation_gate.py / domain/observation_identity.py
 *   claim       → domain/relation_claim.py (RelationClaim)
 *   capture     → domain/capture.py (Capture)
 *   finding     → FindingView, already typed in lib/api
 *
 * Every field is either a platform field, a platform identifier, or an explicit
 * `null` meaning "not reported". Nothing is inferred, defaulted or filled in:
 * an absent value renders as an explicit "not reported" row, never as a blank
 * and never as a plausible-looking default.
 *
 * §99, precisely: these types let the UI *show* that an observation, a claim
 * and an entity are different records. They do not give the frontend its own
 * semantic model.
 */

/**
 * One observation (§33). Field-for-field what the gate writes:
 *   observation_id, capture_id, locator, record_digest, content_type,
 *   runtime_producer(+_version), parser_hint, source_id, uri, lifecycle.
 */
export interface ObservationRecord {
  observation_id: string;
  /** The capture this observation was extracted from. Identity includes it. */
  capture_id: string | null;
  /** Provenance address inside the capture — never empty in practice. */
  locator: string | null;
  /** Content address of the record. Part of observation identity. */
  record_digest: string | null;
  content_type: string | null;
  runtime_producer: string | null;
  runtime_producer_version: string | null;
  /** Which parser is declared to read this record. */
  parser_hint: string | null;
  source_id: string | null;
  uri: string | null;
  /** When the observation entered the pipeline. Null ⇒ not reported. */
  collected_at: string | null;
  /** Lifecycle / processing state as the platform reports it. */
  lifecycle: string | null;
  tenant_id: string | null;
}

/** The Capture behind an observation (§33: "where did this come from?"). */
export interface CaptureRecord {
  capture_id: string;
  source_id: string | null;
  source_family: string | null;
  target_uri: string | null;
  locator: string | null;
  content_digest: string | null;
  media_type: string | null;
  fetched_at: string | null;
  /** `FETCH` / `WARC` / … the basis of the capture's timestamp. */
  time_basis: string | null;
}

/** The Source registry entry behind a capture. */
export interface SourceRecord {
  source_id: string;
  name: string | null;
  kind: string | null;
  tenant_id: string | null;
}

/**
 * A claim (§34). Deliberately NOT a boolean: it is a relation with a type,
 * ordered participants, a temporal scope, its own lifecycle, an evidence
 * grade, and a derivation trail.
 *
 * Field names are RelationClaim's own (`relation_type`, `subject_ref`,
 * `object_ref`, `valid_from`/`valid_to`, …), not a UI re-invention.
 */
export interface ClaimRecord {
  relation_id: string;
  /** The asserted predicate, e.g. `works_for`. */
  relation_type: string;
  /** Ordered participants: subject first, then object. Refs, never names. */
  subject_ref: string;
  object_ref: string;
  /** Role bindings for n-ary relations (RelationRoleBinding). */
  role_bindings: Array<{ role: string; member_ref: string }>;
  /** Temporal scope of the assertion. Null bounds mean "open". */
  valid_from: string | null;
  valid_to: string | null;
  /** When it was observed / published / known — distinct from validity. */
  observed_at: string | null;
  published_at: string | null;
  known_from: string | null;
  known_until: string | null;
  /** Validation: platform-reported grade + confidence. Null ⇒ not reported. */
  evidence_grade: string | null;
  confidence: number | null;
  /** Admission: the claim's lifecycle state. */
  status: string;
  /** Assertions that produced this claim. */
  assertion_refs: string[];
  /** Evidence: the observations this claim rests on. */
  observation_refs: string[];
  /** Derivation: which extraction/normalisation/ontology version produced it. */
  extraction_version: string | null;
  normalization_version: string | null;
  ontology_version: string | null;
  /** Contradictions recorded against this claim. */
  contradicts: string[];
  supersedes: string | null;
  investigation_id: string | null;
  candidate_id: string | null;
}

/** The whole server-side bundle the inspector may read. Never stored in Zustand (§7). */
export interface InspectorData {
  entity: EntityView | null;
  observation: ObservationRecord | null;
  capture: CaptureRecord | null;
  source: SourceRecord | null;
  claim: ClaimRecord | null;
  finding: FindingView | null;
  /** Correlations supporting the selected finding, when the view fetched them. */
  findingCorrelations: Correlation[];
  investigation: InvestigationView | null;
}

export const EMPTY_INSPECTOR_DATA: InspectorData = {
  entity: null,
  observation: null,
  capture: null,
  source: null,
  claim: null,
  finding: null,
  findingCorrelations: [],
  investigation: null,
};

/** One labelled row in an inspector section. */
export interface InspectorField {
  /** Stable key, also the test id: `inspector-field-<key>`. */
  key: string;
  label: string;
  /** `null` renders as an explicit "not reported" — never a blank row. */
  value: string | number | boolean | null;
  /** Monospace: ids, digests, timestamps, URIs, raw values. */
  mono?: boolean;
  /** Link target when this field addresses another workspace object (§69). */
  linkTo?: { kind: WorkspaceObjectKind; id: string; label?: string };
}

export interface InspectorSection {
  id: string;
  title: string;
  /** Section ordering is explicit so the panel does not depend on object shape. */
  order: number;
  fields: InspectorField[];
  /** Object ids referenced by this section, for the "go to" affordances. */
  references?: Array<{ kind: WorkspaceObjectKind; id: string; label?: string }>;
}

export interface InspectorModel {
  /** The kind actually resolved. `null` when nothing is selected. */
  kind: WorkspaceObjectKind | null;
  id: string | null;
  /** Object name as the platform reports it. Null when the platform has no name. */
  title: string | null;
  /** Short mono line under the title: the object's own identifier. */
  subtitle: string | null;
  /** Classification / provenance markers. Gold per §57 — metadata, not warning. */
  badges: Array<{ label: string; tone: "neutral" | "accent" | "gold" | "danger" | "analytical" }>;
  sections: InspectorSection[];
}