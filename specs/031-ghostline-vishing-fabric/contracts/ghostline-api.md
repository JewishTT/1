# API Contract: GhostLine

**Feature**: `031-ghostline-vishing-fabric` | **Base**: `/api/v1/specops/ghostline`

Every control GhostLine's CLI exposes is served here, so the CLI is a convenience
rather than the only way to operate it.

| CLI verb | Served as |
|----------|-----------|
| `clone`  | `POST /voices/clone`, `POST /voices` |
| `serve`  | `POST /runtime/start`, `POST /runtime/stop`, `GET /status` |
| `call`   | `POST /calls` |
| `analytics` | `GET /analytics`, `GET /analytics/export`, `GET /calls`, `GET /calls/{id}` |

Plus two surfaces the CLI has no shape for: reading a playbook before dialling it
(`GET /playbooks`, `GET /playbooks/{id}`) and running its stage machine over a
scripted transcript (`POST /playbooks/{id}/simulate`).

## Envelope

Every response carries the CI/SpecOps department's standard shape:

```json
{ "served": ["/specops/ghostline"], "missing": [], "scope": "tenant-wide", "...": "" }
```

`scope` is always `tenant-wide`: an exercise belongs to an engagement, not to one
investigation. `missing[]` names what this deployment could not serve — a donor
dependency, a credential, an endpoint — and is never a zero or an empty object.

## Status codes

The codes are separated by *kind of failure*, because the three mean different things
to an operator and must not read the same in the UI.

| Code | Meaning |
|------|---------|
| `200` / `201` | Served |
| `404` | A named record does not exist (playbook, call, voice) |
| `409` | **`RoEError`** — the rules-of-engagement gate refused. An authorisation fact. |
| `422` | **`RosterError`** — a target outside the approved roster. An authorisation fact. |
| `422` | A malformed request (bad format, unknown outcome, unknown export format) |
| `424` | **A setup fact** — a credential is unset, or a donor dependency is not installed |
| `503` | The `specops.ghostline` subpackage could not be imported at all |

`409`/`422` are the gate's two codes and nothing else in this module uses them for a
setup problem; `424` is never an authorisation verdict. The UI keys its refusal
styling off that split (`data-kind="gate"` vs `data-kind="setup"`).

## The capture invariant

Every response that could carry a credential field carries it as `0`, structurally:

```json
{ "capture_passwords": false, "credentials_captured": 0 }
```

There is no request parameter that changes this. Transcripts are redacted at the
storage boundary before they are written; `redaction_kinds[]` on each stored turn
names the *shapes* removed, never the values.

---

## `GET /status`

Everything the Runtime panel renders in one pass: the donor report, provider
readiness, the runtime descriptor, counts, playbook validation errors and absences.

```json
{
  "served": ["/specops/ghostline"], "missing": [], "scope": "tenant-wide",
  "donor": {
    "donor_id": "ghostline", "license": "MIT", "present": true,
    "stage_engine": { "ready": ["ghostline.taxonomy", "..."], "absent": [] },
    "live_edges":  { "ready": [], "absent": ["ghostline.telephony.twilio needs the twilio package..."] }
  },
  "config": { "model": "openai/gpt-4o-mini", "tts_model": "...", "stt_model": "...", "...": "" },
  "providers": [
    { "name": "twilio", "configured": false,
      "env_var": "GHOSTLINE_TWILIO_ACCOUNT_SID + GHOSTLINE_TWILIO_AUTH_TOKEN",
      "detail": "Outbound PSTN placement and Media Stream dial-back." }
  ],
  "blockers": ["twilio: set GHOSTLINE_TWILIO_ACCOUNT_SID ..."],
  "runtime": { "state": "stopped", "...": "" },
  "counts": { "playbooks": 5, "playbooks_valid": 5, "voices": 1, "calls": 0 },
  "playbook_validation_errors": {},
  "missing": []
}
```

**No secret is ever in this response.** Providers report `configured: true|false` and
the variable that would configure them. In particular `GHOSTLINE_TWILIO_FROM_NUMBER` —
the operator's own PSTN identity — is reported as configured and never echoed.

## `GET /playbooks`

The donor's YAML library, loaded through the donor's own `Playbook` validator. A
playbook that appears here is one the donor's stage machine will accept.

```json
{
  "playbooks": [{
    "playbook_id": "zero_day_it_patch",
    "name": "Zero-Day Patch — Midnight IT Emergency",
    "stage_count": 12, "first_stage": "RAPPORT", "has_branching": true,
    "persona_name": "Axel",
    "techniques": [{ "id": "T1566.002", "reason": "Phishing: Spearphishing Voice — the channel GhostLine dials." }],
    "mapping_source": "platform-declared",
    "valid": true, "invalid_reason": null, "missing": []
  }],
  "invalid": {}
}
```

`mapping_source` is always `platform-declared`: GhostLine carries no ATT&CK data, and
an unattributed technique id would read as a measurement.

## `GET /playbooks/{id}`

Adds `stages[]` (per-stage prompt, `success_regex`, `goto_on_*`, `max_cycles`,
`silent_until`, `language_hint`, donor `psych_triggers` / `checkin_line`), `persona`
and `defaults`. `psych_triggers` and `checkin_line` are `null` — not `[]` — when the
donor's taxonomy module is not importable, and the playbook's `missing[]` names it.

`stages[].captures_credential` marks the stages whose `success_regex` fishes for a
secret rather than for a state. Those stages' transcripts are scrubbed with the
playbook's own patterns; every other stage's are not, because a `DISCOVERY` pattern
like `\b(single|married|family)\b` matches an ordinary answer.

