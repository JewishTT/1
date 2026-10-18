# ADR-030-09 — Copyleft is permitted through reviewed deployment; process separation is not a legal conclusion

- **Status**: Accepted
- **Date**: 2026-10-17
- **Feature**: `030-global-platform-upgrade`
- **Implements**: T024 (includes the T012 giotto-tda disposition)
- **Cites**: FR-113, FR-114, Constitution P13, ADR-0037 (`0037` is not related — see below), ADR-0010
- **Related**: ADR-030-05 (clean-room basis for fusion), ADR-030-06 (Splink deferral)

> **This ADR makes no legal determination and offers no legal advice.** It records an engineering
> deployment decision and the operational obligations that follow from it. Whether any particular
> distribution or deployment satisfies any particular licence is a question for qualified counsel, and
> this document does not answer it. Where it says "process separation", it means an architectural and
> operational arrangement the platform maintains — not a conclusion about what any licence requires.

## Context

The platform has copyleft dependencies. `research.md §2.9` lists the measured set: **giotto-tda is
AGPL-3.0**, Raphtory is GPL-3.0, Browsertrix is AGPL-3.0-or-later, and Phoenix is Elastic License 2.0
— *"source-available, not OSI."* The 029 donor matrix reached the same conclusion and, per
`research.md §2.9`, requires *"a documented deployment/compliance design for AGPL — not a blocker, but
a decision, not a default."*

The word that matters there is **default**. Copyleft in a dependency is not automatically a problem; an
*undisclosed* copyleft dependency with no recorded deployment model is. giotto-tda was exactly that:
declared as an `apps/projection` dependency with no recorded disposition anywhere.

**[MEASURED] The giotto-tda disposition has, in fact, been executed — and it was removal.**
`apps/projection/pyproject.toml:19-25` carries the record in the manifest itself:

> *giotto-tda REMOVED 2026-10-16. It was declared but had zero imports anywhere in the tree — not one
> `import giotto_tda`. Keeping it was not free: every giotto-tda release, including the current
> 0.6.2, hard-pins `scikit-learn==1.3.2`, which caps numpy at <2.0 workspace-wide. That single unused
> declaration blocked river>=0.26 (needs numpy>=2.2.5), scikit-learn 1.9 and the Splink 4 stack.
> specs/030 §2.9 already recorded giotto-tda as "a disposition, not an adoption"; this is that
> disposition, executed. If a second TDA engine is ever adopted, it must not reintroduce a hard
> numpy<2 pin.*

`gudhi>=3.10` remains at `:18` with its own note at `:17`: *"gudhi is the TDA path that is actually
called (tda/pipeline.py, tda/bridge.py)."* That claim is consistent with the measured gudhi imports at
`tda/__init__.py:196`, `tda/pipeline.py:35,94` and `tda/bridge.py:299,301,326`.

**[MEASURED] The AGPL dependency that is still in the tree is Browsertrix.**
`apps/acquisition/adapters/browsertrix/` exists with `__init__.py` and `collect.py`. T106 hardens it
rather than building a second crawler, and instructs that the *"AGPL-3.0-or-later deployment decision
in `donor-matrix.md`"* be recorded.

**[MEASURED] Splink is MIT and already carries its own deployment posture.**
`apps/admission/resolution/splink_adapter.py:5-8` records upstream, pinned revision 4.0.10, MIT
licence, and `Mode: B — upstream package behind a COGNITIVE contract`. ADR-030-06 governs it.

**[MEASURED]** `donors/registry.yaml` does not exist. There is no `benchmarks/` directory, so no
SBOM. FR-113 requires code licence, dependency licence, model weights, datasets, training data,
bundled binaries, documentation and sample assets to be *"inventoried separately"* — seven categories,
none of which currently has a machine-readable home.

**A terminology note.** `plan.md §Technical Context` cites ADR-0026 for the transport runtime. This ADR
cites no ADR for licensing because none exists; ADR-0037 in this repository is
`0037-ranking-policy-no-multiplicative-utility.md`, which is unrelated and is deliberately not invoked.

## Decision

**D1 — Copyleft is permitted.** AGPL and GPL components are not excluded from the platform. The
obligation is a **recorded, reviewed deployment model**, not a prohibition.

