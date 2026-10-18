# Contract 02 — `EvidenceSpanRef`

**Feature**: `030-global-platform-upgrade`
**Governs**: how any derived result points at the exact source bytes.
**Enforces**: FR-004, FR-005, FR-006, SC-004, SC-005.

---

## Why this contract exists

**[MEASURED] 2026-10-14 — the defect that motivates it.**

> `Segment.offset` means **byte offset** in one parser, **segment index** in another, and is always
> **`0`** in a third. All three are then summed into a single field at
> `apps/interpretation/…/extractors/lane.py:82-86`.
>
> Downstream, `document_adapter.py:271-300` consumes the span to mint a `mention_id` and then
> **discards it**. `ResolutionMention` has **no span field at all**.

The consequence is exact: a span that grounds a mention is destroyed after use, and the one field
that survives means three different things. Any system claiming evidence-first is, at that point,
claiming it without evidence.

**This contract does not fix that code — WP5 does.** What it does is make the required semantics
explicit and make the current state a contract violation that CI can fail on.

---

## Shape

```text
EvidenceSpanRef
├── observation_ref            REQUIRED   the immutable observation this points into
├── blob_digest                REQUIRED   content address of the raw bytes
├── selector                   REQUIRED   exactly one variant
│   ├── char_span              { start, end, encoding }
│   ├── page_box               { page, box: [x0, y0, x1, y1], coordinate_system }
│   ├── table_cell             { table_ref, row, column, header_path[] }
│   ├── json_path              { pointer }
│   ├── time_range             { start, end, track?, frame? }
│   ├── geometry               { feature_ref, geometry_ref }
│   ├── warc_record            { record_offset, warc_digest }
│   └── source_locator         { uri, fragment? }
├── source_locator             REQUIRED   how to re-fetch the source
└── selector_semantics_version REQUIRED   which producer wrote it — see R2
```

---

## Normative rules

### R1 — There is no bare positional field

A span is a **typed union**, never an integer. Any new producer adds a selector variant plus a
semantics version, or it does not emit spans.

### R2 — `selector_semantics_version` is mandatory

It names the producer convention. This is what makes the conflation detectable:

> Two spans with **different** `selector_semantics_version` MUST NOT be compared, summed, or
> converted implicitly. When no conversion exists, the system **refuses** and reports the ambiguity
> (FR-006).

Refusal is the required behaviour. A "best-effort" merge of two unknown conventions silently
manufactures wrong provenance.

### R3 — Coordinates carry their frame

`page_box.coordinate_system` is required (e.g. `pdf_points`, `pixel_top_left`, `geo_wgs84`). A box
without a frame is not a location. Where a coordinate was produced by a transform from source data,
the span references the **original representation**, not the transform output.

### R4 — Spans survive into derived identity candidates

`ResolutionMention` gains a span field. A resolution candidate presented to an analyst for a
merge/split decision MUST carry the span of each side's evidence, or be explicitly rendered
un-grounded (FR-004, FR-005).

### R5 — Findings resolve or degrade visibly

The chain is `Finding → claim → derived artifact → observation → span → blob`. If any hop fails to
resolve, the finding renders as **partial / unsupported / hypothesis**. It never renders as grounded
(FR-005, SC-004).

### R6 — Normalization never rewrites a span

Transliteration, Unicode normalization and alias expansion produce **additional candidate forms**.
The original text, script and span are retained unchanged. A normalized span is a new span with its
own lineage back to the original.

### R7 — Reparsing creates new spans, never mutates old ones

A new parser version emits new spans under a new operator version. Prior spans remain retrievable
(FR-003, P1).

### R8 — The raw object is the ground truth, not the span

The span is a **pointer**. The blob digest is the **identity**. If a span and the blob disagree, the
blob wins and the span is reported as stale with the mismatch recorded.

---

## Round-trip requirement

**Given** a stored raw document, **when** a span is resolved, **then** it MUST yield the exact
substring / page region / cell / field that produced the derived text — byte-identical after the
declared encoding, with no normalisation applied.

This is a machine-checked property (`roundtrip` test per selector variant), not a review comment.

---

## Anti-patterns this contract forbids

| Forbidden | Why |
|---|---|
| `offset: int` shared across producers | **[MEASURED]** three incompatible meanings summed at `lane.py:82-86` |
| Span consumed to build an id, then discarded | **[MEASURED]** `document_adapter.py:271-300` — provenance destroyed |
| Coordinate without a frame | Not a location |
| Implicit conversion between semantics versions | Manufactures wrong provenance |
| Zero as "no position" | Indistinguishable from "position zero" |
| Normalisation applied to the stored span | Destroys byte-level grounding |
| Parser v2 overwriting v1 spans | Violates P1 immutability of prior interpretations |

---

## Validation

| Check | On failure |
|---|---|
| Exactly one selector variant present | reject |
| `selector_semantics_version` present and known | reject |
| `blob_digest` matches the observation's stored digest | flag stale span |
| `page_box.coordinate_system` present | reject |
| `char_span.end > char_span.start` | reject |
| Span resolves against the stored blob | mark ungrounded, never silently drop |
| Producer's declared semantics version matches the emitted version | reject |

---

## Example

```json
{
  "observation_ref": "obs-91c4",
  "blob_digest": "sha256:3d7b1f…",
  "selector": {
    "table_cell": {
      "table_ref": "tbl-2",
      "row": 14,
      "column": 3,
      "header_path": ["Region", "Q3 2026", "Approved units"]
    }
  },
  "source_locator": { "uri": "https://example.org/report.pdf", "fragment": "page=7" },
  "selector_semantics_version": "table_cell/2"
}
```

`header_path` is required for a cell span because a bare `(row, column)` is meaningless once the
table is filtered — and filtering is routine. A span that only resolves under one incidental filter
is not a stable address.