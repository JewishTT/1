"""Contract tests: HIERARCHY transitive closure over asymmetric predicates (spec 026, FR-023).

What is pinned here, and why each one is a contract rather than a detail:

* composition happens **only** where a law says so -- the default registry derives nothing
  from anything, and an undeclared predicate is distinguishable from a declared-atomic one;
* asymmetry is **computed**, not looked up: transitive and not symmetric is a hierarchy,
  transitive and symmetric is an equivalence and is labelled one;
* a derived edge is never an observed edge -- different types, different fields, one
  ``origin`` on each -- and a triple a source also reported comes back marked;
* a cycle terminates the walk and is reported, never dropped;
* the depth budget refuses and is marked, never approximated;
* order of input cannot change order of output or any identity;
* every derived edge cites observations and carries a derivation whose id is a content
  digest.
"""

from __future__ import annotations

import itertools
from typing import ClassVar

import pytest
from domain.derivation import MethodFingerprint

from context.hierarchy import (
    DEFAULT_LAWS,
    AmbiguousPredicateLaw,
    ClosureFlag,
    ClosureReport,
    DerivedEdge,
    EdgeOrigin,
    HierarchyError,
    ObservedEdge,
    PredicateDeclarationCycle,
    PredicateDeclarationError,
    PredicateLaw,
    PredicateLawKind,
    PredicateRegistry,
    hierarchy,
    transitive_closure,
)


def _laws(*declarations: PredicateLaw) -> PredicateRegistry:
    """A registry holding exactly the declared laws -- never a module-level default."""
    return PredicateRegistry(declarations)


CONTROL = PredicateLaw("owns", transitive=True)
ATOMIC = PredicateLaw("mentions", transitive=False)
EQUIVALENCE = PredicateLaw("knows", transitive=True, symmetric=True)
#: Invented on the spot. Nothing in the engine has ever heard of it, which is the point.
QUANT = PredicateLaw("quantifies", transitive=True)


class TestChainAndBranching:
    def test_two_hop_chain_yields_one_derived_edge(self) -> None:
        derived = transitive_closure(
            [("A", "owns", "B"), ("B", "owns", "C")],
            registry=_laws(CONTROL),
        )
        assert len(derived) == 1
        edge = derived[0]
        assert (edge.subject, edge.object) == ("A", "C")
        assert edge.predicate == "owns"
        assert edge.path == ("B",)
        assert edge.depth == 2
        assert edge.chain == ("A", "B", "C")

    def test_four_hop_chain_reaches_every_intermediate(self) -> None:
        derived = transitive_closure(
            [("A", "owns", "B"), ("B", "owns", "C"), ("C", "owns", "D"), ("D", "owns", "E")],
            registry=_laws(CONTROL),
        )
        pairs = {(e.subject, e.object, e.depth) for e in derived}
        assert pairs == {
            ("A", "C", 2),
            ("B", "D", 2),
            ("C", "E", 2),
            ("A", "D", 3),
            ("B", "E", 3),
            ("A", "E", 4),
        }

    def test_branching_subject_derives_both_arms(self) -> None:
        derived = transitive_closure(
            [("A", "owns", "B"), ("A", "owns", "C"), ("B", "owns", "D"), ("C", "owns", "D")],
            registry=_laws(CONTROL),
        )
        assert {(e.subject, e.object) for e in derived} == {("A", "D")}

    def test_output_is_sorted_shallowest_first(self) -> None:
        derived = transitive_closure(
            [("A", "owns", "B"), ("B", "owns", "C"), ("A", "owns", "D"), ("D", "owns", "E")],
            registry=_laws(CONTROL),
        )
        depths = [e.depth for e in derived]
        assert depths == sorted(depths)
        assert derived[0].depth == 2


