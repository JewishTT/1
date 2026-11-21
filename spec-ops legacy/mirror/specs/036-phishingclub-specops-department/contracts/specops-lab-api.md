# Contract — `/api/v1/specops/lab/*`

All responses use the department envelope:

```json
{
  "served": ["/specops/lab"],
  "missing": [],
  "scope": "red-team"
}
```

`missing` names every unserved endpoint/service; no response fabricates a zero for a
field it could not measure. Errors are `{"detail": ...}` and use:

| Status | Meaning |
|---|---|
| `409` | authorization refusal — RoE missing/expired, kill switch, teardown |
| `422` | target refusal — malformed identity/host, duplicate roster |
| `424` | setup refusal — missing donor adapter, missing encryption key, sender credential |
| `404` | absent object, including a cross-tenant read |
| `503` | the `specops.lab` package could not be imported |

Tenant comes from the bearer token through `resolve_tenant`; no endpoint accepts a
tenant in the body.

## GET `/specops/lab`

One read that feeds the whole canvas.

```json
{
  "served": ["/specops/lab"],
  "missing": [],
  "scope": "red-team",
  "lab": {"lab_id": "lab-…", "status": "ready", "egress_policy": "roe-gated",
          "targets": ["*"], "kill_switch_at": null,
          "teardown_at": null},
  "readiness": {
    "donor": {"id": "phishingclub", "status": "verified", "version": "31ff3f544af8",
              "license": "AGPL-3.0", "blockers": [], "adapter_served": true,
              "service_url": "https://127.0.0.1:8002",
              "console_url": "https://127.0.0.1:8002", "api_key_configured": false},
    "encryption": {"algorithm": "AES-256-GCM", "key_source": "ephemeral", "ready": true},
    "full_red_team_enabled": true,
    "blockers": []
  },
  "campaigns": [CampaignView],
  "templates": [TemplateView],
  "senders": [SenderView],
  "sessions": [SessionView],
  "artifacts": [ArtifactView],
  "reports": [ReportView],
  "operations": [OperationView],
  "engagement": {
    "channel_funnel": {"sent": 0, "opened": 0, "clicked": 0, "reported": 0},
    "training": {"assigned": 0, "completed": 0},
    "subjects": 0, "anonymized": false
  },
  "audit": [AuditView]
}
```

## POST `/specops/lab/campaigns`

```json
{"name": "Q4 drill", "template_id": "tpl-…", "sender_id": "snd-…",
 "roster": ["alice@lab", "bob@lab"], "attack_mapping": ["T1566"],
 "retention_days": 30}
```

`200` with `{campaign: CampaignView}`. `422` for an empty roster, a duplicate recipient,
a malformed identity, an unknown template, or an unready sender. No send occurs.

`CampaignView`:

```json
{"campaign_id": "cmp-…", "tenant_id": "t-…", "name": "Q4 drill",
 "template_id": "tpl-…", "sender_id": "snd-…", "roster": ["alice@lab"],
 "state": "draft", "roe_status": "unconfirmed", "roe_id": null,
 "attack_mapping": ["T1566"], "launched_at": null, "assessment_id": null,
 "retention_days": 30,
 "funnel": {"sent": 0, "opened": 0, "clicked": 0, "reported": 0,
            "training": {"assigned": 0, "completed": 0}, "source": "derived"},
 "captured_credentials_count": 0}
```

## POST `/specops/lab/campaigns/{campaign_id}/launch`

`{"roe_id": "roe-…"}`. `200` with `{campaign: CampaignView}`; `409` RoE
missing/expired/kill switch; `422` roster/target refusal; `424`
sender not ready. On success the engagement fabric is appended once per recipient and
the funnel is re-derived.

## GET `/specops/lab/campaigns/{campaign_id}`

`200` with `{campaign: CampaignView}` or `404`.

## GET `/specops/lab/templates` · POST `/specops/lab/templates`

`GET` → `{templates: [TemplateView]}`.

`POST` body `{name, stages: ["landing", "training"], assets: ["lab://…"],
variables: {"first_name": "Lab"}}` → `200` `{template: TemplateView}`. An asset uses
`lab://`, `http(s)://`, or a relative path; an unsupported scheme is
`422 ExternalAssetRefused`, with the refused URL in `detail`.

## GET `/specops/lab/senders` · POST `/specops/lab/senders`

`POST` body `{name, host: "smtp.lab", tls: true, dns_ready: true,
credential_ref: "vault://lab/smtp"}` → `200` `{sender: SenderView}`. `ready` is
`tls and dns_ready and credential_ref`; `missing` names each unmet
prerequisite. A missing `credential_ref` is `ready=false`, not a default credential.

## POST `/specops/lab/aitm/sessions`

```json
{"mode": "reverse_proxy", "target_host": "specops-lab.local",
 "roe_id": "roe-…", "retention_hours": 24}
```

`200` `{session: SessionView}`. `409` when the RoE is missing/expired; `422` when the
target host is malformed. `mode=remote_browser` and `mode=reverse_proxy` both require
the full tier and a confirmed RoE.

## GET `/specops/lab/aitm/sessions` · GET `/specops/lab/aitm/sessions/{session_id}`

`200` `{sessions: [SessionView]}` / `{session: SessionView}`; `404` if absent (also for
another tenant).

