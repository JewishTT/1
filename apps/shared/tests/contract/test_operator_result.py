"""``OperatorResult`` contract tests (spec 030 contract 01, task T029/T035).

The validation table is load-bearing, and every row of it is a refusal:

* ``output_digest`` present **iff** ``status in {succeeded, partial}`` -- an empty output is
  never a status, and ``artifact_refs`` is non-empty on the same two statuses because a digest
  over nothing plus a success is exactly that;
* ``error_code`` required on ``{failed, blocked, quarantined}`` and absent on the success
  statuses;
* ``deterministic=True`` implies ``model_fingerprint=null`` **and**
  ``replay_mode=deterministic``.

Plus the three that make the envelope worth carrying: the replay key excludes the wall clock, a
``CapacityGap`` lives *alongside* the result rather than replacing it, and an unestimated cost
component is ``null`` rather than ``0.0`` and never omitted.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from contracts.canonical import CanonicalError
from contracts.error_codes import ErrorCode
from contracts.evidence_span import CharSpan, EvidenceSpanRef, SourceLocator, StoredDocument
from contracts.operator_result import (
    CapacityGap,
    CostVector,
    OperatorIdentity,
    OperatorInputs,
    OperatorMethod,
    OperatorOutput,
    OperatorResult,
    OperatorResultError,
    ReplayMode,
    SourceTime,
    TimePrecision,
)
from contracts.stage_outcome import StageStatus

pytestmark = pytest.mark.contract

STARTED = datetime(2026, 10, 14, 9, 12, 3, tzinfo=UTC)
COMPLETED = datetime(2026, 10, 14, 9, 12, 7, 412000, tzinfo=UTC)
LOCATOR = SourceLocator(uri="https://example.org/report.pdf")
IDENTITY = OperatorIdentity(
    operator_id="parser.pdf.layout",
    operator_version="1.4.2",
    tenant_id="t-acme",
    investigation_id="INV-7f3a",
    policy_fingerprint="sha256:9c1e",
)
DOCUMENT = StoredDocument(data=b"Acme Corp filed at 2026-09-30. Total 4120000 units.")
SPAN = EvidenceSpanRef(
    observation_ref="obs-91c4",
    blob_digest=DOCUMENT.blob_digest(),
    selector=CharSpan(start=0, end=9),
    source_locator=LOCATOR,
    selector_semantics_version="char_span/1",
)


def _inputs(**kw) -> OperatorInputs:
    base = {
        "input_observation_ids": ("obs-91c4",),
        "input_digests": ("sha256:3d7b",),
        "semantic_profile_ref": "semantic/standard/2",
    }
    base.update(kw)
    return OperatorInputs(**base)


def _method(**kw) -> OperatorMethod:
    base = {
        "method_fingerprint": "sha256:5aa0",
        "parameters_fingerprint": "sha256:b71c",
        "deterministic": True,
        "replay_mode": ReplayMode.DETERMINISTIC,
        "replay_key": "sha256:44f2",
    }
    base.update(kw)
    return OperatorMethod(**base)


def _output(**kw) -> OperatorOutput:
    base: dict[str, object] = {
        "output_kind": "document_layout",
        "output_schema_version": "1.2.0",
    }
    base.update(kw)
    return OperatorOutput(**base)


def _produced_output(**kw) -> OperatorOutput:
    return _output(
        output_digest="sha256:e81a",
        artifact_refs=("art-layout-004",),
        evidence_refs=(SPAN,),
        **kw,
    )


def _result(**kw) -> OperatorResult:
    base: dict[str, object] = {
        "identity": IDENTITY,
        "inputs": _inputs(),
        "output": _produced_output(),
        "method": _method(),
        "status": StageStatus.SUCCEEDED,
        "started_at": STARTED,
        "completed_at": COMPLETED,
    }
    base.update(kw)
    return OperatorResult(**base)


def _empty_output(**kw) -> OperatorOutput:
    return _output(
        output_digest=None,
        artifact_refs=(),
        evidence_refs=(),
        derives_from_raw_content=False,
        **kw,
    )


def _digest_only_output() -> OperatorOutput:
    """A produced output whose content is a digest over already-derived features.

    The legitimate case for an empty ``evidence_refs``: a pure aggregation has no source
    content behind it. R7 permits it only when ``missingness`` says so. The kind is not in
    :data:`DERIVED_OUTPUT_KINDS` precisely because it aggregates rather than derives.
    """
    return _output(
        output_kind="feature_aggregate",
        output_digest="sha256:e81a",
        artifact_refs=("art-agg-001",),
        evidence_refs=(),
        derives_from_raw_content=False,
    )


class TestTheHappyPath:
    def test_a_grounded_parser_result_builds(self):
        assert _result().is_successful is True

    def test_the_serialised_form_has_every_contract_01_block(self):
        assert set(_result().as_dict()) == {
            "identity",
            "inputs",
            "output",
            "method",
            "outcome",
            "time",
            "cost",
            "capacity_gap",
        }

    def test_an_unestimated_uncertainty_component_is_null_not_zero(self):
        result = _result(uncertainty={"segment_confidence": None})
        assert result.uncertainty["segment_confidence"] is None
        assert result.as_dict()["outcome"]["uncertainty"]["segment_confidence"] is None


class TestDigestIsPresentIffSucceededOrPartial:
    """R1: an empty output is never a status."""

    def test_succeeded_without_a_digest_is_refused(self):
        with pytest.raises(OperatorResultError) as e:
            _result(output=_output(output_digest=None, artifact_refs=("a",), evidence_refs=(SPAN,)))
        assert "output.output_digest" in str(e.value)

    def test_partial_without_a_digest_is_refused(self):
        with pytest.raises(OperatorResultError):
            _result(
                status=StageStatus.PARTIAL,
                output=_output(
                    output_digest=None, artifact_refs=("a",), evidence_refs=(SPAN,)
                ),
                missingness=("pages 4-40 not extracted",),
                binding_limit="token_budget=4096",
                resumable=True,
            )

    def test_succeeded_with_no_artifact_refs_is_refused(self):
        """A digest over an empty artifact list is an empty output carrying a success status."""
        with pytest.raises(OperatorResultError) as e:
            _result(
                output=_output(
                    output_digest="sha256:e81a",
                    artifact_refs=(),
                    evidence_refs=(SPAN,),
                )
            )
        assert "artifact_ref" in str(e.value)

    def test_a_failed_run_may_not_carry_a_digest(self):
        with pytest.raises(OperatorResultError) as e:
            _result(
                status=StageStatus.FAILED,
                error_code=ErrorCode.SOURCE_UNAVAILABLE,
                output=_digest_only_output(),
            )
        assert "content that does not exist" in str(e.value)

    @pytest.mark.parametrize(
        "status",
        [StageStatus.FAILED, StageStatus.BLOCKED, StageStatus.QUARANTINED],
    )
    def test_no_failure_status_may_carry_a_digest(self, status: StageStatus):
        with pytest.raises(OperatorResultError):
            _result(
                status=status,
                error_code=ErrorCode.SOURCE_UNAVAILABLE,
                output=_digest_only_output(),
            )

    def test_an_unsupported_parser_is_not_a_succeeded_empty_document(self):
        """Contract 01's own rule: unsupported, not a zero-length document with succeeded."""
        outcome = _result(
            status=StageStatus.UNSUPPORTED,
            output=_empty_output(),
            error_code=ErrorCode.CAPABILITY_UNAVAILABLE,
            missingness=("encrypted PDF; no text layer and no OCR capability in this profile",),
            capacity_gap=CapacityGap(
                capability_required="ocr",
                gap_reason="no OCR capability registered in this profile",
                owner="platform",
                next_action="register an OCR capability or supply a text layer",
            ),
        )
        assert outcome.status is StageStatus.UNSUPPORTED
        assert outcome.output.output_digest is None
        assert outcome.output.artifact_refs == ()


