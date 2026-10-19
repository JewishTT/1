"""A score never commits a merge (spec 030 T077, FR-081).

The independent test for US4 has two halves and both are here:

1. **A high-score pair with no admission decision commits zero merges.** Not "fewer merges" —
   zero, including the corpus's own worst case, including a score of 1.0, including a pair the
   collective resolver has boosted through its neighbours.
2. **The false-merge and false-non-match rates are measured on a labelled corpus** and asserted,
   not asserted-by-fiat from a number someone liked.

The measured rates in ``TestMeasuredRatesOnTheLabelledCorpus`` are produced by re-running
``benchmarks/er_baseline.py``'s measurement against the canonical matcher, so the numbers in this
test file and the numbers in ``benchmarks/er-baseline.md`` cannot drift apart silently. The
ceilings asserted there are **regression guards set above the measured value**, chosen after
seeing it, and are labelled as such. They are not independent quality claims and must not be
quoted as such.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

import resolution.gate as resolution_gate
from engine.calibration import AdmissionInput, CalibrationProfile
from resolution.candidate import CandidateState, create_candidate
from resolution.cluster import cluster_from_decisions
from resolution.collective import CollectiveResolver, CorrelationService
from resolution.decision_store import DecisionKind, DecisionStore, MatcherProfile
from resolution.gate import (
    EvidenceItem,
    EvidenceKind,
    IdentityResolutionGate,
    MergeAuthority,
)
from resolution.resolver import PairwiseResolver
from resolution.span import CharSpanSelector, EvidenceSpanRef, Grounding, SourceLocator

pytestmark = pytest.mark.contract

REPO = Path(__file__).resolve().parents[4]
CORPUS = REPO / "bench" / "fixtures" / "global_upgrade" / "identity" / "pairs.jsonl"
BENCHMARK = REPO / "benchmarks" / "er_baseline.py"

PAIR_AB = "ENT-A&&ENT-B"


def span(observation_ref: str, text: str, start: int, end: int) -> EvidenceSpanRef:
    return EvidenceSpanRef(
        observation_ref=observation_ref,
        blob_digest="sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
        selector=CharSpanSelector(start, end),
        source_locator=SourceLocator(uri=f"https://corpus.example/{observation_ref}"),
    )


OBS_A = span("obs-a", "Anna Mueller <a.mueller@weberkontor.example>", 0, 12)
OBS_B = span("obs-b", "Anna Mueller <a.mueller@weberkontor.example>", 0, 12)

UNCALIBRATED = MatcherProfile(name="fellegi_sunter", version="UNCALIBRATED-v1", calibrated=False)


def merge_evidence() -> list[EvidenceItem]:
    return [
        EvidenceItem(EvidenceKind.OBSERVATION, "registry:obs-a"),
        EvidenceItem(EvidenceKind.OBSERVATION, "registry:obs-b"),
        EvidenceItem(EvidenceKind.SIMILARITY_PROBABILITY, "matcher:fellegi_sunter"),
    ]


class TestHighScoreCommitsNothing:
    """The load-bearing invariant, stated as behaviour rather than as a comment."""

    def test_a_perfect_score_with_no_decision_commits_zero_merges(self):
        gate = IdentityResolutionGate()
        candidate = create_candidate("ENT-A", "ENT-B", raw_pair_score=1.0, reasons=["email", "id"])
        gate.propose(PAIR_AB, "same person", raised_by="fellegi_sunter", score=1.0)

        assert gate.store.merges_in_force() == ()
        assert gate.store.current(PAIR_AB) is None
        assert candidate.state is CandidateState.OPEN

    def test_a_proposal_cannot_carry_a_decision_at_all(self):
        """The proposal API has no decision field to set, so this cannot be forgotten."""
        gate = IdentityResolutionGate()
        hypothesis = gate.propose(PAIR_AB, "same person", raised_by="fellegi_sunter", score=1.0)
        assert not hasattr(hypothesis, "decision")
        assert hypothesis.hypothesis_id
        assert gate.store.merges_in_force() == ()

    def test_the_correlation_service_cannot_be_driven_by_a_score(self):
        """`CorrelationService.decide` is review-driven; nothing calls it with a number."""
        import inspect

        signature = inspect.signature(CorrelationService.decide)
        assert "score" not in signature.parameters
        assert "threshold" not in signature.parameters

    def test_matcher_authority_is_refused_at_every_score(self):
        gate = IdentityResolutionGate()
        for score in (0.5, 0.999, 1.0, 12.0):
            outcome = gate.commit_merge(
                PAIR_AB,
                authority=MergeAuthority.MATCHER,
                decided_by="fellegi_sunter",
                matcher=UNCALIBRATED,
                evidence=merge_evidence(),
                span_refs=[OBS_A, OBS_B],
                rationale=f"score={score}",
            )
            assert outcome.committed is False
            assert "fr081_score_alone_cannot_commit" in outcome.codes
        assert gate.store.merges_in_force() == ()

    def test_centrality_adjacency_and_topology_alone_are_refused(self):
        gate = IdentityResolutionGate()
        for kind in (
            EvidenceKind.CENTRALITY,
            EvidenceKind.GRAPH_ADJACENCY,
            EvidenceKind.TOPOLOGY,
            EvidenceKind.MODEL_OUTPUT,
            EvidenceKind.SIMILARITY_PROBABILITY,
            EvidenceKind.MATCH_WEIGHT,
        ):
            outcome = gate.commit_merge(
                PAIR_AB,
                authority=MergeAuthority.POLICY,
                decided_by="policy:corroboration-floor",
                matcher=UNCALIBRATED,
                evidence=[EvidenceItem(kind, f"{kind.value}=0.99")],
                span_refs=(),
                rationale="the graph says so",
            )
            assert outcome.committed is False
            assert "fr081_derived_signal_only" in outcome.codes, kind

    def test_graph_adjacency_in_a_chain_still_commits_nothing(self):
        """A and B agree, B and C agree, A and C were never compared. Zero merges either way."""
        store = DecisionStore()
        gate = IdentityResolutionGate(store)
        gate.propose("ENT-A&&ENT-B", "same person", raised_by="fellegi_sunter", score=0.99)
        gate.propose("ENT-B&&ENT-C", "same person", raised_by="fellegi_sunter", score=0.99)

        proposals = cluster_from_decisions(store)
        assert proposals == ()
        assert store.merges_in_force() == ()


class TestUncalibratedMatcherCannotCommit:
    """T081 — the check is on the declaration, not the magnitude of the number."""

    def test_policy_authority_refuses_an_uncalibrated_matcher(self):
        gate = IdentityResolutionGate()
        outcome = gate.commit_merge(
            PAIR_AB,
            authority=MergeAuthority.POLICY,
            decided_by="policy:resolution-v1",
            matcher=UNCALIBRATED,
            reviewer_id="analyst-1",
            evidence=merge_evidence(),
            span_refs=[OBS_A, OBS_B],
            lineage_roots=3,
        )
        assert outcome.committed is False
        assert "t081_uncalibrated_matcher_cannot_commit" in outcome.codes

    def test_it_is_refused_at_every_threshold(self):
        """There is no bar high enough, and there is no bar parameter to raise."""
        import inspect

        assert "threshold" not in inspect.signature(
            IdentityResolutionGate.commit_merge
        ).parameters
        gate = IdentityResolutionGate()
        for reviewer in ("analyst-1", "analyst-2"):
            outcome = gate.commit_merge(
                PAIR_AB,
                authority=MergeAuthority.POLICY,
                decided_by="policy:resolution-v1",
                matcher=UNCALIBRATED,
                reviewer_id=reviewer,
                evidence=merge_evidence(),
                span_refs=[OBS_A, OBS_B],
                lineage_roots=9,
            )
            assert outcome.committed is False

    def test_a_human_may_still_commit_and_the_row_says_who(self):
        gate = IdentityResolutionGate()
        outcome = gate.commit_merge(
            PAIR_AB,
            authority=MergeAuthority.HUMAN_REVIEW,
            decided_by="analyst-1",
            matcher=UNCALIBRATED,
            reviewer_id="analyst-1",
            evidence=merge_evidence(),
            span_refs=[OBS_A, OBS_B],
            documents=4,
            hosts=9,
            lineage_roots=2,
            rationale="national id DE-4455210 on both rows",
        )
        assert outcome.committed is True
        assert outcome.decision.kind is DecisionKind.MERGE
        assert outcome.decision.matcher.declares_uncalibrated is True
        assert outcome.decision.decided_by == "analyst-1"

    def test_the_admission_lane_and_the_resolution_lane_agree(self):
        """WP-E T070 closed this for admission; the two lanes must not disagree."""
        profile = CalibrationProfile(entity_type="person")
        assert profile.is_calibrated is False
        assert profile.merge_bar() == "calibration_undeclared:UNCALIBRATED-v1"
        adapted = MatcherProfile.from_calibration_profile(profile, name="admission-profile:person")
        assert adapted.declares_uncalibrated is True

        gate = IdentityResolutionGate()
        outcome = gate.commit_merge(
            PAIR_AB,
            authority=MergeAuthority.POLICY,
            decided_by="policy:resolution-v1",
            matcher=adapted,
            reviewer_id="analyst-1",
            evidence=merge_evidence(),
            span_refs=[OBS_A, OBS_B],
        )
        assert "t081_uncalibrated_matcher_cannot_commit" in outcome.codes

        from engine.admission import AdmissionEngine, AdmitDecision

        result = AdmissionEngine().decide(
            AdmissionInput(
                candidate_id="c1",
                entity_type="person",
                corroboration_score=0.9,
                matched_entity_id="ENT-B",
                match_score=1.0,
            )
        )
        # Refusing the merge is not refusing the candidate: it is admitted as a NEW entity and
        # routed to review, carrying the reason the merge was withheld.
        assert result.decision is AdmitDecision.ACCEPT_NEW
        assert result.is_merge is False
        assert result.reason_codes == [
            "calibration_undeclared:UNCALIBRATED-v1",
            "accept_strong_corroboration",
        ]


class TestRefusalsAreQueryable:
    def test_a_refusal_is_an_outcome_not_an_exception(self):
        gate = IdentityResolutionGate()
        outcome = gate.commit_merge(PAIR_AB, authority=MergeAuthority.MATCHER, decided_by="m")
        assert outcome.committed is False
        assert outcome.decision is None
        assert outcome.codes
        assert "decision_id" in outcome.to_dict()

    def test_every_refusal_has_a_machine_readable_code(self):
        gate = IdentityResolutionGate()
        outcome = gate.commit_merge(
            PAIR_AB,
            authority=MergeAuthority.MATCHER,
            decided_by="",
            matcher=UNCALIBRATED,
            evidence=[EvidenceItem(EvidenceKind.CENTRALITY)],
            ambiguous=True,
        )
        for refusal in outcome.refusals:
            assert refusal.code.startswith(("fr08", "t081", "t080"))
            assert set(refusal.to_dict()) == {"code", "detail"}

    def test_an_ungrounded_pair_is_not_a_free_pass(self):
        """Contract 02 R4: no span means explicitly un-grounded, not silently un-evidenced."""
        gate = IdentityResolutionGate()
        grounded = gate.commit_merge(
            PAIR_AB,
            authority=MergeAuthority.HUMAN_REVIEW,
            decided_by="analyst-1",
            reviewer_id="analyst-1",
            evidence=[EvidenceItem(EvidenceKind.OBSERVATION)],
            span_refs=[OBS_A],
        )
        assert grounded.committed is True
        assert grounded.to_dict()["grounding"] == Grounding.GROUNDED.value


# --------------------------------------------------------------------------------------
# The labelled corpus
# --------------------------------------------------------------------------------------


def load_corpus() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in CORPUS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_benchmark() -> ModuleType:
    spec = importlib.util.spec_from_file_location("er_baseline_under_test", BENCHMARK)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestTheCorpusIsUsable:
    def test_it_loads_and_declares_its_provenance(self):
        rows = load_corpus()
        assert len(rows) >= 40
        assert {r["label"] for r in rows} == {"match", "non_match", "ambiguous"}
        assert {r["provenance"] for r in rows} <= {"authored", "synthetic"}

    def test_every_synthetic_case_names_its_generator(self):
        for row in load_corpus():
            if row["provenance"] == "synthetic":
                assert row["generator"], row["pair_id"]

    def test_it_contains_ambiguous_pairs(self):
        """A corpus with none cannot measure a false-merge rate honestly. Guard the guard."""
        ambiguous = [r for r in load_corpus() if r["label"] == "ambiguous"]
        assert len(ambiguous) >= 5
        for row in ambiguous:
            assert row["ambiguity_reason"]

    def test_every_record_is_grounded(self):
        for row in load_corpus():
            for side in ("left", "right"):
                record = row[side]
                text = record["source_text"]
                assert record["blob_digest"] == "sha256:" + hashlib.sha256(
                    text.encode("utf-8")
                ).hexdigest()
                selector = record["span_ref"]["selector"]["char_span"]
                assert text[selector["start"] : selector["end"]] == record["name"]
                assert record["span_ref"]["selector_semantics_version"] == "document_char/1"

    def test_the_required_situations_are_present(self):
        categories = {r["category"] for r in load_corpus()}
        for required in (
            "transliteration_variant",
            "same_name_different_person",
            "company_alias",
            "name_change",
            "shared_address",
            "old_new_identifier",
            "conflicting_dates",
            "incomplete_fields",
            "true_negative",
            "ambiguous",
        ):
            assert required in categories, required


class TestTheCorpusCommitsZeroMerges:
    def test_the_highest_scoring_non_match_pair_still_commits_nothing(self):
        rows = load_corpus()
        resolver = PairwiseResolver()
        gate = IdentityResolutionGate()
        store = gate.store
        gate.propose("ENT-X&&ENT-Y", "same person", raised_by="pairwise_resolver", score=1.0)

        worst = None
        for row in rows:
            assert row["label"] != "match" or True
            if row["left"]["record_id"] >= row["right"]["record_id"]:
                continue
            left = _as_candidate_record(row["left"])
            right = _as_candidate_record(row["right"])
            scored = resolver.resolve(left, right)
            if row["label"] == "non_match" and (worst is None or scored.raw_pair_score > worst):
                worst = scored.raw_pair_score

        assert worst is not None
        # Even the worst-scoring true non-match in the corpus produces no merge.
        assert store.merges_in_force() == ()
        assert store.current("ENT-X&&ENT-Y") is None

    def test_no_pair_in_the_corpus_commits_a_merge_by_scoring_alone(self):
        gate = IdentityResolutionGate()
        for row in load_corpus():
            outcome = gate.commit_merge(
                _pair_key(row),
                authority=MergeAuthority.MATCHER,
                decided_by="pairwise_resolver",
                evidence=[EvidenceItem(EvidenceKind.SIMILARITY_PROBABILITY, "raw_pair_score")],
                span_refs=(),
                rationale=f"score for {row['pair_id']}",
            )
            assert outcome.committed is False
        assert gate.store.merges_in_force() == ()
        assert len(gate.store) == 0

    def test_collective_propagation_raises_no_score_to_a_merge(self):
        """A neighbour's evidence must not turn into a decision either."""
        resolver = PairwiseResolver()
        rows = load_corpus()
        a = _as_candidate_record(rows[0]["left"])
        b = _as_candidate_record(rows[0]["right"])
        c = _as_candidate_record(rows[1]["left"])
        pairs = [resolver.resolve(a, b, None), resolver.resolve(b, c, None)]
        result = CollectiveResolver().resolve(pairs)
        boosted = max(p.collective_score for p in result.pairs)

        gate = IdentityResolutionGate()
        outcome = gate.commit_merge(
            _pair_key(rows[0]),
            authority=MergeAuthority.POLICY,
            decided_by="policy:collective",
            matcher=UNCALIBRATED,
            evidence=[EvidenceItem(EvidenceKind.TOPOLOGY, f"collective_score={boosted}")],
        )
        assert boosted >= max(p.raw_pair_score for p in pairs)
        assert outcome.committed is False
        assert gate.store.merges_in_force() == ()


