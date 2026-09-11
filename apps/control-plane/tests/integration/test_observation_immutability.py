"""Invariant test: observation immutability (T019, I-1, SC-002).

The observation model rejects any mutation of immutable fields once recorded.
Uses an in-memory store to keep the invariant check hermetic (no live stack).
"""

import importlib.util
from pathlib import Path

import pytest

# Load the SHARED domain (invariants, I-1) under a distinct module name so it
# never occupies `sys.modules['domain']`: control-plane ships its own top-level
# `domain` package (investigation/policy), and both are top-level names. This
# keeps the two packages from colliding within one interpreter.
_shared_domain_path = Path(__file__).resolve().parents[4] / "apps" / "shared" / "domain" / "__init__.py"
_spec = importlib.util.spec_from_file_location("shared_domain_invariants", _shared_domain_path)
assert _spec and _spec.loader
_shared_domain = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_shared_domain)

ObservationImmutableError = _shared_domain.ObservationImmutableError
enforce_observation_immutable = _shared_domain.enforce_observation_immutable


class _ObservationRepo:
    """Minimal immutable observation store used for the invariant test."""

    def __init__(self) -> None:
        self._rows: dict[str, dict] = {}

    def create(self, observation_id: str, uri: str, tenant_id: str) -> dict:
        row = {
            "observation_id": observation_id,
            "uri": uri,
            "tenant_id": tenant_id,
            "status": "created",
            "duplicate": False,
            "provenance": {"version": 1},
        }
        self._rows[observation_id] = row
        return row

    def update(self, observation_id: str, patch: dict) -> dict:
        existing = self._rows.get(observation_id)
        if not existing:
            raise KeyError(observation_id)
        # Enforce I-1: immutable fields cannot be patched.
        enforce_observation_immutable(existing, patch)
        # Allowed operational fields.
        for k, v in patch.items():
            existing[k] = v
        return existing


@pytest.mark.integration
class TestObservationImmutability:
    def test_create_then_immutable_uri_rejected(self) -> None:
        repo = _ObservationRepo()
        repo.create("OBS-1", "http://fixtures.local/index.html", "tenant-1")
        with pytest.raises(ObservationImmutableError):
            repo.update("OBS-1", {"uri": "http://fixtures.local/different.html"})

    def test_sha_content_ref_immutable(self) -> None:
        repo = _ObservationRepo()
        repo.create("OBS-2", "http://x", "t")
        with pytest.raises(ObservationImmutableError):
            repo.update("OBS-2", {"content_hash": "deadbeef"})

    def test_operational_status_update_allowed(self) -> None:
        repo = _ObservationRepo()
        repo.create("OBS-3", "http://x", "t")
        updated = repo.update("OBS-3", {"status": "unchanged"})
        assert updated["status"] == "unchanged"

    def test_duplicate_flag_update_allowed(self) -> None:
        repo = _ObservationRepo()
        repo.create("OBS-4", "http://x", "t")
        updated = repo.update("OBS-4", {"duplicate": True})
        assert updated["duplicate"] is True

    def test_immutable_error_code_is_i1(self) -> None:
        repo = _ObservationRepo()
        repo.create("OBS-5", "http://x", "t")
        with pytest.raises(ObservationImmutableError, match="I-1"):
            repo.update("OBS-5", {"uri": "http://mutated"})