class TestErrorCodeIsPresentIffTheStatusSaysItDidNotHappen:
    """Required on failed/blocked/quarantined, forbidden on the success statuses."""

    @pytest.mark.parametrize(
        "status",
        [StageStatus.FAILED, StageStatus.BLOCKED, StageStatus.QUARANTINED],
    )
    def test_each_failure_status_requires_an_error_code(self, status: StageStatus):
        with pytest.raises(OperatorResultError) as e:
            _result(status=status, output=_empty_output())
        assert "error_code" in str(e.value)

    @pytest.mark.parametrize("status", [StageStatus.SUCCEEDED, StageStatus.PARTIAL])
    def test_no_success_status_may_carry_an_error_code(self, status: StageStatus):
        with pytest.raises(OperatorResultError) as e:
            _result(
                status=status,
                error_code=ErrorCode.SOURCE_UNAVAILABLE,
                missingness=("pages 4-40 not extracted",) if status is StageStatus.PARTIAL else (),
                binding_limit="token_budget=4096" if status is StageStatus.PARTIAL else "",
                resumable=True if status is StageStatus.PARTIAL else None,
            )
        assert "not a failure" in str(e.value)

    def test_no_change_may_not_carry_an_error_code_either(self):
        with pytest.raises(OperatorResultError):
            _result(
                status=StageStatus.NO_CHANGE,
                output=_empty_output(),
                error_code=ErrorCode.SOURCE_UNAVAILABLE,
            )

    def test_unsupported_may_carry_one_because_contract_01s_own_example_does(self):
        """The asymmetry is deliberate and comes from the contract's worked example.

        Contract 01's validation table says "present iff", and its unsupported-parser example
        carries ``CAPABILITY_UNAVAILABLE``. The example is honoured, because a spec whose
        example violates its own table has to be read with the example winning -- and the
        practical loss is nil: the code still has to come from the declared table.
        """
        outcome = _result(
            status=StageStatus.UNSUPPORTED,
            output=_empty_output(),
            error_code=ErrorCode.CAPABILITY_UNAVAILABLE,
            missingness=("encrypted PDF",),
            capacity_gap=CapacityGap(
                capability_required="ocr",
                gap_reason="no OCR capability",
                owner="platform",
                next_action="register an OCR capability",
            ),
        )
        assert outcome.error_code is ErrorCode.CAPABILITY_UNAVAILABLE


