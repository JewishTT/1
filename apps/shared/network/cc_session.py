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
from urllib.parse import urlsplit

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
    subset: str = ""
    warc_record_id: str = ""

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
            "subset": self.subset,
            "warc_record_id": self.warc_record_id,
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
    crawl: str = ""
    subset: str = ""

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

    def query_domain(
        self, url_pattern: str, *, surt_prefix: str | None = None, match_type: str = "domain"
    ) -> list[CCPageRecord]:
        """Return exact-host hits from either legacy or current CC schema.

        The current URL index names capture fields ``fetch_time``,
        ``fetch_status``, ``content_mime_type``, ``content_digest`` and
        ``warc_record_*``.  Small hermetic fixtures still use the older names,
        so aliases are resolved from the parquet schema instead of guessing.
        Host matching is boundary-aware: ``example.com`` never matches
        ``example.computer`` or ``example.com.evil``.
        """
        raw = url_pattern.strip().rstrip("/")
        if not raw:
            return []
        parsed = urlsplit(raw if "://" in raw else f"//{raw}")
        host = (parsed.hostname or raw).lower().rstrip(".")
        if host.startswith("www."):
            host = host[4:]
        if not host:
            return []

        description = self._conn.execute(
            "SELECT * FROM read_parquet(?) LIMIT 0", [self.index_path]
        ).description
        columns = {str(item[0]) for item in description}

        def column(*names: str, default: str = "NULL") -> str:
            for name in names:
                if name in columns:
                    return f'"{name}"'
            return default

        url_col = column("url")
        time_col = column("fetch_time", "timestamp", default="CAST(NULL AS VARCHAR)")
        status_col = column(
            "fetch_status", "status", default="CAST(NULL AS BIGINT)"
        )
        mime_col = column(
            "content_mime_type", "mime", default="CAST(NULL AS VARCHAR)"
        )
        digest_col = column(
            "content_digest", "digest", default="CAST(NULL AS VARCHAR)"
        )
        filename_col = column("warc_filename", "filename")
        offset_col = column("warc_record_offset", "offset", default="CAST(NULL AS BIGINT)")
        length_col = column("warc_record_length", "length", default="CAST(NULL AS BIGINT)")
        crawl_col = column("crawl")
        subset_col = column("subset")
        record_id_col = column("warc_record_id", "record_id")
        host_col = column(
            "url_host_name",
            default=(
                f"regexp_extract(lower({url_col}), "
                "'^[a-z][a-z0-9+.-]*://([^/:?#]+)', 1)"
            ),
        )

        registered_host_col = column("url_host_registered_domain")
        if match_type == "domain" and registered_host_col != "NULL":
            host_col = registered_host_col
            where = [f"lower({host_col}) = lower(?)"]
            params = [host]
        else:
            where = [f"(lower({host_col}) = lower(?) OR lower({host_col}) LIKE lower(?))"]
            params = [host, f"%.{host}"]
        if crawl_col != "NULL" and self.crawl:
            where.append(f"lower({crawl_col}) = lower(?)")
            params.append(self.crawl)
        if subset_col != "NULL" and self.subset:
            where.append(f"lower({subset_col}) = lower(?)")
            params.append(self.subset)
        if "url_surtkey" in columns and surt_prefix:
            where.append("lower(\"url_surtkey\") LIKE lower(?)")
            surt = surt_prefix.removeprefix("http://").rstrip(",/")
            params.append(surt if surt.endswith("%") else f"{surt}%")

        sql = f"""
            SELECT {url_col}, {time_col}, {status_col}, {mime_col}, {digest_col},
                   {filename_col}, {offset_col}, {length_col},
                   {crawl_col}, {subset_col}, {record_id_col}
            FROM read_parquet(?)
            WHERE {' AND '.join(where)}
            ORDER BY {url_col}, {time_col}
        """
        rows = self._conn.execute(sql, [self.index_path, *params]).fetchall()
        return [
            CCPageRecord(
                url=str(r[0] or ""),
                timestamp=str(r[1] or ""),
                status=int(r[2] or 0),
                mime=str(r[3] or ""),
                digest=str(r[4] or ""),
                warc_filename=str(r[5] or ""),
                offset=int(r[6] or 0),
                length=int(r[7] or 0),
                crawl=str(r[8] or self.crawl),
                subset=str(r[9] or self.subset),
                warc_record_id=str(r[10] or ""),
            )
            for r in rows
        ]

    def query_hosts(self, limit: int = 50) -> list[str]:
        """Deterministic host inventory (for surface/feedback)."""
        rows = self._conn.execute(
            "SELECT DISTINCT regexp_extract(lower(\"url\"), "
            "'^[a-z][a-z0-9+.-]*://([^/:?#]+)', 1) AS h "
            "FROM read_parquet(?) WHERE h != '' ORDER BY h LIMIT ?",
            [self.index_path, limit],
        ).fetchall()
        return [r[0] for r in rows]


_URL_STRIP = re.compile(r"^https?://(www\.)?")


def hostname_of(url: str) -> str:
    """Deterministic bare host for feedback/frontier dedup (FR-015)."""
    s = _URL_STRIP.sub("", url.strip())
    return s.split("/", 1)[0].split("?")[0].split("#")[0]


__all__ = ["CCPageRecord", "CcIndexSession", "Transport", "hostname_of"]