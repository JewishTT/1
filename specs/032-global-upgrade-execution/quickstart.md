# Quickstart — Verifying Feature 032

**Feature**: `032-global-upgrade-execution` | **Date**: 2026-10-19

This document answers one question: **how would a reviewer check, in under an hour, whether this
programme's claims are true?**

Every step below produces an artifact or an exit status. A claim without one is not verified.

---

## 0. Preconditions

- Repository at `C:\Users\tim\Desktop\COGNITIVE\1` (or the equivalent checkout).
- Python 3.11 environment at `.venv/` with the repository's dependencies installed.
- PostgreSQL and MinIO/S3 reachable, or a documented statement that they are not — in which case the
  affected checks are `BLOCKED`, not `PASS`.
- PowerShell 7 (`pwsh`) for the Spec Kit scripts.

```powershell
cd C:\Users\tim\Desktop\COGNITIVE\1
.venv\Scripts\python.exe --version
git rev-parse HEAD
git status --porcelain | Measure-Object -Line
```

Record the three outputs. They are the baseline every later comparison uses.

---

## 1. Verify the specification is intact

The spec's Appendix A is the owner's v1.0 blueprint, byte for byte. Confirm it:

```powershell
$raw  = Get-Content .\specs\032-global-upgrade-execution\spec.md -Raw
$s    = $raw.IndexOf('<!-- BEGIN VERBATIM SOURCE -->') + '<!-- BEGIN VERBATIM SOURCE -->'.Length
$e    = $raw.IndexOf('<!-- END VERBATIM SOURCE -->')
$body = $raw.Substring($s, $e - $s).Trim("`r","`n")
$text = ($body -replace '(?s)^```markdown\r?\n', '') -replace '\r?\n```$', ''
$sha  = [Security.Cryptography.SHA256]::Create()
([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($text))) -replace '-','')
```

**Expected**: `CC62D760A40AC5DBB40A6527FA597F12AC60A0A1378A91AD3CFBD8F013BA4E25`.

If it differs, the spec has been edited in a way that changes the governing text. Restore the
appendix before proceeding — this is the one check that must never be waived.

The bundled helper automates it:

```powershell
.\tools\specs\inject_verbatim_source.ps1 `
  -SpecPath .\specs\032-global-upgrade-execution\spec.md `
  -SourcePath C:\Users\tim\Downloads\COGNITIVE_Global_Upgrade_Blueprint.md
```

It re-injects the source and prints a `Verbatim : True` line. Re-running it on an already-injected
spec is idempotent.

---

## 2. Verify WP0 exists and gated the programme

```powershell
Test-Path .\specs\032-global-upgrade-execution\benchmarks\WP0-baseline.md
Test-Path .\specs\032-global-upgrade-execution\benchmarks\WP0-capability-matrix.md
Test-Path .\specs\032-global-upgrade-execution\benchmarks\WP0-owner-map.md
```

Then read the sign-off record (T012) and confirm:

- every gate item is `PASS`, `BLOCKED` or `NOT_RUN` — none is blank;
- each `BLOCKED` names an owner and a next action;
- no WP1+ merge predates the sign-off.

**Failure mode this catches**: a programme that started coding because the audit was boring.

---

## 3. Verify the one evidence seam

```powershell
# Every writer of observation state must be the sink and the gate.
rg -n "observation" apps --glob "*.py" -l
rg -n "ArtifactSink|artifact_sink" apps --glob "*.py" -l
```

A writer that constructs a canonical observation outside `apps/acquisition/artifact_sink.py` and
`apps/shared/events/observation_gate.py` is a bypass. The WP0 owner map should already have named it.

Then run the seam tests:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_evidence_seam.py -q
.venv\Scripts\python.exe -m pytest tests/replay/test_evidence_seam_idempotency.py -q
```

**Expected**: pass; the idempotency test asserts that a replayed artifact adds zero observations,
zero coverage and zero revisions.

---

## 4. Verify spans resolve to bytes

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_spans_to_findings.py -q
.venv\Scripts\python.exe -m pytest tests/integration/test_spans_unresolved.py -q
```

