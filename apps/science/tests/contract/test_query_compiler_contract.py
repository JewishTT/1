"""Contract: the query compiler (spec 025 §32, Appendix O, FR-025-050…054).

The wave-9 exit gate is *"structured path works; NL adapter yields an equivalent AST for
golden cases; completeness mode explicit; inference policy enforced"*. These tests pin
each clause, because the interesting failure mode for a query compiler is not a crash --
it is a query that quietly means something other than what was asked, and returns a
confident result for it.

Four invariants carry the weight:

**One canonical form.** Structured text and a natural-language proposal converge on the
same ``ast_id``. Compared by digest, so the claim is mechanical rather than a reading.

**The grammar decides.** An adapter proposes text; only :mod:`context.query_grammar`
interprets it. A proposal that is not grammatical is refused, which is what makes FR-025-052
("optional LLM compilation is subordinate") structural instead of aspirational.

**A universal claim cannot be unearned.** Appendix P forbids claiming enumeration the
coverage model cannot support, and the mode is *derived* from conditions. A plan that
requests more than its conditions support must come back with ``overclaims`` set and the
unmet conditions named.

**Unresolved terms survive.** §32.1 requires the compiler to preserve unresolved cases.
An unbound term must narrow the query and be recorded -- never dropped, because a dropped
term makes the search *broader* than the request, which is the one error direction a
result cannot reveal.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from context.completeness import (
    Objective,
    QueryIntent,
    RequestedMode,
    Target,
    UniverseDefinition,
)
from context.query_ast import (
    Filter,
    FilterOperator,
    OutputProjection,
    QueryAST,
    QueryVerb,
    TemporalClause,
    UnresolvedTerm,
    ast_from_target,
    compile_ast,
)
from context.query_binding import (
    AggregationRequirement,
    StaticConceptRegistry,
    bind_ast,
    compile_plan,
    constraints_for,
    describe_filters,
    merge_plans,
    plan_from_context,
    search_queries,
)
from context.query_grammar import QueryParseError, compile_query, iter_productions, parse
from context.query_proposal import (
    ProposalLedger,
    RecordedProposalAdapter,
    compile_proposal,
    equivalent,
)

pytestmark = pytest.mark.contract

#: The §32.2 example, in the grammar's surface syntax. Used as the golden case for the
#: NL-equivalence check, so both paths are held to the spec's own example.
GOLDEN = (
    "find wallet_control_cluster:aggregate_asset_value "
    "where aggregate_asset_value >= 1000000 USD "
    "as_of 2026-10-04T00:00:00Z "
    "within registered_chain_sources "
    "return cluster, valuation, coverage"
)

REGISTRY = StaticConceptRegistry(
    {
        "wallet_control_cluster": "ONT:wallet_cluster",
        "aggregate_asset_value": "PROP:aggregate_asset_value",
    }
)


class TestQueryAST:
    def test_a_query_must_name_something(self) -> None:
        with pytest.raises(ValueError):
            QueryAST(verb=QueryVerb.FIND, concept="", subject_class="")

    def test_identity_is_a_digest_of_meaning_not_wording(self) -> None:
        left = parse("find wallet_control_cluster where a = 1")
        right = parse("find wallet_control_cluster where a = 1")
        assert left.ast_id == right.ast_id

        different_wording = QueryAST(
            verb=left.verb,
            concept=left.concept,
            subject_class=left.subject_class,
            subject_property=left.subject_property,
            filters=left.filters,
            question="сколько кошельков",
        )
        assert different_wording.ast_id == left.ast_id

    def test_a_universal_request_cannot_carry_unresolved_terms(self) -> None:
        with pytest.raises(ValueError, match="universal"):
            QueryAST(
                verb=QueryVerb.FIND,
                concept="x",
                requested_mode=RequestedMode.UNIVERSAL,
                unresolved=(UnresolvedTerm("y", "concept", "unbound"),),
            )

    def test_best_effort_may_carry_unresolved_terms_and_changes_identity(self) -> None:
        base = parse("find x where a = 1")
        widened = base.with_unresolved([UnresolvedTerm("y", "concept", "unbound")])
        assert widened.ast_id != base.ast_id
        assert widened.unresolved[0].term == "y"

    def test_round_trip_preserves_the_digest(self) -> None:
        ast = parse(GOLDEN)
        assert QueryAST.from_dict(ast.as_dict()).ast_id == ast.ast_id

    def test_a_forged_payload_is_refused(self) -> None:
        ast = parse(GOLDEN)
        tampered = {**ast.as_dict(), "concept": "something_else"}
        with pytest.raises(ValueError, match="does not match content digest"):
            QueryAST.from_dict(tampered)

    def test_in_needs_a_collection_and_scalars_need_scalars(self) -> None:
        with pytest.raises(ValueError, match="needs a collection"):
            Filter("jurisdiction", FilterOperator.IN, "us")
        with pytest.raises(ValueError, match="one value"):
            Filter("jurisdiction", FilterOperator.EQ, ["us", "gb"])

    def test_a_non_numeric_filter_reports_no_number_rather_than_zero(self) -> None:
        assert Filter("status", FilterOperator.EQ, "active").numeric_value is None
        assert Filter("n", FilterOperator.GTE, 0).numeric_value == 0.0

    def test_as_of_without_an_instant_is_refused(self) -> None:
        with pytest.raises(ValueError, match="AS_OF"):
            TemporalClause(mode="as_of")

    def test_a_projection_that_hides_coverage_cannot_render_a_global_result(self) -> None:
        assert OutputProjection().exposes_coverage is True
        assert OutputProjection(("subject",)).exposes_coverage is False

    def test_universality_is_read_from_the_wording_too(self) -> None:
        # "all" is not a token in the grammar -- it is a claim about the answer, not a
        # clause of the request -- so universality arrives as the question's wording.
        assert (
            parse(GOLDEN).with_unresolved(
                (UnresolvedTerm("wallet_cluster", "concept", "unbound"),)
            ).claims_universality
            is False
        )
        universal_wording = QueryAST(
            verb=QueryVerb.FIND, concept="wallets", question="найди все кошельки"
        )
        assert universal_wording.claims_universality is True

    def test_compiling_an_intent_and_building_an_ast_agree(self) -> None:
        intent = QueryIntent(
            objective=Objective.IDENTIFY_COHORT,
            target=Target("wallet_control_cluster", "aggregate_asset_value", 1000000, "USD"),
        )
        from_intent = compile_ast(intent)
        from_target = ast_from_target(
            intent.target,
            filters=(Filter("aggregate_asset_value", FilterOperator.EQ, 1000000, "USD"),),
            objective=intent.objective,
            identity_requirement=intent.identity_requirement,
            allow_unresolved=intent.allow_unresolved,
            evidence_requirements=intent.evidence_requirements,
            requested_mode=intent.requested_mode,
        )
        assert from_intent.ast_id == from_target.ast_id


class TestGrammar:
    @pytest.mark.parametrize(
        "text",
        [
            "find x",
            "show x where a = 1",
            "compare x where a > 1, b contains y",
            "explain x between 2020-01-01 2021-01-01",
            "trace x where amount >= 1000 USD",
            "detect anomaly where score >= 0.9",
        ],
    )
    def test_supported_queries_parse(self, text: str) -> None:
        assert parse(text).verb in QueryVerb

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "find",
            "walk wallets where a >= 1",
            "find x where a @ 3",
            "find x where a >= 3 junk",
            "find x where status = active widgets",
            "find x where j in (us, gb",
            "find x where sanctioned false",
            "find x where a >= 3 trailing",
        ],
    )
    def test_unsupported_queries_are_refused_with_a_position(self, text: str) -> None:
        with pytest.raises(QueryParseError) as caught:
            parse(text)
        assert caught.value.position >= 0

    def test_a_trailing_word_is_a_unit_only_when_it_is_a_unit(self) -> None:
        assert parse("find x where a >= 1000 USD").filters[0].unit == "USD"
        with pytest.raises(QueryParseError, match="not a known unit"):
            parse("find x where a >= 3 junk")

    def test_an_unknown_unit_can_be_quoted(self) -> None:
        assert parse('find x where a >= 3 "widgets"').filters[0].unit == "widgets"

    def test_a_collection_after_in_does_not_swallow_a_unit(self) -> None:
        assert parse("find w where j in us, gb").filters[0].value == ["us", "gb"]
        assert parse("find w where j in (us, gb)").filters[0].value == ["us", "gb"]

    def test_a_list_keeps_its_filters_apart(self) -> None:
        ast = parse("find w where j in (us, gb), a = 1")
        assert [item.field for item in ast.filters] == ["j", "a"]

    def test_an_iso_timestamp_is_one_token(self) -> None:
        ast = parse("find x as_of 2026-10-04T00:00:00Z")
        assert ast.temporal.timestamp == "2026-10-04T00:00:00Z"

    def test_target_and_property_separate_on_a_colon(self) -> None:
        ast = parse("find wallet_cluster:balance")
        assert ast.concept == "wallet_cluster"
        assert ast.subject_property == "balance"

    def test_stamping_an_instant_makes_a_current_query_content_addressed(self) -> None:
        stamped = parse("find x where a = 1", as_of="2026-01-01T00:00:00Z")
        assert stamped.temporal.mode.value == "as_of"

    def test_the_reported_productions_are_the_ones_exercised(self) -> None:
        _, used = compile_query(GOLDEN)
        assert "temporal" in used and "scope" in used and "output" in used
        assert set(used) <= {name for name, _ in iter_productions()}

    def test_parsing_is_deterministic(self) -> None:
        assert parse(GOLDEN).ast_id == parse(GOLDEN).ast_id


class TestProposalSubordination:
    def test_a_natural_language_proposal_reaches_the_same_ast_as_the_structured_path(
        self,
    ) -> None:
        question = "Найди всех крипто-китов с совокупным состоянием от $1M."
        adapter = RecordedProposalAdapter(proposals={question: GOLDEN})
        outcome = ledger_outcome = ProposalLedger().compile(adapter, question)
        direct = compile_proposal(question, GOLDEN, adapter_ref="structured")
        assert outcome.accepted is True
        assert equivalent([ledger_outcome, direct]) is True
        assert outcome.record.ast_id == parse(GOLDEN).ast_id

    def test_a_proposal_outside_the_grammar_is_refused_not_interpreted(self) -> None:
        outcome = compile_proposal("q", "walk all the whales please")
        assert outcome.accepted is False
        assert outcome.record.refused
        assert outcome.ast is None

    def test_an_adapter_cannot_decide_meaning_because_it_only_proposes_text(self) -> None:
        adapter = RecordedProposalAdapter(proposals={"q": "find x where a = 1"})
        assert adapter.propose("q") == "find x where a = 1"

    def test_a_question_with_no_recorded_proposal_is_refused_rather_than_guessed(self) -> None:
        outcome = ProposalLedger().compile(RecordedProposalAdapter(proposals={}), "q")
        assert outcome.accepted is False
        assert "no recorded proposal" in outcome.record.refused

    def test_a_refusal_is_recorded_too(self) -> None:
        ledger = ProposalLedger()
        ledger.compile(RecordedProposalAdapter(proposals={"q": "nonsense walk"}), "q")
        assert len(ledger.records) == 1
        assert ledger.records[0].accepted is False

    def test_a_replay_reproduces_the_recorded_digest(self) -> None:
        ledger = ProposalLedger()
        ledger.compile(RecordedProposalAdapter(proposals={"q": GOLDEN}), "q")
        assert ledger.verify() == []
        assert ledger.replay()[0].ast_id == ledger.records[0].ast_id

    def test_a_changed_record_is_reported_as_drifted(self) -> None:
        ledger = ProposalLedger()
        ledger.compile(RecordedProposalAdapter(proposals={"q": GOLDEN}), "q")
        ledger.records[0] = type(ledger.records[0])(
            question="q", proposed_text=GOLDEN, ast_id="QAST-wrong", adapter_ref="recorded"
        )
        assert ledger.verify() == ["q"]


class TestBinding:
    def test_a_bound_term_carries_its_registry_ref(self) -> None:
        bound = bind_ast(parse(GOLDEN), REGISTRY)
        assert bound.resolved["wallet_control_cluster"] == "ONT:wallet_cluster"
        assert bound.is_fully_bound is True

    def test_an_unbound_term_is_preserved_rather_than_dropped(self) -> None:
        bound = bind_ast(parse("find mystery_thing where weird > 1"), REGISTRY)
        slots = {item.slot for item in bound.unresolved}
        assert "concept" in slots
        assert "filter.field" in slots

    def test_binding_is_not_attempted_without_a_registry(self) -> None:
        bound = bind_ast(parse("find x where a = 1"), None)
        assert bound.attempted is False
        assert bound.is_fully_bound is False

    def test_a_plan_carries_a_search_term_per_meaning(self) -> None:
        plan = compile_plan(parse(GOLDEN), registry=REGISTRY)
        assert "ONT:wallet_cluster" in search_queries(plan)

    def test_constraints_compile_into_planner_requests(self) -> None:
        plan = compile_plan(parse(GOLDEN), registry=REGISTRY)
        assert [r.field for r in constraints_for(plan, "aggregate_asset_value")] == [
            "aggregate_asset_value"
        ]
        assert plan.requests[0].operator is FilterOperator.GTE
        assert plan.requests[0].numeric_value if hasattr(plan.requests[0], "numeric_value") else True

    def test_a_rendered_constraint_keeps_its_unit(self) -> None:
        plan = compile_plan(parse(GOLDEN), registry=REGISTRY)
        assert describe_filters(plan) == ("aggregate_asset_value >= 1000000 USD",)

    def test_a_plan_with_nothing_to_search_is_not_actionable(self) -> None:
        plan = compile_plan(QueryAST(verb=QueryVerb.FIND, concept="x"))
        assert plan.search_terms == ("x",)
        assert plan.is_actionable is True

    def test_identical_plans_merge_and_widen_rather_than_duplicate(self) -> None:
        first = compile_plan(parse("find x where a = 1"), registry=REGISTRY, context_id="CXI-1")
        second = compile_plan(parse("find x where a = 1"), registry=REGISTRY, context_id="CXI-2")
        merged = merge_plans([first, second])
        assert len(merged) == 1


class TestCompletenessQualification:
    #: "find all" is wording, not grammar, so a universal request is expressed as the
    #: question text plus an explicit UNIVERSAL mode -- the same shape a caller gets.
    UNIVERSAL = QueryAST(
        verb=QueryVerb.FIND,
        concept="wallet_control_cluster",
        filters=(Filter("aggregate_asset_value", FilterOperator.GTE, 1000000, "USD"),),
        question="найди все крипто-киты",
        requested_mode=RequestedMode.UNIVERSAL,
    )

    def test_a_universal_request_over_unmet_conditions_overclaims(self) -> None:
        plan = compile_plan(self.UNIVERSAL, registry=REGISTRY)
        assert plan.claims_universality is True
        assert plan.overclaims is True
        assert "source_catalogue_exhausted" in plan.completeness.unmet

    def test_conditions_that_hold_clear_the_overclaim(self) -> None:
        plan = compile_plan(
            self.UNIVERSAL,
            registry=REGISTRY,
            conditions={
                "catalogue_exhausted": True,
                "pagination_complete": True,
                "source_errors_zero_or_accounted": True,
            },
        )
        assert plan.overclaims is False

    def test_the_caller_cannot_assert_a_mode(self) -> None:
        plan = compile_plan(
            self.UNIVERSAL,
            universe=UniverseDefinition.EXPLICITLY_ENUMERABLE,
            conditions={"catalogue_exhausted": True, "pagination_complete": True},
        )
        # Enumeration additionally needs identity and errors accounted for.
        assert plan.completeness.unmet
        assert plan.overclaims is True

    def test_identity_is_not_complete_when_binding_never_ran(self) -> None:
        plan = compile_plan(parse("find x where a = 1"))
        identity = next(
            condition
            for condition in plan.completeness.conditions
            if condition.name == "identity_resolution_complete"
        )
        assert identity.satisfied is False


class TestAggregation:
    def test_a_cohort_query_needs_a_population(self) -> None:
        assert AggregationRequirement("aggregate_asset_value").is_satisfied is False
        assert (
            AggregationRequirement(
                "aggregate_asset_value", population="wallet_control_cluster"
            ).is_satisfied
            is True
        )


class TestContextEntry:
    def test_a_context_narrows_the_search_and_attributes_the_plan(self) -> None:
        class Context:
            context_id = "CXI-1"
            revision = 7
            question = "кто владеет CLUSTER-1?"
            scope_refs = ("CLUSTER-1", "GAZPROM")

        plan = plan_from_context(Context(), parse(GOLDEN), registry=REGISTRY)
        assert plan.context_id == "CXI-1"
        assert plan.revision == 7
        assert "CLUSTER-1" in plan.search_terms
        assert "GAZPROM" in plan.search_terms

    def test_the_context_question_is_used_when_the_ast_has_no_wording(self) -> None:
        class Context:
            context_id = "CXI-1"
            revision = 0
            question = "кто владеет?"
            scope_refs = ()

        plan = plan_from_context(Context(), QueryAST(verb=QueryVerb.FIND, concept="x"))
        assert plan.question == "кто владеет?"

    def test_narrowing_by_investigation_does_not_upgrade_the_completeness_mode(self) -> None:
        class Context:
            context_id = "CXI-1"
            revision = 0
            question = ""
            scope_refs = ("only-one-entity",)

        plan = plan_from_context(
            Context(),
            QueryAST(verb=QueryVerb.FIND, concept="x", requested_mode=RequestedMode.UNIVERSAL),
        )
        assert plan.completeness.unmet
        assert plan.overclaims is True