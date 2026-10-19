# Contract 05 — `ContextAssemblyManifest`

**Feature**: `033-universal-context-runtime`
**Governs**: the exact snapshot a model, solver or operator received.
**Enforces**: FR-040…FR-045; blueprint §22.

---

## Why this contract exists

The blueprint names the failure it prevents: *"Это позволяет проверить, почему агент ответил именно
так и не был ли ключевой конфликт отрезан компактизацией."*

Without an assembly manifest, the only explanation available for a conclusion is "the model was given
the context". With one, an analyst can see that the decisive contradiction was pruned for budget and
that the answer was produced without it.

---

## Shape

```text
ContextAssemblyManifest
├── question                  REQUIRED   the specific question, not the whole goal
├── output_schema             REQUIRED
├── included[]
│   └── { ref, kind, reason_included }      REQUIRED   one reason per element
├── excluded[]
│   └── { ref, reason }                      REQUIRED   reason ∈ {irrelevant, duplicate,
│                                                        inaccessible, over_budget, stale}
├── revisions
│   ├── context_revision      REQUIRED
│   ├── ontology_revision     REQUIRED
│   ├── policy_version        REQUIRED
│   └── time_cut              REQUIRED
├── summary_links[]
│   └── { summary_ref, source_refs[] }      REQUIRED for every summary included
├── abstraction_manifests[]   REQUIRED for every abstraction included
├── budget
│   ├── tokens / bytes / rows REQUIRED
│   └── pruning_decisions[]   REQUIRED   what was dropped and why
├── must_not_omit
│   ├── unresolved_conflicts[] REQUIRED
│   └── unknowns[]             REQUIRED
├── privacy
│   ├── filters[]             REQUIRED
│   └── redactions[]          REQUIRED
├── assembly_digest           REQUIRED
└── renderer_version          REQUIRED
```

---

## Normative rules

### R1 — Every inclusion and exclusion has a reason

An element with no recorded reason is either unexplained or the manifest is incomplete. Both are
defects. The five exclusion reasons are the closed vocabulary; "other" is not a reason.

### R2 — Conflicts and unknowns are protected

`must_not_omit.unresolved_conflicts[]` and `unknowns[]` are assembled **before** budget packing, and
a packing decision that would drop one is recorded as such. The answer must state that it was
produced without it.

### R3 — Budget packing is auditable

`pruning_decisions[]` records what was dropped, for which budget (tokens, bytes, rows) and by what
rule. A truncation without a record is a silent evidence loss.

### R4 — Summary links travel

A summary included in the assembly carries its `source_refs[]` and its `AbstractionManifest`. A
summary without them is a claim with no path back.

### R5 — The digest is cited

Every answer produced from an assembly cites `assembly_digest`. An answer that cannot cite its
assembly cannot be reviewed.

### R6 — Time cut is explicit

`time_cut` is part of the assembly, not a property of the store. An answer assembled from a stale cut
is a different answer, and it says so.

### R7 — Privacy filters are applied before assembly

Redaction happens before the material enters the assembly, and the redactions are listed. Redacting
after the model has seen the content is not redaction.

### R8 — The compiler is versioned

`renderer_version` identifies the code that shaped the context. Two answers from different compiler
versions are not directly comparable, and the version makes that visible.

---

## Prohibitions

- An assembly with an included element and no reason.
- Dropping an unresolved conflict without recording it.
- A summary without source links.
- An answer without an assembly digest.
- Redacting after model ingestion.
- A budget "just large enough" with no pruning record.

---

## Tests

| Test | Asserts |
|---|---|
| `tests/contract/test_assembly_manifest.py::test_every_item_has_reason` | R1 |
| `tests/golden/test_conflict_survives_pruning.py` | R2 |
| `tests/golden/test_pruning_is_recorded.py` | R3 |
| `tests/golden/test_answer_cites_assembly.py` | R5 |
| `tests/security/test_redaction_before_assembly.py` | R7 |
