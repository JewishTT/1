---

description: "Specification for cutting + adapting real donor code into COGNITIVE"
---

# Spec: Donor Code Extraction & Integration

**Input**: `specs/002-donor-pattern-integration/research.md` (R-1…R-10) + the cloned
repositories in `donors/`.

## Objective

`/speckit.specify` — **FR-014 (donor adoption) is upgraded from "patterns only" to
"code extraction":** take the most valuable, license-safe pieces of code from the
donor clones, cut them out, adapt/rewrite them to COGNITIVE conventions, and
integrate them so they are actually used by the pipeline — not dead imports.

## Constraints

- **License gate**: only permissive code is copied.
  - Allowed: OpenOSINT (MIT), FollowTheMoney (MIT), NetForensicAI (MIT),
    Kafka-SIEM (Apache-2.0), SpiderFoot (MIT, logic layer).
  - **Blocked — no code copy**: reNgine (GPLv3, Django/Celery), PANO
    (CC BY-NC-4.0, inspiration only), kipi (broken clone, empty).
- **Adaptation**: donor identifiers/idioms are rewritten to the COGNITIVE domain
  (candidate vs entity, observation provenance, tenant-scoping). Faithful ports are
  a rewrite, not a paste; each adapted module carries an attribution header
  (source repo, commit-ish, license, what changed).
- **No new heavy dependencies**: adapted modules may only use stdlib + already-wired
  deps (pytest for tests). No Django/Celery/DSPy/semhash (unlike source repos).

## Scope (this spec-cut only — 3 modules, 3 integrations)

1. **Correlation graph** ← OpenOSINT `openosint/correlation.py` (~394 LOC, zero deps).
   Non-destructive dedup graph (I-2: never merges), deterministic exports.
2. **Statement provenance value-class** ← FollowTheMoney `ftm/statement/statement.py`
   (~369 LOC). Deterministic `make_key` (sha1 over dataset.entity.prop.value),
   dataset boundary, original_value preservation.
3. **Evidence vault (ingest + manifest + verify)** ← NetForensicAI
   `netforensicai/core/evidence.py` (~201 LOC, stdlib only). Content-addressed ingest,
   read-only stored copy, `manifest.json`, streaming SHA-256 verify.

## Acceptance

- Each adapted module has unit tests in `apps/shared/tests/unit/donor/`.
- Each module is **wired into the pipeline or the delivered bench harness**
  (not dead code): correlation graph → `collective.py` correlation export;
  statement key + evidence vault → `bench/bench/harness.py` micro-benchmarks.
- `ruff` clean; existing suites stay green (shared 77, admission 37, bench 18).