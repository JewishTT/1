"""Discovery pass endpoint (T027/T028, US3).

``POST /api/v1/discovery/run`` runs one discovery pass for a seed and returns the
report Layer A produced. The pass itself is not reimplemented here: sources,
canonicalisation, coalescing and the frontier write are
``adapters.discovery.DiscoveryRegistry``'s and ``FrontierSinkAdapter``'s, which
are the only code that knows how a candidate is built or where a frontier row
goes.

What this route owns is everything around the pass:

* **tenant scope and role** -- the tenant comes from ``resolve_tenant`` and the
  caller must be an analyst or an admin; a viewer cannot spend the acquisition
  budget a pass spends;
* **the response cap** -- the candidates array is capped (100 by default, 1000 at
  most) while ``candidates_found`` reports the *true* total, so a truncated
  response can never be read as a pass that found nothing more;
* **bounded failures** -- a source that fails does not abort the pass and does
  not fail the request; its error is named, truncated and stripped of tracebacks
  and host paths, and the response says which sources produced nothing;
* **the frontier failure that does matter** -- a pass whose candidates could not
  be committed is a 503, not an empty 200. ``candidates_found`` would be true and
  ``enqueued`` zero, and a caller that believed the pass succeeded would never
  look again.

--------------------------------------------------------------------------
Admission: why a wrapper, and what it does not do
--------------------------------------------------------------------------

``DiscoveryRegistry.register`` admits a source only if it declares a capability
the engine implements, and refuses anything declaring that answering needs an
access control crossed (FR-018, Constitution VII). Every built-in source
declares *more* than it needs to: ``crtsh`` says ``ct-logs, subdomains``,
``wayback-cdx`` says ``archive, cdx``, ``commoncrawl-index`` says ``index, web,
bulk``, ``link-graph`` says ``web-graph, links`` -- and each of those also names
something the engine genuinely does, so each is refused on a label rather than on
a capability.

``AdmittedSource`` declares the one capability that is actually implemented for
that source -- ``api`` for a source that reads a public JSON interface, ``index``
for a data-driven URL index, ``web-graph`` for the graph projection -- and
forwards ``name``, ``access_mode`` and every ``ACCESS_CONTROL_REQUIREMENTS`` flag
untouched, so the registry's access-control refusal still fires and a source that
needs a CAPTCHA, a login or a paywall is still refused. What is narrowed is a
label, not a wall, and every narrowing is reported in the response's
``sources_admitted`` so the decision is auditable rather than silent.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Annotated, Any

import adapters.discovery

# Layer A: hermetic, synchronous, dependency-free (FR-005/FR-006).
from adapters.discovery import DiscoveryRegistry
from adapters.discovery.registry import (
    ACCESS_CONTROL_REQUIREMENTS,
    ALLOWED_CAPABILITIES,
    DiscoverySourceRefused,
)
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import TenantContext, require_analyst
from db.session import make_session_factory
from services.discovery_frontier import FrontierSinkAdapter, LinkEdgeProvider, canonical_host
from services.query_planner import _error_text
from services.search_backends import search_projection

# The vendor source modules are loaded by file path, not by dotted name.
#
# On this workspace's interpreter the import machinery's directory finder
# resolves ``adapters.discovery.<name>`` to nothing while still resolving the
# bare ``<name>`` from that same directory, so ``from
# adapters.discovery.commcrawl_index import CommonCrawlIndexSource`` dies with
# ModuleNotFoundError for a file that demonstrably exists and is listed by that
# very finder. The failure is specific to *dotted* lookups into this package
# once the app's path shims have reordered sys.path, and it is a property of
# the interpreter, not of these modules.
#
# Loading by path is the workaround this repo already uses for cross-app
# modules it cannot import by name (``api/routes/network.py`` loads
# ``tda/features.py`` that way, and ``services/search_backends.py`` loads the
# projection search modules that way). Each module is registered under its real
# dotted name in ``sys.modules`` and bound on the package before it executes, so
# the modules keep working as ordinary members of ``adapters.discovery``:
# their own ``from .contracts import ...`` resolves against the package the
# import above already initialised, and any later dotted import anywhere in
# the process hits the sys.modules entry instead of the finder.
_DISCOVERY_DIR = Path(adapters.discovery.__file__).parent


def _load_discovery_source(name: str) -> ModuleType:
    """Load ``adapters/discovery/<name>.py`` under its real dotted name."""
    fullname = f"adapters.discovery.{name}"
    existing = sys.modules.get(fullname)
    if existing is not None:
        return existing
    path = _DISCOVERY_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(fullname, path)
    if spec is None or spec.loader is None:  # pragma: no cover - unreadable install
        raise ImportError(f"cannot load the discovery source at {path}")
    module = importlib.util.module_from_spec(spec)
    module.__package__ = fullname.rpartition(".")[0]
    sys.modules[fullname] = module
    setattr(adapters.discovery, name, module)
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(fullname, None)
        delattr(adapters.discovery, name)
        raise
    return module


_CommonCrawlIndexSource = _load_discovery_source("commoncrawl_index").CommonCrawlIndexSource
_CrtshSource = _load_discovery_source("crtsh").CrtshSource
_LinkGraphSource = _load_discovery_source("linkgraph").LinkGraphSource
_WaybackCdxSource = _load_discovery_source("wayback_cdx").WaybackCdxSource

router = APIRouter(prefix="/discovery", tags=["discovery"])

#: Candidate array cap. The report's ``candidates_found`` is never capped -- it is
#: the number the pass actually found, and a cap that hid it would turn "there are
#: more" into "there are none" (Constitution Invariant 9).
DEFAULT_CANDIDATE_CAP = 100
MAX_CANDIDATE_CAP = 1000

#: A source error is a label on a response, not a log line.
SOURCE_ERROR_MAX = 200

_TRACEBACK_MARKER = "Traceback (most recent call last)"

# An absolute path anchored at a token boundary, so ``/var/lib/x`` and ``C:\x``
# are redacted while intra-token slashes ("a/b", "api/v1") are not. Same rule the
# planner applies to backend degradation notices; a source that fails over a
# socket or a temp directory must not put host layout in a response body either.
_ABSOLUTE_PATH = re.compile(r"(^|[\s'\"=(])(?:[A-Za-z]:)?[\\/][^\s'\"]*")


class DiscoveryRunRequest(BaseModel):
    seed: str = Field(min_length=1)
    seed_type: str = "domain"  # domain | entity | url
    investigation_id: str = Field(default="", max_length=64)
    sources: list[str] | None = None
    limit: int = Field(default=DEFAULT_CANDIDATE_CAP, ge=1, le=MAX_CANDIDATE_CAP)
    priority: int = 0


class AdmittedSource:
    """One production source, declaring only the capability the engine implements.

    See the module docstring: this narrows a declared label and forwards the
    access-control declarations verbatim. It is not a subclass and not a wrapper
    around a registry -- ``discover`` is the source's own method, so the real
    source does all the work and nothing here can answer a query.
    """

    def __init__(self, source: Any, capability: str) -> None:
        if capability not in ALLOWED_CAPABILITIES:
            raise ValueError(f"{capability!r} is not a capability the engine implements")
        self._source = source
        self._capability = capability
        # Forwarded, not defaulted: the registry reads these with getattr, and a
        # flag the source raised must reach it whatever this wrapper declares.
        self.access_mode = getattr(source, "access_mode", "public")
        for requirement in ACCESS_CONTROL_REQUIREMENTS:
            if hasattr(source, requirement):
                setattr(self, requirement, getattr(source, requirement))

    @property
    def name(self) -> str:
        return str(self._source.name)

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset({self._capability})

    @property
    def declared_capabilities(self) -> frozenset[str]:
        """What the wrapped source declared, reported so the narrowing is visible."""
        return frozenset(str(cap) for cap in getattr(self._source, "capabilities", ()) or ())

    def discover(self, query: str) -> list[Any]:
        return self._source.discover(query)


def _sources_for(tenant_id: str) -> list[AdmittedSource]:
    """Every production discovery source, each declaring what it really needs."""
    return [
        AdmittedSource(
            _CommonCrawlIndexSource(
                index_uri=os.environ.get("COMMOMCRAWL_INDEX_URI", ""),
                crawl=os.environ.get("COMMOMCRAWL_CRAWL", "latest"),
            ),
            "index",
        ),
        AdmittedSource(_CrtshSource(), "api"),
        AdmittedSource(_WaybackCdxSource(), "api"),
        AdmittedSource(
            _LinkGraphSource(
                edge_provider=LinkEdgeProvider(
                    search_projection().graph_store, tenant_id=tenant_id
                )
            ),
            "web-graph",
        ),
    ]


class _RecordingSink:
    """The durable sink, plus the candidates that went through it.

    ``DiscoveryReport`` carries counts, not the candidates, and the endpoint has
    to return the candidates themselves. Rather than re-run the sources -- which
    would coalesce and enqueue a second time and could disagree with the report --
    this records what the registry handed the sink, in the order it handed it, and
    delegates the write. The registry's own ``enqueued`` count is unaffected: it
    falls back to counting unique canonical candidates for a sink it cannot
    introspect, which is this one.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.candidates: list[dict[str, Any]] = []

    def enqueue(
        self,
        *,
        uri: str,
        tenant_id: str,
        investigation_id: str,
        source: str,
        method: str,
        priority: int = 0,
        provenance: dict[str, Any] | None = None,
    ) -> None:
        self.candidates.append(
            {
                "uri": uri,
                "source": source,
                "method": method,
                "priority": priority,
                "provenance": dict(provenance or {}),
            }
        )
        self._inner.enqueue(
            uri=uri,
            tenant_id=tenant_id,
            investigation_id=investigation_id,
            source=source,
            method=method,
            priority=priority,
            provenance=provenance,
        )


