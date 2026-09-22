# Tasks: Deterministic Entity Extraction Stack

**Input**: Design documents from `1/specs/007-deterministic-entity-extraction-stack/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Tests**: включены (SC-5 требует hermetic-контракты); tests-first по конвенции репо.

**Organization**: по user story; каждый story независим.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallel-safe (разные файлы)
- **[Story]**: US1..US5 из spec.md
- Paths относительны `1/` (репо-рут воркспейса)

## Phase 1: Setup (Shared Infrastructure)

- [x] T001 Add pinned deps: `apps/interpretation/pyproject.toml` (trafilatura, selectolax, extruct, phonenumbers, nameparser, pymorphy3, pyahocorasick, charset-normalizer, pypdf, python-docx, openpyxl, pillow, anyascii, rapidfuzz) + `apps/shared/pyproject.toml` (pyahocorasick, charset-normalizer) + optional extras group `lang-tiers` (simplemma, jieba, fugashi, unidic-lite); `uv lock`

- [x] T002 [P] Create fixture corpus `bench/fixtures/extraction/` (profile.html c JSON-LD+OG, bio_en.txt, bio_ru.txt, cp1251_page.html, contact.html, sample.pdf, sample.docx, sample_exif.jpg, corrupt.bin)
- [x] T003 [P] Scaffold `apps/shared/datasets/` (`__init__.py`, `build.py`) per contracts

**Checkpoint**: deps locked, fixtures ready, dataset scaffold exists.

---

## Phase 2: Foundational (Blocking Prerequisites)

- [x] T004 [P] `apps/shared/datasets/__init__.py`: DictionaryDataset model + lazy automaton loader (pyahocorasick singleton, key kind+version)
- [x] T005 [P] `apps/shared/datasets/build.py`: offline build geonames/sanctions/first_names/surnames → content-addressed store + license metadata
- [x] T006 [P] `apps/interpretation/parsers/registry.py`: charset pre-normalization before dispatch + `extract()` extraction lane (charset-normalizer via `decode_bytes`; `extract_artifact` merges extraction-aware adapters; `extract` stays out of the runtime protocol so legacy parse-only adapters keep passing `isinstance`, NFR-4)
- [x] T007 [P] Unit tests: dataset loader determinism + version stamping (covered in `apps/interpretation/tests/test_deterministic_extraction.py::TestDatasets`)

---

## Phase 3: User Story 1 — Structure-first extraction (P1) 🎯 MVP

**Goal**: entities the artifact declares about itself.

### Tests (first, failing)

- [x] T008 [P] [US1] Contract: `html_full` adapter on profile.html → main text w/o boilerplate (`apps/interpretation/tests/test_deterministic_extraction.py::TestHtmlFull`)
- [x] T009 [P] [US1] Contract: `structured` adapter → JSON-LD/OG mentions + sameAs evidence (`apps/interpretation/tests/test_deterministic_extraction.py::TestStructured`)

### Implementation

- [x] T010 [US1] `apps/interpretation/parsers/html_full.py`: trafilatura adapter (segments w/ offsets, boilerplate excluded)
- [x] T011 [P] [US1] `apps/interpretation/parsers/structured.py`: extruct adapter (JSON-LD/schema.org, OG/meta, microformats) → mentions (source=structure, sameAs evidence)
- [x] T012 [US1] Register adapters into ParserRegistry + `extract_demo` entrypoint (quickstart)
- [x] T013 [P] [US1] Determinism test: double-run byte-identical output on US1 fixtures

**Checkpoint**: `uv run pytest apps/interpretation/tests -q` green; extract_demo works.

---

## Phase 4: User Story 2 — Dictionary & rule person/place extraction (P1)

**Goal**: persons/places from narration without ML.

### Tests (first, failing)

- [x] T014 [P] [US2] Contract: persons extractor on bio_ru/bio_en (`apps/interpretation/tests/contract/test_persons.py`)
- [x] T015 [P] [US2] Contract: places (mini-geonames fixture) + sanctions hit with version stamp (`apps/interpretation/tests/contract/test_dictionary_entities.py`)

### Implementation

- [x] T016 [US2] `apps/interpretation/extractors/persons.py`: nameparser (Latin) + yargy-style grammars with pymorphy3 (ru ФИО, initials shapes) → `source=morph|pattern` (role-based family-first disambiguation for 2-word surfaces added)
- [x] T017 [P] [US2] `apps/interpretation/extractors/places.py`: GeoNames automaton (ru+en alternatenames) → geo-id mentions
- [x] T018 [P] [US2] `apps/interpretation/extractors/dictionary_entities.py`: sanctions matcher → `dictionary=sanctions@version`
- [x] T019 [US2] Register extractors (OntologyPack gate honored) + hermetic mini-fixture datasets for tests (auto-built via `tests/conftest.py`)

**Checkpoint**: extract_demo produces person+place+dictionary mentions deterministically.

---

## Phase 5: User Story 3 — Normalization & identity-relevant evidence (P2)

- [x] T020 [P] [US3] Contract: canonical collapse of declined/initials/transliterated variants (`apps/interpretation/tests/contract/test_normalize.py`)
- [x] T021 [US3] `apps/interpretation/extractors/normalize.py`: pymorphy3 lemmas, translit tables (GOST/ICU + web variants), initials→hypotheses (credence=null), evidence attrs (sameAs/profile/co_occurrence); tier-1 morphology pack only stamped for known languages (honest tier-3 note otherwise)
- [x] T022 [US3] Wire normalization as post-pass in extract_demo + registry

**Checkpoint**: SC-2 verified (canonical forms + hypothesis typing).

---

## Phase 6: User Story 4 — Document & media lane (P2)

- [x] T023 [P] [US4] Contract: documents adapter on sample.pdf/docx/exif.jpg; corrupt.bin → quarantine (`apps/interpretation/tests/contract/test_documents.py`)
- [x] T024 [US4] `apps/interpretation/parsers/documents.py`: pypdf/python-docx/openpyxl text+meta; Pillow EXIF GPS→place mention; quarantine routing
- [x] T025 [P] [US4] OCR escalation stub: tesseract external-process class (typed outcome, skippable when binary absent)

**Checkpoint**: SC-3 verified.

---

## Phase 7: User Story 5 — Language tiers (P2)

- [x] T026 [P] [US5] Contract: cp1251 fixture → clean Cyrillic; lang tags ru/en (`apps/interpretation/tests/contract/test_lang_parity.py`)
- [x] T027 [US5] Tier framework: morphology pack interface (tier1 ru/en registered; tier2/3 typed `lang_pack` notes when absent), stopword-heuristic lang tagger, universal translit via anyascii (SC-4); `pack_note` no longer double-tags (`tier3-dictionary@zh`, not `...@zh@zh`)
- [x] T027b [P] [US5] Multilingual: zh tier-parity test (inline zh artifact in `test_lang_parity.py` — structure mentions identical, morphology note never tier1)


**Checkpoint**: SC-4 verified.

---

## Phase 8: Polish & Cross-Cutting

- [x] T028 [P] Bench: `bench/extraction/bench_extract.py` — determinism hash + per-fixture latency (≈10–60 ms/artifact, run via `uv run --project apps/interpretation python bench/extraction/bench_extract.py`)
- [x] T029 [P] Docs: `docs/architecture/overview.md` interpretation row + spec index (`docs/README.md`)
- [x] T030 Full suite: `apps/interpretation/tests` green (115) + `apps/control-plane/tests` green (141 passed) + `apps/shared/tests` re-checked — pre-existing failures in untracked `apps/shared/websearch` (unrelated feature bug) and infra integration tests (need live kafka/redpanda/minio) are NOT part of spec 007.
- [x] T031 Quickstart validation end-to-end: `extract_demo` on `bench/fixtures/extraction/{profile.html,bio_ru.txt}` → typed JSON (kind/value/offsets/normalized/evidence/dictionary stamp)

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 → stories. US1 и US2 параллельны после Phase 2 (разные файлы); US3 зависит от shapes US1/US2; US4 параллелен US3; US5 замыкает.
- Tests-first: T008/T009/T014/T015/T020/T023/T026 fail до реализации своего story.

## Implementation Strategy

- MVP = Setup + Foundation + US1 (+US2 следом): extract_demo уже показывает типизированные сущности на реальных страницах.
- Каждый story закрывается зелёными контракт-тестами; конфликтов файлов нет (адаптеры/экстракторы разнесены).


