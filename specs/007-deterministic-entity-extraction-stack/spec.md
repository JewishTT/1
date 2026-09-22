---
description: "Specification for the Deterministic Entity Extraction Stack: a no-ML, structure/dictionary/rule-based extraction layer that pulls every typed entity (persons, orgs, places, contacts, identifiers, document metadata) out of collected artifacts — deterministically, offline, on top of proven open-source components"
---

# Feature Specification: Deterministic Entity Extraction Stack

**Feature Branch**: `007-deterministic-entity-extraction-stack`

**Created**: 2026-09-19

**Status**: Draft

**Input**: User description: "Сначала — стек извлечения сущностей и данных: детерминированное, без ML извлечение практически любых сущностей из собранных артефактов, на качественных open-source инструментах, не изобретая велосипед. Discovery/поиск и оркестрация пивотов — отдельные будущие фичи."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Structure-first extraction: entities the artifact declares about itself (Priority: P1)

Given a collected artifact (HTML page, JSON payload, plain text), the extraction lane
surfaces every entity the artifact *explicitly declares*: embedded structured semantics
(JSON-LD / schema.org, OpenGraph, microformats2, RDFa, meta tags) are parsed into typed
mentions via an extruct-class library; clean main text is separated from boilerplate by
a readability-class extractor so body segments exclude navigation/footers; contact
entities are normalized (email; phone numbers to E.164 via phonenumbers; messenger
handles `t.me`/`tg://`; social profile URLs; domains; IPs; crypto addresses via the
existing pattern extractors). No neural/statistical model weights at runtime; the same
artifact processed twice yields byte-identical mention sets. Every mention keeps its
byte offset and the extractor id that produced it.

**Why this priority**: Structured data is the highest-precision, lowest-cost source of
entities on the modern web — most pages already *state* who they talk about
(schema.org `Person`/`Organization` with `sameAs`, emails, phones). Today
`apps/interpretation` extracts none of it (the NER module is an empty file; parsing is
bare stdlib text). This story turns the existing Observation → Mention chain into a
real entity producer with the cheapest, most reliable machinery first.

**Independent Test**: A fixture corpus (an HTML profile page embedding JSON-LD + OG
meta + a body bio, a JSON artifact, a plain-text bio) runs twice; output contains
person/org/contact mentions with offsets and extractor ids, JSON-LD `sameAs` surfaces
as typed evidence attributes, boilerplate is excluded from body segments, and both
runs are byte-identical with zero network calls.

**Acceptance Scenarios**:

1. **Given** an HTML artifact embedding schema.org/JSON-LD (`Person` with `sameAs`, `email`, `telephone`, `address`) **When** parsed **Then** the mention set includes those typed values with source `json-ld`, plus main-text mentions from the readability-cleaned body, and boilerplate is excluded from body segments.
2. **Given** an HTML artifact with OpenGraph/meta author/geo tags **When** parsed **Then** the tag values surface as typed mentions with source `meta`.
3. **Given** the same artifact processed twice **When** outputs are compared **Then** they are identical (determinism), and each mention records `extractor=<id>` and byte `offset`.

---

### User Story 2 - Dictionary & rule-based name/place extraction: persons and places without ML (Priority: P1)

Given clean text segments, the extraction lane finds persons and places
deterministically: person names are segmented into given/family/patronymic parts by
rule+dictionary machinery — `nameparser`-class parsing for Latin names, yargy/natasha-
style grammars with pymorphy3 morphology for Russian (surname/patronymic endings,
initial patterns `И. О. Фамилия`, `Фамилия И. О.`), a first-name/surname dictionary
filter (downloaded, versioned), and Aho-Corasick gazetteer matching (pyahocorasick)
over GeoNames places and an OpenSanctions-derived entity dictionary. Matches degrade
honestly: a token sequence that only *pattern-matches* but is not in any dictionary is
emitted with lower confidence and `source=pattern`, never silently dropped, never
promoted to a resolved entity (I-2: mentions stay mentions).

