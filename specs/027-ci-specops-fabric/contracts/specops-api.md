# CI/SpecOps API Contract (`/api/v1/specops/*`)

**Feature**: `027-ci-specops-fabric` | **Date**: 2026-10-10

Thin FastAPI routers wrapping integrated donor functionality. All responses follow the platform's named-absence rule: a field a donor does not serve is `null` plus the source name in a `missing[]` array — never zero, never a default (FR-012). Unknown donor status strings map to `"Unknown"` (FR-011).

## Common envelope
Every list/get response carries:
```json
{ "served": ["<endpoint parts that answered>"],
  "missing": ["<endpoint part (what would close it)>"],
  "scope": "tenant-wide | investigation-scoped" }
```

---

## Emulation (kill-chain) — `specops_emulation.py`

### `GET /api/v1/specops/emulation/plans`
List ATT&CK emulation plans loaded from donor libraries.
```json
{ "plans": [ { "plan_id", "name", "source_donor", "target_techniques": ["T1059"], "lab_fixture" } ],
  "served": [...], "missing": [...], "scope": "tenant-wide" }
```

### `GET /api/v1/specops/emulation/plans/{plan_id}`
Plan detail: abilities + expected telemetry.
```json
{ "plan": { "plan_id", "abilities": [ {"ability_id","technique","tactic","executor","expected_telemetry":[…]} ],
            "expected_telemetry": [...], "lab_fixture" }, "served": [...], "missing": [...] }
```

### `POST /api/v1/specops/emulation/operations`
Launch an operation. **Blocked** unless a confirmed RoE is supplied.
```json
// request
{ "plan_id", "lab_fixture", "roe_id" }
// 200
{ "operation": { "operation_id","state":"running","abilities":[{"ability_id","status":"planned"}], "started_at" } }
// 409 (gate)
{ "error": "RoEError", "reason": "no confirmed rules-of-engagement for this target" }
```

### `GET /api/v1/specops/emulation/operations/{operation_id}`
Live + post-run state: per-ability planned vs executed, beacons, pivots.
```json
{ "operation": { "operation_id","state","roe_status",
                 "abilities":[{"ability_id","technique","status":"executed"}],
                 "agent_beacons":[...], "pivot_paths":[...], "halted_reason":null },
  "served": [...], "missing": [...] }
```

---

## Phishing / SAT — `specops_phishing.py`

### `POST /api/v1/specops/phishing/campaigns`
Create a draft campaign (no send).
```json
// request
{ "name", "template_source", "roster": ["approved@lab"], "attack_mapping": ["T1566"] }
```

### `POST /api/v1/specops/phishing/campaigns/{campaign_id}/launch`
Send. **Blocked** without confirmed RoE and in-roster targets only.
```json
// request
{ "roe_id" }
// 409 (gate)
{ "error": "RoEError", "reason": "roe not confirmed" }
// 422 (roster)
{ "error": "RosterError", "rejected_targets": ["not-approved@…"] }
```
Invariant: response never contains captured credentials; server never stores them (FR-006).

### `GET /api/v1/specops/phishing/campaigns/{campaign_id}`
```json
{ "campaign": { "campaign_id","state","engagement_metrics":{"sent","opened","clicked","submitted"},
                "attack_mapping":[...], "captured_credentials_count": 0 },
  "served": [...], "missing": [...] }
```

---

## Counterintelligence — `specops_counterintel.py`

### `GET /api/v1/specops/counterintel/subjects/{subject_id}`
```json
{ "subject": { "subject_id","kind","display",
               "invariants":[ {"kind":"belief-state","value":"…","confidence":0.7,
                               "evidence_refs":["obs-…"], "supported": true} ],
               "relations":[ {"to":"subject-2","kind":"…","evidence_refs":[...] } ] },
  "served": [...], "missing": [...], "scope": "investigation-scoped" }
```
Invariant with empty `evidence_refs` ⇒ `"supported": false` (FR-008).

---

## Social-reaction — `specops_social.py`

### `POST /api/v1/specops/social/projections`
```json
// request
{ "population_ref", "narrative_input", "horizon" }
// 200
{ "projection": { "projection_id","trajectories":[{"t":0,"reach":…,"polarization":…}],
                  "phase_transition_risk":{"indicator":0.8,"threshold_crossed":true},
                  "confidence":"low|medium|high",
                  "artifacts_ref":"…" },
  "served": [...], "missing": [...] }
```

---

## Forensics — `specops_forensics.py`

### `GET /api/v1/specops/forensics/operations/{operation_id}`
Expected vs actual telemetry + detection gaps.
```json
{ "forensics": { "operation_id",
                 "comparison":[ {"ability_id","expected":"…","actual":["obs-…"],"status":"corroborated|gap"} ],
                 "gaps":[ {"gap_id","ability_id","expected_telemetry"} ] },
  "coverage": { "techniques":[ {"technique":"T1059","covered":true} ] },
  "served": [...], "missing": [...] }
```

---

## Rules of Engagement — `specops_roe.py`

### `POST /api/v1/specops/roe`
Record a sign-off (supervisor).
```json
// request
{ "target_ref", "scope", "approved_by", "expires_at" }
// 200
{ "roe": { "roe_id","status":"confirmed","expires_at" } }
```

## Notes
- Routers mount at `/api/v1` alongside existing routers (`main.py` pattern).
- Donor lab services (PhishSlayer, Labyrinth) are proxied by these routers; the process boundary is preserved (research D2 shape 2).
- Every router tolerates its donor being down: returns `served: []`, names the source in `missing`, and the panel renders a named absence (FR-012/FR-013).
