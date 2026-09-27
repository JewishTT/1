"""Relation identity: arity canonicalisation, id shape, distinctness, tampering.

Tasks T008/T009/T010 (US1), T015/T016 (US2) and T029 of
``specs/016-relation-evidence-graph-fabric``. Pins ADR-0023: identity is a
128-bit truncated SHA-256 over documented material, arity mode is part of that
material, and a 1,000,000-claim corpus neither collides nor hides a collision.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from domain.relation_claim import RelationClaim, RelationRoleBinding
from domain.relation_identity import (
    DIGEST_BITS,
    LOGICAL_ID_PREFIX,
    REVISION_ID_PREFIX,
    IdentityCollision,
    RelationArityMode,
    _normalise,
    canonical_material,
    detect_identity_collisions,
    digest128,
    identity_collision_count,
    logical_material,
    logical_relation_id,
    recompute_identity,
    relation_id,
)

pytestmark = pytest.mark.unit

_HEX32 = re.compile(r"^[0-9a-f]{32}$")
_LOGICAL = re.compile(rf"^{LOGICAL_ID_PREFIX}[0-9a-f]{{32}}$")
_REVISION = re.compile(rf"^{REVISION_ID_PREFIX}[0-9a-f]{{32}}$")
_HEX = "0123456789abcdef"
_MODES = tuple(RelationArityMode)

_FROM = datetime(2017, 1, 1, tzinfo=UTC)
_TO = datetime(2022, 6, 1, tzinfo=UTC)
_OBSERVED = datetime(2022, 7, 1, 9, 0, tzinfo=UTC)

def _corpus_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "")
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


_CORPUS = _corpus_env("RELATION_IDENTITY_CORPUS", 1_000_000)
_MIXED_CORPUS = 5_000
_CLAIM_CORPUS = 5_000

_REVISION_MATERIAL = {
    "valid_from": "2017-01-01T00:00:00+00:00",
    "valid_to": "2022-06-01T00:00:00+00:00",
    "observed_at": "2022-07-01T09:00:00+00:00",
    "published_at": None,
    "context_ref": "CX-1",
    "observation_refs": ["OB-1", "OB-2"],
    "assertion_refs": ["AS-1"],
    "revision_number": 1,
}


def _nary(*bindings: tuple[str, str]) -> tuple[RelationRoleBinding, ...]:
    return tuple(RelationRoleBinding(role, member) for role, member in bindings)


# --------------------------------------------------------------------------
# T008: direction is assertable for directed types, symmetric for co-occurrence
# --------------------------------------------------------------------------


def test_t008_directed_reverse_diverges_undirected_reverse_collides() -> None:
    forward = logical_relation_id(RelationArityMode.DIRECTED, "works_for", ("ENT-A", "ENT-B"))
    reverse = logical_relation_id(RelationArityMode.DIRECTED, "works_for", ("ENT-B", "ENT-A"))
    assert forward != reverse

    co_occurs = logical_relation_id(
        RelationArityMode.UNDIRECTED, "co_occurs_with", ("ENT-A", "ENT-B")
    )
    mirrored = logical_relation_id(
        RelationArityMode.UNDIRECTED, "co_occurs_with", ("ENT-B", "ENT-A")
    )
    assert co_occurs == mirrored

    assert relation_id(forward, _REVISION_MATERIAL) != relation_id(reverse, _REVISION_MATERIAL)


def test_t008_undirected_deduplicates_repeated_participants() -> None:
    once = logical_relation_id(RelationArityMode.UNDIRECTED, "co_occurs_with", ("ENT-A", "ENT-B"))
    repeated = logical_relation_id(
        RelationArityMode.UNDIRECTED, "co_occurs_with", ("ENT-B", "ENT-A", "ENT-B")
    )
    assert once == repeated


def test_t008_temporal_window_participates_in_identity() -> None:
    participants = ("ENT-A", "ENT-B")
    first = logical_relation_id(
        RelationArityMode.TEMPORAL, "employment", participants, valid_from="2017", valid_to="2020"
    )
    second = logical_relation_id(
        RelationArityMode.TEMPORAL, "employment", participants, valid_from="2017", valid_to="2022"
    )
    assert first != second
    assert logical_material(
        RelationArityMode.TEMPORAL,
        "employment",
        participants,
        valid_from="2017",
        valid_to="2020",
    ) == {
        "mode": "temporal",
        "type": "employment",
        "members": ["ENT-A", "ENT-B"],
        "valid_from": "2017",
        "valid_to": "2020",
    }


def test_t008_arity_mode_is_part_of_the_identity_material() -> None:
    participants = ("ENT-P1", "ENT-O1")
    directed = logical_relation_id(RelationArityMode.DIRECTED, "employment", participants)
    nary = logical_relation_id(
        RelationArityMode.NARY,
        "employment",
        (),
        _nary(("person", "ENT-P1"), ("organization", "ENT-O1")),
    )
    assert directed != nary


def test_t008_temporal_preserves_participant_order() -> None:
    assert RelationArityMode.UNDIRECTED.default_neighbor_direction == "both"
    assert RelationArityMode.NARY.default_neighbor_direction == "both"
    assert RelationArityMode.DIRECTED.default_neighbor_direction == "out"
    assert RelationArityMode.TEMPORAL.default_neighbor_direction == "out"
    assert logical_relation_id(
        RelationArityMode.TEMPORAL, "employment", ("ENT-A", "ENT-B")
    ) != logical_relation_id(RelationArityMode.TEMPORAL, "employment", ("ENT-B", "ENT-A"))


# --------------------------------------------------------------------------
# T009: every id is a mode prefix plus exactly 32 lowercase hex characters
# --------------------------------------------------------------------------


def test_t009_digest_is_128_bits_of_lowercase_hex() -> None:
    assert DIGEST_BITS == 128
    assert len(digest128("")) == 32
    assert _HEX32.match(digest128(""))
    assert _HEX32.match(digest128("идентичность-Ω"))


def test_t009_canonical_material_is_order_independent() -> None:
    assert canonical_material({"b": 1, "a": [1, 2]}) == canonical_material({"a": [1, 2], "b": 1})
    assert canonical_material({"a": 1}) == '{"a":1}'
    assert canonical_material({"a": {"z": 1, "y": 2}}) == '{"a":{"y":2,"z":1}}'


def test_t009_canonical_material_normalises_temporal_and_unordered_values() -> None:
    assert canonical_material({"at": datetime(2017, 1, 1, tzinfo=UTC)}) == (
        '{"at":"2017-01-01T00:00:00+00:00"}'
    )
    assert canonical_material({"at": datetime(2017, 1, 1)}) == '{"at":"2017-01-01T00:00:00"}'
    assert canonical_material({"at": datetime(2017, 1, 1, tzinfo=UTC)}) != canonical_material(
        {"at": datetime(2017, 1, 1)}
    )
    assert canonical_material({"refs": {"b", "a"}}) == '{"refs":["a","b"]}'
    assert canonical_material({"refs": ("b", "a")}) == '{"refs":["b","a"]}'


def test_t009_canonical_material_equals_explicit_normalisation() -> None:
    payload = {
        "mode": RelationArityMode.NARY,
        "at": datetime(2017, 1, 1, tzinfo=UTC),
        "refs": {"b", "a"},
        "nested": ({"inner": datetime(2017, 1, 1)}, {"inner": 1}),
    }
    assert canonical_material(payload) == json.dumps(
        _normalise(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )


@pytest.mark.parametrize("mode", _MODES)
def test_t009_both_id_kinds_carry_a_prefix_and_32_hex(mode: RelationArityMode) -> None:
    participants = ("ENT-A", "ENT-B")
    bindings = (
        _nary(("organization", "ENT-B"), ("person", "ENT-A"))
        if mode is RelationArityMode.NARY
        else ()
    )
    logical = logical_relation_id(mode, "employment", participants, bindings)
    revision = relation_id(logical, _REVISION_MATERIAL)
    assert _LOGICAL.match(logical), logical
    assert _REVISION.match(revision), revision
    assert len(logical) == 35 and len(revision) == 35
    material = logical_material(mode, "employment", participants, bindings)
    assert digest128(canonical_material(material)) == logical[len(LOGICAL_ID_PREFIX) :]
    assert (
        digest128(canonical_material({"logical_id": logical, **_REVISION_MATERIAL}))
        == (revision[len(REVISION_ID_PREFIX) :])
    )


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (
            RelationArityMode.UNDIRECTED,
            {"mode": "undirected", "type": "co_occurs_with", "members": ["ENT-A", "ENT-B"]},
        ),
        (
            RelationArityMode.DIRECTED,
            {"mode": "directed", "type": "works_for", "subject": "ENT-A", "object": "ENT-B"},
        ),
        (
            RelationArityMode.NARY,
            {
                "mode": "nary",
                "type": "employment",
                "roles": [["organization", "ENT-B"], ["person", "ENT-A"]],
            },
        ),
    ],
)
def test_t009_material_shapes_match_the_canonicalisation_table(
    mode: RelationArityMode, expected: dict
) -> None:
    bindings = (
        _nary(("person", "ENT-A"), ("organization", "ENT-B"))
        if mode is RelationArityMode.NARY
        else ()
    )
    assert logical_material(mode, expected["type"], ("ENT-A", "ENT-B"), bindings) == expected


def test_t009_directed_requires_exactly_two_participants() -> None:
    with pytest.raises(ValueError):
        logical_material(RelationArityMode.DIRECTED, "works_for", ("ENT-A", "ENT-B", "ENT-C"))
    with pytest.raises(ValueError):
        logical_material(RelationArityMode.DIRECTED, "works_for", ("ENT-A",))


def test_t009_revision_material_is_order_insensitive_and_revision_addressed() -> None:
    logical = logical_relation_id(RelationArityMode.DIRECTED, "works_for", ("ENT-A", "ENT-B"))
    first = relation_id(logical, _REVISION_MATERIAL)
    shuffled = relation_id(
        logical,
        {**_REVISION_MATERIAL, "observation_refs": ["OB-2", "OB-1"], "assertion_refs": ["AS-1"]},
    )
    assert first == shuffled
    assert relation_id(logical, {**_REVISION_MATERIAL, "revision_number": 2}) != first
    other = logical_relation_id(RelationArityMode.DIRECTED, "works_for", ("ENT-B", "ENT-C"))
    assert relation_id(other, _REVISION_MATERIAL) != first


# --------------------------------------------------------------------------
# T010: N-ary identity ignores member order and honours role assignment
# --------------------------------------------------------------------------


def test_t010_nary_identity_is_order_free_but_role_sensitive() -> None:
    person_first = logical_relation_id(
        RelationArityMode.NARY,
        "employment",
        (),
        _nary(("person", "ENT-P1"), ("organization", "ENT-O1")),
    )
    organization_first = logical_relation_id(
        RelationArityMode.NARY,
        "employment",
        (),
        _nary(("organization", "ENT-O1"), ("person", "ENT-P1")),
    )
    assert person_first == organization_first

    roles_permuted = logical_relation_id(
        RelationArityMode.NARY,
        "employment",
        (),
        _nary(("person", "ENT-O1"), ("organization", "ENT-P1")),
    )
    assert roles_permuted != person_first


def test_t010_nary_role_names_are_load_bearing() -> None:
    as_ceo = logical_relation_id(
        RelationArityMode.NARY, "employment", (), _nary(("ceo", "ENT-P1"), ("org", "ENT-O1"))
    )
    as_person = logical_relation_id(
        RelationArityMode.NARY, "employment", (), _nary(("org", "ENT-O1"), ("person", "ENT-P1"))
    )
    assert as_ceo != as_person


# --------------------------------------------------------------------------
# T015: 1,000,000 deterministically generated claims, zero collisions
# --------------------------------------------------------------------------


def test_t015_one_million_claims_yield_one_million_distinct_ids() -> None:
    """SC-002 at full scale: 1,000,000 claims, 1,000,000 distinct ids, none malformed.

    One canonicalisation plus one truncated SHA-256 per claim, so the sweep
    costs roughly 30-50s on a slow ``json`` encoder (~20us per four-key
    ``json.dumps`` here versus ~2us on a current CPU). The 1,000,000 figure is
    the spec's, so it is not scaled down to keep a unit test quick.
    """
    ids: set[str] = set()
    malformed: list[str] = []
    for index in range(_CORPUS):
        value = logical_relation_id(
            RelationArityMode.DIRECTED, "works_for", (f"ENT-{index}", f"ORG-{index}")
        )
        ids.add(value)
        if value[:3] != LOGICAL_ID_PREFIX or value[3:].strip(_HEX):
            malformed.append(value)
    assert len(ids) == _CORPUS
    assert not malformed
    # The logical id is part of the revision material, so distinct logical ids
    # cannot collapse into one relation id; the composition is pinned above.
    assert len({value[3:] for value in ids}) == _CORPUS


def test_t015_mixed_arity_corpus_is_collision_free() -> None:
    ids: set[str] = set()
    for index in range(_MIXED_CORPUS):
        mode = _MODES[index % len(_MODES)]
        bindings = (
            _nary(("organization", f"ORG-{index}"), ("person", f"ENT-{index}"))
            if mode is RelationArityMode.NARY
            else ()
        )
        ids.add(logical_relation_id(mode, "works_for", (f"ENT-{index}", f"ORG-{index}"), bindings))
    assert len(ids) == _MIXED_CORPUS


def _directed_claim(index: int) -> RelationClaim:
    """A derived directed claim: its ids are recomputed from its own fields."""
    return _derive(
        RelationClaim(
            relation_id="RC-pending",
            logical_relation_id="RL-pending",
            revision_number=1,
            relation_type="works_for",
            arity_mode=RelationArityMode.DIRECTED,
            subject_ref=f"ENT-{index}",
            object_ref=f"ORG-{index}",
            valid_from=_FROM,
            valid_to=_TO,
            observed_at=_OBSERVED,
            assertion_refs=(f"AS-{index}",),
            observation_refs=(f"OB-{index}",),
            context_ref=f"CX-{index % 97}",
            source_independence_groups=((f"family-{index % 13}",),),
            tenant_id="tenant-a",
        )
    )


def _nary_claim(index: int) -> RelationClaim:
    """A derived N-ary claim: the bindings carry the identity, not the endpoints."""
    return _derive(
        RelationClaim(
            relation_id="RC-pending",
            logical_relation_id="RL-pending",
            revision_number=1,
            relation_type="works_for",
            arity_mode=RelationArityMode.NARY,
            subject_ref=f"ENT-{index}",
            object_ref=f"ORG-{index}",
            role_bindings=(
                RelationRoleBinding("organization", f"ORG-{index}"),
                RelationRoleBinding("person", f"ENT-{index}"),
            ),
            valid_from=_FROM,
            valid_to=_TO,
            observed_at=_OBSERVED,
            assertion_refs=(f"AS-{index}",),
            observation_refs=(f"OB-{index}",),
            context_ref=f"CX-{index % 97}",
            source_independence_groups=((f"family-{index % 13}",),),
            tenant_id="tenant-a",
        )
    )


def _derive(claim: RelationClaim) -> RelationClaim:
    logical, revision = recompute_identity(claim)
    return replace(claim, logical_relation_id=logical, relation_id=revision)


def test_t015_claim_corpus_round_trips_with_no_unreported_collision() -> None:
    claims = [_directed_claim(index) for index in range(_CLAIM_CORPUS)]
    assert len({claim.relation_id for claim in claims}) == _CLAIM_CORPUS
    assert all(len(claim.relation_id) == 35 for claim in claims)
    assert detect_identity_collisions(claims) == ()
    assert identity_collision_count(claims) == 0
    first = claims[0]
    assert recompute_identity(first) == (first.logical_relation_id, first.relation_id)
    assert RelationClaim.from_dict(first.to_dict()) == first


def test_t015_idempotent_rewrite_is_not_a_collision() -> None:
    claim = _directed_claim(1)
    assert detect_identity_collisions((claim, claim)) == ()
    assert identity_collision_count((claim, claim)) == 0


def test_t029_collision_is_reported_with_every_claim_and_never_merged() -> None:
    claim = _directed_claim(7)
    divergent = replace(claim, confidence=0.9)
    assert divergent.relation_id == claim.relation_id
    assert divergent.logical_relation_id == claim.logical_relation_id
    assert divergent.content_hash != claim.content_hash

    collisions = detect_identity_collisions((claim, divergent, _directed_claim(8)))
    assert len(collisions) == 1
    assert isinstance(collisions[0], IdentityCollision)
    assert collisions[0].relation_id == claim.relation_id
    # The relation id carries the logical id, so a bucket can only diverge in
    # content; both colliding claims are returned, never merged (FR-011).
    assert collisions[0].claims == (claim.logical_relation_id, claim.logical_relation_id)
    assert identity_collision_count((claim, divergent, _directed_claim(8))) == 1
    assert detect_identity_collisions(tuple(reversed((claim, divergent)))) == collisions


# --------------------------------------------------------------------------
# T016: tampering with any identity-bearing field is caught by re-derivation
# --------------------------------------------------------------------------


def test_t016_recomputation_reproduces_the_ids_a_claim_carries() -> None:
    claim = _directed_claim(11)
    assert recompute_identity(claim) == (claim.logical_relation_id, claim.relation_id)
    assert _LOGICAL.match(claim.logical_relation_id)
    assert _REVISION.match(claim.relation_id)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("relation_type", "employed_by"),
        ("subject_ref", "ENT-TAMPERED"),
        ("object_ref", "ORG-TAMPERED"),
        ("valid_from", datetime(2016, 1, 1, tzinfo=UTC)),
        ("valid_to", datetime(2030, 1, 1, tzinfo=UTC)),
        ("observed_at", datetime(2030, 1, 1, tzinfo=UTC)),
        ("published_at", datetime(2030, 1, 1, tzinfo=UTC)),
        ("context_ref", "CX-tampered"),
        ("observation_refs", ("OB-1",)),
        ("assertion_refs", ()),
        ("revision_number", 2),
        ("arity_mode", RelationArityMode.TEMPORAL),
    ],
)
def test_t016_tampering_with_a_directed_field_is_caught_by_re_derivation(
    field: str, value: object
) -> None:
    claim = _directed_claim(13)
    tampered = replace(claim, **{field: value})
    derived = recompute_identity(tampered)
    assert derived != (tampered.logical_relation_id, tampered.relation_id)
    assert derived != (claim.logical_relation_id, claim.relation_id)


@pytest.mark.parametrize(
    "bindings",
    [
        (("employee", "ENT-13"), ("organization", "ORG-13")),
        (("organization", "ORG-13"), ("person", "ENT-14")),
    ],
)
def test_t016_tampering_with_a_role_binding_is_caught_by_re_derivation(
    bindings: tuple[tuple[str, str], ...],
) -> None:
    claim = _nary_claim(13)
    tampered = replace(claim, role_bindings=_nary(*bindings))
    derived = recompute_identity(tampered)
    assert derived != (tampered.logical_relation_id, tampered.relation_id)
    assert derived != (claim.logical_relation_id, claim.relation_id)


def test_t016_an_untampered_claim_re_derives_identically_on_replay() -> None:
    claim = _directed_claim(17)
    replayed = RelationClaim.from_dict(claim.to_dict())
    assert recompute_identity(replayed) == recompute_identity(claim)
    assert replayed.content_hash == claim.content_hash
