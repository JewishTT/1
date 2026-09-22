# Data Model: Deterministic Entity Extraction Stack

## TypedMention (extension of `apps/interpretation/extractors` Mention)

| Field | Type | Notes |
| --- | --- | --- |
| kind | str | person, org, place, email, phone, handle, domain, ip, crypto, doc_meta, evidence_link |
| value | str | raw surface value (as appears in the artifact) |
| offset / end_offset | int | byte offsets into the decoded artifact |
| extractor | str | extractor id (`html_full`, `structured`, `persons`, `places`, `contacts`, …) |
| lang | str\|None | heuristic language tag (`ru`/`en`/None) from the charset+script step |
| source | enum | `structure` \| `pattern` \| `morph` \| `context` \| `coords` (honest degradation, FR-4) |
| confidence | float | 1.0 for structural; reduced for pattern/context-only; never `0` |
| normalized | NormalizedName\|None | canonical form + transform chain where applicable |
| evidence | dict | sameAs[], profile_urls[], contact_hashes[], coords (for EXIF→place) |
| lang_pack | str | morphology pack name/level used for normalization/expansion, if any (e.g. `pymorphy3@ru`) |

## NormalizedName

| Field | Type |
| --- | --- |
| canonical | str (e.g. `Иванов Сергей`) |
| latin | str\|None (`Ivanov Sergei`) |
| given / family / patronymic | str\|None |
| transforms | list[str] (e.g. `pymorphy3-lemma`, `anyascii-translit`, `initials-expand`) |
| hypothesis | bool (True for initials-expansion variants; credence marked `null`) |

## ExtractionResult

| Field | Type |
| --- | --- |
| artifact_sha | str (content address) |
| content_type | str (detected after charset normalization) |
| segments | list[Segment] (existing model; lang field added) |
| mentions | list[TypedMention] |
| quarantined | bool + reason (existing DLQ semantics) |

Invariants:
- Mentions never resolved to entities here (I-2); only data and evidence attributes.
- Deterministic: no wall-clock, no randomness, no network in extraction lane.
- Honest source: `structure > coords/context > morph > pattern`.

