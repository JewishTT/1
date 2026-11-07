from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from domain.capture import CaptureTimeBasis
from zero.evidence import ZeroLayerEvidenceSink
from zero.harvesters.transport import PublicFetchCapture


class _Accepted:
    capture_id = "CAP-1"
    observation_id = "OBS-1"
    raw_ref = "s3://tenant/raw/sha256/abc"
    content_digest = "sha256:abc"
    event_id = "EVT-1"
    topic = "observation"


class _ArtifactSink:
    def __init__(self) -> None:
        self.calls = []

    async def accept(self, artifact, **kwargs):
        self.calls.append((artifact, kwargs))
        return _Accepted()


@pytest.mark.asyncio
async def test_raw_public_capture_uses_canonical_fetch_capture_time_basis() -> None:
    raw = _ArtifactSink()
    sink = ZeroLayerEvidenceSink(raw, source_id="zero-layer")
    capture = PublicFetchCapture(
        url="https://example.org/about",
        status=200,
        body=b"<html>public page</html>",
        content_type="text/html",
        fetched_at=datetime.now(UTC),
        pinned_ip="203.0.113.10",
    )

    accepted = await sink.persist_capture(
        capture, tenant_id="tenant-1", investigation_id="INV-1"
    )

    artifact, kwargs = raw.calls[0]
    assert accepted is _Accepted or accepted.observation_id == "OBS-1"
    assert artifact.body == capture.body
    assert artifact.target_uri == capture.url
    assert artifact.metadata["result_role"] == "DISCOVERY_ONLY"
    assert artifact.metadata["claim_admission_allowed"] is False
    assert kwargs["tenant_id"] == "tenant-1"
    assert kwargs["time_basis"] is CaptureTimeBasis.FETCH


@pytest.mark.asyncio
async def test_stage_observations_are_also_discovery_only() -> None:
    raw = _ArtifactSink()
    sink = ZeroLayerEvidenceSink(raw, source_id="zero-layer")
    record = {
        "stage": "HARVEST",
        "wave_index": 0,
        "seed_id": "seed-1",
        "seed_type": "url",
        "seed_value": "https://example.org/",
        "candidates": [],
        "candidate_count": 0,
    }

    persisted = await sink.persist(record, tenant_id="tenant-1")
    artifact, kwargs = raw.calls[0]
    assert persisted.observation_id == "OBS-1"
    assert artifact.metadata["result_role"] == "DISCOVERY_ONLY"
    assert artifact.metadata["claim_admission_allowed"] is False
    assert kwargs["time_basis"] is CaptureTimeBasis.ABSENT


@pytest.mark.asyncio
async def test_raw_capture_rejects_non_https_and_empty_payloads() -> None:
    sink = ZeroLayerEvidenceSink(_ArtifactSink(), source_id="zero-layer")
    with pytest.raises(ValueError, match="HTTPS"):
        await sink.persist_capture(
            PublicFetchCapture(
                url="http://example.org/",
                status=200,
                body=b"body",
                content_type="text/html",
                fetched_at=datetime.now(UTC),
                pinned_ip="203.0.113.10",
            ),
            tenant_id="tenant-1",
        )
    with pytest.raises(ValueError, match="empty"):
        await sink.persist_capture(
            PublicFetchCapture(
                url="https://example.org/",
                status=200,
                body=b"",
                content_type="text/html",
                fetched_at=datetime.now(UTC),
                pinned_ip="203.0.113.10",
            ),
            tenant_id="tenant-1",
        )
