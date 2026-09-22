"""Common Crawl columnar index session (FR-001/FR-002, 011).

Queries the Common Crawl URL index with DuckDB *in place* — without
downloading the 4PB corpus. The CC URL index ships as columnar part files
(single-table URL asserts -> WARC offsets/lengths). We point DuckDB at a
local parquet slice (fixture) or at an index service mirror (S3 Range /
Hugging Face) and issue SQL:

    SELECT * FROM 'cc-index.parquet' WHERE url LIKE '<domain>%'

The zero layer knows nothing about entities: it returns byte-exact WARC
locators (`warc_filename@offset,length`) that `range_pull` turns into pages.

Determinism contract (I-11): same index slice + same query ⇒ same ordered
candidate list. No randomness, no wall-clock dependence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

try:  # duckdb is an optional heavy dep — import lazily at session creation
    import duckdb

    _HAS_DUCKDB = True
except ImportError:  # pragma: no cover - env without duckdb
    duckdb = None  # type: ignore[assignment]
    _HAS_DUCKDB = False


@dataclass(frozen=True)
class CCPageRecord:
    """A normalized page hit from the CC URL index (FR-002)."""

    url: str
    timestamp: str
    status: int
    mime: str
    digest: str
    warc_filename: str
    offset: int
    length: int
    crawl: str

    @property
    def locator(self) -> str:
        """Byte-exact WARC locator consumed by range_pull (S3 range GET)."""
        return f"{self.warc_filename}@{self.offset},{self.length}"

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "timestamp": self.timestamp,
            "status": self.status,
            "mime": self.mime,
            "digest": self.digest,
            "warc_filename": self.warc_filename,
            "offset": self.offset,
            "length": self.length,
            "crawl": self.crawl,
            "locator": self.locator,
        }


class Transport(Protocol):
    """Fetch a byte-range of a CC WARC file (S3 Range Request, FR-003)."""

    async def fetch(self, filename: str, offset: int, length: int) -> bytes: ...


@dataclass
class CcIndexSession:
    """DuckDB session over a CC URL-index parquet slice.

    ``index_path`` points at a columnar file (or a directory of part files).
    A live mirror can be mounted as a partition/object store; tests use a
    committed fixture slice (SC-001/SC-002: ~zero live dependency).
    """

    index_path: str
    crawl: str = "CC-MAIN-2023-40"

    @classmethod
    def available(cls) -> bool:
        return _HAS_DUCKDB

    def __post_init__(self) -> None:
        if not _HAS_DUCKDB:
            raise RuntimeError(
                "duckdb is required for CcIndexSession; add 'duckdb>=1.0' "
                "to the app that constructs it"
            )
        self._conn = duckdb.connect(database=":memory:")
        self._conn.execute("INSTALL parquet; LOAD parquet;")

    def close(self) -> None:
        self._conn.close()

    def query_domain(self, url_pattern: str) -> list[CCPageRecord]:
        """Deterministic candidate hits for a domain prefix (FR-001).

        ``url_pattern`` is a single host/prefix, e.g. ``example.com``.
        Matching: ``url LIKE 'example.com%' OR url LIKE 'www.example.com%'``
        — deterministic, index-friendly (CC index is clustered by host).
        """
        pat = url_pattern.strip().rstrip("/")
        if not pat:
            return []
        pat_q = pat.replace("'", "''")
        like = f"{pat_q}%"
        www = f"www.{pat_q}%"
        rows = self._conn.execute(
            """
            SELECT "url", "timestamp", "status", "mime", "digest",
                   "filename", "offset", "length"
            FROM read_parquet(?) AS p
            WHERE regexp_replace("url",
                    '^[a-zA-Z][a-zA-Z0-9+.-]*://(www[.])?', '') LIKE ?
               OR regexp_replace("url",
                    '^[a-zA-Z][a-zA-Z0-9+.-]*://(www[.])?', '') LIKE ?
            ORDER BY "url", "timestamp"
            """,
            [self.index_path, like, www],
        ).fetchall()
        return [
            CCPageRecord(
                url=r[0],
                timestamp=r[1],
                status=int(r[2] or 0),
                mime=r[3] or "",
                digest=r[4] or "",
                warc_filename=r[5],
                offset=int(r[6]),
                length=int(r[7]),
                crawl=self.crawl,
            )
            for r in rows
        ]

    def query_hosts(self, limit: int = 50) -> list[str]:
        """Deterministic host inventory (for surface/feedback)."""
        rows = self._conn.execute(
            "SELECT DISTINCT hostname(url) AS h FROM read_parquet(?) "
            "WHERE hostname(url) != '' ORDER BY h LIMIT ?",
            [self.index_path, limit],
        ).fetchall()
        return [r[0] for r in rows]


_URL_STRIP = re.compile(r"^https?://(www\.)?")


def hostname_of(url: str) -> str:
    """Deterministic bare host for feedback/frontier dedup (FR-015)."""
    s = _URL_STRIP.sub("", url.strip())
    return s.split("/", 1)[0].split("?")[0].split("#")[0]


__all__ = ["CCPageRecord", "CcIndexSession", "Transport", "hostname_of"]