`SessionView`:

```json
{"session_id": "aitm-…", "mode": "reverse_proxy", "target_host": "specops-lab.local",
 "state": "running", "roe_status": "confirmed", "started_at": "…",
 "stopped_at": null, "retention_expires_at": "…", "artifact_ids": ["art-…"]}
```

## POST `/specops/lab/aitm/sessions/{session_id}/capture`

Body `{kind: "token", secret: "synthetic-token-value", label: "session"}`.
`200` `{artifact: ArtifactView}`. The response contains only `redacted_preview`; the
plaintext is encrypted before storage. `409` if the session is not running; `422` for an
unknown kind.

`ArtifactView`:

```json
{"artifact_id": "art-…", "session_id": "aitm-…", "kind": "token",
 "redacted_preview": "session ••••", "sha256": "…", "captured_at": "…",
 "expires_at": "…", "available": true, "access_count": 1}
```

## POST `/specops/lab/aitm/sessions/{session_id}/stop`

`200` `{session: SessionView}`; records `session.stopped`; evidence remains.

## POST `/specops/lab/operations`

`{"plan_id": "plan-ael", "lab_fixture": "specops/lab-target", "roe_id": "roe-…"}`.
`200` `{operation: OperationView}`; delegates to `specops.emulation.REGISTRY` after the
same RoE + lab gate. `409`/`422` as above.

## POST `/specops/lab/assessments`

`{"campaign_id": "cmp-…", "operation_id": "op-…"}` → `200`
`{assessment: {assessment_id, campaign_id, operation_id, created_at}}`. `404` if either
object is absent.

## POST `/specops/lab/reports/{campaign_id}` · GET `/specops/lab/reports/{campaign_id}`

`POST` generates and returns `{report: ReportView}`; `GET` returns the latest or `404`.
`ReportView`:

```json
{"report_id": "rpt-…", "campaign_id": "cmp-…", "generated_at": "…",
 "figures": {
   "sent": {"value": 2, "status": "derived", "source": "engagement:campaign_recipient_message_sent", "missing": null},
   "clicked": {"value": 1, "status": "derived", "source": "engagement:campaign_recipient_page_visited", "missing": null},
   "operation_abilities": {"value": null, "status": "unavailable", "source": "emulation:operation", "missing": "no linked operation"},
   "training_completed": {"value": 0, "status": "measured", "source": "engagement:campaign_recipient_training_completed", "missing": null}
 },
 "limitations": ["RoE-bound red-team activity; targets require a confirmed sign-off",
                 "Phishing Club donor is served through the local HTTP adapter"],
 "provenance": ["engagement:cmp-…", "donor:phishingclub:31ff3f544af8", "audit:12"],
 "redaction": "raw session tokens and credentials are never included",
 "export_digest": null}
```

## POST `/specops/lab/reports/{campaign_id}/export`

`200` `{export: {format: "markdown", digest: "…", body: "…"}}`. The body contains no
raw secret; `digest` is the SHA-256 of the body and is recorded in audit.

## GET `/specops/lab/phishingclub/health`

`200` with the department envelope plus:

```json
{"phishingclub": {"configured": true, "reachable": true, "status": 200, "error": null}}
```

The adapter defaults to `https://127.0.0.1:8002`, uses `PHISHINGCLUB_URL`,
`PHISHINGCLUB_CONSOLE_URL` and `PHISHINGCLUB_API_KEY`, and verifies TLS for remote
hosts. Loopback self-signed TLS is accepted unless `PHISHINGCLUB_VERIFY_TLS` overrides
it.

## GET/POST/PUT/PATCH/DELETE `/specops/lab/phishingclub/{path}`

Transparent proxy to the donor admin API. The route forwards the path, query, body,
`cookie`, `content-type`, `accept-language` and the configured `x-API` key, and returns
the donor status/body/headers without the department envelope. Login cookies and
console traffic therefore work through the platform origin.

## POST `/specops/lab/kill-switch`

`200` `{lab: LabView, stopped_sessions: 2, partial_campaigns: 1}`. Idempotent. Stops all
activity; preserves evidence.

## POST `/specops/lab/teardown`

`200` `{lab: LabView, preserved: {"campaigns": 2, "sessions": 1, "artifacts": 3,
"reports": 1, "audit_rows": 40}}`. Deletes nothing.

## POST `/specops/lab/reset`

`200` `{lab: LabView}`. Returns the boundary to `ready` after a kill/teardown; does not
delete evidence.

## GET `/specops/lab/audit?limit=100`

`200` `{events: [AuditView], integrity: {"ok": true, "broken_seq": null}}`.

`AuditView`: `{seq, actor, action, object_type, object_id, outcome, at,
correlation_id, detail, prev_hash, row_hash}`.

## UI contract notes

- The banner `full red-team · RoE-gated · Phishing Club` is persistent on every panel.
- A `409` is rendered as an authorization refusal with the reason verbatim; a `422` is
  a target refusal naming the entry; a `424` is a setup fact naming the prerequisite.
  They are never collapsed into one "failed" state.
- Captured artifacts render `redacted_preview` only; the UI has no reveal control.
- A panel with no data renders the named absence from `missing`, not `0`.
