"""Minimal async ClickHouse client over the HTTP interface.

Deliberately not a driver dependency: the store's contract is the seam, and Principle V
requires that domain logic carry no vendor class. ClickHouse's HTTP interface is a plain
POST of a SQL string, so a client is 60 lines and pulls in no package tree.

Usage mirrors the official client for the subset used here::

    async with ClickHouseHTTP(url="http://localhost:8123", database="cognitive") as ch:
        await ch.execute("CREATE TABLE ...")
        rows = await ch.fetch_all("SELECT 1")
"""

from __future__ import annotations

import json
from types import TracebackType
from typing import Any

import httpx


class ClickHouseError(RuntimeError):
    def __init__(self, code: int, message: str, query: str) -> None:
        self.code = code
        self.query = query
        super().__init__(f"[{code}] {message} :: {query[:200]}")


class ClickHouseHTTP:
    """HTTP-interface client. One connection pool per instance; reuse it."""

    def __init__(
        self,
        *,
        url: str = "http://localhost:8123",
        database: str = "cognitive",
        user: str = "default",
        password: str = "",
        timeout: float = 60.0,
    ) -> None:
        self._url = url.rstrip("/")
        self._database = database
        self._auth = (user, password) if password else None
        self._client = httpx.AsyncClient(timeout=timeout)

    async def __aenter__(self) -> ClickHouseHTTP:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    def _params(self) -> dict[str, str]:
        return {"database": self._database} if self._database else {}

    async def execute(self, query: str) -> None:
        response = await self._client.post(
            self._url, params=self._params(), content=query, auth=self._auth
        )
        if response.status_code >= 400:
            raise ClickHouseError(response.status_code, response.text, query)

    async def fetch_all(self, query: str) -> list[dict[str, Any]]:
        response = await self._client.post(
            self._url,
            params={**self._params(), "default_format": "JSONEachRow"},
            content=query,
            auth=self._auth,
        )
        if response.status_code >= 400:
            raise ClickHouseError(response.status_code, response.text, query)
        body = response.text.strip()
        if not body:
            return []
        # JSONEachRow is one object per line; it has to be rejoined with commas before
        # it is a JSON array. Wrapping the raw body in brackets yields invalid JSON.
        return json.loads("[" + ",".join(body.splitlines()) + "]")

    async def ping(self) -> bool:
        try:
            await self.fetch_all("SELECT 1 AS ok")
            return True
        except Exception:
            return False


__all__ = ["ClickHouseError", "ClickHouseHTTP"]