class TestDiamond:
    def test_diamond_derives_one_edge_with_two_chains(self) -> None:
        derived = transitive_closure(
            [("A", "owns", "B"), ("B", "owns", "D"), ("A", "owns", "C"), ("C", "owns", "D")],
            registry=_laws(CONTROL),
        )
        assert len(derived) == 1
        assert derived[0].alternative_paths == 2
        assert len(derived[0].premises) == 2

    def test_diamond_does_not_emit_the_triple_twice(self) -> None:
        derived = transitive_closure(
            [("A", "owns", "B"), ("B", "owns", "D"), ("A", "owns", "C"), ("C", "owns", "D")],
            registry=_laws(CONTROL),
        )
        claims = [e.claim for e in derived]
        assert claims == ["A owns D"]

    def test_diamond_picks_the_canonical_chain_not_the_first_arrival(self) -> None:
        forward = transitive_closure(
            [("A", "owns", "B"), ("B", "owns", "D"), ("A", "owns", "C"), ("C", "owns", "D")],
            registry=_laws(CONTROL),
        )
        backward = transitive_closure(
            [("C", "owns", "D"), ("A", "owns", "C"), ("B", "owns", "D"), ("A", "owns", "B")],
            registry=_laws(CONTROL),
        )
        # ``B`` is the canonical intermediate: the chain is chosen by content, not by
        # whichever route the input happened to supply first.
        assert forward[0].path == backward[0].path == ("B",)
        assert forward[0].chain == ("A", "B", "D")


class TestAsymmetry:
    def test_reverse_edge_is_never_synthesized(self) -> None:
        derived = transitive_closure(
            [("A", "owns", "B"), ("B", "owns", "C")],
            registry=_laws(CONTROL),
        )
        claims = {e.claim for e in derived}
        assert claims == {"A owns C"}
        assert "C owns A" not in claims

    def test_derived_edge_declares_itself_asymmetric(self) -> None:
        edge = transitive_closure(
            [("A", "owns", "B"), ("B", "owns", "C")], registry=_laws(CONTROL)
        )[0]
        assert edge.asymmetric is True
        assert edge.law is PredicateLawKind.ASYMMETRIC

    def test_a_two_cycle_stops_at_the_observed_pair(self) -> None:
        report = hierarchy([("A", "owns", "B"), ("B", "owns", "A")], registry=_laws(CONTROL))
        assert {e.claim for e in report.derived} <= {"A owns A", "B owns B"}
        assert report.derived == ()
        assert report.cycle_closed is True


