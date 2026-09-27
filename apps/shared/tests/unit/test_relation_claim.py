"""Relation claim: revision identity, content hash, the ten rejections, counts.

Tasks T011/T012/T013/T014 (US1) and T016 of
``specs/016-relation-evidence-graph-fabric`` (the identity/re-derivation half of
T016 is pinned in ``test_relation_identity.py``). FR-003 identity is separate
from version, FR-005 identical content is idempotent (I-11), FR-007 a claim
carries an evidence context (I-12), FR-001 a relation is a first-class claim.
"""

from __future__ import annotations

from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from domain.relation_claim import (
    DEFAULT_CONFIDENCE,
    EvidenceGrade,
    RelationClaim,
    RelationContractError,
    RelationRevision,
    RelationRoleBinding,
    RelationStatus,
    check_role_bindings,
    revisions_of,
)
from domain.relation_identity import RelationArityMode, recompute_identity

pytestmark = pytest.mark.unit

_FROM = datetime(2017, 1, 1, tzinfo=UTC)
_MID = datetime(2020, 1, 1, tzinfo=UTC)
_TO = datetime(2022, 6, 1, tzinfo=UTC)
_OBSERVED = datetime(2022, 7, 1, 9, 0, tzinfo=UTC)
_PUBLISHED = datetime(2022, 7, 2, 12, 0, tzinfo=UTC)
_CREATED = datetime(2022, 7, 3, 8, 30, tzinfo=UTC)

_PENDING_LOGICAL = "RL-pending"
_PENDING_REVISION = "RC-pending"
_FORGED = "RC-" + "0" * 32


def _claim(**overrides: Any) -> RelationClaim:
    """A valid N-ary claim whose ids are derived from its own fields."""
    fields_: dict[str, Any] = {
        "relation_id": _PENDING_REVISION,
        "logical_relation_id": _PENDING_LOGICAL,
        "revision_number": 1,
        "relation_type": "employment",
        "arity_mode": RelationArityMode.NARY,
        "subject_ref": "ENT-P1",
        "object_ref": "ENT-O1",
        "role_bindings": (
            RelationRoleBinding("organization", "ENT-O1", "organization"),
            RelationRoleBinding("person", "ENT-P1", "person"),
        ),
        "valid_from": _FROM,
        "valid_to": None,
        "observed_at": _OBSERVED,
        "published_at": _PUBLISHED,
        "known_from": _OBSERVED,
        "known_until": None,
        "assertion_refs": ("AS-1",),
        "observation_refs": ("OB-1",),
        "context_ref": "CX-1",
        "source_independence_groups": (("family-a", "family-a"),),
        "extraction_version": "1.0.0",
        "normalization_version": "1.0.0",
        "ontology_version": "onto-1",
        "schema_version": "1",
        "status": RelationStatus.ACTIVE,
        "confidence": DEFAULT_CONFIDENCE,
        "evidence_grade": EvidenceGrade.UNGRADED,
        "tenant_id": "tenant-a",
        "investigation_id": "inv-1",
        "created_by": "extractor-1",
        "supersedes": "",
        "contradicts": (),
        "created_at": _CREATED,
    }
    fields_.update(overrides)
    claim = RelationClaim(**fields_)
    logical, revision = recompute_identity(claim)
    if (claim.logical_relation_id, claim.relation_id) == (logical, revision):
        return claim
    return replace(claim, logical_relation_id=logical, relation_id=revision)


def _valid_kwargs(**overrides: Any) -> dict[str, Any]:
    """Construction kwargs that satisfy every rejection rule."""
    return {
        "relation_id": _FORGED,
        "logical_relation_id": _PENDING_LOGICAL,
        "revision_number": 1,
        "relation_type": "employment",
        "arity_mode": RelationArityMode.NARY,
        "subject_ref": "ENT-P1",
        "object_ref": "ENT-O1",
        "role_bindings": (
            RelationRoleBinding("organization", "ENT-O1"),
            RelationRoleBinding("person", "ENT-P1"),
        ),
        "valid_from": _FROM,
        "valid_to": _TO,
        "context_ref": "CX-1",
        "observation_refs": ("OB-1",),
        "assertion_refs": ("AS-1",),
        **overrides,
    }


# --------------------------------------------------------------------------
# T011: a correction is a revision, not a second relation
# --------------------------------------------------------------------------