**Why this priority**: This is the "extract practically any entity without ML" core —
structure (US1) covers what pages declare; dictionaries+grammar cover what pages
narrate. Deterministic, offline, license-clean, and fast (Aho-Corasick scales to
millions of dictionary terms).

**Independent Test**: A ru/en fixture corpus (bios, news-like paragraphs, contact
pages) produces person mentions with normalized name parts, place mentions with
GeoNames ids, and dictionary entity hits with their dictionary version recorded;
reruns are identical; no network, no model files.

**Acceptance Scenarios**:

1. **Given** a Russian plain-text bio "Иванов, Сергей Петрович родился в Казани…" **When** parsed **Then** the person mention carries normalized `given=Сергей family=Иванов patronymic=Петрович` (declension-resolved via pymorphy3) and "Казани" resolves to a GeoNames place mention with geo-id.
2. **Given** a text containing a name listed in the OpenSanctions-derived dictionary **When** parsed **Then** a mention with `dictionary=sanctions@<version>` and its entity id is produced.
3. **Given** a capitalized token sequence matching name shape but absent from dictionaries **When** parsed **Then** a `pattern`-sourced person mention with reduced confidence is emitted (not dropped, not resolved).

---

### User Story 3 - Normalization & identity-relevant evidence extraction (Priority: P2)

Extracted mentions are normalized so downstream identity work is deterministic:
ru declensions collapse to lemmas (pymorphy3), transliteration tables (ICU/GOST and
common web variants) map Cyrillic↔Latin forms, initials expand into *hypothesis*
variants (И. О. Фамилия → full-name candidates with credence, not claims), names are
segmented consistently regardless of input form ("Фамилия И. О." vs "Имя Отчество
Фамилия"). Structured identity links (`sameAs`, `url` in JSON-LD; profile URLs in
meta) and document-local co-occurrence (two mentions in one artifact) surface as
typed evidence attributes on mentions — feeding the existing resolution lane later,
without performing resolution here (I-2/I-6 stay outside this feature).

**Why this priority**: Without canonical forms, the same person extracted from ten
pages is ten different strings; normalization is what makes the stack's output
*joinable*. It is still pure rules and tables — no ML.

**Independent Test**: Declined/initials/transliterated variants of the same name all
normalize to one canonical form in the mention's `normalized` attribute; structured
`sameAs`/profile links appear as evidence attributes; expansion hypotheses are
recorded with credence placeholders, never as resolved claims.

**Acceptance Scenarios**:

1. **Given** "Сергеем Ивановым", "Сергей Иванов", and "Sergey Ivanov" in three artifacts **When** normalized **Then** all three produce canonical form `Иванов Сергей` (+ latin form) with a recorded transform chain.
2. **Given** "И. О. Иванов" in text **When** normalized **Then** expansion candidates (given/patronymic pairs consistent with initials) are emitted as hypotheses with `credence=null` placeholder, never as resolved persons.
3. **Given** a JSON-LD `sameAs` array **When** extracted **Then** each link becomes an identity-evidence attribute on the corresponding mention.

---

### User Story 4 - Document & media lane: PDF/Office/EXIF through hardened parsers (Priority: P2)

Given binary artifacts collected into observations (PDF, DOCX/XLSX, images), the
extraction lane renders them into text segments and typed metadata: PDF text +
metadata (pypdf/pdfminer-class), office documents (python-docx/openpyxl-class),
image EXIF (device, timestamps, GPS coordinates → place mentions via the US2
gazetteer), all routed through the existing size/depth/time quarantine hardening.
OCR (tesseract, invoked as an external process) is an escalation path for image-only
pages, marked as a distinct execution class with its own cost unit.

**Why this priority**: The most valuable payloads (résumés, scans, photos with geo,
office docs) are binaries that today go straight to quarantine and yield nothing.

**Independent Test**: Fixture PDF/DOCX/JPEG artifacts produce text segments + metadata
mentions (including an EXIF GPS → place mention); oversized/corrupt inputs are
quarantined with preserved payloads, never crashing the pipeline.

**Acceptance Scenarios**:

