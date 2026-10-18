# Data Model: GhostLine Integration

**Feature**: `031-ghostline-vishing-fabric`

GhostLine has no persistence worth adopting: a SQLite ledger behind `aiosqlite`, which
the platform does not carry, holding four tables the platform's own projection already
covers. What the platform adds is the *assessment record* — which scenario ran, against
which rostered target, through which stages, how it ended — and one structural
invariant the donor does not have.

## Invariants

1. **A call is a record of an action against a person.** Not a telemetry row. It names
   the target, the authorisation, the scenario and the outcome.
2. **`credentials_captured` is `0`. Always.** Not a field with a zero default — a class
   constant with no argument that could change it, and forced back to `0` on read so a
   hand-edited ledger file cannot promote it.
3. **`capture_passwords` is `false`. Always.** Pinned to the platform's gate
   (`specops.roe.gate.CAPTURE_PASSWORDS`).
4. **A transcript stores the *fact* that a credential was elicited and never the
   credential.** `redaction_kinds[]` names the shapes removed.
5. **The ledger file is the record; the in-memory index is a projection of it.** The
   index is rebuilt from the file, and rebuilding is keyed on the resolved path so an
   index can never disagree with the file it was built from.

## Entities

### `LedgerCall`

```python
call_id        str    # "gl-<hex>"; the platform's stable identity, independent of any provider id
sid            str?   # the Twilio Call SID, once placed
target         str    # E.164; the one rostered number this call was placed to
campaign       str
persona        str    # the prosody name
playbook_id    str?   # the scenario; drives the redactor
roe_id         str?   # the sign-off that authorised it
started_at     str    # ISO-8601 UTC
ended_at       str?
outcome        str?   # compromised | abandoned | in_progress | no_answer | null
capture_passwords  bool  # constant False
credentials_captured int  # constant 0
notes          str?
messages       list[LedgerMessage]
```

Derived, never stored: `message_count`, `final_stage`.

### `LedgerMessage`

```python
call_id            str
role               str    # target | agent | operator
content            str    # REDACTED before it is stored
stage              str?   # one of the donor's twelve
timestamp          str
redaction_kinds    tuple[str]   # otp | credential-value | digit-run | account-number | playbook-success
sentiment_score    float?
interest_level     float?
objection_type     str?
trigger_used       str?
```

### `Voice`

```python
voice_id      str    # the ElevenLabs voice id, or a premade one
name          str
origin        str    # "cloned" | "premade"
created_at    str
sample_ref    str?   # name inside the samples root
sample_bytes  int?
notes         str?
```

`origin` is kept because a clone is a reproduction of a specific person's voice and a
stock voice is not. An assessment record that does not distinguish them is not one an
assessor can sign.

### `RuntimeState`

```python
state            str    # stopped | blocked | running
voice_id         str?
playbook_id      str?
model            str?
capabilities     dict   # the donor's own report: modality, native_stt/tts, source
ws_url           str?   # the WSS URL Twilio dials back into
tunnel_provider  str?   # ngrok | configured | none
port             int?
started_at       str?
media_route_served bool
blockers         tuple[str]   # named prerequisites, in the order an operator fixes them
missing          tuple[str]   # what this deployment cannot serve
```

One runtime per process, not a pool: an exercise is bound to one voice, one playbook
and one tunnel, and two would be two active identities on the same caller ID.
Concurrency belongs to the donor's per-call WebSocket.

### `ProviderReadiness`

```python
name        str    # twilio | twilio_from_number | deepgram | elevenlabs | llm | tunnel
configured  bool
env_var     str    # the variable that would configure it
detail      str    # what it is for, and what is unnecessary without it
```

No accessor anywhere returns a secret. Readiness answers "is this usable", never "is
this correct" — validity is a live call to the provider, and guessing either way would
be a lie.

## Storage

| What | Where | Format |
|------|-------|--------|
| Call ledger | `logs/ghostline/calls.jsonl` | JSONL, one `{"call": {...}}` per line |
| Voice registry | `logs/ghostline/voices.jsonl` | JSONL, one voice per line |
| Voice samples | `GHOSTLINE_SAMPLES_ROOT` (default `donors/ghostline/assets`) | WAV / M4A |
| Playbooks | `donors/ghostline/playbooks/*.yaml` | the donor's own schema, unmodified |
| Donor source | `donors/ghostline/src/ghostline/` | unmodified, imported by path |

**Why JSONL and not the donor's SQLite.** `aiosqlite` is not a dependency the platform
carries, and four tables do not justify one. JSONL keeps the record readable in a text
editor — which for an assessment artefact is worth more than O(1) appends — and keeps
the donor's column names, so a deployment that installs `aiosqlite` can reconcile the
two without a migration.

## The repair on transfer

GhostLine's playbooks succeed on a *spoken* secret (`success_regex: "\\b\\d{6}\\b"` on a
CLOSE stage means "the target read back the one-time code") and the donor logs the
utterance verbatim. That is the donor working as designed, and it collides with the
platform's gate, which pins `CAPTURE_PASSWORDS = False`.

The resolution is a repair, not a decline and not a rewrite: redaction at the single
boundary every transcript crosses, so the donor's functionality is intact — the stage
machine still matches, the call still records `compromised` — and only the *persistence
of the secret* is cut. An assessment needs to know a target complied; it does not need
the secret, and storing it would make the platform custodian of every credential it
ever elicited.

`redaction.py` fails closed: a pattern that will not compile falls back to the generic
shapes rather than passing text through. It also fails *quiet* in the right direction —
`\b\d{4,8}\b` does not match inside `SEC-4217`, because a ledger full of redacted ticket
numbers is a ledger nobody reads, and an operator who stops reading the marker has
stopped noticing the redaction at all.