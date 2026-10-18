# Tasks: GhostLine Integration

**Feature**: `031-ghostline-vishing-fabric`

## Phase 0 — importability (prerequisite; a pre-existing defect)

- [x] T001 `apps/specops` is a plain source directory with no distribution, so `import specops` failed under pytest. Add `apps/` to the root `conftest.py` path, lowest priority, so the specific source dirs still win collisions.
- [x] T002 Document in `api/path_shim.py` that `specops` resolves through `apps/`, its parent — not through `apps/specops`.
- [x] T003 Do **not** put `apps/specops` on `sys.path`. It would put a `ghostline/` directory there and shadow `donors/ghostline/src/ghostline`, failing every donor import with a path error that reads as a broken donor. Documented in `conftest.py`.
- [x] T004 Verify: `pytest apps/specops -q` collects both pre-existing modules (21 tests) instead of erroring.

## Phase 1 — the donor arrives

- [x] T010 Vendor `mbhatt1/GhostLine` to `donors/ghostline/` (MIT), unmodified, no install step.
- [x] T011 `loader.py` — import the donor under its own name via `sys.path`, probe each module, and report per-module readiness. Split the donor into a **stage engine** (runs here) and **live edges** (need packages + credentials).
- [x] T012 Never raise from a donor resolution: an unimportable module is a named absence, not a crash of whatever surface asked for it.

## Phase 2 — configuration and the capture invariant

- [x] T020 `config.py` — read `GHOSTLINE_*` (donor names as a fallback). Never the donor's `.env` (constitution §VII).
- [x] T021 No accessor returns a secret. Readiness reports `configured` + the env var that would set it.
- [x] T022 `redaction.py` — the repair on transfer. Fail closed on an uncompilable pattern; report the *kind*, never the value; do not over-redact identifiers like `SEC-4217`.
- [x] T023 Scope the playbook's declared patterns to credential-eliciting stages only, so a `DISCOVERY` pattern like `\b(single|married|family)\b` does not blank out ordinary answers.

## Phase 3 — the donor's stage engine, served

- [x] T030 `catalog.py` — load every playbook through the donor's own `Playbook` validator. An invalid one is listed as invalid with the donor's rejection reason.
- [x] T031 Serve the donor's `taxonomy` extras per stage: `psych_triggers`, `default_prompt`, `checkin_line`. `null` + `missing[]` when the module is absent — never `[]`.
- [x] T032 Platform-declared ATT&CK mapping, with `mapping_source` on every record. GhostLine carries none.
- [x] T033 `engine.py` — run the donor's real `PlaybookRunner` over a scripted transcript. Nothing dialled, nothing persisted.
- [x] T034 A `matched_pattern` on a credential stage reports its redaction kind, never the match.
- [x] T035 Name what the simulation could not run (the persuasion model needs `openai-agents` + `litellm`).

## Phase 4 — the donor's CLI verbs, as services

