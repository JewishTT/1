# Quickstart — Verifying Feature 033

**Feature**: `033-universal-context-runtime` | **Date**: 2026-10-19

This document answers one question: **how would a reviewer check, in under an hour, whether the
Universal Context Runtime's claims are true?**

Every step produces an artifact or a command with an exit status. A claim without one is not
verified, and `NOT_RUN` is an acceptable answer — a fabricated `PASS` is not.

---

## 0. Preconditions

```powershell
cd C:\Users\tim\Desktop\COGNITIVE\1
.venv\Scripts\python.exe --version
git rev-parse HEAD
git status --porcelain | Measure-Object -Line
```

Record the three outputs. Phase A's baseline must contain the same values; a mismatch means the
verification is running against a different tree than the one that was measured.

---

## 1. Verify the specification is intact

The spec's Appendix A is the owner's v2.0 document, byte for byte.

```powershell
$raw  = Get-Content .\specs\033-universal-context-runtime\spec.md -Raw
$s    = $raw.IndexOf('<!-- BEGIN VERBATIM SOURCE -->') + '<!-- BEGIN VERBATIM SOURCE -->'.Length
$e    = $raw.IndexOf('<!-- END VERBATIM SOURCE -->')
$body = $raw.Substring($s, $e - $s).Trim("`r","`n")
$text = ($body -replace '(?s)^```markdown\r?\n', '') -replace '\r?\n```$', ''
$sha  = [Security.Cryptography.SHA256]::Create()
([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($text))) -replace '-','')
```

**Expected**: `7B645578F210454CA3FE6FC96D2A18D5699E0D5CC1A1A609E3AB08BBE9BD32C6`.

The helper also works and is idempotent:

```powershell
.\tools\specs\inject_verbatim_source.ps1 `
  -SpecPath .\specs\033-universal-context-runtime\spec.md `
  -SourcePath "C:\Users\tim\Downloads\COGNITIVE_Global_Upgrade_Blueprint (1).md"
```

**Expected**: `Verbatim : True`, 167 121 bytes, 1 979 lines.

---

## 2. Verify the runtime attaches to the programme and did not fork it

Open `plan.md` §"Relationship to Features 030 and 032" and check that:

- the evidence seam, spans, identity and conflict records are **consumed**, not redefined;
- the context engine is `apps/control-plane/context_engine`, not a new service;
- no new canonical store is declared.

Then:

```powershell
Test-Path apps\control-plane\context_engine
Test-Path apps\shared\contracts
```

**Expected**: both exist, and `plan.md`'s structure decision points at them.

---

## 3. Verify a new domain can be admitted without a core change

```powershell
.venv\Scripts\python.exe -m pytest tests/golden/test_domain_pack_registration.py -q
```

Then perform the check by hand:

1. count the migrations before installing the pack;
2. install a pack that registers a new `kind_uri` and a new schema;
3. count the migrations after;
4. grep the core enums for the new kind.

**Expected**: identical migration count, identical enum set, and the pack's content stored,
retrievable and disableable.

**This is the single test of the word "universal".** If it fails, the runtime is extensible in
appearance only.

---

## 4. Verify unknown content is preserved

```powershell
.venv\Scripts\python.exe -m pytest tests/contract/test_context_element.py -q
.venv\Scripts\python.exe -m pytest tests/golden/test_unknown_predicate_round_trip.py -q
```

**Expected**: an opaque `kind_uri`, a malformed payload and an unknown predicate each survive
storage, events, API, export and UI — or are quarantined with named decoding errors. Nothing is
silently dropped.

---

## 5. Verify abstraction is accountable

```powershell
.venv\Scripts\python.exe -m pytest tests/golden/test_summary_drill_down.py -q
.venv\Scripts\python.exe -m pytest tests/golden/test_abstraction_counterexamples.py -q
```

Then pick one summary and resolve its `drill_down.route` by hand to a source byte range.

**Expected**: every summary has an `AbstractionManifest`, the manifest names what it omitted, and the
drill-down resolves to stored bytes.

---

## 6. Verify capability substitution and permission containment

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_provider_swap_invariance.py -q
.venv\Scripts\python.exe -m pytest tests/security/test_derive_cannot_write.py -q
.venv\Scripts\python.exe -m pytest tests/integration/test_capability_gap.py -q
```

**Expected**: swapping a provider changes neither the `ContextDefinition` nor the output contract; a
`DERIVE` capability cannot write canonical state; a missing capability produces a durable gap rather
than a silent substitution.

---

## 7. Verify ambiguity is exposed, not resolved silently

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_ambiguity_materialised.py -q
```

