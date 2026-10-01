/** Deterministic edge formation (W5 persistence — same input ⇒ same graph).
 *
 * Single source of truth for edge identity, dedupe and emit order across the
 * webapp graph builders (entityGraph, intelGraph). This is the frontend half of
 * **ADR-0023** (`docs/adr/0023-relation-identity-and-arity.md`); the rules
 * implemented here are a translation of the platform's already-tested Python
 * donor, not a second design:
 *
 * - `apps/shared/domain/relation_identity.py` — `canonical_material`,
 *   `digest128`, `RelationArityMode`, the per-mode participant canonicalisation
 *   and the `logical_relation_id` / `relation_id` split.
 * - `apps/shared/domain/observation_identity.py` — the schema-versioned
 *   observation address, reused for N-ary co-occurrence records.
 *
 * Two things the retired implementation got wrong, both now closed:
 *
 * 1. **Direction was destroyed.** Every pair was normalised through `min`/`max`
 *    for *all six* relation kinds, so `A works_for B` and `B works_for A` shared
 *    one id and the surviving edge stood for a statement nobody made. Arity is
 *    now declared per kind (`EDGE_ARITY`) and drives canonicalisation:
 *    `UNDIRECTED` sorts and dedupes its members, `DIRECTED` preserves
 *    `(subject, object)`. Only `co_occurrence` is undirected, because only there
 *    is the reverse the same assertion.
 * 2. **The digest was 32-bit FNV-1a.** Disqualified on arithmetic, not taste:
 *    `sqrt(2 · 2^32 · ln 2) ≈ 77,163` relations to a 50% collision probability,
 *    against a platform target of 10^7 — roughly 130× past a more-likely-than-not
 *    outcome. Identity is now `UI-` + 128-bit truncated SHA-256 over documented
 *    canonical material (`sqrt(2 · 2^128 · ln 2) ≈ 2.17e19`).
 *
 * FNV-1a is **retired for identity only** and retained for the layout seed, per
 * ADR-0023's explicit carve-out; `layoutSeed` is not an address and does not
 * need collision resistance. `graphState.ts` keeps its own copy for the view
 * fingerprint and the export checksum, likewise untouched — the duplicated
 * implementation is a recorded follow-up, not an oversight.
 *
 * N-ary observations are kept as one record and are never expanded implicitly.
 * A clique of pairwise edges is a *derived view* that the caller must ask for
 * (`pairwiseProjection`), so the assertion stays auditable as the thing that was
 * actually observed, and every projected edge names the record it came from.
 */

import { sha256HexOf } from "./sha256";

export type EdgeKind =
  | "assertion"
  | "evidence"
  | "possible_match"
  | "relationship"
  | "source_host"
  | "co_occurrence";

/**
 * Arity vocabulary, matching `RelationArityMode` in
 * `apps/shared/domain/relation_identity.py` character for character so the
 * canonical material serialises to the same bytes on both sides of the wire.
 * `nary` is unreachable through `EdgeKind` — the frontend declares no role
 * bindings — but it is part of the shared vocabulary, not a local invention.
 */
export type ArityMode = "undirected" | "directed" | "nary";

/**
 * Declared arity per relation kind. This is the registry ADR-0023's follow-up
 * section calls a hard precondition ("arity must be registered before any
 * extractor emits relations, or extraction will guess a mode per call site and
 * the identity space will fragment").
 *
 * `co_occurrence` is the single undirected kind: the assertion behind it is
 * "these two were observed in the same observation", which is true if and only
 * if its reverse is true, so sorting the pair *is* the correct canonical form.
 * Every other kind is directed — `relationship` carries an ontology predicate
 * (`works_for`, `owns`, `located_in`, `controls`, `reports_to`) whose reverse is
 * either false, meaningless, or an independently meaningful relation.
 */
export const EDGE_ARITY = {
  assertion: "directed",
  evidence: "directed",
  possible_match: "directed",
  relationship: "directed",
  source_host: "directed",
  co_occurrence: "undirected",
} as const satisfies Record<EdgeKind, ArityMode>;

