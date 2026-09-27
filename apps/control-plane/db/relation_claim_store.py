"""Durable SQL persistence for relation claims and their revision chain (016, US2, T030).

Identity is two-level: ``logical_relation_id`` names the relation across revisions
and ``relation_id`` covers one revision's content. Both levels are content-addressed
by the domain, so this adapter never mints an id -- it persists what the
``RelationClaimService`` derived, appends every revision to the ledger rather than
updating it in place (I-1, FR-006), and never reads outside the caller's tenant
(FR-048).
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from domain import enforce_projection_provenance
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.schema import RelationClaim as RelationClaimRow
from db.schema import RelationClaimRevision as RelationClaimRevisionRow

CLAIM_JSONB_COLUMNS = frozenset(
    {
        "role_bindings",
        "assertion_refs",
        "observation_refs",
        "source_independence_groups",
        "contradicts",
    }
)

DIRECTED_MODES = frozenset({"directed", "temporal"})

_VALID = "valid"


def _scalar(value: Any) -> Any:
    """Unwrap a ``StrEnum`` member to its value, leaving plain values untouched."""
    return getattr(value, "value", value)


def _instant(value: Any) -> datetime | None:
    """Accept a ``datetime`` or an ISO-8601 string for a ``timestamptz`` column."""
    if value is None or value == "":
        return None
    moment = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _refs(value: Any) -> list[str]:
    """Materialise a tuple of refs as a JSONB-safe list."""
    return [str(item) for item in value] if value else []


def _groups(value: Any) -> list[list[str]]:
    """Keep independence groups as their own nesting, never a flattened count."""
    return [[str(member) for member in group] for group in value] if value else []


def _role_bindings(value: Any) -> list[dict[str, str]]:
    """Serialise role bindings as plain dicts, whether bound objects or dicts."""
    bindings: list[dict[str, str]] = []
    for binding in value or ():
        if isinstance(binding, Mapping):
            bindings.append({str(key): str(item) for key, item in binding.items()})
        else:
            bindings.append(
                {
                    "role": str(binding.role),
                    "member_ref": str(binding.member_ref),
                    "member_class": str(getattr(binding, "member_class", "") or ""),
                }
            )
    return bindings


def _member_ref(binding: Any) -> str:
    return str(binding.get("member_ref", "")) if isinstance(binding, Mapping) else str(
        getattr(binding, "member_ref", "")
    )


def _json_safe(value: Any) -> Any:
    """Coerce a serialised record into plain JSON types for a JSONB column.

    Enum members are unwrapped explicitly rather than left to their ``str``
    behaviour, so a stored verdict is the bare value on every enum base class the
    domain may pick.
    """
    if isinstance(value, enum.Enum):
        return _json_safe(_scalar(value))
    if isinstance(value, Mapping):
        return {str(_scalar(key)): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None or isinstance(value, str | bool | int | float):
        return value
    return str(_scalar(value))


def _revision_row_id(logical_relation_id: str, revision_number: int) -> str:
    """Ledger key: ``logical_id`` + ``-r`` + revision number (data-model 10.1)."""
    return f"{logical_relation_id}-r{revision_number}"


def _participates(claim: Any, ref: str) -> bool:
    """Directional participant match, identical to the in-memory oracle.

    A ``DIRECTED`` or ``TEMPORAL`` claim only matches on its subject, so its
    object is not reported as a participant; an ``UNDIRECTED`` or ``NARY`` claim
    matches either endpoint and any role-binding member.
    """
    if _scalar(claim.arity_mode) in DIRECTED_MODES:
        return claim.subject_ref == ref
    if claim.subject_ref == ref or claim.object_ref == ref:
        return True
    return any(_member_ref(binding) == ref for binding in claim.role_bindings)


def _to_row(
    payload: Mapping[str, Any], *, tenant_id: str, content_hash: str
) -> RelationClaimRow:
    """Build the ``relation_claim`` row for one claim revision."""
    return RelationClaimRow(
        relation_id=str(payload["relation_id"]),
        logical_relation_id=str(payload["logical_relation_id"]),
        revision_number=int(payload["revision_number"]),
        tenant_id=tenant_id,
        investigation_id=str(payload.get("investigation_id") or ""),
        relation_type=str(payload["relation_type"]),
        arity_mode=str(_scalar(payload["arity_mode"])),
        subject_ref=str(payload["subject_ref"]),
        object_ref=str(payload["object_ref"]),
        role_bindings=_role_bindings(payload.get("role_bindings")),
        valid_from=_instant(payload.get("valid_from")),
        valid_to=_instant(payload.get("valid_to")),
        observed_at=_instant(payload.get("observed_at")),
        published_at=_instant(payload.get("published_at")),
        known_from=_instant(payload.get("known_from")),
        known_until=_instant(payload.get("known_until")),
        assertion_refs=_refs(payload.get("assertion_refs")),
        observation_refs=_refs(payload.get("observation_refs")),
        context_ref=str(payload.get("context_ref") or ""),
        source_independence_groups=_groups(payload.get("source_independence_groups")),
        extraction_version=str(payload.get("extraction_version") or ""),
        normalization_version=str(payload.get("normalization_version") or ""),
        ontology_version=str(payload.get("ontology_version") or ""),
        schema_version=str(payload.get("schema_version") or ""),
        status=str(_scalar(payload.get("status")) or "active"),
        confidence=float(payload.get("confidence", 0.5)),
        evidence_grade=str(_scalar(payload.get("evidence_grade")) or "ungraded"),
        created_by=str(payload.get("created_by") or ""),
        supersedes=str(payload.get("supersedes") or ""),
        contradicts=_refs(payload.get("contradicts")),
        content_hash=content_hash,
        created_at=_instant(payload.get("created_at")),
    )


def _from_row(row: RelationClaimRow) -> Any:
    """Reconstruct the domain claim; ``RelationClaim.from_dict`` owns the contract.

    Every column of ``relation_claim`` is fed back, so the round trip is closed
    even for the fields the store never interprets itself. ``created_at`` is the
    only value the database may own: when the claim did not carry one the column
    falls back to ``now()``, and the populated value is passed through on the way
    out.
    """
    from domain.relation_claim import RelationClaim

    return RelationClaim.from_dict(
        {
            "relation_id": row.relation_id,
            "logical_relation_id": row.logical_relation_id,
            "revision_number": row.revision_number,
            "relation_type": row.relation_type,
            "arity_mode": row.arity_mode,
            "subject_ref": row.subject_ref,
            "object_ref": row.object_ref,
            "role_bindings": _role_bindings(row.role_bindings),
            "valid_from": _instant(row.valid_from),
            "valid_to": _instant(row.valid_to),
            "observed_at": _instant(row.observed_at),
            "published_at": _instant(row.published_at),
            "known_from": _instant(row.known_from),
            "known_until": _instant(row.known_until),
            "assertion_refs": _refs(row.assertion_refs),
            "observation_refs": _refs(row.observation_refs),
            "context_ref": row.context_ref or "",
            "source_independence_groups": _groups(row.source_independence_groups),
            "extraction_version": row.extraction_version or "",
            "normalization_version": row.normalization_version or "",
            "ontology_version": row.ontology_version or "",
            "schema_version": row.schema_version or "",
            "status": row.status or "active",
            "confidence": row.confidence,
            "evidence_grade": row.evidence_grade or "ungraded",
            "tenant_id": row.tenant_id,
            "investigation_id": row.investigation_id or "",
            "created_by": row.created_by or "",
            "supersedes": row.supersedes or "",
            "contradicts": _refs(row.contradicts),
            "created_at": _instant(row.created_at),
        }
    )


def _validation_column() -> tuple[type[Any], str]:
    """Resolve which table and column durably holds a ``ValidationResult``.

    Migration 016 gives ``relation_claim`` only the JSONB columns that carry the
    claim's own structure -- ``role_bindings``, ``assertion_refs``,
    ``observation_refs``, ``source_independence_groups``, ``contradicts`` -- and
    gives ``relation_claim_revision`` no JSONB at all, so as written neither can
    hold a verdict with its reasons, its grade components and the versions it was
    rendered against. ``claim_context_lineage`` is deliberately not borrowed:
    ``contracts/operations.md`` scopes it to a ``LineageTrace``'s hop list, and
    putting a verdict in ``hops`` would conflate two different artefacts.

    The lookup runs against the live schema, so the store starts persisting
    verdicts the moment a ``relation_claim.validation_record`` or
    ``relation_claim_revision.payload`` JSONB column is added, and refuses loudly
    -- naming the missing column -- until then rather than dropping the record
    (FR-050).
    """
    for model, owned in ((RelationClaimRow, CLAIM_JSONB_COLUMNS), (RelationClaimRevisionRow, None)):
        for column in model.__table__.columns:
            if isinstance(column.type, JSONB) and column.name not in (owned or ()):
                return model, column.name
    raise NotImplementedError(
        "no JSONB column exists to persist a ValidationResult: relation_claim has only its "
        f"own structural JSONB columns ({', '.join(sorted(CLAIM_JSONB_COLUMNS))}) and "
        "relation_claim_revision has none; migration 016 needs "
        "relation_claim.validation_record JSONB (or relation_claim_revision.payload JSONB) "
        "before a non-VALID verdict can be preserved and replayed (FR-050)"
    )


def _validation_payload(result: Any) -> dict[str, Any]:
    """Serialise a ``ValidationResult`` into a replayable record.

    The five grade components are carried as their own entries and never summed
    into one score (FR-025), and the versions the verdict was rendered against
    travel with the reasons so a replay reads exactly the inputs that produced
    the decision (FR-050). ``recorded_at`` is the store's own timestamp: neither
    the domain result nor the ``context.validation.recorded`` event payload
    carries when the record itself was persisted.

    A ``Mapping`` is accepted as-is because that is the shape the durable event
    log replays; a domain object is read through its own ``to_dict`` when it has
    one and field by field otherwise.
    """
    to_dict = getattr(result, "to_dict", None)
    if isinstance(result, Mapping):
        source = result
    elif to_dict is not None:
        source = to_dict()
    else:
        source = _validation_fields(result)
    record = _json_safe(source)
    record["recorded_at"] = datetime.now(UTC).isoformat()
    return record


def _validation_fields(result: Any) -> dict[str, Any]:
    """Read a ``ValidationResult`` field by field when it offers no ``to_dict``."""
    return {
        "verdict": result.verdict,
        "layers": dict(result.layers),
        "reasons": [
            {
                "code": reason.code,
                "layer": reason.layer,
                "detail": reason.detail,
                "evidence": _refs(getattr(reason, "evidence", ())),
            }
            for reason in result.reasons
        ],
        "evidence_grade": result.evidence_grade,
        "grade_components": dict(result.grade_components),
        "claim_id": str(result.claim_id),
        "context_id": str(result.context_id),
        "evaluated_versions": dict(result.evaluated_versions),
    }


class SqlRelationClaimStore:
    """Tenant-scoped persistence for relation claims, revisions and verdicts.

    ``session`` is supplied by the caller so the store can join the control-plane
    transaction boundary. Every query filters on an explicit ``tenant_id``, so a
    cross-tenant read returns nothing rather than another tenant's row (FR-048).
    ``upsert`` takes its tenant from the claim instead of a keyword, because the
    claim is the only object that carries one.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(self, claim: Any, *, provenance: Mapping[str, Any]) -> str:
        """Idempotently persist one claim revision and append it to the ledger.

        Idempotency is keyed on ``(tenant_id, content_hash)`` -- the
        ``uq_relation_claim_content`` unique index -- and on ``relation_id``: a
        retried or replayed write resolves to the stored row and appends no second
        ledger entry, so a log replay converges instead of forking the chain
        (I-11). A write whose ``provenance`` lacks ``event_id``/``observation_id``
        is refused before anything is staged, leaving the store unchanged (I-12).
        """
        enforce_projection_provenance(dict(provenance) if provenance else None)
        tenant_id = str(getattr(claim, "tenant_id", "") or "")
        if not tenant_id:
            raise ValueError("relation claim must carry a tenant_id")
        relation_id = str(claim.relation_id)
        content_hash = str(claim.content_hash)
        if await self._stored(relation_id, content_hash, tenant_id=tenant_id):
            return relation_id

        row = _to_row(claim.to_dict(), tenant_id=tenant_id, content_hash=content_hash)
        self.session.add(row)
        self.session.add(
            RelationClaimRevisionRow(
                revision_row_id=_revision_row_id(row.logical_relation_id, row.revision_number),
                relation_id=row.relation_id,
                logical_relation_id=row.logical_relation_id,
                revision_number=row.revision_number,
                tenant_id=tenant_id,
                valid_from=row.valid_from,
                valid_to=row.valid_to,
                context_ref=row.context_ref,
                status=row.status,
                evidence_grade=row.evidence_grade,
            )
        )
        try:
            await self.session.commit()
        except IntegrityError:
            # A concurrent writer claimed the same content or revision slot.
            await self.session.rollback()
            if not await self._stored(relation_id, content_hash, tenant_id=tenant_id):
                raise
        return relation_id

    async def get(self, relation_id: str, *, tenant_id: str) -> Any:
        """Return one claim revision, or ``None`` when it is absent or other-tenant."""
        result = await self.session.execute(
            select(RelationClaimRow).where(
                RelationClaimRow.tenant_id == tenant_id,
                RelationClaimRow.relation_id == relation_id,
            )
        )
        row = result.scalar_one_or_none()
        return _from_row(row) if row is not None else None

    async def revisions(self, logical_relation_id: str, *, tenant_id: str) -> tuple[Any, ...]:
        """Return the whole revision chain, ordered by ``revision_number``.

        Non-``ACTIVE`` revisions are included, so "every version of this relation"
        stays answerable (FR-006). The last element is the current revision, and
        the ``(revision_number, relation_id)`` ordering is the one
        ``InMemoryRelationStore.revisions`` uses, so the two stores agree even on
        a chain the ledger's unique index would otherwise have rejected.
        """
        result = await self.session.execute(
            select(RelationClaimRow)
            .where(
                RelationClaimRow.tenant_id == tenant_id,
                RelationClaimRow.logical_relation_id == logical_relation_id,
            )
            .order_by(RelationClaimRow.revision_number, RelationClaimRow.relation_id)
        )
        claims = tuple(_from_row(row) for row in result.scalars().all())
        from domain.relation_claim import RelationRevision

        return tuple(
            RelationRevision(
                logical_relation_id=logical_relation_id, revisions=claims
            ).revisions
        )

    async def by_type(
        self,
        relation_type: str,
        *,
        tenant_id: str,
        active_at: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Any], int]:
        """Return one page of claims of a type plus the unpaged total.

        ``active_at`` is applied through the claim's own ``is_active_at`` rather
        than in SQL, so the database filter and the domain rule cannot drift
        apart. The page is therefore taken after filtering and the total counts
        the whole filtered set (FR-036). Ordering by ``relation_id`` makes paging
        deterministic.
        """
        if limit < 0 or offset < 0:
            raise ValueError("limit and offset must be non-negative")
        result = await self.session.execute(
            select(RelationClaimRow)
            .where(
                RelationClaimRow.tenant_id == tenant_id,
                RelationClaimRow.relation_type == relation_type,
            )
            .order_by(RelationClaimRow.relation_id)
        )
        claims = [_from_row(row) for row in result.scalars().all()]
        if active_at is not None:
            claims = [claim for claim in claims if claim.is_active_at(active_at)]
        return claims[offset : offset + limit], len(claims)

    async def by_participant(self, ref: str, *, tenant_id: str) -> list[Any]:
        """Return every claim ``ref`` participates in, directionally.

        ``DIRECTED``/``TEMPORAL`` claims match on the subject only; ``UNDIRECTED``
        and ``NARY`` claims match either endpoint or any role-binding member.
        ``role_bindings`` is JSONB, so the rule is applied to the reconstructed
        claims rather than pushed into the query.
        """
        result = await self.session.execute(
            select(RelationClaimRow)
            .where(RelationClaimRow.tenant_id == tenant_id)
            .order_by(RelationClaimRow.relation_id)
        )
        return [
            claim
            for claim in (_from_row(row) for row in result.scalars().all())
            if _participates(claim, ref)
        ]

    async def checksum(self, *, tenant_id: str) -> str:
        """Order-independent checksum over every stored claim in the tenant.

        ``InMemoryRelationStore.checksum`` is the rebuild oracle, so the digest
        here is computed the same way: the stored ``content_hash`` values in
        ``relation_id`` order, newline-joined, then ``digest128``. The result is
        byte-identical to the oracle's for the same claim set, and therefore
        invariant under the order the database happened to return rows in
        (FR-040, SC-011).
        """
        from domain.relation_identity import digest128

        result = await self.session.execute(
            select(RelationClaimRow.content_hash)
            .where(RelationClaimRow.tenant_id == tenant_id)
            .order_by(RelationClaimRow.relation_id)
        )
        return digest128("\n".join(str(value) for value in result.scalars().all()))

    async def record_validation(
        self, relation_id: str, *, tenant_id: str, result: Any
    ) -> None:
        """Persist a ``ValidationResult`` so a non-``VALID`` verdict is replayable.

        The record is written to the JSONB column :func:`_validation_column`
        resolves -- ``relation_claim.validation_record`` when the schema has it,
        otherwise ``relation_claim_revision.payload`` -- and carries the verdict,
        all seven layer outcomes, the structured reasons, the five grade
        components, the evaluated versions and a ``recorded_at`` timestamp
        (FR-050, FR-025). A claim is never deleted or downgraded to hide a
        verdict: the rejection is preserved in place.

        The column is looked up rather than assumed because migration 016 defines
        no such column, and fabricating a home in ``claim_context_lineage.hops``
        would mix a verdict into a ``LineageTrace``. Until the column exists both
        this method and :meth:`non_valid` raise ``NotImplementedError`` naming it.
        """
        model, column = _validation_column()
        result_set = await self.session.execute(self._verdict_query(model, relation_id, tenant_id))
        row = result_set.scalar_one_or_none()
        if row is None:
            raise ValueError(
                f"relation {relation_id} has no stored claim for tenant {tenant_id}"
            )
        setattr(row, column, _validation_payload(result))
        await self.session.commit()

    async def non_valid(self, *, tenant_id: str) -> list[dict[str, Any]]:
        """The replay queue: every claim whose recorded verdict is not ``VALID``.

        Each entry names the claim and its revision, the decision, the reasons,
        the five grade components, the versions it was evaluated against and when
        it was recorded, so a quarantined claim can be replayed under exactly the
        conditions that rejected it (FR-050). Rejected claims are never deleted,
        so this is a filter over durable state, not a log that gets drained
        (FR-006). Claims that were never validated are not in the queue: there is
        no decision to replay.
        """
        model, column = _validation_column()
        result_set = await self.session.execute(self._verdict_query(model, None, tenant_id))
        queue: list[dict[str, Any]] = []
        for row in result_set.scalars().all():
            record = dict(getattr(row, column) or {})
            if str(record.get("verdict", "")).lower() == _VALID:
                continue
            queue.append(
                {
                    "relation_id": row.relation_id,
                    "logical_relation_id": row.logical_relation_id,
                    "revision_number": row.revision_number,
                    "verdict": str(record.get("verdict", "")),
                    "evidence_grade": str(record.get("evidence_grade", "")),
                    "layers": record.get("layers", {}),
                    "reasons": record.get("reasons", []),
                    "grade_components": record.get("grade_components", {}),
                    "evaluated_versions": record.get("evaluated_versions", {}),
                    "recorded_at": str(record.get("recorded_at", "")),
                }
            )
        return queue

    def _verdict_query(
        self, model: type[Any], relation_id: str | None, tenant_id: str
    ) -> Any:
        """Tenant-scoped selector over whichever table holds the verdict column."""
        if model is RelationClaimRow:
            query = select(RelationClaimRow).where(RelationClaimRow.tenant_id == tenant_id)
            if relation_id is not None:
                query = query.where(RelationClaimRow.relation_id == relation_id)
            return query.order_by(RelationClaimRow.relation_id)
        query = select(RelationClaimRevisionRow).where(
            RelationClaimRevisionRow.tenant_id == tenant_id
        )
        if relation_id is not None:
            query = query.where(RelationClaimRevisionRow.relation_id == relation_id)
        return query.order_by(RelationClaimRevisionRow.revision_number)

    async def _stored(self, relation_id: str, content_hash: str, *, tenant_id: str) -> bool:
        """Whether this content is already durable for the tenant (I-11)."""
        for lookup in (
            select(RelationClaimRow).where(
                RelationClaimRow.tenant_id == tenant_id,
                RelationClaimRow.relation_id == relation_id,
            ),
            select(RelationClaimRow).where(
                RelationClaimRow.tenant_id == tenant_id,
                RelationClaimRow.content_hash == content_hash,
            ),
        ):
            found = await self.session.execute(lookup)
            if found.scalar_one_or_none() is not None:
                return True
        return False


__all__ = ["SqlRelationClaimStore"]