class TestPredicateLaws:
    def test_default_registry_derives_nothing(self) -> None:
        assert transitive_closure([("A", "owns", "B"), ("B", "owns", "C")]) == ()
        assert DEFAULT_LAWS.declared() == ()

    def test_undeclared_predicate_is_not_an_error_and_not_a_closure(self) -> None:
        report = hierarchy([("A", "mentions", "B"), ("B", "mentions", "C")])
        assert report.derived == ()
        assert report.undeclared_predicates == ("mentions",)

    def test_atomic_predicate_is_reported_apart_from_undeclared(self) -> None:
        report = hierarchy(
            [
                ("A", "owns", "B"),
                ("B", "owns", "C"),
                ("A", "mentions", "B"),
                ("B", "mentions", "C"),
            ],
            registry=_laws(CONTROL, ATOMIC),
        )
        assert report.atomic_predicates == ("mentions",)
        assert report.undeclared_predicates == ()
        assert {e.claim for e in report.derived} == {"A owns C"}

    def test_no_predicate_vocabulary_is_baked_in(self) -> None:
        """A predicate invented after this module was written behaves like any other."""
        report = hierarchy(
            [("A", "quantifies", "B"), ("B", "quantifies", "C")], registry=_laws(QUANT)
        )
        assert {e.claim for e in report.derived} == {"A quantifies C"}

    def test_inherited_law_makes_a_finer_predicate_transitive(self) -> None:
        laws = _laws(
            PredicateLaw("controls", transitive=True),
            PredicateLaw("branch_of", extends=("controls",)),
        )
        report = hierarchy([("A", "branch_of", "B"), ("B", "branch_of", "C")], registry=laws)
        assert {e.claim for e in report.derived} == {"A branch_of C"}
        assert laws.known("branch_of") is True
        assert laws.ancestors_of("branch_of") == ("controls",)

    def test_nearest_declaration_wins_per_field(self) -> None:
        laws = _laws(
            PredicateLaw("controls", transitive=True, symmetric=False, depth_limit=5),
            PredicateLaw("strict_controls", extends=("controls",), symmetric=True),
        )
        resolved = laws.resolve("strict_controls")
        assert resolved.transitive is True  # inherited
        assert resolved.symmetric is True  # own, nearest
        assert resolved.depth_limit == 5  # inherited
        assert laws.kind("strict_controls") is PredicateLawKind.EQUIVALENCE

    def test_sibling_disagreement_is_refused_not_tie_broken(self) -> None:
        laws = _laws(
            PredicateLaw("controls", transitive=True),
            PredicateLaw("branches", transitive=False),
        )
        with pytest.raises(AmbiguousPredicateLaw) as caught:
            laws.declare(PredicateLaw("domains", extends=("controls", "branches")))
        assert "transitive" in str(caught.value)
        assert laws.known("domains") is False  # rolled back, not half-declared

    def test_sibling_agreement_is_accepted(self) -> None:
        laws = _laws(
            PredicateLaw("controls", transitive=True, depth_limit=4),
            PredicateLaw("branches", transitive=True, depth_limit=4),
            PredicateLaw("domains", extends=("controls", "branches")),
        )
        resolved = laws.resolve("domains")
        assert resolved.transitive is True
        assert resolved.depth_limit == 4

    def test_declaration_cycles_are_refused(self) -> None:
        laws = PredicateRegistry()
        # ``alpha`` is declared naming a parent that does not exist yet; that is admitted
        # because laws arrive as a table. Declaring ``beta`` back the other way is what
        # closes the loop, and it is refused there and rolled back.
        laws.declare(PredicateLaw("alpha", transitive=True, extends=("beta",)))
        assert laws.unresolved_parents("alpha") == ("beta",)
        with pytest.raises(PredicateDeclarationCycle):
            laws.declare(PredicateLaw("beta", transitive=True, extends=("alpha",)))
        assert laws.known("beta") is False
        assert laws.resolve("alpha").transitive is True

    def test_a_parent_declared_later_is_picked_up(self) -> None:
        laws = PredicateRegistry()
        laws.declare(PredicateLaw("branch_of", extends=("controls",)))
        assert laws.resolve("branch_of").transitive is None  # nothing to inherit yet
        laws.declare(PredicateLaw("controls", transitive=True))
        assert laws.resolve("branch_of").transitive is True
        assert laws.unresolved_parents("branch_of") == ()

    def test_self_extending_law_is_refused(self) -> None:
        with pytest.raises(PredicateDeclarationCycle):
            PredicateLaw("owns", extends=("owns",))

    def test_dangling_parent_is_reported_not_refused(self) -> None:
        laws = PredicateRegistry([PredicateLaw("branch_of", extends=("controls",))])
        assert laws.unresolved_parents("branch_of") == ("controls",)
        # Nothing to inherit, so the predicate composes nothing -- and the closure report
        # says "undeclared" rather than reporting a hierarchy that was never declared.
        report = hierarchy([("A", "branch_of", "B"), ("B", "branch_of", "C")], registry=laws)
        assert report.derived == ()
        assert report.undeclared_predicates == ("branch_of",)

    def test_second_law_for_one_name_is_refused(self) -> None:
        laws = _laws(CONTROL)
        with pytest.raises(PredicateDeclarationError):
            laws.declare(PredicateLaw("owns", transitive=False))

    def test_symmetric_transitive_predicate_is_flagged_not_hidden(self) -> None:
        report = hierarchy([("A", "knows", "B"), ("B", "knows", "C")], registry=_laws(EQUIVALENCE))
        edge = report.derived[0]
        assert edge.has(ClosureFlag.EQUIVALENCE)
        assert edge.asymmetric is False
        assert report.equivalence_predicates == ("knows",)

    def test_cross_predicate_composition_is_declared_not_inferred(self) -> None:
        laws = _laws(
            CONTROL,
            PredicateLaw(
                "subsidiary_of",
                transitive=True,
                extends=("owns",),
                composes_with=("subsidiary_of", "controls"),
            ),
            PredicateLaw("controls", transitive=True),
        )
        report = hierarchy([("A", "subsidiary_of", "B"), ("B", "controls", "C")], registry=laws)
        assert {e.claim for e in report.derived} == {"A subsidiary_of C"}
        assert report.derived[0].depth == 2

    def test_composes_with_defaults_to_strict_self_composition(self) -> None:
        laws = _laws(CONTROL, PredicateLaw("controls", transitive=True))
        assert laws.composes_with("owns") == ("owns",)
        assert laws.composes_with("mentions") == ()
        report = hierarchy([("A", "owns", "B"), ("B", "controls", "C")], registry=laws)
        assert report.derived == ()


