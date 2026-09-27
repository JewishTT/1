"""Evidence lineage: bidirectional traversal and explicit incompleteness.

Tasks T058-T062 (US6) of ``specs/016-relation-evidence-graph-fabric`` with T064
as their implementation. FR-032 a forward traversal returns every derived
relation with the assertion that grounds it, FR-033 a traversal that cannot
complete names its first unresolved hop and never truncates silently, FR-034 two
captures of one source family are one independent source and are never fused with
the publication count (constitution IV).
"""

from __future__ import annotations

import pytest

from domain.evidence_lineage import (
    BACKWARD_CHAIN,
    EvidenceGraph,
    EvidenceHop,
    HopKind,
    LineageTrace,
    independence_groups,
)
from domain.relation_claim import RelationClaim
from domain.relation_identity import RelationArityMode

pytestmark = pytest.mark.unit

_API_PATH = (
    "relation",
    "assertion",
    "mention",
    "segment",
    "observation",
    "capture",
    "source",
)

_SPINE = (
    HopKind.RELATION,
    HopKind.ASSERTION,
    HopKind.MENTION,
    HopKind.SEGMENT,
    HopKind.OBSERVATION,
    HopKind.CAPTURE,
    HopKind.SOURCE,
)

_CHAIN = (
    (HopKind.RELATION, "rel-1", "as-1", "", "rel-1"),
    (HopKind.ASSERTION, "as-1", "mn-1", "rel-1", ""),
    (HopKind.MENTION, "mn-1", "sg-1", "as-1", ""),
    (HopKind.SEGMENT, "sg-1", "ob-1", "mn-1", ""),
    (HopKind.OBSERVATION, "ob-1", "cp-1", "sg-1", ""),
    (HopKind.CAPTURE, "cp-1", "sr-1", "ob-1", ""),
    (HopKind.SOURCE, "sr-1", "", "cp-1", ""),
)

_BRANCHING = _CHAIN + (
    (HopKind.RELATION, "rel-2", "as-2", "", "rel-2"),
    (HopKind.ASSERTION, "as-2", "mn-2", "rel-2", ""),
    (HopKind.MENTION, "mn-2", "sg-2", "as-2", ""),
    (HopKind.SEGMENT, "sg-2", "ob-2", "mn-2", ""),
    (HopKind.OBSERVATION, "ob-2", "cp-2", "sg-2", ""),
    (HopKind.CAPTURE, "cp-2", "sr-1", "ob-2", ""),
    (HopKind.SOURCE, "sr-1", "", "cp-2", ""),
)

_FAMILIES = {"ob-1": "wire-uk", "ob-2": "wire-uk", "ob-3": "wire-us"}


def _graph(rows: tuple[tuple[HopKind, str, str, str, str], ...] = _CHAIN) -> EvidenceGraph:
    graph = EvidenceGraph()
    for kind, node_id, derived_from, derives, relation_id in rows:
        graph.add_hop(
            EvidenceHop(kind=kind, node_id=node_id, relation_id=relation_id),
            forward=derived_from,
            backward=derives,
        )
    return graph


def _claim(observation_refs: tuple[str, ...], groups: tuple[tuple[str, ...], ...]) -> RelationClaim:
    return RelationClaim(
        relation_id="RC-" + "1" * 32,
        logical_relation_id="RL-" + "2" * 32,
        revision_number=1,
        relation_type="employment",
        arity_mode=RelationArityMode.DIRECTED,
        subject_ref="ENT-P1",
        object_ref="ENT-O1",
        assertion_refs=("as-1",),
        observation_refs=observation_refs,
        context_ref="CX-1",
        source_independence_groups=groups,
    )


# --------------------------------------------------------------------------
# T058: a complete chain resolves to the source, hop by hop
# --------------------------------------------------------------------------


