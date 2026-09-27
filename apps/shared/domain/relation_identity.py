"""Relation identity derivation — the only id-producing primitive (feature 016).

Tasks T023 (primitives, arity modes, identity derivation) and T029 (collision
detection) of ``specs/016-relation-evidence-graph-fabric``; contract is
``data-model.md`` sections 1, 2 and 4.1 with ``docs/adr/0023-relation-identity-and-arity.md``.

Two-level identity, both 128-bit truncated SHA-256 over documented canonical
material so an operator can recompute any id from the record alone (backend,
frontend and replay cannot disagree):

- ``logical_relation_id`` (``RL-``) answers *which relation this is*. The
  material is the arity-mode shape — mode, relation type, canonical
  participants, role bindings — and excludes the window, evidence, context and
  revision number, so every revision of one relation shares it.
- ``relation_id`` (``RC-``) answers *this content*. The material is the logical
  id plus the window, observation/publication times, evidence refs, context ref
  and revision number. Identical content always yields an identical id
  (idempotency, I-11) and a correction is a new id, never an overwrite.

Arity mode is part of the material: ``Employment{person=P1, org=O1}`` declared
``NARY`` and the pair ``P1 employed_by O1`` declared ``DIRECTED`` are different
relations, so an arity change is never silent. Per mode the participants are
canonicalised once, here: sorted+deduped for ``UNDIRECTED``, order-preserved
``(subject, object)`` for ``DIRECTED`` and sorted ``(role, member)`` pairs for
``NARY``.

Arity answers *how many participants and in what shape*. It deliberately does
not answer *when*: temporality is an orthogonal dimension carried by
``TemporalSemantics`` (``POINT``, ``OPTIONAL_INTERVAL``, ``REQUIRED_INTERVAL``,
``OPEN_ENDED``) on ``RelationSchema``/``RelationClaim``. An earlier
``RelationArityMode.TEMPORAL`` conflated the two and has been removed: a directed
relation may equally be temporal, and an n-ary one may too, so a temporal mode
under arity could only ever have been right for a subset and silently wrong for
the rest. With it goes the window-folding branch of :func:`logical_material` —
the window is revision material, and folding it into identity would have made
every directed relation revision-addressed and destroyed the identity/revision
split this module exists to keep.

A collision is surfaced, never merged (FR-011): ``detect_identity_collisions``
returns every bucket holding more than one *distinct* claim together with the
claims involved, so an event that is unobservable at read time cannot become a
silent data-integrity failure.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from domain.relation_claim import RelationClaim

#: Identity width: SHA-256 truncated to 128 bits and hex-encoded (32 chars).
DIGEST_BITS = 128

#: Prefix for "which relation this is" — shared by every revision.
LOGICAL_ID_PREFIX = "RL-"

#: Prefix for "this content" — one revision of a relation.
REVISION_ID_PREFIX = "RC-"

#: Types ``json`` already serialises deterministically, so ``_normalise`` is a
#: no-op for them and the fast path stays a single set lookup.
_JSON_NATIVE = frozenset({str, int, float, bool, type(None)})


def _normalise(value: object) -> object:
    """Make one value canonical before serialisation.

    ``datetime`` becomes its ``isoformat()`` so an aware and a naive instant
    never serialise to the same material, and a ``set``/``frozenset`` becomes a
    sorted list so an unordered container cannot leak its hash order. Sequence
    types keep their order: it is load-bearing identity (``DIRECTED`` preserves
    ``(subject, object)``), so sorting a tuple would be the one thing that must
    never happen here.
    """
    if value.__class__ in _JSON_NATIVE:
        return value
    if isinstance(value, str | int | float):
        return value  # a StrEnum/IntEnum member already is the value it serialises to
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _normalise(item) for key, item in value.items()}
    if isinstance(value, set | frozenset):
        return sorted(_normalise(item) for item in value)
    if isinstance(value, list | tuple):
        return [_normalise(item) for item in value]
    return str(value)


def canonical_material(value: object) -> str:
    """Deterministic, order-independent serialisation of identity material.

    ``json`` already renders ``dict``/``list``/``tuple``/scalars in a fixed,
    key-sorted form, so :func:`_normalise` runs only for the leaves ``json``
    cannot serialise at all — through the ``default`` hook — and the result is
    identical to normalising the whole value first. Identity is recomputed on
    every claim, so the hot path is kept free of a redundant walk.
    """
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_normalise,
    )


def digest128(material: str) -> str:
    """128-bit truncated SHA-256 as 32 lowercase hex characters."""
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[: DIGEST_BITS // 4]


class RelationArityMode(StrEnum):
    """How many participants a relation has and in what shape (participant count only).

    Temporality is *not* an arity mode. ``works_for`` directed may carry a
    required interval, ``co_occurs_with`` undirected may be a point in time, and
    an n-ary ``Employment`` may span years -- three arities, three independent
    temporal answers. See ``TemporalSemantics`` on ``RelationSchema``.
    """

    UNDIRECTED = "undirected"
    DIRECTED = "directed"
    NARY = "nary"

    @property
    def default_neighbor_direction(self) -> str:
        """``neighbors`` default: ``both`` where the reverse is the same relation."""
        if self in (RelationArityMode.UNDIRECTED, RelationArityMode.NARY):
            return "both"
        return "out"


class RoleBindingLike(Protocol):
    """What identity derivation reads off a role binding.

    Structural rather than the concrete type, so this module stays independent
    of ``domain.relation_claim`` (which imports this one) while still naming
    the contract: a role and the member that fills it.
    """

    role: str
    member_ref: str


def _window(value: object) -> str | None:
    """One window bound as canonical text (``None`` = open end)."""
    if value is None or value == "":
        return None
    return value.isoformat() if isinstance(value, datetime) else str(value)


def logical_material(
    arity_mode: RelationArityMode,
    relation_type: str,
    participants: Sequence[str],
    role_bindings: Sequence[RoleBindingLike] = (),
    *,
    valid_from: object = None,
    valid_to: object = None,
) -> dict[str, Any]:
    """Identity material of the *logical* relation, one shape per arity mode.

    The validity window is excluded for every mode. It is revision material
    (see :func:`revision_material`): a relation is "the same relation" across a
    correction to its window, and one logical relation may carry many revisions.
    Folding the window in here would make every relation revision-addressed and
    collapse the identity/revision split.
    """
    mode = RelationArityMode(arity_mode)
    if mode is RelationArityMode.UNDIRECTED:
        return {
            "mode": str(mode),
            "type": relation_type,
            "members": sorted({str(participant) for participant in participants}),
        }
    if mode is RelationArityMode.DIRECTED:
        members = [str(participant) for participant in participants]
        if len(members) != 2:
            raise ValueError(
                f"directed relation needs exactly two participants, got {len(members)}"
            )
        return {
            "mode": str(mode),
            "type": relation_type,
            "subject": members[0],
            "object": members[1],
        }
    if not role_bindings:
        raise ValueError("nary identity needs role bindings; participants carry no role")
    return {
        "mode": str(mode),
        "type": relation_type,
        "roles": sorted([str(binding.role), str(binding.member_ref)] for binding in role_bindings),
    }


def logical_relation_id(
    arity_mode: RelationArityMode,
    relation_type: str,
    participants: Sequence[str],
    role_bindings: Sequence[RoleBindingLike] = (),
    *,
    valid_from: object = None,
    valid_to: object = None,
) -> str:
    """``RL-`` + 32 hex: which relation this is, across all its revisions."""
    material = logical_material(
        arity_mode,
        relation_type,
        participants,
        role_bindings,
        valid_from=valid_from,
        valid_to=valid_to,
    )
    return LOGICAL_ID_PREFIX + digest128(canonical_material(material))


def relation_id(logical_id: str, revision_material: Mapping[str, Any]) -> str:
    """``RC-`` + 32 hex: this content of one revision.

    ``revision_material`` carries the window, observation/publication times,
    evidence refs, context ref and revision number. Evidence refs are sorted
    here so a claim differing only in the order it collected its refs keeps one
    identity (I-11) — the logical id wins over a caller's own ``logical_id``
    key, so the two can never be derived from different relations.
    """
    material: dict[str, Any] = {"logical_id": logical_id, **dict(revision_material)}
    for key in ("observation_refs", "assertion_refs"):
        value = material.get(key)
        if isinstance(value, list | tuple | set | frozenset):
            material[key] = sorted(value)
    return REVISION_ID_PREFIX + digest128(canonical_material(material))


#: Fields that decide *which relation this is*. They are covered by
#: :func:`logical_material` and enter ``logical_relation_id``, so every revision
#: of one relation shares them. Listed explicitly because the partition below has
#: to be total, and "covered upstream" is exactly the kind of exemption that lets
#: a field go unclassified.
LOGICAL_IDENTITY_MATERIAL_FIELDS: frozenset[str] = frozenset(
    {
        "relation_type",
        "arity_mode",
        "subject_ref",
        "object_ref",
        "role_bindings",
    }
)

#: Fields that make a revision *itself* rather than a view of it. A change here
#: produces a different ``relation_id`` because the claim's semantic content
#: changed: a different extractor or ontology version produced a different claim,
#: and two tenants must never address one id (constitution IV).
IDENTITY_MATERIAL_FIELDS: frozenset[str] = frozenset(
    {
        "revision_number",
        "valid_from",
        "valid_to",
        "observed_at",
        "published_at",
        "context_ref",
        "observation_refs",
        "assertion_refs",
        "source_independence_groups",
        "extraction_version",
        "normalization_version",
        "ontology_version",
        "schema_version",
        "tenant_id",
        "investigation_id",
        "created_by",
    }
)

#: Fields a claim's *projection* may legitimately restate without that being a new
#: claim. Excluded from identity on purpose, and each for a stated reason:
#:
#: - ``status`` / ``known_from`` / ``known_until`` - lifecycle. A claim that has
#:   been superseded keeps the id of the revision that was superseded; changing
#:   identity on a state transition would break the revision chain.
#: - ``confidence`` / ``evidence_grade`` - re-derived by scoring. A rescoring pass
#:   must not mint a new relation, or every ranking change forks the graph.
#: - ``supersedes`` / ``contradicts`` - links to claims that may not exist yet, so
#:   they are filled in after the fact.
#: - ``created_at`` - wall clock. Including it would make an event replayed at a
#:   different moment mint a different id, which is exactly the
#:   determinism the constitution requires of a rebuild (VII). Replay must be a
#:   fixed point.
#:
#: Because these are mutable, two claims sharing a ``relation_id`` may legitimately
#: differ here. That residual is bounded and checked:
#: :func:`detect_content_divergence` reports any such pair, so an in-place edit
#: that was never meant as a projection update is still surfaced rather than
#: silently retained.
MUTABLE_PROJECTION_FIELDS: frozenset[str] = frozenset(
    {
        "status",
        "confidence",
        "evidence_grade",
        "known_from",
        "known_until",
        "supersedes",
        "contradicts",
        "created_at",
    }
)


def revision_material(claim: RelationClaim) -> dict[str, Any]:
    """The documented revision material of one claim (I-11: pure function).

    Covers :data:`IDENTITY_MATERIAL_FIELDS` in full, so every semantic field that
    can change the meaning of a claim changes its id. The derived id fields
    themselves (``relation_id``, ``logical_relation_id``) and the participant shape
    are excluded: the former are outputs, the latter is the logical id this
    material is keyed by.
    """
    return {
        "valid_from": _window(claim.valid_from),
        "valid_to": _window(claim.valid_to),
        "observed_at": _window(claim.observed_at),
        "published_at": _window(claim.published_at),
        "context_ref": claim.context_ref,
        "observation_refs": sorted(claim.observation_refs),
        "assertion_refs": sorted(claim.assertion_refs),
        "source_independence_groups": sorted(
            [sorted(str(ref) for ref in group) for group in claim.source_independence_groups]
        ),
        "extraction_version": claim.extraction_version,
        "normalization_version": claim.normalization_version,
        "ontology_version": claim.ontology_version,
        "schema_version": claim.schema_version,
        "tenant_id": claim.tenant_id,
        "investigation_id": claim.investigation_id,
        "created_by": claim.created_by,
        "revision_number": claim.revision_number,
    }


def verify_material_partition(claim: RelationClaim) -> None:
    """Fail if any claim field is unclassified, or classified twice.

    Without this the partition decays silently: someone adds a field to the
    claim, it lands in no set, and it is quietly excluded from identity --
    reproducing exactly the bug this module was corrected for, one new field at a
    time. The three classes are exhaustive and mutually exclusive:

    * ``LOGICAL_IDENTITY_MATERIAL_FIELDS`` - which relation this is;
    * ``IDENTITY_MATERIAL_FIELDS`` - which revision of it;
    * ``MUTABLE_PROJECTION_FIELDS`` - restatable without a new claim;
    * the two derived id fields, which are outputs rather than inputs.
    """
    material = claim._material()  # noqa: SLF001 - same package, and the point is to read it all
    derived = {"relation_id", "logical_relation_id"}
    identity = LOGICAL_IDENTITY_MATERIAL_FIELDS | IDENTITY_MATERIAL_FIELDS
    classified = identity | MUTABLE_PROJECTION_FIELDS | derived
    unclassified = sorted(set(material) - classified)
    if unclassified:
        raise ValueError(
            "RelationClaim fields are neither identity material nor declared "
            f"mutable projection metadata: {unclassified}. Add each to "
            "LOGICAL_IDENTITY_MATERIAL_FIELDS, IDENTITY_MATERIAL_FIELDS or "
            "MUTABLE_PROJECTION_FIELDS in domain.relation_identity so the "
            "partition stays total."
        )
    for left, right, label in (
        (LOGICAL_IDENTITY_MATERIAL_FIELDS, IDENTITY_MATERIAL_FIELDS, "logical and revision"),
        (identity, MUTABLE_PROJECTION_FIELDS, "identity and mutable"),
    ):
        overlap = sorted(left & right)
        if overlap:
            raise ValueError(f"fields classified as both {label} material: {overlap}")
    if derived & classified - derived:  # pragma: no cover - derived is disjoint by construction
        raise ValueError("a derived id field was also classified as material")
    missing = sorted(IDENTITY_MATERIAL_FIELDS - set(revision_material(claim)))
    if missing:
        raise ValueError(
            f"IDENTITY_MATERIAL_FIELDS declares fields revision_material does not emit: {missing}"
        )


def recompute_identity(claim: RelationClaim) -> tuple[str, str]:
    """Re-derive ``(logical_relation_id, relation_id)`` from a claim's own fields.

    The identity validation layer compares this pair against the ids the claim
    carries, so tampering with any identity-bearing field is detected. ``NARY``
    identity comes from the role bindings, every other mode from the endpoint
    pair — the same partition ``logical_material`` documents.
    """
    mode = claim.arity_mode
    if not isinstance(mode, RelationArityMode):
        mode = RelationArityMode(mode)
    role_bindings = claim.role_bindings
    if mode is RelationArityMode.NARY:
        participants = tuple(binding.member_ref for binding in role_bindings)
    else:
        participants = (claim.subject_ref, claim.object_ref)
    logical = logical_relation_id(
        mode,
        claim.relation_type,
        participants,
        role_bindings,
        valid_from=_window(claim.valid_from),
        valid_to=_window(claim.valid_to),
    )
    return logical, relation_id(logical, revision_material(claim))


@dataclass(frozen=True)
class IdentityCollision:
    """Two distinct claims share one ``relation_id`` — reported, never merged.

    ``claims`` is the ``logical_relation_id`` of every colliding claim,
    duplicates preserved: the relation id carries the logical id, so a bucket
    can only diverge in content, and a divergence under one logical id
    therefore shows the same id twice rather than collapsing to one entry.
    """

    relation_id: str
    claims: tuple[str, ...]


def detect_identity_collisions(
    claims: Iterable[RelationClaim],
) -> tuple[IdentityCollision, ...]:
    """Every ``relation_id`` bucket holding more than one distinct claim (FR-011).

    Byte-identical claims in one bucket are an idempotent re-write (I-11), not
    a collision; only distinct content sharing an id is reported. Colliding
    claims are always returned whole — merging them is what a collision looks
    like at read time, so it must never happen silently.
    """
    buckets: dict[str, list[RelationClaim]] = {}
    for claim in claims:
        buckets.setdefault(claim.relation_id, []).append(claim)
    collisions = [
        IdentityCollision(
            relation_id=bucket_id,
            claims=tuple(sorted(claim.logical_relation_id for claim in bucket)),
        )
        for bucket_id, bucket in buckets.items()
        if len(bucket) > 1 and len({claim.content_hash for claim in bucket}) > 1
    ]
    return tuple(sorted(collisions, key=lambda collision: collision.relation_id))


def identity_collision_count(claims: Iterable[RelationClaim]) -> int:
    """How many distinct colliding buckets a claim set holds (FR-011)."""
    return len(detect_identity_collisions(claims))


@dataclass(frozen=True)
class ContentDivergence:
    """One ``relation_id`` whose claims disagree only on mutable projection fields.

    Not an integrity break: ``status``, ``confidence`` and the rest are declared
    mutable precisely so a re-scoring pass can restate them without minting a new
    relation. It is reported rather than ignored because two of these is usually
    a lost update -- the second write silently overwrote the first -- and that is
    worth seeing. ``fields`` names exactly what disagreed, so the distinction
    between "rescored" and "a semantic field changed" needs no guesswork.
    """

    relation_id: str
    fields: tuple[str, ...]
    content_hashes: tuple[str, ...]


def detect_content_divergence(claims: Iterable[RelationClaim]) -> tuple[ContentDivergence, ...]:
    """Buckets where one ``relation_id`` carries differing ``content_hash`` (FR-011).

    The complementary question to :func:`detect_identity_collisions`. Collision
    detection says "one id, many claims"; this says *which* fields disagreed,
    which is what separates a benign re-score from a claim whose identity material
    moved without a new id being minted for it.
    """
    buckets: dict[str, list[RelationClaim]] = {}
    for claim in claims:
        buckets.setdefault(claim.relation_id, []).append(claim)

    divergences: list[ContentDivergence] = []
    for bucket_id, bucket in buckets.items():
        hashes = {claim.content_hash for claim in bucket}
        if len(bucket) < 2 or len(hashes) < 2:
            continue
        materials = [claim._material() for claim in bucket]  # noqa: SLF001 - see verify_material_partition
        differing = tuple(
            sorted(
                key
                for key in materials[0]
                if len({canonical_material(material.get(key)) for material in materials}) > 1
            )
        )
        divergences.append(
            ContentDivergence(
                relation_id=bucket_id,
                fields=differing,
                content_hashes=tuple(sorted(hashes)),
            )
        )
    return tuple(sorted(divergences, key=lambda divergence: divergence.relation_id))


@dataclass(frozen=True)
class IdentityForgery:
    """A claim whose ``relation_id`` does not follow from its own identity material.

    The strongest statement this module can make, and the one that cannot be
    reached by divergence: not "two claims disagree" but "this single claim is not
    addressed by its own contents". A tampered ``extraction_version`` or
    ``tenant_id`` reaches here, and it means the id was written rather than
    derived -- which is precisely the property the whole module exists to make
    verifiable.

    There is deliberately no field naming the discrepancy. Recomputing from the
    claim cannot say *which* field was edited, only that the id no longer follows;
    naming one would be a guess dressed as a diagnosis. Diff the claim against its
    source of truth for that, or use :func:`detect_content_divergence` to compare
    two claims under one id.
    """

    relation_id: str
    expected_relation_id: str


def detect_identity_forgery(claims: Iterable[RelationClaim]) -> tuple[IdentityForgery, ...]:
    """Claims whose carried id does not match a re-derivation from their own fields.

    Recomputes identity from the record and compares. Also serves as the
    self-check that identity derivation stayed total after the material changed.
    """
    forgeries: list[IdentityForgery] = []
    for claim in claims:
        _, expected = recompute_identity(claim)
        if expected != claim.relation_id:
            forgeries.append(
                IdentityForgery(
                    relation_id=claim.relation_id,
                    expected_relation_id=expected,
                )
            )
    return tuple(sorted(forgeries, key=lambda forgery: forgery.relation_id))


__all__ = [
    "DIGEST_BITS",
    "IDENTITY_MATERIAL_FIELDS",
    "LOGICAL_IDENTITY_MATERIAL_FIELDS",
    "LOGICAL_ID_PREFIX",
    "MUTABLE_PROJECTION_FIELDS",
    "REVISION_ID_PREFIX",
    "ContentDivergence",
    "IdentityCollision",
    "IdentityForgery",
    "RelationArityMode",
    "RoleBindingLike",
    "canonical_material",
    "detect_content_divergence",
    "detect_identity_collisions",
    "detect_identity_forgery",
    "digest128",
    "identity_collision_count",
    "logical_material",
    "logical_relation_id",
    "recompute_identity",
    "relation_id",
    "revision_material",
    "verify_material_partition",
]
