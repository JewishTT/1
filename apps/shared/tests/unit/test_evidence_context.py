"""Evidence context: the content-addressed frame, the resolver, cycle detection.

Tasks T031-T035 (US3) of ``specs/016-relation-evidence-graph-fabric``; contract is
``data-model.md`` section 5 with ``docs/adr/0024-claim-and-context-persistence.md``.
FR-013 the frame is a first-class immutable object, FR-014 ``context_id`` is a content
address over its canonical content, FR-015 mutation raises, FR-016 resolution fails
loudly rather than substituting a default frame, FR-017 a parent cycle is reported.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from domain.evidence_context import (
    ContextCompleteness,
    ContextContractError,
    ContextResolver,
    ContextTrustState,
    EvidenceContext,
    InMemoryContextResolver,
    detect_context_cycle,
)

pytestmark = pytest.mark.unit

_FROM = datetime(2017, 1, 1, tzinfo=UTC)
_TO = datetime(2022, 6, 1, tzinfo=UTC)
_OBSERVED = datetime(2022, 7, 1, 9, 0, tzinfo=UTC)
_PUBLISHED = datetime(2022, 7, 2, 12, 0, tzinfo=UTC)

_UNKNOWN = "CX-" + "0" * 32
_UNREGISTERED = "CX-" + "9f" * 16

#: The field order of ``data-model.md`` section 5, written out rather than derived
#: from the dataclass, so this file fails if the order itself moves.
_FIELD_ORDER = (
    "context_id",
    "tenant_id",
    "investigation_id",
    "entity_anchor",
    "observation_id",
    "source_id",
    "document_id",
    "segment_id",
    "subject_candidate_ids",
    "object_candidate_ids",
    "observed_at",
    "published_at",
    "valid_from",
    "valid_to",
    "source_family",
    "independence_group",
    "language",
    "location_context",
    "extraction_version",
    "normalization_version",
    "ontology_version",
    "completeness",
    "trust_state",
    "policy_snapshot_ref",
    "parent_context_id",
)

#: One fully populated frame, positional, in :data:`_FIELD_ORDER`.
_CANONICAL_VALUES: tuple[Any, ...] = (
    "",
    "tenant-a",
    "inv-1",
    "ENT-P1",
    "OB-1",
    "SRC-1",
    "DOC-1",
    "SEG-1",
    ("ENT-P1", "ENT-P2"),
    ("ENT-O1",),
    _OBSERVED,
    _PUBLISHED,
    _FROM,
    _TO,
    "family-a",
    "independence-1",
    "en",
    "Kyiv",
    "1.0.0",
    "1.0.0",
    "onto-1",
    ContextCompleteness.COMPLETE,
    ContextTrustState.UNVERIFIED,
    "policy-1",
    "",
)

#: The digest is a contract, not an implementation detail: the same frame must
#: address to this id in a fresh process, from a store, and on a re-read.
_CANONICAL_CONTEXT_ID = "CX-pending"


def _canonical_dict() -> dict[str, Any]:
    """The canonical frame as keyword arguments."""
    return dict(zip(_FIELD_ORDER, _CANONICAL_VALUES, strict=True))


def _frame(**overrides: Any) -> EvidenceContext:
    """One fully populated frame, built by keyword with a derived ``context_id``."""
    return EvidenceContext(**{**_canonical_dict(), **overrides})


def _self_loop(frame: EvidenceContext) -> EvidenceContext:
    """Point a frame's ``parent_context_id`` at itself.

    Only a hand-edited or corrupted store row can produce this: construction
    verifies ``context_id`` against the material and no digest is its own input,
    which is exactly why cycle detection lives in the resolver rather than here.
    """
    object.__setattr__(frame, "parent_context_id", frame.context_id)
    return frame


# --------------------------------------------------------------------------
# T031: identical field values by different construction paths, one id
# --------------------------------------------------------------------------


def test_t031_keyword_and_positional_construction_agree_byte_for_byte() -> None:
    keyword = _frame()
    positional = EvidenceContext(*_CANONICAL_VALUES)
    assert tuple(field.name for field in fields(EvidenceContext)) == _FIELD_ORDER
    assert positional == keyword
    assert positional.context_id == keyword.context_id
    assert keyword.context_id == _CANONICAL_CONTEXT_ID
    assert keyword.context_id.startswith("CX-")
    assert len(keyword.context_id) == 35
    assert keyword.context_id != _UNKNOWN
    assert [getattr(positional, name) for name in _FIELD_ORDER] == list(_CANONICAL_VALUES)


def test_t031_candidate_order_and_duplication_canonicalise_to_one_id() -> None:
    ordered = _frame()
    shuffled = _frame(subject_candidate_ids=("ENT-P2", "ENT-P1", "ENT-P2"))
    from_lists = _frame(subject_candidate_ids=["ENT-P2", "ENT-P1"])
    assert ordered == shuffled == from_lists
    assert ordered.subject_candidate_ids == ("ENT-P1", "ENT-P2")
    assert shuffled.subject_candidate_ids == ("ENT-P1", "ENT-P2")
    assert shuffled.context_id == ordered.context_id
    assert from_lists.context_id == ordered.context_id
    assert shuffled.frame_fingerprint == ordered.frame_fingerprint
    assert _frame(object_candidate_ids=("ENT-O2", "ENT-O1")).object_candidate_ids == (
        "ENT-O1",
        "ENT-O2",
    )


def test_t031_enum_text_and_a_record_round_trip_to_one_id() -> None:
    from_text = _frame(completeness="complete", trust_state="unverified")
    round_tripped = EvidenceContext.from_dict(_frame().to_dict())
    positional_text = EvidenceContext(
        *_CANONICAL_VALUES[:-2],
        "complete",
        "unverified",
        *_CANONICAL_VALUES[-1:],
    )
    assert from_text.context_id == _frame().context_id
    assert round_tripped == _frame()
    assert from_text.completeness is ContextCompleteness.COMPLETE
    assert from_text.trust_state is ContextTrustState.UNVERIFIED
    assert positional_text == round_tripped
    assert positional_text.context_id == from_text.context_id == round_tripped.context_id


def test_t031_one_changed_field_changes_the_id() -> None:
    base = _frame()
    for name, value in (
        ("tenant_id", "tenant-b"),
        ("investigation_id", "inv-2"),
        ("entity_anchor", "ENT-P9"),
        ("observation_id", "OB-2"),
        ("valid_to", _OBSERVED),
        ("source_family", "family-b"),
        ("independence_group", "independence-2"),
        ("language", "uk"),
        ("location_context", "Odesa"),
        ("ontology_version", "onto-2"),
        ("policy_snapshot_ref", "policy-2"),
        ("completeness", ContextCompleteness.PARTIAL),
        ("trust_state", ContextTrustState.DISPUTED),
        ("observed_at", None),
        ("subject_candidate_ids", ("ENT-P1",)),
    ):
        changed = replace(base, **{name: value})
        assert changed.context_id != base.context_id, name
        assert changed.frame_fingerprint != base.frame_fingerprint, name


def test_t031_the_frame_fingerprint_is_the_digest_behind_the_id() -> None:
    frame = _frame()
    assert frame.frame_fingerprint == _CANONICAL_CONTEXT_ID.removeprefix("CX-")
    assert len(frame.frame_fingerprint) == 32
    assert int(frame.frame_fingerprint, 16) >= 0
    assert frame.context_id == f"CX-{frame.frame_fingerprint}"
    assert frame.to_dict()["frame_fingerprint"] == frame.frame_fingerprint
    restored = EvidenceContext.from_dict(frame.to_dict())
    assert restored.frame_fingerprint == frame.frame_fingerprint
    assert restored.context_id == frame.context_id


# --------------------------------------------------------------------------
# T032: the frame is frozen
# --------------------------------------------------------------------------


def test_t032_field_assignment_raises_rather_than_altering_the_frame() -> None:
    frame = _frame()
    with pytest.raises(FrozenInstanceError):
        frame.tenant_id = "tenant-z"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        frame.context_id = _UNKNOWN  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        frame.subject_candidate_ids = ("ENT-P7",)  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        frame.observed_at = _FROM  # type: ignore[misc]
    assert frame == _frame()
    assert frame.tenant_id == "tenant-a"
    assert frame.context_id == _CANONICAL_CONTEXT_ID
    assert frame.observed_at == _OBSERVED


def test_t032_a_tuple_field_cannot_hold_a_mutable_copy() -> None:
    frame = _frame()
    assert isinstance(frame.subject_candidate_ids, tuple)
    assert isinstance(frame.object_candidate_ids, tuple)
    with pytest.raises(TypeError):
        frame.subject_candidate_ids[0] = "ENT-P7"  # type: ignore[index]
    with pytest.raises(AttributeError):
        frame.subject_candidate_ids.append("ENT-P7")  # type: ignore[attr-defined]
    extended = frame.subject_candidate_ids + ("ENT-P7",)
    assert extended == ("ENT-P1", "ENT-P2", "ENT-P7")
    assert frame.subject_candidate_ids == ("ENT-P1", "ENT-P2")
    assert len({frame, _frame()}) == 1
    assert hash(frame) == hash(_frame())


# --------------------------------------------------------------------------
# T033: registration is idempotent, resolution fails loudly
# --------------------------------------------------------------------------


def test_t033_register_is_idempotent_and_resolve_returns_the_frame() -> None:
    resolver: ContextResolver = InMemoryContextResolver()
    frame = _frame()
    first = resolver.register(frame)
    second = resolver.register(_frame())
    assert first == second == frame.context_id == _CANONICAL_CONTEXT_ID
    assert len(resolver) == 1
    assert frame.context_id in resolver
    assert resolver.resolve(first) == frame
    assert resolver.resolve(first) is frame
    assert resolver.resolve(frame.context_id).tenant_id == "tenant-a"
    assert "CX-nothing" not in resolver
    assert isinstance(resolver, ContextResolver)


def test_t033_resolve_of_an_unknown_id_returns_none_not_a_default_frame() -> None:
    resolver = InMemoryContextResolver()
    assert resolver.resolve(_UNKNOWN) is None
    assert resolver.resolve("") is None
    assert len(resolver) == 0
    resolver.register(_frame())
    assert resolver.resolve(_UNKNOWN) is None
    assert len(resolver) == 1
    assert resolver.ancestors(_UNKNOWN) == ()


def test_t033_registering_a_different_frame_under_one_id_raises() -> None:
    resolver = InMemoryContextResolver()
    frame = _frame()
    resolver.register(frame)
    forged = _self_loop(_frame())
    assert forged.context_id == frame.context_id
    with pytest.raises(ContextContractError) as caught:
        resolver.register(forged)
    assert caught.value.code == "context_id_conflict"
    assert isinstance(caught.value, ValueError)
    assert "context_id_conflict" in str(caught.value)
    assert len(resolver) == 1
    assert resolver.resolve(frame.context_id) == frame
    assert resolver.resolve(frame.context_id) is frame


def test_t033_ancestors_walks_upward_and_stops_at_the_first_unregistered_id() -> None:
    resolver = InMemoryContextResolver()
    root = _frame(entity_anchor="ENT-ROOT", parent_context_id="")
    child = _frame(entity_anchor="ENT-CHILD", parent_context_id=root.context_id)
    grandchild = _frame(entity_anchor="ENT-GRAND", parent_context_id=child.context_id)
    orphan = _frame(entity_anchor="ENT-ORPHAN", parent_context_id=_UNREGISTERED)
    for frame in (grandchild, child, root, orphan):
        resolver.register(frame)
    assert resolver.ancestors(grandchild.context_id) == (child, root)
    assert resolver.ancestors(child.context_id) == (root,)
    assert resolver.ancestors(root.context_id) == ()
    assert resolver.ancestors(orphan.context_id) == ()
    assert resolver.ancestors(_UNKNOWN) == ()


def test_t033_ancestors_of_a_cyclic_chain_terminates() -> None:
    resolver = InMemoryContextResolver()
    frame = _self_loop(_frame())
    resolver.register(frame)
    assert resolver.ancestors(frame.context_id) == ()


def test_t033_a_seeded_resolver_deduplicates_its_input() -> None:
    frame = _frame()
    resolver = InMemoryContextResolver((frame, _frame()))
    assert len(resolver) == 1
    assert resolver.resolve(frame.context_id) is frame


# --------------------------------------------------------------------------
# T034: parent-cycle detection
# --------------------------------------------------------------------------


def test_t034_a_self_loop_reports_a_two_element_path() -> None:
    frame = _self_loop(_frame())
    path = detect_context_cycle((frame,))
    assert path == (frame.context_id, frame.context_id)
    assert path[0] == path[-1]


def test_t034_a_two_cycle_reports_a_three_element_path() -> None:
    first = _frame(entity_anchor="ENT-A")
    second = _frame(entity_anchor="ENT-B", parent_context_id=first.context_id)
    object.__setattr__(first, "parent_context_id", second.context_id)
    path = detect_context_cycle((first, second))
    assert len(path) == 3
    assert path[0] == path[-1]
    assert path[1] != path[0]
    assert set(path) == {first.context_id, second.context_id}


def test_t034_a_three_cycle_reports_the_whole_loop() -> None:
    first = _frame(entity_anchor="ENT-A")
    second = _frame(entity_anchor="ENT-B", parent_context_id=first.context_id)
    third = _frame(entity_anchor="ENT-C", parent_context_id=second.context_id)
    object.__setattr__(first, "parent_context_id", third.context_id)
    path = detect_context_cycle((third, first, second))
    parents = {
        first.context_id: third.context_id,
        second.context_id: first.context_id,
        third.context_id: second.context_id,
    }
    assert len(path) == 4
    assert path[0] == path[-1]
    assert set(path) == set(parents)
    for current, following in zip(path, path[1:], strict=True):
        assert parents[current] == following


def test_t034_an_acyclic_chain_and_a_root_report_no_cycle() -> None:
    root = _frame(entity_anchor="ENT-ROOT", parent_context_id="")
    child = _frame(entity_anchor="ENT-CHILD", parent_context_id=root.context_id)
    grandchild = _frame(entity_anchor="ENT-GRAND", parent_context_id=child.context_id)
    assert detect_context_cycle((grandchild, child, root)) == ()
    assert detect_context_cycle((root,)) == ()
    assert detect_context_cycle(()) == ()


def test_t034_a_diamond_of_one_shared_ancestor_is_not_a_cycle() -> None:
    root = _frame(entity_anchor="ENT-ROOT", parent_context_id="")
    left = _frame(entity_anchor="ENT-LEFT", parent_context_id=root.context_id)
    right = _frame(entity_anchor="ENT-RIGHT", parent_context_id=root.context_id)
    assert detect_context_cycle((right, left, root)) == ()
    assert detect_context_cycle((root, left, right)) == ()


def test_t034_a_parent_outside_the_frame_set_is_unresolved_not_a_cycle() -> None:
    dangling = _frame(entity_anchor="ENT-DANGLING", parent_context_id=_UNREGISTERED)
    child = _frame(entity_anchor="ENT-CHILD", parent_context_id=dangling.context_id)
    assert detect_context_cycle((dangling,)) == ()
    assert detect_context_cycle((child, dangling)) == ()
    assert detect_context_cycle((child,)) == ()


def test_t034_detection_is_independent_of_the_order_frames_are_supplied() -> None:
    first = _frame(entity_anchor="ENT-A")
    second = _frame(entity_anchor="ENT-B", parent_context_id=first.context_id)
    third = _frame(entity_anchor="ENT-C", parent_context_id=second.context_id)
    object.__setattr__(first, "parent_context_id", third.context_id)
    assert detect_context_cycle((first, second, third)) == detect_context_cycle(
        (third, second, first)
    )
    assert detect_context_cycle((first, second)) == detect_context_cycle((second, first))


# --------------------------------------------------------------------------
# T035: an inverted validity window is rejected at construction
# --------------------------------------------------------------------------


def test_t035_an_inverted_interval_is_rejected_with_a_stable_code() -> None:
    with pytest.raises(ContextContractError) as caught:
        _frame(valid_from=_TO, valid_to=_FROM)
    assert caught.value.code == "validity_interval_inverted"
    assert "validity_interval_inverted" in str(caught.value)
    assert isinstance(caught.value, ValueError)
    with pytest.raises(ContextContractError, match=r"\[validity_interval_inverted\]"):
        EvidenceContext(valid_from=_TO, valid_to=_FROM)
    with pytest.raises(ContextContractError, match=r"\[validity_interval_inverted\]"):
        EvidenceContext.from_dict({"valid_from": _TO.isoformat(), "valid_to": _FROM.isoformat()})


def test_t035_a_zero_width_and_a_half_open_interval_are_accepted() -> None:
    zero_width = _frame(valid_from=_FROM, valid_to=_FROM)
    assert zero_width.valid_from == zero_width.valid_to == _FROM
    assert replace(zero_width, valid_to=_FROM + timedelta(days=1)).valid_to > _FROM
    assert _frame(valid_from=None, valid_to=_TO).valid_to == _TO
    assert _frame(valid_from=_FROM, valid_to=None).valid_to is None
    assert _frame().valid_to == _TO
    assert _frame(valid_from=_TO, valid_to=_TO).valid_from == _TO


# --------------------------------------------------------------------------
# Derived behaviour: the record, the forged id, the defaults
# --------------------------------------------------------------------------


def test_to_dict_from_dict_round_trips_every_field() -> None:
    frame = _frame(completeness=ContextCompleteness.FRAGMENT, trust_state="disputed")
    payload = frame.to_dict()
    assert set(payload) == set(_FIELD_ORDER) | {"frame_fingerprint"}
    restored = EvidenceContext.from_dict(payload)
    assert restored == frame
    assert restored.to_dict() == payload
    for name in _FIELD_ORDER:
        assert getattr(restored, name) == getattr(frame, name), name
    assert payload["completeness"] == "fragment"
    assert payload["trust_state"] == "disputed"
    assert payload["observed_at"] == "2022-07-01T09:00:00+00:00"
    assert payload["valid_from"] == "2017-01-01T00:00:00+00:00"
    assert payload["published_at"] == "2022-07-02T12:00:00+00:00"
    assert payload["subject_candidate_ids"] == ["ENT-P1", "ENT-P2"]
    assert restored.completeness is ContextCompleteness.FRAGMENT
    assert restored.trust_state is ContextTrustState.DISPUTED
    assert restored.context_id == frame.context_id


def test_from_dict_of_a_minimal_payload_takes_the_documented_defaults() -> None:
    minimal = EvidenceContext.from_dict({"tenant_id": "tenant-b", "entity_anchor": "ENT-Z"})
    default = EvidenceContext(tenant_id="tenant-b", entity_anchor="ENT-Z")
    assert minimal == default
    assert minimal.context_id == default.context_id
    assert minimal.observed_at is None
    assert minimal.valid_to is None
    assert minimal.parent_context_id == ""


def test_a_supplied_context_id_must_match_the_derivation() -> None:
    frame = _frame()
    accepted = EvidenceContext(**{**_canonical_dict(), "context_id": frame.context_id})
    assert accepted == frame
    with pytest.raises(ContextContractError) as caught:
        EvidenceContext(**{**_canonical_dict(), "context_id": _UNKNOWN})
    assert caught.value.code == "context_id_mismatch"
    assert isinstance(caught.value, ValueError)
    assert frame.context_id in str(caught.value)
    with pytest.raises(ContextContractError) as tampered:
        EvidenceContext(**{**_canonical_dict(), "context_id": "CX-" + "f" * 32})
    assert tampered.value.code == "context_id_mismatch"
    with pytest.raises(ContextContractError) as from_record:
        EvidenceContext.from_dict({**frame.to_dict(), "context_id": _UNKNOWN})
    assert from_record.value.code == "context_id_mismatch"


def test_the_defaults_are_the_documented_ones() -> None:
    empty = EvidenceContext()
    assert empty.context_id.startswith("CX-")
    assert len(empty.context_id) == 35
    assert empty.tenant_id == "default-tenant"
    assert empty.investigation_id == "" and empty.entity_anchor == ""
    assert empty.observation_id == "" and empty.source_id == ""
    assert empty.document_id == "" and empty.segment_id == ""
    assert empty.subject_candidate_ids == () and empty.object_candidate_ids == ()
    assert empty.observed_at is None and empty.published_at is None
    assert empty.valid_from is None and empty.valid_to is None
    assert empty.source_family == "" and empty.independence_group == ""
    assert empty.language == "" and empty.location_context == ""
    assert empty.extraction_version == "" and empty.normalization_version == ""
    assert empty.ontology_version == ""
    assert empty.completeness is ContextCompleteness.COMPLETE
    assert empty.trust_state is ContextTrustState.UNVERIFIED
    assert empty.policy_snapshot_ref == "" and empty.parent_context_id == ""


def test_the_vocabularies_are_the_documented_ones() -> None:
    assert tuple(member.value for member in ContextCompleteness) == (
        "complete",
        "partial",
        "fragment",
    )
    assert tuple(member.value for member in ContextTrustState) == (
        "verified",
        "attested",
        "unverified",
        "disputed",
    )
    assert ContextCompleteness.PARTIAL == "partial"
    assert ContextTrustState.DISPUTED == "disputed"
    text = _frame(completeness="partial", trust_state="attested")
    assert text.completeness is ContextCompleteness.PARTIAL
    assert text.trust_state is ContextTrustState.ATTESTED
