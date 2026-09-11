/**
 * Analyst review queue model (feature 005 US6).
 *
 * Attribution / license
 * =====================
 * Source: vitni (Apache-2.0) `app/renderer/src/features/review/reviewModel.ts` —
 * the review queue derivation/filter/sort/status logic is a faithful port.
 *
 * Adaptation notes
 * ================
 * - The donor's `@shared` / bridge / graph-snapshot imports are dropped; the
 *   record shapes are redefined locally (`ReviewAssertion`, `SourceRecord`,
 *   `GraphSnapshot`) with the same fields the functions read.
 * - `Confidence` is reused from the already-ported `./confidence` vocabulary.
 * - `stableSerialize` is kept verbatim: it is the grouping key that decides
 *   corroboration vs conflict.
 * - All functions are pure; empty/unknown inputs are tolerated (empty queue
 *   renders as an empty list, unknown ids fall back to their raw values).
 */

import type { Confidence } from "./confidence";

export type AssertionReviewState = "unreviewed" | "disputed" | "rejected" | "accepted";
export type ReviewEvidenceStatus = "none" | "single" | "multiple";
export type ReviewConflictStatus = "none" | "conflict";
export type ReviewSortMode = "unreviewed_first" | "newest" | "oldest" | "weakest_evidence";

export type ReviewFilters = {
  query: string;
  reviewState: "all" | AssertionReviewState;
  evidence: "all" | "none" | "weak";
  confidence: "all" | Confidence;
  sort: ReviewSortMode;
};

/** A reviewable assertion/claim row (adapted record — donor: ParsedAssertionRecord). */
export interface ReviewAssertion {
  id: string;
  subject_id: string;
  path: string;
  value: Record<string, unknown>;
  source_id?: string | null;
  review_state: AssertionReviewState;
  confidence: Confidence;
  created_at: number;
}

export interface SourceRecord {
  id: string;
  title?: string | null;
  display_name?: string | null;
  file_name?: string | null;
  locator?: string | null;
}

export interface GraphNode {
  id: string;
  label?: string | null;
}

export interface GraphSnapshot {
  nodes: GraphNode[];
}

export type DerivedReviewAssertion = ReviewAssertion & {
  subjectLabel: string;
  sourceTitle: string | null;
  supportingSourceCount: number;
  corroborationCount: number;
  evidenceStatus: ReviewEvidenceStatus;
  conflictStatus: ReviewConflictStatus;
  valueSummary: string;
};

export type DerivedNodeReviewStatus = {
  reviewTone: "clear" | "needs_review" | "conflict";
  evidenceTone: "supported" | "gap";
};

export const DEFAULT_REVIEW_FILTERS: ReviewFilters = {
  query: "",
  reviewState: "all",
  evidence: "all",
  confidence: "all",
  sort: "unreviewed_first",
};

