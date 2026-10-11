"""What the Context Graph is required to refuse, and what it must never confuse.

The interesting properties here are all negatives. The graph's job is to hold the record of
work that did not go well -- a question nobody answered, a claim that was retracted, an
investigation that was opened and abandoned -- and every one of those is a state a
rebuild-from-facts projection cannot represent, because the projection's inputs are exactly
the things that did not survive. So the tests below spend most of their effort on what the
graph must *not* collapse.

The other half is transactional: an edge may reference a node written in the same
transaction, and a refused write must leave nothing behind. Half an investigation -- a
question without the scope that bounds it -- is the kind of gap that becomes a wrong answer
three steps later.
"""

from __future__ import annotations

import asyncio

from datetime import UTC, datetime
from typing import Any

import pytest

from context_engine.context_graph import (
    ContextEdge,
    ContextEdgeType,
    ContextGraph,
    ContextGraphError,
    ContextNode,
    ContextNodeType,
    InMemoryContextGraphStore,
    Transaction,
    node_id,
)

pytestmark = pytest.mark.contract


class SyncGraph:
    """Synchronous face over the async graph.

    The graph is async because the durable store is; the in-memory store answers inline. The
    tests stay synchronous and read as one sequence of assertions each, which is what makes the
    *ordering* of a write visible -- and the ordering is half of what is being tested here.
    Pulling an async plugin in to save eight ``await`` keywords would have cost more than it
    saved.
    """

    def __init__(self, graph: ContextGraph) -> None:
        self._graph = graph

    def apply(self, *args: Any, **kwargs: Any) -> Any:
        return asyncio.run(self._graph.apply(*args, **kwargs))

    def ask(self, *args: Any, **kwargs: Any) -> Any:
        return asyncio.run(self._graph.ask(*args, **kwargs))

    def record_unknown(self, *args: Any, **kwargs: Any) -> Any:
        return asyncio.run(self._graph.record_unknown(*args, **kwargs))

    def snapshot(self, *args: Any, **kwargs: Any) -> Any:
        return asyncio.run(self._graph.snapshot(*args, **kwargs))

    def state_of(self, *args: Any, **kwargs: Any) -> Any:
        return asyncio.run(self._graph.state_of(*args, **kwargs))

    def open_unknowns(self, *args: Any, **kwargs: Any) -> Any:
        return asyncio.run(self._graph.open_unknowns(*args, **kwargs))

    def audit_trail(self, *args: Any, **kwargs: Any) -> Any:
        return asyncio.run(self._graph.audit_trail(*args, **kwargs))

TENANT = "t-ctx"
INV = "inv-1"


@pytest.fixture
def graph() -> SyncGraph:
    return SyncGraph(ContextGraph(InMemoryContextGraphStore()))


def question(text: str, investigation: str = INV) -> ContextNode:
    return ContextNode(
        node_id=node_id(ContextNodeType.QUESTION, investigation, text),
        type=ContextNodeType.QUESTION,
        investigation_id=investigation,
        label=text,
        key=text,
    )


def claim(text: str, investigation: str = INV) -> ContextNode:
    return ContextNode(
        node_id=node_id(ContextNodeType.CLAIM, investigation, text),
        type=ContextNodeType.CLAIM,
        investigation_id=investigation,
        label=text,
        key=text,
    )


# ── the ten of each, by construction ────────────────────────────────────────────────


def test_the_graph_carries_exactly_the_specified_node_types() -> None:
    assert {str(t) for t in ContextNodeType} == {
        "Investigation",
        "Question",
        "Scope",
        "Hypothesis",
        "Task",
        "EvidenceSet",
        "Claim",
        "Contradiction",
        "Unknown",
        "Revision",
    }


def test_the_graph_carries_exactly_the_specified_edge_types() -> None:
    assert {str(t) for t in ContextEdgeType} == {
        "asks",
        "scopes",
        "supports",
        "contradicts",
        "refines",
        "delegates",
        "observes",
        "revises",
        "derived_from",
        "supersedes",
    }


# ── §3.8: unknown is not empty ──────────────────────────────────────────────────────


def test_an_unwritten_investigation_is_empty(graph: ContextGraph) -> None:
    assert graph.state_of(TENANT, INV) == "empty"


def test_a_graph_whose_everything_is_unknown_is_unknown(graph: ContextGraph) -> None:
    graph.record_unknown(TENANT, INV, "who owns this domain")

    assert graph.state_of(TENANT, INV) == "unknown"
    assert len(graph.open_unknowns(TENANT, INV)) == 1


