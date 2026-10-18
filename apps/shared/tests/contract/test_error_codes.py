"""Error code and canonical-serialisation contract tests (spec 030 contract 07, task T031).

Three categories -- expected-negative / retryable / defect -- and the properties that make them
worth having:

* **a client parses a code, not a string**, so an undeclared code is refused rather than guessed;
* **cross-tenant access returns byte-identical shape to a genuinely-absent object** (FR-090).
  That indistinguishability is a security property, not a formatting detail, so it is asserted
  on the exact bytes that would leave the process;
* **errors carry no raw content and no secrets** (R3, FR-096) -- checked on field *names* and on
  value *shapes*, because either check alone is easy to walk past.

Canonical serialisation is pinned here because the cross-tenant guarantee is stated in terms of
bytes: "byte-identical" is only a checkable claim if the byte rendering is itself deterministic,
and that is what ``contracts.canonical`` provides -- stable key ordering, timestamps folded to
UTC, and no ``repr()`` or memory address anywhere on an identity-critical path.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from contracts.canonical import (
    CanonicalError,
    UnhashableForIdentity,
    canonical_bytes,
    canonical_json,
    canonicalize,
    digest_of,
    instant_text,
    normalize_instant,
)
from contracts.error_codes import (
    ABSENCE_CODES,
    CONTRACT_03_ONLY,
    CrossTenantIndistinguishabilityError,
    EmptyStateEnvelope,
    ErrorCategory,
    ErrorCode,
    ErrorEnvelope,
    ErrorSurfaceError,
    absence_envelope,
    cross_tenant_envelope,
    is_release_blocker,
    release_blocker_codes,
)

pytestmark = pytest.mark.contract


class TestEveryCodeHasExactlyOneCategory:
    """The three categories, never conflated. A code in none is a code nobody can handle."""

    def test_every_declared_code_is_classified(self):
        for code in ErrorCode:
            assert isinstance(code.category, ErrorCategory)

    def test_no_code_is_in_two_categories(self):
        """The property that is not visible in ``code.category`` and is therefore easy to break."""
        by_category: dict[ErrorCategory, set[ErrorCode]] = {}
        for code in ErrorCode:
            by_category.setdefault(code.category, set()).add(code)
        overlap = set.intersection(*by_category.values()) if len(by_category) > 1 else set()
        assert overlap == set()

    def test_a_defect_must_not_be_retryable(self):
        for code in ErrorCode:
            if code.category is ErrorCategory.DEFECT:
                assert code.is_retryable is False

    def test_an_expected_negative_must_not_be_retryable(self):
        for code in ErrorCode:
            if code.category is ErrorCategory.EXPECTED_NEGATIVE:
                assert code.is_retryable is False

    def test_retryable_codes_are_exactly_the_infrastructure_ones(self):
        retryable = {code for code in ErrorCode if code.is_retryable}
        assert ErrorCode.SOURCE_UNAVAILABLE in retryable
        assert ErrorCode.TIMEOUT in retryable
        assert ErrorCode.TRANSIENT_INFRA in retryable
        assert ErrorCode.POLICY_BLOCKED not in retryable
        assert ErrorCode.CAPABILITY_UNAVAILABLE not in retryable
        assert ErrorCode.REPLAY_MISMATCH not in retryable


class TestClientsParseCodesNotStrings:
    def test_a_declared_code_parses(self):
        assert ErrorCode.parse("POLICY_BLOCKED") is ErrorCode.POLICY_BLOCKED

    def test_an_undeclared_code_is_refused(self):
        with pytest.raises(ErrorSurfaceError) as e:
            ErrorCode.parse("SOMETHING_FAILED_BADLY")
        assert "not a declared error code" in str(e.value)

    def test_the_failure_carries_a_code_on_the_wire(self):
        wire = ErrorEnvelope(
            code=ErrorCode.SOURCE_UNAVAILABLE,
            ref_type="source",
            reason="connection reset by peer",
        ).as_wire()
        assert wire["error"]["code"] == "SOURCE_UNAVAILABLE"
        assert wire["error"]["category"] == "retryable_infra"

    def test_an_error_without_a_reason_is_refused(self):
        """'blocked' with nothing named is not an answer anybody can act on (R5)."""
        with pytest.raises(ErrorSurfaceError):
            ErrorEnvelope(code=ErrorCode.POLICY_BLOCKED, ref_type="investigation", reason="  ")

    def test_a_refusal_names_the_blocker(self):
        envelope = ErrorEnvelope(
            code=ErrorCode.BUDGET_EXHAUSTED,
            ref_type="investigation",
            reason="tenant retry budget exhausted at the tenant level",
        )
        assert "tenant" in envelope.reason


class TestCrossTenantIsByteIdenticalToAbsence:
    """FR-090: no distinguishable cross-tenant signal. This is a security property."""

    @pytest.mark.parametrize("ref_type", sorted(ABSENCE_CODES))
    def test_the_two_responses_are_byte_identical(self, ref_type: str):
        assert absence_envelope(ref_type).as_bytes() == cross_tenant_envelope(ref_type).as_bytes()

    def test_the_wire_json_is_identical_too_not_merely_the_dict(self):
        assert absence_envelope("context").as_json() == cross_tenant_envelope("context").as_json()

    def test_the_cross_tenant_code_is_not_distinguishable_on_the_wire(self):
        wire = cross_tenant_envelope("context").as_json()
        assert "TENANT_SCOPE_VIOLATION" not in wire
        assert absence_envelope("context").as_json() in wire

    def test_the_cross_tenant_response_echoes_no_identifier(self):
        """Echoing the reference would confirm it exists somewhere."""
        envelope = cross_tenant_envelope("context")
        assert "ctx-9f2a" not in envelope.as_json()
        assert "ctx-9f2a" not in envelope.reason

    def test_the_distinction_is_kept_off_the_wire_for_operators_only(self):
        envelope = cross_tenant_envelope("context")
        assert envelope.internal_reason
        assert "internal_reason" not in envelope.as_wire()["error"]

    def test_asking_for_a_distinguishable_code_is_refused(self):
        """So a future 'just add a debug flag' cannot make this leak."""
        with pytest.raises(CrossTenantIndistinguishabilityError) as e:
            cross_tenant_envelope("context", code=ErrorCode.TENANT_SCOPE_VIOLATION)
        assert "existence oracle" in str(e.value)

    def test_tenancy_scope_violation_cannot_even_be_an_absence_code(self):
        with pytest.raises(CrossTenantIndistinguishabilityError):
            absence_envelope("context", code=ErrorCode.TENANT_SCOPE_VIOLATION)

    def test_a_ref_type_with_no_absence_code_is_refused_rather_than_defaulted(self):
        """Without a registered absence code the cross-tenant path could not be made
        indistinguishable, so the whole point is to fail here rather than at the wire."""
        with pytest.raises(ErrorSurfaceError) as e:
            absence_envelope("unicorn")
        assert "no absence code is registered" in str(e.value)


class TestNoRawContentOrSecretsInErrors:
    """R3 / FR-096. Errors carry identifiers, codes and reasons -- never payloads."""

    def test_a_payload_field_name_is_refused(self):
        with pytest.raises(ErrorSurfaceError) as e:
            ErrorEnvelope(
                code=ErrorCode.MALFORMED_INPUT,
                ref_type="observation",
                reason="decode failed",
                detail={"raw_body": "<html>..."},
            )
        assert "release blocker" in str(e.value)

    @pytest.mark.parametrize(
        "field",
        ["payload", "body", "raw", "content", "text", "snippet", "document", "secret"],
    )
    def test_every_payload_shaped_field_name_is_refused(self, field: str):
        with pytest.raises(ErrorSurfaceError):
            ErrorEnvelope(
                code=ErrorCode.PROJECTION_FAILED,
                ref_type="projection",
                reason="build failed",
                detail={field: "anything"},
            )

    @pytest.mark.parametrize(
        "value",
        [
            "Authorization: Bearer abc123",
            "-----BEGIN RSA PRIVATE KEY-----",
            "AKIAIOSFODNN7EXAMPLE",
            "password=hunter2",
        ],
    )
    def test_a_credential_shaped_value_is_refused_under_any_field_name(self, value: str):
        """The field name can be innocent; the value cannot."""
        with pytest.raises(ErrorSurfaceError) as e:
            ErrorEnvelope(
                code=ErrorCode.SOURCE_UNAVAILABLE,
                ref_type="source",
                reason="upstream refused",
                detail={"note": value},
            )
        assert "credential" in str(e.value)

    def test_a_secret_nested_two_levels_deep_is_still_caught(self):
        with pytest.raises(ErrorSurfaceError):
            ErrorEnvelope(
                code=ErrorCode.TRANSIENT_INFRA,
                ref_type="source",
                reason="dependency down",
                detail={"note": {"inner": ["sk-abcdefghijklmnopqrstuvwx"]}},
            )

    def test_a_reason_long_enough_to_be_a_payload_is_refused(self):
        with pytest.raises(ErrorSurfaceError) as e:
            ErrorEnvelope(
                code=ErrorCode.MALFORMED_INPUT,
                ref_type="observation",
                reason="x" * 500,
            )
        assert "payload" in str(e.value)


class TestAbsenceIsStatedNotImplied:
    """R4: a bare ``[]`` does not distinguish five different states."""

    def test_an_empty_state_must_state_its_coverage(self):
        with pytest.raises(ErrorSurfaceError) as e:
            EmptyStateEnvelope(
                status=ErrorCode.EXPECTED_NO_RESULT,
                coverage="",
                provenance="parser v2 over obs-1",
                limitations=(),
            )
        assert "coverage" in str(e.value)

    def test_an_empty_state_must_state_its_provenance(self):
        with pytest.raises(ErrorSurfaceError):
            EmptyStateEnvelope(
                status=ErrorCode.EXPECTED_NO_RESULT,
                coverage="3/3 declared sources searched",
                provenance="  ",
                limitations=(),
            )

    def test_a_complete_empty_state_serialises_its_four_parts(self):
        wire = EmptyStateEnvelope(
            status=ErrorCode.CAPABILITY_UNAVAILABLE,
            coverage="2 of 5 sources searched; 3 lack the required capability",
            provenance="web-search adapter v3 over obs-1..obs-3",
            limitations=("3 sources have no text layer",),
        ).as_wire()
        assert set(wire) == {"status", "category", "coverage", "provenance", "limitations"}


class TestReleaseBlockersAreNamed:
    def test_the_three_contract_07_release_blockers_are_flagged(self):
        flagged = {code for code in release_blocker_codes()}
        assert ErrorCode.IMMUTABLE_VIOLATION in flagged
        assert ErrorCode.DETECTION_POWER_UNKNOWN in flagged
        assert ErrorCode.REPLAY_MISMATCH in flagged

    def test_a_defect_must_be_reported_rather_than_degraded_to_a_valid_answer(self):
        """A degraded-but-valid answer is never returned where a defect occurred."""
        for code in ErrorCode:
            if code.category is ErrorCategory.DEFECT:
                assert code.must_degrade is True

    def test_is_release_blocker_agrees_with_the_property(self):
        for code in ErrorCode:
            assert is_release_blocker(code) is code.is_release_blocker

    def test_the_contract_03_codes_carry_a_category_too(self):
        """Both documents are normative; a failure from either must be classifiable."""
        for code in CONTRACT_03_ONLY:
            assert isinstance(code.category, ErrorCategory)


class TestCanonicalSerialisationIsStable:
    """Stable key ordering and normalised timestamps, at every level of nesting."""

    def test_two_equal_dicts_built_in_different_orders_produce_the_same_digest(self):
        first = {"b": 1, "a": 2, "c": {"z": [3, 2, 1], "y": {"q": 1, "p": 2}}}
        second = {"c": {"y": {"p": 2, "q": 1}, "z": [3, 2, 1]}, "a": 2, "b": 1}
        assert canonical_json(first) == canonical_json(second)
        assert digest_of(first) == digest_of(second)

    def test_key_ordering_is_stable_all_the_way_down_not_just_at_the_top(self):
        flat = {"x": {"b": 1, "a": 2}}
        nested = {"x": {"a": 2, "b": 1}}
        assert canonical_json(flat) == canonical_json(nested)

    def test_sequence_order_is_load_bearing_and_never_sorted(self):
        """A directed pair and a sequence of reads are not the same value."""
        assert canonical_json({"order": [1, 2]}) != canonical_json({"order": [2, 1]})

    def test_a_set_of_different_member_types_still_orders_deterministically(self):
        left = canonical_json({"s": {"b", "a", 3, 1}})
        right = canonical_json({"s": {1, 3, "a", "b"}})
        assert left == right

    def test_an_enum_member_canonicalises_as_its_value_not_its_repr(self):
        from enum import StrEnum

        class Kind(StrEnum):
            ONE = "one"

        assert canonical_json({"k": Kind.ONE}) == '{"k":"one"}'

    def test_a_dataclass_is_canonicalised_field_by_field(self):
        from dataclasses import dataclass

        @dataclass
        class Point:
            y: int
            x: int

        assert digest_of(Point(y=2, x=1)) == digest_of(Point(y=2, x=1))
        assert digest_of(Point(y=2, x=1)) != digest_of(Point(y=1, x=2))


class TestTimestampsAreNormalised:
    def test_the_same_instant_in_two_timezones_is_one_text(self):
        utc = datetime(2026, 10, 14, 9, 12, 3, tzinfo=UTC)
        plus_two = datetime(2026, 10, 14, 11, 12, 3, tzinfo=timezone(timedelta(hours=2)))
        assert instant_text(utc) == instant_text(plus_two)

    def test_the_same_instant_in_two_timezones_is_one_digest(self):
        utc = {"at": datetime(2026, 10, 14, 9, 12, 3, tzinfo=UTC)}
        plus_two = {"at": datetime(2026, 10, 14, 11, 12, 3, tzinfo=timezone(timedelta(hours=2)))}
        assert digest_of(utc) == digest_of(plus_two)

    def test_an_aware_datetime_is_folded_to_utc(self):
        plus_two = datetime(2026, 10, 14, 11, 12, 3, tzinfo=timezone(timedelta(hours=2)))
        assert normalize_instant(plus_two).tzinfo is UTC

    def test_a_naive_datetime_is_refused_not_assumed_to_be_utc(self):
        with pytest.raises(CanonicalError) as e:
            instant_text(datetime(2026, 10, 14, 9, 12, 3))
        assert "not an instant" in str(e.value)

    def test_a_naive_datetime_nested_in_a_payload_is_still_refused(self):
        with pytest.raises(CanonicalError):
            canonical_json({"range": {"from": datetime(2026, 1, 1)}})


class TestNoReprOrMemoryAddressReachesADigest:
    """The identity path has no ``str()`` fallback. That is the whole point of it."""

    def test_an_object_of_an_unknown_type_is_refused_rather_than_stringified(self):
        class Opaque:
            pass

        with pytest.raises(CanonicalError) as e:
            canonical_json({"payload": Opaque()})
        assert "no canonical form" in str(e.value)

    def test_a_class_with_a_hostile_repr_is_never_consulted(self):
        calls = 0

        class Hostile:
            def __repr__(self) -> str:
                nonlocal calls
                calls += 1
                return "<hostile 0xdeadbeef>"

        with pytest.raises(CanonicalError):
            canonical_json({"payload": Hostile()})
        assert calls == 0, "the identity path called repr() on a value it did not understand"

    def test_a_string_that_is_already_a_memory_address_is_refused(self):
        """The caller can pass an address as a string; the digest must still refuse it."""
        with pytest.raises(UnhashableForIdentity) as e:
            canonical_json({"ref": f"{id(object()):#x}"})
        assert "memory address" in str(e.value)

    def test_a_hex_address_of_the_zero_pad_form_is_refused_too(self):
        with pytest.raises(UnhashableForIdentity):
            canonical_json({"ref": f"0x{id(object()):016x}"})

    def test_an_address_nested_in_a_list_is_refused(self):
        with pytest.raises(UnhashableForIdentity):
            canonical_json({"refs": ["ok", "0x7f3a1c04d5e0"]})

    def test_two_objects_at_different_addresses_refuse_to_the_same_error(self):
        """If the error text carried the address, even the *error* would not be reproducible."""
        first, second = object(), object()
        with pytest.raises(UnhashableForIdentity) as e1:
            canonical_json({"ref": f"{id(first):#x}"})
        with pytest.raises(UnhashableForIdentity) as e2:
            canonical_json({"ref": f"{id(second):#x}"})
        assert str(e1.value) == str(e2.value)

    def test_a_normal_hex_digest_is_not_mistaken_for_an_address(self):
        """A content address is full of hex; refusing those would refuse every digest."""
        assert digest_of({"a": 1}).startswith("sha256:")
        assert canonical_json({"d": digest_of({"a": 1})}).startswith('{"d":"sha256:')

    def test_two_structurally_equal_payloads_have_equal_digests_regardless_of_identity(self):
        """``id()`` never appears, so two separately-allocated equal objects agree."""
        left = {"rows": [{"a": 1}, {"a": 2}]}
        right = {"rows": [{"a": 1}, {"a": 2}]}
        assert digest_of(left) == digest_of(right)
        assert canonical_bytes(left) == canonical_bytes(right)


class TestUnmeasurableIsNotZero:
    """R3: ``null`` with the key present, never ``0.0`` and never silently omitted."""

    def test_a_missing_and_a_measured_zero_are_different_digests(self):
        assert digest_of({"segment_confidence": None}) != digest_of({"segment_confidence": 0.0})

    def test_an_omitted_key_is_a_different_digest_from_a_null_one(self):
        assert digest_of({"a": None}) != digest_of({})

    def test_negative_zero_and_zero_are_one_number(self):
        assert digest_of({"x": -0.0}) == digest_of({"x": 0.0})

    def test_a_non_finite_quantity_is_refused(self):
        with pytest.raises(CanonicalError) as e:
            canonicalize({"x": float("nan")})
        assert "null" in str(e.value)


class TestTwoMappingKeysThatCollideAreRefused:
    def test_an_int_key_and_its_string_form_are_refused(self):
        with pytest.raises(CanonicalError) as e:
            canonical_json({"m": {1: "a", "1": "b"}})
        assert "would lose one of them" in str(e.value)