function stableSerialize(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map((item) => stableSerialize(item)).join(",")}]`;
  const entries = Object.entries(value as Record<string, unknown>).sort(([left], [right]) =>
    left.localeCompare(right),
  );
  return `{${entries
    .map(([key, entryValue]) => `${JSON.stringify(key)}:${stableSerialize(entryValue)}`)
    .join(",")}}`;
}

function summarizeValue(value: Record<string, unknown>): string {
  const serialized = JSON.stringify(value);
  if (serialized.length <= 120) return serialized;
  return `${serialized.slice(0, 117)}...`;
}

export function buildDerivedReviewAssertions(
  assertions: ReviewAssertion[],
  sources: SourceRecord[],
  graph: GraphSnapshot,
): DerivedReviewAssertion[] {
  const sourceTitleMap = new Map<string, string>(
    sources
      .map(
        (source) =>
          [source.id, source.title || source.display_name || source.file_name || source.locator] as const,
      )
      .filter((entry): entry is readonly [string, string] => Boolean(entry[1])),
  );
  const nodeLabelMap = new Map(graph.nodes.map((node) => [node.id, node.label || node.id]));
  const groupedAssertions = new Map<string, ReviewAssertion[]>();

  assertions.forEach((assertion) => {
    const groupKey = `${assertion.subject_id}::${assertion.path}`;
    const current = groupedAssertions.get(groupKey) ?? [];
    current.push(assertion);
    groupedAssertions.set(groupKey, current);
  });

  return assertions.map((assertion) => {
    const groupKey = `${assertion.subject_id}::${assertion.path}`;
    const group = groupedAssertions.get(groupKey) ?? [];
    const ownValueKey = stableSerialize(assertion.value);
    const corroborating = group.filter(
      (candidate) => stableSerialize(candidate.value) === ownValueKey,
    );
    const conflicting = group.some((candidate) => stableSerialize(candidate.value) !== ownValueKey);
    const supportingSourceIds = new Set(
      corroborating
        .map((candidate) => candidate.source_id)
        .filter((sourceId): sourceId is string => Boolean(sourceId)),
    );
    const supportingSourceCount = supportingSourceIds.size;

    return {
      ...assertion,
      subjectLabel: nodeLabelMap.get(assertion.subject_id) || assertion.subject_id,
      sourceTitle: assertion.source_id ? sourceTitleMap.get(assertion.source_id) ?? null : null,
      supportingSourceCount,
      corroborationCount: Math.max(0, corroborating.length - 1),
      evidenceStatus:
        supportingSourceCount === 0
          ? "none"
          : supportingSourceCount === 1
            ? "single"
            : "multiple",
      conflictStatus: conflicting ? "conflict" : "none",
      valueSummary: summarizeValue(assertion.value),
    };
  });
}

export function filterReviewAssertions(
  items: DerivedReviewAssertion[],
  filters: ReviewFilters,
): DerivedReviewAssertion[] {
  const query = filters.query.trim().toLowerCase();
  const filtered = items.filter((item) => {
    if (filters.reviewState !== "all" && item.review_state !== filters.reviewState) return false;
    if (filters.evidence === "none" && item.evidenceStatus !== "none") return false;
    if (filters.evidence === "weak" && item.evidenceStatus === "multiple") return false;
    if (filters.confidence !== "all" && item.confidence !== filters.confidence) return false;
    if (!query) return true;

    return [item.path, item.subjectLabel, item.valueSummary, item.sourceTitle || ""]
      .join(" ")
      .toLowerCase()
      .includes(query);
  });

  const sortWeight = (item: DerivedReviewAssertion): number => {
    if (item.evidenceStatus === "none") return 0;
    if (item.evidenceStatus === "single") return 1;
    return 2;
  };

  filtered.sort((left, right) => {
    switch (filters.sort) {
      case "newest":
        return right.created_at - left.created_at;
      case "oldest":
        return left.created_at - right.created_at;
      case "weakest_evidence": {
        const evidenceDelta = sortWeight(left) - sortWeight(right);
        if (evidenceDelta !== 0) return evidenceDelta;
        return right.created_at - left.created_at;
      }
      case "unreviewed_first":
      default: {
        const leftPriority = left.review_state === "unreviewed" ? 0 : 1;
        const rightPriority = right.review_state === "unreviewed" ? 0 : 1;
        if (leftPriority !== rightPriority) return leftPriority - rightPriority;
        const evidenceDelta = sortWeight(left) - sortWeight(right);
        if (evidenceDelta !== 0) return evidenceDelta;
        return right.created_at - left.created_at;
      }
    }
  });

  return filtered;
}

export function buildNodeReviewStatusMap(items: DerivedReviewAssertion[]): Map<string, DerivedNodeReviewStatus> {
  const map = new Map<string, DerivedNodeReviewStatus>();

  const grouped = new Map<string, DerivedReviewAssertion[]>();
  items.forEach((item) => {
    const current = grouped.get(item.subject_id) ?? [];
    current.push(item);
    grouped.set(item.subject_id, current);
  });

  grouped.forEach((nodeItems, subjectId) => {
    const hasConflict = nodeItems.some(
      (item) =>
        item.review_state === "disputed" ||
        item.review_state === "rejected" ||
        item.conflictStatus === "conflict",
    );
    const hasReviewAttention = nodeItems.some((item) => item.review_state === "unreviewed");
    const hasEvidenceGap = nodeItems.some((item) => item.evidenceStatus === "none");

    map.set(subjectId, {
      reviewTone: hasConflict ? "conflict" : hasReviewAttention ? "needs_review" : "clear",
      evidenceTone: hasEvidenceGap ? "gap" : "supported",
    });
  });

  return map;
}

export function getAdjacentReviewAssertionId(
  items: DerivedReviewAssertion[],
  currentId: string | null,
  direction: "previous" | "next",
): string | null {
  if (items.length === 0) return null;
  if (!currentId) return items[0]?.id ?? null;
  const index = items.findIndex((item) => item.id === currentId);
  if (index === -1) return items[0]?.id ?? null;
  const nextIndex =
    direction === "next" ? Math.min(items.length - 1, index + 1) : Math.max(0, index - 1);
  return items[nextIndex]?.id ?? null;
}

export function getNextUnreviewedAssertionId(
  items: DerivedReviewAssertion[],
  currentId: string | null,
): string | null {
  const unreviewed = items.filter((item) => item.review_state === "unreviewed");
  if (unreviewed.length === 0) return null;
  if (!currentId) return unreviewed[0]?.id ?? null;
  const currentIndex = unreviewed.findIndex((item) => item.id === currentId);
  if (currentIndex === -1 || currentIndex === unreviewed.length - 1) return unreviewed[0]?.id ?? null;
  return unreviewed[currentIndex + 1]?.id ?? null;
}