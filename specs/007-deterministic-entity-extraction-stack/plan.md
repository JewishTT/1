# Implementation Plan: Deterministic Entity Extraction Stack

**Branch**: `007-deterministic-entity-extraction-stack` | **Date**: 2026-09-19 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `1/specs/007-deterministic-entity-extraction-stack/spec.md`

## Summary

Upgrade the interpretation layer into a deterministic, ML-free entity extraction
stack: structure-first extraction (JSON-LD/schema.org/OG/microformats via extruct;
main-text/boilerplate separation via trafilatura), dictionary+rule person/place
extraction (nameparser, pymorphy3, yargy-style grammars, pyahocorasick over GeoNames
+ OpenSanctions-derived dictionaries), canonical normalization (declensions,
transliteration, initials-as-hypotheses), a binary lane (PDF/DOCX/XLSX/EXIF,
tesseract escalation), and ru/en lane parity (charset-normalizer before decode).
Everything plugs into the existing `ParserRegistry`/`ExtractorRegistry` seams with
quarantine hardening preserved.

## Technical Context

**Language/Version**: Python 3.11 (uv workspace), Rust only where existing workers already are (untouched here)

**Primary Dependencies**: trafilatura (LGPL-3.0, unmodified pip dep), selectolax (MIT), extruct (BSD-3), phonenumbers (Apache-2.0), nameparser (MIT), pymorphy3 (MIT), pyahocorasick (MIT), charset-normalizer (MIT), pypdf (BSD-3), python-docx (MIT), openpyxl (MIT), Pillow (HPND, recorded); tesseract as external GPL process (B-2 boundary)

**Storage**: existing content-addressed object store for dictionary datasets; no new databases

**Testing**: pytest (hermetic unit/contract; integration against live stack per existing conventions)

**Target Platform**: Windows dev box + Linux containers (k8s path)

**Project Type**: monorepo app extension (`apps/interpretation`, `apps/shared`)

**Performance Goals**: ≥ 2 MB/s/core HTML→mentions; automaton build once per process

**Constraints**: offline after dataset install; no model weights; deterministic byte-identical reruns; GPL only as external process

**Scale/Scope**: single extraction lane; ~8 new modules; dictionary build step

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **C-4/C-5 (no vendor crossing / vendor-neutral domain logic)**: PASS — all libraries live behind ParserAdapter/extractor seams; domain invariants untouched.
- **C-7 (isolation, hostile-input safety)**: PASS — new parsers route through existing size/depth/time quarantine; tesseract stays an external process.
- **I-2 (Mention != Candidate != Entity)**: PASS — this feature only emits mentions + evidence attributes; initials expansion is hypothesis-typed.
- **I-5 (no blobs on Kafka)**: PASS — extraction reads from storage refs; emits nothing to Kafka directly.
- **B-2 license discipline**: PASS — permissive deps vendored as pip pins; LGPL trafilatura unmodified; GPL tesseract external process; data licenses recorded per dataset.
- **006 hard boundary**: PASS — no sensitive-attribute scoring; extraction is type-generic.

## Project Structure

### Documentation (this feature)

```text
1/specs/007-deterministic-entity-extraction-stack/
├── plan.md              # This file (/speckit.plan output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── parser-adapter.md
│   ├── extractor-adapter.md
│   └── dictionary-dataset.md
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root: `1/`)

```text
1/apps/interpretation/
├── parsers/
│   ├── html_full.py         # NEW: trafilatura adapter (main text + boilerplate)
│   ├── structured.py        # NEW: extruct adapter (JSON-LD/OG/microformats)
│   ├── documents.py         # NEW: pypdf/python-docx/openpyxl/Pillow EXIF adapter
│   └── registry.py          # EXISTING: registers new adapters, hardening kept
├── extractors/
│   ├── persons.py           # NEW: nameparser + yargy/pymorphy3 grammars
│   ├── places.py            # NEW: GeoNames automaton (pyahocorasick)
│   ├── dictionary_entities.py # NEW: OpenSanctions dictionary matcher
│   ├── normalize.py         # NEW: canonical forms, translit, initials→hypotheses
│   └── registry.py          # EXISTING: registration + OntologyPack gate
└── tests/                   # NEW: contract/unit fixtures (ru/en corpora, binaries)

1/apps/shared/
├── datasets/
│   ├── __init__.py          # NEW: DictionaryDataset model + loader
│   └── build.py             # NEW: offline build scripts (geonames/sanctions → store)
└── tests/unit/datasets/     # NEW
```

**Structure Decision**: extend the existing `apps/interpretation` app and add a small
dataset utility under `apps/shared` — no new apps, no new services; all seams already
exist (FR-010 parser contract, extractors registry, quarantine).

## Complexity Tracking

> No constitution violations — table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
