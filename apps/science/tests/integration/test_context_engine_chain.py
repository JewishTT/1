"""End-to-end: every context-engine layer exercised in one pass.

This is the assembly test. Each layer has its own contract suite, and a suite cannot
say whether the pieces work *together* -- so this walks one investigation through the
whole chain and asserts on what comes out:

    §33  intent + completeness   -> what may be claimed
    §13  truth + contradiction   -> what is believed, and what disagrees
    §14A independence            -> how many sources actually count
    §7   cells + growth           -> where the evidence lives, and at what depth
    §9/§10 compatibility+gluing  -> whether the cells agree, pairwise and jointly
    §15/§18 dialectics           -> which rival explanations survive, and why
    §20.3 ranking                -> which next action is defensible
    §22  saturation              -> whether it is finished, and what is missing

The chain is the point. A verdict produced by `gluing` that ignores independence is
not a wrong verdict, it is a wrong kind of verdict; the property pinned at the end --
no clean conclusion without declared coverage -- is exactly the property that
per-layer suites cannot see.

Everything runs through the operator registry rather than by direct import, so a
layer that stops being selectable fails here even if its own tests pass.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from context.argumentation import Candidate, GainTier
from context.completeness import (
    CompletenessMode,
    Objective,
    QueryIntent,
    RequestedMode,
    ResultSet,
    Target,
    UniverseDefinition,
)
from context.coverage import (
    CoverageQualifiedAbsence,
    assess_independence,
    assess_saturation,
)
from context.dialectics import (
    Exhaustive,
    Hypothesis,
    HypothesisSpace,
    SteelmanParity,
)
from context.epistemic import (
    ContradictionKind,
    EvidenceContribution,
    Proposition,
    TruthState,
    contradiction_for_both,
    derive_truth_state,
)
from context.locality import (
    CellKind,
    ContextCell,
    Scope,
    descendants_of,
)
from context.operators.adapters import build_default_registry
from context.operators.base import Tier
from context.operators.compatibility import assess_pair

pytestmark = [pytest.mark.integration, pytest.mark.contract]

CTX = "CXI-crypto-whales"
REGISTRY = build_default_registry()
PARITY = SteelmanParity(
    same_evidence_view=True,
    same_template_family=True,
    same_complexity_bound=True,
    same_assumption_budget=True,
)


def _cell(members: list[str], parent: str = "") -> ContextCell:
    return ContextCell(
        context_id=CTX,
        kind=CellKind.ORGANIZATION,
        scope=Scope.entity(*members),
        parent_cell=parent,
        produced_by="growth.extend_cells@1.0",
        method_fingerprint="mf-growth",
    )


def _run(capability: str, payload, parameters=None, *, tier: Tier = Tier.STATISTICAL):
    """Every layer goes through the registry, so selectability is part of the test."""
    selection = REGISTRY.select(required=frozenset({capability}), max_tier=tier)
    assert selection.ok, f"{capability}: {selection.gap}"
    return selection.registration.operator.run(payload, parameters, seed=0).value


class TestAppendixCCanonicalQuery:
    """The spec's canonical example, run end to end through every layer."""

    def test_the_whole_chain_produces_an_honest_answer(self) -> None:
        # -- §32/§33 what was asked, and what may be claimed ------------------
        intent = QueryIntent(
            objective=Objective.IDENTIFY_COHORT,
            target=Target("wallet_control_cluster", "aggregate_asset_value", 1_000_000, "USD"),
            question="find all crypto whales with >= $1M",
            identity_requirement="CONTROL_CLUSTER",
            allow_unresolved=True,
            evidence_requirements={"balance_sources_min": 1, "attribution_sources_min": 0},
            requested_mode=RequestedMode.UNIVERSAL,
        )
        assert intent.intent_id.startswith("QIN-")

        # 200 outlets republished one press release; three registries are independent.
        registry_items = ["EV-reg1", "EV-reg2", "EV-reg3"]
        items = [f"EV-{index}" for index in range(200)] + registry_items
        lineage = {
            f"EV-{index}": "OBS-press-release" for index in range(200)
        }
        lineage.update(
            {"EV-reg1": "OBS-reg-a", "EV-reg2": "OBS-reg-b", "EV-reg3": "OBS-reg-c"}
        )
        independence = _run("n_eff", (items, lineage), tier=Tier.DETERMINISTIC)
        assert independence.raw_count == 203
        assert independence.n_eff == 4.0  # 200 copies = 1, plus 3 registries

        # -- §13 what is believed, and what disagrees -------------------------
        proposition = Proposition(
            subject="WALLET-A",
            predicate="controls",
            object="CLUSTER-1",
            scope=CTX,
            temporal_qualifier="2026-Q1",
        )
        truth = derive_truth_state(
            [
                EvidenceContribution("EV-reg1", positive=True),
                EvidenceContribution("EV-press", positive=True),
                EvidenceContribution("EV-reg2", positive=False),
            ]
        )
        assert truth is TruthState.BOTH
        conflict = contradiction_for_both(
            proposition.with_truth(truth),
            positive_refs=["EV-reg1", "EV-press"],
            negative_refs=["EV-reg2"],
            independent=True,
            kind=ContradictionKind.SUPPORT,
        )
        assert conflict is not None
        assert {side["side"] for side in conflict.sides} == {"supporting", "refuting"}

        # -- §7 where the evidence lives ---------------------------------------
        root = _cell(["CLUSTER-1"])
        growth = _run(
            "cell_creation",
            (CTX, (root,), {"O-reg": Scope.entity("CLUSTER-1", "WALLET-A")}),
            {"revealed_by": {"O-reg": root.cell_id}},
            tier=Tier.DETERMINISTIC,
        )
        assert len(growth.created) == 1
        assert len(descendants_of(root.cell_id, growth.cells)) == 1

        deep = _cell(["CLUSTER-1", "WALLET-A", "SIGNER-1"], root.cell_id)
        assert deep.ancestry({c.cell_id: c for c in growth.cells}) == (
            root.cell_id,
            deep.cell_id,
        )

        # -- §9/§10 do the cells agree, pairwise and jointly? -----------------
        assessment = assess_pair(root, deep, overlap_id="OVL-1")
        assert assessment.blocking_dimensions == ()

        # A second member cell of the same cluster, so the overlap graph holds a
        # triangle: cluster cell plus two member cells that each share CLUSTER-1.
        rival = _cell(["CLUSTER-1", "WALLET-B"], root.cell_id)
        gluing = _run(
            "triple_coherence",
            ([root, deep, rival], CTX),
            {"max_triples": 100},
            tier=Tier.DETERMINISTIC,
        )
        assert gluing.triples_checked >= 1
        assert gluing.verdict.value in {"glued", "partially_glued", "blocked"}
        # Every obstruction explains itself, whatever the verdict.
        assert all(item.detail for item in gluing.obstructions)

        # -- §15/§18 which rival explanations survive --------------------------
        thesis = Hypothesis(
            "WALLET-A controls CLUSTER-1 directly",
            local_id="LHYP-direct",
            posterior=0.4,
            assumptions=("registry is current", "no nominee"),
        )
        antithesis = Hypothesis(
            "CLUSTER-1 is controlled through nominee SPV-77",
            local_id="LHYP-nominee",
            posterior=0.25,
            assumptions=("registry is current", "nominee exists"),
        )
        space = HypothesisSpace(
            context_id=CTX,
            question="who controls CLUSTER-1?",
            members=(thesis, antithesis, Hypothesis.residual(0.35)),
            exclusivity_groups=(frozenset({"LHYP-direct", "LHYP-nominee"}),),
            exhaustive=Exhaustive.FALSE,
        )
        assert space.residual is not None

        dialectic = _run(
            "counter_hypothesis",
            (space, thesis),
            {"templates": (("nominee", antithesis),), "parity": PARITY},
            tier=Tier.DETERMINISTIC,
        )
        assert dialectic["outcome"].value == "generated"
        assert dialectic["pairs"][0].parity.is_parity

        # -- §20.3 which next action is defensible ------------------------------
        blocked = Candidate(
            "act-nominee-attribution",
            {"gain": 100.0},
            # The §49.3 inference policy blocks attribution to natural persons.
            policy_allowed=False,
        )
        allowed = Candidate(
            "act-pull-registry",
            {"gain": 1.0},
            gain_tier=GainTier.IG_PROBABILISTIC,
            gain_value=0.42,
        )
        ranking = _run("argumentation", [blocked, allowed], {"mode": "LEXICOGRAPHIC"},
                       tier=Tier.DETERMINISTIC)
        assert ranking["ranked"] == ["act-pull-registry"]

        # -- §22 is it finished, and what is missing ---------------------------
        saturation = _run(
            "saturation",
            ("OBL-control-cluster", independence),
            {"coverage": 0.6, "source_families": 3},
            tier=Tier.DETERMINISTIC,
        )
        assert saturation.verdict.value != "saturated"
        assert "insufficient_coverage" in [
            reason.value for reason in saturation.reason_codes
        ]

        # -- §33 what may finally be said ---------------------------------------
        completeness = _run(
            "universal_claim",
            (UniverseDefinition.REGISTERED_SOURCES, {}),
            tier=Tier.DETERMINISTIC,
        )
        assert completeness.feasible_mode is CompletenessMode.OPEN_WORLD_DISCOVERY

        result = ResultSet(
            observed_set=tuple(items[:3]),
            candidate_set=("WALLET-A", "WALLET-B"),
            resolved_set=("WALLET-A",),
            unresolved_set=("WALLET-B",),
            coverage_estimate=0.6,
            source_universe="registered chain sources",
            saturation_state=saturation.verdict.value,
            known_blind_spots=("off-chain wallets", "private relays"),
            completeness=completeness,
        )
        phrasing = result.phrasing()
        assert "declared coverage" in phrasing
        assert "open_world_discovery" in phrasing

    def test_no_clean_conclusion_without_declared_coverage(self) -> None:
        """The property per-layer suites cannot see.

        Any result that resolves something while coverage is unestablished must still
        say so in its own phrasing. A confident sentence here would be the single
        most damaging failure this engine could have.
        """
        for coverage, saturated in ((None, "unsaturated"), (0.1, "unsaturated"),
                                    (0.6, "unknown")):
            result = ResultSet(
                candidate_set=("E1", "E2"),
                resolved_set=("E1",),
                unresolved_set=("E2",),
                coverage_estimate=coverage,
                source_universe="registered",
                saturation_state=saturated,
            )
            assert "declared coverage" in result.phrasing()
            assert result.banner()["completeness_mode"]


