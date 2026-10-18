# Quickstart & Validation: GhostLine Integration

**Feature**: `031-ghostline-vishing-fabric` | **Date**: 2026-10-16

Runnable validation scenarios. Contract: [`contracts/ghostline-api.md`](./contracts/ghostline-api.md).

## Prerequisites

- The donor is vendored: `donors/ghostline/` (source only, no install step).
- Control plane running (`apps/control-plane`, FastAPI on :8000) with `specops_ghostline`
  mounted.
- Webapp dev server (`apps/webapp`, Vite on :5173).

**No credentials are required for most of this.** The donor's stage engine — its
taxonomy, playbook schema, transition runner, mu-law codec and Twilio frame protocol —
has no third-party dependency the platform lacks, so the Playbooks and Simulator panels
are fully exercisable on a clean checkout. Only the live edges (Twilio, Deepgram,
ElevenLabs, ngrok, LiteLLM) need configuration, and every one of them reports itself
absent by name until it is set.

## Environment

The platform reads its own `GHOSTLINE_*` variables and **never** the donor's `.env`
(constitution §VII, secret isolation):

```
GHOSTLINE_TWILIO_ACCOUNT_SID=AC...
GHOSTLINE_TWILIO_AUTH_TOKEN=...
GHOSTLINE_TWILIO_FROM_NUMBER=+15551234567   # never echoed by the API
GHOSTLINE_DEEPGRAM_API_KEY=...
GHOSTLINE_ELEVENLABS_API_KEY=...
GHOSTLINE_LITELLM_MODEL=openai/gpt-4o-mini
GHOSTLINE_OPENAI_API_KEY=...                # or the provider your model prefix names
GHOSTLINE_PUBLIC_BASE_URL=https://...       # an open WSS front door (no pyngrok needed)
GHOSTLINE_LEDGER_DIR=logs/ghostline
```

## Scenario 1 — the department surface (US1)

1. Open the workspace → CI/SpecOps department → the **GhostLine** tab.
2. **Expect**: seven tabs (Runtime · Playbooks · Simulator · Voices · Dialler ·
   Transcripts · Analytics) and the rail hint naming the scope and the capture rule.
3. **Expect** on Runtime: the donor split in two — "stage engine: 5 ready, runs
   in-process" against "live edges: 0 / 7, need a package and a credential".

## Scenario 2 — reading a scenario before dialling it (US2)

1. Playbooks → open **Zero-Day Patch**.
2. **Expect**: the twelve stages in canonical order, each with its intent
   (`URGENCY → compress the decision window`), its `success_regex`, its silence
   threshold and the donor's `psych_triggers`.
3. **Expect**: `CLOSE` is marked *elicits a credential* and its `success_regex` is shown.
4. **Expect**: `URGENCY` shows `on fail → OBJECTION` — the branch is drawn, not hidden.
5. **Expect**: every technique badge's tooltip ends `platform-declared`.
6. Edit `donors/ghostline/playbooks/*.yaml` with a duplicate stage; Runtime → Reload
   playbooks. **Expect**: the playbook stays listed, marked invalid, with the donor
   validator's own rejection reason.

## Scenario 3 — the simulator (US3, the reason this is more than a wrapper)

1. Simulator → **HR Benefits** → script three utterances, one per line:
   `happy friday` / `single` / `the code is 482913`.
2. **Expect**: a trace where each step names the transition, and any step that did not
   advance is badged *held · N cycle(s) left*.
3. **Expect**: the third utterance is rendered `the code is [redacted:no-capture]`, the
   capture counter reads `0 credentials captured`, and `482913` appears nowhere.
4. **Expect**: the rungs strip shows which of the twelve stages the run reached.
5. **Expect**: `missing[]` names that the *generated reply* did not run (no
   `openai-agents` / `litellm`) while the stage machine itself ran in full.
6. Add 250 lines. **Expect**: `missing[]` names the truncation — never a silent cut.

## Scenario 4 — voices (US4)

1. Voices → enter a stock id from the provider's console → **Register**.
2. **Expect**: it appears badged `premade`, and the runtime's voice picker lists it.
   This is the path the donor documents for the free tier and the CLI cannot record.
3. Voices → Clone with a `.mp3` upload. **Expect**: `422` naming `.wav` / `.m4A` — the
   formats the donor's reader actually handles.
4. Clone with `sample_ref` set to `../../etc/passwd`. **Expect**: `422` naming the samples
   root. A name is sent, never a path.
5. Clone with no `GHOSTLINE_ELEVENLABS_API_KEY`. **Expect**: `422` naming the variable.

## Scenario 5 — the runtime (US5)

1. Runtime with nothing configured → **Start runtime**.
2. **Expect**: `424`, `data-kind="setup"` (gold, not red), and the blockers list naming
   the caller ID, the Twilio credentials and the tunnel.
3. Set `GHOSTLINE_PUBLIC_BASE_URL` and the Twilio variables → reload → **Start runtime**.
4. **Expect**: state `running`, the WSS URL Twilio must dial back into, the tunnel
   provider, and the resolved model modality with its `source`.

## Scenario 6 — the gate (US6, mandatory)

1. Dialler → target `+15559999999`, roster `+15551234567`, RoE `roe-nope` → **Place call**.
2. **Expect**: `data-kind="gate"` (red), `RoEError`. Nothing recorded.
3. Record a sign-off (`POST /api/v1/specops/roe`), enter its id, keep the unrostered
   target → **Place call**.
4. **Expect**: `RosterError` with `+15559999999` named under *rejected*. Nothing recorded.
5. Put the target on the roster → **Place call** with the runtime stopped.
6. **Expect**: `data-kind="setup"`, `DialBlocked` — the gate passed, the platform is not
   ready. Two different facts, two different presentations.
7. Throughout: the panel shows `0 credentials captured`, and the operator's own
   `GHOSTLINE_TWILIO_FROM_NUMBER` is never rendered anywhere.

## Scenario 7 — transcripts and analytics (US7)

1. Transcripts → append a turn reading `my code is 482913`.
2. **Expect**: stored and rendered as `my code is [redacted:no-capture]` with a
   `redacted: playbook-success` badge.
3. Analytics → **Expect**: the rate is `—`, not `0%`.
4. Analytics → **Export CSV**. **Expect**: the same figures the panel rendered.
5. Open `logs/ghostline/calls.jsonl`. **Expect**: no credential on disk, and
   `credentials_captured: 0` on every record.

## Automated gates

```bash
pytest apps/specops -q                    # 89 tests: adapter + routers
ruff check apps/specops apps/control-plane/api/routes/specops_ghostline.py
cd apps/webapp && npx tsc --noEmit && npx vitest run src/ghostline && npx eslint src/ghostline
```

## Known environment note

`apps/control-plane/tests/unit` has pre-existing collection failures in this checkout
unrelated to GhostLine (the project's dependency set is not fully installed). The
GhostLine suites do not depend on them and run green.