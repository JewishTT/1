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
import json
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
from sqlalchemy import select
from urllib.parse import parse_qsl, urlsplit

from api.auth import TenantContext, require_analyst
from db.schema import Investigation as InvestigationRow
from db.session import make_session_factory
from services.discovery_frontier import FrontierSinkAdapter, LinkEdgeProvider, canonical_host
from services.query_planner import _error_text
from services.search_backends import search_projection
from security import SecurityBlocked, validate_seed_url
from zero.type_detector import InputType, TypeDetector

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
    seed_type: str | None = None  # inferred from deterministic TypeDetector; public domain/url only
    investigation_id: str = Field(min_length=1, max_length=64)
    sources: list[str] | None = None
    limit: int = Field(default=DEFAULT_CANDIDATE_CAP, ge=1, le=MAX_CANDIDATE_CAP)
    max_enqueue_candidates: int = Field(default=250, ge=1, le=500)
    priority: int = Field(default=0, ge=0, le=100)


class HarvestRunRequest(BaseModel):
    """Bounded zero-layer harvest over a public domain or HTTPS page."""

    seed: str = Field(min_length=1, max_length=2048)
    seed_type: str | None = None
    investigation_id: str = Field(min_length=1, max_length=64)


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

    def __init__(self, inner: Any, *, seed_provenance: dict[str, Any]) -> None:
        self._inner = inner
        self._seed_provenance = dict(seed_provenance)
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
    ) -> bool:
        enriched = dict(provenance or {})
        enriched["zero_layer"] = dict(self._seed_provenance)
        inserted = self._inner.enqueue(
            uri=uri,
            tenant_id=tenant_id,
            investigation_id=investigation_id,
            source=source,
            method=method,
            priority=priority,
            provenance=enriched,
        )
        self.candidates.append(
            {
                "uri": uri,
                "source": source,
                "method": method,
                "priority": priority,
                "provenance": enriched,
                "state": "UNVERIFIED_DISCOVERY_LEAD",
                "claim_admission_allowed": False,
            }
        )
        return bool(inserted)


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
    """Run a tenant- and investigation-bound public discovery pass."""
    detected = TypeDetector().detect(body.seed)
    detected_type = detected.detected_type
    if detected_type not in {InputType.DOMAIN, InputType.URL}:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unsupported_seed_type",
                "detail": "Production Zero Layer intake accepts public domains and HTTP(S) URLs only.",
                "detected_type": detected_type.value,
            },
        )
    if body.seed_type and body.seed_type.lower() != detected_type.value:
        raise HTTPException(status_code=422, detail={"error": "seed_type_mismatch", "detected_type": detected_type.value})
    try:
        if detected_type is InputType.DOMAIN:
            normalized_seed = f"https://{body.seed.strip().lower().rstrip('.')}/"
            validate_seed_url(normalized_seed)
        else:
            normalized_seed = validate_seed_url(body.seed.strip())
        parsed_seed = urlsplit(normalized_seed)
        if parsed_seed.username or parsed_seed.password:
            raise ValueError("URL userinfo is not accepted as a public discovery seed")
        sensitive_query_keys = {"key", "api_key", "token", "access_token", "auth", "password", "signature", "sig"}
        if any(key.lower() in sensitive_query_keys for key, _ in parse_qsl(parsed_seed.query, keep_blank_values=True)):
            raise ValueError("credential-like query parameters are not accepted in a discovery seed")
        query_anchor = parsed_seed.hostname or ""
        if not query_anchor:
            raise ValueError("seed has no host")
    except (SecurityBlocked, ValueError) as exc:
        raise HTTPException(status_code=422, detail={"error": "invalid_public_seed", "detail": str(exc)}) from exc

    async with make_session_factory()() as session:
        investigation = (
            await session.execute(
                select(InvestigationRow).where(
                    InvestigationRow.investigation_id == body.investigation_id,
                    InvestigationRow.tenant_id == ctx.tenant_id,
                )
            )
        ).scalar_one_or_none()
    if investigation is None:
        raise HTTPException(status_code=404, detail="investigation not found")
    state = str(getattr(investigation.state, "value", investigation.state)).upper()
    if state not in {"DRAFT", "PLANNING", "RUNNING"}:
        raise HTTPException(status_code=409, detail=f"investigation does not accept discovery in state {state}")
    scope = investigation.scope if isinstance(investigation.scope, dict) else {}
    allowed_types = scope.get("allowed_discovery_seed_types")
    if isinstance(allowed_types, list) and detected_type.value not in {str(x).lower() for x in allowed_types}:
        raise HTTPException(status_code=403, detail="seed type is outside the investigation discovery scope")
    # Link-graph is intentionally withheld here: its current production provider
    # enforces tenant scope but not investigation scope.
    safe_sources = {
        InputType.DOMAIN: {"commoncrawl-index", "crtsh", "wayback-cdx"},
        InputType.URL: {"commoncrawl-index", "wayback-cdx"},
    }[detected_type]
    scoped_sources = scope.get("allowed_discovery_sources")
    if isinstance(scoped_sources, list):
        safe_sources &= {str(x) for x in scoped_sources}
    requested_sources = set(body.sources) if body.sources is not None else set(safe_sources)
    if not requested_sources or not requested_sources.issubset(safe_sources):
        raise HTTPException(status_code=403, detail={"error": "discovery_source_outside_scope", "allowed_sources": sorted(safe_sources)})
    seed_id = detected.seed_id
    seed_provenance = {
        "seed_id": seed_id,
        "seed_type": detected_type.value,
        "detector_confidence": round(float(detected.confidence), 6),
        "entrypoint": "api.v1.discovery.run",
        "claim_admission_allowed": False,
    }
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
        FrontierSinkAdapter(make_session_factory(), host_key_of=canonical_host),
        seed_provenance=seed_provenance,
    )
    try:
        report = registry.discover(
            query_anchor,
            sources=sorted(requested_sources),
            frontier=sink,
            tenant_id=ctx.tenant_id,
            investigation_id=body.investigation_id,
            priority=body.priority,
            max_enqueues=body.max_enqueue_candidates,
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
        "seed": normalized_seed,
        "seed_id": seed_id,
        "seed_type": detected_type.value,
        "detector_confidence": round(float(detected.confidence), 6),
        "tenant_id": ctx.tenant_id,
        "investigation_id": body.investigation_id,
        "report": payload,
        "candidates": candidates[: body.limit],
        "candidates_returned": min(len(candidates), body.limit),
        "candidates_truncated": len(candidates) > body.limit,
        "candidates_enqueue_capped": payload.get("candidates_enqueue_capped", False),
        "max_enqueue_candidates": body.max_enqueue_candidates,
        "result_role": "DISCOVERY_ONLY",
        "claim_admission_allowed": False,
        "sources_admitted": admitted,
        "sources_refused": refused,
    }



