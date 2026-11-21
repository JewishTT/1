# Specification: GhostLine — Voice-Borne Social Engineering in the SpecOps Department

**Feature**: `031-ghostline-vishing-fabric` | **Date**: 2026-10-16 | **Status**: implemented

## Why

The CI/SpecOps department (Feature 027) covers kill-chain emulation, phishing/SAT, APT
forensics, counterintelligence and social-reaction projection. Every one of those acts
on **systems**. GhostLine acts on **people**: it places a PSTN call, transcribes a
target's speech, answers through a persuasion model, and works a twelve-stage playbook
to decide when to press.

That difference drives three decisions the rest of the department does not have to
make.

**A dial is a send.** A phishing campaign and a phone call are the same act of
aggression against a human being, so they share one authorisation gate — the same
`specops.roe.gate` module, the same order (RoE then roster), the same codes. The donor's
CLI has no such check; it trusts the operator to hold a signed authorisation, which its
own README states as a requirement rather than enforcing. This platform does not trust,
it verifies.

**The platform must not become custodian of the credentials it elicits.** The gate
already pins `CAPTURE_PASSWORDS = False` for the phishing panel. GhostLine's playbooks
succeed on a *spoken* secret and log the utterance verbatim, so the same invariant
applies here — as a repair at the storage boundary, not as a refusal to take the donor.
An assessment needs to know a target complied. It does not need the one-time code.

**The operator's own PSTN identity is sensitive.** `GHOSTLINE_TWILIO_FROM_NUMBER` is
read to place calls and reported only as configured. It is never echoed into a
response, a log line or the UI.

## What it is

A donor integration plus a complete replacement for its CLI as the operating surface.

**The donor**: [mbhatt1/GhostLine](https://github.com/mbhatt1/GhostLine), MIT — an
LLM-driven vishing operative with a twelve-stage playbook engine, Twilio/Deepgram/
ElevenLabs/LiteLLM edges, a Typer CLI (`clone`, `serve`, `call`, `analytics`) and a
plain HTML dashboard.

**The integration**: the donor vendored to `donors/ghostline/`, its stage engine running
unmodified inside the control plane, its live edges gated behind the platform's own
RoE gate, and every CLI verb served as a full UI panel.

## Why the donor's stage engine is the centre of this

GhostLine splits cleanly in two, and only one half needs credentials:

| | Needs | Runs here |
|---|---|---|
| **stage engine** — taxonomy, playbook schema, transition runner, mu-law codec, Twilio frame protocol | `pyyaml`, `pydantic`, `numpy` | **yes** |
| **live edges** — Twilio, Deepgram, ElevenLabs, ngrok, LiteLLM/Agents, SQLite ledger | six packages + six credentials | no — named |

So the platform runs the donor's **real** `PlaybookRunner` over a scripted transcript
and shows exactly where each utterance would have moved the call. Nothing is dialled.

This is the part that earns the integration its place, and the donor's CLI cannot do
it. A playbook with `max_cycles: 1` on an `URGENCY` stage and no `goto_on_fail` sends the
call onward whatever the target says; a `success_regex` that can never match makes a
stage a dead end. Both are invisible in a YAML file and obvious in a trace, and finding
them should not require placing a call.

## Functional requirements

**US1 — the department surface.** GhostLine is a tab on the CI/SpecOps canvas, not a
separate product. Same envelope, same scope note, same panel furniture.

**US2 — read a scenario before dialling it.** Every playbook in the donor's library is
listed with its stages, prompts, success patterns, branches, silence thresholds, donor
psych triggers and the platform's ATT&CK mapping.

**US3 — simulate the stage machine.** A scripted transcript produces a per-utterance
transition trace, held steps, and a terminal outcome. Nothing is dialled, nothing is
persisted, credentials in the input are redacted.

**US4 — the voice registry.** Register a premade voice id (the donor's documented
free-tier route) or clone from a sample — a name in the samples root or a bounded
upload. Origin is kept visible: a clone reproduces a specific person's voice and a
stock voice does not.

**US5 — the runtime.** Bring the pipeline up on a voice and a playbook; see the WSS URL
Twilio must dial back into, the resolved model modality and its source, and a named
blocker list when something is missing. Stopping closes the tunnel.

**US6 — dialling, gated.** Place an outbound call. RoE first, then roster, then the
donor. A sign-off that is absent, unconfirmed or expired is `409`; a target the
supervisor did not approve is `422` with the number named; a missing credential or
uninstalled package is `424`.

**US7 — the assessment record.** Calls, redacted transcripts, outcomes, stage
distribution, a redaction ledger, and the export served rather than written to a file.

## Non-functional requirements

- **FR-001 — donor reuse.** Every behaviour comes from the vendored donor's own modules.
  No reimplementation of the stage machine, the playbook schema, the codec or the frame
  protocol.
- **FR-002 — secrets.** No accessor returns a secret. Readiness reports `configured` and
  the variable that would set it. The donor's `.env` is never read.
- **FR-003 — no-capture.** `credentials_captured` is `0` and `capture_passwords` is
  `false` on every record and every response. Neither is a parameter.
- **FR-004 — named absence.** A donor dependency, a credential or an endpoint that
  cannot be served is named in `missing[]`. Never a zero, never a blank pane, never a
  fabricated default.
- **FR-005 — closed status vocabulary.** An unrecognised donor status maps to
  `Unknown`. The UI invents no states and no colours.
- **FR-006 — refusal kinds.** An authorisation refusal and a setup gap are different
  facts with different codes and different presentations.
- **FR-007 — untrusted input.** Uploads are size-capped, suffix-checked, contained to a
  configured root, and stored under a server-derived name. Targets are E.164-validated.
- **FR-008 — attribution.** The donor is vendored with its licence, its repository URL
  and its version. Its README's authorisation requirement is this feature's premise.
- **FR-009 — CLI parity.** Every `ghostline` verb is reachable from the UI. The CLI is a
  convenience, not a gate.

## Out of scope

- Caller-ID spoofing. The donor does not do it and this does not add it.
- Making calls. This integration builds, gates and records; placing a call requires the
  operator's own Twilio account, their own numbers and their own sign-off.
- Egress-policy and process-isolation hardening, deferred with the rest of the
  department's gate (Feature 027, FR-003/SC-007).
- A durable store for the ledger (see `tasks.md`, Deferred D2).