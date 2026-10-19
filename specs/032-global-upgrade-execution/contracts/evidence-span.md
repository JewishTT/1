# Contract 04 — `EvidenceSpanRef` (delta)

**Feature**: `032-global-upgrade-execution`
**Governs**: how a derived statement points into stored bytes.
**Enforces**: FR-016, FR-017, FR-018; blueprint §4.2.

**Canonical definition**: `specs/030-global-platform-upgrade/contracts/evidence-span.md`. That
document defines the typed union and its rules. This file records the producer-side obligations that
Feature 032 adds, and the behaviour required when a span cannot be reconstructed.

---

## Delta against 030

| # | Added obligation | Source | Why |
|---|---|---|---|
| D1 | The span kind is chosen **at the producer**, from the format the producer actually decoded | §4.2, FR-016 | a display layer that infers the kind can only guess |
| D2 | `selector_semantics_version` is assigned by the producer, not by a later normalizer | §4.2, FR-017 | version laundering erases the ambiguity the field exists to expose |
| D3 | A span that cannot be reconstructed yields a `partial/unresolved` finding, with the failure classified — never a synthetic offset | §4.2, FR-018 | a synthetic offset is a false citation that looks true |
| D4 | Every hop in `finding → claim → derived artifact → observation → span → blob` is resolvable or explicitly broken, with the broken hop named | §4.2, SC-003 | "the chain is mostly there" is not a chain |
| D5 | Two spans with different `selector_semantics_version` are incomparable until an explicit conversion policy is invoked and recorded | §4.2, FR-017 | silent conversion manufactures provenance |

## Span kinds and the producer that owns each

| Kind | Fields | Produced by | Typical defect if owned by the wrong layer |
|---|---|---|---|
| `char_span` | start, end, encoding | HTML/text parser | byte offset interpreted as character offset |
| `page_box` | page, box[x0,y0,x1,y1], coordinate system | PDF/document layout parser | a box without a frame |
| `table_cell` | table_ref, row, column, header_path[] | table reconstruction | row index confused with page line |
| `json_path` | pointer | structured-record parser | array index drift after re-serialisation |
| `time_range` | start, end, track?, frame? | ASR / video segmentation | seconds confused with sample index |
| `warc_record` | record_offset, warc_digest | WARC reader | archive offset without record digest |
| `geometry` | feature_ref, geometry_ref | spatial extractor | geometry without CRS |
| `source_locator` | uri, fragment? | any source that can be re-fetched | a locator that no longer resolves |

---

## Normative rules

### R1 — No bare positional field anywhere

An integer named `offset` may exist inside a typed span as one field of a declared kind. It may not
travel alone, and no consumer may accept one.

### R2 — The frame travels with the coordinate

A page box without `coordinate_system`, a geometry without a CRS, or a time range without a clock
semantics is not a span. It is a number with an aspiration.

### R3 — Integrity is checked, not assumed

At resolution time the span is verified against the stored bytes: the digest matches and the
selector re-derives the same bytes. A span that fails verification becomes `unresolved` with the
failing check named.

### R4 — Failure is a first-class outcome

`unresolved` spans are stored, counted and surfaced. They are not silently dropped from a result
set and they never reduce a finding's status to "grounded".

### R5 — Normalization adds spans, never mutates them

Transliteration, Unicode normalization, translation and alias expansion produce **additional**
candidate forms, each with its own span and lineage. The original span remains the anchor.

### R6 — A conversion policy is a recorded artifact

If two semantics versions must be compared, the conversion is a named, tested, versioned policy,
recorded on the result. A conversion without a policy is a refusal, and the refusal is the required
behaviour.

---

## Prohibitions

- Summing, averaging or comparing spans across semantics versions.
- A "best effort" offset written when reconstruction fails.
- A span that references a transformed representation instead of the original.
- A finding presented as grounded when any hop in its chain is broken.

---

## Tests

| Test | Asserts |
|---|---|
| `tests/integration/test_spans_to_findings.py` (four formats) | R3, D4 |
| `tests/integration/test_spans_unresolved.py` | D3, R4 |
| `tests/contract/test_evidence_span.py::test_cross_version_refusal` | D5, R6 |
| `tests/golden/test_span_survives_rebuild.py` | R3 after a projection rebuild |