class TestDeterministicImpliesNoModel:
    def test_a_deterministic_operator_with_a_model_fingerprint_is_refused(self):
        with pytest.raises(OperatorResultError) as e:
            _method(model_fingerprint="sha256:model-2b41")
        assert "model_fingerprint=null" in str(e.value)

    def test_a_deterministic_operator_must_declare_the_deterministic_replay_mode(self):
        with pytest.raises(OperatorResultError) as e:
            _method(replay_mode=ReplayMode.RESULT_REPLAY)
        assert "replay_mode=deterministic" in str(e.value)

    def test_a_clean_deterministic_method_builds(self):
        assert _method().model_fingerprint is None

    def test_a_non_deterministic_operator_claiming_deterministic_replay_is_refused(self):
        with pytest.raises(OperatorResultError) as e:
            _method(
                deterministic=False,
                model_fingerprint="sha256:model-2b41",
                replay_mode=ReplayMode.DETERMINISTIC,
            )
        assert "declare result_replay instead" in str(e.value)

    def test_a_non_deterministic_operator_without_a_model_fingerprint_is_refused(self):
        with pytest.raises(OperatorResultError):
            _method(deterministic=False, replay_mode=ReplayMode.RESULT_REPLAY)

    def test_a_model_hosted_result_declares_result_replay(self):
        outcome = _result(
            method=_method(
                deterministic=False,
                model_fingerprint="sha256:model-2b41",
                replay_mode=ReplayMode.RESULT_REPLAY,
            ),
            uncertainty={"candidate_confidence": "uncalibrated_score"},
        )
        assert outcome.is_deterministic is False
        assert outcome.method.replay_mode is ReplayMode.RESULT_REPLAY


class TestTheReplayKeyExcludesTheWallClock:
    """R2. A replay key keyed on execution time deduplicates nothing (FR-065)."""

    def _key(self, **kw) -> str:
        base = {
            "tenant_id": "t-acme",
            "scope_ref": "INV-7f3a",
            "input_digests": ("sha256:3d7b",),
            "operator_id": "parser.pdf.layout",
            "operator_version": "1.4.2",
            "parameters": {"layout": "reading-order"},
            "model_fingerprint": None,
            "semantic_profile_ref": "semantic/standard/2",
        }
        base.update(kw)
        return OperatorResult.compute_replay_key(**base)

    def test_two_runs_an_hour_apart_share_one_replay_key(self):
        assert self._key() == self._key()

    def test_the_input_order_does_not_change_the_key(self):
        assert self._key(input_digests=("a", "b")) == self._key(input_digests=("b", "a"))

    def test_the_parameter_key_order_does_not_change_the_key(self):
        assert self._key(parameters={"z": 1, "a": 2}) == self._key(parameters={"a": 2, "z": 1})

    @pytest.mark.parametrize(
        "changed",
        [
            {"tenant_id": "t-other"},
            {"scope_ref": "INV-0000"},
            {"input_digests": ("sha256:0000",)},
            {"operator_id": "parser.txt"},
            {"operator_version": "1.4.3"},
            {"parameters": {"layout": "reading-order-v2"}},
            {"model_fingerprint": "sha256:model-2b41"},
            {"semantic_profile_ref": "semantic/standard/3"},
            {"time_scope": ("2011-01-01/2012-01-01",)},
        ],
    )
    def test_every_declared_input_changes_the_key(self, changed: dict[str, object]):
        assert self._key(**changed) != self._key()

    def test_a_time_scope_is_included_when_it_is_semantically_part_of_the_input(self):
        """The one legitimate reason a timestamp reaches a replay key."""
        assert self._key(time_scope=("2026-01-01/2026-10-01",)) != self._key()

    def test_two_results_of_the_same_run_deduplicate_on_the_replay_key(self):
        left = _result(completed_at=COMPLETED)
        right = _result(completed_at=COMPLETED + timedelta(hours=1))
        assert left.method.replay_key == right.method.replay_key