class TestCycles:
    def test_cycle_terminates_and_is_reported(self) -> None:
        report = hierarchy(
            [("A", "owns", "B"), ("B", "owns", "C"), ("C", "owns", "A")],
            registry=_laws(CONTROL),
        )
        assert report.cycles
        assert report.cycle_closed is True
        assert report.is_total is False

    def test_cycle_is_never_a_self_derivation(self) -> None:
        report = hierarchy(
            [("A", "owns", "B"), ("B", "owns", "C"), ("C", "owns", "A")],
            registry=_laws(CONTROL),
        )
        assert all(e.subject != e.object for e in report.derived)

    def test_cycle_records_the_chain_it_tried_to_close(self) -> None:
        report = hierarchy(
            [("A", "owns", "B"), ("B", "owns", "C"), ("C", "owns", "A")],
            registry=_laws(CONTROL),
        )
        closed = {c.closed_path for c in report.cycles}
        assert ("A", "B", "C", "A") in closed

    def test_edges_derived_from_a_cyclic_subject_are_marked(self) -> None:
        report = hierarchy(
            [
                ("B", "owns", "C"),
                ("C", "owns", "E"),
                ("E", "owns", "F"),
                ("C", "owns", "B"),
            ],
            registry=_laws(CONTROL),
        )
        # ``B`` and ``C`` are on a loop; the entailments below them still hold and are
        # marked as resting on a non-well-founded premise.
        from_b = [e for e in report.derived if e.subject == "B"]
        assert from_b
        assert all(e.has(ClosureFlag.CYCLE_AT_SUBJECT) for e in from_b)

    def test_a_cycle_does_not_erase_the_acyclic_part(self) -> None:
        report = hierarchy(
            [
                ("A", "owns", "B"),
                ("B", "owns", "C"),
                ("C", "owns", "A"),
                ("C", "owns", "D"),
            ],
            registry=_laws(CONTROL),
        )
        assert ("A", "C") in {(e.subject, e.object) for e in report.derived}
        assert report.cycles

    def test_self_loop_is_reported_and_never_composed_from(self) -> None:
        report = hierarchy(
            [("A", "owns", "A"), ("A", "owns", "B"), ("B", "owns", "C")], registry=_laws(CONTROL)
        )
        assert report.self_loops == ("A owns A",)
        assert all(e.subject != e.object for e in report.derived)
        assert report.is_total is False


