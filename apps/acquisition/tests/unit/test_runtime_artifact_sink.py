"""Runtime acquisition must persist raw-first evidence through ArtifactSink."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

APP = Path(__file__).resolve().parents[2]
REPO = APP.parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(REPO / "apps" / "shared"))

from domain.capture import CaptureTimeBasis
from worker_acquisition import AcquisitionWorker


class _Runtime:
    runtime_ref = "searxng"
    requires_connector_config = False

    def __init__(self) -> None:
        self.calls = 0

    async def acquire(self, task):
        self.calls += 1
        yield object()


class _Accepted:
    event_id = "EVT-runtime-1"
    observation_id = "OBS-runtime-1"
    topic = "observation.created"
    content_digest = "a" * 64
    raw_ref = "s3://knowledge-raw/tenant-a/2026-11/" + ("a" * 64)
    capture_id = "CAP-runtime-1"
    locator = "searxng:page:1"

    def to_dict(self):
        return {
            "event_id": self.event_id,
            "observation_id": self.observation_id,
            "topic": self.topic,
            "content_digest": self.content_digest,
            "raw_ref": self.raw_ref,
            "capture_id": self.capture_id,
            "locator": self.locator,
        }


class _Sink:
    def __init__(self) -> None:
        self.accepted = []

    async def accept(self, artifact, **kwargs):
        self.accepted.append((artifact, kwargs))
        return _Accepted()


class _Connector:
    def __init__(self, sink=None) -> None:
        self.sink = sink

    def definition_for(self, source_id):
        if source_id != "SRC-searxng":
            return None
        return SimpleNamespace(
            name="searxng_public_search",
            enabled=True,
            source_family="public_search",
            time_basis=CaptureTimeBasis.FETCH,
        )

    def artifact_sink_factory(self, definition):
        return self.sink


def _envelope():
    payload = {
        "task_id": "TSK-runtime-1",
        "source_id": "SRC-searxng",
        "source_name": "searxng_public_search",
        "query": '"Acme Systems"',
        "category": "08. Knowledge",
        "runtime_ref": "searxng",
    }
    return SimpleNamespace(
        payload=json.dumps(payload).encode(),
        work_id="TSK-runtime-1",
        source_id="SRC-searxng",
        tenant_id="tenant-a",
        investigation_id="case-a",
    )


async def test_named_runtime_uses_artifact_sink_and_does_not_publish_twice() -> None:
    sink = _Sink()
    connector = _Connector(sink)
    runtime = _Runtime()
    worker = AcquisitionWorker(
        connector=connector,
        runtimes={"searxng": runtime},
    )

    result = await worker.handle(_envelope())

    assert not result.failures
    assert len(result.observations) == 1
    event = result.observations[0]
    assert event["event_type"] == "observation.created"
    assert event["event_published"] is True
    assert event["raw_ref"] == _Accepted.raw_ref
    assert event["content_digest"] == _Accepted.content_digest
    assert len(sink.accepted) == 1
    assert sink.accepted[0][1]["tenant_id"] == "tenant-a"
    assert sink.accepted[0][1]["investigation_id"] == "case-a"
    assert sink.accepted[0][1]["time_basis"] == CaptureTimeBasis.FETCH

    replay = await worker.handle(_envelope())
    assert replay.superseded is True
    assert len(sink.accepted) == 1
    assert runtime.calls == 1


async def test_named_runtime_fails_closed_without_artifact_sink() -> None:
    runtime = _Runtime()
    routed: list[tuple[object, object]] = []

    def failure_sink(failure, envelope) -> None:
        routed.append((failure, envelope))

    worker = AcquisitionWorker(
        connector=_Connector(sink=None),
        sink=failure_sink,
        runtimes={"searxng": runtime},
    )

    result = await worker.handle(_envelope())

    assert not result.observations
    assert len(result.failures) == 1
    assert result.failures[0].code == "runtime_artifact_sink_unavailable"
    assert len(routed) == 1
    assert routed[0][0].code == "runtime_artifact_sink_unavailable"
    assert routed[0][1].tenant_id == "tenant-a"
    assert runtime.calls == 0