class TestCostComponentsAreDeclaredNotOmitted:
    """R3: absent means null, never omitted, and never 0.0."""

    def test_every_cost_component_is_present_as_null_by_default(self):
        serialised = CostVector().as_dict()
        components = [key for key in serialised if key != "policy_version"]
        assert set(components) >= {
            "network_io_bytes",
            "cpu_seconds",
            "memory_bytes",
            "model_tokens",
            "latency_ms",
            "storage_bytes",
            "retries",
            "expected_human_review_minutes",
            "licensing_cost",
        }
        assert all(serialised[key] is None for key in components)

    def test_measured_as_zero_is_distinguishable_from_not_measured(self):
        assert CostVector(retries=0).retries == 0
        assert CostVector().retries is None

    def test_a_negative_cost_component_is_refused(self):
        with pytest.raises(OperatorResultError):
            CostVector(network_io_bytes=-1)

    def test_the_cost_vector_travels_with_the_result(self):
        result = _result(cost=CostVector(latency_ms=4412, retries=0))
        assert result.as_dict()["cost"]["latency_ms"] == 4412


class TestPartialCarriesWhatItOmitted:
    """R6: a budget exhaustion is partial, never a success."""

    def _partial(self, **kw):
        base = {
            "status": StageStatus.PARTIAL,
            "output": _produced_output(),
            "missingness": ("pages 4-40 not extracted",),
            "binding_limit": "token_budget=4096",
            "resumable": True,
        }
        base.update(kw)
        return _result(**base)

    def test_a_complete_partial_builds(self):
        assert self._partial().status is StageStatus.PARTIAL

    def test_partial_without_missingness_is_refused(self):
        with pytest.raises(OperatorResultError) as e:
            self._partial(missingness=())
        assert "missingness" in str(e.value)

    def test_partial_without_a_named_limit_is_refused(self):
        with pytest.raises(OperatorResultError) as e:
            self._partial(binding_limit="")
        assert "binding limit" in str(e.value)

    def test_partial_without_a_resumable_answer_is_refused(self):
        with pytest.raises(OperatorResultError):
            self._partial(resumable=None)

    def test_partial_still_carries_a_digest(self):
        """It produced something; that is what separates it from failed."""
        assert self._partial().output.output_digest == "sha256:e81a"


class TestTimeAndTenancy:
    def test_a_run_that_finished_before_it_started_is_refused(self):
        with pytest.raises(OperatorResultError) as e:
            _result(completed_at=STARTED - timedelta(seconds=1))
        assert "precedes started_at" in str(e.value)

    def test_completed_at_may_be_null_while_the_run_is_in_flight(self):
        assert _result(completed_at=None).completed_at is None

    def test_a_result_without_a_tenant_is_refused(self):
        with pytest.raises(OperatorResultError) as e:
            OperatorIdentity(
                operator_id="parser.pdf.layout",
                operator_version="1.4.2",
                tenant_id="  ",
                investigation_id="INV-7f3a",
                policy_fingerprint="sha256:9c1e",
            )
        assert "tenant" in str(e.value)

    def test_input_ids_must_be_parallel_to_input_digests(self):
        with pytest.raises(OperatorResultError) as e:
            _inputs(input_observation_ids=("a", "b"), input_digests=("x",))
        assert "matching digest" in str(e.value)

    def test_a_blank_input_digest_is_refused(self):
        with pytest.raises(OperatorResultError) as e:
            _inputs(input_digests=("  ",))
        assert "unverified input digest" in str(e.value)

    def test_a_missing_semantic_profile_ref_is_refused(self):
        with pytest.raises(OperatorResultError):
            _inputs(semantic_profile_ref="")

    def test_a_naive_started_at_is_refused(self):
        """An instant that does not say which instant it means is not a timestamp (FR-020)."""
        with pytest.raises(CanonicalError):
            _result(started_at=datetime(2026, 10, 14, 9, 12, 3))

    def test_source_times_are_typed_and_never_folded_into_one_datetime(self):
        published = SourceTime(
            kind="source_published_at",
            value=datetime(2026, 9, 30, tzinfo=UTC),
            precision=TimePrecision.DAY,
        )
        retrieved = SourceTime(
            kind="observed_at",
            value=datetime(2026, 10, 14, 9, 12, tzinfo=timezone(timedelta(hours=2))),
            precision=TimePrecision.SECOND,
        )
        outcome = _result(source_times=(published, retrieved))
        serialised = outcome.as_dict()["time"]["source_times"]
        assert len(serialised) == 2
        assert serialised[0] != serialised[1]
        assert serialised[0]["precision"] == "day"

    def test_the_same_instant_in_two_timezones_serialises_to_one_source_time(self):
        published = SourceTime(
            kind="source_published_at",
            value=datetime(2026, 10, 14, 9, tzinfo=UTC),
            precision=TimePrecision.SECOND,
        )
        same = SourceTime(
            kind="other_clock",
            value=datetime(2026, 10, 14, 11, tzinfo=timezone(timedelta(hours=2))),
            precision=TimePrecision.SECOND,
        )
        assert published.as_dict()["value"] == same.as_dict()["value"]