def _bounded_error(entry: dict[str, str]) -> dict[str, str]:
    """``{source, error}`` with the error stripped of stacks, paths and length.

    The registry renders ``type: message`` and hands this module a *string*, so
    the planner's ``_error_text`` -- which takes an exception -- cannot be reused
    here; what is reused is its rule, not its code. The source name is never
    rewritten.
    """
    return {"source": str(entry.get("source") or ""), "error": _bounded_text(str(entry.get("error") or ""))}


def _bounded_text(text: str) -> str:
    """One line, no traceback, no host path, bounded length."""
    if _TRACEBACK_MARKER in text:
        text = text.split(_TRACEBACK_MARKER, 1)[0]
    text = " ".join(text.split())
    text = _ABSOLUTE_PATH.sub(r"\1<path>", text).strip()
    text = " ".join(text.split())
    if len(text) > SOURCE_ERROR_MAX:
        text = text[: SOURCE_ERROR_MAX - 1].rstrip() + "…"
    return text


@router.post("/run")
async def run_discovery(
    body: DiscoveryRunRequest,
    ctx: Annotated[TenantContext, Depends(require_analyst)] = None,
) -> dict[str, Any]:
    """Run one discovery pass for a seed and report what it did."""
    registry = DiscoveryRegistry()
    admitted: list[dict[str, Any]] = []
    refused: list[dict[str, str]] = []
    for source in _sources_for(ctx.tenant_id):
        try:
            registry.register(source)
        except DiscoverySourceRefused as exc:
            refused.append({"source": source.name, "error": _error_text(exc)})
            continue
        admitted.append(
            {
                "source": source.name,
                "capability": min(source.capabilities),
                "declared": sorted(source.declared_capabilities),
            }
        )

    if not registry.names():
        # Nothing could run. A 200 here would report an empty pass that never
        # happened, which is the one answer a caller must not be handed.
        raise HTTPException(
            status_code=503,
            detail={
                "error": "no_admissible_discovery_source",
                "seed": body.seed,
                "tenant_id": ctx.tenant_id,
                "sources_refused": refused,
            },
        )

    sink = _RecordingSink(
        FrontierSinkAdapter(make_session_factory(), host_key_of=canonical_host)
    )
    try:
        report = registry.discover(
            body.seed,
            sources=body.sources,
            frontier=sink,
            tenant_id=ctx.tenant_id,
            investigation_id=body.investigation_id,
            priority=body.priority,
        )
    except Exception as exc:
        # The pass ran and found candidates that could not be committed. Reported
        # as a failure to commit, not as an empty result set.
        raise HTTPException(
            status_code=503,
            detail={
                "error": "frontier_unavailable",
                "seed": body.seed,
                "tenant_id": ctx.tenant_id,
                "cause": _error_text(exc),
            },
        ) from exc

    payload = report.as_dict()
    payload["sources_failed"] = [_bounded_error(entry) for entry in payload["sources_failed"]]
    candidates = sink.candidates
    return {
        "seed": body.seed,
        "seed_type": body.seed_type,
        "tenant_id": ctx.tenant_id,
        "investigation_id": body.investigation_id,
        "report": payload,
        "candidates": candidates[: body.limit],
        "candidates_returned": min(len(candidates), body.limit),
        "candidates_truncated": len(candidates) > body.limit,
        "sources_admitted": admitted,
        "sources_refused": refused,
    }
