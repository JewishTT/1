from __future__ import annotations

import pytest

from services.zero_layer import ZeroLayerCaseError, ZeroLayerCaseService


def test_published_idempotency_reservation_replays_saved_response() -> None:
    response = {
        "case_id": "case-1",
        "run_id": "ZLR-run-1",
        "captured_pages": 2,
        "observation_refs": ["OBS-1", "OBS-2"],
        "result_role": "DISCOVERY_ONLY",
        "claim_admission_allowed": False,
    }
    reservation = {
        "created": False,
        "state": "PUBLISHED",
        "payload": {"outcome": {"response": response}},
    }

    replayed = ZeroLayerCaseService._cached_idempotent_response(reservation)

    assert replayed is not None
    assert replayed["replayed"] is True
    assert replayed["observation_refs"] == ["OBS-1", "OBS-2"]
    assert replayed["claim_admission_allowed"] is False


def test_reserved_idempotency_key_never_authorizes_a_second_fetch() -> None:
    reservation = {
        "created": False,
        "state": "RESERVED",
        "payload": {"request_digest": "sha256:abc"},
    }

    with pytest.raises(ZeroLayerCaseError, match="duplicate collection is refused"):
        ZeroLayerCaseService._cached_idempotent_response(reservation)


def test_new_idempotency_reservation_continues_to_execute() -> None:
    assert ZeroLayerCaseService._cached_idempotent_response({"created": True}) is None