def test_t058_backward_lineage_returns_every_hop_in_canonical_order() -> None:
    trace = _graph().backward("rel-1")

    assert isinstance(trace, LineageTrace)
    assert trace.subject_id == "rel-1"
    assert trace.direction == "backward"
    assert trace.complete is True
    assert trace.first_unresolved_hop is None
    assert trace.unresolved_node_id == ""
    assert tuple(hop.kind for hop in trace.hops) == (
        HopKind.ASSERTION,
        HopKind.MENTION,
        HopKind.SEGMENT,
        HopKind.OBSERVATION,
        HopKind.CAPTURE,
        HopKind.SOURCE,
    )
    assert tuple(str(hop.kind) for hop in trace.hops) == _API_PATH[1:]
    assert tuple(hop.kind for hop in trace.hops) == BACKWARD_CHAIN[1:]
    assert tuple(hop.node_id for hop in trace.hops) == (
        "as-1",
        "mn-1",
        "sg-1",
        "ob-1",
        "cp-1",
        "sr-1",
    )
    assert trace.hops[-1].node_id == "sr-1"


# --------------------------------------------------------------------------
# T059: a broken chain names the gap and keeps what it resolved
# --------------------------------------------------------------------------


def test_t059_a_missing_segment_names_the_gap_and_keeps_the_hops_found() -> None:
    broken = tuple(row for row in _CHAIN if row[0] is not HopKind.SEGMENT)
    trace = _graph(broken).backward("rel-1")

    assert trace.complete is False
    assert trace.first_unresolved_hop is HopKind.SEGMENT
    assert trace.first_unresolved_hop == "segment"
    assert trace.unresolved_node_id == "mn-1"
    assert trace.hops != ()
    assert trace.hops
    assert tuple(hop.kind for hop in trace.hops) == (HopKind.ASSERTION, HopKind.MENTION)
    assert tuple(hop.node_id for hop in trace.hops) == ("as-1", "mn-1")


@pytest.mark.parametrize(
    ("missing", "resolved", "expected_node"),
    [
        (HopKind.ASSERTION, (), "rel-1"),
        (HopKind.MENTION, (HopKind.ASSERTION,), "as-1"),
        (HopKind.SEGMENT, (HopKind.ASSERTION, HopKind.MENTION), "mn-1"),
        (HopKind.OBSERVATION, (HopKind.ASSERTION, HopKind.MENTION, HopKind.SEGMENT), "sg-1"),
        (
            HopKind.CAPTURE,
            (HopKind.ASSERTION, HopKind.MENTION, HopKind.SEGMENT, HopKind.OBSERVATION),
            "ob-1",
        ),
        (
            HopKind.SOURCE,
            (
                HopKind.ASSERTION,
                HopKind.MENTION,
                HopKind.SEGMENT,
                HopKind.OBSERVATION,
                HopKind.CAPTURE,
            ),
            "cp-1",
        ),
    ],
)
def test_t059_every_break_names_its_own_hop_and_keeps_what_it_resolved(
    missing: HopKind,
    resolved: tuple[HopKind, ...],
    expected_node: str,
) -> None:
    rows = tuple(row for row in _CHAIN if row[0] is not missing)
    trace = _graph(rows).backward("rel-1")

    assert trace.complete is False
    assert trace.first_unresolved_hop == str(missing)
    assert trace.unresolved_node_id == expected_node
    assert tuple(hop.kind for hop in trace.hops) == resolved
    if resolved:
        assert trace.hops != ()


# --------------------------------------------------------------------------
# T060: forward lineage returns every derived relation, with its assertion
# --------------------------------------------------------------------------


def test_t060_forward_lineage_returns_every_derived_relation_with_its_assertion() -> None:
    trace = _graph().forward("sr-1")

    assert trace.subject_id == "sr-1"
    assert trace.direction == "forward"
    assert trace.complete is True
    assert trace.first_unresolved_hop is None
    assert tuple(hop.kind for hop in trace.hops) == (
        HopKind.CAPTURE,
        HopKind.OBSERVATION,
        HopKind.SEGMENT,
        HopKind.MENTION,
        HopKind.ASSERTION,
        HopKind.RELATION,
    )
    assert {hop.node_id for hop in trace.hops if hop.kind is HopKind.RELATION} == {"rel-1"}
    assert all(hop.relation_id == "rel-1" for hop in trace.hops)
    assert [hop.node_id for hop in trace.hops if hop.kind is HopKind.ASSERTION] == ["as-1"]


