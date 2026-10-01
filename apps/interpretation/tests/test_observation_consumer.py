"""The downstream consumer: §85, §86, §108, §125, §173, §174, §192.

The properties that matter here are mostly negative ones - the consumer must not
reach the network, must not lose a malformed message, and must be a no-op on
replay - and negative properties are exactly what a happy-path test misses.
"""

from __future__ import annotations

import ast
import json
import pathlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from events import event_envelope_pb2 as pb

from observation_consumer import (
    CONSUMER_VERSION,
    ObservationConsumer,
)

SEARX_RESULT = {
    "url": "https://github.com/topics/event-driven",
    "title": "Event-driven",
    "engine": "brave",
    "category": "general",
    "content": "About event-driven architecture",
    "score": 4.5,
    "template": "default.html",
}
RAW = json.dumps(SEARX_RESULT, sort_keys=True).encode("utf-8")


class _Store:
    def __init__(self, body: bytes = RAW) -> None:
        self.body = body
        self.reads: list[tuple[str, str]] = []

    async def read_range(self, *, bucket: str, key: str, offset: int = 0, length=None) -> bytes:
        self.reads.append((bucket, key))
        return self.body


def envelope(
    *,
    observation_id: str = "OBS-" + "a" * 32,
    locator: str = "json:results[0]",
    raw_ref: str = "s3://bucket/raw/tenant/202609/abc",
    payload: bytes | None = None,
    parser_hint: str = "structured_fields",
) -> pb.EventEnvelope:
    body = payload
    if body is None:
        body = json.dumps(
            {
                "capture_id": "CAP-" + "b" * 32,
                "observation_id": observation_id,
                "locator": locator,
                "raw_ref": raw_ref,
                "parser_hint": parser_hint,
                "content_type": "application/json",
                "runtime_producer": "searxng",
            },
            sort_keys=True,
        ).encode("utf-8")
    return pb.EventEnvelope(
        event_id="evt-" + "c" * 32,
        event_type="observation.created",
        event_version="2.0",
        producer="observation-gate",
        producer_version="0.1.0",
        observation_id=observation_id,
        tenant_id="acme",
        source_id="searxng.search",
        payload=body,
    )


class TestConsumerProcesses:
    @pytest.mark.asyncio
    async def test_reads_raw_and_parses(self):
        store = _Store()
        consumer = ObservationConsumer(store=store)
        result = await consumer.handle(envelope())
        assert result.status == "processed"
        assert result.record_count > 1, "a JSON result must not collapse to one line"
        assert result.locator == "json:results[0]"
        assert result.capture_id.startswith("CAP-")

    @pytest.mark.asyncio
    async def test_reads_the_capture_it_was_given(self):
        """§174: fetch what the event names, not what we expect."""
        store = _Store()
        consumer = ObservationConsumer(store=store)
        await consumer.handle(envelope())
        assert store.reads == [("bucket", "raw/tenant/202609/abc")]

    @pytest.mark.asyncio
    async def test_binds_mentions(self):
        consumer = ObservationConsumer(store=_Store())
        result = await consumer.handle(envelope())
        assert result.mention_count > 0

    @pytest.mark.asyncio
    async def test_records_a_machine_readable_result(self):
        """§86: the proof is a value, not a log line."""
        consumer = ObservationConsumer(store=_Store(), processing_run_id="run-1")
        result = await consumer.handle(envelope())
        d = result.to_dict()
        for key in (
            "processing_run_id",
            "observation_id",
            "consumer",
            "consumer_version",
            "processed_at",
            "status",
            "derived_ref",
        ):
            assert d[key]
        assert d["processing_run_id"] == "run-1"
        assert CONSUMER_VERSION in d["consumer_version"]

    @pytest.mark.asyncio
    async def test_derived_ref_names_the_parser_and_version(self):
        """§63: traceable to the parser that read it."""
        consumer = ObservationConsumer(store=_Store())
        result = await consumer.handle(envelope())
        assert "structured_fields" in result.derived_ref
        assert CONSUMER_VERSION in result.derived_ref

    @pytest.mark.asyncio
    async def test_unknown_parser_is_not_guessed(self):
        """An undeclared parser takes the text route and records a refusal."""
        consumer = ObservationConsumer(store=_Store())
        result = await consumer.handle(envelope(parser_hint="no_such_parser"))
        assert result.status == "processed"
        assert "text_lines" in result.derived_ref


class TestConsumerIsIdempotent:
    @pytest.mark.asyncio
    async def test_replay_returns_the_same_result(self):
        """§125, §192: same id, one semantic result."""
        store = _Store()
        consumer = ObservationConsumer(store=store)
        first = await consumer.handle(envelope())
        second = await consumer.handle(envelope())
        assert first is second
        assert len(store.reads) == 1, "a replay must not re-read the raw bytes"

    @pytest.mark.asyncio
    async def test_distinct_observations_are_distinct_results(self):
        consumer = ObservationConsumer(store=_Store())
        await consumer.handle(envelope(observation_id="OBS-" + "1" * 32))
        await consumer.handle(envelope(observation_id="OBS-" + "2" * 32))
        assert len(consumer.results) == 2

    @pytest.mark.asyncio
    async def test_replay_is_byte_stable(self):
        a = ObservationConsumer(store=_Store())
        b = ObservationConsumer(store=_Store())
        ra = (await a.handle(envelope())).to_dict()
        rb = (await b.handle(envelope())).to_dict()
        for key in ("observation_id", "status", "derived_ref", "record_count", "mention_count"):
            assert ra[key] == rb[key]


