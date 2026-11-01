"""Governed Layer-0 public-document harvesting for approved research cases.

The service never accepts arbitrary URLs. It starts from discovery leads projected
from the current tenant/case scope, reserves a durable budget, fetches only public
HTTPS pages that permit the named crawler in robots.txt, and writes raw bytes plus
deterministic stage outputs through the canonical Acquisition ArtifactSink.

All output stays DISCOVERY_ONLY. This service does not create claims, identity
matches, private contact records, or evidence-satisfaction events.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from datetime import UTC, datetime
from typing import Any, Mapping
from urllib.parse import urlsplit

from context_engine.person_case_profile import PUBLIC_PROFESSIONAL, PUBLIC_ROLE_REVIEW
from services.research_case_service import CaseNotFound, CaseNotApproved


class ZeroLayerCaseError(RuntimeError):
    """A public-document harvest was refused or could not complete safely."""


class ZeroLayerCaseService:
    MAX_LEADS = 25
    MAX_BYTES_PER_PAGE = 2_000_000
    MAX_SECONDS_PER_PAGE = 20

    def __init__(
        self,
        *,
        case_service: Any,
        projection_provider: Any,
        budget_service: Any,
        policy: Any,
        context_store: Any,
        session_factory: Any,
        artifact_sink: Any | None = None,
        transport_factory: Any | None = None,
    ) -> None:
        required = (case_service, projection_provider, budget_service, policy, context_store, session_factory)
        if any(item is None for item in required):
            raise ValueError("zero-layer requires case, projection, policy, budget and durable store services")
        self._case_service = case_service
        self._projection = projection_provider
        self._budget = budget_service
        self._policy = policy
        self._context_store = context_store
        self._session_factory = session_factory
        self._artifact_sink = artifact_sink
        self._transport_factory = transport_factory
        self._sink_lock = asyncio.Lock()

    @staticmethod
    def _request_key(value: str) -> str:
        token = str(value or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9:_-]{8,160}", token):
            raise ZeroLayerCaseError("idempotency_key must be 8-160 ASCII letters, digits, ':' '_' or '-'")
        return token

    @staticmethod
    def _host(url: str) -> str:
        parsed = urlsplit(url)
        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
        ):
            raise ZeroLayerCaseError("only public HTTPS URLs on port 443 may be processed")
        host = parsed.hostname.encode("idna").decode("ascii").lower()
        if host == "localhost" or host.endswith(".local"):
            raise ZeroLayerCaseError("local hostnames are not public sources")
        return host

    async def _get_artifact_sink(self) -> Any:
        if self._artifact_sink is not None:
            return self._artifact_sink
        async with self._sink_lock:
            if self._artifact_sink is not None:
                return self._artifact_sink
            # Imports stay lazy so the API can boot in a degraded environment. The
            # attempt itself fails closed if canonical evidence dependencies are absent.
            from artifact_sink import ArtifactSink
            from dispatcher.kafka_producer import KafkaProducer
            from evidence_writer import PostgresAcquisitionEvidenceWriter
            from events.content_router import ContentRouter
            from events.observation_gate import ObservationGate
            from storage.s3 import ObjectStore

            store = ObjectStore()
            producer = KafkaProducer()
            gate = ObservationGate(
                store=store,
                router=ContentRouter(max_bytes=self.MAX_BYTES_PER_PAGE),
                producer=producer,
            )
            self._artifact_sink = ArtifactSink(
                gate=gate,
                store=store,
                source_family="public_web_document",
                recorded_by="zero-layer-public-document",
                evidence_writer=PostgresAcquisitionEvidenceWriter(self._session_factory),
            )
            return self._artifact_sink

    async def harvest(
        self,
        *,
        case_id: str,
        tenant_id: str,
        actor_id: str,
        lead_ids: list[str],
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Process selected leads from the current case projection; never accept raw URLs."""
        key = self._request_key(idempotency_key)
        selected_ids = sorted(set(str(item).strip() for item in lead_ids if str(item).strip()))
        if not selected_ids or len(selected_ids) > self.MAX_LEADS:
            raise ZeroLayerCaseError(f"select between 1 and {self.MAX_LEADS} current discovery leads")

        case = await self._case_service.get_case(case_id=case_id, tenant_id=tenant_id)
        if not case.get("approved"):
            raise CaseNotApproved("case must be approved before public-document processing")
        launch_profile = str(case.get("launch_profile") or "")
        if launch_profile not in {PUBLIC_PROFESSIONAL, PUBLIC_ROLE_REVIEW}:
            raise ZeroLayerCaseError("zero-layer public-person processing is limited to public professional/role cases")

        context = await self._context_store.get_context(case_id)
        if context is None or str(getattr(context, "tenant_id", "")) != tenant_id:
            raise CaseNotFound(f"case {case_id} not found")
        metadata = await self._context_store.get_person_case_metadata(case_id)
        if not isinstance(metadata, Mapping) or metadata.get("tenant_id") != tenant_id or not metadata.get("approved"):
            raise CaseNotApproved("durable case approval is absent or belongs to another tenant")
        await self._case_service._validate_current_scope(context=context, meta=metadata)

        expiry = metadata.get("expires_at")
        if expiry:
            parsed_expiry = datetime.fromisoformat(str(expiry).replace("Z", "+00:00"))
            if parsed_expiry.tzinfo is None:
                parsed_expiry = parsed_expiry.replace(tzinfo=UTC)
            if parsed_expiry <= datetime.now(UTC):
                raise ZeroLayerCaseError("case scope has expired")

        allowed_sources = set(str(item) for item in metadata.get("allowed_source_ids", []))
        discovery_source = "searxng_public_search"
        page_source = "public_web_document_fetch"
        if discovery_source not in allowed_sources or page_source not in allowed_sources:
            raise ZeroLayerCaseError(
                "the approved scope must include both searxng_public_search and public_web_document_fetch"
            )

        discovery_eligibility = self._policy.source_eligible(
            source_id=discovery_source,
            launch_profile=launch_profile,
        )
        page_eligibility = self._policy.source_eligible(
            source_id=page_source,
            launch_profile=launch_profile,
        )
        if not discovery_eligibility.eligible:
            raise ZeroLayerCaseError(f"discovery source blocked: {discovery_eligibility.detail}")
        if not page_eligibility.eligible:
            raise ZeroLayerCaseError(f"public document source blocked: {page_eligibility.detail}")
        page_profile = self._policy._sources.get(page_source, {})
        declared_egress = set(str(host).strip() for host in page_profile.get("egress_hosts", []))
        if "public_https_from_current_discovery_projection" not in declared_egress:
            raise ZeroLayerCaseError("public-page source lacks the case-derived public HTTPS egress declaration")

        projected = await self._projection.discovery_leads(case_id=case_id, tenant_id=tenant_id)
        current_leads = {
            str(lead.get("lead_id")): lead
            for lead in projected.get("leads", [])
            if isinstance(lead, Mapping)
        }
        missing = sorted(set(selected_ids) - set(current_leads))
        if missing:
            raise ZeroLayerCaseError(
                "one or more selected leads are absent from the current approved case projection"
            )

        selected = [current_leads[item] for item in selected_ids]
        urls: list[str] = []
        seed_context: dict[str, dict[str, str]] = {}
        for lead in selected:
            if (
                lead.get("result_role") != "DISCOVERY_ONLY"
                or lead.get("claim_admission_allowed") is not False
                or lead.get("state") != "UNVERIFIED_DISCOVERY_LEAD"
                or str(lead.get("source_id") or "") != discovery_source
            ):
                raise ZeroLayerCaseError("selected lead does not satisfy the unverified discovery contract")
            url = str(lead.get("url") or "").strip()
            self._host(url)
            urls.append(url)
            seed_context[url] = {
                "parent_observation_id": str(lead.get("observation_id") or lead["lead_id"]),
                "source_id": discovery_source,
            }

        policy_digest = str(self._policy.policy_digest)
        scope_digest = str(metadata["scope_digest"])
        scope_revision = int(metadata["scope_revision"])
        request_digest = "sha256:" + hashlib.sha256(
            (tenant_id + "|" + case_id + "|" + scope_digest + "|" + policy_digest + "|" +
             "|".join(selected_ids)).encode("utf-8")
        ).hexdigest()
        reservation = await self._budget.reserve_case(
            budget_ref=str(metadata.get("budget_ref") or ""),
            tenant_id=tenant_id,
            case_id=case_id,
            investigation_id=str(getattr(context, "investigation_id", context.context_id)),
            idempotency_key=key,
            scope_digest=scope_digest,
            policy_digest=policy_digest,
            requests=len(urls),
            raw_bytes=len(urls) * self.MAX_BYTES_PER_PAGE,
            records=len(urls) * 8,
            concurrency=1,
            wall_seconds=len(urls) * self.MAX_SECONDS_PER_PAGE,
            source_refs=(page_source,),
            request_digest=request_digest,
        )
        reservation_id = str(reservation["reservation_id"])
        run_id = "ZLR-" + hashlib.sha256(
            (case_id + "|" + key + "|" + request_digest).encode("utf-8")
        ).hexdigest()[:28]

        if self._transport_factory is None:
            from zero.harvesters.transport import SecurePublicTransport
            transport = SecurePublicTransport(
                max_response_bytes=self.MAX_BYTES_PER_PAGE,
                minimum_host_interval_s=1.0,
            )
        else:
            transport = self._transport_factory()
        for lead, url in zip(selected, urls, strict=True):
            transport.set_source_metadata(
                url,
                parent_observation_id=str(lead.get("observation_id") or lead["lead_id"]),
                discovery_source_id=discovery_source,
                action_ref=str(lead.get("action_ref") or ""),
            )

        from zero.evidence_sink import CanonicalArtifactSink
        from zero.harvest_wave import HarvestWave
        from zero.harvesters.public_document import PublicDocumentHarvester
        from zero.harvesters.registry import HarvesterRegistry
        from zero.observation_gate import ZeroLayerGate
        from zero.type_detector import TypeDetector

        registry = HarvesterRegistry()
        registry.register(PublicDocumentHarvester())
        wave = HarvestWave(
            detector=TypeDetector(),
            registry=registry,
            gate=ZeroLayerGate(),
            transport=transport,
            max_depth=1,
            min_new_seeds=0,
            enable_enrichment=False,
            seed_context=seed_context,
        )
        artifact_sink = await self._get_artifact_sink()
        canonical_sink = CanonicalArtifactSink(
            artifact_sink=artifact_sink,
            case_id=case_id,
            scope_digest=scope_digest,
            scope_revision=scope_revision,
            run_id=run_id,
            actor_id=actor_id,
        )

        try:
            summaries, accepted = await wave.run_and_persist(
                urls,
                evidence_sink=canonical_sink,
                tenant_id=tenant_id,
                investigation_id=str(context.investigation_id),
            )
            failures = list(getattr(transport, "failures", ()))
            captures = list(getattr(transport, "captures", ()))
            await self._budget.mark_reservation(
                reservation_id=reservation_id,
                state="PUBLISHED",
                outcome={
                    "run_id": run_id,
                    "selected_leads": selected_ids,
                    "captured_pages": len(captures),
                    "failed_pages": len(failures),
                    "accepted_artifacts": len(accepted),
                    "observation_refs": [
                        str(item.observation_id) for item in accepted
                        if getattr(item, "observation_id", None)
                    ],
                    "result_role": "DISCOVERY_ONLY",
                },
            )
        except Exception as exc:
            await self._budget.mark_reservation(
                reservation_id=reservation_id,
                state="FAILED",
                outcome={
                    "run_id": run_id,
                    "failed_stage": "zero_layer_public_document_capture",
                    "error_type": type(exc).__name__,
                },
            )
            raise ZeroLayerCaseError(
                f"public document processing failed at the canonical evidence boundary ({type(exc).__name__})"
            ) from exc

        return {
            "case_id": case_id,
            "run_id": run_id,
            "scope_digest": scope_digest,
            "scope_revision": scope_revision,
            "budget_reservation_id": reservation_id,
            "selected_leads": len(selected),
            "captured_pages": len(captures),
            "failed_pages": len(failures),
            "failures": failures,
            "waves": [item.as_dict() for item in summaries],
            "observation_refs": [
                str(item.observation_id) for item in accepted
                if getattr(item, "observation_id", None)
            ],
            "result_role": "DISCOVERY_ONLY",
            "claim_admission_allowed": False,
            "notice": (
                "Pages and deterministic metadata were captured for analyst triage only. "
                "They are not admitted claims and do not satisfy research obligations."
            ),
        }
