"""Manual assertion endpoints scoped to an investigation (T024 gap, 025 FR-025-077).

Why this exists
---------------
Until now an analyst could only create entities and relations through the legacy
``/entities`` and ``/intel`` routes, which carry no investigation reference. Anything an
analyst typed therefore landed in a global pool with no record of which question prompted
it, which is the same class of defect as an unscoped graph read: the work exists, but it
cannot be attributed to the investigation that produced it.

These routes create the same durable objects as the legacy path and add three things:

1. ``investigation_id`` and ``tenant_id`` on the relation claim, so the assertion is
   retrievable as part of this investigation.
2. ``created_by`` and ``provenance = MANUAL_ANALYST_ASSERTION``, so a hand-typed relation
   is never mistaken for an extracted one. This distinction is load-bearing: a manual
   assertion is the analyst's statement, not evidence the system observed.
3. An ``ANL-`` analyst assertion recorded alongside, so "who said this, when, on what
   basis" is answerable without reading application logs (025 Appendix L.8).

What this is not
----------------
It is not the 025 analyst layer. That is `AnalystDecision` with justification, override
semantics beside model state, and mainline isolation (ADR-0038) -- Phase L work. These
routes are the minimal honest version: a human statement, scoped and attributed. They do
not override model state and they do not admit anything; an assertion is an assertion.

Relations created here carry ``status = MANUAL_ASSERTED`` rather than ``ASSERTED`` so that
downstream admission treats them as claims requiring evaluation, not as already-admitted
facts. An analyst's statement that silently became an admitted fact would defeat the
purpose of having an admission boundary at all.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text

from api.auth import TenantContext, resolve_tenant
from api.routes.investigations import ensure_durable_context

router = APIRouter(tags=["manual-assertions"])

# Validated at import so an unknown arity is rejected at the boundary rather than becoming
# a NOT NULL violation 500 from the driver.
_ARITY_MODES: frozenset[str] = frozenset({"undirected", "directed"})


class ManualEntity(BaseModel):
    """An entity an analyst asserts exists.

    ``canonical_identity`` is required and must be non-empty: an entity with no identity
    cannot be resolved, referenced, or re-found, so accepting one would create an object
    that no query can ever return.
    """

    canonical_identity: dict[str, str]
    label: str | None = None
    aliases: list[str] = Field(default_factory=list)
    entity_type: str = "entity"
    basis: str = ""
    """Free text: why the analyst believes this. Stored with the assertion."""


class ManualRelation(BaseModel):
    subject_ref: str
    object_ref: str
    relation_type: str
    role_bindings: dict[str, str] = Field(default_factory=dict)
    arity_mode: str = "directed"
    """`undirected` | `directed` | `nary` (domain.relation_identity.RelationArityMode).

    Defaults to `directed` because the overwhelming majority of analyst-asserted
    relations are directional ("works for", "controls", "owns"). It is still an explicit
    field rather than an inference: `nary` is meaningless for the two refs this endpoint
    accepts, so asserting it here would be a claim about structure the input does not carry.
    """
    confidence: float
    """Required, 0..1.

    ``relation_claim.confidence`` is ``NOT NULL DEFAULT 0.5``. That default is exactly the
    donor defect ``AGENTS.md`` §2 names: an unmeasured confidence silently becomes a
    measured 0.5, and a consumer cannot tell the two apart.

    Rather than inherit it, an unstated confidence is **refused** (422) instead of being
    defaulted. Writing 0.0 would be equally wrong in the other direction -- unmeasured is
    not "no confidence". The proper fix is a migration making the column nullable, which
    is 025 Phase B work; until then the honest options are "state it" or "do not write the
    relation".
    """
    basis: str = ""
    valid_from: str | None = None
    valid_to: str | None = None


def _content_hash(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


async def _context_exists(investigation_id: str, tenant_id: str) -> None:
    """Refuse manual assertions against an investigation that has no context.

    An assertion with no context is an assertion attached to nothing. Failing here is
    better than storing a row that no scoped query will ever return.
    """
    from sqlalchemy import text

    from api.routes.entities import _pg_session

    async with _pg_session()() as session:
        row = await session.execute(
            text(
                "SELECT 1 FROM investigation_contexts "
                "WHERE investigation_id = :inv AND tenant_id = :tenant LIMIT 1"
            ),
            {"inv": investigation_id, "tenant": tenant_id},
        )
        if row.scalar() is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"no context for investigation {investigation_id} in this tenant; "
                    "create the investigation first"
                ),
            )


@router.post(
    "/investigations/{investigation_id}/assertions/entity",
    status_code=201,
)
async def assert_entity(
    investigation_id: str,
    body: ManualEntity,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    if not body.canonical_identity or not any(
        str(v).strip() for v in body.canonical_identity.values()
    ):
        raise HTTPException(status_code=422, detail="canonical_identity must not be empty")

    await _context_exists(investigation_id, ctx.tenant_id)

    label = body.label or next(
        (str(v) for v in body.canonical_identity.values() if str(v).strip()), ""
    )
    entity_id = "ENT-" + hashlib.sha256(
        f"{ctx.tenant_id}|{_content_hash(body.canonical_identity)}".encode()
    ).hexdigest()[:12]
    assertion_id = "ANL-" + uuid.uuid4().hex[:32]
    now = datetime.now(UTC).isoformat()

    attributes = {
        "label": label,
        "aliases": body.aliases or ([label] if label else []),
        "entity_type": body.entity_type,
    }

    from db.schema import AnalystAssertion, Entity
    from db.session import make_session_factory

    session_factory = make_session_factory()
    async with session_factory() as session:
        existing = await session.get(Entity, entity_id)
        created = existing is None
        if created:
            session.add(
                Entity(
                    entity_id=entity_id,
                    tenant_id=ctx.tenant_id,
                    entity_type=body.entity_type,
                    canonical_name=label,
                    attributes=attributes,
                    current_version=1,
                )
            )
        # The assertion is recorded whether or not the entity row already existed: a
        # re-assertion of a known entity is still a distinct act with its own basis.
        session.add(
            AnalystAssertion(
                assertion_id=assertion_id,
                tenant_id=ctx.tenant_id,
                investigation_id=investigation_id,
                entity_ref=entity_id,
                statement={
                    "type": "ENTITY_EXISTS",
                    "identity": body.canonical_identity,
                },
                basis=body.basis,
                created_by=f"analyst:{ctx.tenant_id}",
            )
        )
        await session.commit()

    return {
        "entity_id": entity_id,
        "label": label,
        "entity_type": body.entity_type,
        "created": created,
        "assertion_id": assertion_id,
        "investigation_id": investigation_id,
        "provenance": "MANUAL_ANALYST_ASSERTION",
        "admitted": False,
        "detail": "an analyst assertion, not an observed fact; awaiting evaluation",
    }


@router.post(
    "/investigations/{investigation_id}/assertions/relation",
    status_code=201,
)
async def assert_relation(
    investigation_id: str,
    body: ManualRelation,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    if not body.subject_ref or not body.object_ref:
        raise HTTPException(status_code=422, detail="subject_ref and object_ref are required")
    if not body.relation_type.strip():
        raise HTTPException(status_code=422, detail="relation_type is required")
    if body.arity_mode not in _ARITY_MODES:
        raise HTTPException(
            status_code=422,
            detail=f"arity_mode must be one of {sorted(_ARITY_MODES)}",
        )
    if not 0.0 <= body.confidence <= 1.0:
        raise HTTPException(status_code=422, detail="confidence must be within [0, 1]")

    await _context_exists(investigation_id, ctx.tenant_id)

    relation_id = "REL-" + hashlib.sha256(
        "|".join(
            [
                ctx.tenant_id,
                investigation_id,
                body.subject_ref,
                body.relation_type,
                body.object_ref,
            ]
        ).encode()
    ).hexdigest()[:24]
    logical_id = "LREL-" + _content_hash(
        {
            "subject": body.subject_ref,
            "type": body.relation_type,
            "object": body.object_ref,
        }
    )
    now = datetime.now(UTC).isoformat()
    assertion_id = "ANL-" + uuid.uuid4().hex[:32]

    from db.schema import AnalystAssertion, RelationClaim
    from db.session import make_session_factory

    session_factory = make_session_factory()
    async with session_factory() as session:
        prior_result = await session.execute(
            select(RelationClaim.revision_number)
            .where(
                RelationClaim.logical_relation_id == logical_id,
                RelationClaim.tenant_id == ctx.tenant_id,
                RelationClaim.investigation_id == investigation_id,
            )
            .order_by(RelationClaim.revision_number.desc())
            .limit(1)
        )
        prior = prior_result.scalar()
        revision = (int(prior) + 1) if prior is not None else 1
        stored_id = relation_id if revision == 1 else f"{relation_id}-r{revision}"

        session.add(
            RelationClaim(
                relation_id=stored_id,
                logical_relation_id=logical_id,
                revision_number=revision,
                tenant_id=ctx.tenant_id,
                investigation_id=investigation_id,
                relation_type=body.relation_type,
                arity_mode=body.arity_mode,
                subject_ref=body.subject_ref,
                object_ref=body.object_ref,
                role_bindings=body.role_bindings or {},
                # The assertion IS the provenance of this claim. An empty
                # ``assertion_refs`` would make the row unattributable.
                assertion_refs=[assertion_id],
                observation_refs=[],
                contradicts=[],
                # Exactly one independent source: the analyst. Stated explicitly rather
                # than left empty, because "no groups" would read as "no sources".
                source_independence_groups=[
                    {
                        "group_id": assertion_id,
                        "basis": "MANUAL_ANALYST_ASSERTION",
                        "size": 1,
                    }
                ],
                # The claim belongs to this investigation's context, not to a global pool.
                context_ref=investigation_id,
                extraction_version="manual",
                normalization_version="manual",
                ontology_version="manual",
                schema_version="manual-assertion/v1",
                evidence_grade="manual_assertion",
                # status MANUAL_ASSERTED, not ASSERTED: a hand-typed relation is a claim
                # awaiting evaluation, not an admitted fact. See module docstring.
                status="MANUAL_ASSERTED",
                confidence=body.confidence,
                created_by=f"analyst:{ctx.tenant_id}",
                valid_from=body.valid_from,
                valid_to=body.valid_to,
                content_hash=_content_hash(body.model_dump()),
            )
        )
        session.add(
            AnalystAssertion(
                assertion_id=assertion_id,
                tenant_id=ctx.tenant_id,
                investigation_id=investigation_id,
                relation_ref=stored_id,
                statement={
                    "type": "RELATION_ASSERTED",
                    "subject": body.subject_ref,
                    "predicate": body.relation_type,
                    "object": body.object_ref,
                },
                basis=body.basis,
                created_by=f"analyst:{ctx.tenant_id}",
            )
        )
        await session.commit()

    return {
        "relation_id": relation_id if revision == 1 else f"{relation_id}-r{revision}",
        "logical_relation_id": logical_id,
        "revision": revision,
        "investigation_id": investigation_id,
        "status": "MANUAL_ASSERTED",
        "confidence": body.confidence,
        "confidence_source": "ANALYST_STATED",
        "provenance": "MANUAL_ANALYST_ASSERTION",
        "admitted": False,
        "assertion_id": assertion_id,
        "detail": "requires evaluation; a manual assertion is a claim, not an admitted fact",
    }


@router.get("/investigations/{investigation_id}/assertions")
async def list_assertions(
    investigation_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    """What the analyst asserted for this investigation, and on what basis."""
    from db.schema import AnalystAssertion
    from db.session import make_session_factory

    session_factory = make_session_factory()
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(AnalystAssertion)
                .where(
                    AnalystAssertion.investigation_id == investigation_id,
                    AnalystAssertion.tenant_id == ctx.tenant_id,
                )
                .order_by(AnalystAssertion.created_at)
            )
        ).scalars().all()

    return {
        "investigation_id": investigation_id,
        "tenant_id": ctx.tenant_id,
        "assertions": [
            {
                "assertion_id": r.assertion_id,
                "entity_ref": r.entity_ref,
                "relation_ref": r.relation_ref,
                "statement": r.statement,
                "basis": r.basis,
                "created_by": r.created_by,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ],
        "note": (
            "These are analyst statements, not observed facts. They are inputs to "
            "evaluation and carry no admission."
        ),
    }


@router.post("/investigations/{investigation_id}/context/ensure", status_code=201)
async def ensure_context_route(
    investigation_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
    title: str = "",
    question: str = "",
) -> dict:
    """Create the investigation's context if it is missing.

    Exposed because a durable context is a precondition for every scoped read and write
    here, and a legacy investigation created before context-on-create has none. Returns the
    existing context when one is already present rather than creating a second.
    """
    context_id = await ensure_durable_context(
        investigation_id, ctx.tenant_id, title=title, question=question
    )
    return {
        "investigation_id": investigation_id,
        "context_id": context_id,
        "tenant_id": ctx.tenant_id,
    }