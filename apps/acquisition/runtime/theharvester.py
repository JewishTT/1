"""Authorized-domain runtime for a separately deployed theHarvester service.

The only enabled upstream capability is passive subdomain discovery. Outputs
are normalized into discovery-only AcquisitionArtifacts and then flow through
the existing ArtifactSink/ObservationGate path. IPs and ASNs are retained as
non-expanding external references; no result schedules another target.
"""
from __future__ import annotations

import asyncio
import json
import threading
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from domain.acquisition_artifact import AcquisitionArtifact

from industry_adapters.theharvester import (
    AdapterError,
    AuthorizationError,
    AuthorizationScope,
    TheHarvesterApiClient,
)
from runtime import CostEstimate, RuntimeError_, RuntimeHealth


class TheHarvesterRuntime:
    """One finite, authorized, passive subdomain-enumeration runtime."""

    runtime_ref = "theharvester"
    execution_class = "api/http"
    requires_connector_config = False

    def __init__(
        self,
        *,
        client: TheHarvesterApiClient,
        authorization: AuthorizationScope,
        producer_version: str = "rest-adapter-v1",
        max_records: int = 10_000,
        max_output_bytes: int = 16 * 1024 * 1024,
    ) -> None:
        if not producer_version.strip():
            raise ValueError("producer_version is required")
        if not 1 <= max_records <= 10_000:
            raise ValueError("max_records must be in [1, 10000]")
        if not 1024 <= max_output_bytes <= 16 * 1024 * 1024:
            raise ValueError("max_output_bytes is outside the supported bound")
        self._client = client
        self._authorization = authorization
        self._producer_version = producer_version
        self._max_records = max_records
        self._max_output_bytes = max_output_bytes

    def capabilities(self) -> list[str]:
        return ["http", "passive-discovery", "json-output", "bounded-run"]

    def estimate(self, task: dict[str, Any]) -> CostEstimate:
        return CostEstimate(
            expected_artifacts=min(self._max_records, 500) + 1,
            expected_bytes=min(self._max_output_bytes, 2 * 1024 * 1024),
            expected_seconds=600,
        )

    async def probe(self) -> RuntimeHealth:
        """Report that the runtime is configured without echoing credentials."""
        try:
            self._authorization.assert_active()
            return RuntimeHealth(
                ready=True,
                detail="operator allowlist configured; upstream REST reachability is checked on first run",
                checks={
                    "authorization_ref_present": bool(self._authorization.authorization_ref),
                    "allowed_domain_count": len(self._authorization.allowed_domains),
                    "tenant_bound": True,
                    "expiry": self._authorization.expires_at.isoformat(),
                    "network_probe": "deferred",
                },
                runtime_ref=self.runtime_ref,
            )
        except AuthorizationError as exc:
            return RuntimeHealth(
                ready=False,
                detail=str(exc),
                checks={"code": "authorization_scope_expired"},
                runtime_ref=self.runtime_ref,
            )

    async def aclose(self) -> None:
        # urllib's per-request responses are always closed inside the client.
        return None

    async def acquire(self, task: dict[str, Any]):
        """Stream one sanitized run manifest followed by its normalized records."""
        tenant_id = str(task.get("tenant_id") or "").strip()
        if tenant_id != self._authorization.tenant_id:
            raise RuntimeError_(
                "authorization_tenant_mismatch",
                "theHarvester runtime is bound to a different tenant",
            )
        result_role = str(task.get("result_role") or "EVIDENCE").upper()
        if result_role != "DISCOVERY_ONLY":
            raise RuntimeError_(
                "theharvester_result_role_forbidden",
                "theHarvester domain results must be dispatched with result_role=DISCOVERY_ONLY",
            )
        target = str(task.get("query") or "").strip()
        if not target:
            raise RuntimeError_("theharvester_domain_missing", "task.query must contain an authorized DNS domain")
        try:
            target = self._authorization.assert_domain(target)
        except AuthorizationError as exc:
            raise RuntimeError_("authorization_scope_refused", str(exc)) from exc
        task_id = str(task.get("task_id") or "")
        source_id = str(task.get("source_id") or "")
        if not task_id or not source_id:
            raise RuntimeError_("theharvester_task_binding_missing", "task_id and source_id are required")

        stop_event = threading.Event()
        run = asyncio.create_task(
            asyncio.to_thread(
                self._client.run_authorized_domain,
                target,
                self._authorization,
                limit=min(self._max_records, 10_000),
                source_workers=3,
                stop_event=stop_event,
            )
        )
        try:
            evidence = await run
        except asyncio.CancelledError:
            stop_event.set()
            raise
        except AuthorizationError as exc:
            raise RuntimeError_("authorization_scope_refused", str(exc)) from exc
        except AdapterError as exc:
            raise RuntimeError_("theharvester_upstream_error", str(exc)) from exc
        except ValueError as exc:
            raise RuntimeError_("theharvester_input_invalid", str(exc)) from exc

        if len(evidence.records) > self._max_records:
            raise RuntimeError_(
                "resource_limit_exceeded",
                f"normalized result count exceeded {self._max_records}",
            )

        completed_at = _parse_time(evidence.completed_at) or datetime.now(UTC)
        target_uri = f"{self._client.base_url}/api/v1/runs/{quote(evidence.run_id, safe='')}"
        capture_locator = "blob"
        manifest = {
            "schema": "cognitive.theharvester.discovery/v1",
            "run_id": evidence.run_id,
            "target": target,
            "authorization_ref": self._authorization.authorization_ref,
            "lifecycle_status": evidence.lifecycle_status,
            "evidence_status": evidence.evidence_status,
            "may_support_qualified_absence": evidence.may_support_qualified_absence,
            "record_count": len(evidence.records),
            # Keep the normalized record array inside the durable parent capture so
            # json:records[N] remains resolvable during parser replay.
            "records": [
                {
                    "kind": record.kind,
                    "value": record.value,
                    "source_ids": list(record.source_ids),
                    "scope_class": record.scope_class,
                    "expandable": record.expandable,
                    "result_role": "DISCOVERY_ONLY",
                }
                for record in evidence.records
            ],
            "filtered_counts": dict(sorted(evidence.filtered_counts.items())),
            "source_outcomes": list(evidence.source_outcomes),
            "submitted_at": evidence.submitted_at,
            "completed_at": completed_at.isoformat(),
            "result_role": "DISCOVERY_ONLY",
        }
        manifest_bytes = _canonical_json(manifest)
        if len(manifest_bytes) > self._max_output_bytes:
            raise RuntimeError_("resource_limit_exceeded", "run manifest exceeded the output-size budget")

        # A sanitized manifest is the capture. Raw upstream JSONL is never copied
        # across this trust boundary; excluded person/email/breach rows do not enter
        # the canonical evidence store.
        yield AcquisitionArtifact(
            task_id=task_id,
            source_id=source_id,
            worker_ref="http",
            target_uri=target_uri,
            locator=capture_locator,
            body=manifest_bytes,
            content_type="application/json",
            fetched_at=completed_at,
            transport="http",
            producer="theHarvester",
            producer_version=self._producer_version,
            metadata={
                "runtime_ref": self.runtime_ref,
                "authorization_ref": self._authorization.authorization_ref,
                "domain_scope": target,
                "result_role": "DISCOVERY_ONLY",
                "record_count": len(evidence.records),
                "evidence_status": evidence.evidence_status,
                "qualified_absence": evidence.may_support_qualified_absence,
            },
        )

        emitted_bytes = len(manifest_bytes)
        for index, record in enumerate(evidence.records):
            payload = {
                "kind": record.kind,
                "value": record.value,
                "source_ids": list(record.source_ids),
                "scope_class": record.scope_class,
                "expandable": record.expandable,
                "result_role": "DISCOVERY_ONLY",
            }
            body = _canonical_json(payload)
            emitted_bytes += len(body)
            if emitted_bytes > self._max_output_bytes:
                raise RuntimeError_(
                    "resource_limit_exceeded",
                    f"normalized artifacts exceeded {self._max_output_bytes} bytes",
                )
            yield AcquisitionArtifact(
                task_id=task_id,
                source_id=source_id,
                worker_ref="http",
                target_uri=target_uri,
                locator=f"json:records[{index}]",
                body=body,
                content_type="application/json",
                fetched_at=completed_at,
                transport="http",
                producer="theHarvester",
                producer_version=self._producer_version,
                capture_locator=capture_locator,
                metadata={
                    "runtime_ref": self.runtime_ref,
                    "authorization_ref": self._authorization.authorization_ref,
                    "domain_scope": target,
                    "result_role": "DISCOVERY_ONLY",
                    "record_index": index,
                    "kind": record.kind,
                    "scope_class": record.scope_class,
                    "expandable": record.expandable,
                    "source_ids": list(record.source_ids),
                },
            )


def _canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
