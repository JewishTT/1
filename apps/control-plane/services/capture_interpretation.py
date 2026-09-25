"""Turn a WARC range pull into provenance-bearing interpretation/admission data."""
from __future__ import annotations

import hashlib
from typing import Any


def interpret_warc_capture(
    *, entity_id: str, tenant_id: str, warc: Any, url: str, observed_at: str,
    observation_id: str, crawl: str, page: int, locator: str,
) -> dict[str, Any]:
    """Parse one capture, extract relations, and run real admission."""
    from admission.engine.intake import IntakeClaim, WarcIntake
    from extractors.registry import ExtractorRegistry
    from interpretation.parsers.warc import HttpMessage, WarcDocument, parse_http_message
    from interpretation.relations import DocumentContext, RelationExtractor

    message: HttpMessage = parse_http_message(warc.payload)
    body = message.body
    text = body.decode("utf-8", errors="replace")
    body_sha = hashlib.sha256(body).hexdigest()
    document = WarcDocument(
        document_id="WD-" + observation_id.removeprefix("OBS-"),
        record_id=warc.warc_record_id or observation_id,
        record_type=warc.record_type or "response",
        url=warc.url or url,
        warc_date=warc.warc_date,
        content_type=message.header("content-type") or warc.content_type,
        charset=(message.header("content-type") or "").split("charset=", 1)[-1].split(";")[0],
        http_status=message.status_code,
        text=text,
        payload=body,
        body_sha256=body_sha,
        warc_digest=warc.digest,
        digest_verified=None,
        notes=("non_text_payload",) if not text.strip() else (),
    )
    context = DocumentContext(
        document_id=document.document_id, record_id=document.record_id,
        source_uri=document.url, warc_date=document.warc_date, body_sha256=body_sha,
    )
    relations = RelationExtractor().extract(
        text, context, mentions=ExtractorRegistry().extract(text)
    ) if text.strip() else []
    claims = [
        IntakeClaim(
            subject=relation.subject_value, relation=relation.predicate,
            object_value=relation.object_value, document_id=document.document_id,
            subject_kind=relation.subject_kind, confidence=relation.confidence,
            evidence_id=relation.relation_id,
        )
        for relation in relations
    ]
    intake = WarcIntake(dataset_id="common-crawl", tenant_id=tenant_id).run(
        [document], claims
    )
    decisions = [
        {
            "admission_id": item.admission_id,
            "candidate_id": item.candidate_id,
            "decision": item.decision.value,
            "reason_codes": list(item.reason_codes),
            "score_vector": item.score_vector.to_dict() if item.score_vector else {},
            "evidence_refs": [
                {"observation_id": ref.observation_id, "source_id": ref.source_id}
                for ref in (item.evidence.evidence_refs if item.evidence else [])
            ],
        }
        for item in intake.decisions
    ]
    host = ""
    if "://" in document.url:
        host = document.url.split("://", 1)[1].split("/", 1)[0].lower()
    return {
        "event_at": observed_at,
        "source": "common_crawl",
        "url": url,
        "observation_id": observation_id,
        "locator": locator,
        "crawl": crawl,
        "page": page,
        "warc_record_id": warc.warc_record_id or "",
        "content_sha256": body_sha,
        "byte_length": len(body),
        "participants": [{"entity_id": entity_id, "role": "record_subject"}, {"entity_id": host, "role": "source"}] if host else [],
        "state_delta": {"last_url": url, "last_capture_at": observed_at, "last_crawl": crawl},
        "event_type": "cc.capture",
        "confidence": 0.91,
        "interpretation": {
            "document_id": document.document_id,
            "document": document.provenance(),
            "relations": [relation.to_dict() for relation in relations],
            "admission": {"decisions": decisions, "counts": intake.counts_by_decision()},
            "quarantined": [item.to_dict() for item in intake.quarantined],
        },
        "admission": {
            "decision": decisions[0]["decision"] if decisions else "DEFER",
            "status": "ACCEPTED" if decisions and decisions[0]["decision"] in {"ACCEPT_NEW", "ACCEPT_EXISTING"} else "DEFERRED",
            "confidence": 0.91,
            "policy": "cc-capture-v1",
        },
    }


__all__ = ["interpret_warc_capture"]