Then submit a request containing an ambiguous name and an ambiguous period and read the compiled
frame.

**Expected**: two or more named interpretation hypotheses, and no committed single meaning without a
visible assumption or a branch.

---

## 8. Verify assembly is inspectable and conflicts survive pruning

```powershell
.venv\Scripts\python.exe -m pytest tests/golden/test_conflict_survives_pruning.py -q
.venv\Scripts\python.exe -m pytest tests/golden/test_answer_cites_assembly.py -q
```

**Expected**: an answer cites its `assembly_digest`; a forced-pruning case either keeps the decisive
conflict or records that the answer was produced without it.

---

## 9. Verify reasoning modes are attributed

```powershell
.venv\Scripts\python.exe -m pytest tests/contract/test_reasoning_modes.py -q
.venv\Scripts\python.exe -m pytest tests/golden/test_causal_non_identifiable.py -q
```

**Expected**: each component of a composed analysis names its mode, assumptions and limit; a
non-identifiable causal question returns non-identifiability, not an estimate.

---

## 10. Verify multimodal grounding

```powershell
.venv\Scripts\python.exe -m pytest tests/golden/test_multimodal_alignment.py -q
```

**Expected**: OCR text resolves to an image box, transcript phrases to audio intervals, and both
survive a rebuild, within the declared tolerance.

---

## 11. Verify memory layers are independent

```powershell
.venv\Scripts\python.exe -m pytest tests/contract/test_memory_layers.py -q
.venv\Scripts\python.exe -m pytest tests/security/test_preference_never_evidence.py -q
```

**Expected**: nine layers with nine scopes; a preference never appears as evidence; expiry records
lineage impact rather than deleting silently.

---

## 12. Verify unknown states and completion honesty

```powershell
.venv\Scripts\python.exe -m pytest tests/contract/test_completion_report.py -q
.venv\Scripts\python.exe -m pytest tests/integration/test_no_stop_on_empty_queue.py -q
.venv\Scripts\python.exe -m pytest tests/golden/test_qualified_absence_requires_detection_power.py -q
```

**Expected**: all fourteen states distinguishable; every terminal state has a `CompletionReport`; an
empty queue is not completion; a qualified absence names its detection power.

---

## 13. Verify API honesty

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_long_running_returns_run.py -q
.venv\Scripts\python.exe -m pytest tests/integration/test_event_only_after_commit.py -q
.venv\Scripts\python.exe -m pytest tests/security/test_dsl_no_code_execution.py -q
```

**Expected**: long work returns a run id; no event precedes its commit; the DSL cannot execute
arbitrary code.

---

## 14. Verify security separation

```powershell
.venv\Scripts\python.exe -m pytest tests/security -q
```

**Expected**: prompt injection is inert, a cross-tenant reference is refused, a model cannot request
an external action, a high-confidence identity match does not authorise collection, and a replay is
re-authorised under current policy.

---

## 15. Verify the conformance and ADR registers are truthful

Open `conformance/suites.md` and `adr/README.md` and check:

- every suite has a status (including `NOT_RUN` with a reason);
- every `PASS` cites a command and an exit status;
- every ADR entry is `OPEN` or `ACCEPTED` with its inputs present;
- no suite is `PASS` without evidence, and no ADR is `ACCEPTED` without its measurements.

**This is the review step that catches the most common failure**: a release report that is green
because nothing was run.

---

## 16. The Definition of Done

Open §35 of Appendix A and walk its bullets. For each:

- name the artifact that demonstrates it;
- name the command that produced the artifact;
- record `PASS`, `FAIL`, `BLOCKED` or `NOT_RUN`.

**Expected**: a table with no blank rows. A blank row is an unmet bullet.

---

## What a reviewer should conclude

If steps 1–16 pass, the runtime is doing what §35 requires: it admits a new domain without a core
change, preserves what it does not understand, accounts for every abstraction, selects by capability
and permission, exposes ambiguity, assembles inspectably, attributes every reasoning mode, grounds
non-text material, scopes memory, classifies unknown, reports honestly, and enforces security as
policy rather than confidence.

If a step cannot run, the correct outcome is `BLOCKED` or `NOT_RUN` with a reason. The blueprint's
governing rule (§35) is that the platform exposes exactly what is evidenced, inferred, assumed,
simulated, disputed or still unknown — and a verification document that hides a `NOT_RUN` violates
that rule more seriously than a missing feature does.
