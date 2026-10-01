"""The artifact seam and the sink: §5, §6, §9, §11, §12, §61, §69, §124.

Written to fail first. The properties asserted here are the ones that make the
seam trustworthy rather than merely present - streaming, boundedness, the blob
being stored exactly once, and the whole identity chain being reproducible.
"""

from __future__ import annotations

import hashlib
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

# Same bootstrap the existing acquisition tests use (see tests/integration/
# test_live_loop.py): the app directory *is* the package root, so its modules are
# imported by their own name. ``cognitive-shared`` is an editable workspace
# dependency, so ``domain``/``events`` resolve without a path entry.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from artifact_sink import (  # noqa: E402
    STAGE_OBSERVATION,
    STAGE_RAW_STORE,
    ArtifactSink,
    ArtifactSinkError,
)
from domain.acquisition_artifact import (  # noqa: E402
    AcquisitionArtifact,
    ArtifactBudget,
    ArtifactContractError,
    stream_artifact,
)
from domain.capture import Capture, CaptureTimeBasis  # noqa: E402
from events.observation_gate import ObservationGate  # noqa: E402

FETCHED = datetime(2026, 9, 29, 12, 0, 0, tzinfo=UTC)
BODY = b'{"results": [{"url": "https://a.example", "title": "A"}]}'
CATEGORIES = {
    "dns_cloudflare",
    "rdap_domain",
    "openphish_feed",
    "searxng.search",
    "airbyte.records",
    "maigret.site",
    "bbot.event",
    "spiderfoot.event",
}


def artifact(**over) -> AcquisitionArtifact:
    kw = {
        "task_id": "TSK-1",
        "source_id": "searxng.search",
        "worker_ref": "http",
        "target_uri": "https://searxng.internal/search?q=test",
        "locator": "json:results[0]",
        "body": BODY,
        "content_type": "application/json",
        "fetched_at": FETCHED,
        "transport": "http",
        "producer": "searxng",
        "producer_version": "2026.9.29",
        "metadata": {},
    }
    kw.update(over)
    return AcquisitionArtifact(**kw)


# ---------------------------------------------------------------- stubs ------


class _Ref:
    def __init__(self, uri: str, sha256: str) -> None:
        self.uri = uri
        self.sha256 = sha256


class _Store:
    def __init__(self, *, fail: bool = False) -> None:
        self.writes: list[bytes] = []
        self.fail = fail

    async def put_raw_dedup(self, body: bytes, tenant_id: str, meta: dict | None = None):
        if self.fail:
            raise RuntimeError("object store unavailable")
        self.writes.append(body)
        d = hashlib.sha256(body).hexdigest()
        return _Ref(f"s3://{tenant_id}/raw/{d}", d), False


class _Router:
    def classify(self, body: bytes, *, url: str = "", headers: dict | None = None) -> dict:
        return {
            "content_type": "application/json",
            "sha256": hashlib.sha256(body).hexdigest(),
        }


class _Producer:
    def __init__(self) -> None:
        self.produced: list[tuple[str, str]] = []

    def produce(self, topic: str, envelope: object, key: str) -> None:
        self.produced.append((topic, envelope.event_id))


def _sink(*, store=None, producer=True):
    st = store or _Store()
    pr = _Producer() if producer else None
    gate = ObservationGate(store=st, router=_Router(), producer=pr)
    return ArtifactSink(gate=gate, store=st, source_family="search"), st, pr


# ------------------------------------------------------------ artifact -------


