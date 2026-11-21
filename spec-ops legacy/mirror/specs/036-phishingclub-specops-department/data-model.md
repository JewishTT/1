# Data Model — Feature 036

All records are tenant-scoped (`tenant_id`). Money-free, no real subjects. In-process
registries are guarded by one `threading.RLock`; the engagement funnel is a projection of
the existing append-only `specops.engagement` log.

## LabBoundary

| Field | Type | Notes |
|---|---|---|
| `lab_id` | `str` | `lab-<hex>`; one per process |
| `status` | `"ready" \| "killed" \| "torn_down"` | `killed` blocks every mutation until `reset()` |
| `targets` | `tuple[str, ...]` | permitted target patterns; default `("*",)` |
| `egress_policy` | `"roe-gated"` | literal; no setter |
| `kill_switch_at` | `str \| None` | ISO-8601 UTC |
| `teardown_at` | `str \| None` | ISO-8601 UTC |

**Invariants**: `check_egress` accepts any syntactically valid `http(s)` host and port
after the RoE gate; `lab://` and relative assets are also accepted. Malformed targets
append `egress.denied` and raise `EgressDenied`. `kill_switch()` is idempotent and
appends one audit row per call.

**Transitions**: `ready -> killed -> ready` via `reset()`; `ready|killed -> torn_down`
via `teardown()`. `torn_down -> ready` only via an explicit `reset()` that records
`lab.reset`.

## LabTarget

| Field | Type | Notes |
|---|---|---|
| `host` | `str` | valid host, lower-case, no scheme |
| `kind` | `"web" \| "smtp" \| "fixture"` | target kind |
| `synthetic` | `bool` | fixture marker; RoE governs authorization |

## Campaign

| Field | Type | Notes |
|---|---|---|
| `campaign_id` | `str` | `cmp-<hex>` |
| `tenant_id` | `str` | from `resolve_tenant` |
| `name` | `str` | non-empty |
| `template_id` | `str` | must exist in the lab template catalog |
| `sender_id` | `str \| None` | must exist and be ready before launch |
| `roster` | `list[LabRecipient]` | valid email identities; duplicates refused |
| `schedule` | `str` | `"manual"` for this increment |
| `attack_mapping` | `list[str]` | ATT&CK ids, informational |
| `state` | `"draft" \| "ready" \| "sending" \| "partial" \| "complete" \| "refused"` | |
| `roe_id` | `str \| None` | recorded at launch only |
| `assessment_id` | `str \| None` | set when linked to an operation |
| `created_at` / `launched_at` | `str \| None` | ISO-8601 UTC |
| `retention_days` | `int` | 1..365, default 30 |

**Derived (never stored as counters)**: `funnel` from
`specops.engagement.campaign_funnel(campaign_id, events)`, `captured_credentials_count`
pinned to `0` on the simulation track.

**Validation**: every roster address is a syntactically valid email and is unique
case-insensitively. A campaign with no recipients is `422`. Launch requires confirmed,
unexpired RoE and a ready sender; it is refused while `boundary.status != "ready"`.

**Launch projection**: for each recipient, append `MESSAGE_SENT`; for every recipient
except the last, append `MESSAGE_READ` and `PAGE_VISITED`. No `SUBMITTED_DATA` event is
written by the simulation; the AiTM lane records captures separately.

## LabRecipient

`{address: str, display: str | None}` — address is the identity; display is synthetic.

## Template / Lure

| Field | Type | Notes |
|---|---|---|
| `template_id` | `str` | `tpl-<hex>` |
| `name` | `str` | |
| `stages` | `tuple[str, ...]` | ordered, min 1 |
| `assets` | `tuple[str, ...]` | `lab://`, `http(s)://`, or relative |
| `variables` | `dict[str, str]` | preview values only |
| `provenance` | `str` | `synthetic` or `donor:<id>@<rev>` |
| `authorized` | `bool` | synthetic or explicitly authorized |

**Validation**: an asset with an unsupported scheme raises `ExternalAssetRefused`
(`422`) before the template is stored. No network fetch occurs; the donor performs any
asset delivery.

## SenderProfile

| Field | Type | Notes |
|---|---|---|
| `sender_id` | `str` | `snd-<hex>` |
| `name` | `str` | |
| `host` | `str` | valid sender host |
| `tls` | `bool` | |
| `dns_ready` | `bool` | |
| `credential_ref` | `str \| None` | a reference, never a secret |
| `ready` | `bool` | `tls and dns_ready and credential_ref` |
| `missing` | `list[str]` | names each unmet prerequisite |