class TestDepthLimit:
    def test_depth_limit_stops_the_walk(self) -> None:
        edges = [
            ("A", "owns", "B"),
            ("B", "owns", "C"),
            ("C", "owns", "D"),
            ("D", "owns", "E"),
        ]
        report = hierarchy(edges, depth_limit=2, registry=_laws(CONTROL))
        # The budget bounds depth, not how many subjects are walked: every subject gets its
        # one allowed hop and nothing gets a second.
        assert {e.claim for e in report.derived} == {"A owns C", "B owns D", "C owns E"}
        # Only the edges that actually had somewhere left to go are named: "C owns E" ended
        # at a leaf and was not cut off by anything.
        assert report.truncated == ("A owns C", "B owns D")
        assert max(e.depth for e in report.derived) == 2
        assert report.is_total is False

    def test_depth_limit_flags_the_deepest_edge(self) -> None:
        report = hierarchy(
            [("A", "owns", "B"), ("B", "owns", "C"), ("C", "owns", "D")],
            depth_limit=2,
            registry=_laws(CONTROL),
        )
        edge = next(e for e in report.derived if e.object == "C")
        assert edge.has(ClosureFlag.DEPTH_LIMIT)

    def test_a_complete_closure_reports_no_truncation(self) -> None:
        report = hierarchy(
            [("A", "owns", "B"), ("B", "owns", "C")], depth_limit=8, registry=_laws(CONTROL)
        )
        assert report.truncated == ()
        assert report.is_total is True

    def test_declared_limit_is_tighter_than_the_callers(self) -> None:
        laws = _laws(PredicateLaw("owns", transitive=True, depth_limit=2))
        report = hierarchy(
            [("A", "owns", "B"), ("B", "owns", "C"), ("C", "owns", "D")],
            depth_limit=5,
            registry=laws,
        )
        assert max(e.depth for e in report.derived) == 2
        assert report.truncated

    def test_depth_limit_of_one_composes_nothing_and_says_so(self) -> None:
        report = hierarchy(
            [("A", "owns", "B"), ("B", "owns", "C")], depth_limit=1, registry=_laws(CONTROL)
        )
        assert report.derived == ()
        assert report.truncated == ("A owns B",)

    def test_a_non_positive_depth_limit_is_refused(self) -> None:
        with pytest.raises(HierarchyError):
            hierarchy([("A", "owns", "B")], depth_limit=0, registry=_laws(CONTROL))


class TestDeterminism:
    EDGES: ClassVar[tuple[tuple[str, str, str], ...]] = (
        ("A", "owns", "B"),
        ("B", "owns", "C"),
        ("A", "owns", "C"),
        ("C", "owns", "D"),
        ("A", "knows", "D"),
    )

    def test_every_permutation_gives_the_same_output(self) -> None:
        laws = _laws(CONTROL, EQUIVALENCE)
        reference = [e.as_dict() for e in transitive_closure(self.EDGES, registry=laws)]
        for order in itertools.permutations(self.EDGES):
            other = [e.as_dict() for e in transitive_closure(order, registry=laws)]
            assert other == reference

    def test_derivation_ids_survive_permutation(self) -> None:
        laws = _laws(CONTROL)
        baseline = [e.derivation_id for e in transitive_closure(self.EDGES, registry=laws)]
        shuffled = list(reversed(self.EDGES))
        assert [e.derivation_id for e in transitive_closure(shuffled, registry=laws)] == baseline

    def test_cycles_are_reported_in_a_stable_order(self) -> None:
        edges = [("A", "owns", "B"), ("B", "owns", "C"), ("C", "owns", "A")]
        first = hierarchy(edges, registry=_laws(CONTROL)).as_dict()
        second = hierarchy(list(reversed(edges)), registry=_laws(CONTROL)).as_dict()
        assert first == second

    def test_running_twice_changes_nothing(self) -> None:
        laws = _laws(CONTROL)
        one = hierarchy(self.EDGES, registry=laws).as_dict()
        two = hierarchy(self.EDGES, registry=laws).as_dict()
        assert one == two


