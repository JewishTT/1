# Contracts

The typed surface other layers must not bypass. Python contracts carry the dataclasses/enums;
the markdown contracts carry the prose contract; the root YAML/JSON carry request/response schemas.

## Python contracts

| Contract | Path | Classes | Functions |
|---|---|---|---|
| `canonical` | `apps/shared/contracts/canonical.py` | `CanonicalError`, `UnhashableForIdentity`, `_SelfCanonicalizing` | `normalize_instant`, `instant_text`, `_canonical_float`, `_enum_value`, `_normalize`, `_normalize_mapping`, `_mapping_key`, `_normalize_set` |
| `error_codes` | `apps/shared/contracts/error_codes.py` | `ErrorSurfaceError`, `CrossTenantIndistinguishabilityError`, `ErrorCategory`, `ErrorCode`, `ErrorEnvelope`, `EmptyStateEnvelope` | `is_release_blocker`, `release_blocker_codes`, `_reject_leaking_detail`, `_iter_strings`, `absence_envelope`, `cross_tenant_envelope` |
| `evidence_span` | `apps/shared/contracts/evidence_span.py` | `SpanContractError`, `SpanSemanticsMismatch`, `SelectorKind`, `CoordinateSystem`, `SelectorSemanticsVersion`, `SourceLocator`, `ResolvedRegion`, `StoredDocument` | `offset_vocabulary_agrees_with_runtime`, `_interval_overlaps`, `_selector_form`, `_selector_fields` |
| `operator_result` | `apps/shared/contracts/operator_result.py` | `OperatorResultError`, `ReplayMode`, `TimePrecision`, `OperatorIdentity`, `OperatorInputs`, `OperatorOutput`, `OperatorMethod`, `SourceTime` |  |
| `projection_manifest` | `apps/shared/contracts/projection_manifest.py` | `ProjectionKind`, `ProjectionStatus`, `ProjectionDeclarationError`, `Staleness`, `BuilderRef`, `ProjectionManifest` | `_canonical` |
| `stage_outcome` | `apps/shared/contracts/stage_outcome.py` | `StageOutcomeError`, `StageStatus`, `RetrySemantics`, `ErrorClass`, `BudgetLevel`, `EpistemicState`, `CoverageStatement`, `QuarantineRecord` |  |

## Contract documents

