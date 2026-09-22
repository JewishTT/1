"""Production-grade BM25 search backend (feature 010, slice 2).

Thin adapter over [tantivy](https://github.com/quickwit-oss/tantivy) (Rust, Lucene-like)
that implements the same contract surface as ``RankedInvertedIndex``.
"""

from __future__ import annotations

import os
import re

from domain import enforce_projection_provenance

try:
    import tantivy
except ImportError:
    tantivy = None

import path_shim  # noqa: F401
from search.relevance import RelevanceHit, _TOKEN_RE

_TITLE_DOC_KINDS = {"documents", "observations"}