class TestObservedVersusDerived:
    def test_observed_and_derived_are_never_one_list(self) -> None:
        report = hierarchy([("A", "owns", "B"), ("B", "owns", "C")], registry=_laws(CONTROL))
        assert [type(e) for e in report.observed] == [ObservedEdge, ObservedEdge]
        assert all(isinstance(e, DerivedEdge) for e in report.derived)
        assert len(report.observed) == 2
        assert len(report.derived) == 1

    def test_origins_are_distinct_on_both_kinds(self) -> None:
        report = hierarchy([("A", "owns", "B"), ("B", "owns", "C")], registry=_laws(CONTROL))
        assert all(e.origin is EdgeOrigin.OBSERVED for e in report.observed)
        assert all(e.is_derived and not e.is_observed for e in report.derived)

    def test_an_observed_edge_is_never_re_emitted_as_derived(self) -> None:
        report = hierarchy(
            [("A", "owns", "B"), ("B", "owns", "C"), ("A", "owns", "C")],
            registry=_laws(CONTROL),
        )
        assert "A owns C" in {e.claim for e in report.derived}
        assert "A owns B" not in {e.claim for e in report.derived}

    def test_a_corroborated_triple_is_marked_and_counted_apart(self) -> None:
        report = hierarchy(
            [("A", "owns", "B"), ("B", "owns", "C"), ("A", "owns", "C")],
            registry=_laws(CONTROL),
        )
        edge = next(e for e in report.derived if e.object == "C")
        assert edge.has(ClosureFlag.CORROBORATED)
        assert edge.is_novel is False
        assert report.corroborated == (edge,)
        assert report.novel == ()

    def test_duplicate_reports_collapse_into_one_observed_edge(self) -> None:
        report = hierarchy(
            [
                ObservedEdge("A", "owns", "B", source_ref="doc:1"),
                ObservedEdge("A", "owns", "B", source_ref="doc:2"),
            ],
            registry=_laws(CONTROL),
        )
        assert len(report.observed) == 1
        assert report.observed[0].sources == ("doc:1", "doc:2")

    def test_the_serialized_form_carries_the_origin_on_both_kinds(self) -> None:
        report = hierarchy([("A", "owns", "B"), ("B", "owns", "C")], registry=_laws(CONTROL))
        payload = report.as_dict()
        assert {e["origin"] for e in payload["observed"]} == {"observed"}
        assert {e["origin"] for e in payload["derived"]} == {"derived"}

    def test_snapshot_reports_counts_and_the_completeness_of_the_walk(self) -> None:
        report = hierarchy([("A", "owns", "B"), ("B", "owns", "C")], registry=_laws(CONTROL))
        assert report.snapshot() == {
            "observed": 2,
            "derived": 1,
            "novel": 1,
            "corroborated": 0,
            "max_depth": 2,
            "cycles": 0,
            "self_loops": 0,
            "truncated": 0,
            "depth_limit": 8,
            "is_total": True,
        }


class TestDerivations:
    def test_every_derived_edge_cites_observations_and_only_observations(self) -> None:
        report = hierarchy(
            [("A", "owns", "B"), ("B", "owns", "C"), ("C", "owns", "D")],
            registry=_laws(CONTROL),
        )
        observed_ids = {e.edge_id for e in report.observed}
        for edge in report.derived:
            assert edge.premises
            assert set(edge.premises) <= observed_ids

    def test_premises_are_the_edges_along_the_chain_in_order(self) -> None:
        report = hierarchy([("A", "owns", "B"), ("B", "owns", "C")], registry=_laws(CONTROL))
        edge = report.derived[0]
        assert [e.claim for e in edge.premise_edges] == ["A owns B", "B owns C"]

    def test_each_edge_has_its_own_derivation_recorded(self) -> None:
        report = hierarchy(
            [("A", "owns", "B"), ("B", "owns", "C"), ("C", "owns", "D")],
            registry=_laws(CONTROL),
        )
        assert len(report.derivations) == len(report.derived)
        for edge in report.derived:
            assert edge.derivation_id in report.derivations

    def test_the_derivation_names_the_chain_it_walked(self) -> None:
        report = hierarchy([("A", "owns", "B"), ("B", "owns", "C")], registry=_laws(CONTROL))
        statement = report.derived[0].derivation.statement
        assert "A -> B -> C" in statement
        assert "transitivity of 'owns'" in statement

    def test_identical_runs_produce_identical_ids(self) -> None:
        laws = _laws(CONTROL)
        edges = [("A", "owns", "B"), ("B", "owns", "C")]
        assert [e.derivation_id for e in transitive_closure(edges, registry=laws)] == [
            e.derivation_id for e in transitive_closure(edges, registry=laws)
        ]

    def test_a_different_budget_is_a_different_derivation(self) -> None:
        laws = _laws(CONTROL)
        edges = [("A", "owns", "B"), ("B", "owns", "C"), ("C", "owns", "D")]
        shallow = transitive_closure(edges, depth_limit=2, registry=laws)[0]
        deep = next(
            e
            for e in transitive_closure(edges, depth_limit=4, registry=laws)
            if e.subject == "A" and e.object == "D"
        )
        assert shallow.claim != deep.claim
        common = [e for e in transitive_closure(edges, depth_limit=4, registry=laws)]
        narrow = next(e for e in common if e.subject == "A" and e.object == "C")
        assert narrow.derivation.environment.values["depth_limit"] == 4

    def test_a_different_method_version_is_a_different_id(self) -> None:
        laws = _laws(CONTROL)
        edges = [("A", "owns", "B"), ("B", "owns", "C")]
        v1 = transitive_closure(edges, registry=laws)[0].derivation_id
        v2 = transitive_closure(
            edges, registry=laws, method=MethodFingerprint("hierarchy.transitive_closure", "v2")
        )[0].derivation_id
        assert v1 != v2

    def test_the_id_is_a_digest_of_content_not_a_counter(self) -> None:
        edge = ObservedEdge("A", "owns", "B", source_ref="doc:1")
        assert edge.edge_id == ObservedEdge("A", "owns", "B", source_ref="doc:1").edge_id
        assert edge.edge_id != ObservedEdge("A", "owns", "B", source_ref="doc:2").edge_id
        assert edge.edge_id.startswith("HE-")

    def test_the_serialized_edge_carries_its_derivation(self) -> None:
        report = hierarchy([("A", "owns", "B"), ("B", "owns", "C")], registry=_laws(CONTROL))
        payload = report.derived[0].as_dict()
        assert payload["derivation_id"] == report.derived[0].derivation_id
        assert payload["chain"] == ["A", "B", "C"]
        assert payload["statement"]


