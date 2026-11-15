# Research — Feature 036

**Date**: 2026-11-01 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

> **Revision 2026-11-02**: the owner removed the lab-only scope, default-deny egress,
> target allowlist and ADR-0040/Amendment 2.1.0 gate. The donor is verified at
> `31ff3f544af8` and is served through the local adapter. Decisions 2, 3, 7, 9 and 11
> below are updated to the current design.

## 1. Department placement

**Decision**: A first-class route `/specops/lab` rendered inside `AppShell`, with a nav
entry under the existing SPECOPS module and a breadcrumb title.

**Evidence**: Feature 027's department is a *view within an investigation*
(`/investigations/ci`), while 036's spec calls the lab a "new SpecOps destination" and
requires a persistent lab banner independent of any investigation. The app already mounts
SpecOps operator surfaces at `/specops`, `/specops/quarantine`, `/specops/connectors`
(`App.tsx:104-109`); `/specops/lab` is the same kind of destination. Keeping it out of
`InvestigationWorkspace` also avoids scoping lab runs to a case.

**Alternatives rejected**: `/investigations/lab` (implies case scope; spec says
tenant-wide lab), a new top-level module (the user asked for a SpecOps department, not a
fourth module).

## 2. Engine boundary

**Decision**: `LabEngine` is platform-owned and in-process. Phishing Club runs as a
local HTTPS service behind `specops.lab.phishingclub`; the adapter forwards health,
console cookies and API traffic. The donor is verified in `donors/registry.yaml` at
`31ff3f544af8` under AGPL-3.0.

**Evidence**: The donor is a Go/Gin service with its own admin console, API-key auth and
SQLite store; importing it as a library would re-implement its feature set. The platform
adapter keeps a contract boundary while exposing the donor's full console/API. The
donor's frontend is proxied, not embedded in the platform design system.

**Alternatives rejected**: porting the Go backend into the platform (duplicates the
donor), embedding donor components in the UI (breaks FR-008).

## 3. Authorization model

**Decision**: The owner removed the lab-only exception and the ADR-0040/Amendment 2.1.0
runtime gate. Full red-team capture is enabled by the confirmed RoE, encrypted artifact
store, audit chain and kill switch.

**Evidence**: The owner selected the full tier and explicitly removed the lab-only
scope. The production rule remains: no authentication bypass or credential capture in
production; the full tier is authorization-bound red-team activity.

**Alternatives rejected**: retaining a separate ratification gate that no longer has an
artefact to read; silently leaving the ADR in place.

## 4. Artifact encryption and redaction

**Decision**: AES-256-GCM (via `cryptography`) with a per-process key from
`SPECOPS_LAB_ARTIFACT_KEY`; if unset, a random key is generated and readiness reports
`key_source: ephemeral`. The API only ever returns `redacted_preview` (e.g.
`session-token ••••`), never plaintext. Decryption exists solely inside the engine for
retention verification and is never routed.

**Evidence**: `cryptography 50.0.1` is installed in the workspace venv. Spec FR-006
requires encryption at rest, redaction in UI/logs and access audit. Fernet/AES-GCM is
authenticated encryption; a home-grown scheme would be a liability.

**Alternatives rejected**: storing plaintext with a UI-only mask (violates at-rest
requirement), reversible hashing (not encryption; dictionary attacks).

## 5. Audit trail

**Decision**: Append-only in-process audit list; each row carries `seq`, actor, action,
object, outcome, correlation id, timestamp, detail and `prev_hash`, with
`row_hash = sha256(prev_hash || canonical(row))`. Export/report actions append rows.
Teardown appends a row and deletes nothing.

**Evidence**: Constitution P1/P2/P15 and spec FR-007/FR-012. The platform's existing
GhostLine ledger is the closest precedent (append-only JSONL), but the lab needs a
hash chain so tampering is detectable in tests.

**Alternatives rejected**: the engagement fabric's JSONL for audit (it is engagement
events, not operator actions), `logging` only (not queryable evidence).

## 6. Campaign funnel

**Decision**: Launch writes `MESSAGE_SENT`, `MESSAGE_READ`, `PAGE_VISITED` (and
optionally `REPORTED`) events into `specops.engagement`; the dashboard reads the funnel
from `campaign_funnel()`. No counter is incremented on the campaign object.

**Evidence**: Feature 032's fabric already owns the fourteen-event taxonomy, the shared
ladder, training separation and anonymisation. Spec FR-007/FR-013 and SC-005 require
figures derivable from evidence. Reusing the fabric avoids a second event model.

**Alternatives rejected**: campaign-local counters (not re-derivable), a new taxonomy
(the platform already refused the donor's raw counting).

## 7. RoE-gated egress

**Decision**: The boundary accepts any syntactically valid target after the RoE gate.
`LabBoundary.check_egress(url)` permits `http(s)`/`lab` schemes and valid hosts/ports;
malformed targets append an audit row and raise `EgressDenied` → `422`. Templates accept
`lab://`, `http(s)://` or relative assets and reject unsupported schemes.

**Evidence**: The owner removed the target allowlist. The remaining hard gate is the
confirmed, unexpired RoE plus the audit/encryption/kill-switch boundary.

**Alternatives rejected**: a hard-coded allowlist that no longer reflects the authorized
engagement scope.

## 8. Kill switch and teardown

**Decision**: One process-wide `LabBoundary` state. `kill_switch()` sets
`status="killed"`, marks every running session `stopped` and every sending campaign
`partial`, and appends an audit row; all mutating engine methods check the state first.
`teardown()` sets `status="torn_down"` and preserves campaigns, sessions, artifacts
metadata, reports and audit. `reset()` clears active state but not evidence.

**Evidence**: Spec FR-012/SC-007; the in-process registry has no timers, so "within five
seconds" is immediate and testable.

## 9. UI composition

**Decision**: One `LabCanvas` with eight tabs, a persistent banner
(`full red-team · RoE-gated · Phishing Club`), and panels fed by one
`GET /specops/lab` overview plus targeted actions. Use `CiPanelShell`, `StatusChip`,
`CiEmpty` and existing `ci.css` classes; no donor Svelte or palette.

**Evidence**: Feature 027's `CICanvas` is the department pattern, and its panel furniture
already encodes scope + named absence. The lab is a separate canvas because its risk tier
is higher; merging it into `CICanvas` would blur that.

**Alternatives rejected**: embedding the donor frontend (spec FR-008), eight separate
routes (fragments the department).

## 10. Tenant isolation

**Decision**: Every registry key is scoped by tenant id from `resolve_tenant`; the
in-memory registries store `tenant_id` on campaigns, sessions, artifacts, reports and
audit rows. Cross-tenant reads return `404` with the same body as an absent object.

**Evidence**: Spec FR-016/SC-012 and Constitution P14. Existing department registries
are tenant-agnostic; 036 must not repeat that gap.

## 11. Donor attribution

**Decision**: `donors/phishingclub/ATTRIBUTION.md` carries the AGPL-3.0 notice,
source-offer route, authorized-use statement and no-warranty statement. The registry entry
is verified at `31ff3f544af8` and readiness reports the license source.

**Evidence**: `specops/engagement/taxonomy.py` points at this file. Spec FR-010 and
SC-006 require attribution and source offer before enablement; the verified registry
entry records that review.