## AitmSession

| Field | Type | Notes |
|---|---|---|
| `session_id` | `str` | `aitm-<hex>` |
| `tenant_id` | `str` | |
| `mode` | `"reverse_proxy" \| "remote_browser"` | full mode |
| `target_host` | `str` | valid host |
| `state` | `"running" \| "stopped" \| "denied" \| "expired"` | |
| `roe_id` | `str` | confirmed at start |
| `started_at` / `stopped_at` | `str \| None` | |
| `retention_hours` | `int` | 1..720, default 24 |
| `retention_expires_at` | `str` | computed at start |
| `artifact_ids` | `list[str]` | |
| `access_audit` | `list[dict]` | actor, action, at; no plaintext |

**Transition**: `running -> stopped` (operator or kill switch), `running -> expired`
(retention sweep), `denied` when the target is malformed. Start requires a confirmed
RoE and a running boundary.

## CapturedArtifact

| Field | Type | Notes |
|---|---|---|
| `artifact_id` | `str` | `art-<hex>` |
| `tenant_id` / `session_id` | `str` | |
| `kind` | `"cookie" \| "token" \| "credential" \| "header"` | |
| `ciphertext` | `bytes` | AES-256-GCM; never returned |
| `nonce` | `bytes` | 12 bytes; stored with ciphertext |
| `sha256` | `str` | digest of plaintext, for integrity/lineage |
| `redacted_preview` | `str` | e.g. `session-token ••••` |
| `captured_at` / `expires_at` | `str` | |
| `available` | `bool` | false after retention purge; row survives |
| `access_count` | `int` | incremented by metadata reads |

**Invariants**: no method returns `ciphertext` or plaintext to the router. A retention
sweep zeroes ciphertext, sets `available=false`, appends `artifact.expired`; the row and
its digest remain for counts and pseudonyms. Every capture appends `artifact.captured`;
every metadata read appends `artifact.accessed` (no secret in detail).

## Assessment

`{assessment_id, tenant_id, campaign_id, operation_id, created_at}`. Links one campaign
to one Caldera/AEL operation while both keep separate evidence. The report reads the
campaign projection and the operation view; neither is copied into the other.

## Report

| Field | Type | Notes |
|---|---|---|
| `report_id` | `str` | `rpt-<hex>` |
| `tenant_id` / `campaign_id` | `str` | |
| `generated_at` | `str` | |
| `figures` | `dict[str, ReportFigure]` | funnel stages, operation abilities, training |
| `limitations` | `list[str]` | named, not hidden |
| `provenance` | `list[str]` | audit/event refs and donor status |
| `redaction` | `str` | states that raw secrets are never included |
| `export_digest` | `str \| None` | set when exported |

`ReportFigure = {value: int | null, status: "measured" | "derived" | "unavailable",
source: str, missing: str | null}`. A figure with no evidence is `value=null`,
`status="unavailable"` and names the missing instrumentation — never `0`.

## AuditEvent

| Field | Type | Notes |
|---|---|---|
| `seq` | `int` | monotonic per process |
| `tenant_id` | `str` | |
| `actor` | `str` | `user_id` from tenant context, or `system` |
| `action` | `str` | closed-ish vocabulary, dotted |
| `object_type` / `object_id` | `str` | |
| `outcome` | `"ok" \| "refused" \| "error"` | |
| `at` | `str` | ISO-8601 UTC |
| `correlation_id` | `str` | request/action id |
| `detail` | `dict` | no secret, no roster PII beyond lab addresses |
| `prev_hash` / `row_hash` | `str` | SHA-256 chain |

**Verification**: `audit.verify()` recomputes every `row_hash` and returns the first
broken `seq` or `None`.

## Readiness

`{donor: {id, status, version, license, blockers[], adapter_served, service_url,
console_url, api_key_configured}, encryption: {algorithm, key_source}, lab: {...},
missing[]}`. `missing` names every closed-shape prerequisite (donor verification,
attribution, adapter service, encryption, RoE). The UI renders these as named absences,
not zeros.

## State ownership

| Store | Owner | Durability |
|---|---|---|
| Boundary / audit | `specops.lab.boundary` / `.audit` | process; hash chain |
| Campaigns / templates / senders / sessions / artifacts / reports / assessments | `specops.lab.engine.LabEngine` | process (in-memory) |
| Engagement events | `specops.engagement.fabric` | append-only JSONL |
| Operations | `specops.emulation.REGISTRY` | process |
| RoE | `specops.roe.gate.REGISTRY` | process |
