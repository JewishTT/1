"""Unit tests: scope guard refused before any math + audit (T108, US3).

Every person-sensitive outcome class is hard-excluded by the single shared
guard (FR-007/SC-005). Rejections are structural: they happen before the
caller computes anything, and always produce a ``science.causal.scope_rejected``
audit envelope carrying the policy reference.
"""

from __future__ import annotations

import pytest

from causal.model import CausalModel
from causal.scope import FORBIDDEN_CLASSES, ensure_scoped
from errors import ScopeBoundaryError


class CaptureProducer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, object, str | None]] = []

    def produce(self, topic, envelope, key=None, **kwargs) -> None:
        self.sent.append((topic, envelope, key))


class TestScopeGuard:
    @pytest.mark.parametrize("outcome", sorted(FORBIDDEN_CLASSES))
    def test_forbidden_class_refused_before_math(self, outcome: str) -> None:
        producer = CaptureProducer()
        computed = []
        with pytest.raises(ScopeBoundaryError):
            ensure_scoped(outcome, entry_point="test", actor="t", producer=producer)
            computed.append(True)  # never reached
        assert computed == []
        assert [env.event_type for _t, env, _k in producer.sent] == [
            "science.causal.scope_rejected"
        ]
        payload = producer.sent[0][1].payload.decode()
        assert "scope-boundary.md" in payload.split("policy")[1]

    @pytest.mark.parametrize(
        "attribute",
        ["political views of a person", "his involvement in illegal activity", "an individual's marginalized-group membership"],
    )
    def test_person_phrasing_refused(self, attribute: str) -> None:
        with pytest.raises(ScopeBoundaryError):
            ensure_scoped(attribute, entry_point="test")

    @pytest.mark.parametrize(
        "attribute",
        ["transmission_rate", "network_density", "cascading_failure_latency", "motif_count"],
    )
    def test_structural_attributes_pass(self, attribute: str) -> None:
        ensure_scoped(attribute, entry_point="test")  # no raise

    def test_forbidden_class_cannot_be_declared_in_model(self) -> None:
        with pytest.raises(ScopeBoundaryError):
            CausalModel(
                model_id="bad@1.0",
                graph={},
                confounders=[],
                assumptions=[],
                scope_decl={"marginalized-group-membership"},
            )