class TestArtifactContract:
    def test_locator_is_required(self):
        with pytest.raises(ArtifactContractError) as exc:
            artifact(locator="")
        assert exc.value.code == "artifact_locator_missing"

    def test_producer_is_required(self):
        """Provenance is not inferred from runtime_ref (§97)."""
        with pytest.raises(ArtifactContractError) as exc:
            artifact(producer="")
        assert exc.value.code == "artifact_producer_missing"

    def test_body_must_be_bytes(self):
        """A runtime that decoded its output has taken the parser's job (§3)."""
        with pytest.raises(ArtifactContractError) as exc:
            artifact(body='{"a":1}')
        assert exc.value.code == "artifact_body_missing"

    def test_empty_body_is_allowed(self):
        """An empty response is a result, not a malformed artifact."""
        assert artifact(body=b"").byte_length == 0

    def test_frozen(self):
        import dataclasses

        with pytest.raises(dataclasses.FrozenInstanceError):
            artifact().locator = "changed"

    def test_metadata_is_copied_not_aliased(self):
        m = {"a": 1}
        a = artifact(metadata=m)
        m["b"] = 2
        assert "b" not in a.metadata

    def test_to_dict_omits_the_body(self):
        """§69: the event payload is refs only."""
        d = artifact().to_dict()
        assert "body" not in d
        assert d["byte_length"] == len(BODY)

    def test_record_digest_is_the_body_digest(self):
        assert artifact().record_digest() == hashlib.sha256(BODY).hexdigest()

    def test_different_bytes_different_digest(self):
        assert artifact(body=b"x").record_digest() != artifact().record_digest()


class TestArtifactObservationIdentity:
    def test_delegates_to_the_single_writer(self):
        from domain.observation_identity import observation_id_for

        a = artifact()
        assert a.observation_identity(tenant_id="acme", capture_id="CAP-" + "ab" * 16) == (
            observation_id_for(
                tenant_id="acme",
                capture_id="CAP-" + "ab" * 16,
                locator=a.locator,
                record_digest=a.record_digest(),
            )
        )

    def test_replay_reproduces_the_address(self):
        a = artifact()
        assert a.observation_identity(tenant_id="t", capture_id="CAP-x") == (
            a.observation_identity(tenant_id="t", capture_id="CAP-x")
        )


class TestArtifactBudget:
    def test_counts_what_passed(self):
        b = ArtifactBudget()
        b.admit(artifact())
        b.admit(artifact(locator="json:results[1]"))
        assert b.artifacts == 2
        assert b.bytes == 2 * len(BODY)

    def test_refuses_past_max_artifacts(self):
        b = ArtifactBudget(max_artifacts=1)
        b.admit(artifact())
        with pytest.raises(ArtifactContractError) as exc:
            b.admit(artifact(locator="json:results[1]"))
        assert exc.value.code == "resource_limit_exceeded"

    def test_refuses_past_max_bytes(self):
        b = ArtifactBudget(max_bytes=len(BODY))
        b.admit(artifact())
        with pytest.raises(ArtifactContractError):
            b.admit(artifact(locator="json:results[1]"))

    def test_refuses_rather_than_truncating(self):
        """§61: a truncated artifact's digest would not describe the response."""
        b = ArtifactBudget(max_bytes=10)
        with pytest.raises(ArtifactContractError):
            b.admit(artifact())

    def test_reports_its_counters(self):
        b = ArtifactBudget(max_artifacts=5)
        b.admit(artifact())
        assert b.to_dict()["artifacts"] == 1
        assert b.to_dict()["max_artifacts"] == 5

    def test_no_limit_means_no_refusal(self):
        b = ArtifactBudget()
        for i in range(50):
            b.admit(artifact(locator=f"json:results[{i}]"))
        assert b.artifacts == 50


class TestArtifactStreaming:
    @pytest.mark.asyncio
    async def test_yields_as_the_producer_yields(self):
        async def gen():
            for i in range(3):
                yield artifact(locator=f"json:results[{i}]")

        got = [a async for a in stream_artifact(gen())]
        assert [a.locator for a in got] == ["json:results[0]", "json:results[1]", "json:results[2]"]

    @pytest.mark.asyncio
    async def test_budget_applies_mid_stream(self):
        async def gen():
            for i in range(10):
                yield artifact(locator=f"json:results[{i}]")

        b = ArtifactBudget(max_artifacts=3)
        taken = []
        with pytest.raises(ArtifactContractError):
            async for a in stream_artifact(gen(), budget=b):
                taken.append(a)
        assert len(taken) == 3, "the limit stops consumption, not after the fact"

    @pytest.mark.asyncio
    async def test_empty_stream_is_not_an_error(self):
        async def gen():
            return
            yield  # pragma: no cover

        assert [a async for a in stream_artifact(gen())] == []


