# Implementation Plan: Phishing Club SpecOps Department — Full Red-Team

**Branch**: `036-phishingclub-specops-department` | **Date**: 2026-11-01 | **Spec**: [spec.md](./spec.md)

> **Revision 2026-11-02**: lab-only scope, default-deny egress, target/identity
> allowlist, the unverified-donor block and the ADR-0040 runtime gate are removed.
> Phishing Club is verified at `31ff3f544af8` and is reached through the local-service
> adapter at `/specops/lab/phishingclub/*`. Sections below that describe the earlier
> lab-isolated design are historical.

**Input**: Feature specification from `/specs/036-phishingclub-specops-department/spec.md`

## Summary

Add a fourth SpecOps surface — **SpecOps → Red-Team Lab** — that joins the existing
CI/SpecOps department and its engagement fabric. The department has eight panels
(Operations, Campaigns, Templates & Lures, Senders & Domains, AiTM / Remote Browser,
Engagement & Training, Reports, Lab Control) over one lab boundary, one RoE gate, one
append-only audit trail, and one readiness matrix.

The implementation is a platform-owned red-team vertical slice. Phishing Club is a
verified donor pinned at `31ff3f544af8` and is reached through an authenticated local
service adapter; the campaign/AiTM workflow stays behind the same `LabEngine` contract.
The donor console is linked from Lab Control and its API is proxied through
`/specops/lab/phishingclub/*`.

Full red-team capture (reverse proxy, remote browser, session/token capture) runs in
full mode. The ADR-0040 and Constitution 2.1.0 ratification gate has been removed; the
remaining hard gate is a confirmed RoE plus the tested boundary.

## Technical Context

**Language/Version**: Python 3.11; TypeScript 5.5 / React 18

**Primary Dependencies**: FastAPI + Pydantic (API), `cryptography` (AES-GCM artifact
encryption), existing `specops.roe.gate`, `specops.engagement`, `specops.emulation`;
React + existing UI 2.0 primitives (Tabs, Button, Input, Badge, Panel)

**Storage**: In-process registries for this increment (the department's existing pattern:
`specops.phishing`, `specops.emulation`, `specops.roe`); the engagement fabric's
append-only JSONL log is the durable engagement record. Artifacts are encrypted before
they enter the registry. A durable lab store is a later concern, named in readiness.

**Testing**: pytest (engine + FastAPI `TestClient`); Vitest + Testing Library (canvas);
`tsc -b`; ESLint; platform-model drift gate

**Target Platform**: Linux server / Windows dev; browser UI at `/specops/lab`

**Project Type**: Web application (FastAPI control plane + React webapp), inside an
existing monorepo

**Performance Goals**: Kill switch stops all lab activity within 5 s (in-process: next
request sees `killed`; no timers to cancel); readiness read < 100 ms; no external
network call from the lab engine

**Constraints**: RoE-gated egress; any syntactically valid target/identity; RoE
confirmed + unexpired server-side; no raw secret in any API response, log, audit row or
report; tenant scope on every read/write; donor registry entry verified before enablement

**Scale/Scope**: One department, eight panels, one lab, in-memory campaign/session
registries sized for drills (hundreds of recipients), not production throughput

## Constitution Check

*GATE: evaluated before Phase 0 and re-checked after Phase 1 design.*