- [x] T040 `voices.py` — `clone`. Premade-voice registration as a first-class path (the donor's documented free-tier route, which the CLI has nowhere to record).
- [x] T041 Upload containment: names not paths, confined to `samples_root`, derived stored filenames, suffix + size caps.
- [x] T042 `runtime.py` — `serve` as an inspectable lifecycle. Blocked with named blockers rather than a failure. Pollable while running.
- [x] T043 Tunnel is not ngrok-only: `GHOSTLINE_PUBLIC_BASE_URL` takes an open WSS front door.
- [x] T044 `telephony.py` — `call`. The tunnel URL comes from the runtime, not a shell variable between two terminals.
- [x] T045 Translate the donor's two documented Twilio trial-account errors into the sentence that fixes them.
- [x] T046 `ledger.py` — the assessment record. Path-keyed reload so the index can never disagree with the file.
- [x] T047 Force the capture invariant back on read: a hand-edited ledger cannot promote `credentials_captured`.
- [x] T048 `service.py` — the facade. The safety ordering lives in exactly one file.

## Phase 5 — the API

- [x] T050 `specops_ghostline.py` — one route per CLI verb, plus `/playbooks`, `/playbooks/{id}` and `/playbooks/{id}/simulate`.
- [x] T051 Gate first: RoE (409), then roster (422), then the donor. Nothing reaches a provider, a ledger or a runtime before both pass.
- [x] T052 Setup facts are `424` with a reason. Absent records are `404`. A donor that will not import is `503`.
- [x] T053 Envelope on every response: `served` / `missing` / `scope`.
- [x] T054 Mount in `api/main.py` beside the other specops routers.

## Phase 6 — the UI, replacing the CLI

- [x] T060 `lib/api.ts` — one typed client method per route; wire types next to the client that calls them.
- [x] T061 `ghostline/model.ts` — pure derivation. Every field is real or explicitly `null`; an unknown donor status is `Unknown`, never a new colour.
- [x] T062 `panelParts.tsx` — `classify()` decides gate-vs-setup from the server's own `detail`, never from a message string.
- [x] T063 **RuntimePanel** — the donor split in two, the composition, the provider readiness checklist with the variable each needs, and the WSS URL.
- [x] T064 **PlaybooksPanel** — the twelve-stage ladder with intent, branches drawn, credential stages marked, techniques attributed.
- [x] T065 **SimulatePanel** — the scripted transcript, the transition trace, held steps, the rungs strip.
- [x] T066 **VoicesPanel** — premade registration + clone (name or upload), with origin kept visible.
- [x] T067 **DialerPanel** — roster and sign-off on screen, the capture counter, and the refusal split by kind.
- [x] T068 **TranscriptsPanel** — redacted turns with their redaction kinds; hand-appending goes through the same redaction.
- [x] T069 **AnalyticsPanel** — stage distribution, outcome split, the redaction ledger, export served rather than written. An unmeasured rate renders `—`.
- [x] T070 `GhostlineCanvas` + `ghostline.css` — seven tabs on the department's existing tokens.
- [x] T071 Wire into `CICanvas` as the eighth tab; `CiPanel` gains `"ghostline"`.

## Phase 7 — verification

- [x] T080 `apps/specops/tests/conftest.py` — one fixture for the three pieces of global state. Ordering is load-bearing and is documented as such.
- [x] T081 `test_ghostline.py` — 66 tests. The stage engine runs against the real donor with nothing mocked; redaction tests assert the *absence* of the secret.
- [x] T082 `test_specops_ghostline_routers.py` — 23 tests through the whole control plane over HTTP.
- [x] T083 `ghostline.test.tsx` — 26 mounted tests, including gate-vs-setup rendering and the capture counter.
- [x] T084 `ruff check` clean on every touched file. `tsc --noEmit` clean. `eslint` clean.
- [x] T085 Confirm the 4 pre-existing webapp failures (`Selection.performance`,
      `InvestigationsGraphContainer`) are unrelated: reproduced identically on a stashed
      clean tree.

## Phase 8 — documentation

- [x] T090 `contracts/ghostline-api.md` — every route, the envelope, the status-code split by kind of failure.
- [x] T091 `plan.md` — why the split is drawn where it is; D1–D8; the risks; the pre-existing defect found.
- [x] T092 `data-model.md` — the entities, storage, and the repair on transfer.
- [x] T093 `quickstart.md` — seven scenarios, runnable without credentials for the first three.

## Deferred

- **D1** The donor's media WebSocket handler is not mounted in-process. `RuntimeState.media_route_served`
  reports it and `missing[]` names the dependency (`openai-agents`, `pydub`, `twilio`).
  A deployment that installs the donor's live stack gets the real pipeline; one that
  does not gets a served surface that says so rather than a stub that dead-airs a call.
- **D2** A durable store for the ledger. JSONL is a projection-shaped durable file and
  the shape matches the donor's SQLite columns, so the swap is a repository, not a
  migration.
- **D3** Streaming live transcripts to the browser over SSE while the donor owns the
  socket. `POST /calls/{id}/turns` is the write path today; a read stream is a
  projection on top of it.
- **D4** Caller-ID verification status. The platform reports whether the from number is
  configured; Twilio's own verification state is only observable by making a call.