/** Declared arity of one relation kind. */
export function arityOf(kind: EdgeKind): ArityMode {
  return EDGE_ARITY[kind];
}

/** Prefix for a pairwise relation's identity — this module's one id scheme. */
export const EDGE_ID_PREFIX = "UI-";

/** Prefix for an N-ary observation record. Distinct from `EDGE_ID_PREFIX` so a
 *  record and a pairwise edge over the same participants never share an id. */
export const OBSERVATION_ID_PREFIX = "UO-";

/**
 * Shape-version tag for observation material, following `IDENTITY_SCHEMA_V1` in
 * `apps/shared/domain/observation_identity.py`. The value goes *into* the
 * digest, so changing the shape genuinely re-addresses every record instead of
 * silently reusing ids minted under the old shape.
 */
export const OBSERVATION_IDENTITY_SCHEMA = "ui-observation-identity/v1";

/**
 * Compare by Unicode code point, matching Python's `sorted()` on `str`.
 *
 * The default `Array.prototype.sort` comparator and the `<` operator both order
 * by UTF-16 code *unit*, which places astral-plane characters (surrogate pairs,
 * leading unit `0xD800`–`0xDBFF`) *before* U+E000–U+FFFF instead of after. Two
 * sides of the wire sorting the same participant list differently would produce
 * two identities for one relation — the exact cross-language skew ADR-0023
 * exists to remove, one layer below the UTF-8 byte fix.
 */
function compareCodePoints(left: string, right: string): number {
  if (left === right) return 0;
  const a = Array.from(left);
  const b = Array.from(right);
  const shared = Math.min(a.length, b.length);
  for (let i = 0; i < shared; i += 1) {
    const x = a[i].codePointAt(0) as number;
    const y = b[i].codePointAt(0) as number;
    if (x !== y) return x < y ? -1 : 1;
  }
  if (a.length === b.length) return 0;
  return a.length < b.length ? -1 : 1;
}

/**
 * House canonical form — the JS rendering of
 * `json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`
 * from `relation_identity.canonical_material`.
 *
 * `JSON.stringify` already emits compact separators and, since ES2019's
 * well-formed stringify, escapes exactly the same characters Python does with
 * `ensure_ascii=False`: `"` and `\`, the short escapes `\b \f \n \r \t`, other
 * control characters as `\u00xx`, and no non-ASCII at all — so the UTF-8 bytes
 * that reach the digest are the bytes Python would hash. Keys are sorted by code
 * point rather than by insertion or by UTF-16 unit order.
 *
 * This is deliberately *not* `stableStringify` from `graphState.ts`: that one
 * sorts with the UTF-16 comparator, and importing it would couple the identity
 * primitive to a view-state module ADR-0023 explicitly keeps apart from it.
 * Identity material is restricted to strings and arrays of strings, so the two
 * known JSON divergences (float formatting, and Python's `str()` fallback for
 * non-serialisable leaves) cannot be reached from here.
 */