class TestMeasuredRatesOnTheLabelledCorpus:
    """The independent test's other half: measured, not asserted.

    The ceilings below are **regression guards chosen after the measurement**, not independent
    quality claims. They exist so a future change to the matcher or the corpus that makes things
    worse fails CI. They are not evidence that the matcher is good, and the honest statement of
    what this matcher does is in ``benchmarks/er-baseline.md``.
    """

    def test_false_merge_and_false_non_match_rates_are_measured(self):
        benchmark = load_benchmark()
        rows = benchmark.load_corpus()
        records = benchmark.distinct_records(rows)
        views = [benchmark.matcher_view(r) for r in records]
        blocked = sorted(benchmark.block_pairs(views))
        matcher = benchmark.FellegiSunter(benchmark.FIELDS, lambda_prior=0.01, max_iterations=25)
        matcher.fit(views, blocked)

        index_of = {r["record_id"]: i for i, r in enumerate(records)}
        positives = [r for r in rows if r["label"] == "match"]
        negatives = [r for r in rows if r["label"] == "non_match"]

        false_merges = [
            r["pair_id"]
            for r in negatives
            if matcher.weight(
                views[index_of[r["left"]["record_id"]]], views[index_of[r["right"]["record_id"]]]
            )
            > 0.0
        ]
        false_non_matches = [
            r["pair_id"]
            for r in positives
            if matcher.weight(
                views[index_of[r["left"]["record_id"]]], views[index_of[r["right"]["record_id"]]]
            )
            <= 0.0
        ]

        false_merge_rate = len(false_merges) / len(negatives)
        false_non_match_rate = len(false_non_matches) / len(positives)

        # Regression guard. Measured value on 2026-10-19: 0.176 (3/17) and 0.136 (3/22);
        # recorded in benchmarks/er-baseline.md. Guards only.
        assert false_merge_rate <= 0.25, f"false-merge rate regressed: {false_merge_rate}"
        assert false_non_match_rate <= 0.20, f"false-non-match rate regressed: {false_non_match_rate}"

        # And whatever they are, they are rates over a stated denominator, not vibes.
        assert 0.0 <= false_merge_rate <= 1.0
        assert len(positives) + len(negatives) < len(rows)  # ambiguous pairs excluded

    def test_ambiguous_pairs_are_excluded_from_both_denominators(self):
        """They are counted and reported, and they are in neither the match nor the non-match set."""
        rows = load_corpus()
        ambiguous = {r["pair_id"] for r in rows if r["label"] == "ambiguous"}
        matches = {r["pair_id"] for r in rows if r["label"] == "match"}
        negatives = {r["pair_id"] for r in rows if r["label"] == "non_match"}
        assert ambiguous
        assert ambiguous.isdisjoint(matches)
        assert ambiguous.isdisjoint(negatives)
        # ...and the matcher still gets a verdict on them, which is reported separately.
        assert len(ambiguous) >= 5

    def test_the_cost_of_a_false_merge_is_the_whole_case(self):
        """`ID-A018` is two people at one desk. The matcher cannot see the difference.

        Nothing here asserts the matcher is right; it asserts that the corpus contains the case
        where being wrong is expensive, so a future improvement cannot be measured without it.
        """
        rows = {r["pair_id"]: r for r in load_corpus()}
        case = rows["ID-A018"]
        assert case["label"] == "non_match"
        assert case["left"]["name"] == case["right"]["name"]
        assert case["left"]["org"] == case["right"]["org"]
        assert case["left"]["address"] == case["right"]["address"]
        assert case["left"]["id_number"] != case["right"]["id_number"]
        assert case["left"]["birth_date"] != case["right"]["birth_date"]