1. **Given** a PDF artifact **When** parsed **Then** text segments carry offsets, document metadata (author/producer/dates) surfaces as typed mentions, and the artifact hash is preserved.
2. **Given** a JPEG with EXIF GPS **When** parsed **Then** a location mention with coordinates + GeoNames resolution is produced and linked to the observation.
3. **Given** a corrupt or oversized binary **When** parsed **Then** it is quarantined via `events.dlq` semantics with the payload preserved for replay.

---

### User Story 5 - Language tiers: universal core + per-language morphology packs (Priority: P2)

The stack is language-agnostic by construction: the structure layer (US1) and the
gazetteer/dictionary layer (US2) are script-agnostic and work for every language the
dictionaries cover. Language-specific behavior is confined to swappable morphology
packs with three tiers:

- **Tier 1 (full)**: Russian and English — extraction, declension lemmas (pymorphy3),
  name segmentation, initials expansion, transliteration, full normalization.
- **Tier 2 (structural+dictionary)**: European languages (uk, pl, de, fr, es, tr, …) —
  name-shape grammars + suffix dictionaries + universal gazetteer; normalization via
  universal transliteration (anyascii-class); morphology is honestly absent
  (`source=dictionary|pattern`, never `morph`).
- **Tier 3 (dictionary-only)**: scripts without word boundaries or with heavy
  agglutination (CJK, Arabic, Thai) — lightweight dictionary segmentation packs
  (jieba-class) + dictionary names; structure layer applies unconditionally.

Language is tagged by charset-script ranges + stopword heuristics (no model); charset
detection (charset-normalizer-class) always precedes decoding; the same fixture page
must extract identically regardless of the language pack installed (packs only
upgrade confidence tiers, never change mention counts for structural matches).

**Why this priority**: The platform's working context includes the Russian-language
segment (Tier 1 first-class), but "extract practically any entity" means the core
must not silently degrade for other languages — and blind utf-8 decoding destroys
windows-1251/koi8-r pages today.

**Independent Test**: A windows-1251 page decodes to clean Cyrillic; a ru/en parallel
corpus shows Tier-1 parity (persons+places+normalization); a Chinese/Japanese fixture
produces dictionary-tier person mentions via segmentation + gazetteer (or a typed
`lang_pack_unavailable` note — never silent absence); structural (JSON-LD) mentions
extract identically on a multilingual page set.

**Acceptance Scenarios**:

1. **Given** a windows-1251 encoded HTML page **When** collected and parsed **Then** charset is detected and text segments contain valid Cyrillic (no replacement mojibake).
2. **Given** equivalent ru/en bios **When** extracted **Then** both produce person+place mentions with comparable completeness and a recorded language hint.
3. **Given** a CJK fixture with a segmentation pack installed **When** parsed **Then** dictionary-tier person mentions appear; **Given** the pack absent **When** parsed **Then** structural mentions still extract and a typed `lang_pack` note is recorded (no silent zero).
4. **Given** the same multilingual page set **When** extracted with different installed packs **Then** structure-sourced mention sets are identical; only non-structural confidence/normalization fields differ.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-1**: Extraction is deterministic: identical inputs produce identical mention sets; no runtime model weights; after dictionary/gazetteer datasets are installed, the whole lane runs offline.
- **FR-2**: Extraction coverage: main-text/boilerplate separation; embedded structured semantics (JSON-LD/schema.org, OpenGraph, microformats2, meta); email/phone/handle/messenger/social/domain/IP/crypto patterns; person names (given/family/patronymic, ru+en) by rules+dictionaries; places via GeoNames gazetteer; dictionary entities via OpenSanctions-derived dictionary.
- **FR-3**: Every mention carries: kind, value, byte offset, extractor id, language hint, source observation reference, and (when applicable) a `normalized` canonical form with its transform chain.
- **FR-4**: Honest degradation: pattern-only matches are emitted with `source=pattern` and reduced confidence — never dropped, never resolved (I-2).
- **FR-5**: Structured identity links (`sameAs`, profile URLs) and document-local co-occurrence surface as typed evidence attributes; no resolution decisions are made in this lane.
- **FR-6**: Binary artifacts (PDF/DOCX/XLSX/images) parse through quarantine-hardened limits; EXIF GPS produces place mentions; OCR is a distinct escalation execution class.
- **FR-7**: Charset detection runs before decoding; language tagging is heuristic (charset+stopwords); ru/en normalization parity.
- **FR-8**: Dictionary/gazetteer datasets are versioned, content-addressed, and their version is recorded in every mention they produce.
- **FR-9**: The parser registry keeps its hardening semantics (size/depth/time limits, deterministic adapter dispatch, quarantine via `events.dlq`); new extractors register into the existing `ExtractorRegistry` and honor the OntologyPack gate (FR-012 semantics).
- **FR-10**: All new components are testable hermetically: injectable file/transport seams, fixture corpora in-repo, no network in unit tests.