def test_t011_revision_keeps_logical_id_takes_a_new_relation_id_and_increments() -> None:
    first = _claim()
    second = _claim(
        revision_number=first.revision_number + 1,
        valid_to=_TO,
        supersedes=first.relation_id,
    )
    assert second.logical_relation_id == first.logical_relation_id
    assert second.relation_id != first.relation_id
    assert second.revision_number == first.revision_number + 1
    assert second.supersedes == first.relation_id
    assert recompute_identity(second) == (second.logical_relation_id, second.relation_id)
    assert recompute_identity(replace(first, status=RelationStatus.SUPERSEDED)) == (
        first.logical_relation_id,
        first.relation_id,
    )


def test_t011_revision_chain_is_ordered_by_revision_number() -> None:
    first = _claim()
    second = _claim(revision_number=2, valid_to=_TO, supersedes=first.relation_id)
    third = _claim(
        revision_number=3,
        valid_to=_TO,
        supersedes=second.relation_id,
        status=RelationStatus.SUPERSEDED,
    )
    chain = revisions_of((third, first, second), first.logical_relation_id)
    assert isinstance(chain, RelationRevision)
    assert chain.logical_relation_id == first.logical_relation_id
    assert chain.revision_numbers == (1, 2, 3)
    assert chain.current is third
    assert [claim.revision_number for claim in chain.revisions] == [1, 2, 3]
    assert revisions_of((first, second, third), "RL-other").revisions == ()
    assert revisions_of((first, second, third), "RL-other").current is None


def test_t011_superseded_and_contradicted_claims_stay_queryable() -> None:
    first = _claim()
    second = _claim(
        revision_number=2,
        valid_to=_TO,
        supersedes=first.relation_id,
        status=RelationStatus.SUPERSEDED,
        contradicts=(first.relation_id,),
    )
    for status in (
        RelationStatus.ACTIVE,
        RelationStatus.SUPERSEDED,
        RelationStatus.RETRACTED,
        RelationStatus.CONTRADICTED,
        RelationStatus.QUARANTINED,
    ):
        assert replace(second, status=status).status is status
    assert tuple(RelationStatus) == (
        RelationStatus.ACTIVE,
        RelationStatus.SUPERSEDED,
        RelationStatus.RETRACTED,
        RelationStatus.CONTRADICTED,
        RelationStatus.QUARANTINED,
    )
    assert first.relation_id in second.contradicts
    assert first.relation_id != second.relation_id


# --------------------------------------------------------------------------
# T012: identical content is byte-identical and round-trips
# --------------------------------------------------------------------------


def test_t012_identical_content_yields_an_identical_content_hash() -> None:
    first = _claim()
    second = _claim(
        observation_refs=("OB-1",),
        assertion_refs=("AS-1",),
        role_bindings=(
            RelationRoleBinding("person", "ENT-P1", "person"),
            RelationRoleBinding("organization", "ENT-O1", "organization"),
        ),
    )
    assert first == second
    assert first.content_hash == second.content_hash
    assert first.relation_id == second.relation_id
    assert first.logical_relation_id == second.logical_relation_id
    assert len(first.content_hash) == 32
    assert first.content_hash != "0" * 32


def test_t012_ref_order_does_not_change_content_or_identity() -> None:
    ordered = _claim(
        observation_refs=("OB-1", "OB-2"),
        assertion_refs=("AS-1", "AS-2"),
        contradicts=("RC-b", "RC-a"),
        source_independence_groups=(("family-b",), ("family-a",)),
    )
    shuffled = _claim(
        observation_refs=("OB-2", "OB-1"),
        assertion_refs=("AS-2", "AS-1"),
        contradicts=("RC-a", "RC-b"),
        source_independence_groups=(("family-a",), ("family-b",)),
    )
    assert ordered == shuffled
    assert ordered.observation_refs == ("OB-1", "OB-2")
    assert ordered.assertion_refs == ("AS-1", "AS-2")
    assert ordered.contradicts == ("RC-a", "RC-b")
    assert ordered.source_independence_groups == (("family-a",), ("family-b",))
    assert ordered.relation_id == shuffled.relation_id
    assert ordered.content_hash == shuffled.content_hash
    duplicated = _claim(
        observation_refs=("OB-1", "OB-1", "OB-2"),
        assertion_refs=("AS-1", "AS-2", "AS-1"),
        source_independence_groups=(("family-a", "family-a"), ("family-b",)),
    )
    assert duplicated.relation_id == ordered.relation_id
    assert duplicated.source_independence_groups == (("family-a",), ("family-b",))