def test_t060_one_source_captured_twice_returns_both_derived_relations() -> None:
    graph = _graph(_BRANCHING)
    trace = graph.forward("sr-1")

    assert trace.complete is True
    assert [hop.node_id for hop in trace.hops if hop.kind is HopKind.CAPTURE] == ["cp-1", "cp-2"]
    assert [hop.node_id for hop in trace.hops if hop.kind is HopKind.RELATION] == [
        "rel-1",
        "rel-2",
    ]
    assert [hop.relation_id for hop in trace.hops if hop.kind is HopKind.ASSERTION] == [
        "rel-1",
        "rel-2",
    ]
    assert all(
        hop.relation_id == "rel-1"
        for hop in trace.hops
        if hop.node_id in ("cp-1", "ob-1", "sg-1", "mn-1", "as-1")
    )
    assert all(
        hop.relation_id == "rel-2"
        for hop in trace.hops
        if hop.node_id in ("cp-2", "ob-2", "sg-2", "mn-2", "as-2")
    )
    assert tuple(hop.kind for hop in graph.backward("rel-2").hops) == BACKWARD_CHAIN[1:]


def test_t060_a_forward_trace_with_no_relation_yet_is_not_complete() -> None:
    rows = tuple(row for row in _CHAIN if row[0] is not HopKind.RELATION)
    trace = _graph(rows).forward("sr-1")

    assert trace.complete is False
    assert trace.first_unresolved_hop == "relation"
    assert trace.unresolved_node_id == "as-1"
    assert tuple(hop.kind for hop in trace.hops)[-1] is HopKind.ASSERTION


# --------------------------------------------------------------------------
# T061: independence is by source family, and the two counts stay apart
# --------------------------------------------------------------------------


def test_t061_two_captures_of_one_source_family_collapse_into_one_group() -> None:
    groups = independence_groups(("ob-1", "ob-2", "ob-3"), _FAMILIES)

    assert groups == (("ob-1", "ob-2"), ("ob-3",))
    assert len(groups) == 2
    assert groups[0] == ("ob-1", "ob-2")
    assert len(groups[0]) == 2
    assert EvidenceGraph().independence_groups(("ob-1", "ob-2", "ob-3"), _FAMILIES) == groups


def test_t061_two_captures_of_different_families_are_two_groups() -> None:
    assert independence_groups(("ob-2", "ob-3"), _FAMILIES) == (("ob-2",), ("ob-3",))
    assert independence_groups((), _FAMILIES) == ()
    assert independence_groups(("ob-1",), {}) == (("ob-1",),)
    assert independence_groups(("ob-9", "ob-1"), {"ob-1": "wire-uk"}) == (
        ("ob-1",),
        ("ob-9",),
    )


def test_t061_independence_count_and_publication_count_remain_separate() -> None:
    groups = independence_groups(("ob-1", "ob-2"), _FAMILIES)
    claim = _claim(("ob-1", "ob-2"), groups)

    assert claim.publication_count == 2
    assert claim.independent_source_count == 1
    assert claim.publication_count != claim.independent_source_count
    assert claim.source_independence_groups == (("ob-1", "ob-2"),)

    syndicated = _claim(
        ("ob-1", "ob-2", "ob-3"),
        independence_groups(("ob-1", "ob-2", "ob-3"), _FAMILIES),
    )
    assert syndicated.publication_count == 3
    assert syndicated.independent_source_count == 2


# --------------------------------------------------------------------------
# T062: the API-level path relation -> source is reachable in both directions
# --------------------------------------------------------------------------


def test_t062_the_api_path_is_reachable_in_both_directions() -> None:
    graph = _graph()
    back = graph.backward("rel-1")
    forward = graph.forward("sr-1")

    assert [str(hop.kind) for hop in back.hops] == list(_API_PATH[1:])
    assert [str(hop.kind) for hop in forward.hops] == list(reversed(_API_PATH[:-1]))
    assert back.complete is True and forward.complete is True
    assert back.hops[0].node_id == "as-1"
    assert back.hops[-1].node_id == "sr-1"
    assert forward.hops[0].node_id == "cp-1"
    assert forward.hops[-1].node_id == "rel-1"
    assert ("rel-1", *(hop.node_id for hop in back.hops)) == (
        "sr-1",
        *(reversed(tuple(hop.node_id for hop in forward.hops))),
    )


