"""The gate itself: §160's ``observation_id random`` blocker, pinned behaviourally.

These tests read the gate's *behaviour*, not its source text. That distinction was
learned the hard way: a source-scan test for ``uuid4`` passes with the defect
reintroduced, because a docstring mentioning ``uuid4()`` satisfies a substring
check. So every test here calls the gate twice and asserts the two runs agree -
which is the property §12 actually requires, and which a random id cannot have.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from events.observation_gate import CAPTURE_LOCATOR, ObservationGate


class _Router:
    """Minimal ContentRouter stand-in: one content type, one digest."""

    def classify(self, body: bytes, url: str = "", headers: dict | None = None) -> dict:
        import hashlib

        return {
            "content_type": "application/json",
            "sha256": hashlib.sha256(body).hexdigest(),
        }


class _Ref:
    def __init__(self, uri: str, sha256: str) -> None:
        self.uri = uri
        self.sha256 = sha256


class _Store:
    """ObjectStore stand-in that records whether bytes were written."""

    def __init__(self) -> None:
        self.writes: list[bytes] = []

    async def put_raw_dedup(self, body: bytes, tenant_id: str, meta: dict | None = None):
        import hashlib

        self.writes.append(body)
        digest = hashlib.sha256(body).hexdigest()
        return _Ref(f"s3://{tenant_id}/raw/{digest}", digest), False


class _Producer:
    def __init__(self) -> None:
        self.produced: list[tuple[str, object, str]] = []

    def produce(self, topic: str, envelope: object, key: str) -> None:
        self.produced.append((topic, envelope, key))


def _gate() -> tuple[ObservationGate, _Store, _Producer]:
    store, producer = _Store(), _Producer()
    return ObservationGate(store=store, router=_Router(), producer=producer), store, producer


BODY = b'{"results": [{"url": "https://a.example"}]}'
KW = {
    "body": BODY,
    "uri": "https://searxng.internal/search?q=test",
    "tenant_id": "acme",
    "investigation_id": "INV-1",
    "source_id": "searxng.search",
    "work_id": "WID-1",
}


class TestGateObservationIdentityIsReproducible:
    @pytest.mark.asyncio
    async def test_two_independent_gates_agree_on_the_observation_id(self):
        """The property a uuid4 id structurally cannot have."""
        first, _, _ = _gate()
        second, _, _ = _gate()
        a = await first.ingest(**KW)
        b = await second.ingest(**KW)
        assert a["observation_id"] == b["observation_id"]

    @pytest.mark.asyncio
    async def test_replaying_the_same_bytes_yields_the_same_observation_id(self):
        """§12 replay invariant, at the gate."""
        gate, _, _ = _gate()
        first = await gate.ingest(**KW)
        second = await gate.ingest(**KW)
        assert first["observation_id"] == second["observation_id"]

    @pytest.mark.asyncio
    async def test_three_replays_all_agree(self):
        gate, _, _ = _gate()
        ids = {(await gate.ingest(**KW))["observation_id"] for _ in range(3)}
        assert len(ids) == 1

    @pytest.mark.asyncio
    async def test_different_bytes_yield_different_observation_ids(self):
        gate, _, _ = _gate()
        a = await gate.ingest(**{**KW, "body": b'{"a":1}'})
        b = await gate.ingest(**{**KW, "body": b'{"a":2}'})
        assert a["observation_id"] != b["observation_id"]

    @pytest.mark.asyncio
    async def test_different_tenant_yields_a_different_observation_id(self):
        """§110 tenant isolation reaches the address, not only the row."""
        gate, _, _ = _gate()
        a = await gate.ingest(**KW)
        b = await gate.ingest(**{**KW, "tenant_id": "other"})
        assert a["observation_id"] != b["observation_id"]

    @pytest.mark.asyncio
    async def test_observation_id_is_not_a_uuid(self):
        gate, _, _ = _gate()
        obs = await gate.ingest(**KW)
        oid = obs["observation_id"]
        assert oid.startswith("OBS-"), "the address keeps the canonical prefix"
        # A uuid4 hex prefix would leave further '-' separators inside the body.
        # ``OBS-`` plus exactly one separator is what a content address looks like.
        assert oid.count("-") == 1, f"{oid!r} has uuid shape: the defect is back"

    @pytest.mark.asyncio
    async def test_address_is_a_content_address(self):
        gate, _, _ = _gate()
        obs = await gate.ingest(**KW)
        body = obs["observation_id"].removeprefix("OBS-")
        assert len(body) == 32
        assert all(c in "0123456789abcdef" for c in body)


class TestGateEventIdentityIsReproducible:
    @pytest.mark.asyncio
    async def test_two_gates_emit_the_same_event_id(self):
        a_gate, _, a_prod = _gate()
        b_gate, _, b_prod = _gate()
        await a_gate.ingest(**KW)
        await b_gate.ingest(**KW)
        a_env = a_prod.produced[0][1]
        b_env = b_prod.produced[0][1]
        assert a_env.event_id == b_env.event_id

    @pytest.mark.asyncio
    async def test_event_id_is_not_built_from_the_raw_sha(self):
        """The legacy f'evt-{sha256}-{lifecycle}' form is not a §11 address."""
        gate, _, prod = _gate()
        await gate.ingest(**KW)
        event_id = prod.produced[0][1].event_id
        assert not event_id.endswith("-created")
        assert len(event_id) == len("evt-") + 32
    @pytest.mark.asyncio
    async def test_event_id_passes_the_deterministic_guard(self):
        from domain.observation_identity import require_deterministic_event_id

        gate, _, prod = _gate()
        await gate.ingest(**KW)
        require_deterministic_event_id(prod.produced[0][1].event_id)


class TestGateHasNoRandomSource:
    """Belt-and-braces: the behaviour tests above are the real guard.

    This one reads the module's imports rather than its whole text, so the
    docstring explaining the removal does not trip it.
    """

    def test_uuid_is_not_imported_by_the_gate(self):
        tree = ast.parse(
            pathlib.Path("apps/shared/events/observation_gate.py").read_text("utf-8")
        )
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module.split(".")[0])
        assert "uuid" not in modules, "the gate must not import uuid (§160)"
        assert "random" not in modules


class TestIngestRecordSeam:
    """§9's second path: address a record without re-storing the blob."""

    @pytest.mark.asyncio
    async def test_record_does_not_restore_the_blob(self):
        gate, store, _ = _gate()
        await gate.ingest_record(
            capture_id="CAP-" + "ab" * 16,
            record_locator="json:results[0]",
            record_digest="c" * 64,
            tenant_id="acme",
        )
        assert store.writes == [], "ingest_record must not write the blob again"

    @pytest.mark.asyncio
    async def test_record_identity_is_deterministic(self):
        a_gate, _, _ = _gate()
        b_gate, _, _ = _gate()
        kw = {
            "capture_id": "CAP-" + "ab" * 16,
            "record_locator": "json:results[0]",
            "record_digest": "c" * 64,
            "tenant_id": "acme",
        }
        a = await a_gate.ingest_record(**kw)
        b = await b_gate.ingest_record(**kw)
        assert a["observation_id"] == b["observation_id"]

    @pytest.mark.asyncio
    async def test_replaying_one_record_is_the_same_observation(self):
        gate, _, prod = _gate()
        kw = {
            "capture_id": "CAP-" + "ab" * 16,
            "record_locator": "airbyte:message:17",
            "record_digest": "d" * 64,
            "tenant_id": "acme",
        }
        first = await gate.ingest_record(**kw)
        second = await gate.ingest_record(**kw)
        assert first["observation_id"] == second["observation_id"]
        assert len(prod.produced) == 1, "a replayed record must not publish twice"

    @pytest.mark.asyncio
    async def test_same_record_in_two_captures_is_two_observations(self):
        """§34: identical JSON under different streams is two occurrences."""
        gate, _, _ = _gate()
        common = {
            "record_locator": "airbyte:message:0",
            "record_digest": "e" * 64,
            "tenant_id": "acme",
        }
        a = await gate.ingest_record(capture_id="CAP-" + "11" * 16, **common)
        b = await gate.ingest_record(capture_id="CAP-" + "22" * 16, **common)
        assert a["observation_id"] != b["observation_id"]

    @pytest.mark.asyncio
    async def test_distinct_locators_are_distinct_observations(self):
        gate, _, _ = _gate()
        common = {"capture_id": "CAP-" + "ab" * 16, "record_digest": "e" * 64, "tenant_id": "acme"}
        a = await gate.ingest_record(record_locator="json:results[0]", **common)
        b = await gate.ingest_record(record_locator="json:results[1]", **common)
        assert a["observation_id"] != b["observation_id"]

    @pytest.mark.asyncio
    async def test_missing_locator_refuses_by_name(self):
        from domain.observation_identity import ObservationIdentityError

        gate, _, _ = _gate()
        with pytest.raises(ObservationIdentityError) as exc:
            await gate.ingest_record(
                capture_id="CAP-" + "ab" * 16,
                record_locator="",
                record_digest="c" * 64,
                tenant_id="acme",
            )
        assert exc.value.code == "observation_locator_missing"

    @pytest.mark.asyncio
    async def test_unknown_fields_are_retained(self):
        """§62: an unmapped field is kept, not dropped."""
        gate, _, _ = _gate()
        obs = await gate.ingest_record(
            capture_id="CAP-" + "ab" * 16,
            record_locator="bbot:event:0",
            record_digest="f" * 64,
            tenant_id="acme",
            record_metadata={"vendor_specific": {"x": 1}, "unknown_field": "keep me"},
        )
        assert obs["record_metadata"]["unknown_field"] == "keep me"

    @pytest.mark.asyncio
    async def test_capture_and_record_observations_are_different_addresses(self):
        """§6: what came back, and what was addressed in it, are two things."""
        gate, _, _ = _gate()
        parent = await gate.ingest(**KW)
        child = await gate.ingest_record(
            capture_id="CAP-" + parent["content_hash"],
            record_locator="json:results[0]",
            record_digest="9" * 64,
            tenant_id="acme",
        )
        assert parent["observation_id"] != child["observation_id"]
        assert parent.get("locator") is None, "a blob-level capture is not a record"
        assert child["locator"] == "json:results[0]"

    @pytest.mark.asyncio
    async def test_capture_observation_uses_the_reserved_capture_locator(self):
        gate, _, _ = _gate()
        await gate.ingest(**KW)
        assert CAPTURE_LOCATOR == "capture"