def test_t012_to_dict_from_dict_round_trips_every_field() -> None:
    claim = _claim()
    payload = claim.to_dict()
    assert payload["content_hash"] == claim.content_hash
    assert set(payload) == {field.name for field in fields(RelationClaim)} | {"content_hash"}
    restored = RelationClaim.from_dict(payload)
    assert restored == claim
    assert restored.to_dict() == payload
    for field in fields(RelationClaim):
        assert getattr(restored, field.name) == getattr(claim, field.name), field.name
    assert recompute_identity(restored) == recompute_identity(claim)
    assert restored.content_hash == claim.content_hash


def test_t012_round_trip_survives_iso_strings_and_enums() -> None:
    claim = _claim(
        status=RelationStatus.CONTRADICTED,
        evidence_grade=EvidenceGrade.MODERATE,
        arity_mode=RelationArityMode.TEMPORAL,
        confidence=0.9,
        valid_to=_TO,
    )
    payload = claim.to_dict()
    assert payload["status"] == "contradicted"
    assert payload["evidence_grade"] == "moderate"
    assert payload["arity_mode"] == "temporal"
    assert payload["valid_to"] == "2022-06-01T00:00:00+00:00"
    restored = RelationClaim.from_dict(payload)
    assert restored == claim
    assert restored.status is RelationStatus.CONTRADICTED
    assert restored.evidence_grade is EvidenceGrade.MODERATE
    assert restored.arity_mode is RelationArityMode.TEMPORAL


def test_t012_a_changed_field_changes_the_content_hash() -> None:
    claim = _claim()
    for field, value in (
        ("confidence", 0.99),
        ("object_ref", "ENT-O2"),
        ("created_by", "extractor-2"),
        ("evidence_grade", EvidenceGrade.WEAK),
        ("known_until", _TO),
    ):
        assert replace(claim, **{field: value}).content_hash != claim.content_hash


# --------------------------------------------------------------------------
# T013: the ten construction rejections
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        pytest.param(
            {"subject_ref": "ENT-P1", "object_ref": "ENT-P1"}, "self_loop", id="self_loop"
        ),
        pytest.param({"relation_type": ""}, "missing_relation_type", id="relation_type"),
        pytest.param({"context_ref": ""}, "missing_context_ref", id="context_ref"),
        pytest.param(
            {"role_bindings": (RelationRoleBinding("person", "ENT-P1"),)},
            "insufficient_members",
            id="insufficient_members",
        ),
        pytest.param(
            {
                "role_bindings": (
                    RelationRoleBinding("person", "ENT-P1"),
                    RelationRoleBinding("organization", "ENT-P1"),
                )
            },
            "duplicate_member",
            id="duplicate_member",
        ),
        pytest.param(
            {"arity_mode": RelationArityMode.DIRECTED}, "role_binding_on_directed", id="directed"
        ),
        pytest.param(
            {"valid_from": _TO, "valid_to": _FROM}, "inverted_validity", id="inverted_validity"
        ),
        pytest.param({"confidence": 1.5}, "confidence_out_of_range", id="confidence_high"),
        pytest.param({"confidence": -0.1}, "confidence_out_of_range", id="confidence_low"),
        pytest.param({"revision_number": 0}, "invalid_revision_number", id="revision_number"),
        pytest.param({"supersedes": _FORGED}, "self_supersession", id="self_supersession"),
    ],
)
def test_t013_every_construction_rejection_has_a_stable_code(
    overrides: dict[str, Any], code: str
) -> None:
    with pytest.raises(RelationContractError) as caught:
        RelationClaim(**_valid_kwargs(**overrides))
    assert caught.value.code == code
    assert code in str(caught.value)
    assert isinstance(caught.value, ValueError)


def test_t013_a_valid_claim_passes_every_rejection() -> None:
    claim = RelationClaim(**_valid_kwargs())
    assert claim.arity_mode is RelationArityMode.NARY
    assert claim.confidence == 0.5
    assert claim.role_bindings == (
        RelationRoleBinding("organization", "ENT-O1"),
        RelationRoleBinding("person", "ENT-P1"),
    )