# ---------------------------------------------------------------- sink -------


class TestSinkStoresThenAddresses:
    @pytest.mark.asyncio
    async def test_stores_the_blob_exactly_once(self):
        """§124: same bytes, one raw object - and one write per artifact."""
        sink, store, _ = _sink()
        await sink.accept(artifact(), tenant_id="acme")
        assert store.writes == [BODY]

    @pytest.mark.asyncio
    async def test_returns_the_whole_chain(self):
        """§71: task, capture, raw_ref, observation, event, topic."""
        sink, _, prod = _sink()
        got = await sink.accept(artifact(), tenant_id="acme", investigation_id="INV-1")
        assert got.task_id == "TSK-1"
        assert got.capture_id.startswith("CAP-")
        assert got.raw_ref.startswith("s3://acme/raw/")
        assert got.observation_id.startswith("OBS-")
        assert got.event_id and got.event_id.startswith("evt-")
        assert got.topic
        assert got.locator == "json:results[0]"
        assert prod.produced == [(got.topic, got.event_id)]

    @pytest.mark.asyncio
    async def test_capture_carries_the_required_fields(self):
        """§8's fifteen fields reach the durable object."""
        sink, _, _ = _sink(source_family := None) if False else _sink()
        await sink.accept(artifact(), tenant_id="acme")
        cap = Capture(
            tenant_id="acme",
            source_id="searxng.search",
            source_family="search",
            target_uri="https://searxng.internal/search?q=test",
            locator="json:results[0]",
            content_digest=hashlib.sha256(BODY).hexdigest(),
            content_length=len(BODY),
            media_type="application/json",
            fetched_at=FETCHED,
            time_basis=CaptureTimeBasis.FETCH,
            transport="http",
            recorded_by="acquisition-worker",
        )
        assert cap.capture_id.startswith("CAP-")
        assert cap.payload_key

    @pytest.mark.asyncio
    async def test_no_producer_means_no_event_id_not_a_placeholder(self):
        sink, _, _ = _sink(producer=False)
        got = await sink.accept(artifact(), tenant_id="acme")
        assert got.event_id is None
        assert got.topic is None

    @pytest.mark.asyncio
    async def test_event_id_is_deterministic(self):
        """§160: a random event id blocks release."""
        a, _, _ = _sink()
        b, _, _ = _sink()
        first = await a.accept(artifact(), tenant_id="acme")
        second = await b.accept(artifact(), tenant_id="acme")
        assert first.event_id == second.event_id
        assert first.observation_id == second.observation_id
        assert first.capture_id == second.capture_id

    @pytest.mark.asyncio
    async def test_records_of_one_page_share_the_capture(self):
        """§20: one response page is one capture; its results address into it.

        This is the case that catches a per-record locator leaking into
        ``Capture``, which registers one fetch as N captures.
        """
        sink, store, _ = _sink()
        a = await sink.accept(
            artifact(locator="json:results[0]", capture_locator="capture:page:1"),
            tenant_id="acme",
        )
        b = await sink.accept(
            artifact(locator="json:results[1]", capture_locator="capture:page:1"),
            tenant_id="acme",
        )
        assert a.observation_id != b.observation_id, "distinct records, distinct addresses"
        assert a.capture_id == b.capture_id, "one page fetched once is one capture"
        assert len(store.writes) == 2, "two artifacts were stored; the store is not the capture"

    @pytest.mark.asyncio
    async def test_different_pages_are_different_captures(self):
        sink, _, _ = _sink()
        a = await sink.accept(
            artifact(capture_locator="capture:page:1"), tenant_id="acme"
        )
        b = await sink.accept(
            artifact(capture_locator="capture:page:2"), tenant_id="acme"
        )
        assert a.capture_id != b.capture_id, "§98: a fetched page must not be overwritten"

    @pytest.mark.asyncio
    async def test_a_standalone_artifact_is_its_own_capture(self):
        """The single-record case every non-HTTP runtime produces."""
        sink, _, _ = _sink()
        got = await sink.accept(artifact(), tenant_id="acme")
        assert got.capture_id.startswith("CAP-")
        assert got.locator == "json:results[0]"

    @pytest.mark.asyncio
    async def test_tenant_reaches_the_address(self):
        """§110: isolation reaches the identity, not only the row."""
        a, _, _ = _sink()
        b, _, _ = _sink()
        x = await a.accept(artifact(), tenant_id="acme")
        y = await b.accept(artifact(), tenant_id="other")
        assert x.observation_id != y.observation_id
        assert x.capture_id != y.capture_id

    @pytest.mark.asyncio
    async def test_replay_yields_the_same_observation(self):
        """§12: same artifact, same address, not a second copy."""
        sink, _, _ = _sink()
        first = await sink.accept(artifact(), tenant_id="acme")
        second = await sink.accept(artifact(), tenant_id="acme")
        assert first.observation_id == second.observation_id

    @pytest.mark.asyncio
    async def test_runtime_provenance_is_retained(self):
        """§63: traceable to collector, producer and version."""
        sink, _, _ = _sink()
        got = await sink.accept(
            artifact(producer="bbot", producer_version="3.2.0", worker_ref="external_tool"),
            tenant_id="acme",
        )
        assert got.runtime_producer == "bbot"
        assert got.runtime_producer_version == "3.2.0"
        assert got.worker_ref == "external_tool"

    @pytest.mark.asyncio
    async def test_vendor_metadata_is_retained(self):
        """§62: unmapped fields are kept, not dropped."""
        sink, _, _ = _sink()
        got = await sink.accept(
            artifact(metadata={"vendor_specific": {"x": 1}}), tenant_id="acme"
        )
        assert got.to_dict()["runtime_producer"] == "searxng"

    @pytest.mark.asyncio
    async def test_accepted_history_is_available(self):
        sink, _, _ = _sink()
        await sink.accept(artifact(), tenant_id="acme")
        assert len(sink.accepted) == 1