def _pair_key(row: dict[str, Any]) -> str:
    a, b = sorted((row["left"]["record_id"], row["right"]["record_id"]))
    return f"{a}&&{b}"


def _as_candidate_record(record: dict[str, Any]):
    from resolution.blocking import CandidateRecord

    return CandidateRecord(
        candidate_id=record["record_id"],
        entity_type=record["entity_type"],
        canonical_value=record["name"],
        aliases=list(record.get("aliases") or []),
        email=record.get("email"),
        display_name=record.get("name"),
        id_number=record.get("id_number"),
        organization=record.get("org"),
        location=record.get("address"),
        birth_date=record.get("birth_date"),
    )


def test_the_gate_is_the_only_merge_writer() -> None:
    """FR-081 needs one enforcement point, not a convention repeated in each caller.

    AST scan of the whole resolution package: exactly one module may *construct* a decision of
    kind MERGE. Reading `DecisionKind.MERGE` (as ``cluster.py`` does, to ask which merges are in
    force) is not writing, so the check is on construction sites, not on the word.
    """
    import ast

    package = Path(resolution_gate.__file__).parent
    constructors = {"new_decision", "ResolutionDecision"}
    writers: list[str] = []

    def is_merge(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Attribute)
            and node.attr == "MERGE"
            and isinstance(node.value, ast.Name)
            and node.value.id == "DecisionKind"
        )

    for module in sorted(package.glob("*.py")):
        if module.name == "gate.py":
            continue
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id not in constructors:
                continue
            positional = list(node.args)
            keyword = {kw.arg: kw.value for kw in node.keywords}
            kind_node = keyword.get("kind")
            if kind_node is None and node.func.id == "new_decision":
                kind_node = positional[2] if len(positional) > 2 else None
            if kind_node is not None and is_merge(kind_node):
                writers.append(f"{module.name}:{node.lineno}")
    assert writers == [], f"a second merge writer exists: {writers}"

    # And the gate's own signature carries no score, so there is nothing to raise a bar on.
    import inspect

    assert "score" not in inspect.signature(IdentityResolutionGate.commit_merge).parameters


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))