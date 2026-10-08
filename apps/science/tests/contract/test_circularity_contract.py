"""Contract: CIRCULARITY -- elementary cycles and their classification (FR-022, FR-021).

FR-022 is the requirement this module exists to satisfy::

    CIRCULARITY MUST classify a cycle as load-bearing or inert.
    A 2-cycle between mutual references is not the same finding as circular ownership.

So the primitive is tested on both halves. Finding a cycle is the easy half and is
pinned only where it can be checked exactly -- an explicit expected inventory on a
graph whose cycles are countable by hand. The classification is where the contract
actually lives, and these tests pin the decision boundary rather than the implementation:

1. a 2-cycle is INERT by default **and is returned with its mark** -- dropping it is a
   different, unauditable act, and the mark is what stops it disappearing between
   detection and classification;
2. a 2-cycle leaves INERT only on the full proof: forced reciprocal reach, real traffic
   through the pair, two different predicates, no longer loop sharing the pair;
3. a loop of three or more nodes is LOAD_BEARING only when the loop is the *only* route
   between its nodes **and** something outside it travels through it;
4. absence of that proof is ``SUSPECT`` -- never INERT, because unproven is not the same
   as harmless;
5. INERT is reserved for positive demonstrations of noise: a uniform predicate
   vocabulary, a complete induced relation with nothing attached, and self reference;
6. determinism is by content -- permuting the input cannot change the output, because a
   finding whose identity depends on traversal cannot be compared against a recompute;
7. an unbounded search is a hang, so the budget raises with partial evidence instead of
   returning a tuple that looks complete;
8. no vocabulary is enumerated: the module mentions no domain, and a predicate no cue
   list has heard of still closes a cycle and still classifies (FR-021, FR-030).
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from context.circularity import (
    CircularityBudget,
    CircularityBudgetExceeded,
    CircularityInputError,
    Cycle,
    CycleMark,
    CycleVerdict,
    PredicateGraph,
    Signal,
    classify,
    cycles_in,
    find_cycles,
)

pytestmark = pytest.mark.contract

MODULE_PATH = Path(__file__).resolve().parents[2] / "context" / "circularity.py"

#: A loop whose only route is itself, with an outside node travelling through it.
LOAD_BEARING_NODES = ("a", "b", "c", "y")
LOAD_BEARING_EDGES = (
    ("a", "b", "step_1"),
    ("b", "c", "step_2"),
    ("c", "a", "step_3"),
    ("a", "y", "step_4"),
    ("y", "a", "step_5"),
)

#: Four overlapping cycles on six edges, countable by hand.
OVERLAP_NODES = ("A", "B", "C", "D")
OVERLAP_EDGES = (
    ("A", "B", "p1"),
    ("B", "A", "p2"),
    ("B", "C", "p3"),
    ("C", "A", "p4"),
    ("C", "D", "p5"),
    ("D", "B", "p6"),
)


def _cycle(nodes: tuple[str, ...], length: int) -> Cycle:
    """The unique cycle whose canonical node tuple is ``nodes``."""
    matches = [item for item in find_cycles(nodes, list(OVERLAP_EDGES)) if item.nodes == nodes]
    assert len(matches) == 1, (nodes, matches)
    assert matches[0].length == length
    return matches[0]


def _classify(nodes: tuple[str, ...], edges: tuple[tuple[str, str, str], ...]):
    graph = PredicateGraph.build(nodes, edges)
    return graph, cycles_in(graph)


def _verdict_of(cycle: Cycle, graph: PredicateGraph, inventory) -> CycleVerdict:
    return classify(cycle, graph, cycles=inventory).verdict


class TestFindCycles:
    def test_two_cycle_is_found_with_length_predicates_and_mark(self) -> None:
        cycles = find_cycles(["a", "b"], [("a", "b", "rel_1"), ("b", "a", "rel_2")])
        assert len(cycles) == 1
        cycle = cycles[0]
        assert cycle.length == 2
        assert cycle.nodes == ("a", "b")
        assert cycle.predicates == ("rel_1", "rel_2")
        assert cycle.marks == (CycleMark.MUTUAL_REFERENCE,)
        assert cycle.is_mutual_reference is True
        assert cycle.edge_pairs() == (("a", "b"), ("b", "a"))

    def test_three_cycle_predicates_align_with_their_edges(self) -> None:
        cycles = find_cycles(
            ["a", "b", "c"],
            [("a", "b", "e_ab"), ("b", "c", "e_bc"), ("c", "a", "e_ca")],
        )
        assert len(cycles) == 1
        cycle = cycles[0]
        assert cycle.nodes == ("a", "b", "c")
        assert cycle.predicates == ("e_ab", "e_bc", "e_ca")
        assert cycle.vocabulary == ("e_ab", "e_bc", "e_ca")
        assert cycle.marks == ()

    def test_exact_inventory_on_a_hand_countable_graph(self) -> None:
        """A->B->A, A->B->C->A and B->C->D->B, and nothing else.

        This is the completeness check a naive back-edge walk cannot pass: it depends on
        the loops *not* chosen by one DFS tree being found as well.
        """
        cycles = find_cycles(list(OVERLAP_NODES), list(OVERLAP_EDGES))
        assert tuple(item.nodes for item in cycles) == (
            ("A", "B"),
            ("A", "B", "C"),
            ("B", "C", "D"),
        )

    def test_two_disjoint_cycles_are_both_reported(self) -> None:
        cycles = find_cycles(
            ["a", "b", "c", "x", "y", "z"],
            [
                ("a", "b", "p"),
                ("b", "c", "p"),
                ("c", "a", "p"),
                ("x", "y", "q"),
                ("y", "z", "q"),
                ("z", "x", "q"),
            ],
        )
        assert tuple(item.nodes for item in cycles) == (("a", "b", "c"), ("x", "y", "z"))

    def test_nested_cycles_are_both_reported(self) -> None:
        """A 2-cycle that is also a chord of a 3-cycle: two findings, one shape each."""
        cycles = find_cycles(
            ["a", "b", "c"],
            [("a", "b", "p1"), ("b", "a", "p2"), ("b", "c", "p3"), ("c", "a", "p4")],
        )
        assert tuple(item.nodes for item in cycles) == (("a", "b"), ("a", "b", "c"))
        chord, longer = cycles
        assert chord.is_mutual_reference is True
        assert longer.is_mutual_reference is False

    def test_self_loop_is_reported_and_marked(self) -> None:
        cycles = find_cycles(["a", "b"], [("a", "a", "p1"), ("a", "b", "p2")])
        assert tuple(item.nodes for item in cycles) == (("a",),)
        assert cycles[0].marks == (CycleMark.SELF_REFERENCE,)
        assert cycles[0].is_self_reference is True
        assert cycles[0].predicates == ("p1",)

    def test_layered_dag_reports_nothing(self) -> None:
        """Ten layers of ten, every node joined to the next: no cycle may be invented."""
        edges = [
            (f"l{layer}_n{index}", f"l{layer + 1}_n{index}", "forward")
            for layer in range(9)
            for index in range(10)
        ]
        nodes = [f"l{layer}_n{index}" for layer in range(10) for index in range(10)]
        assert find_cycles(nodes, edges) == ()

    def test_diamond_convergence_produces_no_false_cycle(self) -> None:
        edges = [
            ("root", "left", "part"),
            ("root", "right", "part"),
            ("left", "join", "part"),
            ("right", "join", "part"),
            ("join", "tail", "part"),
        ]
        assert find_cycles(["root", "left", "right", "join", "tail"], edges) == ()

    def test_parallel_predicates_are_preserved_and_resolved_deterministically(self) -> None:
        cycles = find_cycles(
            ["a", "b"],
            [("a", "b", "zeta"), ("a", "b", "alpha"), ("b", "a", "mid")],
        )
        cycle = cycles[0]
        assert cycle.vocabulary == ("alpha", "mid", "zeta")
        assert cycle.predicates == ("alpha", "mid")

    def test_identical_edges_are_idempotent(self) -> None:
        edges = [("a", "b", "p"), ("a", "b", "p"), ("b", "a", "p")]
        cycles = find_cycles(["a", "b"], edges)
        assert len(cycles) == 1
        assert cycles[0].predicates == ("p", "p")

    def test_edge_endpoint_outside_the_node_list_is_admitted(self) -> None:
        """A missing node in the declaration must not delete a real relation."""
        cycles = find_cycles(["a"], [("a", "ghost", "p"), ("ghost", "a", "q")])
        assert len(cycles) == 1
        assert cycles[0].nodes == ("a", "ghost")
        graph = PredicateGraph.build(["a"], [("a", "ghost", "p"), ("ghost", "a", "q")])
        assert "ghost" in graph.nodes

    def test_unknown_predicate_still_yields_and_closes_a_cycle(self) -> None:
        """FR-030: a predicate no cue list has heard of is still an edge."""
        weird = "zz_vocabulary_nobody_enumerated_42"
        cycles = find_cycles(["a", "b"], [("a", "b", weird), ("b", "a", weird)])
        assert len(cycles) == 1
        assert cycles[0].vocabulary == (weird,)

    def test_output_is_independent_of_input_permutation(self) -> None:
        baseline = find_cycles(list(OVERLAP_NODES), list(OVERLAP_EDGES))
        rotated = list(OVERLAP_EDGES[3:]) + list(OVERLAP_EDGES[:3])
        assert find_cycles(list(reversed(OVERLAP_NODES)), rotated) == baseline
        assert find_cycles(list(reversed(OVERLAP_NODES)), list(reversed(rotated))) == baseline

    def test_repeated_calls_and_cycles_in_agree(self) -> None:
        first = find_cycles(list(OVERLAP_NODES), list(OVERLAP_EDGES))
        second = find_cycles(list(OVERLAP_NODES), list(OVERLAP_EDGES))
        graph = PredicateGraph.build(OVERLAP_NODES, OVERLAP_EDGES)
        assert first == second == cycles_in(graph)

    def test_edge_of_the_wrong_arity_is_refused(self) -> None:
        with pytest.raises(CircularityInputError):
            find_cycles(["a", "b"], [("a", "b")])


class TestSizeBoundary:
    def test_large_sparse_graph_terminates_and_finds_only_planted_cycles(self) -> None:
        """1000-node path plus one closed loop: no blow-up, no invented cycle."""
        nodes = [f"n{index}" for index in range(1000)] + ["c0", "c1", "c2"]
        edges = [(f"n{index}", f"n{index + 1}", "next") for index in range(999)]
        edges += [("c0", "c1", "loop"), ("c1", "c2", "loop"), ("c2", "c0", "loop")]
        cycles = find_cycles(nodes, edges)
        assert tuple(item.nodes for item in cycles) == (("c0", "c1", "c2"),)

    def test_dense_graph_raises_with_partial_evidence_instead_of_hanging(self) -> None:
        """A complete digraph on 9 nodes carries 40320 cycles; the budget must bite."""
        nodes = [f"n{index}" for index in range(9)]
        edges = [(a, b, "p") for a in nodes for b in nodes if a != b]
        with pytest.raises(CircularityBudgetExceeded) as caught:
            find_cycles(nodes, edges, budget=CircularityBudget(max_cycles=40))
        assert len(caught.value.partial) == 40
        assert all(isinstance(item, Cycle) for item in caught.value.partial)
        assert "incomplete" in str(caught.value) or "may exist" in str(caught.value)

    def test_cycle_longer_than_the_length_budget_is_refused_not_dropped(self) -> None:
        nodes = [f"n{index}" for index in range(6)]
        edges = [(f"n{index}", f"n{(index + 1) % 6}", "step") for index in range(6)]
        with pytest.raises(CircularityBudgetExceeded) as caught:
            find_cycles(nodes, edges, budget=CircularityBudget(max_cycle_length=3))
        assert isinstance(caught.value.partial, tuple)

    def test_oversized_node_count_is_refused_before_any_search(self) -> None:
        with pytest.raises(CircularityBudgetExceeded) as caught:
            find_cycles(
                ["a", "b"],
                [("a", "b", "p"), ("b", "a", "p")],
                budget=CircularityBudget(max_nodes=1),
            )
        assert caught.value.partial == ()


def _reference_cycles(nodes: list[str], edges: list[tuple[str, str, str]]) -> set[tuple[str, ...]]:
    """A deliberately dumb oracle: every simple path, kept when it closes on its start.

    Exhaustive by construction and hopeless in practice, which is exactly why the search
    is not written this way -- and exactly why it is the right thing to compare against.
    A hand-written expectation can only prove the cases its author imagined; this proves
    the search invents no cycle and misses none on graphs small enough to enumerate.
    """
    adjacency: dict[str, list[str]] = {node: [] for node in nodes}
    for source, target, _predicate in edges:
        if target not in adjacency[source]:
            adjacency[source].append(target)

    found: set[tuple[str, ...]] = set()

    def walk(start: str, path: list[str]) -> None:
        for nxt in adjacency[path[-1]]:
            if nxt == start:
                loop = tuple(path)
                anchor = min(range(len(loop)), key=lambda index: loop[index])
                found.add(loop[anchor:] + loop[:anchor])
            elif nxt not in path:
                walk(start, [*path, nxt])

    for node in nodes:
        walk(node, [node])
    return found


class TestCompletenessAgainstOracle:
    """The search must agree with enumeration exactly -- both directions."""

    @pytest.mark.parametrize(
        ("nodes", "edges"),
        [
            (
                list("ABC"),
                [
                    ("A", "B", "p"),
                    ("B", "A", "q"),
                    ("B", "C", "r"),
                    ("C", "A", "s"),
                ],
            ),
            (
                list("ABCDE"),
                [
                    ("A", "B", "1"),
                    ("B", "C", "2"),
                    ("C", "A", "3"),
                    ("C", "D", "4"),
                    ("D", "E", "5"),
                    ("E", "B", "6"),
                    ("B", "A", "7"),
                    ("D", "A", "8"),
                ],
            ),
            (
                list("ABC"),
                [
                    ("A", "B", "1"),
                    ("B", "C", "2"),
                    ("C", "A", "3"),
                    ("A", "C", "4"),
                    ("C", "B", "5"),
                    ("B", "A", "6"),
                ],
            ),
            (
                list("ABCDEF"),
                [
                    ("A", "B", "1"),
                    ("B", "C", "2"),
                    ("C", "D", "3"),
                    ("D", "E", "4"),
                    ("E", "F", "5"),
                    ("F", "A", "6"),
                    ("A", "C", "7"),
                    ("C", "E", "8"),
                    ("E", "B", "9"),
                    ("B", "D", "10"),
                ],
            ),
            (
                list("ABCD"),
                [(a, b, "p") for a in "ABCD" for b in "ABCD" if a != b],
            ),
        ],
    )
    def test_search_equals_exhaustive_enumeration(self, nodes, edges) -> None:
        produced = {cycle.nodes for cycle in find_cycles(nodes, edges)}
        expected = _reference_cycles(nodes, edges)
        assert produced == expected, (
            f"invented: {produced - expected}, missed: {expected - produced}"
        )


class TestClassification:
    def test_two_cycle_is_inert_by_default_with_an_explanation(self) -> None:
        graph, inventory = _classify(("a", "b"), (("a", "b", "p"), ("b", "a", "q")))
        verdict = classify(inventory[0], graph, cycles=inventory)
        assert verdict.verdict is CycleVerdict.INERT
        assert Signal.LENGTH_2 in verdict.signals
        assert Signal.MUTUAL_REFERENCE in verdict.signals
        assert "mutual reference by default" in verdict.reason

    def test_two_cycle_is_returned_not_silently_discarded(self) -> None:
        cycles = find_cycles(["a", "b"], [("a", "b", "p"), ("b", "a", "q")])
        assert len(cycles) == 1
        assert cycles[0].marks == (CycleMark.MUTUAL_REFERENCE,)

    def test_two_cycle_inside_a_longer_loop_is_inert_as_a_chord(self) -> None:
        graph, inventory = _classify(
            ("a", "b", "c"),
            (("a", "b", "p1"), ("b", "a", "p2"), ("b", "c", "p3"), ("c", "a", "p4")),
        )
        chord = classify(inventory[0], graph, cycles=inventory)
        assert chord.verdict is CycleVerdict.INERT
        assert Signal.REDUNDANT_CHORD in chord.signals
        assert "chord of a strictly longer loop" in chord.reason

    def test_two_cycle_with_the_full_proof_is_load_bearing(self) -> None:
        graph, inventory = _classify(
            ("a", "b", "y"),
            (("a", "b", "p1"), ("b", "a", "p2"), ("b", "y", "p3"), ("y", "b", "p4")),
        )
        pair = next(item for item in inventory if item.nodes == ("a", "b"))
        verdict = classify(pair, graph, cycles=inventory)
        assert verdict.verdict is CycleVerdict.LOAD_BEARING
        assert Signal.NO_BYPASS in verdict.signals
        assert Signal.CARRIES_TRAFFIC in verdict.signals

    def test_two_cycle_uniform_predicate_stays_inert_even_under_traffic(self) -> None:
        graph, inventory = _classify(
            ("a", "b", "y"),
            (("a", "b", "same"), ("b", "a", "same"), ("b", "y", "p3"), ("y", "b", "p4")),
        )
        pair = next(item for item in inventory if item.nodes == ("a", "b"))
        verdict = classify(pair, graph, cycles=inventory)
        assert verdict.verdict is CycleVerdict.INERT
        assert Signal.UNIFORM_PREDICATE in verdict.signals

    def test_self_reference_is_inert(self) -> None:
        graph, inventory = _classify(("a", "b"), (("a", "a", "p1"), ("a", "b", "p2")))
        verdict = classify(inventory[0], graph, cycles=inventory)
        assert verdict.verdict is CycleVerdict.INERT
        assert Signal.SELF_REFERENCE in verdict.signals
        assert "self reference" in verdict.reason

    def test_forced_loop_with_traffic_is_load_bearing(self) -> None:
        graph, inventory = _classify(LOAD_BEARING_NODES, LOAD_BEARING_EDGES)
        loop = next(item for item in inventory if item.nodes == ("a", "b", "c"))
        verdict = classify(loop, graph, cycles=inventory)
        assert verdict.verdict is CycleVerdict.LOAD_BEARING
        assert Signal.NO_BYPASS in verdict.signals
        assert Signal.CARRIES_TRAFFIC in verdict.signals
        assert Signal.CLIQUE_INDUCTION not in verdict.signals

    def test_forced_loop_without_traffic_is_suspect_not_inert(self) -> None:
        graph, inventory = _classify(
            ("a", "b", "c"), (("a", "b", "p1"), ("b", "c", "p2"), ("c", "a", "p3"))
        )
        verdict = classify(inventory[0], graph, cycles=inventory)
        assert verdict.verdict is CycleVerdict.SUSPECT
        assert Signal.NO_BYPASS in verdict.signals
        assert Signal.PERIPHERAL in verdict.signals
        assert "nothing outside the loop travels through it" in verdict.reason

    def test_loop_with_a_parallel_route_is_suspect_even_under_traffic(self) -> None:
        graph, inventory = _classify(
            ("a", "b", "c", "x", "y"),
            (
                ("a", "b", "p1"),
                ("b", "c", "p2"),
                ("c", "a", "p3"),
                ("a", "x", "p4"),
                ("x", "b", "p5"),
                ("c", "y", "p6"),
                ("y", "a", "p7"),
            ),
        )
        loop = next(item for item in inventory if item.nodes == ("a", "b", "c"))
        verdict = classify(loop, graph, cycles=inventory)
        assert verdict.verdict is CycleVerdict.SUSPECT
        assert Signal.BYPASSABLE in verdict.signals
        assert Signal.CARRIES_TRAFFIC in verdict.signals
        assert "bypassed" in verdict.reason

    def test_uniform_predicate_loop_is_inert_even_under_traffic(self) -> None:
        graph, inventory = _classify(
            ("a", "b", "c", "y"),
            (
                ("a", "b", "same"),
                ("b", "c", "same"),
                ("c", "a", "same"),
                ("a", "y", "p4"),
                ("y", "a", "p5"),
            ),
        )
        loop = next(item for item in inventory if item.nodes == ("a", "b", "c"))
        verdict = classify(loop, graph, cycles=inventory)
        assert verdict.verdict is CycleVerdict.INERT
        assert Signal.UNIFORM_PREDICATE in verdict.signals
        assert Signal.CARRIES_TRAFFIC in verdict.signals
        assert "tautology" in verdict.reason

    def test_complete_induced_loop_without_traffic_is_inert_cooccurrence(self) -> None:
        graph, inventory = _classify(
            ("a", "b", "c"),
            (
                ("a", "b", "p1"),
                ("b", "a", "p2"),
                ("a", "c", "p3"),
                ("c", "a", "p4"),
                ("b", "c", "p5"),
                ("c", "b", "p6"),
            ),
        )
        loop = next(item for item in inventory if item.length == 3)
        verdict = classify(loop, graph, cycles=inventory)
        assert verdict.verdict is CycleVerdict.INERT
        assert Signal.CLIQUE_INDUCTION in verdict.signals
        assert "co-occurrence density" in verdict.reason

    def test_complete_induced_loop_with_traffic_never_becomes_load_bearing(self) -> None:
        graph, inventory = _classify(
            ("a", "b", "c", "y"),
            (
                ("a", "b", "p1"),
                ("b", "a", "p2"),
                ("a", "c", "p3"),
                ("c", "a", "p4"),
                ("b", "c", "p5"),
                ("c", "b", "p6"),
                ("a", "y", "p7"),
                ("y", "a", "p8"),
            ),
        )
        loop = next(item for item in inventory if item.length == 3)
        verdict = classify(loop, graph, cycles=inventory)
        assert verdict.verdict is CycleVerdict.SUSPECT
        assert Signal.CLIQUE_INDUCTION in verdict.signals
        assert Signal.CARRIES_TRAFFIC in verdict.signals

    def test_two_signals_with_different_implications_resolve_by_declared_precedence(self) -> None:
        """A tautological loop sitting on a busy route: both readings apply.

        The verdict must not depend on which signal was evaluated first, so the same
        input is classified repeatedly and the winner must not move.
        """
        edges = (
            ("a", "b", "same"),
            ("b", "c", "same"),
            ("c", "a", "same"),
            ("a", "y", "p4"),
            ("y", "a", "p5"),
        )
        graph, inventory = _classify(("a", "b", "c", "y"), edges)
        loop = next(item for item in inventory if item.length == 3)
        verdicts = {classify(loop, graph, cycles=inventory) for _ in range(5)}
        assert len(verdicts) == 1
        verdict = verdicts.pop()
        assert verdict.verdict is CycleVerdict.INERT
        assert Signal.UNIFORM_PREDICATE in verdict.signals
        assert Signal.CARRIES_TRAFFIC in verdict.signals
        assert verdict.reason.startswith("tautology")

    def test_signals_are_reported_in_declaration_order(self) -> None:
        graph, inventory = _classify(OVERLAP_NODES, OVERLAP_EDGES)
        for cycle in inventory:
            verdict = classify(cycle, graph, cycles=inventory)
            order = list(Signal)
            positions = [order.index(signal) for signal in verdict.signals]
            assert positions == sorted(positions)

    @pytest.mark.parametrize(
        ("nodes", "edges"),
        [
            (("a", "b"), (("a", "b", "p1"), ("b", "a", "p2"))),
            (LOAD_BEARING_NODES, LOAD_BEARING_EDGES),
            (OVERLAP_NODES, OVERLAP_EDGES),
            (
                ("a", "b", "c"),
                (
                    ("a", "b", "same"),
                    ("b", "c", "same"),
                    ("c", "a", "same"),
                    ("a", "y", "q1"),
                    ("y", "a", "q2"),
                ),
            ),
        ],
    )
    def test_every_verdict_carries_a_reason_and_at_least_one_signal(self, nodes, edges) -> None:
        graph = PredicateGraph.build(nodes, edges)
        inventory = cycles_in(graph)
        assert inventory, "fixture must contain a cycle for this test to mean anything"
        for cycle in inventory:
            verdict = classify(cycle, graph, cycles=inventory)
            assert isinstance(verdict.verdict, CycleVerdict)
            assert verdict.reason.strip()
            assert verdict.signals
            assert set(verdict.signals) <= set(Signal)
            assert verdict.cycle == cycle

    def test_classification_does_not_depend_on_the_inventory_argument(self) -> None:
        graph = PredicateGraph.build(OVERLAP_NODES, OVERLAP_EDGES)
        inventory = cycles_in(graph)
        for cycle in inventory:
            assert classify(cycle, graph, cycles=inventory) == classify(cycle, graph)

    def test_classification_is_invariant_under_input_permutation(self) -> None:
        straight = PredicateGraph.build(OVERLAP_NODES, OVERLAP_EDGES)
        shuffled = PredicateGraph.build(
            list(reversed(OVERLAP_NODES)), list(reversed(OVERLAP_EDGES))
        )
        first = {cycle.nodes: classify(cycle, straight) for cycle in cycles_in(straight)}
        second = {cycle.nodes: classify(cycle, shuffled) for cycle in cycles_in(shuffled)}
        assert first == second

    def test_verdict_and_reason_are_stable_across_repeated_classification(self) -> None:
        cycle = _cycle(("A", "B", "C"), 3)
        graph = PredicateGraph.build(OVERLAP_NODES, OVERLAP_EDGES)
        assert len({classify(cycle, graph).to_dict()["reason"] for _ in range(5)}) == 1

    def test_cycle_objects_are_hashable_and_comparable_by_value(self) -> None:
        """Canonical form is what makes a stored finding comparable to a recompute."""
        first = find_cycles(list(OVERLAP_NODES), list(OVERLAP_EDGES))
        second = find_cycles(list(reversed(OVERLAP_NODES)), list(reversed(OVERLAP_EDGES)))
        assert hash(first) == hash(second)
        assert set(first) == set(second)

    def test_classify_reports_the_cycle_it_was_given(self) -> None:
        cycle = _cycle(("B", "C", "D"), 3)
        graph = PredicateGraph.build(OVERLAP_NODES, OVERLAP_EDGES)
        verdict = classify(cycle, graph)
        assert verdict.cycle is cycle
        assert verdict.length == 3


class TestDomainIndependence:
    """FR-021 and FR-030 are enforced by the absence of code, so they are tested as such."""

    @pytest.mark.parametrize(
        "forbidden",
        ["family", "ownership", "cve", "malware", "vendor", "registry", "domain"],
    )
    def test_no_domain_word_in_any_identifier_or_code_literal(self, forbidden: str) -> None:
        """FR-021: no domain may appear *in the engine*.

        Identifiers, keyword arguments and non-docstring string literals are the code.
        Docstrings are exempt on purpose -- quoting the requirement a module implements
        is not the module implementing a domain -- and the test would otherwise punish
        the one place the requirement is most useful.
        """
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        docstrings = {
            ast.get_docstring(node, clean=False)
            for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        }
        haystack: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                haystack.append(node.id)
            elif isinstance(node, ast.arg):
                haystack.append(node.arg)
            elif isinstance(node, ast.Attribute):
                haystack.append(node.attr)
            elif isinstance(node, ast.keyword) and node.arg:
                haystack.append(node.arg)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                haystack.append(node.name)
            elif (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value
                and node.value not in docstrings
            ):
                haystack.append(node.value)
        pattern = re.compile(rf"\b{re.escape(forbidden)}\b")
        offenders = [item for item in haystack if pattern.search(item.lower())]
        assert not offenders, offenders

    def test_module_does_not_import_from_control_plane(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        assert "control-plane" not in source
        assert "control_plane" not in source

    def test_module_imports_only_the_standard_library(self) -> None:
        """A primitive that grows an import of the application stops being a primitive."""
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imported.add(node.module.split(".")[0])
        assert imported <= {"enum", "collections", "dataclasses", "typing", "__future__"}

    def test_no_predicate_literal_is_branched_on(self) -> None:
        """Predicates are data. The code may only compare them, never name one."""
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        named_string_comparisons = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Compare)
            and any(
                isinstance(side, ast.Constant)
                and isinstance(side.value, str)
                and side.value
                for side in node.comparators
            )
        ]
        assert not named_string_comparisons

    def test_unknown_predicates_classify_without_a_vocabulary(self) -> None:
        graph, inventory = _classify(
            ("a", "b", "c"),
            (
                ("a", "b", "unheard_of_1"),
                ("b", "c", "unheard_of_2"),
                ("c", "a", "unheard_of_3"),
            ),
        )
        verdict = classify(inventory[0], graph, cycles=inventory)
        assert verdict.verdict is CycleVerdict.SUSPECT
        assert set(inventory[0].vocabulary) == {
            "unheard_of_1",
            "unheard_of_2",
            "unheard_of_3",
        }

    def test_empty_predicate_string_is_still_an_edge(self) -> None:
        cycles = find_cycles(["a", "b"], [("a", "b", ""), ("b", "a", "")])
        assert len(cycles) == 1
        assert cycles[0].vocabulary == ("",)
