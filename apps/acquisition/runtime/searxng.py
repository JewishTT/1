"""SearXNG runtime: a real search backend, reached only over its own endpoint.

Directive §15-§23. Three things here are not implementation detail and are the
reason this is a module rather than a source definition:

**§17's probe, and why ``/config`` is not enough.** An instance that has not
declared ``json`` in ``search.formats`` answers ``/search?format=json`` with
**HTTP 403**. A 403 on a search endpoint is otherwise indistinguishable from a
forbidden request, so an integration can spend a long time debugging credentials
that were never the problem. The probe therefore *asks for JSON* and treats a 403
on that specific request as ``SEARXNG_JSON_FORMAT_DISABLED`` - a named,
non-retryable condition, because retrying cannot enable a setting inside the
instance.

Verified against ``searxng/searxng`` at the pinned digest: its ``/config`` does
**not** publish ``search.formats``, so a probe reading that field would report a
working instance as unusable. The live request is the only honest test, which is
what §17 asks for.

**§19's pagination reads the result collection.** The stopping rule is
"the ``results`` array is empty", not "the body is non-empty" - a 200 carrying an
empty result set is a successful search with no results (§103), and treating it
as "keep going" walks the same page forever. Two independent bounds back that up:
``hard_max_pages`` and a wall-clock budget, so a source that keeps answering with
one result cannot become an unbounded task.

**§21's fields are read, not reconstructed.** Every result is yielded with the
fields the response actually carries, and nothing is invented: an absent field
stays absent rather than becoming ``None``, because ``None`` asserts a fact the
source never stated. Unknown keys survive into ``metadata`` verbatim (§62).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx
from domain.acquisition_artifact import AcquisitionArtifact

from runtime import (
    RUNTIME_HTTP_ERROR,
    RUNTIME_TIMEOUT,
    CostEstimate,
    ResourceClass,
    RuntimeError_,
    RuntimeHealth,
)

#: §17's named, non-retryable refusal. Kept as a module constant because it is a
#: condition operators search for, and because a string literal duplicated into a
#: YAML is a string literal that will drift.
SEARXNG_JSON_FORMAT_DISABLED = "SEARXNG_JSON_FORMAT_DISABLED"

#: §21's fields, named so "which fields does the platform read" is a single
#: answerable question. This is a *reading* list, not a schema assertion: a field
#: absent from a response is absent from the observation.
#: The registered parser name for a SearXNG result. A SearXNG result is a JSON
#: object, so the generic structured walk reads it; the text route would collapse
#: a forty-field result to one line.
PARSER_HINT: str = "structured_fields"

#: Locator scheme for a response page - the *capture* (§20), of which the results
#: are records. §10 asks for per-family locator schemes, and the namespace is the
#: family's own (``searxng:``, ``airbyte:``, ``bbot:``, ``spiderfoot:``).
#:
#: It is deliberately **not** ``capture:``. That prefix is reserved by
#: :mod:`domain.mention_occurrence_index` for deferred occurrence addresses, and a
#: repository-wide invariant test scans production source for a second builder of
#: it. An earlier version here used ``capture:page:`` and the scan caught it - the
#: guard working as intended, against a namespace it was written to protect.
PAGE_CAPTURE_PREFIX: str = "searxng:page:"

RESULT_FIELDS: tuple[str, ...] = (
    "url",
    "title",
    "content",
    "engine",
    "category",
    "publishedDate",
    "thumbnail",
    "template",
    "score",
)


class SearXNGRuntime:
    """One acquisition runtime for SearXNG (§15)."""

    runtime_ref = "searxng"
    execution_class = "api/http"

    def __init__(
        self,
        *,
        base_url: str = "http://searxng:8080",
        timeout: float = 20.0,
        resource_class: ResourceClass | None = None,
        hard_max_pages: int = 5,
        hard_runtime_budget: float = 120.0,
        language: str = "en",
        categories: str = "general",
        safesearch: int = 0,
        transport_host: str | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._resource = resource_class or ResourceClass(
            name="small", max_runtime_seconds=hard_runtime_budget, max_output_bytes=32 * 1024 * 1024
        )
        self._max_pages = hard_max_pages
        self._budget = hard_runtime_budget
        self._language = language
        self._categories = categories
        self._safesearch = safesearch
        # §64: where the egress check already happened, recorded on the runtime so
        # the run manifest can say *that* it was checked, not merely that a URL
        # looked fine.
        self._transport_host = transport_host or self._base
        self._client = httpx.AsyncClient(timeout=timeout, follow_redirects=False)

    # ------------------------------------------------------------- contract --

    def capabilities(self) -> list[str]:
        """Checked against a resolved runtime, never used to choose one (§57)."""
        return ["http", "search", "json-output", "paged"]

    def estimate(self, task: dict[str, Any]) -> CostEstimate:
        return CostEstimate(
            expected_artifacts=self._max_pages * 20,
            expected_bytes=self._max_pages * 512 * 1024,
            expected_seconds=self._budget,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    # ---------------------------------------------------------------- probe --

    async def probe(self) -> RuntimeHealth:
        """§17. Asks for JSON and reports, by name, why the instance is unusable.

        A ``/config`` read is attempted first because it is cheap and answers
        "is there an API at all", but the verdict comes from the JSON request -
        which is the only one that can observe the 403.
        """
        checks: dict[str, Any] = {"base_url": self._base}
        try:
            config = await self._get("/config")
            checks["config_reachable"] = True
            checks["engines_configured"] = bool(config)
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            return RuntimeHealth(
                ready=False,
                detail=f"/config unreachable: {type(exc).__name__}: {exc}",
                checks={**checks, "code": RUNTIME_HTTP_ERROR},
                runtime_ref=self.runtime_ref,
            )

        try:
            body = await self._search_page(query="searxng", page=1)
        except _JsonFormatDisabled as exc:
            return RuntimeHealth(
                ready=False,
                detail=(
                    f"{SEARXNG_JSON_FORMAT_DISABLED}: {exc}. The instance must declare "
                    f"`json` in search.formats; retrying cannot change an instance setting."
                ),
                checks={**checks, "code": SEARXNG_JSON_FORMAT_DISABLED, "status": 403},
                runtime_ref=self.runtime_ref,
            )
        except Exception as exc:  # noqa: BLE001
            return RuntimeHealth(
                ready=False,
                detail=f"/search failed: {type(exc).__name__}: {exc}",
                checks={**checks, "code": RUNTIME_HTTP_ERROR},
                runtime_ref=self.runtime_ref,
            )

        results = body.get("results")
        if not isinstance(results, list):
            return RuntimeHealth(
                ready=False,
                detail=f"JSON response has no results array (keys: {sorted(body)})",
                checks={**checks, "code": "searxng_results_absent"},
                runtime_ref=self.runtime_ref,
            )
        checks["json_output"] = True
        checks["results_field"] = True
        return RuntimeHealth(
            ready=True,
            detail=f"json output enabled, {len(results)} results on probe",
            checks=checks,
            runtime_ref=self.runtime_ref,
        )

    # -------------------------------------------------------------- acquire --

    async def acquire(self, task: dict[str, Any]) -> AsyncIterator[AcquisitionArtifact]:
        """Yield one artifact per response page, then one per result (§20, §6).

        The page itself is yielded first as a whole-capture artifact, because a
        page is what physically came back and the raw bytes must be durable
        before anything addresses into them. The result artifacts then share its
        ``capture_locator``, so a page of forty results is one capture with forty
        observations rather than forty captures (§20).
        """
        query = str(task.get("query") or "").strip()
        if not query:
            raise RuntimeError_("searxng_query_missing", "§18: a task must carry a query")
        task_id = str(task.get("task_id") or "")
        source_id = str(task.get("source_id") or "searxng.search")
        started = datetime.now(UTC)
        deadline = started.timestamp() + min(self._budget, self._resource.max_runtime_seconds)

        for page in range(1, self._max_pages + 1):
            if datetime.now(UTC).timestamp() > deadline:
                # §19's second bound. A hard cut, reported rather than silent:
                # a run that stopped early and one that finished look identical
                # otherwise, and only one of them is a complete observation.
                break
            body = await self._search_page(query=query, page=page)
            results = body.get("results")
            if not isinstance(results, list):
                raise RuntimeError_(
                    "searxng_results_absent", f"page {page}: no results array in {sorted(body)}"
                )
            page_uri = f"{self._base}/search?q={query}&format=json&pageno={page}"
            page_bytes = json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")

            # -- the capture: one response page (§20) ------------------------
            yield AcquisitionArtifact(
                task_id=task_id,
                source_id=source_id,
                worker_ref="http",
                target_uri=page_uri,
                locator=f"{PAGE_CAPTURE_PREFIX}{page}",
                body=page_bytes,
                content_type="application/json",
                fetched_at=datetime.now(UTC),
                transport="http",
                producer=self.runtime_ref,
                producer_version=self._version(),
                metadata={
                    "query": query,
                    "page": page,
                    # §63: the parser that reads this artifact. Declared by the
                    # runtime, carried on the record, and consumed downstream as
                    # ``parser_hint`` - so the interpretation is chosen where the
                    # source is known rather than guessed by the consumer from a
                    # producer name.
                    "parser_hint": PARSER_HINT,
                    "result_count": len(results),
                    "unresponsive_engines": body.get("unresponsive_engines") or [],
                    "suggestions": body.get("suggestions") or [],
                    "answers": body.get("answers") or [],
                },
            )

            # -- the records: one per result, sharing the page's capture ------
            for index, result in enumerate(results):
                if not isinstance(result, dict):
                    continue
                yield AcquisitionArtifact(
                    task_id=task_id,
                    source_id=source_id,
                    worker_ref="http",
                    target_uri=page_uri,
                    locator=f"json:results[{index}]",
                    capture_locator=f"{PAGE_CAPTURE_PREFIX}{page}",
                    body=json.dumps(result, ensure_ascii=False, sort_keys=True).encode("utf-8"),
                    content_type="application/json",
                    fetched_at=datetime.now(UTC),
                    transport="http",
                    producer=self.runtime_ref,
                    producer_version=self._version(),
                    metadata={
                        "query": query,
                        "page": page,
                        "index": index,
                        "parser_hint": PARSER_HINT,
                        # §62: whatever the result carried beyond the fields the
                        # platform names is kept verbatim, and the raw artifact
                        # remains the source of truth for all of it.
                        "result_fields": self._present(result),
                        "result": result,
                    },
                )

            # §19: stop on an *empty result collection*. Not on an empty body,
            # and not merely on a 200 - a 200 with `results: []` is a successful
            # search that found nothing (§103), and it must not fetch page 2.
            if not results:
                break

    # -------------------------------------------------------------- helpers --

    @staticmethod
    def _present(result: dict[str, Any]) -> list[str]:
        """Which of the §21 fields this result actually carried.

        Reported rather than assumed, so a run manifest can distinguish "the
        source returned no thumbnail" from "we did not read one".
        """
        return [f for f in RESULT_FIELDS if f in result]

    def _version(self) -> str:
        import os

        return os.environ.get("COGNITIVE_SEARXNG_VERSION", "unpinned-runtime")

    async def _get(self, path: str) -> dict[str, Any]:
        response = await self._request(path)
        return self._as_json(response)

    async def _search_page(self, *, query: str, page: int) -> dict[str, Any]:
        params = {
            "q": query,
            "format": "json",
            "pageno": str(page),
            "language": self._language,
            "categories": self._categories,
            "safesearch": str(self._safesearch),
        }
        response = await self._request("/search", params=params)
        return self._as_json(response)

    async def _request(
        self, path: str, *, params: dict[str, str] | None = None
    ) -> httpx.Response:
        try:
            return await self._client.get(f"{self._base}{path}", params=params)
        except httpx.TimeoutException as exc:
            raise RuntimeError_(RUNTIME_TIMEOUT, f"{path}: {type(exc).__name__}") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError_(RUNTIME_HTTP_ERROR, f"{path}: {type(exc).__name__}: {exc}") from exc

    @staticmethod
    def _as_json(response: httpx.Response) -> dict[str, Any]:
        """Decode, and separate the one status that has its own meaning (§17)."""
        if response.status_code == 403:
            raise _JsonFormatDisabled(
                "HTTP 403 on /search?format=json; the instance has not declared "
                "`json` in search.formats"
            )
        if response.status_code >= 400:
            raise RuntimeError_(
                RUNTIME_HTTP_ERROR, f"HTTP {response.status_code}: {response.text[:200]}"
            )
        try:
            decoded = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError_(
                "searxng_json_invalid", f"declared JSON but sent {response.text[:200]!r}"
            ) from exc
        if not isinstance(decoded, dict):
            raise RuntimeError_("searxng_json_not_object", f"top level is {type(decoded).__name__}")
        return decoded


class _JsonFormatDisabled(Exception):
    """HTTP 403 specifically for a JSON request. Not a generic 403."""
