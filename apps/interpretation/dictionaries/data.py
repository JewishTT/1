"""Lazy dataset loaders for the deterministic extractors (spec 007, FR-8).

Resolves the hermetic mini datasets committed under ``dictionaries/data/``
(env-overridable via ``COGNITIVE_DATASET_ROOT`` for hermetic tests),
verifies their content address and returns process-wide cached Aho-Corasick
automatons (NFR-2: automaton built once per process, keyed by kind+version).
"""

from __future__ import annotations

import os
from pathlib import Path

from datasets import AutomatonCache, DictionaryDataset, load_meta, shared_cache

from .build_mini import VERSIONS

_DEFAULT_ROOT = Path(__file__).resolve().parent / "data"


def dataset_root() -> Path:
    """Root directory of the mini datasets (env override for hermetic tests)."""
    override = os.environ.get("COGNITIVE_DATASET_ROOT")
    return Path(override) if override else _DEFAULT_ROOT


def set_dataset_root(path: str | Path) -> Path:
    """Point the loader at another dataset root (T092 injectable seam)."""
    root = Path(path)
    os.environ["COGNITIVE_DATASET_ROOT"] = str(root)
    return root


def _resolve(kind: str, version: str) -> tuple[DictionaryDataset, Path]:
    root = dataset_root()
    meta_path = root / f"{kind}_{version}.meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(
            f"dataset {kind}@{version} not built; run 'python -m dictionaries.build_mini'"
        )
    return load_meta(meta_path), root / f"{kind}_{version}.jsonl"


def load(kind: str) -> AutomatonCache:
    version = VERSIONS[kind]
    meta, data_path = _resolve(kind, version)
    cache: AutomatonCache = shared_cache()
    cache.get(meta, data_path=data_path)
    return cache


def automaton(kind: str) -> tuple[DictionaryDataset, object]:
    """(dataset-meta, built automaton) for a dataset kind (lazy, cached)."""
    version = VERSIONS[kind]
    meta, data_path = _resolve(kind, version)
    cache = shared_cache()
    return meta, cache.get(meta, data_path=data_path)


def dataset(kind: str) -> DictionaryDataset:
    return _resolve(kind, VERSIONS[kind])[0]


def geonames() -> AutomatonCache:
    """GeoNames city/country gazetteer automaton (lazy singleton)."""
    return load("geonames")


def sanctions() -> AutomatonCache:
    """OpenSanctions-derived dictionary automaton (lazy singleton)."""
    return load("sanctions")


def first_names() -> AutomatonCache:
    """RU/EN first-name dictionary automaton (lazy singleton)."""
    return load("first_names")


def surnames() -> AutomatonCache:
    """Surname dictionary automaton (lazy singleton)."""
    return load("surnames")


def companies() -> AutomatonCache:
    """Company/organization dictionary automaton (lazy singleton)."""
    return load("companies")