"""Contract tests: causal classification + scope boundary (T107, US3).

Tests-first for ``apps/science/causal/*`` per interface-contracts §5 and
contracts/scope-boundary.md: without a model classification is CORRELATIONAL
with confounders; with a declared model (which owns the outcome and controls
named confounders) it is CAUSAL; person-sensitive outcomes are refused before
any computation and produce a scope-rejection audit event.
"""

from __future__ import annotations

import pytest

from causal.infer import classify
from causal.model import CausalLabel, CausalModel
from claims.model import EvidenceDirection, EvidenceLink
from errors import ScopeBoundaryError


class CaptureProducer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, object, str | None]] = []

    def produce(self, topic, envelope, key=None, **kwargs) -> None:
        self.sent.append((topic, envelope, key))


def _evidence(*ids: str) -> list[EvidenceLink]:
    return [
        EvidenceLink(
            link_id=f"L-{oid}",
            observation_id=oid,
            raw_sha256=f"sha256:{oid}",
            direction=EvidenceDirection.SUPPORTS,
            weight=0.6,
        )
        for oid in ids
    ]


class TestClassify:
    def test_without_model_is_correlational_with_confounders(self) -> None:
        producer = CaptureProducer()
        conclusion = classify(
            _evidence("OBS-1", "OBS-2"),
            None,
            outcome_attribute="transmission_rate",
            producer=producer,
        )
        assert conclusion.label == CausalLabel.CORRELATIONAL
        assert conclusion.model_ref is None
        assert isinstance(conclusion.possible_confounders, list)
        assert [env.event_type for _t, env, _k in producer.sent] == [
            "science.causal.classified"
        ]

    def test_declared_model_yields_causal(self) -> None:
        model = CausalModel(
            model_id="transmission-graph@1.0",
            graph={"density": [], "transmission_rate": ["density", "connectivity"]},
            confounders=["density"],
            assumptions=["no unobserved common cause of density and transmission"],
            scope_decl={"transmission_rate"},
        )
        producer = CaptureProducer()
        conclusion = classify(
            _evidence("OBS-1"),
            model,
            outcome_attribute="transmission_rate",
            producer=producer,
        )
        assert conclusion.label == CausalLabel.CAUSAL
        assert conclusion.model_ref == "transmission-graph@1.0"
        assert conclusion.controlled_confounders == ["density"]
        assert conclusion.assumptions

    def test_forbidden_model_scope_rejected_at_creation(self) -> None:
        with pytest.raises(ScopeBoundaryError):
            CausalModel(
                model_id="bad@1.0",
                graph={},
                confounders=[],
                assumptions=[],
                scope_decl={"political-affiliation"},
            )

    def test_person_sensitive_outcome_refused_before_math(self) -> None:
        producer = CaptureProducer()
        with pytest.raises(ScopeBoundaryError):
            classify(
                _evidence("OBS-1"),
                None,
                outcome_attribute="illegal-activity-involvement",
                producer=producer,
            )
        kinds = [env.event_type for _t, env, _k in producer.sent]
        assert "science.causal.scope_rejected" in kinds
        assert "science.causal.classified" not in kinds  # nothing was computed


class TestCausalConclusion:
    def test_conclusion_id_prefix_and_fields(self) -> None:
        conclusion = classify(_evidence("OBS-1"), None, outcome_attribute="transmission_rate")
        assert conclusion.conclusion_id.startswith("CS-")
        assert len(conclusion.evidence_links) == 1