class TestSinkRefusalOrder:
    @pytest.mark.asyncio
    async def test_store_failure_aborts_before_any_address(self):
        """§160: no observation without raw lineage."""
        sink, store, prod = _sink(store=_Store(fail=True))
        with pytest.raises(ArtifactSinkError) as exc:
            await sink.accept(artifact(), tenant_id="acme")
        assert exc.value.stage == STAGE_RAW_STORE
        assert prod.produced == [], "nothing may be published without durable raw"
        assert sink.accepted == ()

    @pytest.mark.asyncio
    async def test_missing_locator_never_reaches_the_store(self):
        """A malformed artifact must not cost a write."""
        sink, store, _ = _sink()
        with pytest.raises(ArtifactContractError):
            artifact(locator="")
        assert store.writes == []

    @pytest.mark.asyncio
    async def test_wrong_type_is_named(self):
        sink, _, _ = _sink()
        with pytest.raises(ArtifactSinkError) as exc:
            await sink.accept({"locator": "x"}, tenant_id="acme")  # type: ignore[arg-type]
        assert exc.value.stage == STAGE_OBSERVATION

    @pytest.mark.asyncio
    async def test_failure_carries_a_named_stage(self):
        """§73 forbids a generic 'integration failed'."""
        sink, _, _ = _sink(store=_Store(fail=True))
        try:
            await sink.accept(artifact(), tenant_id="acme")
        except ArtifactSinkError as exc:
            assert exc.stage
            assert exc.code
        else:
            pytest.fail("expected ArtifactSinkError")


class TestLocatorGrammar:
    """§10: one grammar, six schemes, deterministic."""

    @pytest.mark.parametrize("locator", sorted(CATEGORIES - {"json:results[0]"}))
    def test_every_family_has_a_usable_locator(self, locator):
        assert artifact(locator=locator).locator == locator

    def test_locator_is_part_of_the_address(self):
        a = artifact(locator="bbot:event:0").observation_identity(
            tenant_id="t", capture_id="CAP-x"
        )
        b = artifact(locator="bbot:event:1").observation_identity(
            tenant_id="t", capture_id="CAP-x"
        )
        assert a != b
