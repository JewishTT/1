# Research: Deterministic Entity Extraction Stack

**Phase 0 output** — resolves all unknowns in Technical Context. Decision / Rationale / Alternatives format per `/speckit.plan`. Constraint from user: **no ML**, reuse proven OSS, license-clean (B-2).

## R-1: HTML main-text/boilerplate extraction library

- **Decision**: `trafilatura` (LGPL-3.0) as the readability/main-text extractor behind the ParserAdapter seam; `selectolax` (MIT, modest-speed lexical HTML parsing over lexbor) for fast structural queries where trafilatura is unnecessary; `justext` (BSD-3) as a fallback boilerplate filter.
- **Rationale**: trafilatura is the strongest open-source main-content extractor (benchmarks consistently above readability-lxml/goose3), deterministic, offline. LGPL is process/library-linkage-safe for our purposes as a pip dependency behind an adapter (B-2: recorded; boundary rule satisfied — it is a separate work of authorship used unmodified).
- **Alternatives**: `readability-lxml` (Apache-2.0, weaker on modern pages); `goose3` (Apache-2.0, unmaintained drift); hand-rolled heuristics (rejected: reinvents a solved problem, violates user directive).

## R-2: Embedded structured semantics (JSON-LD / microformats / meta)

- **Decision**: `extruct` (BSD-3) for JSON-LD, microformats2, microdata, RDFa; direct meta/OG tag extraction via selectolax.
- **Rationale**: extruct is the reference implementation for in-page structured data; deterministic; outputs dicts we map to mentions.

## R-3: Person names without ML

- **Decision**: three-layer deterministic stack:
  1. `nameparser` (MIT) for Latin full-name segmentation;
  2. yargy-style grammar rules + pymorphy3 (MIT) morphology for Russian (surname/patronymic endings, initials patterns), inspired by natasha (MIT) but rule-only — no natasha neural models;
  3. name dictionaries (downloaded first-name/surname lists, e.g. from open datasets + Wikidata labels) as a confidence filter, matched via `pyahocorasick` (MIT).
- **Rationale**: covers "practically any entity without ML": pattern shape → morphology plausibility → dictionary evidence, each layer stamped into the mention (`source=pattern|morph|dictionary`).
- **Alternatives**: spaCy/stanza (rejected for this feature: model weights, violates no-ML constraint); pure regex (rejected: misses declensions).

## R-4: Places and dictionary entities

- **Decision**: GeoNames cities dump (CC-BY 4.0) as versioned content-addressed dataset → pyahocorasick automaton (ru+en alternatenames); OpenSanctions entities (CC-BY 4.0 non-commercial terms — recorded per B-2) as the sanctions/known-entity dictionary; both built by an offline build script into the object store.
- **Rationale**: gazetteer lookup is deterministic, fast (automaton), and scales to millions of terms; versions ride in provenance (FR-8).

## R-5: Phones, contacts, identifiers

- **Decision**: `phonenumbers` (Apache-2.0) for parse/E.164; existing regex extractors remain for email/domain/IP/crypto; messenger handles via link patterns (`t.me`, `tg://`).
- **Rationale**: phonenumbers is the standard deterministic telephony library; no alternatives worth considering.

## R-6: Charset & language

- **Decision**: `charset-normalizer` (MIT) before decoding (replaces blind utf-8-replace); language tag by charset script ranges + stopword heuristics (ru/en; no model).
- **Rationale**: direct fix of the mojibake hole; heuristic language tagging is sufficient for lane routing without ML.

## R-7: Normalization (declensions, transliteration, initials)

- **Decision**: pymorphy3 lemma/declension resolution for ru names; ICU/GOST transliteration via a pinned table module (no new dependency — small pure-Python tables with tests); initials expansion emits typed *hypotheses* (`credence=null`).
- **Rationale**: makes output joinable across pages; keeps I-2/I-6 outside this feature.

## R-8: Binary lane

- **Decision**: `pypdf` (BSD-3) for PDF text+metadata; `python-docx` (MIT) / `openpyxl` (MIT) for office docs; `Pillow` (HPND — permissive, recorded) for EXIF incl. GPS; `tesseract` as external process (GPL — process boundary per B-2) behind an escalation class.
- **Rationale**: all permissive, offline, deterministic; tesseract stays out-of-process.

## R-9: Where the code lives

- **Decision**: extend `apps/interpretation` — new `parsers/html_full.py` (trafilatura adapter), `parsers/structured.py` (extruct adapter), `parsers/documents.py` (pdf/docx/xlsx/image), `extractors/persons.py` / `extractors/places.py` / `extractors/dictionary_entities.py` / `extractors/normalize.py`, `datasets/` (dataset build+load utilities in `apps/shared` for content-addressed dictionaries). All registered into existing registries; OntologyPack gate honored.
- **Rationale**: reuses FR-010/FR-011 seams and quarantine hardening; no new app.

## R-10: Performance approach

- **Decision**: single build of automatons per process (lazy singleton), selectolax-first parsing, trafilatura only when main-text separation is needed; benchmark added to `bench/`.
- **Rationale**: NFR-1 (≥2 MB/s/core) is reachable only with fast lexical parsing + cached automatons.

## R-11: Multilingual tiers

- **Decision**: universal core (structure + gazetteer) is script-agnostic; language behavior isolated in morphology packs:
  - Tier 1: ru (pymorphy3 + yargy grammars) and en (nameparser + suffix rules) — full cycle.
  - Tier 2: European languages — suffix dictionaries + universal gazetteer + `anyascii` (ISC) transliteration; `simplemma` (GPL, теперь допустимо) for dictionary lemmatization where useful.
  - Tier 3: CJK/Arabic/Thai — segmentation packs `jieba` (MIT), `fugashi`+`unidic-lite` (MIT/BSD, optional), `hazm` (MIT), `pythainlp` (Apache-2.0) as optional extras; gazetteer-only extraction when absent, with a typed `lang_pack` note.
- **Rationale**: honest degradation is already FR-4; tiers make multilingual support additive, not blocking.

## R-12: ML/statistical NER modules — explicitly out of scope, opt-in seam

- **Decision**: no neural/statistical models in this feature. The extractor registry accepts future ML extractors through the same seam (spaCy, Gliner, polyglot) — a registration point, not an implementation.
- **Rationale**: user constraint for this feature; the seam keeps the option open without scope creep.

