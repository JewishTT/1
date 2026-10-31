"""Dossier API — the surface an analyst actually reads.

Everything below the HTTP layer already worked: a sweep runs, writes itself to
``entity_stream``, and a dossier is rebuilt from those rows. What did not exist was a way to
ask for either, which is the reason the enrichment engine could be complete and still be
invisible. This router is that missing step and nothing more — it holds no domain logic,
performs no fetch itself, and returns the engine's own objects rather than a reshaped view
of them.

Three shapes of question, three endpoints, because they have genuinely different costs:

* ``POST /enrich`` runs the outside world. It calls real sources, so it is slow, it is not
  idempotent, and it appends to the stream. ``max_sources`` is capped for that reason: a
  sweep over 146 definitions can run for minutes, and an unbounded request is a way to hold
  a worker open.
* ``GET /{entity_ref}`` is a pure read. It re-folds the invariant from the rows every time,
  which is cheap and is the point of an append-only stream: there is no second copy of the
  state that could disagree with the events.
* ``GET /`` lists what has been looked at, so the UI has something to offer before an
  analyst has typed anything.

A subject that was never swept returns ``404`` rather than an empty dossier. The difference
is the whole coverage vocabulary: "we never looked" is not "we looked and found nothing".
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.auth import TenantContext, resolve_tenant

router = APIRouter(prefix="/dossier", tags=["dossier"])

#: Hard ceiling on sources per sweep. The catalogue holds 146 definitions; asking for all of
#: them from a web request is a request that can outlive its connection. The cap is a
#: throughput guard, not a coverage claim -- the plan reports what was *not* attempted.
MAX_SOURCES = 60


class EnrichRequest(BaseModel):
    """One subject to sweep.

    ``kind`` is the caller's assertion about what the subject is and is used for labelling
    only. Which sources run is decided by the shape of ``subject`` itself -- see
    ``enrichment_service._query_shapes`` -- because no source in the catalogue accepts a
    "person" or a "domain"; they accept domains, names, addresses and free text.
    """

    subject: str = Field(min_length=1, max_length=512)
    kind: str = Field(default="", max_length=64)
    max_sources: int | None = Field(default=None, ge=1, le=MAX_SOURCES)
    depth: int = Field(default=0, ge=0, le=2)


def _source_names() -> dict[str, str]:
    """Source id -> human name, from the live catalogue.

    A gap naming ``SRC-4c80dec9b97ce0d4aa12009fac6babf2`` cannot be acted on. The dossier core
    deliberately knows nothing about the catalogue -- it is pure and its ids are content
    addresses -- so the naming happens here, at the boundary where a catalogue exists.
    """
    from sources.catalogue import load_catalogue

    try:
        definitions, _ = load_catalogue()
    except Exception:  # noqa: BLE001 - a missing catalogue must not break reading a dossier
        return {}
    return {d.source_id: d.name for d in definitions}


def _name_gaps(dossier: dict[str, Any]) -> dict[str, Any]:
    names = _source_names()
    for gap in dossier.get("gaps", ()):
        gap["candidate_source_names"] = [names.get(s, s) for s in gap.get("candidate_sources", ())]
        gap["blocked_source_names"] = [names.get(s, s) for s in gap.get("blocked_sources", ())]
    return dossier


def _factory():
    from db.session import make_session_factory

    return make_session_factory()


@router.post("/enrich")
async def enrich(
    body: EnrichRequest,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict[str, Any]:
    """Run a sweep, persist it, and return the dossier it produced."""
    from context_engine.dossier_store import PostgresEnrichmentSink
    from context_engine.enrichment_service import EnrichmentService

    factory = _factory()
    service = EnrichmentService(
        tenant_id=ctx.tenant_id,
        sink=PostgresEnrichmentSink(factory, tenant_id=ctx.tenant_id),
    )
    report = await service.enrich(
        body.subject,
        kind=body.kind or "unknown",
        depth=body.depth,
        max_sources=body.max_sources,
    )
    return {
        "query": report.query,
        "entity_ref": report.subject.entity_ref,
        "type_label": report.subject.type_label,
        "sources_called": len(report.reports),
        "known_attributes": list(report.subject.known()),
        "invariant_error": report.invariant_error,
        "dossier": _name_gaps(report.dossier.as_dict()) if report.dossier else None,
        "reports": [r.as_dict() for r in report.reports],
        "refusals": [r.as_dict() for r in report.refusals],
        "discovered": [d.as_dict() for d in report.discovered],
    }


@router.get("")
async def list_subjects(
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    """Subjects with a persisted life-stream, most recently observed first."""
    factory = _factory()
    async with factory() as conn:
        rows = (
            await conn.execute(
                text(
                    """
                    SELECT entity_id,
                           count(*)          AS events,
                           min(ts)           AS first_seen,
                           max(ts)           AS last_seen
                    FROM entity_stream
                    WHERE tenant_id = :tenant
                    GROUP BY entity_id
                    ORDER BY max(ts) DESC
                    LIMIT :limit
                    """
                ),
                {"tenant": ctx.tenant_id, "limit": limit},
            )
        ).mappings().all()
    return {
        "subjects": [
            {
                "entity_ref": r["entity_id"],
                "events": int(r["events"]),
                "first_seen": r["first_seen"].isoformat() if r["first_seen"] else None,
                "last_seen": r["last_seen"].isoformat() if r["last_seen"] else None,
            }
            for r in rows
        ]
    }


@router.get("/{entity_ref}")
async def get_dossier(
    entity_ref: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict[str, Any]:
    """The dossier for one subject, rebuilt from its events.

    Capabilities are resolved from the subject the sweep actually queried rather than from
    the referent, so the coverage figures are comparable across subjects.
    """
    from context_engine.dossier_store import DossierReader

    reader = DossierReader(_factory(), tenant_id=ctx.tenant_id)
    dossier = await reader.read(entity_ref)
    if dossier is None:
        raise HTTPException(
            status_code=404,
            detail=f"no life-stream for {entity_ref}; it has not been swept",
        )
    return _name_gaps(dossier.as_dict())