## `POST /playbooks/{id}/simulate`

```json
{ "utterances": ["happy friday", "single", "the code is 482913"] }
```

Runs the donor's real `PlaybookRunner` over the transcript. Nothing is dialled, nothing
is persisted, and utterances are redacted on the way back out.

```json
{ "simulation": {
  "steps": [{ "index": 0, "utterance": "happy friday",
              "stage_before": "RAPPORT", "stage_after": "CREDIBILITY",
              "success": false, "cycles_remaining": 0,
              "matched_pattern": null, "next_line": "...", "exited": false }],
  "final_stage": "CREDIBILITY", "outcome": null, "outcome_reason": null,
  "capture_passwords": false, "credentials_captured": 0,
  "redaction_kinds": [], "missing": ["the generated reply ... needs openai-agents"]
}}
```

`matched_pattern` reports a *state* match verbatim (`"matched (playbook-success)"` when
the match was a credential) — returning the match on a `CLOSE` stage would hand back
the one-time code the redaction exists to withhold.

`424 SimulationUnavailable` when the donor's runner is not importable or the playbook
will not load.

## `GET /voices` · `POST /voices` · `POST /voices/clone` · `DELETE /voices/{id}`

```json
{ "voice": { "voice_id": "21m00...", "name": "support desk",
             "origin": "premade", "created_at": "...", "sample_ref": null } }
```

`POST /voices` records a voice id the operator already holds — the path the donor's own
documentation sends free-tier operators down, since instant cloning needs a paid plan
and the CLI has nowhere to put the stock id they picked.

`POST /voices/clone` takes either `{ "name", "sample_ref" }` (a name inside the
configured samples root) or `{ "name", "sample_base64", "sample_filename" }`.

`422 VoiceUnavailable` with an operator-actionable reason, in this order of
fundamentality: no ElevenLabs key → the sample is not a cloneable format / escapes the
samples root / exceeds the size cap → the donor's `pydub` dependency is absent.

`DELETE` is `409` while a running runtime is pinned to the voice.

## `POST /runtime/start`

```json
{ "voice_id": "21m00...", "playbook_id": "it-test", "port": null }
```

```json
{ "runtime": { "state": "running", "voice_id": "...", "playbook_id": "...",
               "ws_url": "wss://x.ngrok-free.app/twilio", "tunnel_provider": "ngrok",
               "capabilities": { "modality": "text", "needs_deepgram": true,
                                 "needs_elevenlabs": true, "source": "litellm" },
               "media_route_served": true, "blockers": [], "missing": [] }}
```

`424 RuntimeUnavailable` with `blockers[]` when a prerequisite is absent — a missing
caller ID, missing Twilio credentials, no tunnel, no model credential, or an
unimportable donor module. This is a setup checklist, not an authorisation refusal.

`GHOSTLINE_PUBLIC_BASE_URL` accepts an already-open WSS front door, which removes
`pyngrok` from the critical path entirely.

`POST /runtime/stop` is idempotent and closes the tunnel.

## `POST /calls`

```json
{ "target": "+15551234567", "campaign": "drill", "persona": "professional",
  "roe_id": "roe-...", "approved_roster": ["+15551234567"], "playbook_id": "it-test" }
```

Gate order is fixed: **RoE first** (is this authorised at all?), then **roster** (is
this specific target authorised?), then the donor's Twilio service. Nothing reaches a
provider, a ledger or a runtime until both pass.

| Failure | Status | `detail.error` |
|---------|--------|----------------|
| No / expired / unconfirmed sign-off | `409` | `RoEError` |
| Target not on `approved_roster` | `422` | `RosterError` + `rejected_targets[]` |
| Target not E.164, or runtime not up | `424` | `DialBlocked` |

## `GET /calls` · `GET /calls/{id}` · `POST /calls/{id}/turns` · `POST /calls/{id}/complete`

```json
{ "call": { "call_id": "gl-...", "sid": "CA...", "target": "+1555...",
            "outcome": "compromised", "capture_passwords": false,
            "credentials_captured": 0, "message_count": 12, "final_stage": "CLOSE" } }
```

`GET /calls/{id}` adds `messages[]`, each with `content` already redacted and
`redaction_kinds[]` naming what was removed.

`POST /calls/{id}/turns` is how a live call reaches this ledger when the donor's media
server owns the socket. It uses the same redaction, so a hand-logged turn is
indistinguishable from a donor-written one.

`POST /calls/{id}/complete` takes `outcome` ∈ `compromised | abandoned | in_progress | no_answer`.

## `GET /analytics` · `GET /analytics/export`

```json
{ "analytics": {
  "call_count": 3, "completed_count": 3, "in_progress_count": 0, "turn_count": 40,
  "stage_counts": { "RAPPORT": 12, "CLOSE": 4 },
  "outcomes": { "compromised": 2, "abandoned": 1 },
  "by_campaign": { "drill": 3 },
  "redaction_kinds": { "playbook-success": 2 },
  "capture_passwords": false, "credentials_captured": 0,
  "conversion_rate": 0.6667 } }
```

`conversion_rate` is `null` until at least one call has completed. It is never `0`
before that: an assessment with no completed calls has no rate, and `0%` would assert
that the targets resisted.

`GET /analytics/export?format=csv|json` returns the donor's `analytics` export served
rather than written to a file, generated from the same aggregate the dashboard renders.