"""Offline build of the hermetic mini content-addressed datasets (spec 007).

Reads the pure-python dictionaries of this package and emits canonical,
content-addressed JSONL + meta sidecars into ``dictionaries/data/`` using the
shared ``datasets.build`` canonicalizer (same inputs → same bytes → same
sha256, FR-8). Each term is stored in original and lowercased form so the
gazetteer can run over case-folded text deterministically.

Usage (from the repo root):
    uv run --project apps/interpretation python -m dictionaries.build_mini

The generated files are committed so extraction runs fully offline (FR-1).
"""

from __future__ import annotations

from pathlib import Path

from datasets import build as dataset_build

from . import cities, companies, countries, first_names, sanctions

DATA_DIR = Path(__file__).resolve().parent / "data"

VERSIONS = {
    "geonames": "2026.08",
    "sanctions": "2026.09",
    "first_names": "2026.08",
    "surnames": "2026.08",
    "companies": "2026.08",
}

LICENSES = {
    "geonames": "CC-BY-4.0 (GeoNames public city data, derived)",
    "sanctions": "CC-BY-4.0 (OpenSanctions-derived test fixture)",
    "first_names": "public-domain name lists",
    "surnames": "public-domain name lists",
    "companies": "public company registries, factual names",
}


def _with_lower_variants(entries: list[dict]) -> list[dict]:
    """Duplicate every term as its case-folded form (deterministic order)."""
    out: list[dict] = []
    for entry in entries:
        term = str(entry["term"]).strip()
        out.append(entry)
        folded = term.casefold()
        if folded != term:
            out.append({"term": folded, "payload": entry["payload"]})
    return out


def build_all(*, out_dir: Path | None = None) -> list[Path]:
    out_dir = out_dir or DATA_DIR
    built: list[Path] = []
    jobs = {
        "geonames": [*cities.CITY_ALIASES, *countries.COUNTRY_ALIASES],
        "sanctions": sanctions.sanctioned_entries(),
        "first_names": first_names.first_name_entries(),
        "surnames": first_names.surname_entries(),
        "companies": companies.company_aliases(),
    }
    for kind, entries in jobs.items():
        data_path, _, _ = dataset_build.build(
            kind=kind,
            version=VERSIONS[kind],
            license_note=LICENSES[kind],
            input_bytes=_to_bytes(_with_lower_variants(entries)),
            out_dir=out_dir,
        )
        built.append(data_path)
    return built


def _to_bytes(entries: list[dict]) -> bytes:
    import json

    lines = [json.dumps(e, ensure_ascii=False, separators=(",", ":"), sort_keys=True) for e in entries]
    return ("\n".join(lines) + "\n").encode("utf-8")


if __name__ == "__main__":
    for path in build_all():
        print(f"built {path}")
    print("mini datasets ready")