@router.post("/harvest")
async def run_zero_layer_harvest(
    body: HarvestRunRequest,
    ctx: Annotated[TenantContext, Depends(require_analyst)] = None,
) -> dict[str, Any]:
    """Collect one scoped public seed through Zero Layer and canonical evidence.

    This route is not a name/phone/account profiler. It accepts only public domain or
    HTTPS URL seeds; it honours investigation source scope, robots.txt, a bounded
    SecurePublicTransport budget and a no-AI candidate allow-list. Raw pages and all
    three derivation stages are persisted as Capture/Observation records and emitted
    through the existing observation event contract.
    """
    detected = TypeDetector().detect(body.seed)
    detected_type = detected.detected_type
    if detected_type not in {InputType.DOMAIN, InputType.URL}:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unsupported_seed_type",
                "detail": "Production zero-layer harvest accepts public domains and HTTPS URLs only.",
                "detected_type": detected_type.value,
            },
        )
    if body.seed_type and body.seed_type.lower() != detected_type.value:
        raise HTTPException(
            status_code=422,
            detail={"error": "seed_type_mismatch", "detected_type": detected_type.value},
        )
    try:
        if detected_type is InputType.DOMAIN:
            normalized_seed = f"https://{body.seed.strip().lower().rstrip('.')}/"
        else:
            normalized_seed = body.seed.strip()
        normalized_seed = validate_seed_url(normalized_seed)
        parsed = urlsplit(normalized_seed)
        if parsed.scheme.lower() != "https":
            raise ValueError("production zero-layer only collects HTTPS public pages")
        if parsed.username or parsed.password:
            raise ValueError("URL userinfo is not accepted")
        sensitive_query_keys = {
            "key", "api_key", "token", "access_token", "auth", "password",
            "signature", "sig", "session",
        }
        if any(
            key.lower() in sensitive_query_keys
            for key, _ in parse_qsl(parsed.query, keep_blank_values=True)
        ):
            raise ValueError("credential-like URL query parameters are not accepted")
    except (SecurityBlocked, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid_public_seed", "detail": str(exc)},
        ) from exc

    session_factory = make_session_factory()
    async with session_factory() as session:
        investigation = (
            await session.execute(
                select(InvestigationRow).where(
                    InvestigationRow.investigation_id == body.investigation_id,
                    InvestigationRow.tenant_id == ctx.tenant_id,
                )
            )
        ).scalar_one_or_none()
    if investigation is None:
        raise HTTPException(status_code=404, detail="investigation not found")
    state = str(getattr(investigation.state, "value", investigation.state)).upper()
    if state not in {"DRAFT", "PLANNING", "RUNNING"}:
        raise HTTPException(
            status_code=409,
            detail=f"investigation does not accept acquisition in state {state}",
        )
    scope = investigation.scope if isinstance(investigation.scope, dict) else {}
    allowed_types = scope.get("allowed_discovery_seed_types")
    if isinstance(allowed_types, list) and detected_type.value not in {
        str(value).lower() for value in allowed_types
    }:
        raise HTTPException(status_code=403, detail="seed type is outside the investigation scope")
    allowed_sources = scope.get("allowed_source_ids")
    if isinstance(allowed_sources, list) and allowed_sources and "zero-layer" not in {
        str(value) for value in allowed_sources
    }:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "source_outside_scope",
                "source_id": "zero-layer",
                "allowed_source_ids": sorted(str(value) for value in allowed_sources),
            },
        )

    try:
        from artifact_sink import ArtifactSink
        from dispatcher.kafka_producer import KafkaProducer
        from evidence_writer import PostgresAcquisitionEvidenceWriter
        from events.content_router import ContentRouter
        from events.kafka import build_envelope
        from events.observation_gate import ObservationGate
        from events.topics import topic_for
        from storage.s3 import ObjectStore
        from zero.evidence import ZeroLayerEvidenceSink
        from zero.harvest_wave import HarvestWave
        from zero.harvesters.transport import SecurePublicTransport
        from zero.public_policy import allow_public_candidate

        store = ObjectStore()
        producer = KafkaProducer()
        gate = ObservationGate(store=store, router=ContentRouter(), producer=producer)
        artifact_sink = ArtifactSink(
            gate=gate,
            store=store,
            source_family="zero_layer_public",
            recorded_by="zero-layer",
            evidence_writer=PostgresAcquisitionEvidenceWriter(session_factory),
        )
        transport = SecurePublicTransport(
            max_response_bytes=2_000_000,
            minimum_host_interval_s=1.0,
            max_requests=64,
            max_concurrency=4,
        )
        wave = HarvestWave(
            transport=transport,
            max_depth=1,
            enable_enrichment=False,
            candidate_allowed=allow_public_candidate,
        )
        evidence_sink = ZeroLayerEvidenceSink(artifact_sink, source_id="zero-layer")
        summaries, accepted = await wave.run_and_persist(
            [normalized_seed, parsed.hostname or ""],
            evidence_sink=evidence_sink,
            tenant_id=ctx.tenant_id,
            investigation_id=body.investigation_id,
        )

        # Persist a cycle-complete event in the canonical Zero Layer lane. It is
        # keyed deterministically; event delivery is awaited together with every
        # Capture/Observation event, so the response does not report a phantom run.
        for summary in summaries:
            payload = {
                "investigation_id": body.investigation_id,
                "seed_id": detected.seed_id,
                "wave": summary.as_dict(),
                "raw_capture_count": len(transport.captures),
                "stage_observation_count": len(wave.stage_records),
                "result_role": "DISCOVERY_ONLY",
                "claim_admission_allowed": False,
            }
            encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            envelope = build_envelope(
                event_type="zero_layer.harvest_cycle_complete",
                event_version="1.0",
                producer="zero-layer",
                producer_version="1.0.0",
                payload=encoded,
                investigation_id=body.investigation_id,
                tenant_id=ctx.tenant_id,
                source_id="zero-layer",
                work_id=detected.seed_id,
            )
            producer.produce(
                topic_for("zero_layer.harvest_cycle_complete"),
                envelope,
                key=f"{ctx.tenant_id}:{body.investigation_id}:{detected.seed_id}:{summary.wave_index}",
            )

        expected_events = sum(
            1 for item in accepted
            if getattr(item, "event_id", None) and getattr(item, "topic", None)
        ) + len(summaries)
        undelivered = producer.flush(15.0)
        acknowledged = producer.drain()
        if undelivered or len(acknowledged) < expected_events:
            raise RuntimeError(
                f"zero-layer event delivery incomplete: expected {expected_events}, "
                f"acknowledged {len(acknowledged)}, pending {undelivered}"
            )

        refs = [
            {
                "stage": getattr(item, "stage", "RAW_CAPTURE"),
                "wave_index": getattr(item, "wave_index", 0),
                "seed_id": getattr(item, "seed_id", detected.seed_id),
                "capture_id": item.capture_id,
                "observation_id": item.observation_id,
                "raw_ref": item.raw_ref,
                "content_digest": getattr(item, "content_digest", ""),
                "event_id": getattr(item, "event_id", None),
                "topic": getattr(item, "topic", None),
            }
            for item in accepted
        ]
        return {
            "seed": normalized_seed,
            "seed_id": detected.seed_id,
            "seed_type": detected_type.value,
            "tenant_id": ctx.tenant_id,
            "investigation_id": body.investigation_id,
            "wave_summaries": [summary.as_dict() for summary in summaries],
            "raw_captures_persisted": len(transport.captures),
            "stage_observations_persisted": len(wave.stage_records),
            "fetch_failures": [
                {
                    "url": str(item.get("url") or "")[:256],
                    "code": str(item.get("code") or "")[:120],
                    "detail": str(item.get("detail") or "")[:300],
                }
                for item in transport.failures[:64]
            ],
            "request_budget": {
                "max_requests": transport.max_requests,
                "requests_used": transport.requests_used,
                "max_concurrency": transport.max_concurrency,
                "max_response_bytes": transport.max_response_bytes,
            },
            "event_acknowledgements": len(acknowledged),
            "evidence_refs": refs,
            "result_role": "DISCOVERY_ONLY",
            "claim_admission_allowed": False,
            "notice": (
                "Raw HTTPS pages are immutable captures. Extracted technical leads and "
                "generic organisational contact channels remain unverified; personal emails, "
                "phone numbers, breach hits, presence probes and guessed social profiles are "
                "suppressed by the production policy."
            ),
        }
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - persistence failure is never an empty success
        raise HTTPException(
            status_code=503,
            detail={"error": "zero_layer_unavailable", "cause": _error_text(exc)},
        ) from exc
