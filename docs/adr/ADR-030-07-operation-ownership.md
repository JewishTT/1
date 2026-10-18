# ADR-030-07 — Exactly one production owner per graph/TDA/temporal operation

- **Status**: Proposed
- **Date**: 2026-10-17
- **Feature**: `030-global-platform-upgrade`
- **Implements**: T022 ("fill from T011")
- **Cites**: FR-070, Constitution P9, ADR-0010, ADR-0008, ADR-0027
- **BLOCKED ON**: T011, which has not run — see `## Open`

## Context

`research.md §2.7` decided the principle in one line — *"exactly one production owner per operation,
named in an ADR"* — and deferred the table: *"the* table *is a WP0-04 output because the specification
forbids naming owners for code the audit has not yet traced."* T011 is that task. It has not run:
`current-state-audit.md §3–§6` records T011 as `[ ]` and §5 "Not yet done".

So this ADR records the decision, the *measured* duplication that makes the decision necessary, and
nothing else. It does not name the per-operation owner table, because doing so without T011's caller
trace would be exactly the invention this feature forbids (`tasks.md`: *"A grep hit is not a caller"*).

### What is measured

**Three TDA trees, and a live top-level name collision between two of them.**

- `apps/projection/tda/` — `__init__.py`, `bridge.py`, `diagram.py`, `features.py`, `insight.py`,
  `pipeline.py`, `validated.py`. This is the only tree that imports a TDA library. `gudhi` is imported
  at `tda/__init__.py:196`, `tda/bridge.py:299`, `:301`, `:326`, `tda/pipeline.py:35`, `:94`.
- `apps/science/scitda/` — `persistence.py`, `phodms.py`, `series.py`. No TDA library import.
- `GraphInvariant.to_tda_input` — `apps/shared/domain/graph_invariant.py:963`.

**The collision is not hypothetical and is documented in the code.** `apps/control-plane/api/path_shim.py:6-14`
states it plainly: *"`tda` … `apps/science/tda` (VR persistence, Takens series, PHoDMS) and
`apps/projection/tda` (diagram/feature materializers) are both top-level `tda` packages.
`apps/projection` currently wins the .pth ordering."* The shim then re-orders `sys.path` at `:32-34`
so `apps/science` beats `apps/projection` for `tda`, and the consequence is written down at `:12-14`:
*"The science package is the only TDA surface the control plane imports by name; the projection half
stays reachable by file path (`api/routes/network.py` loads `tda/features.py` that way)."*

**[MEASURED]** And it does exactly that. `apps/control-plane/api/routes/network.py:40` builds
`_FEATURES_PATH = Path(__file__).resolve().parents[3] / "projection" / "tda" / "features.py"` and
loads the projection TDA module **by file path**, because a bare import would resolve to the other
package. `api/routes/science_tda.py:9-10` states the converse for its own surface: *"`tda` here is
`apps/science/tda` (`persistence`/`series`), not `apps/projection/tda`."*

