# Contracts: Deterministic Entity Extraction Stack

## ParserAdapter (extends FR-010, `apps/interpretation/parsers/registry.py`)

Existing protocol unchanged (`can_parse`/`parse` → deterministic findings). New
adapters conform and add structured output through the ExtractionResult lane:

```text
ParserAdapter (existing)
  + name: str, content_types: list[str]
  + can_parse(artifact) -> bool          # detection; deterministic
  + parse(artifact) -> list[Segment]     # segments only (existing registry path)
  + extract(artifact) -> ExtractionResult  # NEW optional method: segments + mentions
```

Rules:
- New adapters (`html_full`, `structured`, `documents`) register into `ParserRegistry`
  and inherit size/depth/time quarantine — no limits bypassed.
- Charset normalization happens BEFORE `can_parse` (registry-level pre-step, FR-7).
- Deterministic dispatch stays name-sorted; same artifact → same adapter.

## Extractor (extends FR-011, `apps/interpretation/extractors/registry.py`)

Existing `Extractor = Callable[[str], list[Mention]]` stays; new extractors are
registered the same way and return TypedMention-shaped dicts:

```text
extractors.register("persons", persons_extractor)        # nameparser + pymorphy3 + yargy grammars
extractors.register("places", places_extractor)          # GeoNames automaton (lazy singleton)
extractors.register("sanctions", dictionary_extractor)   # OpenSanctions automaton (lazy singleton)
extractors.register("normalize", normalization_pass)     # post-pass: canonical forms + hypotheses
```

Rules:
- OntologyPack gate honored for every emitted kind (FR-012 semantics).
- Mentions carry `source` honestly: structure > dictionary > morph > pattern.
- No extractor performs resolution or network I/O.

## DictionaryDataset build/load (B-2, FR-8)

```text
uv run python -m apps.shared.datasets.build --kind geonames --version <release> --out s3://knowledge/datasets/
uv run python -m apps.shared.datasets.build --kind sanctions --version <release> ...
```

- Build scripts are offline, idempotent, content-addressed output; license recorded.
- Loaders are lazy singletons keyed by (kind, version); automaton built once per process.