| Document | Path |
|---|---|
| `connector` | `apps/shared/contracts/connector.md` |
| `correlation-review` | `apps/shared/contracts/correlation-review.md` |
| `graph` | `apps/shared/contracts/graph.md` |
| `ontology-pack` | `apps/shared/contracts/ontology-pack.md` |
| `parser` | `apps/shared/contracts/parser.md` |
| `resolution-admission` | `apps/shared/contracts/resolution-admission.md` |
| `statement` | `apps/shared/contracts/statement.md` |
| `acquisition-worker` | `specs/001-global-osint-platform/contracts/acquisition-worker.md` |
| `graph` | `specs/001-global-osint-platform/contracts/graph.md` |
| `README` | `specs/001-global-osint-platform/contracts/README.md` |
| `resolution-admission` | `specs/001-global-osint-platform/contracts/resolution-admission.md` |
| `storage` | `specs/001-global-osint-platform/contracts/storage.md` |
| `utility-scorer` | `specs/001-global-osint-platform/contracts/utility-scorer.md` |
| `connector` | `specs/002-donor-pattern-integration/contracts/connector.md` |
| `correlation-review` | `specs/002-donor-pattern-integration/contracts/correlation-review.md` |
| `ontology-pack` | `specs/002-donor-pattern-integration/contracts/ontology-pack.md` |
| `parser` | `specs/002-donor-pattern-integration/contracts/parser.md` |
| `README` | `specs/002-donor-pattern-integration/contracts/README.md` |
| `statement` | `specs/002-donor-pattern-integration/contracts/statement.md` |
| `interface-contracts` | `specs/005-donor-core-subsystems/contracts/interface-contracts.md` |
| `ux-reference` | `specs/005-donor-core-subsystems/contracts/ux-reference.md` |
| `interface-contracts` | `specs/006-scientific-intelligence-fabric/contracts/interface-contracts.md` |
| `science-api` | `specs/006-scientific-intelligence-fabric/contracts/science-api.md` |
| `science-events` | `specs/006-scientific-intelligence-fabric/contracts/science-events.md` |
| `scope-boundary` | `specs/006-scientific-intelligence-fabric/contracts/scope-boundary.md` |
| `extractor-adapter` | `specs/007-deterministic-entity-extraction-stack/contracts/extractor-adapter.md` |
| `api` | `specs/008-discovery-search-fabric/contracts/api.md` |
| `events` | `specs/008-discovery-search-fabric/contracts/events.md` |
| `operations` | `specs/008-discovery-search-fabric/contracts/operations.md` |
| `service-contracts` | `specs/008-discovery-search-fabric/contracts/service-contracts.md` |
| `api` | `specs/014-temporal-materialization/contracts/api.md` |
| `events` | `specs/014-temporal-materialization/contracts/events.md` |
| `operations` | `specs/014-temporal-materialization/contracts/operations.md` |
| `service-contracts` | `specs/014-temporal-materialization/contracts/service-contracts.md` |
| `api` | `specs/015-worldline-reconstruction/contracts/api.md` |
| `events` | `specs/015-worldline-reconstruction/contracts/events.md` |
| `operations` | `specs/015-worldline-reconstruction/contracts/operations.md` |
| `service-contracts` | `specs/015-worldline-reconstruction/contracts/service-contracts.md` |
| `api` | `specs/016-relation-evidence-graph-fabric/contracts/api.md` |
| `events` | `specs/016-relation-evidence-graph-fabric/contracts/events.md` |
| `operations` | `specs/016-relation-evidence-graph-fabric/contracts/operations.md` |
| `service-contracts` | `specs/016-relation-evidence-graph-fabric/contracts/service-contracts.md` |
| `contracts` | `specs/025-context-reality-approximation-engine/contracts/contracts.md` |
| `specops-api` | `specs/027-ci-specops-fabric/contracts/specops-api.md` |
| `context-revision` | `specs/030-global-platform-upgrade/contracts/context-revision.md` |
| `errors` | `specs/030-global-platform-upgrade/contracts/errors.md` |
| `evidence-span` | `specs/030-global-platform-upgrade/contracts/evidence-span.md` |
| `obligation` | `specs/030-global-platform-upgrade/contracts/obligation.md` |
| `operator-result` | `specs/030-global-platform-upgrade/contracts/operator-result.md` |
| `projection-manifest` | `specs/030-global-platform-upgrade/contracts/projection-manifest.md` |
| `README` | `specs/030-global-platform-upgrade/contracts/README.md` |
| `stage-outcome` | `specs/030-global-platform-upgrade/contracts/stage-outcome.md` |
| `ghostline-api` | `specs/031-ghostline-vishing-fabric/contracts/ghostline-api.md` |
| `acquisition-task` | `specs/032-global-upgrade-execution/contracts/acquisition-task.md` |
| `conflict-record` | `specs/032-global-upgrade-execution/contracts/conflict-record.md` |
| `donor-registry` | `specs/032-global-upgrade-execution/contracts/donor-registry.md` |
| `evidence-seam` | `specs/032-global-upgrade-execution/contracts/evidence-seam.md` |
| `evidence-span` | `specs/032-global-upgrade-execution/contracts/evidence-span.md` |
| `operator-result` | `specs/032-global-upgrade-execution/contracts/operator-result.md` |
| `projection-manifest` | `specs/032-global-upgrade-execution/contracts/projection-manifest.md` |
| `README` | `specs/032-global-upgrade-execution/contracts/README.md` |
| `research-obligation` | `specs/032-global-upgrade-execution/contracts/research-obligation.md` |
| `resolution-decision` | `specs/032-global-upgrade-execution/contracts/resolution-decision.md` |
| `abstraction-manifest` | `specs/033-universal-context-runtime/contracts/abstraction-manifest.md` |
| `api-and-events` | `specs/033-universal-context-runtime/contracts/api-and-events.md` |
| `capability-manifest` | `specs/033-universal-context-runtime/contracts/capability-manifest.md` |
| `completion-report` | `specs/033-universal-context-runtime/contracts/completion-report.md` |
| `context-assembly-manifest` | `specs/033-universal-context-runtime/contracts/context-assembly-manifest.md` |
| `context-element` | `specs/033-universal-context-runtime/contracts/context-element.md` |
| `context-frame` | `specs/033-universal-context-runtime/contracts/context-frame.md` |
| `memory-layers` | `specs/033-universal-context-runtime/contracts/memory-layers.md` |
| `model-gateway` | `specs/033-universal-context-runtime/contracts/model-gateway.md` |
| `README` | `specs/033-universal-context-runtime/contracts/README.md` |

## Root schemas

| Schema | Path | Kind |
|---|---|---|
| `model-capabilities` | `contracts/model-capabilities.yaml` | schema |
| `source-policy-example` | `contracts/source-policy-example.yaml` | schema |
| `claim-extractor.input` | `contracts/schemas/claim-extractor.input.json` | json-schema |
| `claim-extractor.output` | `contracts/schemas/claim-extractor.output.json` | json-schema |
| `hypothesis.input` | `contracts/schemas/hypothesis.input.json` | json-schema |
| `hypothesis.output` | `contracts/schemas/hypothesis.output.json` | json-schema |
| `nl-query-compiler.input` | `contracts/schemas/nl-query-compiler.input.json` | json-schema |
| `nl-query-compiler.output` | `contracts/schemas/nl-query-compiler.output.json` | json-schema |
| `red-team.input` | `contracts/schemas/red-team.input.json` | json-schema |
| `red-team.output` | `contracts/schemas/red-team.output.json` | json-schema |
| `report-drafter.input` | `contracts/schemas/report-drafter.input.json` | json-schema |
| `report-drafter.output` | `contracts/schemas/report-drafter.output.json` | json-schema |
