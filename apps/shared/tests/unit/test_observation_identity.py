"""Deterministic identity: the defect this suite pins was release blocker §160.

``observation_gate.py:74`` used to read ``"OBS-" + uuid.uuid4().hex[:12]``. Every
test here is written to fail against that implementation, because a suite that
passes on both a random and a deterministic id proves nothing about the defect it
claims to cover.
"""

from __future__ import annotations

import pytest

from domain.observation_identity import (
    IDENTITY_SCHEMA_V1,
    ObservationIdentity,
    ObservationIdentityError,
    event_id_for,
    observation_id_for,
    require_deterministic_event_id,
)

M = {
    "tenant_id": "acme",
    "capture_id": "CAP-" + "ab" * 16,
    "locator": "json:results[0]",
    "record_digest": "c" * 64,
}


class TestObservationIdentityIsDeterministic:
    def test_same_material_same_address(self):
        assert observation_id_for(**M) == observation_id_for(**M)

    def test_replay_reproduces_the_address(self):
        """§12: a replay of the same artifact yields the same observation_id."""
        first = observation_id_for(**M)
        second = observation_id_for(**M)
        assert first == second

    def test_address_has_the_canonical_prefix(self):
        assert observation_id_for(**M).startswith("OBS-")

    def test_address_body_is_a_128_bit_digest(self):
        body = observation_id_for(**M).removeprefix("OBS-")
        assert len(body) == 32
        assert all(c in "0123456789abcdef" for c in body)

    def test_distinct_processes_produce_the_same_address(self):
        """Subprocess isolation: no in-process cache could mask non-determinism."""
        import subprocess
        import sys

        code = (
            "import sys; sys.path.insert(0, r'apps/shared');"
            "from domain.observation_identity import observation_id_for;"
            f"print(observation_id_for(**{M!r}))"
        )
        out = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=True
        )
        assert out.stdout.strip() == observation_id_for(**M)

    def test_no_clock_or_random_source_in_the_module(self):
        """The defect was a random id; assert the sources are absent, not unused.

        Reads the *code*, not the text: this module names ``uuid4`` and
        ``datetime.now`` in its docstrings precisely because it explains what it
        removed, so a naive substring scan of the file would fail on the very
        documentation that justifies the fix.
        """
        import ast
        import pathlib

        tree = ast.parse(
            pathlib.Path("apps/shared/domain/observation_identity.py").read_text("utf-8")
        )
        banned = {"uuid", "random", "time"}
        called: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                called.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                called.add(node.module.split(".")[0])
            elif isinstance(node, ast.Attribute):
                called.add(node.attr)
        assert not (called & banned), f"{called & banned} is banned from identity (§11)"
        assert "datetime" not in called, "a clock in identity breaks the §12 replay invariant"


class TestObservationIdentityDiscriminates:
    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("tenant_id", "other"),
            ("capture_id", "CAP-" + "ff" * 16),
            ("locator", "json:results[1]"),
            ("record_digest", "d" * 64),
        ],
    )
    def test_every_component_changes_the_address(self, field, value):
        assert observation_id_for(**{**M, field: value}) != observation_id_for(**M)

    def test_same_record_in_two_streams_is_two_observations(self):
        """§34: identical JSON under different streams is two observed occurrences."""
        a = observation_id_for(**{**M, "capture_id": "CAP-" + "11" * 16})
        b = observation_id_for(**{**M, "capture_id": "CAP-" + "22" * 16})
        assert a != b

    def test_identity_schema_is_in_the_material(self):
        other = ObservationIdentity.for_record(
            **M, identity_schema="observation-identity/v2"
        ).observation_id
        assert other != observation_id_for(**M)
        assert IDENTITY_SCHEMA_V1 != "observation-identity/v2"

    def test_key_order_does_not_matter(self):
        shuffled = {k: M[k] for k in reversed(list(M))}
        assert observation_id_for(**shuffled) == observation_id_for(**M)


