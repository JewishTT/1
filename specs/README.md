# Specs Index — the Global Platform Upgrade pair

**Created**: 2026-10-19 · **Spec Kit**: `specify-cli 1.2.2.dev0`

This index exists for one reason: the two owner-supplied blueprints are versions of **one programme**,
and a reader who lands in either spec directory needs to know which document governs what. Without
it, `032` and `033` look like two competing programme specs — exactly what the v2.0 blueprint forbids
(§33: *"It should not become a competing spec with independent source-of-truth."*).

---

## The pair

| Feature | Source document | Version | Governs | Status |
|---|---|---|---|---|
| [`030-global-platform-upgrade`](./030-global-platform-upgrade/spec.md) | owner narrative + CE-001 | — | Context Engine design, Research Obligation model, closed-loop kernel narrative | Draft (pre-existing) |
| [`032-global-upgrade-execution`](./032-global-upgrade-execution/spec.md) | `COGNITIVE_Global_Upgrade_Blueprint.md` | **v1.0** | The execution and authority contract for the programme: one evidence seam, typed spans, identity/conflict authority, donor gate, WP0–WP12 order | Draft, WP0 not run |
| [`033-universal-context-runtime`](./033-universal-context-runtime/spec.md) | `COGNITIVE_Global_Upgrade_Blueprint (1).md` | **v2.0** | The Universal Context Runtime extension: open context model, abstraction accounting, capability registry, assembly, honest completion, conformance regime | Draft, Phase A not run |

## Which document governs

1. **The v2.0 blueprint's sections 0–14 are the v1.0 body.** For those sections, `032` is the
   operational spec and `033` does not re-specify them.
2. **The v2.0 blueprint's sections 15–36 are the extension.** For those, `033` is the spec and `032`
   does not re-specify them.
3. **Both appendices are verbatim.** `032/spec.md` Appendix A is the v1.0 document; `033/spec.md`
   Appendix A is the v2.0 document. Where a spec's narrative and its appendix differ, the appendix
   governs.
4. **Feature 030 remains the Context Engine design authority.** Neither `032` nor `033` creates a
   second engine, a second canonical store or a parallel memory system.

## Provenance

| Feature | Source SHA-256 | Bytes | Lines |
|---|---|---|---|
| 032 | `CC62D760A40AC5DBB40A6527FA597F12AC60A0A1378A91AD3CFBD8F013BA4E25` | 74 836 | 757 |
| 033 | `7B645578F210454CA3FE6FC96D2A18D5699E0D5CC1A1A609E3AB08BBE9BD32C6` | 167 121 | 1 979 |

Both are reproduced byte-for-byte and verified by
[`tools/specs/inject_verbatim_source.ps1`](../tools/specs/inject_verbatim_source.ps1), which
re-injects and re-hashes. The verification command is also embedded in each spec so a reviewer does
not need the tool.

## Artifact layout

```text
specs/032-global-upgrade-execution/
├── spec.md              specification + Appendix A (v1.0 verbatim)
├── plan.md              execution strategy, constitution gate, WP dependency order
├── tasks.md             T001–T084 across WP0–WP12 and US1–US9
├── data-model.md        ownership map, four identity kinds, temporal and epistemic models
├── quickstart.md        eleven verification steps with commands
├── checklists/          requirements quality gate
└── contracts/           9 contracts: evidence seam, acquisition task, operator result,
                         evidence span, conflict record, resolution decision,
                         research obligation, projection manifest, donor registry

specs/033-universal-context-runtime/
├── spec.md              specification + Appendix A (v2.0 verbatim)
├── plan.md              phases A–H, constitution gate, relationship to 030/032
├── tasks.md             T001–T084 across phases A–H and US1–US12
├── data-model.md        context frame, element, relations, dimensions, abstraction,
                         capability, assembly, memory, completion
├── quickstart.md        sixteen verification steps with commands
├── checklists/          requirements quality gate
├── contracts/           9 contracts: frame, element, abstraction manifest,
                         capability manifest, assembly manifest, completion report,
                         memory layers, API and events, model gateway
├── adr/                 the twenty §34 ADRs and their required inputs
├── conformance/         the eighteen §32.1 suites and the status vocabulary
└── corpus/              the fifteen §32.2 golden fixtures
```

## How to verify the pair

```powershell
# 1. Both appendices are intact
.\tools\specs\inject_verbatim_source.ps1 `
  -SpecPath .\specs\032-global-upgrade-execution\spec.md `
  -SourcePath C:\Users\tim\Downloads\COGNITIVE_Global_Upgrade_Blueprint.md

.\tools\specs\inject_verbatim_source.ps1 `
  -SpecPath .\specs\033-universal-context-runtime\spec.md `
  -SourcePath "C:\Users\tim\Downloads\COGNITIVE_Global_Upgrade_Blueprint (1).md"

# 2. The pair creates no second authority
Select-String -Path .\specs\032-global-upgrade-execution\plan.md,.\specs\033-universal-context-runtime\plan.md `
  -Pattern "second authority|competing|030-global-platform-upgrade"
```

Both must print `Verbatim : True`. Neither plan may describe a new canonical store, engine or memory
system.

## Honest current state

- `032`: **WP0 has not run.** No capability in the matrix is `wired` or `live-proven`; the contracts
  and tasks define what must be proven, not what has been.
- `033`: **Phase A has not run.** All eighteen conformance suites are `NOT_RUN`; all twenty ADRs are
  `OPEN`; all fifteen golden fixtures are defined but unexecuted.
- The registers say so explicitly. That is deliberate: the blueprints' own standard is that a claim
  without a command, a version and an exit status is not a claim.