### Boundary Requirements *(hard)*

- **B-1**: No sensitive-attribute scoring of natural persons (echoes spec 006 hard boundary): this stack extracts mentions; admission/resolution decide. Out of scope by design.
- **B-2**: License transparency: every OSS dependency's license is *recorded* in provenance/research (no gating — any license is allowed); data licenses (GeoNames, OpenSanctions) recorded as dataset metadata facts.
- **B-3**: No discovery/search, no pivot orchestration, no seed-specific logic in this feature — extraction consumes artifacts that the existing collection fabric already delivers. Discovery reservoirs and pivot orchestration are future features.

### Non-Functional Requirements

- **NFR-1**: Throughput ≥ 2 MB/s/core HTML→mentions on commodity hardware (selectolax/lxml-class parsing); deterministic under parallelism.
- **NFR-2**: Dictionary loads are lazy/cached; Aho-Corasick automatons are built once and reused across parses.
- **NFR-3**: Component failures are typed and isolated; one bad artifact cannot crash the pipeline (existing quarantine semantics).
- **NFR-4**: Full suite stays green (existing conventions: hermetic unit/contract, integration against live stack where applicable).

### Success Criteria *(mandatory)*

- **SC-1**: On the fixture corpus, US1+US2 produce ≥ 6 entity kinds with 100% determinism across reruns and zero network calls.
- **SC-2**: Normalization collapses declined/initials/transliterated variants to one canonical form with recorded transform chains; initials expansion stays hypothesis-typed.
- **SC-3**: Binary lane extracts EXIF geo + PDF text on fixtures; hostile inputs quarantine cleanly.
- **SC-4**: windows-1251 fixture decodes correctly; ru/en parity demonstrated on the parallel fixture corpus.
- **SC-5**: All contract tests follow the T092 injectable-transport seam convention; full pytest suite green.

## Non-Goals *(explicit)*

- Discovery/search reservoirs, entity probes, SERP snapshotting → future feature.
- Pivot orchestration / expansion lattices → future feature.
- Entity resolution decisions, credence updates, I-6 merges → owned by existing resolution/admission lanes.
- ML/neural NER, OCR-model-based extraction → future feature (an escalation seam for tesseract is in scope; model-based NER is not).
- Any seed- or person-specific logic: the stack is generic over entity types; concrete investigations only supply inputs.

## Key Entities

- **TypedMention** (extends existing): kind, value, offsets, extractor id, lang, source observation ref, `normalized` (canonical + transform chain), `evidence` (sameAs/profile/co-occurrence attrs), `dictionary` (name@version when dictionary-sourced), `confidence`, `source` (structure|pattern|dictionary).
- **ExtractionResult**: artifact ref (sha), content-type, segments, mentions, quarantined flag.
- **DictionaryDataset**: kind (geonames|sanctions|first_names|surnames), version, content address, license, loader statistics.

## Assumptions & Dependencies

- The existing seams stay authoritative: `ParserRegistry`/`ParserAdapter` (FR-010), `ExtractorRegistry` + OntologyPack gate, Observation Gate, quarantine/DLQ, content-addressed storage.
- OSS tools are consumed as pinned dependencies or external processes per B-2; vendor-neutral contracts (C-5) preserved — libraries live inside parser/extractor implementations, never inside domain invariants.
- Dictionary datasets are built by a small offline build step into the existing object store (content-addressed), not vendored as source blobs.