class TestConsumerNeverRefetches:
    @pytest.mark.asyncio
    async def test_no_http_client_is_imported(self):
        """§174 as an import-list assertion, not a promise.

        The absence of an HTTP client in this module *is* the no-refetch guarantee.
        A consumer that could reach the network would eventually do so, and the
        first time it did, the evidence chain would have a hole no test caught.
        """
        tree = ast.parse(
            pathlib.Path("apps/interpretation/observation_consumer/__init__.py").read_text("utf-8")
        )
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        for banned in ("httpx", "requests", "aiohttp", "urllib"):
            assert banned not in imported, f"{banned} in the consumer would allow a refetch"

    @pytest.mark.asyncio
    async def test_a_url_in_the_payload_is_not_followed(self):
        """The record carries a URL; the consumer still reads the captured bytes."""
        store = _Store()
        consumer = ObservationConsumer(store=store)
        result = await consumer.handle(envelope())
        assert result.status == "processed"
        assert store.reads, "it must have read the capture, not the url"
        assert len(store.reads) == 1


class TestConsumerRefusesLoudly:
    """§108: no silent drop. A failure leaves a result with a reason."""

    @pytest.mark.asyncio
    async def test_missing_raw_ref_is_refused_by_name(self):
        consumer = ObservationConsumer(store=_Store())
        result = await consumer.handle(envelope(raw_ref=""))
        assert result.status == "refused"
        assert result.failure_code == "storage"
        assert "raw_ref" in result.detail

    @pytest.mark.asyncio
    async def test_non_json_payload_is_refused(self):
        consumer = ObservationConsumer(store=_Store())
        result = await consumer.handle(envelope(payload=b"not json at all"))
        assert result.status == "refused"
        assert result.failure_code == "schema"

    @pytest.mark.asyncio
    async def test_empty_payload_is_refused(self):
        consumer = ObservationConsumer(store=_Store())
        result = await consumer.handle(envelope(payload=b""))
        assert result.status == "refused"
        assert result.failure_code == "schema"

    @pytest.mark.asyncio
    async def test_unreadable_raw_is_refused(self):
        class Broken:
            async def read_range(self, **kw):
                raise OSError("object store gone")

        consumer = ObservationConsumer(store=Broken())
        result = await consumer.handle(envelope())
        assert result.status == "refused"
        assert result.failure_code == "storage"

    @pytest.mark.asyncio
    async def test_a_refusal_is_still_a_recorded_result(self):
        """§108: the refusal itself must be retrievable, not discarded."""
        consumer = ObservationConsumer(store=_Store())
        await consumer.handle(envelope(payload=b"not json"))
        assert len(consumer.results) == 1
        assert consumer.results[0].status == "refused"

    @pytest.mark.asyncio
    async def test_refusal_codes_are_classified(self):
        """§73 forbids a generic failure with no classification."""
        consumer = ObservationConsumer(store=_Store())
        # Distinct observation ids: the consumer is idempotent by id, so reusing
        # one would return the first cached result rather than classify the second.
        for index, (env, expected) in enumerate(
            (
                (envelope(observation_id="OBS-" + "1" * 32, raw_ref=""), "storage"),
                (envelope(observation_id="OBS-" + "2" * 32, payload=b"nope"), "schema"),
            )
        ):
            got = (await consumer.handle(env)).failure_code
            assert got == expected, f"case {index} classified as {got}, expected {expected}"

    @pytest.mark.asyncio
    async def test_handle_never_raises_on_bad_data(self):
        """§203: a failure must not become an exception that kills the loop."""
        consumer = ObservationConsumer(store=_Store())
        for payload in (b"", b"\xff\xfe\x00", b"{", b"[1,2,3]", b'"str"'):
            result = await consumer.handle(envelope(payload=payload))
            assert result.status in {"processed", "refused", "skipped_replay"}


class TestConsumerDoesNotOverreach:
    @pytest.mark.asyncio
    async def test_mints_no_entity_and_no_claim(self):
        """§3, §118, §119: this stage parses, it does not decide."""
        source = pathlib.Path("apps/interpretation/observation_consumer/__init__.py").read_text(
            "utf-8"
        )
        code = "\n".join(
            line for line in source.splitlines() if not line.lstrip().startswith("#")
        )
        for banned in ("EntityStore", "GraphWriter", "GraphEdge", "RelationClaim", "KnowledgeGraph"):
            assert banned not in code, f"{banned} must not appear in the consumer"

    @pytest.mark.asyncio
    async def test_does_not_type_anything(self):
        consumer = ObservationConsumer(store=_Store())
        result = await consumer.handle(envelope())
        # A type claim would surface as one; there is no such field.
        assert not hasattr(result, "entity_type")
        assert "email" not in json.dumps(result.to_dict()).lower()
