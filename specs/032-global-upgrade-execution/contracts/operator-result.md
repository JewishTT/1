# Contract 03 — `OperatorResult` (delta)

**Feature**: `032-global-upgrade-execution`
**Governs**: what every parser, extractor, normalizer, matcher and adapter returns.
**Enforces**: FR-014, FR-015; blueprint §4.1.

**Canonical definition**: `specs/030-global-platform-upgrade/contracts/operator-result.md`. That
document is authoritative for the envelope's shape. This file records only what Feature 032 adds and
what it forbids. Where the two differ, the stricter rule governs.

---

## Delta against 030

| # | Added obligation | Source | Why |
|---|---|---|---|
| D1 | `supersedes` and `superseded_by` are required for any re-run that produces a different output digest | §4.1, FR-015 | without it, a parser upgrade overwrites an interpretation |
| D2 | `input_spans[]` is required for every emitted candidate, not only for the artifact as a whole | §4.2, FR-016 | a candidate without its input span is ungrounded by construction |
| D3 | `partial_coverage` is a structured object (excluded regions, failed records, skipped pages), not a boolean | §4.1, FR-014 | "partial" that does not say *what* is partial cannot be evaluated |
| D4 | `result_kind` distinguishes six outcomes that must never collapse | §4.4, FR-022 | see the table below |
| D5 | `model_fingerprint` is required whenever a model contributed, including prompt template version | §4.1, §13 | LLM output is a derived artifact and must be replayable |
| D6 | `determinism` declares `deterministic`, `seeded` or `non_deterministic`, and a `non_deterministic` result may not be used where a deterministic result is required | §4.1, FR-014 | substituting an LLM for a parser is a semantic change, not an optimization |
| D7 | `resource_cost` records actual consumption against the operator's declared envelope | FR-014, FR-057 | cost accounting feeds the frontier's economics |

## The six result kinds (D4)

| `result_kind` | Meaning | What it must NOT be confused with |
|---|---|---|
| `parsed_with_candidates` | parse succeeded, candidates emitted | — |
| `parsed_empty` | parse succeeded, nothing in scope was found | `malformed`, `unsupported` |
| `partial` | parse succeeded on part of the input; the rest is declared | `parsed_empty` |
| `malformed` | the input could not be decoded per its declared format | `partial` |
| `unsupported` | this operator cannot express this input or request | `failed` |
| `timeout_or_resource_limit` | the operator hit its envelope | `failed` |
| `quarantine_or_security_refusal` | the input or output was refused on safety grounds | `malformed` |

An operator returns exactly one. The vocabulary is closed for the platform and every value must
survive storage, events, API, export and UI unchanged (FR-022, SC-007).

---

## Normative rules

### R1 — Nothing is rewritten in place

A re-run produces a **new** derived artifact. The previous result is retained, with `supersedes`
pointing forward and `superseded_by` pointing back. Raw bytes are never touched (FR-015, SC-005).

### R2 — Candidates carry their evidence

Every candidate carries the `EvidenceSpanRef` of the input that produced it, or is explicitly marked
`ungrounded` with a reason. There is no third state (FR-016, FR-018).

### R3 — Unknown is preserved

An unknown predicate, type, language or format is emitted as an open-world record with its raw
label and a mapping status — never dropped because the registry has no entry (FR-021).

### R4 — Determinism is declared honestly

`determinism: non_deterministic` is a legitimate value. What is forbidden is claiming determinism
for a model call, or using a non-deterministic operator where the contract requires a deterministic
result.

### R5 — The operator has no write privilege

An `OperatorResult` is returned to the caller; it is never accompanied by a side effect on a
canonical store. A donor adapter that writes during execution has violated this contract regardless
of what it returns (blueprint §8.7 condition 3).

### R6 — Status is distinguishable from success

A result with `partial` or `parsed_empty` is not an error, and neither is success. The consumer must
be able to branch on the status without parsing a message string.

---

## Prohibitions

- Returning `parsed_empty` when the real cause was `unsupported` or `malformed`.
- A `partial_coverage` boolean.
- Dropping a candidate because its predicate is unknown.
- A model call reported as `deterministic`.
- An adapter that writes to canonical state while returning an `OperatorResult`.

---

## Tests

| Test | Asserts |
|---|---|
| `tests/contract/test_operator_result.py::test_six_result_kinds_round_trip` | D4 |
| `tests/contract/test_operator_result.py::test_supersedes_on_rerun` | R1 |
| `tests/integration/test_operator_no_write_privilege.py` | R5 |
| `tests/golden/test_unknown_predicate_round_trip.py` | R3 |