def test_empty_and_unknown_are_different_claims(graph: ContextGraph) -> None:
    before = graph.state_of(TENANT, INV)
    graph.record_unknown(TENANT, INV, "who owns this domain")
    after = graph.state_of(TENANT, INV)

    assert before != after, "'we never looked' and 'we looked and learned nothing' are different"


def test_an_unknown_inside_a_populated_graph_does_not_erase_what_is_known(graph: ContextGraph) -> None:
    graph.ask(TENANT, INV, "What is this company?")
    graph.record_unknown(TENANT, INV, "beneficial owner")

    assert graph.state_of(TENANT, INV) == "known", (
        "a graph holding a question is not 'unknown' just because one answer is missing"
    )
    assert len(graph.open_unknowns(TENANT, INV)) == 1, (
        "what is still open is reported, not smeared across the graph's state"
    )


# ── transactional write ─────────────────────────────────────────────────────────────


def test_an_edge_may_reference_a_node_written_in_the_same_transaction(graph: ContextGraph) -> None:
    scope = ContextNode(
        node_id=node_id(ContextNodeType.SCOPE, INV, "acquisition"),
        type=ContextNodeType.SCOPE,
        investigation_id=INV,
        label="acquisition",
    )
    q = question("Who registered it?")

    graph.apply(
        TENANT,
        Transaction(
            nodes=(scope, q),
            edges=(
                ContextEdge(
                    edge_id="CE-1",
                    type=ContextEdgeType.SCOPES,
                    source=q.node_id,
                    target=scope.node_id,
                ),
            ),
            rationale="bound the question",
        ),
    )

    snap = graph.snapshot(TENANT, INV)
    assert len(snap.edges) == 1
    assert snap.edges[0].type is ContextEdgeType.SCOPES


def test_a_dangling_edge_is_refused_and_writes_nothing(graph: ContextGraph) -> None:
    q = question("Who registered it?")

    with pytest.raises(ContextGraphError, match="unknown node"):
        graph.apply(
            TENANT,
            Transaction(
                nodes=(q,),
                edges=(
                    ContextEdge(
                        edge_id="CE-x",
                        type=ContextEdgeType.SUPPORTS,
                        source=q.node_id,
                        target="CN-does-not-exist",
                    ),
                ),
            ),
        )

    assert graph.snapshot(TENANT, INV).edges == ()


def test_an_edge_type_may_not_connect_node_types_it_does_not_describe(graph: ContextGraph) -> None:
    # Both endpoints are written in the same transaction, so the refusal is about the *type*
    # shape and not about a missing node -- otherwise this test would pass for the wrong
    # reason, having proved only that dangling edges are caught (which the test above does).
    q = question("Who registered it?")
    target = question("Who is the beneficial owner?")

    with pytest.raises(ContextGraphError, match="may not start at a Question"):
        graph.apply(
            TENANT,
            Transaction(
                nodes=(q, target),
                edges=(
                    ContextEdge(
                        edge_id="CE-y",
                        type=ContextEdgeType.SUPPORTS,
                        source=q.node_id,
                        target=target.node_id,
                    ),
                ),
            ),
        )


def test_a_node_cannot_be_attached_to_another_investigation(graph: ContextGraph) -> None:
    stranger = question("A question from elsewhere", investigation="inv-2")
    graph.ask(TENANT, INV, "A local question")

    with pytest.raises(ContextGraphError, match="belongs to investigation"):
        graph.apply(TENANT, Transaction(nodes=(stranger,)), investigation_id=INV)


def test_an_empty_transaction_is_refused(graph: ContextGraph) -> None:
    with pytest.raises(ContextGraphError, match="records nothing"):
        graph.apply(TENANT, Transaction())


# ── identity and replay ─────────────────────────────────────────────────────────────


def test_the_same_question_in_two_investigations_is_two_questions() -> None:
    assert node_id(ContextNodeType.QUESTION, "inv-1", "who?") != node_id(
        ContextNodeType.QUESTION, "inv-2", "who?"
    )


def test_question_identity_ignores_case_and_surrounding_space() -> None:
    assert node_id(ContextNodeType.QUESTION, INV, "Who?") == node_id(
        ContextNodeType.QUESTION, INV, "  who? "
    )