**[MEASURED] The duplication between the two `to_tda_input` implementations is acknowledged in the
source.** `apps/shared/domain/graph_invariant.py:959` is a section banner reading *"TDA-readiness -
same shapes as projection.adjacency.AdjacencyView.to_tda_input"*, immediately above
`def to_tda_input` at `:963`, whose docstring at `:966-968` states it returns *"(node_ids, [(i, j,
weight), ...]) exactly like `AdjacencyView.to_tda_input`"*. The counterpart is
`apps/projection/graph/adjacency.py:43` (*"Return (node_ids, weighted edge index triples) ready for
TDA"*), with `:153` (*"Shortest-path distance matrix over the view's edges (TDA input)"*).

**A stale path in the shim itself.** `path_shim.py:7` names `apps/science/tda`. That directory **does
not exist** — `Test-Path apps/science/tda` is `False`; the package is `apps/science/scitda`. The shim's
documentation describes a layout that has since been renamed and was not updated. That matters
because the shim's `sys.path` ordering is the only thing preventing one first-party package from
shadowing another, and its stated reason is now wrong.

**Graph traversal has one declared owner already.** `apps/projection/graph/` contains `abstraction.py`,
`adjacency.py`, `neo4j.py`, `relation_store.py`, `snapshot.py`, and `adjacency.py:1-8` states its role:
it *"Reads the graph projection and returns a plain (nodes, edges) adjacency that downstream analytical
planes (TDA, network analysis) consume without importing a vendor client (Constitution V)."* ADR-0008
and ADR-0027 own the abstraction. This is the shape P9 asks for.

**Temporal has more than one candidate and fewer declared owners.** `apps/projection/metrics/temporal_paths.py`
is reachable from production — `api/routes/network.py:185` and `apps/projection/metrics/__init__.py:8`.
Separately, `apps/shared/domain/temporal_metrics.py` exists, with `:17` noting the *"default window for
higher-order / TDA slices"* and `:65` computing a *"Median event inter-arrival (seconds) - the natural
TDA window."* No ADR names an owner for temporal-path computation.

## Decision

**D1 — One production owner per operation, named, enforced, and recorded in this ADR's owner table.**

The rule: for each of {graph traversal, graph snapshot, adjacency/TDA-input construction, persistence
computation, TDA feature extraction, delay-embedding / series construction, temporal path computation,
temporal window selection}, exactly one module is the production owner. Every other implementation is
removed, or is explicitly marked inert with a stated reason.

**D2 — A function that exists is not a production path.** An owner is established only by a trace from
a live caller. `tasks.md` T007 states the standard: *"A grep hit is not a caller."* The gudhi imports
above establish that `apps/projection/tda/` has a library binding; they do not by themselves establish
that a given function is the production owner of its operation.

**D3 — The `to_tda_input` pair is a single operation with two implementations and is resolved to one.**
`graph_invariant.py:963` and `adjacency.py:43` produce the same shape by the latter's own admission.
One is deleted or becomes a thin delegation to the other. The banner at `:959` is a marker of known
duplication, not a justification for keeping it.

**D4 — No vendor client in domain logic (Principle V, restated).** `adjacency.py:5-6` already asserts
this for the graph side. The ownership table must hold it for every row: the owner receives plain data
shapes, never a Neo4j/GUDHI type.

**D5 — Two first-party packages may not share one top-level import name.** The `tda` collision is
resolved by renaming or by removing one of the two trees — not by relying on `sys.path` ordering, which
`path_shim.py:3-4` itself describes as *"NOT guaranteed"*. A shim that must exist to make imports
deterministic is evidence the names collide, and the fix is to stop the collision.

**D6 — Every owner declares the FR-070 projection properties**, so ownership and rebuildability are
decided together rather than sequentially. An operation with no declared owner and no manifest cannot
be called a production path.

**D7 — Ownership decisions are not made for untraced code.** Where the trace is missing, this ADR
records the duplication and leaves the owner unnamed. That is the intended behaviour, not an omission.

## Why not the alternatives

**A — Name the owners now from directory layout.** Rejected, and this is the specific failure
`research.md §2.7` anticipated: *"[naming owners] for code the audit has not yet traced"*. A plausible
table written without the trace is worse than no table, because the next engineer will treat it as
measured and build on it.

**B — Keep both TDA trees and document that `tda` resolves to projection.** Rejected: the current
arrangement already documents the opposite in two places (`path_shim.py:12-14` and
`api/routes/science_tda.py:9-10`) and then works around it by loading a module **by file path**
(`network.py:40`). A file-path import is the strongest signal available that a package boundary is
wrong. Constitution P9's "remove or mark every duplicate execution path" admits no third option.

**C — Make `apps/science/scitda` the sole TDA owner and delete `apps/projection/tda`.** Rejected as
premature, and note the trap: it looks like the clean answer, but the gudhi bindings live in
`apps/projection/tda` (`pipeline.py:35,94`, `bridge.py:299,301,326`) and the science package has no
library import at all. Deleting the library-bound tree on the strength of the name collision would
remove the only TDA implementation. Deciding this requires T011's trace, which is exactly why D7
exists.

**D — Merge `scitda` into `projection/tda` under one name.** Rejected: `plan.md §Structure Decision`
requires pure reasoning to stay at `apps/science/context/` with the existing one-way dependency, and
`science must not import control-plane internals`. Merging an analytical plane into the projection
member inverts that direction. ADR-0008/0010 shape the separation; renaming or deleting one tree does
not require crossing it.

**E — Fix `path_shim.py` and consider ownership resolved.** Rejected: the shim is a mitigation, not an
ownership decision. Fixing the stale `apps/science/tda` → `apps/science/scitda` reference is a correct
small repair (recorded below as owed), and it fixes nothing about which module owns which operation.

**F — Defer the whole ADR until T011 completes.** Rejected. The duplication is measured now and is
already causing a production workaround. Recording it, with the decision stated and the table deferred,
is strictly more useful than silence and strictly more honest than a guessed table.

## Consequences

**Positive**

- The `sys.path`-ordering fragility has a named destination. `path_shim.py:3-4` describing the
  workspace's own ordering as *"NOT guaranteed"* is a real deployment risk, not only a style issue.
- The file-path import at `network.py:40` becomes removable, and with it a class of import breakage
  that is currently invisible until someone reorders `.pth`.
- D2 keeps the ownership table honest, and T011's trace becomes a required input with a named consumer
  rather than a task that exists for its own sake.

**Costs, accepted**

- Renaming or removing a first-party `tda` package touches tests in at least six files under
  `apps/projection/tests/` and the control-plane routes that import either surface. Accepted: the
  breakage is bounded and visible, which is better than the silent shadowing it replaces.
- The ownership table will not exist when this ADR is read. Accepted deliberately; the alternative is a
  fabricated table.

**Not changed**

- ADR-0008 (graph abstraction), ADR-0010 (TDA architecture) and ADR-0027 (PostgreSQL authoritative)
  stand. This ADR does not reopen the storage decision.
- `apps/shared/domain/graph_invariant.py` is not restructured.
- No vendor client enters domain logic.
- No file is renamed or deleted by this ADR.

## Verification

- [ ] The owner table below is populated, and every row cites a live caller, not a definition.
- [ ] Exactly one production owner exists per operation; every other implementation is deleted or
      marked inert with a stated reason.
- [ ] `graph_invariant.py:963` and `adjacency.py:43` are one implementation, not two.
- [ ] No two first-party packages share one top-level import name; `path_shim.py` no longer contains a
      `tda` ordering workaround.
- [ ] `api/routes/network.py:40` loads no module by file path.
- [ ] `path_shim.py:7` names a directory that exists (`apps/science/scitda`).
- [ ] Every owned operation declares the eleven FR-070 projection properties.
- [ ] No owner returns a vendor type across its boundary (Principle V).

## Owner table

**NOT POPULATED — T011 has not run.** This ADR does not guess it.

| Operation | Production owner | Live caller | Status |
|---|---|---|---|
| graph traversal | `apps/projection/graph/` (per ADR-0008/0027) | to be traced | owner family known, not traced |
| adjacency / TDA-input construction | **duplicated** — `graph/adjacency.py:43`, `domain/graph_invariant.py:963` | to be traced | unresolved (D3) |
| persistence computation | candidate trees: `projection/tda/{pipeline,bridge}.py`, `science/scitda/persistence.py` | to be traced | unresolved |
| TDA feature extraction | `projection/tda/features.py` (loaded by file path at `network.py:40`) | `network.py` | partially traced |
| delay embedding / series | `science/scitda/series.py`, `projection/tda/pipeline.py` (`DelaySeriesComplex`) | to be traced | unresolved |
| temporal path computation | `apps/projection/metrics/temporal_paths.py` | `api/routes/network.py:185`, `metrics/__init__.py:8` | partially traced |
| temporal window selection | `apps/shared/domain/temporal_metrics.py` | to be traced | unresolved |

## Open

- **T011 must land before this ADR can be Accepted.** T011 is *"Map graph/TDA/temporal duplicate
  execution paths and name one production owner per operation — resolve U-01 and U-02 from
  `research.md §8`."* `current-state-audit.md` records it `[ ]`, and §5 there states §3–§6 are *"Not
  yet done"*. The table above is measured duplication, not an ownership decision, and this ADR is
  **Proposed** rather than Accepted for exactly that reason.
- **U-01 and U-02 remain open.** `research.md §8` defines U-01 (*"Which operation has which production
  owner (graph / TDA / temporal)?"*) and U-02 (*"Is giotto-tda canonical, isolated, or removed?"*).
  Neither is resolved here. U-02 is partly overtaken by events — see ADR-030-09, where the giotto-tda
  declaration was removed from `apps/projection/pyproject.toml` on 2026-10-16 with a recorded
  rationale — but T012's formal disposition record in `current-state-audit.md §7` does not exist.
- **`path_shim.py:7` is stale.** It documents `apps/science/tda`; that path does not exist and the
  package is `apps/science/scitda`. This is a real defect, found while measuring for this ADR. It is
  recorded here rather than fixed, because this ADR's author does not own that file and a first-party
  package rename is a decision T011 should make, not a side effect of an ADR.