| Gate | Verdict | Evidence / plan |
|---|---|---|
| I. Observation-immutable evidence | PASS | Audit rows are append-only with a SHA-256 hash chain; artifacts are write-once ciphertext; retention deletes secret material, never the audit row. |
| II. Evidence-first | PASS | Every campaign/report figure is a projection of engagement events or an audit row; reports carry per-figure `measured / derived / unavailable` and a lineage ref. |
| III. Projection-first | PASS | Funnel is a fold over `specops.engagement` events; campaign counters are not incremented in place. |
| V. Plugability by contract | PASS | UI and router depend on `LabEngine` / `LabBoundary`; the Phishing Club service is one adapter behind that contract and its registry entry is verified. |
| VII. Security-first (production rule) | PASS | Production still ships no authentication bypass or credential capture. Full-mode capture is RoE-bound, encrypted, redacted, retained and kill-switchable. |
| P1/P9. Immutability / rebuildability | PASS | Artifact metadata is immutable; ciphertext is never mutated. Retention purge updates availability only, with an audit row. |
| P6/P15. Truthful reporting | PASS | Unavailable measurements serialise `null` with the missing endpoint/service; readiness names blockers; no fabricated zero. |
| P11. Hard constraints outrank utility | PASS | RoE and kill switch run before any engine call; refusals are 409/422/424, never warnings. |
| P13. Donor reuse with boundaries | PASS | `donors/registry.yaml` records Phishing Club as verified at `31ff3f544af8` under AGPL-3.0. The platform engine is not donor code; the adapter is the boundary. |
| P14. Security / acceptable acquisition | PASS | Tenant isolation, RoE-gated egress, encrypted artifacts, redacted presentation, no secret in logs. |

**Post-design re-check**: PASS. The owner removed the lab-only exception; there is no
runtime governance-ratification gate. RoE, encryption, audit and kill switch remain.

## Project Structure

### Documentation (this feature)

```text
specs/036-phishingclub-specops-department/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── specops-lab-api.md
├── checklists/
│   └── requirements.md
└── spec.md
```

### Source Code (repository root)

```text
apps/specops/lab/
├── __init__.py          # public contract: LabEngine, LabBoundary, registries
├── models.py            # LabTarget, Campaign, AitmSession, Artifact, Report, AuditEvent
├── boundary.py          # identity/host validation, egress, RoE + kill switch
├── phishingclub.py      # local-service HTTP adapter (health + proxy)
├── audit.py             # append-only hash-chained audit log
├── artifacts.py         # AES-GCM encryption, redaction, retention
├── engine.py            # campaigns, sessions, reports, teardown
└── readiness.py         # capability matrix + donor/registry read

apps/control-plane/api/routes/specops_lab.py
apps/control-plane/api/main.py                  # import + include_router

apps/specops/tests/
├── test_lab_engine.py
└── test_specops_lab_router.py

apps/webapp/src/lab/
├── LabCanvas.tsx
├── lab.css (reuses ci.css classes; layout only)
├── model.ts
├── useLabOverview.ts
├── LabCanvas.test.tsx
└── panels/
    ├── labParts.tsx
    ├── LabControlPanel.tsx
    ├── OperationsLabPanel.tsx
    ├── CampaignsPanel.tsx
    ├── CatalogPanel.tsx        # templates and senders
    ├── AitmPanel.tsx
    ├── EngagementLabPanel.tsx
    └── ReportsPanel.tsx

apps/webapp/src/App.tsx                         # /specops/lab route
apps/webapp/src/shell/nav.ts                    # destination + breadcrumb
apps/webapp/src/lib/api.ts                      # lab wire types + methods

.specify/memory/constitution.md                 # version 2.2.0, amendment 2.1.0 removed
donors/phishingclub/ATTRIBUTION.md
```

**Structure Decision**: The backend follows the department's existing module pattern —
an `apps/specops/<subject>/` package with a thin FastAPI router that imports defensively
and maps gate errors to 409/422/424. The UI is a new `src/lab/` surface reached from the
SPECOPS module, rendered with existing primitives and the existing `ci.css` layout
classes so it cannot drift into a donor palette. The existing CI/SpecOps canvas and
simulation-only phishing panel remain untouched; the new department is additive.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Full-mode credential/session capture | The owner selected the full red-team tier; AiTM/session capture distinguishes it from the simulation panel. | A simulation-only department cannot exercise token/session containment, redaction or retention. Capture is scoped by RoE, tenant isolation, encryption, redaction, retention and a kill switch. |
| Phishing Club service runs locally | The donor is a Go/Gin service with its own console, API-key auth and SQLite store; importing it as a library would re-implement its feature set. | Re-implementing the donor would drift. The adapter keeps it behind a platform-owned contract and exposes its full console/API. |