def test_replaying_a_decision_does_not_double_the_graph(graph: ContextGraph) -> None:
    q = question("Who registered it?")
    decision = Transaction(nodes=(q,), actor="analyst", rationale="asked")
    first = graph.apply(TENANT, decision)
    second = graph.apply(TENANT, decision)

    assert len(graph.snapshot(TENANT, INV).nodes) == 1, (
        "a replayed decision log must converge, not accumulate"
    )
    assert first.added_nodes == second.added_nodes


# ── audit trail (FR-003) ────────────────────────────────────────────────────────────


def test_every_write_leaves_a_decision_record(graph: ContextGraph) -> None:
    graph.ask(TENANT, INV, "What is this?", rationale="opened the investigation")

    trail = graph.audit_trail(TENANT)
    assert len(trail) == 1
    assert trail[0].actor == "analyst"
    assert trail[0].rationale == "opened the investigation"
    assert trail[0].added_nodes, "a decision must name what it changed"


def test_a_question_is_written_with_its_scope_in_one_transaction(graph: ContextGraph) -> None:
    scope = ContextNode(
        node_id=node_id(ContextNodeType.SCOPE, INV, "registry"),
        type=ContextNodeType.SCOPE,
        investigation_id=INV,
        label="registry",
    )
    graph.apply(TENANT, Transaction(nodes=(scope,)))
    graph.ask(TENANT, INV, "Who is the registrant?", scope_ids=(scope.node_id,))

    snap = graph.snapshot(TENANT, INV)
    assert [e.type for e in snap.edges] == [ContextEdgeType.SCOPES], (
        "a question visible without its scope is a question nobody can answer correctly"
    )


# ── supersession ────────────────────────────────────────────────────────────────────


def test_a_revision_supersedes_rather_than_overwrites(graph: ContextGraph) -> None:
    old = claim("registered in 1995")
    revision = ContextNode(
        node_id=node_id(ContextNodeType.REVISION, INV, "registered-in-1995-v2"),
        type=ContextNodeType.REVISION,
        investigation_id=INV,
        label="registered in 1995 (corrected)",
    )
    graph.apply(TENANT, Transaction(nodes=(old,)))

    graph.apply(
        TENANT,
        Transaction(
            nodes=(revision,),
            edges=(
                ContextEdge(
                    edge_id="CE-s",
                    type=ContextEdgeType.SUPERSEDES,
                    source=revision.node_id,
                    target=old.node_id,
                ),
            ),
            rationale="the date was wrong",
        ),
    )

    snap = graph.snapshot(TENANT, INV)
    assert len(snap.nodes) == 2, "supersession keeps the claim it replaced"
    assert snap.edges[0].type is ContextEdgeType.SUPERSEDES
    assert snap.node(old.node_id) is not None


def test_an_unknown_can_be_answered_later_without_deleting_the_question(graph: ContextGraph) -> None:
    graph.record_unknown(TENANT, INV, "beneficial owner")
    assert len(graph.open_unknowns(TENANT, INV)) == 1

    graph.ask(TENANT, INV, "Who is the beneficial owner?")

    assert graph.snapshot(TENANT, INV).node(
        node_id(ContextNodeType.UNKNOWN, INV, "beneficial owner")
    ) is not None, (
        "an answered unknown is answered, not erased: the record of having asked is the point"
    )


def test_snapshot_is_scoped_to_one_investigation(graph: ContextGraph) -> None:
    graph.ask(TENANT, INV, "A local question")
    graph.ask(TENANT, "inv-2", "A different question")

    local = graph.snapshot(TENANT, INV)
    other = graph.snapshot(TENANT, "inv-2")

    assert len(local.nodes) == 1
    assert len(other.nodes) == 1
    assert local.nodes[0].node_id != other.nodes[0].node_id


def test_a_node_serialises_and_returns_unchanged(graph: ContextGraph) -> None:
    q = question("Who registered it?", investigation="inv-serial")
    original = ContextNode(
        node_id=q.node_id,
        type=q.type,
        investigation_id=q.investigation_id,
        label=q.label,
        key=q.key,
        props={"source_count": 3},
        created_at=datetime(2026, 3, 1, tzinfo=UTC),
    )

    assert ContextNode.from_dict(original.to_dict()) == original


def test_a_reused_store_sees_the_earlier_graph(graph: SyncGraph) -> None:
    graph.ask(TENANT, INV, "A local question")

    store = graph._graph._store
    reopened = SyncGraph(ContextGraph(store))

    assert reopened.state_of(TENANT, INV) == "known", (
        "the graph outlives the object that wrote to it; that is the durability requirement"
    )