**D2 — The deployment model is recorded per component, before integration.** For every copyleft
dependency: which version is pinned, how it is deployed (in-process library, separately deployed
executable, sidecar service, worker pool), what the network boundary is, and who owns the operational
consequence. A copyleft dependency with no recorded deployment model is **refused at the registry**,
per FR-114's "recorded as unverified and MUST NOT be integrated on assumption".

**D3 — Process separation is an architectural arrangement, not a licence conclusion.** Where a component
is deployed as a separately executable or sidecar behind a versioned contract, the platform records
*that it does so*. It does not record that doing so satisfies, or fails to satisfy, any licence
obligation. **This ADR explicitly declines to make that determination.** Anyone reading this document to
conclude that sidecar deployment resolves AGPL obligations is reading more into it than it says.

**D4 — No vendor client or vendor type crosses a contract boundary into domain logic** (Constitution
V, restated). This is what makes D3's architectural arrangement real: a donor behind a contract is
reachable only as data.

**D5 — FR-113's seven asset categories are inventoried separately.** A repository's headline licence is
not assumed to cover model weights, datasets, bundled binaries or sample assets. Docling is the
recorded example: MIT code, model licences vary, and one model repository returned HTTP 401 during 029
verification — an unresolvable licence is `unverified`, not permissive.

**D6 — Unverified means unverified.** Where upstream identity, source or licence cannot be established,
the component is recorded `unverified` and is not integrated. This covers the nine non-existent names in
`donor-matrix.md §1` (ranknexus, fuse, QUANTA, IntelShed, worker-browser, Stablerank, OptLLM, lcc, nax)
and the four BLOCKED-licence cases (RCL with no licence at all; Common Crawl's data indemnity;
Phoenix under Elastic 2.0; Phoenix-adjacent Elastic-licensed sources).

**D7 — Copyleft is not a reason to skip hardening, and not a reason to skip a benchmark.** Browsertrix
is hardened in place (T106) and Docling is benchmarked against the current pipeline before promotion
(T107), irrespective of licence. The gate/identity deferral that holds Docling, GROBID, Splink,
Redpanda Connect, H3, DuckDB Spatial, OpenAleph and Browsertrix is a *defect* gate, not a licence
gate: `donor-matrix.md §6`, verbatim, *"All are individually sound. None should receive data while the
gate and identity defects stand."*

**D8 — Disabling a component deletes nothing.** Every integration has a kill switch and a rollback
route; disabling removes no evidence, candidate or derived artifact (FR-112, constitution P13).

### The giotto-tda disposition (T012)

**Verdict: removed.** Measured at `apps/projection/pyproject.toml:19-25`.

The reasoning, as recorded in the manifest and confirmed here: the dependency was **never imported** —
zero `import giotto_tda` anywhere — so it carried no capability; and it was not free, because every
release including 0.6.2 hard-pins `scikit-learn==1.3.2`, which caps numpy below 2.0 workspace-wide and
blocked `river>=0.26`, scikit-learn 1.9 and the Splink 4 stack. An unused AGPL-3.0 dependency that
constrains the entire workspace's numerical stack is a cost with no offsetting benefit. `gudhi>=3.10`
retains the TDA role.

This resolves **U-02** in substance. See `## Open` for what is still missing.

## Why not the alternatives

**A — Exclude AGPL/GPL outright.** Rejected. It would remove Browsertrix — an existing, functioning
adapter at `apps/acquisition/adapters/browsertrix/collect.py` — to avoid a decision, and the 029 matrix
records these components as *"individually sound"*. Exclusion is a default; `research.md §2.9` requires
a decision.

**B — Treat copyleft as permitted with no recorded deployment model.** Rejected: that is the condition
that produced the giotto-tda problem in the first place. A permitted-but-undocumented dependency cannot
be audited, and the audit question — *what is deployed, how, and under what licence* — is the only one
that matters operationally.

**C — State that process separation satisfies AGPL, and proceed.** Rejected, and this is the most
important rejection in the document. That statement is a legal conclusion. The platform has no basis
for making it and this ADR does not make it. What the platform *can* do is choose an architecture,
record it, and have the deployment reviewed. Anything beyond that is outside this document's competence.

**D — Keep giotto-tda as canonical because it is already installed.** Rejected: it is not imported, so
"canonical" describes nothing. Installation is not adoption — the same principle FR-110 applies to
third-party capability generally.

**E — Isolate giotto-tda as a sidecar instead of removing it.** Rejected: there is nothing to isolate.
It performs no work in this tree. Isolating an unused library would create an operating burden
(pinning, deploying, monitoring a service that computes nothing) in exchange for no capability.

