/**
 * `src/evidence` — the evidence and lineage surface (§28–§34, §82).
 *
 * §82 is the constraint that shaped this module: evidence is a PEER of the
 * graph, not a detail panel hanging off it. So this is a two-pane work surface
 * with its own toolbar, its own states and its own query keys, and the viewer has
 * the same six-tab structure as every other surface.
 *
 * The two things worth knowing before reading the code:
 *
 *   rawPayload.ts   JSON/NDJSON/text with a position-tracking parse, so a line
 *                   can be traced to the observation that produced it. That
 *                   mapping is the feature — a highlighted text pane is not.
 *   lineage.ts      two chain types that cannot be concatenated, plus the
 *                   runtime assertion that proves it for data from the server.
 */

export {
  EVIDENCE_TABS,
  EVIDENCE_TAB_LABELS,
  EVIDENCE_TAB_SUPPORT,
  evidenceCounts,
  filterEvidence,
  sortEvidence,
} from "./types";
export type {
  EvidenceLocator,
  EvidencePayload,
  EvidenceQuery,
  EvidenceRow,
  EvidenceRowKind,
  EvidenceSort,
  EvidenceSortKey,
  EvidenceTab,
} from "./types";

export { EvidenceWorkspace } from "./EvidenceWorkspace";
export type { EvidenceWorkspaceProps } from "./EvidenceWorkspace";

export { RawViewer } from "./RawViewer";
export type { RawViewerProps } from "./RawViewer";

export { LineageViewer, LINEAGE_RUNG_ORDER } from "./LineageViewer";
export type { LineageViewerProps } from "./LineageViewer";

export {
  CHAIN_EXCLUSIVE_KINDS,
  DERIVATION_CHAIN_ID,
  DERIVATION_STEP_ORDER,
  EMPTY_LINEAGE,
  EVIDENCE_CHAIN_ID,
  EVIDENCE_STEP_ORDER,
  SHARED_KINDS,
  assertChainsSeparate,
  routeDerivationStep,
  routeEvidenceStep,
} from "./lineage";
export type {
  DerivationLineageChain,
  DerivationLineageStep,
  DerivationStepKind,
  EvidenceLineageChain,
  EvidenceLineageStep,
  EvidenceStepKind,
  LineageChainId,
  LineageModel,
  SeparationResult,
} from "./lineage";

export {
  buildDerivationChain,
  buildEvidenceChain,
  buildLineageModel,
  chainSummary,
} from "./lineageBuilder";
export type { DerivationChainInput, EvidenceChainInput } from "./lineageBuilder";

export {
  COLLAPSE_THRESHOLD,
  buildLineIndex,
  collapseLine,
  highlight,
  lineText,
  parseErrorFor,
  parsePointer,
  parsePositioned,
  resolveLine,
  resolveLineIndex,
  searchPayload,
  spanForPointer,
} from "./rawPayload";
export type {
  CollapsedLine,
  HighlightToken,
  LineIndex,
  LineMatch,
  LineResolution,
  LineSpan,
  ParseResult,
  PositionedValue,
  RawFormat,
  RawLocator,
  RawPayload,
  ResolvedLineIndex,
  SearchHit,
  TokenKind,
} from "./rawPayload";

export {
  EVIDENCE_COVERAGE_MISSING,
  rowsFromProjection,
  useEvidenceRecords,
  useSelectedEvidence,
} from "./useEvidenceRecords";
export type { EvidenceServerState, SelectedEvidence } from "./useEvidenceRecords";