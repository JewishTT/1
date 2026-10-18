# Implementation Plan: GhostLine Integration

**Feature**: `031-ghostline-vishing-fabric` | **Date**: 2026-10-16

## Why this integration is shaped the way it is

The constitution makes donor reuse the default (rev. 1.1.0). Applied literally to
GhostLine, that default happens to be *unusually* well served, because the donor has a
clean seam:

| Donor part | Third-party needs | Runs here? |
|------------|-------------------|------------|
| `taxonomy` (12-stage vocabulary, psych triggers, timings) | none | **yes** |
| `playbook` (YAML schema + validation) | `pyyaml`, `pydantic` | **yes** |
| `playbook_runner` (success_regex / goto_* / max_cycles) | none | **yes** |
| `audio.codec` (pure-numpy G.711 mu-law) | `numpy` | **yes** |
| `telephony.media_stream` (Twilio frame protocol) | none | **yes** |
| `telephony.twilio`, `tunnel`, `stt.deepgram`, `tts.elevenlabs`, `agent.*`, `persistence.*` | `twilio`, `pyngrok`, `pydub`, `openai-agents`, `litellm`, `aiosqlite` + credentials | no — **named** |

So the plan is not "wrap the donor". It is: **run the donor's real stage engine in the
platform, gate the donor's live edges behind the platform's own authorisation gate, and
move the entire CLI surface into a UI.** A playbook that renders in the UI is one the
donor's own validator accepted; a transition trace is a real `PlaybookRunner` run.

The one thing this is emphatically not is a reimplementation. Every behaviour above
comes from `donors/ghostline/src/ghostline/`, imported by path, unmodified.

## Layout

```
donors/ghostline/                      vendored source (MIT, mbhatt1/GhostLine)

apps/specops/ghostline/
  loader.py       import the vendored donor; report exactly which parts run here
  config.py       the platform's own credentials; readiness, never a secret
  catalog.py      the donor's playbook library + the platform's ATT&CK mapping
  engine.py       the donor's PlaybookRunner as a dry-run simulator
  voices.py       `clone`, plus premade-voice registration
  runtime.py      `serve` as an inspectable lifecycle
  telephony.py    `call`, minus the shell-variable tunnel URL
  redaction.py    where an elicited credential is stopped from being stored
  ledger.py       the assessment record: calls, turns, outcomes, aggregates
  service.py      the composition the router calls; safety ordering lives here

apps/control-plane/api/routes/specops_ghostline.py
                                  one route per CLI verb + the two surfaces a CLI lacks

apps/webapp/src/ghostline/
  types.ts  model.ts  panelParts.tsx  GhostlineCanvas.tsx  ghostline.css
  panels/{Runtime,Playbooks,Simulate,Voices,Dialer,Transcripts,Analytics}Panel.tsx
```

## Decisions

### D1 — import the donor under its own name, not a copy

The donor's modules use absolute intra-package imports (`from ghostline.taxonomy import
SalesStage`). Re-homing the tree under `apps/specops/vendor/` would break every one of
them. So `donors/ghostline/src` goes on `sys.path` (appended, never prepended) and the
donor is imported as `ghostline.*`, unmodified — which is what "donor reuse" has to
mean for it to be reuse.

### D2 — the platform owns the secrets, not the donor's `.env`

`ghostline.settings` reads `.env` from the process working directory. Adopting that
would mean the control plane silently inherited a donor-local secrets file from
whatever directory it was launched in — exactly the secret-isolation failure
constitution §VII forbids. The platform reads `GHOSTLINE_*` and constructs the donor's
settings explicitly where one is genuinely needed. The donor's bare variable names are
accepted as a fallback so an operator who followed the donor's walkthrough does not
have to re-type every secret.

### D3 — the redaction is a repair on transfer, not a fork of the donor

The donor logs an elicited credential verbatim; the platform's gate forbids storing one.
Cutting persistence at the single boundary a transcript crosses keeps the donor's
functionality whole — the stage machine still matches, the call still records
`compromised` — and avoids forking the donor's call handler to comply. See
`data-model.md`.

### D4 — authorisation is the platform's gate, in the platform's order

`POST /calls` runs `specops.roe.gate.launch_campaign` before the donor's Twilio service
is touched: RoE first, then roster, then dial. Same gate, same order, same codes as the
phishing and emulation routers, because it is the same gate. The CLI's `call` has no
such check — it trusts the operator to hold a sign-off, which the donor's README states
as a requirement rather than enforcing.

### D5 — setup failures and authorisation failures are different facts

`409`/`422` mean the gate refused; `424` means something is not configured or not
installed. The UI styles them differently (`data-kind="gate"` red, `data-kind="setup"`
gold) because a red "refused" badge on a missing environment variable teaches an
operator that the tool is refusing them rather than telling them what to do.

### D6 — the tunnel is not ngrok-only

The donor hard-wires `pyngrok`; its own design notes call the tunnel provider
swappable. `GHOSTLINE_PUBLIC_BASE_URL` accepts an already-open WSS front door
(Cloudflare, FRP, a reverse proxy), which takes `pyngrok` off the critical path
entirely. A donor defect repaired rather than inherited.

### D7 — `analytics` is served, not written

The CLI writes a CSV and prints a path. Generated separately from anything on screen,
that file drifts from the dashboard it is meant to describe. The export here comes from
the same aggregate the panel renders, returned to the browser to download.

### D8 — no caller-ID echo

`GHOSTLINE_TWILIO_FROM_NUMBER` is the operator's own PSTN identity and the donor's
README says so. It is read to place calls and reported only as `configured`.

## Risks

| Risk | Mitigation |
|------|------------|
| A credential reaches the ledger | Redaction at one boundary; tests assert on the *absence* of the secret, not the presence of a marker; a hand-edited ledger is re-pinned to `0` on read |
| An unrostered number is dialled | Gate runs before the donor is reached; `422` with the rejected number named; a test asserts the ledger is still empty after a refusal |
| A path traversal via an uploaded sample | Names, not paths; resolution confined to `samples_root`; derived stored filenames; suffix and size caps |
| A package the platform lacks breaks the department | Every donor module is probed; an unimportable one is a named absence; the API boots and serves the rest |
| A silent 503 across the whole department | `apps/` is now on `sys.path` in both the root conftest and `api.path_shim`, so `import specops` resolves (see plan §Pre-existing defect) |
| A donor module is shadowed by a platform package | `apps/specops` is deliberately *not* on `sys.path` — it would put a `ghostline/` directory there and shadow the vendor tree. Documented in `conftest.py`. |

## Pre-existing defect found and fixed

`apps/specops` is a plain source directory, not a uv workspace member, so nothing
installed a `specops` distribution. `import specops` only resolved when `apps/` happened
to be on `sys.path` — which the control plane's `api.path_shim` arranged, but the root
`conftest.py` did not. Every `api/routes/specops_*.py` guards its donor import with
`except Exception`, so under pytest the entire CI/SpecOps department failed collection
or silently degraded to six 503s that read as "the donor is down" rather than "the
package is not importable".

Fixed by adding `apps/` to the root conftest's path (lowest priority, so the specific
source dirs still win collisions) and documenting in `api/path_shim.py` why `specops`
resolves through its parent.