class TestChainConsistency:
    def test_a_refused_contradiction_is_not_a_contradiction(self) -> None:
        """One-sided support must not produce an obstruction the engine acts on."""
        proposition = Proposition(subject="A", predicate="p", object="B", scope=CTX)
        one_sided = derive_truth_state([EvidenceContribution("E1", positive=True)])
        assert contradiction_for_both(proposition.with_truth(one_sided)) is None

    def test_independence_does_not_erase_support(self) -> None:
        """§14A rule 4: grouping changes scores, not whether support exists."""
        items = ["E1", "E2", "E3", "E4"]
        lineage = {item: "OBS-p" for item in items}
        assessment = assess_independence(items, lineage)
        assert assessment.n_eff == 1.0
        assert derive_truth_state(
            [EvidenceContribution(item, positive=True) for item in items]
        ) is TruthState.TRUE_ONLY

    def test_a_weak_absence_blocks_saturation(self) -> None:
        """A syndication cluster plus unknown coverage cannot close an obligation."""
        items = [f"EV-{index}" for index in range(50)]
        assessment = assess_independence(items, {item: "OBS-p" for item in items})
        saturation = assess_saturation(
            "OBL-1", assessment=assessment, coverage=None, source_families=4
        )
        assert saturation.verdict.value != "saturated"
        assert "insufficient_independence" in [
            reason.value for reason in saturation.reason_codes
        ]

    def test_every_layer_is_selectable_in_the_deterministic_core(self) -> None:
        """The honesty layers must not depend on a Tier 3 model being present."""
        for capability in (
            "n_eff",
            "saturation",
            "compatibility",
            "triple_coherence",
            "cell_creation",
            "counter_hypothesis",
            "argumentation",
            "universal_claim",
            "change_point",
        ):
            selection = REGISTRY.select(
                required=frozenset({capability}), max_tier=Tier.DETERMINISTIC
            )
            assert selection.ok, f"{capability} is not in the deterministic core"


class TestUniversalNegativeEndToEnd:
    def test_a_qualifying_absence_permits_the_strong_claim(self) -> None:
        """'None exist' requires declared coverage *and* detection power."""
        absence = CoverageQualifiedAbsence(
            context_id=CTX,
            query="registered SPV entry",
            sources=("reg-a", "reg-b", "reg-c"),
            coverage=0.95,
            detection_power=0.8,
            relevance="predicts the SPV is registered",
        )
        result = ResultSet(
            candidate_set=(),
            source_universe="registered company sources",
            qualified_absences=(absence,),
        )
        assert result.may_claim_universal_negative() is True

    def test_an_unqualified_absence_does_not(self) -> None:
        absence = CoverageQualifiedAbsence(
            context_id=CTX,
            query="registered SPV entry",
            sources=("reg-a",),
            coverage=None,
            detection_power=None,
            relevance="predicts the SPV is registered",
        )
        result = ResultSet(
            candidate_set=(),
            source_universe="registered company sources",
            qualified_absences=(absence,),
        )
        assert result.may_claim_universal_negative() is False
        assert result.phrasing() == "none observed under declared coverage"