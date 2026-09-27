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
``(subject, object)`` for ``DIRECTED``, sorted ``(role, member)`` pairs for
``NARY``, and ordered members with the window for ``TEMPORAL``.

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
    ``(subject, object)``, ``TEMPORAL`` preserves its ordered members), so
    sorting a tuple would be the one thing that must never happen here.
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
    """Arity vocabulary; the mode is part of the identity material (ADR-0023)."""

    UNDIRECTED = "undirected"
    DIRECTED = "directed"
    NARY = "nary"
    TEMPORAL = "temporal"

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

    ``TEMPORAL`` folds the window in; every other mode excludes it, so folding a
    window into a directed relation would make all directed relations
    revision-addressed and destroy the identity/revision split.
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
    if mode is RelationArityMode.NARY:
        if not role_bindings:
            raise ValueError("nary identity needs role bindings; participants carry no role")
        return {
            "mode": str(mode),
            "type": relation_type,
            "roles": sorted(
                [str(binding.role), str(binding.member_ref)] for binding in role_bindings
            ),
        }
    return {
        "mode": str(mode),
        "type": relation_type,
        "members": [str(participant) for participant in participants],
        "valid_from": _window(valid_from),
        "valid_to": _window(valid_to),
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


def revision_material(claim: RelationClaim) -> dict[str, Any]:
    """The documented revision material of one claim (I-11: pure function)."""
    return {
        "valid_from": _window(claim.valid_from),
        "valid_to": _window(claim.valid_to),
        "observed_at": _window(claim.observed_at),
        "published_at": _window(claim.published_at),
        "context_ref": claim.context_ref,
        "observation_refs": sorted(claim.observation_refs),
        "assertion_refs": sorted(claim.assertion_refs),
        "revision_number": claim.revision_number,
    }


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


__all__ = [
    "DIGEST_BITS",
    "LOGICAL_ID_PREFIX",
    "REVISION_ID_PREFIX",
    "IdentityCollision",
    "RelationArityMode",
    "RoleBindingLike",
    "canonical_material",
    "detect_identity_collisions",
    "digest128",
    "identity_collision_count",
    "logical_material",
    "logical_relation_id",
    "recompute_identity",
    "relation_id",
    "revision_material",
]