def test_t062_the_candidate_hop_is_traversed_when_it_is_registered() -> None:
    rows = (
        (HopKind.RELATION, "rel-1", "as-1", "", "rel-1"),
        (HopKind.ASSERTION, "as-1", "cd-1", "rel-1", ""),
        (HopKind.CANDIDATE, "cd-1", "mn-1", "as-1", ""),
        (HopKind.MENTION, "mn-1", "sg-1", "cd-1", ""),
        (HopKind.SEGMENT, "sg-1", "ob-1", "mn-1", ""),
        (HopKind.OBSERVATION, "ob-1", "cp-1", "sg-1", ""),
        (HopKind.CAPTURE, "cp-1", "sr-1", "ob-1", ""),
        (HopKind.SOURCE, "sr-1", "", "cp-1", ""),
    )
    trace = _graph(rows).forward("sr-1")

    assert trace.complete is True
    assert tuple(hop.kind for hop in trace.hops) == (
        HopKind.CAPTURE,
        HopKind.OBSERVATION,
        HopKind.SEGMENT,
        HopKind.MENTION,
        HopKind.CANDIDATE,
        HopKind.ASSERTION,
        HopKind.RELATION,
    )
    assert trace.hops[4].node_id == "cd-1"


# --------------------------------------------------------------------------
# The record: round-trips, and never claims a completeness it does not have
# --------------------------------------------------------------------------


def test_t063_a_trace_round_trips_through_its_own_record() -> None:
    complete = _graph().backward("rel-1")
    incomplete = _graph(
        tuple(row for row in _CHAIN if row[0] is not HopKind.SEGMENT)
    ).backward("rel-1")

    for trace in (complete, incomplete, _graph().forward("sr-1")):
        assert LineageTrace.from_dict(trace.to_dict()) == trace
        assert trace.to_dict()["direction"] in ("backward", "forward")
        assert trace.to_dict()["hops"][0] == trace.hops[0].to_dict()
        assert trace.to_dict()["hops"][0]["kind"] == str(trace.hops[0].kind)
    assert complete.to_dict()["first_unresolved_hop"] is None
    assert incomplete.to_dict()["first_unresolved_hop"] == "segment"
    assert EvidenceHop.from_dict(complete.hops[0].to_dict()) == complete.hops[0]


def test_t063_a_hop_needs_an_identity_and_takes_its_kind_as_a_string() -> None:
    hop = EvidenceHop(kind="segment", node_id="sg-1")

    assert hop.kind is HopKind.SEGMENT
    assert hop.to_dict() == {
        "kind": "segment",
        "node_id": "sg-1",
        "label": "",
        "relation_id": "",
        "tenant_id": "default-tenant",
    }
    with pytest.raises(ValueError, match="node_id"):
        EvidenceHop(kind=HopKind.SOURCE, node_id="")
    with pytest.raises(ValueError, match="complete trace"):
        LineageTrace(
            subject_id="rel-1",
            direction="backward",
            hops=(),
            complete=True,
            first_unresolved_hop=HopKind.SEGMENT,
        )


def test_t063_a_chain_pointing_at_an_unregistered_node_stops_cleanly() -> None:
    rows = tuple(row for row in _CHAIN if row[0] is not HopKind.SOURCE)
    trace = _graph(rows).backward("rel-1")

    assert trace.complete is False
    assert trace.first_unresolved_hop == "source"
    assert trace.unresolved_node_id == "cp-1"
    assert tuple(hop.node_id for hop in trace.hops) == ("as-1", "mn-1", "sg-1", "ob-1", "cp-1")


def test_t064_traversal_of_an_unregistered_node_reports_a_gap_instead_of_raising() -> None:
    graph = _graph()

    back = graph.backward("rel-unknown")
    assert back.subject_id == "rel-unknown"
    assert back.hops == ()
    assert back.complete is False
    assert back.first_unresolved_hop == "assertion"
    assert back.unresolved_node_id == "rel-unknown"

    forward = graph.forward("sr-unknown")
    assert forward.hops == ()
    assert forward.direction == "forward"
    assert forward.complete is False
    assert forward.first_unresolved_hop == "capture"
    assert forward.unresolved_node_id == "sr-unknown"
    assert LineageTrace.from_dict(forward.to_dict()) == forward


def test_t064_registering_the_same_link_twice_changes_nothing() -> None:
    graph = _graph()
    before = graph.backward("rel-1")
    graph.add_hop(
        EvidenceHop(kind=HopKind.MENTION, node_id="mn-1"),
        forward="sg-1",
        backward="as-1",
    )

    assert graph.backward("rel-1") == before