def test_t013_role_binding_rules_reject_empty_and_repeated_bindings() -> None:
    with pytest.raises(RelationContractError) as empty:
        check_role_bindings((RelationRoleBinding("", "ENT-P1"),))
    assert empty.value.code == "empty_role"

    with pytest.raises(RelationContractError) as repeated_role:
        check_role_bindings(
            (
                RelationRoleBinding("person", "ENT-P1"),
                RelationRoleBinding("person", "ENT-P2"),
            )
        )
    assert repeated_role.value.code == "duplicate_role"

    with pytest.raises(RelationContractError) as repeated_member:
        check_role_bindings(
            (
                RelationRoleBinding("person", "ENT-P1"),
                RelationRoleBinding("organization", "ENT-P1"),
            )
        )
    assert repeated_member.value.code == "duplicate_member"

    check_role_bindings(
        (
            RelationRoleBinding("attendee", "ENT-P1"),
            RelationRoleBinding("chair", "ENT-P1"),
        ),
        allow_repeated_member=True,
    )


def test_t013_a_claim_rejects_a_role_bound_twice() -> None:
    with pytest.raises(RelationContractError) as caught:
        RelationClaim(
            **_valid_kwargs(
                role_bindings=(
                    RelationRoleBinding("person", "ENT-P1"),
                    RelationRoleBinding("person", "ENT-P2"),
                )
            )
        )
    assert caught.value.code == "duplicate_role"


# --------------------------------------------------------------------------
# T014: publication count and independent-source count never conflate
# --------------------------------------------------------------------------


def test_t014_two_observations_from_one_family_are_one_independent_source() -> None:
    claim = _claim(
        observation_refs=("OB-1", "OB-2"),
        source_independence_groups=(("family-a",),),
    )
    assert claim.publication_count == 2
    assert claim.independent_source_count == 1
    assert claim.evidence_grade is EvidenceGrade.UNGRADED
    assert len({claim.observation_refs, claim.source_independence_groups}) == 2


def test_t014_the_two_counts_move_independently() -> None:
    single = _claim(
        observation_refs=("OB-1",),
        source_independence_groups=(("family-a",),),
    )
    assert (single.publication_count, single.independent_source_count) == (1, 1)

    same_family = _claim(
        observation_refs=("OB-1", "OB-2"),
        source_independence_groups=(("family-a", "family-a"),),
    )
    assert (same_family.publication_count, same_family.independent_source_count) == (2, 1)

    two_families = _claim(
        observation_refs=("OB-1", "OB-2"),
        source_independence_groups=(("family-a",), ("family-b",)),
    )
    assert (two_families.publication_count, two_families.independent_source_count) == (2, 2)

    unpublished = _claim(
        observation_refs=(),
        assertion_refs=(),
        source_independence_groups=(),
    )
    assert (unpublished.publication_count, unpublished.independent_source_count) == (0, 0)
    assert unpublished.evidence_grade is EvidenceGrade.UNGRADED


# --------------------------------------------------------------------------
# Derived behaviour: validity window, canonicalisation, defaults
# --------------------------------------------------------------------------


def test_is_active_at_follows_the_validity_window() -> None:
    claim = _claim(valid_from=_FROM, valid_to=_TO)
    assert claim.is_active_at(_FROM) is True
    assert claim.is_active_at(_MID) is True
    assert claim.is_active_at(_TO) is False
    assert claim.is_active_at(_FROM - timedelta(days=1)) is False
    assert _claim(valid_from=None, valid_to=None).is_active_at(_MID) is True
    assert _claim(valid_from=_FROM, valid_to=None).is_active_at(_MID) is True
    assert _claim(valid_from=None, valid_to=_TO).is_active_at(_MID) is True


def test_defaults_are_the_documented_ones() -> None:
    claim = RelationClaim(**_valid_kwargs())
    assert claim.role_bindings == (
        RelationRoleBinding("organization", "ENT-O1"),
        RelationRoleBinding("person", "ENT-P1"),
    )
    assert claim.observed_at is None and claim.published_at is None
    assert claim.known_from is None and claim.known_until is None
    assert claim.created_at is None
    assert claim.extraction_version == "" and claim.normalization_version == ""
    assert claim.ontology_version == "" and claim.schema_version == ""
    assert claim.status is RelationStatus.ACTIVE
    assert claim.evidence_grade is EvidenceGrade.UNGRADED
    assert claim.confidence == DEFAULT_CONFIDENCE == 0.5
    assert claim.tenant_id == "default-tenant"
    assert claim.investigation_id == ""
    assert claim.created_by == ""
    assert claim.supersedes == ""
    assert claim.contradicts == ()