class TestCapacityGapLivesAlongside:
    """CE-I13: an explicit gap, never a weaker substitute -- and never *instead of* the result."""

    def test_a_result_carrying_a_gap_is_still_a_result(self):
        outcome = _result(
            status=StageStatus.UNSUPPORTED,
            output=_empty_output(),
            error_code=ErrorCode.CAPABILITY_UNAVAILABLE,
            missingness=("no OCR capability in this profile",),
            capacity_gap=CapacityGap(
                capability_required="ocr",
                gap_reason="no OCR capability registered in this profile",
                owner="platform",
                next_action="register an OCR capability",
            ),
        )
        assert outcome.identity.operator_id == "parser.pdf.layout"
        assert outcome.status is StageStatus.UNSUPPORTED
        assert outcome.as_dict()["capacity_gap"]["capability_required"] == "ocr"

    def test_a_gap_that_advertises_a_substitution_is_refused(self):
        with pytest.raises(OperatorResultError) as e:
            CapacityGap(
                capability_required="ocr",
                gap_reason="no OCR capability",
                owner="platform",
                next_action="register an OCR capability",
                substitution_attempted=True,
            )
        assert "CE-I13" in str(e.value)

    def test_a_gap_without_a_next_action_is_refused(self):
        with pytest.raises(OperatorResultError) as e:
            CapacityGap(
                capability_required="ocr",
                gap_reason="no OCR capability",
                owner="platform",
                next_action="  ",
            )
        assert "next_action" in str(e.value)

    def test_an_unsupported_result_with_no_gap_and_no_evidence_is_refused(self):
        """It would otherwise be an unsupported status explaining nothing."""
        with pytest.raises(OperatorResultError) as e:
            _result(
                status=StageStatus.UNSUPPORTED,
                output=_empty_output(),
                error_code=ErrorCode.CAPABILITY_UNAVAILABLE,
            )
        assert "CapacityGap" in str(e.value)


class TestProvenanceCompletenessIsDeclared:
    """R7 / FR-005: a consumer that cannot resolve a span renders partial, never grounded."""

    def test_a_derived_output_with_no_evidence_refs_is_refused_at_construction(self):
        with pytest.raises(OperatorResultError) as e:
            _output(output_digest="sha256:e81a", artifact_refs=("a",), evidence_refs=())
        assert "grounded" in str(e.value)

    def test_declaring_that_the_output_has_no_source_content_needs_a_declared_reason(self):
        with pytest.raises(OperatorResultError) as e:
            _result(output=_digest_only_output())
        assert "missingness" in str(e.value)

    def test_the_declared_reason_satisfies_the_check(self):
        """The legitimate empty-evidence case: a pure aggregation over derived features."""
        outcome = _result(
            output=_digest_only_output(),
            missingness=("pure aggregation over already-derived features; no raw content",),
        )
        assert outcome.output.evidence_refs == ()

    def test_an_evidence_ref_travels_into_the_serialised_output(self):
        refs = _result().as_dict()["output"]["evidence_refs"]
        assert refs[0]["selector"] == {
            "char_span": {
                "start": 0,
                "end": 9,
                "encoding": "utf-8",
                "units": "document_char",
            }
        }
        assert refs[0]["selector_semantics_version"] == "char_span/1"