class TestObservationIdentityRefuses:
    @pytest.mark.parametrize(
        ("field", "code"),
        [
            ("tenant_id", "observation_tenant_missing"),
            ("capture_id", "observation_capture_id_missing"),
            ("locator", "observation_locator_missing"),
            ("record_digest", "observation_record_digest_missing"),
        ],
    )
    def test_missing_component_refuses_by_name(self, field, code):
        with pytest.raises(ObservationIdentityError) as exc:
            observation_id_for(**{**M, field: ""})
        assert exc.value.code == code

    def test_whitespace_is_not_a_value(self):
        with pytest.raises(ObservationIdentityError):
            observation_id_for(**{**M, "locator": "   "})

    def test_refusal_does_not_yield_an_address(self):
        """A malformed input must not produce a well-formed id meaning nothing."""
        try:
            observation_id_for(**{**M, "locator": ""})
        except ObservationIdentityError as exc:
            assert not exc.code.startswith("OBS-")
        else:
            pytest.fail("empty locator was accepted")

    def test_error_carries_a_closed_code(self):
        with pytest.raises(ObservationIdentityError) as exc:
            observation_id_for(**{**M, "locator": ""})
        assert exc.value.code in {
            "observation_locator_missing",
            "observation_record_digest_missing",
            "observation_capture_id_missing",
            "observation_tenant_missing",
        }


class TestIdentityVerifiesItself:
    def test_self_consistent_identity_verifies(self):
        ObservationIdentity.for_record(**M).verify()

    def test_tampered_address_raises(self):
        """Verify, do not trust - the discipline Capture.__post_init__ applies."""
        ident = ObservationIdentity.for_record(**M)
        tampered = ObservationIdentity(
            observation_id="OBS-" + "0" * 32,
            tenant_id=ident.tenant_id,
            capture_id=ident.capture_id,
            locator=ident.locator,
            record_digest=ident.record_digest,
        )
        with pytest.raises(ObservationIdentityError) as exc:
            tampered.verify()
        assert exc.value.code == "observation_id_mismatch"

    def test_material_is_recomputable(self):
        ident = ObservationIdentity.for_record(**M)
        from domain.relation_identity import digest128

        assert "OBS-" + digest128(ident.material) == ident.observation_id

    def test_to_dict_carries_the_address_material(self):
        d = ObservationIdentity.for_record(**M).to_dict()
        assert d["locator"] == M["locator"]
        assert d["identity_schema"] == IDENTITY_SCHEMA_V1


class TestEventIdentityIsDeterministic:
    E = {
        "event_type": "observation.created",
        "event_version": "2.0",
        "observation_id": observation_id_for(**M),
        "producer": "observation-gate",
        "producer_version": "0.1.0",
        "lifecycle": "created",
    }

    def test_same_components_same_event_id(self):
        assert event_id_for(**self.E) == event_id_for(**self.E)

    def test_event_id_has_the_evt_prefix(self):
        assert event_id_for(**self.E).startswith("evt-")

    @pytest.mark.parametrize("field", list(E))
    def test_every_component_changes_the_event_id(self, field):
        assert event_id_for(**{**self.E, field: "different"}) != event_id_for(**self.E)

    def test_lifecycle_is_part_of_the_address(self):
        """One observation, two points in its life, two events - they must differ."""
        assert event_id_for(**{**self.E, "lifecycle": "changed"}) != event_id_for(**self.E)

    def test_producer_is_part_of_the_address(self):
        """Two producers reading one capture must not share an address (§68)."""
        assert event_id_for(**{**self.E, "producer": "searxng"}) != event_id_for(**self.E)

    def test_no_clock_in_event_identity(self):
        import inspect

        src = inspect.getsource(event_id_for)
        for banned in ("now(", "time.", "uuid"):
            assert banned not in src, f"{banned} would break the §12 replay invariant"


class TestEventIdGuard:
    def test_content_address_passes(self):
        eid = event_id_for(**TestEventIdentityIsDeterministic.E)
        assert require_deterministic_event_id(eid) == eid

    def test_bare_32_hex_digest_is_accepted_and_prefixed(self):
        bare = "a" * 32
        assert require_deterministic_event_id(bare) == "evt-" + bare

    def test_empty_refuses(self):
        with pytest.raises(ObservationIdentityError) as exc:
            require_deterministic_event_id("")
        assert exc.value.code == "event_id_not_deterministic"

    def test_uuid_shaped_id_refuses(self):
        """§160: a random event id for a replay-sensitive event is a blocker."""
        with pytest.raises(ObservationIdentityError) as exc:
            require_deterministic_event_id("f47ac10b-58cc-4372-a567-0e02b2c3d479")
        assert exc.value.code == "event_id_not_deterministic"

    def test_legacy_gate_shape_refuses(self):
        """The old f'evt-{sha256}-{lifecycle}' form is not a §11 content address."""
        with pytest.raises(ObservationIdentityError):
            require_deterministic_event_id(f"evt-{'a' * 64}-created")
