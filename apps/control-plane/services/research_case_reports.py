"""Evidence-grounded, durable completion reports for Feature 034.

The report builder is a read model over canonical case state. It does not turn an
extracted relation into truth: only already-admitted claims whose typed spans resolve
against the immutable raw object can appear in the report's findings section.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from typing import Any, Mapping
from urllib.parse import urlsplit

from sqlalchemy import or_, select, text
from sqlalchemy.exc import SQLAlchemyError

from contracts.evidence_span import EvidenceSpanRef, SpanContractError, StoredDocument
from context_engine.store import ContextStore
from db.schema import Entity, Mention, Observation, RelationClaim, ProcessingResultRow
from services.research_case_service import CaseNotFound, CaseServiceError


class CaseReportError(RuntimeError):
    """A report could not be produced or durably committed."""


def _json(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            result = json.loads(value)
            return dict(result) if isinstance(result, Mapping) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
    return {}


def _list(value: Any) -> list[Any]:
    if isinstance(value, list | tuple):
        return list(value)
    if isinstance(value, str):
        try:
            result = json.loads(value)
            return result if isinstance(result, list) else []
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    return []


def _stamp(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=UTC)
        return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")
    raw = str(value).strip()
    return raw or None


def _digest(payload: Mapping[str, Any]) -> str:
    material = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def _safe_filename(value: str) -> str:
    name = str(value or "artifact").replace("\\", "/").split("/")[-1].strip()
    return name[:255] or "artifact"


class ResearchCaseReportService:
    """Build and persist reports from the real case, processing and evidence stores."""

    def __init__(
        self,
        *,
        context_store: ContextStore,
        session_factory: Any,
        projection_provider: Any,
        object_store: Any | None = None,
    ) -> None:
        if context_store is None or session_factory is None or projection_provider is None:
            raise ValueError("context_store, session_factory and projection_provider are required")
        self._store = context_store
        self._session_factory = session_factory
        self._projection = projection_provider
        self._object_store = object_store

    async def _load_claims(
        self, *, tenant_id: str, investigation_id: str
    ) -> list[RelationClaim]:
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(RelationClaim)
                    .where(
                        RelationClaim.tenant_id == tenant_id,
                        RelationClaim.investigation_id == investigation_id,
                    )
                    .order_by(RelationClaim.created_at.asc(), RelationClaim.relation_id.asc())
                    .limit(5001)
                )
                rows = list(result.scalars().all())
            except SQLAlchemyError as exc:
                raise CaseReportError(
                    f"canonical relation claims unavailable ({type(exc).__name__})"
                ) from exc
        return rows[:5000]

    async def _load_processing_results(
        self, *, tenant_id: str, investigation_id: str
    ) -> list[ProcessingResultRow]:
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(ProcessingResultRow)
                    .where(
                        ProcessingResultRow.tenant_id == tenant_id,
                        ProcessingResultRow.investigation_id == investigation_id,
                    )
                    .order_by(ProcessingResultRow.processed_at.desc(), ProcessingResultRow.processing_result_id.asc())
                    .limit(1000)
                )
                return list(result.scalars().all())
            except SQLAlchemyError as exc:
                raise CaseReportError(
                    f"processing-result ledger unavailable ({type(exc).__name__})"
                ) from exc

    async def _load_evidence_rows(
        self,
        *,
        tenant_id: str,
        investigation_id: str,
        claim_rows: list[RelationClaim],
    ) -> tuple[dict[str, Mention], dict[str, Observation], dict[str, Entity]]:
        mention_ids: set[str] = set()
        observation_ids: set[str] = set()
        entity_ids: set[str] = set()
        for row in claim_rows:
            observation_ids.update(str(item) for item in _list(row.observation_refs) if str(item))
            for binding in _list(row.role_bindings):
                if not isinstance(binding, Mapping):
                    continue
                mention_id = str(binding.get("mention_id") or "")
                if mention_id:
                    mention_ids.add(mention_id)
            for ref in (row.subject_ref, row.object_ref):
                if ref:
                    entity_ids.add(str(ref))

        async with self._session_factory() as session:
            try:
                mentions: dict[str, Mention] = {}
                observations: dict[str, Observation] = {}
                entities: dict[str, Entity] = {}
                if mention_ids:
                    result = await session.execute(
                        select(Mention).where(
                            Mention.tenant_id == tenant_id,
                            Mention.mention_id.in_(sorted(mention_ids)),
                        )
                    )
                    mentions = {str(item.mention_id): item for item in result.scalars().all()}
                # The report inventory is the full case observation ledger, not merely
                # the subset referenced by a relation claim. Include direct claim refs too
                # for legacy observations whose investigation_id was never backfilled.
                observation_scope = [
                    Observation.investigation_id == investigation_id
                ]
                if observation_ids:
                    observation_scope.append(
                        Observation.observation_id.in_(sorted(observation_ids))
                    )
                result = await session.execute(
                    select(Observation).where(
                        Observation.tenant_id == tenant_id,
                        or_(*observation_scope),
                    )
                )
                observations = {
                    str(item.observation_id): item
                    for item in result.scalars().all()
                }
                if entity_ids:
                    result = await session.execute(
                        select(Entity).where(
                            Entity.tenant_id == tenant_id,
                            Entity.entity_id.in_(sorted(entity_ids)),
                        )
                    )
                    entities = {str(item.entity_id): item for item in result.scalars().all()}
                return mentions, observations, entities
            except SQLAlchemyError as exc:
                raise CaseReportError(
                    f"evidence lineage lookup unavailable ({type(exc).__name__})"
                ) from exc

    async def _read_verified_raw(
        self, *, tenant_id: str, raw_ref: str, cache: dict[str, bytes]
    ) -> bytes:
        if raw_ref in cache:
            return cache[raw_ref]
        parsed = urlsplit(raw_ref)
        if parsed.scheme != "s3" or not parsed.netloc or not parsed.path:
            raise CaseReportError("raw reference is not an object-store URI")
        store = self._object_store
        if store is None:
            from storage.s3 import ObjectStore
            store = ObjectStore()
            self._object_store = store
        expected_bucket = str(getattr(store, "raw_bucket", "") or "")
        if parsed.netloc != expected_bucket:
            raise CaseReportError("raw reference points outside the configured raw bucket")
        key = parsed.path.lstrip("/")
        if not key.startswith(f"raw/{tenant_id}/"):
            raise CaseReportError("raw reference is not tenant-scoped")
        body = await store.read_range(bucket=parsed.netloc, key=key, offset=0, length=None)
        cache[raw_ref] = bytes(body)
        return cache[raw_ref]

    async def _ground_mention(
        self,
        *,
        mention: Mention,
        observation: Observation | None,
        tenant_id: str,
        raw_cache: dict[str, bytes],
    ) -> dict[str, Any]:
        offsets = _json(mention.offsets)
        payload = offsets.get("evidence_span")
        if offsets.get("status") != "grounded" or not isinstance(payload, Mapping):
            return {
                "status": "ungrounded",
                "mention_id": mention.mention_id,
                "surface": mention.surface_form,
                "reason": str(offsets.get("reason") or "no verified typed EvidenceSpanRef was persisted"),
            }
        if observation is None or not observation.raw_ref:
            return {
                "status": "ungrounded",
                "mention_id": mention.mention_id,
                "surface": mention.surface_form,
                "reason": "the source observation or raw object reference is missing",
            }
        try:
            span = EvidenceSpanRef.from_dict(payload)
            body = await self._read_verified_raw(
                tenant_id=tenant_id, raw_ref=str(observation.raw_ref), cache=raw_cache
            )
            document = StoredDocument(data=body, encoding="utf-8")
            blob_check = span.check_blob(document)
            if blob_check.status != "fresh":
                return {
                    "status": "stale",
                    "mention_id": mention.mention_id,
                    "surface": mention.surface_form,
                    "reason": "the span digest differs from the persisted raw object",
                    "declared_digest": blob_check.declared_digest,
                    "stored_digest": blob_check.stored_digest,
                }
            resolved = span.resolve(document)
            quote = str(resolved.value)
            if quote != str(mention.surface_form):
                return {
                    "status": "ungrounded",
                    "mention_id": mention.mention_id,
                    "surface": mention.surface_form,
                    "reason": "resolved bytes no longer match the canonical mention surface",
                }
            return {
                "status": "grounded",
                "mention_id": mention.mention_id,
                "surface": quote,
                "exact_quote": quote[:500],
                "observation_id": str(observation.observation_id),
                "capture_id": str(observation.provenance.get("capture_id", "")) if isinstance(observation.provenance, Mapping) else "",
                "source_url": str(observation.uri or span.source_locator.uri),
                "raw_ref": str(observation.raw_ref),
                "blob_digest": span.blob_digest,
                "span": span.as_dict(),
                "captured_at": _stamp(observation.created_at),
                "published_at": None,
            }
        except Exception as exc:  # noqa: BLE001 - source/object-store failure means ungrounded, not factual
            return {
                "status": "ungrounded",
                "mention_id": mention.mention_id,
                "surface": mention.surface_form,
                "reason": f"evidence span verification failed: {type(exc).__name__}: {exc}"[:400],
            }

    async def generate(
        self, *, case_id: str, tenant_id: str, actor_id: str
    ) -> dict[str, Any]:
        context = await self._store.get_context(case_id)
        if context is None or context.tenant_id != tenant_id:
            raise CaseNotFound("case not found")
        if not str(actor_id or "").strip():
            raise CaseReportError("report actor is required")
        metadata = await self._store.get_person_case_metadata(case_id)
        if metadata is None or metadata.get("tenant_id") != tenant_id:
            raise CaseNotFound("case not found")

        coverage = await self._projection.coverage_ledger(
            case_id=case_id, tenant_id=tenant_id
        )
        claim_rows = await self._load_claims(
            tenant_id=tenant_id, investigation_id=context.investigation_id
        )
        mentions, observations, entities = await self._load_evidence_rows(
            tenant_id=tenant_id,
            investigation_id=context.investigation_id,
            claim_rows=claim_rows,
        )
        processing_rows = await self._load_processing_results(
            tenant_id=tenant_id, investigation_id=context.investigation_id
        )
        artifact_result = await self._fetch_artifacts(case_id=case_id, tenant_id=tenant_id)

        raw_cache: dict[str, bytes] = {}
        claim_views: list[dict[str, Any]] = []
        findings: list[dict[str, Any]] = []
        claims_by_status: Counter[str] = Counter()
        for claim in claim_rows:
            stored_status = str(claim.status or "unknown")
            claims_by_status[stored_status.upper()] += 1
            obs_refs = [str(ref) for ref in _list(claim.observation_refs) if str(ref)]
            binding_views: list[dict[str, Any]] = []
            grounded_spans: list[dict[str, Any]] = []
            for binding in _list(claim.role_bindings):
                if not isinstance(binding, Mapping):
                    continue
                mention_id = str(binding.get("mention_id") or "")
                mention = mentions.get(mention_id)
                observation = observations.get(str(mention.observation_id)) if mention is not None else None
                if mention is None:
                    binding_views.append({
                        "role": str(binding.get("role") or "unknown"),
                        "mention_id": mention_id,
                        "status": "ungrounded",
                        "reason": "canonical mention row is missing",
                    })
                    continue
                grounded = await self._ground_mention(
                    mention=mention,
                    observation=observation,
                    tenant_id=tenant_id,
                    raw_cache=raw_cache,
                )
                grounded["role"] = str(binding.get("role") or "unknown")
                binding_views.append(grounded)
                if grounded["status"] == "grounded":
                    grounded_spans.append(grounded)

            subject_entity = entities.get(str(claim.subject_ref))
            object_entity = entities.get(str(claim.object_ref))
            all_bound = bool(binding_views) and all(
                item.get("status") == "grounded" for item in binding_views
            )
            admitted = stored_status.upper() in {"ADMITTED", "ACCEPTED"}
            finding_eligible = admitted and all_bound
            claim_view = {
                "claim_id": str(claim.relation_id),
                "logical_claim_id": str(claim.logical_relation_id),
                "revision_number": int(claim.revision_number or 1),
                "predicate": str(claim.relation_type),
                "subject": {
                    "entity_id": str(claim.subject_ref),
                    "label": str(subject_entity.canonical_name) if subject_entity is not None else str(claim.subject_ref),
                    "admission_state": "materialized" if subject_entity is not None else "unresolved",
                },
                "object": {
                    "entity_id": str(claim.object_ref),
                    "label": str(object_entity.canonical_name) if object_entity is not None else str(claim.object_ref),
                    "admission_state": "materialized" if object_entity is not None else "unresolved",
                },
                "status": stored_status,
                "confidence": float(claim.confidence or 0.0),
                "valid_time": {
                    "from": _stamp(claim.valid_from),
                    "until": _stamp(claim.valid_to),
                },
                "knowledge_time": {
                    "from": _stamp(claim.known_from),
                    "until": _stamp(claim.known_until),
                },
                "published_at": _stamp(claim.published_at),
                "observed_at": _stamp(claim.observed_at),
                "observation_refs": obs_refs,
                "evidence_spans": binding_views,
                "grounded": all_bound,
                "factual_assertion_eligible": finding_eligible,
                "disposition": (
                    "admitted_and_grounded"
                    if finding_eligible
                    else "needs_admission_review"
                    if not admitted
                    else "needs_evidence_review"
                ),
                "contradicts": [str(item) for item in _list(claim.contradicts)],
            }
            claim_views.append(claim_view)
            if finding_eligible:
                findings.append({
                    "finding_id": str(claim.relation_id),
                    "statement": (
                        f"{claim_view['subject']['label']} — {claim_view['predicate']} — "
                        f"{claim_view['object']['label']}"
                    ),
                    "claim_ref": str(claim.relation_id),
                    "evidence_spans": grounded_spans,
                    "valid_time": claim_view["valid_time"],
                    "knowledge_time": claim_view["knowledge_time"],
                })

        obligation_rows = list(await self._store.obligations(case_id))
        open_obligations = [
            item for item in obligation_rows
            if str(getattr(item.status, "value", item.status)).upper()
            in {"OPEN", "PROPOSED", "BLOCKED"}
        ]
        plan_revisions = [
            revision for revision in await self._store.revisions(case_id)
            if isinstance(revision.snapshot, Mapping) and revision.snapshot.get("plan_digest")
        ]
        latest_plan = _json(plan_revisions[-1].snapshot) if plan_revisions else {}
        source_ids = sorted({
            str(row.source_id)
            for row in observations.values()
            if row.source_id
        })
        source_urls = sorted({
            str(row.uri)
            for row in observations.values()
            if row.uri
        })
        processing_summary = []
        for row in processing_rows:
            normalization = _json(row.normalization)
            interpretation = _json(row.interpretation)
            processing_summary.append({
                "processing_result_id": row.processing_result_id,
                "observation_id": row.observation_id,
                "capture_id": row.capture_id,
                "consumer": row.consumer,
                "consumer_version": row.consumer_version,
                "status": row.status,
                "processed_at": _stamp(row.processed_at),
                "record_count": int(row.record_count or 0),
                "mention_count": int(row.mention_count or 0),
                "truncated": bool(row.truncated),
                "failure_code": row.failure_code,
                "normalization": {
                    "status": normalization.get("status"),
                    "engine": normalization.get("engine"),
                    "engine_version": normalization.get("engine_version"),
                    "pipeline_digest": normalization.get("pipeline_digest"),
                    "record_count": normalization.get("record_count"),
                } if normalization else None,
                "interpretation": {
                    "status": interpretation.get("status"),
                    "persisted": interpretation.get("persisted"),
                    "relations": interpretation.get("relations"),
                    "entities": interpretation.get("entities"),
                    "unresolved": interpretation.get("unresolved"),
                    "detail": interpretation.get("detail"),
                } if interpretation else None,
            })

        blocked = (
            coverage.get("overall_state") in {"BLOCKED_CAPABILITY", "NOT_PLANNED"}
            and not observations
            and not claim_rows
        )
        all_required_resolved = bool(obligation_rows) and not open_obligations
        all_claims_admitted_and_grounded = all(
            str(row.status or "").upper() in {"ADMITTED", "ACCEPTED"}
            and claim["grounded"]
            for row, claim in zip(claim_rows, claim_views, strict=True)
        )
        if blocked:
            report_status = "BLOCKED"
        elif all_required_resolved and all_claims_admitted_and_grounded:
            report_status = "COMPLETE"
        else:
            report_status = "PARTIAL"

        report_body: dict[str, Any] = {
            "schema": "cognitive.research-case-completion-report/v1",
            "case": {
                "case_id": case_id,
                "tenant_id": tenant_id,
                "investigation_id": context.investigation_id,
                "title": context.title,
                "purpose_code": metadata.get("purpose_code"),
                "purpose_text": context.question,
                "basis_ref": metadata.get("basis_ref"),
                "launch_profile": metadata.get("launch_profile"),
                "scope_digest": metadata.get("scope_digest"),
                "scope_revision": int(metadata.get("scope_revision", 0)),
                "policy_revision": str(context.policy_snapshot_ref),
                "approved": bool(metadata.get("approved", False)),
                "expires_at": metadata.get("expires_at"),
            },
            "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "status": report_status,
            "summary": {
                "findings": len(findings),
                "relation_claim_candidates": len(claim_rows),
                "admitted_grounded_claims": len(findings),
                "unreviewed_or_ungrounded_claims": sum(
                    not item["factual_assertion_eligible"] for item in claim_views
                ),
                "open_obligations": len(open_obligations),
                "obligations": len(obligation_rows),
                "observations": len(observations),
                "processing_results": len(processing_rows),
                "static_artifacts": len(artifact_result["artifacts"]),
            },
            "findings": findings,
            "relation_claims": claim_views,
            "obligations": [
                {
                    "obligation_id": item.obligation_id,
                    "question": item.question,
                    "state": str(getattr(item.status, "value", item.status)),
                    "required_capabilities": list(item.required_capabilities),
                    "satisfaction_criteria": list(item.satisfaction_criteria),
                    "rationale": item.rationale,
                }
                for item in obligation_rows
            ],
            "source_inventory": {
                "configured_sources": sorted(str(item) for item in metadata.get("allowed_source_ids", [])),
                "observed_source_ids": source_ids,
                "observed_urls": source_urls,
                "actual_observations": [
                    {
                        "observation_id": str(row.observation_id),
                        "source_id": str(row.source_id or ""),
                        "uri": str(row.uri or ""),
                        "raw_ref": str(row.raw_ref),
                        "content_digest": str(row.content_hash),
                        "captured_at": _stamp(row.created_at),
                    }
                    for row in sorted(
                        observations.values(),
                        key=lambda item: (item.created_at or datetime.min.replace(tzinfo=UTC), item.observation_id),
                    )
                ],
            },
            "coverage": coverage,
            "plan": {
                "plan_digest": latest_plan.get("plan_digest"),
                "plan_state": latest_plan.get("plan_state"),
                "capability_gaps": _list(latest_plan.get("capability_gaps")),
                "proposed_action_refs": _list(latest_plan.get("proposed_action_refs")),
            },
            "processing": processing_summary,
            "static_artifacts": artifact_result["artifacts"],
            "limitations": [
                "Only claims with durable ADMITTED/ACCEPTED status and a verified typed evidence span are included as factual findings.",
                "Extracted or contested relation claims are shown as review candidates; they are not presented as established facts.",
                "A source not listed as queried in source_inventory was not queried by this case run.",
                "A no-result response is a bounded acquisition outcome, not proof that the information does not exist.",
                "Unsupported claim families, disabled sources, outages, parser limitations, and incomplete obligations remain explicit.",
            ],
            "source_of_truth": {
                "case": "canonical ContextStore + person_case_metadata",
                "claims": "postgres:relation_claim",
                "mentions_and_spans": "postgres:mentions.offsets.evidence_span",
                "observations": "postgres:observations",
                "processing": "postgres:processing_results",
                "artifacts": "postgres:person_case_artifacts",
            },
            "created_by": actor_id,
        }
        report_digest = _digest(report_body)
        report_id = "RPT-" + hashlib.sha256(
            f"{tenant_id}|{case_id}|{report_digest}".encode("utf-8")
        ).hexdigest()[:32]
        payload = {**report_body, "report_id": report_id, "report_digest": report_digest}

        try:
            async with self._session_factory() as session:
                async with session.begin():
                    await session.execute(
                        text(
                            """
                            INSERT INTO person_case_reports (
                                report_id, tenant_id, case_id, scope_digest, report_digest,
                                status, payload, created_by
                            ) VALUES (
                                :report_id, :tenant_id, :case_id, :scope_digest, :report_digest,
                                :status, CAST(:payload AS jsonb), :created_by
                            )
                            ON CONFLICT (tenant_id, case_id, report_digest) DO NOTHING
                            """
                        ),
                        {
                            "report_id": report_id,
                            "tenant_id": tenant_id,
                            "case_id": case_id,
                            "scope_digest": metadata["scope_digest"],
                            "report_digest": report_digest,
                            "status": report_status,
                            "payload": json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
                            "created_by": actor_id,
                        },
                    )
                    stored = (
                        await session.execute(
                            text(
                                """
                                SELECT report_id, tenant_id, case_id, scope_digest, report_digest, status, payload
                                FROM person_case_reports
                                WHERE tenant_id = :tenant_id AND case_id = :case_id
                                  AND report_digest = :report_digest
                                """
                            ),
                            {"tenant_id": tenant_id, "case_id": case_id, "report_digest": report_digest},
                        )
                    ).mappings().first()
                    if stored is None or stored["report_id"] != report_id or stored["scope_digest"] != metadata["scope_digest"]:
                        raise CaseReportError("durable report write could not be verified")
                    stored_payload = _json(stored["payload"])
                    if stored_payload.get("report_digest") != report_digest:
                        raise CaseReportError("stored report payload digest does not match the report row")
        except CaseReportError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise CaseReportError(f"report persistence failed: {type(exc).__name__}: {exc}") from exc

        await self._store.put_person_case_metadata(
            case_id=case_id,
            tenant_id=tenant_id,
            purpose_code=str(metadata["purpose_code"]),
            basis_ref=str(metadata["basis_ref"]),
            launch_profile=str(metadata["launch_profile"]),
            claim_families=list(metadata.get("claim_families", [])),
            allowed_source_ids=list(metadata.get("allowed_source_ids", [])),
            denied_claim_families=list(metadata.get("denied_claim_families", [])),
            scope_digest=str(metadata["scope_digest"]),
            scope_revision=int(metadata["scope_revision"]),
            approved=bool(metadata.get("approved", False)),
            budget_ref=metadata.get("budget_ref"),
            expires_at=metadata.get("expires_at"),
            valid_time=dict(metadata.get("valid_time", {})),
            jurisdictions=list(metadata.get("jurisdictions", [])),
            subject_anchors=list(metadata.get("subject_anchors", [])),
            context_amendments=list(metadata.get("context_amendments", [])),
            dynamic_invariant_anchors=list(metadata.get("dynamic_invariant_anchors", [])),
            static_artifact_refs=list(metadata.get("static_artifact_refs", [])),
            latest_report_ref={
                "report_id": report_id,
                "report_digest": report_digest,
                "status": report_status,
                "created_at": payload["generated_at"],
            },
        )
        from domain.investigation_context import ContextRevision

        revision_number = await self._store.next_revision_number(case_id)
        revision = ContextRevision(
            context_id=case_id,
            revision=revision_number,
            parent_revision=revision_number - 1,
            state=context.state,
            snapshot={
                "context": context.to_dict(),
                "report_ref": {
                    "report_id": report_id,
                    "report_digest": report_digest,
                    "status": report_status,
                },
                "scope_digest": metadata.get("scope_digest"),
                "scope_revision": metadata.get("scope_revision"),
            },
            operator_actions=(actor_id, "completion_report_generated"),
            rules_version="feature-034-report-v1",
            mode="deterministic",
        )
        await self._store.append_revision(revision)
        return payload

    async def get_report(
        self, *, case_id: str, report_id: str, tenant_id: str
    ) -> dict[str, Any]:
        context = await self._store.get_context(case_id)
        if context is None or context.tenant_id != tenant_id:
            raise CaseNotFound("case not found")
        async with self._session_factory() as session:
            result = await session.execute(
                text(
                    """
                    SELECT payload FROM person_case_reports
                    WHERE tenant_id = :tenant_id AND case_id = :case_id AND report_id = :report_id
                    """
                ),
                {"tenant_id": tenant_id, "case_id": case_id, "report_id": report_id},
            )
            row = result.mappings().first()
        if row is None:
            raise CaseNotFound("report not found")
        return _json(row["payload"])

    async def _fetch_artifacts(self, *, case_id: str, tenant_id: str) -> dict[str, Any]:
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    text(
                        """
                        SELECT artifact_id, capture_id, observation_id, raw_ref, content_digest,
                               byte_length, content_type, filename, caption, artifact_kind,
                               uploaded_by, created_at
                        FROM person_case_artifacts
                        WHERE tenant_id = :tenant_id AND case_id = :case_id
                        ORDER BY created_at ASC, artifact_id ASC
                        """
                    ),
                    {"tenant_id": tenant_id, "case_id": case_id},
                )
                rows = [dict(row) for row in result.mappings().all()]
            except SQLAlchemyError as exc:
                raise CaseReportError(
                    f"static artifact ledger unavailable ({type(exc).__name__})"
                ) from exc
        return {
            "case_id": case_id,
            "count": len(rows),
            "artifacts": [
                {
                    "artifact_id": str(row["artifact_id"]),
                    "capture_id": str(row["capture_id"]),
                    "observation_id": str(row["observation_id"]),
                    "raw_ref": str(row["raw_ref"]),
                    "content_digest": str(row["content_digest"]),
                    "byte_length": int(row["byte_length"]),
                    "content_type": str(row["content_type"]),
                    "filename": _safe_filename(str(row["filename"])),
                    "caption": str(row.get("caption") or ""),
                    "artifact_kind": str(row.get("artifact_kind") or "static_attachment"),
                    "uploaded_by": str(row["uploaded_by"]),
                    "created_at": _stamp(row["created_at"]),
                }
                for row in rows
            ],
            "source_of_truth": "postgres:person_case_artifacts",
        }