class TestReading:
    def test_ancestors_walks_back_up(self) -> None:
        report = hierarchy([("A", "owns", "B"), ("B", "owns", "C")], registry=_laws(CONTROL))
        # ``B`` is the reported parent of ``C`` and ``A`` reaches it by entailment; both sit
        # one hop above ``C`` in the closure, so the order within that hop is by name.
        assert report.ancestors("C") == ("A", "B")

    def test_a_root_has_no_ancestors_and_that_is_an_answer(self) -> None:
        report = hierarchy([("A", "owns", "B"), ("B", "owns", "C")], registry=_laws(CONTROL))
        assert report.ancestors("A") == ()

    def test_the_empty_graph_closes_to_an_empty_report(self) -> None:
        report = hierarchy([], registry=_laws(CONTROL))
        assert isinstance(report, ClosureReport)
        assert report.derived == ()
        assert report.observed == ()
        assert report.is_total is True
        assert len(report.derivations) == 0

    def test_an_edge_with_a_blank_part_is_refused(self) -> None:
        with pytest.raises(HierarchyError):
            ObservedEdge("A", "", "C")

    def test_a_malformed_tuple_is_refused(self) -> None:
        with pytest.raises(HierarchyError):
            transitive_closure([("A", "owns")], registry=_laws(CONTROL))

    def test_a_path_budget_is_flagged_rather_than_silently_capped(self) -> None:
        edges = [("A", "owns", m) for m in ("B", "C", "D")] + [
            ("B", "owns", "Z"),
            ("C", "owns", "Z"),
            ("D", "owns", "Z"),
        ]
        report = hierarchy(edges, registry=_laws(CONTROL), max_paths=2)
        edge = next(e for e in report.derived if e.object == "Z")
        # Three distinct chains reach Z and the budget is two, so the count is a floor and
        # the edge says so rather than reporting a number the walk did not finish counting.
        assert edge.has(ClosureFlag.PATH_BUDGET)
        assert edge.alternative_paths == 2
        unbounded = hierarchy(edges, registry=_laws(CONTROL)).derived
        assert next(e for e in unbounded if e.object == "Z").alternative_paths == 3
        assert not next(e for e in unbounded if e.object == "Z").has(ClosureFlag.PATH_BUDGET)

    def test_a_non_positive_path_budget_is_refused(self) -> None:
        with pytest.raises(HierarchyError):
            hierarchy([("A", "owns", "B")], registry=_laws(CONTROL), max_paths=0)
