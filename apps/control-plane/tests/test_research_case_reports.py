"""Evidence-grounded completion-report contracts for Feature 034."""
from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest

from contracts.evidence_span import CharSpan, EvidenceSpanRef, SourceLocator, StoredDocument
from services.research_case_artifacts import CaseArtifactError, ResearchCaseArtifactService
from services.research_case_reports import ResearchCaseReportService


class _MemoryRawStore:
    raw_bucket = "case-raw"

    def __init__(self, body: bytes):
        self.body = body
        self.reads: list[tuple[str, str, int, int | None]] = []

    async def read_range(self, *, bucket: str, key: str, offset: int = 0, length: int | None = None):
        self.reads.append((bucket, key, offset, length))
        assert bucket == self.raw_bucket
        assert key.startswith("raw/tenant-1/")
        end = None if length is None else offset + length
        return self.body[offset:end]


def _span_payload(body: bytes, *, start: int, end: int, surface: str, digest: str | None = None):
    document = StoredDocument(data=body, encoding="utf-8")
    span = EvidenceSpanRef(
        observation_ref="OBS-report-test",
        blob_digest=digest or document.blob_digest(),
        selector=CharSpan(start=start, end=end, encoding="utf-8", units="document_char"),
        source_locator=SourceLocator(
            uri="https://public.example/record/1",
            fragment=f"char_span={start}:{end}",
        ),
        selector_semantics_version="char_span/1",
    )
    return {
        "status": "grounded",
        "start": start,
        "end": end,
        "surface": surface,
        "selector_semantics_version": "char_span/1",
        "evidence_span": span.as_dict(),
    }


def _report_service(body: bytes):
    raw_store = _MemoryRawStore(body)
    service = ResearchCaseReportService(
        context_store=object(),
        session_factory=object(),
        projection_provider=object(),
        object_store=raw_store,
    )
    return service, raw_store


@pytest.mark.asyncio
async def test_ground_mention_reloads_raw_bytes_and_resolves_exact_quote():
    body = b"The author Alice Example works at Open Corp."
    start = body.decode("utf-8").index("Alice Example")
    end = start + len("Alice Example")
    service, raw_store = _report_service(body)
    mention = SimpleNamespace(
        mention_id="MEN-report-test",
        surface_form="Alice Example",
        observation_id="OBS-report-test",
        offsets=_span_payload(body, start=start, end=end, surface="Alice Example"),
    )
    observation = SimpleNamespace(
        observation_id="OBS-report-test",
        raw_ref="s3://case-raw/raw/tenant-1/202610/" + hashlib.sha256(body).hexdigest(),
        provenance={"capture_id": "CAP-report-test"},
        uri="https://public.example/record/1",
        created_at=None,
    )

    result = await service._ground_mention(
        mention=mention,
        observation=observation,
        tenant_id="tenant-1",
        raw_cache={},
    )

    assert result["status"] == "grounded"
    assert result["exact_quote"] == "Alice Example"
    assert result["blob_digest"] == StoredDocument(data=body).blob_digest()
    assert result["capture_id"] == "CAP-report-test"
    assert raw_store.reads == [
        ("case-raw", observation.raw_ref.removeprefix("s3://case-raw/"), 0, None)
    ]


@pytest.mark.asyncio
async def test_ground_mention_rejects_stale_digest_and_surface_mismatch():
    body = b"The author Alice Example works at Open Corp."
    start = body.decode("utf-8").index("Alice Example")
    end = start + len("Alice Example")
    service, _ = _report_service(body)
    observation = SimpleNamespace(
        observation_id="OBS-report-test",
        raw_ref="s3://case-raw/raw/tenant-1/202610/" + hashlib.sha256(body).hexdigest(),
        provenance={},
        uri="https://public.example/record/1",
        created_at=None,
    )
    stale_mention = SimpleNamespace(
        mention_id="MEN-stale",
        surface_form="Alice Example",
        observation_id="OBS-report-test",
        offsets=_span_payload(body, start=start, end=end, surface="Alice Example", digest="sha256:" + "0" * 64),
    )
    stale = await service._ground_mention(
        mention=stale_mention, observation=observation, tenant_id="tenant-1", raw_cache={}
    )
    assert stale["status"] == "stale"

    wrong_quote = SimpleNamespace(
        mention_id="MEN-wrong-quote",
        surface_form="Different Person",
        observation_id="OBS-report-test",
        offsets=_span_payload(body, start=start, end=end, surface="Alice Example"),
    )
    mismatch = await service._ground_mention(
        mention=wrong_quote, observation=observation, tenant_id="tenant-1", raw_cache={}
    )
    assert mismatch["status"] == "ungrounded"
    assert "surface" in mismatch["reason"] or "span" in mismatch["reason"]


@pytest.mark.asyncio
async def test_ground_mention_does_not_invent_missing_evidence():
    service, raw_store = _report_service(b"anything")
    mention = SimpleNamespace(
        mention_id="MEN-no-span",
        surface_form="No span",
        observation_id="OBS-no-span",
        offsets={"status": "ungrounded", "reason": "extractor supplied no absolute offset"},
    )
    result = await service._ground_mention(
        mention=mention,
        observation=None,
        tenant_id="tenant-1",
        raw_cache={},
    )
    assert result["status"] == "ungrounded"
    assert "no absolute offset" in result["reason"]
    assert raw_store.reads == []


def test_artifact_filename_is_basename_only_and_bounded():
    assert ResearchCaseArtifactService._filename("../../etc/passwd") == "passwd"
    assert ResearchCaseArtifactService._filename("report\u0000.pdf") == "report_.pdf"
    assert len(ResearchCaseArtifactService._filename("a" * 400 + ".pdf")) <= 255


@pytest.mark.asyncio
async def test_artifact_upload_refuses_empty_and_oversized_bytes_before_io():
    service = ResearchCaseArtifactService(
        context_store=None,
        session_factory=None,
        object_store=None,
    )
    with pytest.raises(CaseArtifactError, match="empty"):
        await service.upload(
            case_id="case-1",
            tenant_id="tenant-1",
            actor_id="analyst",
            filename="empty.txt",
            content_type="text/plain",
            caption="",
            body=b"",
        )
    with pytest.raises(CaseArtifactError, match="upload limit"):
        await service.upload(
            case_id="case-1",
            tenant_id="tenant-1",
            actor_id="analyst",
            filename="big.bin",
            content_type="application/octet-stream",
            caption="",
            body=b"x" * (25 * 1024 * 1024 + 1),
        )