Then pick one finding produced by the fixture and resolve it by hand:

1. take the `finding_id`, resolve to its claim, then to the derived artifact, then to the
   observation, then to the span, then to the blob;
2. compare the bytes the span selects with the bytes in the stored object;
3. confirm the span's `selector_semantics_version`.

**Expected**: identical bytes and a named version at every hop. A hop that cannot be resolved must
appear in the output as `partial`/`unresolved` — never as a plausible offset.

---

## 5. Verify identity cannot be merged by a score

```powershell
.venv\Scripts\python.exe -m pytest tests/golden/test_transitive_merge_trap.py -q
.venv\Scripts\python.exe -m pytest tests/integration/test_admission_is_only_committer.py -q
.venv\Scripts\python.exe -m pytest tests/golden/test_false_merge_correction.py -q
```

**Expected**: the `A≈B`, `B≈C`, `A≠C` corpus produces no merge; every merge in the store has a
`ResolutionDecision`; the false-merge correction leaves prior claims byte-identical.

---

## 6. Verify conflicts are first-class

```powershell
.venv\Scripts\python.exe -m pytest tests/golden/conflict_corpus -q
```

**Expected**: each fixture produces its expected kind, or `NOT_A_CONFLICT` with a stated
establishment. The salary/currency case must not produce a conflict before units are matched. The
syndicated-copies case must count one lineage root.

---

## 7. Verify time answers three questions

```powershell
.venv\Scripts\python.exe -m pytest tests/replay/test_bitemporal_as_of.py -q
```

**Expected**: `AS_OF(2025)` is unchanged by a 2026 capture asserting a 2020 fact; `CURRENT` reflects
it; `INTERVAL(2020)` returns the 2020 validity.

---

## 8. Verify the loop stops for a stated reason

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_stop_conditions.py -q
.venv\Scripts\python.exe -m pytest tests/golden/test_two_iterations_change_next_action.py -q
```

**Expected**: an empty queue, exhausted retries, a completed task and an empty result list each
produce a non-terminal or explicitly-limited state with a `CompletionReport` naming the residuals.

---

## 9. Verify the projections can be rebuilt

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_projection_rebuild_parity.py -q
.venv\Scripts\python.exe -m pytest tests/integration/test_projection_kill_switch.py -q
```

**Expected**: delete-and-rebuild reproduces the manifest's `output_digest`; disabling a projection
produces an explicit unavailability, not a stale answer.

---

## 10. Verify donor governance

```powershell
$reg = Get-Content .\donors\registry.yaml -Raw
# Every LIVE_PROVEN entry must carry: pinned revision, five licence fields,
# adapter_path, call_site, kill_switch, benchmark_result, e2e_test_id.
$reg | Select-String -Pattern 'status:\s*LIVE_PROVEN' -Context 0,25
```

Then run:

```powershell
.venv\Scripts\python.exe -m pytest tests/golden/test_donor_disable_preserves_evidence.py -q
.venv\Scripts\python.exe -m pytest tests/security/test_donor_cannot_write_canonical.py -q
```

**Expected**: disabling each promoted donor resumes the baseline path and deletes nothing; no donor
adapter can write canonical state.

---

## 11. Verify the release report is honest

Open `benchmarks/WP12-release-report.md` and check:

- every `SC-001`…`SC-015` row has a status and a command with its exit status;
- every `NOT_RUN` names why it did not run and what would unblock it;
- no benchmark row is missing its corpus, configuration, versions or resource figures;
- every unavailable measure is `null` with a named reason.

**This is the single most important review step.** A release report that is all green without
commands is not a report; it is a claim.

---

## What a reviewer should conclude

If steps 1–11 pass, this feature is doing what its spec says: one seam, typed spans, deliberate
identity, first-class conflict, honest time, a loop that stops for reasons, rebuildable projections
and a donor programme that cannot smuggle in a second platform.

If any step cannot run, the correct outcome is `BLOCKED` with the reason. The blueprint's own
standard (§11.2) is that a benchmark or a claim prints its inputs, versions and exit status — and
that an unavailable measure is `null`, never a fabricated green.
