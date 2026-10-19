# Contract 08 — `ProjectionManifest` (delta)

**Feature**: `032-global-upgrade-execution`
**Governs**: what every rebuildable projection must be able to prove about itself.
**Enforces**: FR-006, FR-007; SC-009; blueprint §2, §7.

**Canonical definition**: `specs/030-global-platform-upgrade/contracts/projection-manifest.md`. This
file records the fields and behaviours Feature 032 adds, and the one prohibition that matters most:
a stale projection may not silently satisfy an obligation.

---

## Delta against 030

| # | Added obligation | Source | Why |
|---|---|---|---|
| D1 | `source_cut` is an explicit canonical-stream position — a knowledge-time watermark — not "whatever was in the store" | §2, §7 | rebuild parity is impossible without a declared cut |
| D2 | `staleness` is a structured value: lag from the cut, whether the lag is within SLO, and the reason if not | §2, SC-009 | "stale" without a magnitude cannot drive a decision |
| D3 | `kill_switch` is a tested route, exercised in CI, not a documented intention | §2, FR-006 | an untested kill switch is a hope |
| D4 | `rebuild_route` names the command and the artifact it must reproduce, with its digest | §2, SC-009 | a rebuild nobody can run is not a rebuild |
| D5 | Obligation evaluation consults the manifest and treats a stale satisfying projection as insufficient unless the staleness is explicitly accepted | §9.3, SC-009 | the quiet failure mode of every projection-backed claim |
| D6 | `builder_version` and `operator_versions[]` are recorded so a projection can be attributed to the code that produced it | §2 | a projection without provenance cannot be re-derived |

## Shape

```text
ProjectionManifest
├── identity
│   ├── projection_id          REQUIRED
│   ├── tenant_scope           REQUIRED   global | per-tenant | hybrid
│   └── kind                   REQUIRED   search | graph | metrics | timeline | spatial |
│                                          tda | report | other
├── inputs
│   ├── source_cut             REQUIRED   canonical stream position + knowledge-time watermark
│   ├── input_digests[]        REQUIRED   the digests of the inputs actually consumed
│   └── offsets                REQUIRED   per-source offsets, not a single global counter
├── build
│   ├── builder_version        REQUIRED
│   ├── operator_versions[]    REQUIRED
│   ├── built_at               REQUIRED
│   └── duration               REQUIRED
├── output
│   ├── output_digest          REQUIRED   deterministic over canonical ordering
│   └── output_location        REQUIRED
├── health
│   ├── staleness              REQUIRED   { lag_seconds, within_slo, reason_if_not }
│   ├── status                 REQUIRED   fresh | stale | rebuilding | failed | disabled
│   └── last_successful_build  REQUIRED
└── operations
    ├── rebuild_route          REQUIRED   command + expected digest
    ├── kill_switch            REQUIRED   tested disable route
    └── owner                  REQUIRED
```

---

## Normative rules

### R1 — A projection is never a source of truth

The canonical stream is authoritative. A projection is a rebuildable serving or computation artifact.
Mathematically identical content is still not authority, and a projection that disagrees with the
stream is wrong by definition.

### R2 — Freshness is declared on every response

A query answered from a projection reports the `source_cut` and the `staleness` it used. A response
without that declaration is not admissible for a decision (blueprint §30.1).

### R3 — Rebuild parity is a test

Deleting and rebuilding from the declared cut must reproduce `output_digest`. A rebuild that
produces a different digest is a defect in the builder, the ordering or the determinism — not a
reason to update the digest.

### R4 — The kill switch is exercised

CI disables each projection and asserts that the platform degrades explicitly — an error or a
declared unavailability — rather than silently serving the disabled projection's last output.

### R5 — Stale cannot satisfy

An obligation may only be satisfied by a projection-backed fact when the manifest's staleness is
within the declared bound, or when an explicit staleness acceptance is recorded with an actor and a
reason.

### R6 — One production owner per projection

Two builders for one projection is two truths in one place. WP0's owner map resolves the duplicate
and the losing route is removed with a record.

---

## Prohibitions

- A projection with no manifest.
- A manifest with no tested rebuild route.
- A stale projection satisfying an obligation without an explicit acceptance.
- A projection writing back into the canonical stream.
- A second builder for a projection a different owner already produces.

---

## Tests

| Test | Asserts |
|---|---|
| `tests/integration/test_projection_rebuild_parity.py` | R3 |
| `tests/integration/test_projection_kill_switch.py` | R4 |
| `tests/integration/test_stale_projection_cannot_satisfy.py` | R5 |
| `tests/contract/test_projection_manifest.py::test_required_fields` | shape |
