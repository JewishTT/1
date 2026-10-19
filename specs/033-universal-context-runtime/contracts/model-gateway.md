# Contract 09 — Model Gateway

**Feature**: `033-universal-context-runtime`
**Governs**: every LLM, embedding, reranker, OCR, ASR, VLM and specialist model call.
**Enforces**: FR-066…FR-069; blueprint §28.

---

## Why this contract exists

A model is a dependency with a version, a jurisdiction, a price, a data-use policy and a failure
mode. Treating it as a function call hides all five.

The blueprint's most important sentence here is the last: *"Every LLM output must distinguish
extracted quotation, normalized value, inferred claim, generated summary and speculation."* Those are
five different epistemic objects, and a gateway that returns one undifferentiated string has already
destroyed the distinction.

---

## Shape

```text
ModelProviderManifest
├── provider              REQUIRED
├── model                 REQUIRED   exact identifier
├── version               REQUIRED   immutable snapshot where the provider offers one
├── modality[]            REQUIRED   text | image | audio | video | structured
├── languages[]           REQUIRED
├── context_limits        REQUIRED
├── input_schema          REQUIRED
├── output_schema         REQUIRED
├── cost                  REQUIRED   per token/unit, or `null` with a reason
├── policy
│   ├── regions[]         REQUIRED
│   ├── data_residency    REQUIRED
│   └── eligibility[]     REQUIRED
├── execution
│   ├── timeout           REQUIRED
│   ├── retry             REQUIRED
│   ├── fallback          REQUIRED   explicit chain, or none
│   └── concurrency_cap   REQUIRED
├── prompt_template       REQUIRED   versioned
├── input_manifest_digest REQUIRED
├── validator             REQUIRED   schema + repair policy
├── outcomes              REQUIRED   refusal | error | partial semantics
├── quality
│   ├── eval_results      REQUIRED
│   └── benchmark_set     REQUIRED
├── data_use
│   ├── retention         REQUIRED
│   └── training_use      REQUIRED
└── operations
    ├── disable_switch    REQUIRED
    └── fallback_semantics REQUIRED
```

## The five output classes

```text
ModelOutput
├── extracted_quotation[]   verbatim material, with span refs
├── normalized_value[]      a parsed/normalized form, with the source form and rule
├── inferred_claim[]        a claim the model asserts, with premises and confidence
├── generated_summary[]     a summary, with an AbstractionManifest
└── speculation[]           explicitly flagged speculation
```

A response that cannot be classified into one of these is refused by the gateway.

---

## Normative rules

### R1 — Identity is exact

`provider` and `model` are exact identifiers, and `version` is an immutable snapshot where the
provider offers one. "gpt-latest" is not an identity.

### R2 — Fallback is not silent

A fallback carries the same output contract, the same jurisdiction and the same privacy
characteristics, or it is refused. A fallback that changes region or data use is a different model
call and requires a new authorisation.

### R3 — Determinism is not transferable

Where a deterministic result is required, an LLM is not a substitute for a parser or solver. The
gateway refuses to present a model output as a deterministic result.

### R4 — Output is classified

Every output carries the five classes of §28. A consumer can rely on `extracted_quotation` being
verbatim and on `speculation` being labelled.

### R5 — The prompt is versioned

`prompt_template` and `input_manifest_digest` are recorded, so an output can be reproduced or at
least attributed. An unversioned prompt is an unreproducible input.

### R6 — Validation and repair are explicit

The output validator and its repair policy are declared. A repair that changes meaning is a refusal,
not a repair.

### R7 — Data use is tracked

Retention and training-use terms are recorded per provider. A provider whose terms are unknown cannot
be used for content above the configured classification.

### R8 — The switch works

`disable_switch` disables the provider and its fallbacks degrade explicitly. There is no silent
continuation on a provider the platform believes it has disabled.

### R9 — Model output is never source evidence

A model output is a derived artifact. It never enters the observed-claim store, and its provenance
names the model, prompt and inputs.

---

## Prohibitions

- A call with an unversioned model or prompt.
- A silent fallback to a different jurisdiction or data-use regime.
- A model output presented as a deterministic parse.
- An unclassified output string.
- Raw sensitive content sent to a provider outside its eligibility.
- Model confidence used as evidence quality.

---

## Tests

| Test | Asserts |
|---|---|
| `tests/contract/test_model_gateway.py::test_output_requires_classification` | R4 |
| `tests/integration/test_fallback_preserves_jurisdiction.py` | R2 |
| `tests/security/test_model_not_used_for_deterministic.py` | R3 |
| `tests/integration/test_disable_switch.py` | R8 |
| `tests/golden/test_model_output_never_observed_claim.py` | R9 |
