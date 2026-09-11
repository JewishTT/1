# Interface Contracts: Donor Core Subsystems

**Date**: 2026-09-08 | **Feature**: [spec.md](spec.md)

Authoritative in-repo contract docs referenced where they already exist
(`apps/shared/contracts/statement.md`, `parser.md`, `resolution-admission.md`,
`correlation-review.md`, `connector.md`). New interfaces introduced below.

## 1. Parser Adapter (hardened) — `apps/shared/contracts/parser.md`

```python
@runtime_checkable
class ParserAdapter(Protocol):
    name: str
    content_types: list[str]
    def can_parse(self, artifact: Any) -> bool: ...
    def parse(self, artifact: Any) -> list[Finding]: ...
```

Hardening: adapters MUST tolerate size/time/depth ceilings (raised as
`ParserLimitError`) and MUST be deterministic (FR-009). Unknown formats are
quarantined, never parsed.

## 2. Knowledge Statement barrier

```python
def build_statement(*, schema_name: str, entity_id: str, properties: list[Property],
                    dataset_id: str, original_value: str, extraction_version: str,
                    valid_from: datetime | None = None) -> Statement
```

Invariants: provenance fields required (`StatementProvenanceError`);
unknown `schema_name` → `UnknownSchemaError`; `claimed=True` by default.
Every produced statement emits `statement.created` (payload = refs/fields).

## 3. Resolution Candidate

```python
def create_candidate(a: CandidateRecord, b: CandidateRecord, scored: ResolvedPair) -> Candidate
def decide_candidate(pair_key: str, decision: str, analyst_id: str, reasoning: str) -> ResolutionRecord
def reverse_resolution(pair_key: str) -> ResolutionRecord   # non-destructive
```

Events: `resolution.candidate_created`, `resolution.candidate_decided`.
Merge/reverse only append ResolutionRecords; entities never deleted.

## 4. Evidence Manifest

```python
def build_manifest(finding: Finding, observation_id: str, raw_sha256: str,
                   tenant_id: str) -> EvidenceManifest
```

Event: `evidence.manifest_created` (refs + sha256 only). Append-only, replayable.

## 5. Connector Module (behind AcquisitionWorker)

```python
class ConnectorModule(Protocol):
    name: str
    def capabilities(self) -> dict: ...
    def run(self, task, channel) -> None   # emits events to the task's shared channel
    def stop(self) -> None
```

Registration emits `connector.registered`; state changes emit
`connector.status_changed`. Events normalize via `shared/donor/target.py`.

## 6. Investigation monitor

```python
def update_monitor(investigation_id: str, counter: str, delta: int = 1) -> None   # atomic
def snapshot(investigation_id: str) -> dict   # persisted on close
```

Late events after COMPLETED → `governance.quarantined`, state never mutated.