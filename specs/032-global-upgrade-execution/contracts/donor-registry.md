# Contract 09 — Donor Registry Entry and Promotion Gate

**Feature**: `032-global-upgrade-execution`
**Governs**: how a third-party capability is recorded, evaluated and promoted.
**Enforces**: FR-038…FR-045; SC-010; blueprint §8.1, §8.7.

---

## Why this contract exists

The blueprint's donor thesis is one sentence: *"Максимизируем извлекаемые проверяемые capabilities,
а не количество скопированных репозиториев"* (§8.1).

A donor is therefore not "a repo we depend on". It is a **capability claim** with a licence, an
upstream revision, an adapter, a measured gain and a disable route. The registry entry is where all
of that is recorded, and the promotion gate is where it is proven.

---

## Shape

```text
DonorRegistryEntry
├── identity
│   ├── capability_id            REQUIRED   the platform capability this provides
│   ├── donor_id                 REQUIRED   stable short name
│   ├── canonical_upstream_url   REQUIRED
│   ├── owner                    REQUIRED   the upstream or organisation
│   ├── pinned_revision          REQUIRED   commit SHA, tag or digest — never "main"
│   ├── verified_at              REQUIRED   when the pin was last checked
│   └── status                   REQUIRED   see the lifecycle below
├── licensing
│   ├── code_license             REQUIRED
│   ├── model_weights_license    REQUIRED   "none" is a value; "unknown" blocks promotion
│   ├── dataset_license          REQUIRED
│   ├── docs_license             REQUIRED
│   ├── sample_assets_license    REQUIRED
│   └── data_source_terms        REQUIRED   e.g. Common Crawl is terms-governed, not open
├── transfer
│   ├── transferred_paths[]      REQUIRED   the exact files or algorithms taken
│   ├── not_transferred[]        REQUIRED   what is deliberately left behind
│   ├── target_layer             REQUIRED
│   ├── target_contract_or_operator REQUIRED
│   ├── input_output_semantics   REQUIRED
│   ├── side_effects[]           REQUIRED   "none" is a value
│   └── access_needs[]           REQUIRED
├── integration
│   ├── adapter_path             REQUIRED   where the production adapter lives
│   ├── call_site                REQUIRED   the real caller, not a test
│   ├── feature_flag             REQUIRED
│   ├── kill_switch              REQUIRED   tested
│   ├── rollback_route           REQUIRED   tested
│   └── update_policy            REQUIRED
├── proof
│   ├── contract_test_ids[]      REQUIRED
│   ├── unit_test_ids[]          REQUIRED
│   ├── integration_test_ids[]   REQUIRED
│   ├── live_or_replay_test_ids[] REQUIRED
│   ├── e2e_test_id              REQUIRED
│   ├── benchmark_baseline       REQUIRED   the pre-donor measurement
│   ├── benchmark_result         REQUIRED   quality, cost, latency — `null` + reason if unmeasured
│   └── canonical_write_check    REQUIRED   proof that the adapter cannot write canonical state
└── classification
    ├── donor_class              REQUIRED   code | model | dataset | methodology_only | clean_room
    └── exclusion_reasons[]      OPTIONAL   why any part was refused
```

---

## Status lifecycle

```text
CANDIDATE -> AUDITED -> ADAPTED -> TESTED -> WIRED -> LIVE_PROVEN
     |           |          |          |         |          |
     +-----------+----------+----------+---------+----------> DEFERRED
     +-----------+----------+----------+---------+----------> REJECTED
     +-----------+----------+---------+---------------------> METHODOLOGY_ONLY
```

- `CANDIDATE` — discovered, nothing verified.
- `AUDITED` — licence and revision verified; transfer list written.
- `ADAPTED` — an adapter exists against the platform contract.
- `TESTED` — contract, unit and integration tests pass.
- `WIRED` — reachable from a production call path.
- `LIVE_PROVEN` — observed in operation with a measured gain and a proven disable route.
- `DEFERRED` — a stated reason and a revisit condition.
- `REJECTED` — a stated reason; the entry stays so the rejection is not re-litigated from memory.
- `METHODOLOGY_ONLY` — the idea is usable, the code is not.

`DEFERRED`, `REJECTED` and `METHODOLOGY_ONLY` are terminal for the current scope and remain visible.

---

## The ten-condition promotion gate (§8.7)

A donor reaches `LIVE_PROVEN` only when **all ten** hold:

1. upstream URL, commit and asset licence manifest complete;
2. an `OperatorResult` adapter exists;
3. no direct writes to canonical state (proven, not promised);
4. every output is linked to input observations and spans, or explicitly labelled partial;
5. failure, empty, unsupported, partial and timeout are distinguishable;
6. contract, unit, integration and live/replay tests pass;
7. the capability appears in an actual production call path;
8. quality, cost and latency gain versus baseline are measured on representative data;
9. disabling it resumes the prior path without deleting evidence;
10. owner, upgrade policy, monitoring and rollback are documented.

Failing any condition leaves the donor at the highest status it actually satisfies. There is no
partial promotion and no "promote now, document later".

---

## Per-donor dispositions recorded by this programme

| Donor | Disposition | Binding constraint |
|---|---|---|
| `semantica-agi/semantica` | conflict/fusion candidate | six-step extraction order (§8.5); `most_recent` rejected without validity semantics; voting counts lineage roots; no donor merger mutating canonical identity |
| `scalytics/kafSIEM` | pack-contract and analyst-workflow patterns | no SQLite store, no collector process, no independent entity types, no broker schema; resolve legacy CSS lineage first |
| `AEGiS` (ambiguous) | `UNVERIFIED / URL_REQUIRED` | must not be selected by name similarity; if the epistemic-governance project is intended, methodology-only adapter first |
| `aegisceo/phone-osint-framework` | registered but distinct | it is a phone-oriented module family, not a conflict engine |
| `JanusGraph` + ScyllaDB | architecture pattern | benchmark before migration; canonical truth does not move |
| Common Crawl / Wayback / WARC | archive capability | data terms reviewed separately; not a generic open licence |

---

## Prohibitions

- A registry entry pinned to a moving ref.
- Promotion with "unknown" asset licensing.
- An adapter with a canonical write path, regardless of a feature flag.
- A benchmark whose corpus, configuration or versions are not published.
- A donor whose disable test was never run.
- Selecting a donor by name similarity.

---

## Tests

| Test | Asserts |
|---|---|
| `tests/contract/test_donor_registry.py::test_every_entry_has_pin_and_licenses` | shape |
| `tests/integration/test_promotion_gate.py::test_all_ten_conditions_required` | gate |
| `tests/golden/test_donor_disable_preserves_evidence.py` | condition 9 |
| `tests/security/test_donor_cannot_write_canonical.py` | condition 3 |
