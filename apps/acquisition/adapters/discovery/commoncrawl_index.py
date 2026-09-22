"""Common Crawl columnar index source (FR-002).

Queries the CC Parquet index directly on object storage — data-driven, no
external query service (Constitution I/III: immutable, versioned substrate).

The Parquet reader is injected (``query_fn``) so contract tests run offline;
the default implementation uses DuckDB with an S3/MinIO-aware config.
"""

from __future__ import annotations

from typing import Any, Callable

from .contracts import Candidate, candidates_from_urls

QueryFn = Callable[[str], list[dict[str, Any]]]


class CommonCrawlIndexSource:
    """Discovers URLs by querying the Common Crawl columnar index."""

    def __init__(
        self,
        *,
        index_uri: str,
        crawl: str = "latest",
        limit: int = 1000,
        query_fn: QueryFn | None = None,
        s3_endpoint: str | None = None,
        s3_key: str | None = None,
        s3_secret: str | None = None,
    ) -> None:
        self._index_uri = index_uri
        self._crawl = crawl
        self._limit = limit
        self._query_fn = query_fn
        self._s3_endpoint = s3_endpoint
        self._s3_key = s3_key
        self._s3_secret = s3_secret

    @property
    def name(self) -> str:
        return "commoncrawl-index"

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset({"index", "web", "bulk"})

    def discover(self, query: str) -> list[Candidate]:
        rows = self._run_query(query)
        urls = [str(row.get("url", "")) for row in rows if row.get("url")]
        return candidates_from_urls(
            urls,
            source=self.name,
            method="cc-columnar-index",
            query=query,
            confidence=0.7,
            provenance={"index_uri": self._index_uri, "crawl": self._crawl},
        )

    # -- internals ---------------------------------------------------------
    def _run_query(self, query: str) -> list[dict[str, Any]]:
        if self._query_fn is not None:
            return self._query_fn(query)
        return self._duckdb_query(query)

    def _duckdb_query(self, query: str) -> list[dict[str, Any]]:
        """Query the Parquet index with DuckDB (lazy import, offline-safe)."""
        try:
            import duckdb  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - exercised in prod only
            raise RuntimeError(
                "duckdb is required for the default Common Crawl index reader; "
                "inject query_fn or install duckdb"
            ) from exc

        con = duckdb.connect(database=":memory:")
        con.execute("INSTALL httpfs; LOAD httpfs;")
        if self._s3_endpoint:
            con.execute(f"SET s3_endpoint='{self._s3_endpoint}';")
            con.execute("SET s3_use_ssl=false;")
            con.execute("SET s3_url_style='path';")
        if self._s3_key and self._s3_secret:
            con.execute(f"SET s3_access_key_id='{self._s3_key}';")
            con.execute(f"SET s3_secret_access_key='{self._s3_secret}';")

        sql = (
            "SELECT url FROM read_parquet(?) "
            "WHERE url LIKE ? "
            "LIMIT ?"
        )
        pattern = f"%{query.strip()}%"
        rows = con.execute(sql, [self._index_uri, pattern, self._limit]).fetchall()
        con.close()
        return [{"url": row[0]} for row in rows]
