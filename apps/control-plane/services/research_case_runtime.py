"""Durable Feature 034 budget reservations and the existing Layer-0 dispatcher adapter.

The control plane does not fetch URLs here. It compiles approved, source-bound actions
into the repository's existing AcquisitionTask -> PlanDispatcher -> Dispatcher ->
KafkaProducer -> acquisition.request path. The deployed acquisition worker owns actual
network calls and the raw-first ArtifactSink / ObservationGate return path.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from context_engine.obligations import ResearchAction


class CaseRuntimeBlocked(RuntimeError):
    """A required production runtime or policy precondition is absent."""


def estimate_case_reservation(
    *,
    actions: Sequence[ResearchAction],
    policy: Any,
) -> dict[str, Any]:
    """Estimate finite worst-case limits from the enabled source definitions and policy."""
    from sources.catalogue import load_catalogue
    from urllib.parse import urlsplit, parse_qs

    definitions, _rejected = load_catalogue()
    by_name = {definition.name: definition for definition in definitions}
    source_refs: list[str] = []
    hosts: set[str] = set()
    requests = raw_bytes = records = wall_seconds = 0
    max_raw_per_request = 2_000_000
    for action in actions:
        profile = policy._sources.get(action.source_id)
        if not isinstance(profile, Mapping):
            raise CaseRuntimeBlocked(f"unknown source policy id: {action.source_id}")
        if policy._source_block_reason(action.source_id, str(profile.get("allowed_case_profiles", [""])[0])) is not None:
            # The caller separately validates the exact launch profile. This check is a
            # readiness guard so a broken runtime/terms/env manifest never gets budget.
            reason = policy._source_block_reason(
                action.source_id, str(profile.get("allowed_case_profiles", [""])[0])
            )
            raise CaseRuntimeBlocked(reason or f"source {action.source_id} is not eligible")
        name = str(profile.get("catalogue_source_id") or "").strip()
        definition = by_name.get(name)
        if definition is None or not definition.enabled:
            raise CaseRuntimeBlocked(
                f"policy source {action.source_id} has no matching enabled catalogue source {name!r}"
            )
        uri = str(definition.tool.get("url") or "")
        host = (urlsplit(uri).hostname or "").lower()
        declared_hosts = {
            str(item).strip().lower()
            for item in (profile.get("egress_hosts") or [])
            if str(item).strip()
        }
        if not host or host not in declared_hosts:
            raise CaseRuntimeBlocked(f"catalogue host {host!r} is outside policy egress hosts")
        hosts.add(host)
        source_refs.append(action.source_id)

        pages = max(1, int(definition.pagination.max_pages)) if definition.pagination.enabled else 1
        params = parse_qs(urlsplit(uri).query)
        page_size = definition.pagination.page_size
        if not page_size:
            for key in ("rows", "limit", "per_page", "page_size"):
                try:
                    if params.get(key):
                        page_size = int(params[key][0])
                        break
                except (TypeError, ValueError):
                    pass
        page_size = max(1, min(int(page_size or 10), 1000))
        policy_max_pages = max(1, int(profile.get("max_pages") or pages))
        pages = min(pages, policy_max_pages)
        requests += pages
        raw_bytes += min(max_raw_per_request, max(1, int(profile.get("max_raw_bytes") or max_raw_per_request))) * pages
        records += min(max(1, int(profile.get("max_records") or page_size)), page_size * pages)
        wall_seconds += max(1, int(profile.get("max_wall_seconds") or 300)) * pages

    if not actions:
        raise CaseRuntimeBlocked("cannot reserve a budget for an empty action set")
    return {
        "requests": requests,
        "raw_bytes": raw_bytes,
        "records": records,
        "concurrency": 1,
        "wall_seconds": wall_seconds,
        "source_refs": sorted(set(source_refs)),
        "allowed_hosts": sorted(hosts),
        "planned_action_count": len(actions),
    }


class PostgresCaseBudgetService:
    """Reserve explicit request, raw-byte, record, concurrency, and time budgets.

    Required budgets.limits shape:
      {
        "person_research_case": {
          "max_requests": int, "max_raw_bytes": int, "max_records": int,
          "max_concurrency": int, "max_wall_seconds": int
        }
      }

    Missing budgets and missing limits deny dispatch. Rows stay durable and reserved
    until explicitly reconciled; this prevents a lost worker acknowledgement from
    silently returning capacity that may already have been consumed.
    """

    def __init__(self, session_factory: Any) -> None:
        if session_factory is None:
            raise ValueError("session_factory is required for durable budgets")
        self._session_factory = session_factory

    @staticmethod
    def _positive_limit(limits: Mapping[str, Any], name: str) -> int:
        value = limits.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise CaseRuntimeBlocked(f"budget lacks an explicit {name} limit")
        if not math.isfinite(float(value)) or int(value) != value or value <= 0:
            raise CaseRuntimeBlocked(f"budget {name} limit must be a positive integer")
        return int(value)

    async def reserve_case(
        self,
        *,
        budget_ref: str | None,
        tenant_id: str,
        case_id: str,
        investigation_id: str,
        idempotency_key: str,
        scope_digest: str,
        policy_digest: str,
        requests: int,
        raw_bytes: int,
        records: int,
        concurrency: int = 1,
        wall_seconds: int = 300,
        source_refs: Sequence[str] = (),
    ) -> dict[str, Any]:
        if not budget_ref or not budget_ref.strip():
            raise CaseRuntimeBlocked("budget_ref is required before dispatch")
        if not all((tenant_id, case_id, investigation_id, idempotency_key, scope_digest, policy_digest)):
            raise CaseRuntimeBlocked("budget reservation is missing a bound identity/digest")
        if min(requests, raw_bytes, records, concurrency, wall_seconds) <= 0:
            raise CaseRuntimeBlocked("reservation quantities must be positive")

        reservation_seed = "|".join(
            (tenant_id, case_id, budget_ref, idempotency_key, scope_digest, policy_digest)
        )
        reservation_id = "RBR-" + hashlib.sha256(reservation_seed.encode()).hexdigest()[:32]
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    text(
                        "SELECT budget_id, tenant_id, investigation_id, limits, current_usage "
                        "FROM budgets WHERE budget_id = :budget_id AND tenant_id = :tenant_id "
                        "FOR UPDATE"
                    ),
                    {"budget_id": budget_ref, "tenant_id": tenant_id},
                )
                row = result.mappings().first()
                if row is None:
                    raise CaseRuntimeBlocked(
                        f"budget {budget_ref!r} does not exist for tenant {tenant_id}"
                    )
                if row.get("investigation_id") and row["investigation_id"] != investigation_id:
                    raise CaseRuntimeBlocked("budget is bound to a different investigation")
                raw_limits = row.get("limits")
                if isinstance(raw_limits, str):
                    raw_limits = json.loads(raw_limits)
                if not isinstance(raw_limits, Mapping):
                    raise CaseRuntimeBlocked("budget limits are missing or malformed")
                rc_limits = raw_limits.get("person_research_case")
                if not isinstance(rc_limits, Mapping):
                    raise CaseRuntimeBlocked(
                        "budget must declare limits.person_research_case "
                        "(max_requests, max_raw_bytes, max_records, max_concurrency, max_wall_seconds)"
                    )
                ceilings = {
                    "max_requests": self._positive_limit(rc_limits, "max_requests"),
                    "max_raw_bytes": self._positive_limit(rc_limits, "max_raw_bytes"),
                    "max_records": self._positive_limit(rc_limits, "max_records"),
                    "max_concurrency": self._positive_limit(rc_limits, "max_concurrency"),
                    "max_wall_seconds": self._positive_limit(rc_limits, "max_wall_seconds"),
                }
                requested = {
                    "requests": int(requests),
                    "raw_bytes": int(raw_bytes),
                    "records": int(records),
                    "concurrency": int(concurrency),
                    "wall_seconds": int(wall_seconds),
                }
                ceiling_names = {
                    "requests": "max_requests",
                    "raw_bytes": "max_raw_bytes",
                    "records": "max_records",
                    "concurrency": "max_concurrency",
                    "wall_seconds": "max_wall_seconds",
                }
                for quantity, limit_name in ceiling_names.items():
                    if requested[quantity] > ceilings[limit_name]:
                        raise CaseRuntimeBlocked(
                            f"budget {limit_name}={ceilings[limit_name]} is below "
                            f"scope reservation {quantity}={requested[quantity]}"
                        )

                prior = await session.execute(
                    text(
                        "SELECT reservation_id, tenant_id, case_id, budget_id, investigation_id, "
                        "idempotency_key, scope_digest, policy_digest, request_count, raw_bytes, "
                        "record_count, concurrency, wall_seconds, state, payload "
                        "FROM person_case_budget_reservations "
                        "WHERE tenant_id = :tenant_id AND case_id = :case_id "
                        "AND idempotency_key = :idempotency_key FOR UPDATE"
                    ),
                    {
                        "tenant_id": tenant_id,
                        "case_id": case_id,
                        "idempotency_key": idempotency_key,
                    },
                )
                existing = prior.mappings().first()
                if existing is not None:
                    invariant = {
                        "budget_id": budget_ref,
                        "scope_digest": scope_digest,
                        "policy_digest": policy_digest,
                        "request_count": requested["requests"],
                        "raw_bytes": requested["raw_bytes"],
                        "record_count": requested["records"],
                        "concurrency": requested["concurrency"],
                        "wall_seconds": requested["wall_seconds"],
                    }
                    for field, expected in invariant.items():
                        if existing[field] != expected:
                            raise CaseRuntimeBlocked(
                                f"idempotency key reused with a different reservation {field}"
                            )
                    if existing["state"] in {"RELEASED", "FAILED"}:
                        raise CaseRuntimeBlocked(
                            "this idempotency key has a terminal reservation; use a new run key"
                        )
                    payload = existing.get("payload") or {}
                    if isinstance(payload, str):
                        payload = json.loads(payload)
                    return {
                        **dict(existing),
                        "limits": dict(ceilings),
                        "source_refs": list(payload.get("source_refs") or source_refs),
                        "created": False,
                    }

                active_result = await session.execute(
                    text(
                        "SELECT COALESCE(SUM(request_count), 0) AS requests, "
                        "COALESCE(SUM(raw_bytes), 0) AS raw_bytes, "
                        "COALESCE(SUM(record_count), 0) AS records, "
                        "COALESCE(SUM(concurrency), 0) AS concurrency, "
                        "COALESCE(SUM(wall_seconds), 0) AS wall_seconds "
                        "FROM person_case_budget_reservations "
                        "WHERE budget_id = :budget_id AND state IN ('RESERVED', 'PUBLISHED')"
                    ),
                    {"budget_id": budget_ref},
                )
                active = active_result.mappings().one()
                usage = row.get("current_usage") or {}
                if isinstance(usage, str):
                    usage = json.loads(usage)
                spent = usage.get("person_research_case", {}) if isinstance(usage, Mapping) else {}
                if not isinstance(spent, Mapping):
                    spent = {}
                spent_keys = {
                    "requests": "spent_requests",
                    "raw_bytes": "spent_raw_bytes",
                    "records": "spent_records",
                    "concurrency": "spent_concurrency",
                    "wall_seconds": "spent_wall_seconds",
                }
                for quantity, limit_name in ceiling_names.items():
                    already = int(active[quantity] or 0) + int(spent.get(spent_keys[quantity], 0) or 0)
                    if already + requested[quantity] > ceilings[limit_name]:
                        raise CaseRuntimeBlocked(
                            f"budget {limit_name} exhausted: {already}+{requested[quantity]}"
                            f">{ceilings[limit_name]}"
                        )

                payload = {
                    **requested,
                    "limits": dict(ceilings),
                    "source_refs": sorted(set(source_refs)),
                    "created_at": datetime.now(UTC).isoformat(),
                }
                await session.execute(
                    text(
                        "INSERT INTO person_case_budget_reservations "
                        "(reservation_id, tenant_id, case_id, investigation_id, budget_id, "
                        "idempotency_key, scope_digest, policy_digest, request_count, raw_bytes, "
                        "record_count, concurrency, wall_seconds, state, payload) "
                        "VALUES (:reservation_id, :tenant_id, :case_id, :investigation_id, "
                        ":budget_id, :idempotency_key, :scope_digest, :policy_digest, "
                        ":request_count, :raw_bytes, :record_count, :concurrency, :wall_seconds, "
                        "'RESERVED', CAST(:payload AS jsonb))"
                    ),
                    {
                        "reservation_id": reservation_id,
                        "tenant_id": tenant_id,
                        "case_id": case_id,
                        "investigation_id": investigation_id,
                        "budget_id": budget_ref,
                        "idempotency_key": idempotency_key,
                        "scope_digest": scope_digest,
                        "policy_digest": policy_digest,
                        "request_count": requested["requests"],
                        "raw_bytes": requested["raw_bytes"],
                        "record_count": requested["records"],
                        "concurrency": requested["concurrency"],
                        "wall_seconds": requested["wall_seconds"],
                        "payload": json.dumps(payload, sort_keys=True),
                    },
                )
        return {
            "reservation_id": reservation_id,
            "tenant_id": tenant_id,
            "case_id": case_id,
            "investigation_id": investigation_id,
            "budget_id": budget_ref,
            "idempotency_key": idempotency_key,
            "scope_digest": scope_digest,
            "policy_digest": policy_digest,
            "state": "RESERVED",
            **requested,
            "limits": dict(ceilings),
            "source_refs": sorted(set(source_refs)),
            "created": True,
        }

    async def mark_reservation(
        self, *, reservation_id: str, state: str, outcome: Mapping[str, Any] | None = None
    ) -> None:
        allowed = {"RESERVED", "PUBLISHED", "RELEASED", "FAILED"}
        if state not in allowed:
            raise ValueError(f"unsupported reservation state: {state}")
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    text(
                        "SELECT payload FROM person_case_budget_reservations "
                        "WHERE reservation_id = :reservation_id FOR UPDATE"
                    ),
                    {"reservation_id": reservation_id},
                )
                row = result.mappings().first()
                if row is None:
                    raise CaseRuntimeBlocked("reservation record disappeared")
                payload = row["payload"]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                payload = dict(payload or {})
                payload["outcome"] = dict(outcome or {})
                payload["updated_at"] = datetime.now(UTC).isoformat()
                await session.execute(
                    text(
                        "UPDATE person_case_budget_reservations "
                        "SET state = :state, payload = CAST(:payload AS jsonb), updated_at = now() "
                        "WHERE reservation_id = :reservation_id"
                    ),
                    {
                        "state": state,
                        "payload": json.dumps(payload, sort_keys=True),
                        "reservation_id": reservation_id,
                    },
                )

    async def has_reservation(
        self, *, case_id: str, tenant_id: str, scope_digest: str | None = None
    ) -> bool:
        async with self._session_factory() as session:
            query = (
                "SELECT 1 FROM person_case_budget_reservations WHERE case_id = :case_id "
                "AND tenant_id = :tenant_id AND state IN ('RESERVED', 'PUBLISHED')"
            )
            params: dict[str, Any] = {"case_id": case_id, "tenant_id": tenant_id}
            if scope_digest:
                query += " AND scope_digest = :scope_digest"
                params["scope_digest"] = scope_digest
            query += " LIMIT 1"
            result = await session.execute(text(query), params)
            return result.first() is not None


class CaseBoundResourceLimits:
    """Dispatcher resource guard pinned to a durable reservation and allowed hosts."""

    def __init__(
        self,
        *,
        tenant_id: str,
        case_id: str,
        policy_revision: str,
        reservation_id: str,
        allowed_hosts: set[str],
        max_requests: int,
    ) -> None:
        self.tenant_id = tenant_id
        self.case_id = case_id
        self.policy_revision = policy_revision
        self.reservation_id = reservation_id
        self.allowed_hosts = {host.strip().lower() for host in allowed_hosts if host.strip()}
        self.max_requests = max_requests
        self._calls = 0

    def allows(
        self,
        execution_class: str,
        region: str | None,
        host_key: str,
        required: set[str],
        *,
        tenant_id: str | None = None,
        case_id: str | None = None,
        policy_revision: str | None = None,
    ) -> tuple[bool, str, str | None]:
        if (tenant_id, case_id, policy_revision) != (
            self.tenant_id,
            self.case_id,
            self.policy_revision,
        ):
            return False, "BLOCKED_SCOPE_BINDING", None
        if execution_class != "http" or not required.issubset({"http"}):
            return False, "BLOCKED_CAPABILITY", None
        if host_key.strip().lower() not in self.allowed_hosts:
            return False, "BLOCKED_EGRESS_HOST", None
        if self._calls >= self.max_requests:
            return False, "BLOCKED_BUDGET", None
        self._calls += 1
        return True, "DURABLE_RESERVATION", self.reservation_id


class CaseDispatchExecutor:
    """Validate approved source-bound action records and publish acquisition requests."""

    def __init__(self, *, policy: Any) -> None:
        self._policy = policy

    def estimate_reservation(self, *, actions: Sequence[ResearchAction]) -> dict[str, Any]:
        return estimate_case_reservation(actions=actions, policy=self._policy)

    async def dispatch_case(
        self,
        *,
        case_id: str,
        tenant_id: str,
        run_id: str,
        idempotency_key: str,
        approved_action_refs: Sequence[str],
        actions: Sequence[ResearchAction],
        reservation: Mapping[str, Any],
        scope_digest: str,
        policy_digest: str,
        policy_revision: str,
        scope_revision: int,
        launch_profile: str,
        allowed_source_ids: Sequence[str],
        investigation_id: str,
    ) -> dict[str, Any]:
        if not reservation.get("reservation_id") or reservation.get("state") not in {"RESERVED", "PUBLISHED"}:
            raise CaseRuntimeBlocked("a durable active budget reservation is required")
        if reservation.get("tenant_id") != tenant_id or reservation.get("case_id") != case_id:
            raise CaseRuntimeBlocked("reservation principal does not match case principal")
        if reservation.get("scope_digest") != scope_digest or reservation.get("policy_digest") != policy_digest:
            raise CaseRuntimeBlocked("reservation scope/policy digest is stale")
        if not self._policy.loaded:
            raise CaseRuntimeBlocked("source policy is not loaded")
        by_id = {action.action_id: action for action in actions}
        refs = list(dict.fromkeys(approved_action_refs))
        if not refs or set(refs) != set(by_id):
            raise CaseRuntimeBlocked("dispatch actions must exactly equal the verified action set")

        from sources.catalogue import load_catalogue
        definitions, _rejected = load_catalogue()
        by_catalogue_id = {definition.source_id: definition for definition in definitions}
        from dispatcher.plan_driver import PlanDriver, PlanDispatcher
        from dispatcher.kafka_producer import KafkaProducer
        from dispatcher.scheduler import Dispatcher
        from sources.connector import AcquisitionTask
        from domain.relation_identity import digest128
        from urllib.parse import urlsplit

        work: list[tuple[Any, ResearchAction, str, str]] = []
        allowed_hosts: set[str] = set()
        total_raw_bytes = 0
        total_records = 0
        for action in by_id.values():
            if action.status != "approved" or action.requires_operator_approval:
                raise CaseRuntimeBlocked(f"action {action.action_id} has no durable approval")
            if action.source_id not in set(allowed_source_ids):
                raise CaseRuntimeBlocked(f"action {action.action_id} points outside the approved source set")
            if action.scope_digest != scope_digest or action.policy_digest != policy_digest:
                raise CaseRuntimeBlocked(f"action {action.action_id} has stale scope/policy digests")
            source_profile = self._policy._sources.get(action.source_id)
            if source_profile is None:
                raise CaseRuntimeBlocked(f"source policy id disappeared: {action.source_id}")
            reason = self._policy._source_block_reason(action.source_id, launch_profile)
            if reason:
                raise CaseRuntimeBlocked(reason)
            if not self._policy._source_supports_claim_family(
                source_profile, self._claim_family_for_action(action)
            ):
                raise CaseRuntimeBlocked(f"source {action.source_id} no longer supports its claim family")
            definition = by_catalogue_id.get(action.catalogue_source_id)
            expected_name = str(source_profile.get("catalogue_source_id", "")).strip()
            if definition is None or not expected_name or definition.name != expected_name or not definition.enabled:
                raise CaseRuntimeBlocked(
                    f"source {action.source_id} has no matching enabled catalogue definition"
                )
            runtime_profile = str(source_profile.get("runtime_ref") or "").strip()
            if runtime_profile == "http" and definition.runtime_ref:
                raise CaseRuntimeBlocked("HTTP policy source unexpectedly resolves to another runtime")
            if runtime_profile not in {"", "http"} and definition.runtime_ref != runtime_profile:
                raise CaseRuntimeBlocked("catalogue runtime disagrees with approved source policy")
            source_uri = str(definition.tool.get("url") or "")
            host = (urlsplit(source_uri).hostname or "").lower()
            declared_hosts = {
                str(item).strip().lower()
                for item in (source_profile.get("egress_hosts") or [])
                if str(item).strip()
            }
            if not host or host not in declared_hosts:
                raise CaseRuntimeBlocked(
                    f"catalogue host {host!r} is outside source policy egress allowlist"
                )
            allowed_hosts.add(host)
            task_id = "TSK-" + digest128(
                "|".join(
                    (
                        tenant_id,
                        case_id,
                        scope_digest,
                        idempotency_key,
                        action.action_id,
                        definition.source_id,
                    )
                )
            )
            from dataclasses import replace
            task = AcquisitionTask(
                task_id=task_id,
                source_id=definition.source_id,
                source_name=definition.name,
                query=action.query,
                category=definition.category,
                tenant_id=tenant_id,
                investigation_id=investigation_id,
                runtime_ref=definition.runtime_ref,
            )
            work.append((task, action, source_uri, host))
            pages = max(1, int(definition.pagination.max_pages)) if definition.pagination.enabled else 1
            total_raw_bytes += min(2_000_000, max(1, int(source_profile.get("max_raw_bytes") or 2_000_000))) * pages
            rows = _declared_rows(definition)
            page_size = definition.pagination.page_size or rows
            total_records += min(max(1, int(source_profile.get("max_records") or rows)), max(1, page_size) * pages)

        if not work:
            raise CaseRuntimeBlocked("no approved source-bound actions are runnable")
        if len(work) > int(reservation.get("request_count", 0)):
            raise CaseRuntimeBlocked("budget reservation is too small for the approved action set")

        producer = KafkaProducer()
        limits = CaseBoundResourceLimits(
            tenant_id=tenant_id,
            case_id=case_id,
            policy_revision=policy_revision,
            reservation_id=str(reservation["reservation_id"]),
            allowed_hosts=allowed_hosts,
            max_requests=len(work),
        )
        dispatcher = Dispatcher(
            limits=limits,
            producer=producer,
            tenant_id=tenant_id,
            case_id=case_id,
            policy_revision=policy_revision,
            budget_reservation_id=str(reservation["reservation_id"]),
            min_utility=0.0,
        )
        PlanDriver(dispatcher=dispatcher, producer=producer)
        driver = PlanDispatcher(dispatcher=dispatcher, producer=producer)

        def _publish() -> list[dict[str, Any]]:
            rows: list[dict[str, Any]] = []
            for task, action, source_uri, host in work:
                record = driver.dispatch_one(
                    task,
                    context={
                        "case_id": case_id,
                        "tenant_id": tenant_id,
                        "scope_digest": scope_digest,
                        "policy_digest": policy_digest,
                    },
                    context_score_fields={
                        "case_id": case_id,
                        "tenant_id": tenant_id,
                        "scope_digest": scope_digest,
                        "policy_digest": policy_digest,
                        "policy_revision": policy_revision,
                        "budget_reservation_id": str(reservation["reservation_id"]),
                        "idempotency_key": idempotency_key,
                        "run_id": run_id,
                        "scope_revision": scope_revision,
                        "case_policy_source_id": action.source_id,
                        "approved_action_ref": action.action_id,
                        "action_id": action.action_id,
                        "required_capabilities": ["http"],
                    },
                    uri=source_uri,
                )
                rows.append(
                    {
                        "task_id": record.task_id,
                        "source_id": record.source_id,
                        "policy_source_id": action.source_id,
                        "action_id": action.action_id,
                        "verdict": record.verdict,
                        "published": record.published,
                        "reason": record.reason,
                        "topic": record.topic,
                        "partition": record.partition,
                        "offset": record.offset,
                        "key": record.key,
                        "execution_class": record.execution_class,
                        "host": host,
                    }
                )
            return rows

        records = await asyncio.to_thread(_publish)
        published = [item for item in records if item["published"]]
        return {
            "published": bool(records) and len(published) == len(records),
            "partial": bool(published) and len(published) != len(records),
            "requested_count": len(records),
            "published_count": len(published),
            "records": records,
            "budget_reservation_id": reservation["reservation_id"],
            "scope_digest": scope_digest,
            "policy_digest": policy_digest,
            "reserved_raw_bytes": total_raw_bytes,
            "reserved_records": total_records,
        }

    @staticmethod
    def _claim_family_for_action(action: ResearchAction) -> str:
        marker = "claim_family="
        if marker not in action.proposed_method:
            return ""
        return action.proposed_method.split(marker, 1)[1].split(";", 1)[0].strip()


def _declared_rows(definition: Any) -> int:
    from urllib.parse import parse_qs, urlsplit

    query = parse_qs(urlsplit(str(definition.tool.get("url") or "")).query)
    for key in ("rows", "limit", "per_page", "page_size"):
        values = query.get(key)
        if values:
            try:
                return max(1, min(int(values[0]), 1000))
            except (TypeError, ValueError):
                continue
    return 10