**F — Remove giotto-tda silently, as an unused dependency cleanup.** Rejected: that is what nearly
happened. The disposition is recorded here and in the manifest, because the licence is the reason it
was ever a question, and a future engineer who re-adds giotto-tda needs to know it was removed
deliberately, that it is AGPL-3.0, and that it must not reintroduce a hard `numpy<2` pin.

**G — Treat Phoenix (Elastic 2.0) as permissive because it is "source-available".** Rejected:
source-available is not OSI and the distinction is exactly why it needs its own disposition. It is
listed in the BLOCKED-licence set, not the accepted set.

## Consequences

**Positive**

- The giotto-tda question that `plan.md` called out as a retroactive WP0 deliverable is answered, with
  the evidence in the manifest where the next engineer will see it.
- Removing it frees the workspace's numerical stack: numpy `<2` is no longer capped by an unused
  declaration.
- D2 and D5 give FR-113 a home. Seven asset categories, inventoried separately, is checkable in a way
  "we looked at the licence" is not.
- D3's disclaimer is written into the ADR rather than left to the reader's discretion, which is what
  keeps this document from being cited as legal advice it does not contain.

**Costs, accepted**

- Browsertrix remains AGPL-3.0-or-later and in the tree. D2 obliges a recorded deployment model for it;
  that record is T106's, and it does not yet exist. Accepted as a tracked gap, not as a resolved
  question.
- `donors/registry.yaml` does not exist, so D2 and D5 have no machine-readable enforcement point yet.
  T039 and T040 build it; until then D2 is a review obligation.
- D7 means licence never accelerates a promotion. A permissive component still waits behind the gate
  and identity defects. That is a deliberate ordering from the 029 matrix, not an oversight.

**Not changed**

- ADR-030-01 (PostgreSQL authoritative) stands.
- The giotto-tda removal is not reversed, re-added or re-pinned by this ADR; it is recorded.
- No donor is integrated or rejected by this ADR except giotto-tda, whose disposition was already
  executed in the manifest.
- ADR-030-05's clean-room labelling stands, and is the same discipline applied to code that could not
  be found rather than code that could.

## Verification

- [ ] Every declared dependency and vendored donor has a licence/version entry; CI fails the build
      otherwise (T040, FR-113).
- [ ] Every copyleft dependency has a recorded deployment model naming pinned version, deployment
      shape, network boundary and operational owner (D2).
- [ ] `giotto_tda` appears in no `pyproject.toml` and no source file in the tree.
- [ ] `gudhi>=3.10` remains declared at `apps/projection/pyproject.toml:18` and no dependency pins
      `numpy<2`.
- [ ] No document in the repository asserts that process separation satisfies or fails to satisfy any
      licence obligation (D3).
- [ ] Code licence, dependency licence, model weights, datasets, training data, bundled binaries,
      documentation and sample assets are inventoried as seven separate entries.
- [ ] A component with unestablished identity, source or licence is recorded `unverified` and is
      refused at the registry (FR-114).
- [ ] No integration proceeds without a benchmark, irrespective of licence (D7).
- [ ] Disabling an integrated component deletes no evidence, candidate or derived artifact (D8).

## Open

- **T012's formal disposition record does not exist.** T012 requires the verdict in
  `specs/030-global-platform-upgrade/current-state-audit.md §7`. That file has no §7;
  `current-state-audit.md` records T012 as `[ ]` and its §5 table lists *"T012 | giotto-tda AGPL-3.0
  disposition | `[ ]`"*. This ADR records the disposition **as measured from the manifest** and does not
  claim T012 is complete. **T012 must land** to place it in the audit.
- **Browsertrix's AGPL-3.0-or-later deployment decision is not recorded.** T106 explicitly owns
  *"Record the AGPL-3.0-or-later deployment decision in `donor-matrix.md`"*. `donor-matrix.md` does not
  exist at `specs/030-global-platform-upgrade/`, and
  `specs/030-global-platform-upgrade/donor-matrix.md` is T013's deliverable, not yet produced. D2's
  obligation for the one remaining AGPL component in the tree is therefore **open**.
- **`donors/registry.yaml` does not exist** (`research.md §3.3`; T039/T040), so there is no registry at
  which D2's "refused at the registry" could currently be enforced.
- **`benchmarks/sbom-donors.md` does not exist** (T108), so D5's seven-way inventory has no artifact.