function canonicalMaterial(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalMaterial(item)).join(",")}]`;
  }
  if (value !== null && typeof value === "object") {
    const record = value as Record<string, unknown>;
    const keys = Object.keys(record).sort(compareCodePoints);
    return `{${keys
      .map((key) => `${JSON.stringify(key)}:${canonicalMaterial(record[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value) ?? "null";
}

/**
 * 128-bit truncated SHA-256 as 32 lowercase hex characters — the one id-producing
 * primitive, identical in meaning to `relation_identity.digest128`.
 *
 * The 128-bit truncation is a projection of SHA-256's 256-bit output, so the
 * best available attack on it is the birthday bound over 2^128, which is the
 * model the bound is computed from. That is the whole difference from the
 * retired 32-bit FNV-1a: FNV-1a is not merely narrow, it is invertible enough
 * that collisions are constructible in roughly 2^16 work — orders of magnitude
 * *below* even its own 2^32 space, so the "50% at 77,163" figure flatters it.
 */
function digest128(material: string): string {
  return sha256HexOf(material).slice(0, 32);
}

/**
 * Identity material of one pairwise relation, one shape per arity mode —
 * the translation of `relation_identity.logical_material`.
 *
 * `UNDIRECTED` → `{mode, type, members}` with members sorted and deduped, so
 * order and repeats cannot reach the digest. `DIRECTED` → `{mode, type,
 * subject, object}` with the caller's order preserved, which is the entire
 * point: `A works_for B` and `B works_for A` now differ.
 *
 * `source` is the provenance anchor (correlation edge id, evidence id, host,
 * relationship type). The Python donor places provenance in *revision* material
 * because the backend mints two ids; the frontend has no revision channel, so it
 * folds the same information into the single id it mints. Same information, one
 * level lower — the alternative is a frontend edge that cannot distinguish two
 * claims that differ only in what they rest on.
 */
function edgeMaterial(
  a: string,
  b: string,
  kind: EdgeKind,
  source: string,
): Record<string, unknown> {
  const mode = arityOf(kind);
  if (mode === "undirected") {
    return { mode, type: kind, members: [...new Set([a, b])].sort(compareCodePoints), source };
  }
  return { mode, type: kind, subject: a, object: b, source };
}

/**
 * Content-addressed edge id: `UI-` + 32 lowercase hex, over the documented
 * canonical material of the relation's mode, type, canonical participants and
 * provenance source.
 *
 * Order-sensitive for every directed kind and order-insensitive for the one
 * undirected kind — see `EDGE_ARITY`. The retired implementation sorted *every*
 * pair through `min`/`max` and so could not express direction at all.
 */
export function makeEdgeId(nodeA: string, nodeB: string, kind: EdgeKind, source: string): string {
  return EDGE_ID_PREFIX + digest128(canonicalMaterial(edgeMaterial(nodeA, nodeB, kind, source)));
}

/** One primitive edge already derived from data (the caller holds the raw shape). */
export interface EdgeSeed {
  a: string;
  b: string;
  kind: EdgeKind;
  /** Provenance anchor: correlation edge id, evidence id, host, relationship type… */
  source: string;
  /** Human-readable label shown on the rendered edge. */
  reason?: string;
}

/** Co-mention/observation co-occurrence primitive: every node in `nodes` is conjoined with every other via one edge. */
export interface ObservationCoOccurrence {
  observation_id: string;
  /** Ordered set of node ids observed together (the observation is the anchor/source). */
  nodes: string[];
  /** Provenance-derived kind; defaults to `co_occurrence` when the data carries no explicit kind. */
  kind?: EdgeKind;
}

/** Normalized carrier consumed by `formEdges` — adapters map raw API shapes onto it. */
export interface EdgeFormationData {
  observations: ObservationCoOccurrence[];
  seeds: EdgeSeed[];
}

/** A fully-formed, content-addressed edge with deterministic emit order. */
export interface FormedEdge {
  id: string;
  source: string;
  target: string;
  kind: EdgeKind;
  reason: string;
  /** Set only on edges derived from a pairwise projection: the observation record's id. */
  derivedFrom?: string;
}

/**
 * One N-ary observation kept as a record. This is the assertion; the clique of
 * pairwise edges is a view of it, and each projected edge points back here.
 */
export interface FormedObservation {
  id: string;
  kind: EdgeKind;
  /** Canonical participant set: sorted, deduped. */
  participants: string[];
  source: string;
  reason: string;
}

/** How `formEdges` treats N-ary observations. */
export interface FormEdgeOptions {
  /**
   * Emit the pairwise clique of every observation record in addition to the
   * records themselves. Off by default: expansion is a *view*, and a caller that
   * did not ask for it should not receive a set of edges that nobody asserted.
   */
  pairwiseProjection?: boolean;
}

/** Both records and edges, each independently deduped and id-sorted. */
export interface FormEdgesResult {
  edges: FormedEdge[];
  observations: FormedObservation[];
}

/**
 * Content-addressed id of one N-ary observation record.
 *
 * Schema follows `observation_identity.ObservationIdentity`: the shape tag, the
 * kind, the canonical member set and the anchor are all in the material, so two
 * different observations of the same participants stay two observations, and a
 * change to this function's input shape re-addresses every record rather than
 * reusing ids minted under the old one.
 */
export function makeObservationId(
  kind: EdgeKind,
  participants: ReadonlyArray<string>,
  source: string,
): string {
  return (
    OBSERVATION_ID_PREFIX +
    digest128(
      canonicalMaterial({
        identity_schema: OBSERVATION_IDENTITY_SCHEMA,
        kind,
        members: [...new Set(participants)].sort(compareCodePoints),
        source,
      }),
    )
  );
}

/** One unordered participant pair, in the record's canonical member order. */
export interface CliquePair {
  a: string;
  b: string;
}

/**
 * The pairwise clique of one observation record: every unordered pair of its
 * canonical participants, ordered by the id the pair will be given, so a caller
 * can compare a projected edge list against this directly.
 *
 * The pair orientation follows the record's canonical (code-point sorted)
 * member order. For an undirected kind that orientation is immaterial — the id
 * sorts the pair itself. For a directed kind it is the projection's declared
 * reading, since the record asserts an unordered set and only the record's own
 * order can orient it.
 */
export function pairwiseCliqueProjection(record: FormedObservation): CliquePair[] {
  const members = record.participants;
  const pairs: Array<CliquePair & { id: string }> = [];
  for (let i = 0; i < members.length; i += 1) {
    for (let j = i + 1; j < members.length; j += 1) {
      const a = members[i];
      const b = members[j];
      pairs.push({ a, b, id: makeEdgeId(a, b, record.kind, record.source) });
    }
  }
  return pairs
    .sort((left, right) => (left.id < right.id ? -1 : left.id > right.id ? 1 : 0))
    .map(({ a, b }) => ({ a, b }));
}

/**
 * FNV-1a 32-bit — stable and dependency-free, and **not** an identity function.
 *
 * Retained for the layout seed only, per ADR-0023's carve-out: the seed is a
 * cosmetic input to a layout, not an address, and a collision there costs one
 * differently-seeded canvas. Its `811c9dc5` empty-string vector is a
 * non-identity vector and keeps passing unchanged.
 */
export function fnv1a(input: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < input.length; i += 1) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
    h >>>= 0;
  }
  return h >>> 0;
}

/** Stable node ordering: canonical id sort, order-invariant for the same set. */
export function orderNodeIds(nodes: ReadonlyArray<string>): string[] {
  return [...nodes].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
}

/** Fixed seed base — a NaN-looking play on 0x5EED, kept constant for W5 persistence. */
export const LAYOUT_SEED_BASE = 0x5eed;

/**
 * Stable layout seed derivation: hash-over-node-set (so it survives reordering
 * and reloads) falling back to a fixed constant for empty graphs. Used to key
 * deterministic layout geometry — same data ⇒ same canvas.
 */
export function layoutSeed(nodeIds: ReadonlyArray<string>): number {
  const sorted = orderNodeIds(nodeIds);
  if (sorted.length === 0) return LAYOUT_SEED_BASE;
  return (fnv1a(sorted.join("\u0000")) % 100000) + LAYOUT_SEED_BASE;
}

/**
 * Deterministic layout options for a given layout name. `cose` is forced to
 * `randomize: false` (initial geometry derived from the id-sorted node order)
 * and carries the node-set seed — deterministic when fed from deterministic
 * data; all other layouts are already canonical (grid/circle/concentric/
 * breadthfirst) and pass through unchanged.
 */
export function deterministicLayout(name: string, nodeIds: ReadonlyArray<string>): Record<string, unknown> {
  if (name === "cose") {
    return { name: "cose", randomize: false, randomSeed: layoutSeed(nodeIds) };
  }
  return { name };
}

/** Build one observation record, or null when it is not assertable as given. */
function formObservation(
  obs: ObservationCoOccurrence,
  known: ReadonlySet<string>,
): FormedObservation | null {
  // An unresolvable participant is not trimmed: a partial member set is a
  // *different* set, and minting an id for it would put a false relation in the
  // graph under a true-looking address. The record is dropped instead.
  if (obs.nodes.some((node) => !known.has(node))) return null;
  const participants = [...new Set(obs.nodes)].sort(compareCodePoints);
  // Two or fewer distinct known participants: nothing was co-observed.
  if (participants.length < 2) return null;
  const kind = obs.kind ?? "co_occurrence";
  return {
    id: makeObservationId(kind, participants, obs.observation_id),
    kind,
    participants,
    source: obs.observation_id,
    reason: obs.observation_id,
  };
}

/**
 * Deterministic edge factory over normalized data.
 *
 * N-ary observations become records; explicit seeds become edges; self-loops and
 * edges with unknown endpoints are dropped; both collections are deduped by
 * their content-addressed id and emitted sorted by id.
 *
 * Dedupe is order-invariant in the payload as well as the id set. When two
 * primitives hash to one id they are the same relation, so the surviving label
 * is chosen by a documented rule — the lexicographically least canonical
 * payload — rather than by whichever arrived last. A last-writer-wins map would
 * make a label depend on adapter iteration order, which is exactly the
 * "same input ⇒ same graph" property this module exists to provide.
 *
 * Where a primitive and its own projection address the same relation, the
 * projected edge wins: the projection is the one that carries `derivedFrom`, and
 * dropping that would leave an edge with no route back to the record it came from.
 */
export function formEdges(
  nodes: ReadonlyArray<string>,
  data: EdgeFormationData,
  options: FormEdgeOptions = {},
): FormEdgesResult {
  const known = new Set(nodes);

  const observations = new Map<string, FormedObservation>();
  for (const obs of data.observations ?? []) {
    const record = formObservation(obs, known);
    if (record) observations.set(record.id, record);
  }

  // Canonicalise undirected orientation up front, so identity, payload and the
  // dedupe tiebreak all agree on which of a/b is which.
  const canonicalSeed = (seed: EdgeSeed) => {
    if (arityOf(seed.kind) !== "undirected" || seed.a < seed.b) return seed;
    return { ...seed, a: seed.b, b: seed.a };
  };

  const formed = new Map<string, FormedEdge>();
  const put = (edge: FormedEdge) => {
    formed.set(edge.id, edge);
  };

  const seeds = (data.seeds ?? []).map(canonicalSeed).sort((left, right) => {
    const a = canonicalMaterial({
      a: left.a,
      b: left.b,
      kind: left.kind,
      reason: left.reason ?? left.source,
      source: left.source,
    });
    const b = canonicalMaterial({
      a: right.a,
      b: right.b,
      kind: right.kind,
      reason: right.reason ?? right.source,
      source: right.source,
    });
    return compareCodePoints(a, b);
  });

  for (const seed of seeds) {
    if (seed.a === seed.b) continue;
    if (!known.has(seed.a) || !known.has(seed.b)) continue;
    const id = makeEdgeId(seed.a, seed.b, seed.kind, seed.source);
    if (formed.has(id)) continue;
    put({
      id,
      source: seed.a,
      target: seed.b,
      kind: seed.kind,
      reason: seed.reason ?? seed.source,
    });
  }

  if (options.pairwiseProjection) {
    for (const record of [...observations.values()].sort((a, b) => (a.id < b.id ? -1 : 1))) {
      for (const pair of pairwiseCliqueProjection(record)) {
        put({
          id: makeEdgeId(pair.a, pair.b, record.kind, record.source),
          source: pair.a,
          target: pair.b,
          kind: record.kind,
          reason: record.source,
          derivedFrom: record.id,
        });
      }
    }
  }

  const byId = (a: { id: string }, b: { id: string }): number =>
    a.id < b.id ? -1 : a.id > b.id ? 1 : 0;

  return {
    edges: [...formed.values()].sort(byId),
    observations: [...observations.values()].sort(byId),
  };
}
