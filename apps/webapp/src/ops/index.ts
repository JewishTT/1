/**
 * `src/ops` — the operational surfaces: Operations, Quarantine, Source Catalogue
 * (§46, §47, §48, §160, §192).
 *
 * WHY THIS IS A SEPARATE MODULE AND NOT THREE MORE WORKSPACE VIEWS.
 *
 * The analyst workspace (src/graph, src/evidence, src/timeline) answers *what do
 * these records mean*. This module answers *is the platform working, and what do
 * I do about the records it refused*. Those are different questions with different
 * readers, different vocabularies and different time horizons, and putting the
 * second one behind a view tab inside the first would make an operator's surface
 * look like part of an investigation — which is how an operator ends up reading a
 * tenant-wide failure rate as a statement about the case they are working.
 *
 * Layering, in the order the code reads:
 *   types.ts       the row vocabulary, and the `Unavailable` named-absence type
 *   fabric.ts      the five acquisition runtimes as ONE registry (§48)
 *   model.ts       pure derivations: pools → rows, metrics → signals, DLQ → rows
 *   useOpsState.ts server state (Query). Nothing here writes to the workspace store
 *   Operations / Quarantine / SourceCatalog — the three surfaces
 *
 * The module's discipline, restated once:
 *   §92  every status is a `WorkStatus`; unrecognised platform spellings become
 *        `Unknown`, never a new colour
 *   §99  a field the endpoint does not serve is `null` + the endpoint name. Never
 *        a zero, never a default, never a derived guess
 *   §90  an empty pane that reads as "nothing here" is a defect; a named absence
 *        is the correct rendering
 *   §69  no control that cannot succeed; where an endpoint is missing the surface
 *        says so instead of offering a button
 *   §70  no dashboard cards, no gauge cluster, no decorative chrome
 */

export {
  FABRIC_COVERAGE_MISSING,
  FABRIC_DECLARATIONS,
  connectorEcho,
  fabricRows,
  runtimeHintFor,
} from "./fabric";
export type { ConnectorWire, FabricDeclaration } from "./fabric";

export {
  SECTION_160_BLOCKERS,
  THRESHOLDS,
  blockerRows,
  buildOpsState,
  discoveryYieldRow,
  duplicateDeliveryState,
  formatBytes,
  lagRows,
  poolRows,
  queueRows,
  quarantineRows,
  splitFingerprint,
  storageRows,
  throughputRow,
  utilisationRow,
} from "./model";
export type { PoolWire, QuarantineWire } from "./model";

export { useCatalogState, useOpsState, useQuarantineState } from "./useOpsState";
export type { CatalogServerState, QuarantineServerState } from "./useOpsState";

export { OperationsWorkspace, formatSignalValue } from "./OperationsWorkspace";
export type { OperationsWorkspaceProps } from "./OperationsWorkspace";

export { ACKNOWLEDGE_MISSING, CellValue, QuarantineWorkspace } from "./QuarantineWorkspace";
export type { QuarantineWorkspaceProps } from "./QuarantineWorkspace";

export { SourceCatalog } from "./SourceCatalog";
export type { SourceCatalogProps } from "./SourceCatalog";

export { QUARANTINE_UNAVAILABLE, unavailable } from "./types";
export type {
  BlockerRow,
  ConnectorEcho,
  DuplicateDeliveryState,
  FabricRow,
  OpsServerState,
  QuarantineRow,
  SignalRow,
  SignalSeverity,
  Unavailable,
  WorkerPoolRow,
} from "./types";