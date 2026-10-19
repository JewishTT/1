"""The science → contract `OperatorResult` bridge (FR-014, WP2/F1).

Two types shared one name. The bridge is only useful if it is *strictly* honest about
the difference, so these tests pin three things:

* the parts it can map, map correctly — determinism to replay class, deferral to a
  non-success status;
* the parts the science result cannot supply are **required arguments**, so a caller
  without a tenant or an artifact gets a refusal, not a blank;
* the contract's own validation still fires through the bridge, which is the proof
  that the bridge did not paper over a missing digest with a placeholder.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

_APPS = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_APPS / "shared"))
sys.path.insert(0, str(_APPS / "science"))

from context.operators.base import Determinism
from context.operators.base import OperatorResult as ScienceResult
from context.operators.contract_bridge import replay_mode_for, to_operator_result
from contracts.operator_result import (
    OperatorIdentity,
    OperatorInputs,
    OperatorOutput,
    OperatorResultError,
    ReplayMode,
)
from contracts.stage_outcome import StageStatus

pytestmark = pytest.mark.contract

STARTED = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
COMPLETED = datetime(2026, 10, 19, 12, 0, 4, tzinfo=UTC)

IDENTITY = OperatorIdentity(
    operator_id="science.relation_strength",
    operator_version="2.1.0",
    tenant_id="tenant-a",
    investigation_id="inv-1",
    policy_fingerprint="sha256:" + "a" * 64,
)

INPUTS = OperatorInputs(
    input_observation_ids=("OB-1", "OB-2"),
    input_digests=("sha256:" + "b" * 64, "sha256:" + "c" * 64),
    semantic_profile_ref="ontology-pack@rev-7",
)

OUTPUT = OperatorOutput(
    output_kind="relation_strength",
    output_schema_version="2.1.0",
    output_digest="sha256:" + "d" * 64,
    artifact_refs=("artifact://relation_strength/1",),
    # A strength aggregate is derived from accepted claims, not from raw bytes, so it
    # carries no EvidenceSpanRef of its own. The contract requires that to be declared
    # rather than left to look grounded.
    derives_from_raw_content=False,
)


def _science(determinism: Determinism = Determinism.EXACT, **overrides) -> ScienceResult:
    payload = {
        "operator_id": "science.relation_strength",
        "operator_version": "2.1.0",
        "determinism": determinism,
        "value": {"strength": 0.82},
        "dependency_fingerprint": "sha256:" + "e" * 64,
        "method_fingerprint": "sha256:" + "f" * 64,
    }
    payload.update(overrides)
    return ScienceResult(**payload)


# ---------------------------------------------------------------------------
# Determinism → replay class
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("determinism", "expected"),
    [
        (Determinism.EXACT, ReplayMode.DETERMINISTIC),
        (Determinism.FIXED_POINT, ReplayMode.DETERMINISTIC),
        (Determinism.FLOAT_QUANTIZED, ReplayMode.DETERMINISTIC),
        (Determinism.NON_DETERMINISTIC, ReplayMode.RESULT_REPLAY),
    ],
)
def test_every_determinism_level_has_a_replay_class(determinism, expected) -> None:
    assert replay_mode_for(determinism) is expected


def test_an_unknown_determinism_level_is_refused() -> None:
    with pytest.raises(OperatorResultError):
        replay_mode_for("probabilistic-ish")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# The conversion
# ---------------------------------------------------------------------------


def test_a_deterministic_result_becomes_a_deterministic_contract_result() -> None:
    manifest = to_operator_result(
        _science(),
        identity=IDENTITY,
        inputs=INPUTS,
        output=OUTPUT,
        started_at=STARTED,
        completed_at=COMPLETED,
        parameters={"min_support": 2},
        missingness=("derived from accepted claims, not raw bytes",),
    )

    assert manifest.status is StageStatus.SUCCEEDED
    assert manifest.method.deterministic is True
    assert manifest.method.replay_mode is ReplayMode.DETERMINISTIC
    assert manifest.method.method_fingerprint == "sha256:" + "f" * 64
    assert manifest.identity.tenant_id == "tenant-a"
    assert manifest.output.output_digest == OUTPUT.output_digest


def test_a_non_deterministic_result_declares_result_replay() -> None:
    manifest = to_operator_result(
        _science(Determinism.NON_DETERMINISTIC),
        identity=IDENTITY,
        inputs=INPUTS,
        output=OUTPUT,
        started_at=STARTED,
        completed_at=COMPLETED,
        missingness=("derived from accepted claims, not raw bytes",),
        model_fingerprint="model://llm/relation-strength/2026-09",
    )

    assert manifest.method.replay_mode is ReplayMode.RESULT_REPLAY
    assert manifest.method.deterministic is False, (
        "a result that cannot be recomputed must not be described as deterministic, whatever "
        "the caller wants"
    )


def test_a_deferred_result_is_blocked_and_carries_its_reason() -> None:
    manifest = to_operator_result(
        _science(deferred=True, deferral_reason="Temporal is not reachable"),
        identity=IDENTITY,
        inputs=INPUTS,
        output=OperatorOutput(
            output_kind="relation_strength",
            output_schema_version="2.1.0",
            derives_from_raw_content=False,
        ),
        started_at=STARTED,
    )

    assert manifest.status is StageStatus.BLOCKED
    assert manifest.binding_limit == "Temporal is not reachable"
    assert "Temporal is not reachable" in manifest.warnings


def test_deferral_cannot_wear_a_success_status() -> None:
    """A success status without a digest is refused by the contract, through the bridge."""
    with pytest.raises(OperatorResultError):
        to_operator_result(
            _science(deferred=True, deferral_reason="not yet"),
            identity=IDENTITY,
            inputs=INPUTS,
            output=OperatorOutput(
            output_kind="relation_strength",
            output_schema_version="2.1.0",
            derives_from_raw_content=False,
        ),
            started_at=STARTED,
            status=StageStatus.SUCCEEDED,
        )


def test_the_replay_key_is_stable_and_ignores_the_wall_clock() -> None:
    first = to_operator_result(
        _science(),
        identity=IDENTITY,
        inputs=INPUTS,
        output=OUTPUT,
        started_at=STARTED,
        completed_at=COMPLETED,
        parameters={"min_support": 2},
        missingness=("derived from accepted claims, not raw bytes",),
    )
    later = to_operator_result(
        _science(),
        identity=IDENTITY,
        inputs=INPUTS,
        output=OUTPUT,
        started_at=datetime(2026, 10, 20, 3, 0, tzinfo=UTC),
        completed_at=datetime(2026, 10, 20, 3, 0, 4, tzinfo=UTC),
        parameters={"min_support": 2},
        missingness=("derived from accepted claims, not raw bytes",),
    )

    assert first.method.replay_key == later.method.replay_key, (
        "the same logical run at a different time is the same run; a replay ledger keyed on "
        "execution time deduplicates nothing"
    )


def test_changed_parameters_change_the_replay_key() -> None:
    first = to_operator_result(
        _science(), identity=IDENTITY, inputs=INPUTS, output=OUTPUT,
        started_at=STARTED, parameters={"min_support": 2},
        missingness=("derived from accepted claims, not raw bytes",),
    )
    second = to_operator_result(
        _science(), identity=IDENTITY, inputs=INPUTS, output=OUTPUT,
        started_at=STARTED, parameters={"min_support": 3},
        missingness=("derived from accepted claims, not raw bytes",),
    )

    assert first.method.replay_key != second.method.replay_key
    assert first.method.parameters_fingerprint != second.method.parameters_fingerprint


def test_the_bridge_requires_the_context_the_science_type_lacks() -> None:
    """Tenant, inputs and artifact are keyword-only and mandatory by signature."""
    with pytest.raises(TypeError):
        to_operator_result(  # type: ignore[call-arg]
            _science(),
            inputs=INPUTS,
            output=OUTPUT,
            started_at=STARTED,
        )


def test_a_caller_without_an_artifact_cannot_claim_success() -> None:
    with pytest.raises(OperatorResultError):
        to_operator_result(
            _science(),
            identity=IDENTITY,
            inputs=INPUTS,
            output=OperatorOutput(
                output_kind="relation_strength",
                output_schema_version="2.1.0",
                output_digest="sha256:" + "d" * 64,
                artifact_refs=(),
            ),
            started_at=STARTED,
            completed_at=COMPLETED,
        )
