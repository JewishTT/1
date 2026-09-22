# Quickstart: Deterministic Entity Extraction Stack

## Install

```bash
cd 1
uv sync   # pins: trafilatura, selectolax, extruct, phonenumbers, nameparser,
          #         pymorphy3, pyahocorasick, charset-normalizer, pypdf,
          #         python-docx, openpyxl, pillow
```

## Build dictionary datasets (offline, once)

```bash
uv run python -m apps.shared.datasets.build --kind geonames --version 2026.08
uv run python -m apps.shared.datasets.build --kind sanctions --version 2026.09
```

## Extract entities from an artifact

```bash
uv run python -m apps.interpretation.extract_demo 1/bench/fixtures/extraction/profile.html
uv run python -m apps.interpretation.extract_demo 1/bench/fixtures/extraction/bio_ru.txt
```

Output: JSON with segments + typed mentions (kind, value, offsets, extractor,
normalized form, evidence, dictionary version).

## Validate

```bash
uv run pytest apps/interpretation/tests apps/shared/tests/unit/datasets -q
uv run pytest bench/tests -q -k extraction   # determinism + throughput bench
```
