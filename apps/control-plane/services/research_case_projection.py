"""Durable read projections for Feature 034.

This module only reads canonical PostgreSQL observations, entities and relation claims.
It does not create claims, infer identity, convert missing data into negative findings, or
pretend that a Kafka acknowledgement means a worker completed acquisition.
"""
from __future__ import annotations

import base64
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any, Mapping

from sqlalchemy import and_, or_, select, text
from sqlalchemy.exc import SQLAlchemyError

from context_engine.obligations import ResearchObligation, ResearchAction
from db.schema import Entity, Observation, RelationClaim


class ProjectionUnavailable(RuntimeError):
    """A canonical read projection could not be computed from its backing store."""


class ProjectionCaseNotFound(LookupError):
    """The case or tenant-scoped metadata is missing."""


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return dict(parsed) if isinstance(parsed, Mapping) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
    return {}


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list | tuple):
        return list(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    return []


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=UTC)
        return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")
    text_value = str(value).strip()
    if not text_value:
        return None
    try:
        moment = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
    except ValueError:
        return text_value
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _instant(value: str | datetime | None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid ISO-8601 instant: {value!r}") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _cursor_encode(created_at: Any, relation_id: str) -> str:
    payload = json.dumps(
        {"created_at": _iso(created_at), "relation_id": relation_id},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _cursor_decode(cursor: str) -> tuple[datetime, str]:
    try:
        padded = cursor + ("=" * (-len(cursor) % 4))
        value = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        moment = _instant(value["created_at"])
        relation_id = str(value["relation_id"]).strip()
        if moment is None or not relation_id:
            raise ValueError("cursor is incomplete")
        return moment, relation_id
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid relation-claim cursor") from exc


def _row_visible_as_of(row: RelationClaim, as_of: datetime | None) -> bool:
    if as_of is None:
        return True
    known_from = row.known_from
    known_until = row.known_until
    # An as-of view must not treat a claim with unknown knowledge-time bounds as if
    # it were known at the requested instant.
    if known_from is None:
        return False
    if known_from > as_of:
        return False
    if known_until is not None and known_until <= as_of:
        return False
    return True


def _row_intersects_valid_window(
    row: RelationClaim,
    *,
    valid_from: datetime | None,
    valid_until: datetime | None,
) -> bool:
    if valid_from is not None and row.valid_to is not None and row.valid_to < valid_from:
        return False
    if valid_until is not None and row.valid_from is not None and row.valid_from > valid_until:
        return False
    return True


def _valid_time(row: RelationClaim) -> dict[str, Any]:
    start, end = _iso(row.valid_from), _iso(row.valid_to)
    return {
        "from": start,
        "until": end,
        "precision": "instant" if start or end else "unknown",
    }


def _claim_state(status: Any) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"admitted", "accepted"}:
        return "admitted"
    if normalized in {"contested", "conflicted", "disputed"}:
        return "contested"
    if normalized in {"retracted", "withdrawn"}:
        return "retracted"
    if normalized in {"superseded", "replaced"}:
        return "superseded"
    # A stored active relation claim is an assertion, not a verdict about truth.
    # Until the admission state explicitly says otherwise, show it as a proposal.
    return "proposed"


def _epistemic_state(row: RelationClaim, all_ids: set[str]) -> str:
    contradicted = {str(ref) for ref in (_json_list(row.contradicts) or [])}
    if contradicted.intersection(all_ids):
        return "BOTH"
    # The relation row records an assertion; it doesn't contain an independent
    # truth adjudication. NEITHER is the honest value until a canonical epistemic
    # projection establishes TRUE_ONLY / FALSE_ONLY / BOTH.
    return "NEITHER"


def _edge_kind(relation_type: str) -> str:
    normalized = " ".join(str(relation_type).strip().lower().replace("-", " ").replace("_", " ").split())
    mapping = {
        "works for": "AFFILIATED_WITH",
        "affiliated with": "AFFILIATED_WITH",
        "member of": "AFFILIATED_WITH",
        "employment": "AFFILIATED_WITH",
        "holds public role": "HELD_PUBLIC_ROLE",
        "has role": "HELD_PUBLIC_ROLE",
        "occupies role": "HELD_PUBLIC_ROLE",
        "authored": "AUTHORED",
        "author of": "AUTHORED",
        "wrote": "AUTHORED",
        "participated in public event": "PARTICIPATED_IN_PUBLIC_EVENT",
        "participated in": "PARTICIPATED_IN_PUBLIC_EVENT",
        "published in": "PUBLISHED_IN",
        "possible match": "POSSIBLE_MATCH",
        "supported by": "SUPPORTED_BY",
        "refuted by": "REFUTED_BY",
    }
    return mapping.get(normalized, "ASSERTS")


class PostgresResearchCaseProjectionProvider:
    """Read-only case projections over the existing Context Engine and PostgreSQL rows."""

    def __init__(self, *, session_factory: Any, context_store: Any, policy: Any) -> None:
        if session_factory is None or context_store is None:
            raise ValueError("session_factory and canonical context_store are required")
        self._session_factory = session_factory
        self._store = context_store
        self._policy = policy

    async def _case(self, case_id: str, tenant_id: str):
        context = await self._store.get_context(case_id)
        if context is None or context.tenant_id != tenant_id:
            raise ProjectionCaseNotFound("case not found")
        metadata = await self._store.get_person_case_metadata(case_id)
        if metadata is None or metadata.get("tenant_id") != tenant_id:
            raise ProjectionCaseNotFound("case not found")
        return context, metadata

    async def _relation_rows(
        self,
        *,
        tenant_id: str,
        investigation_id: str,
        limit: int = 5000,
    ) -> list[RelationClaim]:
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(RelationClaim)
                    .where(
                        RelationClaim.tenant_id == tenant_id,
                        RelationClaim.investigation_id == investigation_id,
                    )
                    .order_by(RelationClaim.created_at.desc(), RelationClaim.relation_id.asc())
                    .limit(limit + 1)
                )
                return list(result.scalars().all())
            except SQLAlchemyError as exc:
                raise ProjectionUnavailable(
                    f"canonical relation-claim projection read failed ({type(exc).__name__})"
                ) from exc

    async def _intents_and_reservations(
        self, *, tenant_id: str, case_id: str
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        async with self._session_factory() as session:
            try:
                intents_result = await session.execute(
                    text(
                        "SELECT payload, created_at, updated_at "
                        "FROM person_case_dispatch_intents "
                        "WHERE tenant_id = :tenant_id AND case_id = :case_id "
                        "ORDER BY created_at ASC, idempotency_key ASC"
                    ),
                    {"tenant_id": tenant_id, "case_id": case_id},
                )
                intent_rows = list(intents_result.mappings().all())
                intents: list[dict[str, Any]] = []
                for row in intent_rows:
                    payload = _json_object(row.get("payload"))
                    payload.setdefault("created_at", _iso(row.get("created_at")))
                    payload.setdefault("updated_at", _iso(row.get("updated_at")))
                    intents.append(payload)

                reservations_result = await session.execute(
                    text(
                        "SELECT reservation_id, idempotency_key, state, payload, created_at, updated_at "
                        "FROM person_case_budget_reservations "
                        "WHERE tenant_id = :tenant_id AND case_id = :case_id "
                        "ORDER BY created_at ASC, reservation_id ASC"
                    ),
                    {"tenant_id": tenant_id, "case_id": case_id},
                )
                reservations: dict[str, dict[str, Any]] = {}
                for row in reservations_result.mappings().all():
                    key = str(row.get("idempotency_key") or "")
                    reservations[key] = {
                        "reservation_id": str(row.get("reservation_id") or ""),
                        "state": str(row.get("state") or ""),
                        "payload": _json_object(row.get("payload")),
                        "created_at": _iso(row.get("created_at")),
                        "updated_at": _iso(row.get("updated_at")),
                    }
                return intents, reservations
            except SQLAlchemyError as exc:
                raise ProjectionUnavailable(
                    f"durable case execution ledger read failed ({type(exc).__name__})"
                ) from exc

    async def _current_actions(
        self,
        *,
        case_id: str,
        metadata: Mapping[str, Any],
    ) -> tuple[list[ResearchObligation], dict[str, list[ResearchAction]]]:
        obligations = list(await self._store.obligations(case_id))
        policy_digest = str(getattr(self._policy, "policy_digest", ""))
        actions_by_obligation: dict[str, list[ResearchAction]] = {}
        for obligation in obligations:
            all_actions = list(await self._store.actions(obligation.obligation_id))
            current = [
                action for action in all_actions
                if action.scope_digest == metadata.get("scope_digest")
                and action.policy_digest == policy_digest
            ]
            parents = {action.parent_action_id for action in current if action.parent_action_id}
            leaves = [action for action in current if action.action_id not in parents]
            actions_by_obligation[obligation.obligation_id] = sorted(
                leaves, key=lambda action: (action.source_id, action.action_id)
            )
        return obligations, actions_by_obligation

    async def coverage_ledger(self, *, case_id: str, tenant_id: str) -> dict[str, Any]:
        context, metadata = await self._case(case_id, tenant_id)
        obligations, actions_by_obligation = await self._current_actions(
            case_id=case_id, metadata=metadata
        )
        intents, reservations = await self._intents_and_reservations(
            tenant_id=tenant_id, case_id=case_id
        )

        intent_by_action: dict[str, list[dict[str, Any]]] = defaultdict(list)
        task_to_action: dict[str, str] = {}
        for intent in intents:
            outcome = _json_object(intent.get("outcome"))
            records = _json_list(outcome.get("records"))
            record_by_action: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for record in records:
                if not isinstance(record, Mapping):
                    continue
                action_id = str(record.get("action_id") or "")
                task_id = str(record.get("task_id") or "")
                if action_id:
                    record_by_action[action_id].append(dict(record))
                if action_id and task_id:
                    task_to_action[task_id] = action_id
            for action_ref in _json_list(intent.get("approved_action_refs")):
                intent_by_action[str(action_ref)].append({
                    **intent,
                    "outcome": outcome,
                    "records_for_action": record_by_action.get(str(action_ref), []),
                })

        observations: list[Observation] = []
        wanted_task_ids = set(task_to_action)
        if wanted_task_ids:
            async with self._session_factory() as session:
                try:
                    result = await session.execute(
                        select(Observation)
                        .where(
                            Observation.tenant_id == tenant_id,
                            Observation.investigation_id == context.investigation_id,
                            Observation.task_id.in_(wanted_task_ids),
                        )
                        .order_by(Observation.created_at.asc(), Observation.observation_id.asc())
                        .limit(10000)
                    )
                    observations = list(result.scalars().all())
                except SQLAlchemyError as exc:
                    raise ProjectionUnavailable(
                        f"canonical observation projection read failed ({type(exc).__name__})"
                    ) from exc

        obs_by_action: dict[str, list[Observation]] = defaultdict(list)
        for observation in observations:
            action_id = task_to_action.get(str(observation.task_id or ""))
            if action_id:
                obs_by_action[action_id].append(observation)

        # A plan revision is the durable signal that planning was attempted. The
        # returned API payload itself is not a ledger and cannot establish coverage.
        revisions = list(await self._store.revisions(case_id))
        plan_snapshots = [
            _json_object(getattr(revision, "snapshot", None))
            for revision in revisions
            if isinstance(getattr(revision, "snapshot", None), Mapping)
            and getattr(revision, "snapshot", {}).get("plan_digest")
        ]
        planning_attempted = bool(plan_snapshots)
        last_plan = plan_snapshots[-1] if plan_snapshots else {}

        items: list[dict[str, Any]] = []
        for obligation in obligations:
            actions = actions_by_obligation.get(obligation.obligation_id, [])
            if not actions:
                gap = next((
                    item for item in _json_list(last_plan.get("capability_gaps"))
                    if isinstance(item, Mapping)
                    and item.get("obligation_id") == obligation.obligation_id
                ), {})
                items.append({
                    "obligation_id": obligation.obligation_id,
                    "source_id": None,
                    "query_variant_id": None,
                    "state": "NO_ELIGIBLE_ACTIONS" if planning_attempted else "PLAN_NOT_CREATED",
                    "attempts": 0,
                    "records_received": 0,
                    "raw_artifact_refs": [],
                    "observation_refs": [],
                    "started_at": None,
                    "finished_at": None,
                    "policy_digest": str(getattr(self._policy, "policy_digest", "")),
                    "budget_reservation_id": None,
                    "reason_code": (
                        "NO_ELIGIBLE_SOURCE_ACTION"
                        if planning_attempted
                        else "PLAN_NOT_CREATED"
                    ),
                    "next_action_ref": None,
                    "detail": str(gap.get("detail") or (
                        "Planning has not been persisted for this scope."
                        if not planning_attempted
                        else "No source-bound action proposal is persisted for this obligation."
                    )),
                })
                continue

            for action in actions:
                attempts = intent_by_action.get(action.action_id, [])
                action_observations = obs_by_action.get(action.action_id, [])
                all_records = [
                    record
                    for attempt in attempts
                    for record in attempt.get("records_for_action", [])
                ]
                published = [record for record in all_records if record.get("published") is True]
                failures = [record for record in all_records if record.get("published") is False]
                latest_intent = attempts[-1] if attempts else {}
                reservation = reservations.get(str(latest_intent.get("idempotency_key") or ""), {})
                outcome = _json_object(latest_intent.get("outcome"))
                reservation_id = (
                    outcome.get("budget_reservation_id")
                    or reservation.get("reservation_id")
                    or None
                )
                if action_observations:
                    state = "OBSERVATIONS_RECEIVED"
                    reason_code = None
                    finished_at = _iso(max(
                        (row.created_at for row in action_observations if row.created_at is not None),
                        default=None,
                    ))
                elif published:
                    state = "DISPATCH_ACKNOWLEDGED_AWAITING_OBSERVATIONS"
                    reason_code = "AWAITING_WORKER_OUTCOME"
                    finished_at = None
                elif failures:
                    state = "DISPATCH_REJECTED"
                    reason_code = str(failures[-1].get("verdict") or "DISPATCH_NOT_PUBLISHED")
                    finished_at = None
                elif attempts:
                    state = "DISPATCH_PENDING_ACKNOWLEDGEMENT"
                    reason_code = "BROKER_ACK_NOT_RECORDED"
                    finished_at = None
                elif action.status == "approved":
                    state = "APPROVED_NOT_DISPATCHED"
                    reason_code = "NO_DISPATCH_INTENT"
                    finished_at = None
                elif action.status == "proposed":
                    state = "AWAITING_ACTION_APPROVAL"
                    reason_code = "ACTION_APPROVAL_REQUIRED"
                    finished_at = None
                else:
                    state = str(action.status or "UNKNOWN").upper()
                    reason_code = None
                    finished_at = None

                started_at = (
                    latest_intent.get("created_at")
                    if latest_intent
                    else None
                )
                items.append({
                    "obligation_id": obligation.obligation_id,
                    "source_id": action.source_id,
                    "query_variant_id": None,
                    "state": state,
                    "attempts": len(attempts),
                    "records_received": len(action_observations),
                    "raw_artifact_refs": sorted({
                        str(row.raw_ref)
                        for row in action_observations
                        if row.raw_ref
                    }),
                    "observation_refs": sorted({
                        str(row.observation_id) for row in action_observations
                    }),
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "policy_digest": action.policy_digest,
                    "budget_reservation_id": str(reservation_id) if reservation_id else None,
                    "reason_code": reason_code,
                    "next_action_ref": (
                        action.action_id
                        if state in {"AWAITING_ACTION_APPROVAL", "APPROVED_NOT_DISPATCHED", "DISPATCH_REJECTED"}
                        else None
                    ),
                    "detail": (
                        str(failures[-1].get("reason") or "dispatcher did not publish this task")
                        if failures
                        else (
                            "Broker acknowledgement exists, but no durable observation is yet linked to the task."
                            if state == "DISPATCH_ACKNOWLEDGED_AWAITING_OBSERVATIONS"
                            else ""
                        )
                    ),
                })

        counts = dict(sorted(Counter(item["state"] for item in items).items()))
        states = {item["state"] for item in items}
        if "OBSERVATIONS_RECEIVED" in states:
            overall = "OBSERVATIONS_RECEIVED" if states == {"OBSERVATIONS_RECEIVED"} else "PARTIAL"
        elif "DISPATCH_ACKNOWLEDGED_AWAITING_OBSERVATIONS" in states:
            overall = "AWAITING_WORKER_OUTCOME"
        elif states.intersection({"AWAITING_ACTION_APPROVAL", "APPROVED_NOT_DISPATCHED", "DISPATCH_REJECTED", "DISPATCH_PENDING_ACKNOWLEDGEMENT"}):
            overall = "PLANNED"
        elif states.intersection({"NO_ELIGIBLE_ACTIONS"}):
            overall = "BLOCKED_CAPABILITY"
        else:
            overall = "NOT_PLANNED"
        return {
            "case_id": case_id,
            "scope_revision": int(metadata.get("scope_revision", 0)),
            "overall_state": overall,
            "counts": counts,
            "items": items,
            "source_of_truth": "postgres:person_case_dispatch_intents+person_case_budget_reservations+observations",
        }

    async def _claims_for_case(
        self,
        *,
        case_id: str,
        tenant_id: str,
        as_of: str | None = None,
        valid_from: str | None = None,
        valid_until: str | None = None,
        limit: int = 5000,
    ) -> list[RelationClaim]:
        context, _metadata = await self._case(case_id, tenant_id)
        as_of_dt = _instant(as_of)
        valid_from_dt = _instant(valid_from)
        valid_until_dt = _instant(valid_until)
        rows = await self._relation_rows(
            tenant_id=tenant_id,
            investigation_id=context.investigation_id,
            limit=max(1, min(int(limit), 5000)),
        )
        rows = [
            row for row in rows
            if _row_visible_as_of(row, as_of_dt)
            and _row_intersects_valid_window(
                row, valid_from=valid_from_dt, valid_until=valid_until_dt
            )
        ]
        return rows[: max(1, min(int(limit), 5000))]

    async def _observations_for_claims(
        self,
        *,
        tenant_id: str,
        investigation_id: str,
        claims: list[RelationClaim],
    ) -> dict[str, Observation]:
        observation_ids = sorted({
            str(ref)
            for claim in claims
            for ref in _json_list(claim.observation_refs)
            if str(ref)
        })
        if not observation_ids:
            return {}
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(Observation).where(
                        Observation.tenant_id == tenant_id,
                        Observation.investigation_id == investigation_id,
                        Observation.observation_id.in_(observation_ids),
                    )
                )
                return {
                    str(row.observation_id): row
                    for row in result.scalars().all()
                }
            except SQLAlchemyError as exc:
                raise ProjectionUnavailable(
                    f"evidence observation lookup failed ({type(exc).__name__})"
                ) from exc

    async def list_claims(
        self,
        *,
        case_id: str,
        tenant_id: str,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        context, _metadata = await self._case(case_id, tenant_id)
        limit = max(1, min(int(limit), 500))
        # Keep pagination stable while epistemic links are computed against the whole
        # bounded case result set, not just whichever page happened to be requested.
        all_rows = await self._relation_rows(
            tenant_id=tenant_id,
            investigation_id=context.investigation_id,
            limit=5000,
        )
        truncated = len(all_rows) > 5000
        all_rows = all_rows[:5000]
        all_relation_ids = {str(row.relation_id) for row in all_rows}
        # Newest first, deterministic relation id tie-break; missing creation time
        # stays at the end and is never silently assigned an invented timestamp.
        all_rows.sort(
            key=lambda row: (
                -_instant(row.created_at).timestamp()
                if _instant(row.created_at) is not None
                else float("inf"),
                str(row.relation_id),
            )
        )
        if cursor:
            cursor_created_at, cursor_relation_id = _cursor_decode(cursor)

            def after_cursor(row: RelationClaim) -> bool:
                created_at = _instant(row.created_at)
                if created_at is None:
                    return False
                return (
                    created_at < cursor_created_at
                    or (
                        created_at == cursor_created_at
                        and str(row.relation_id) > cursor_relation_id
                    )
                )

            all_rows = [row for row in all_rows if after_cursor(row)]
        has_more = len(all_rows) > limit
        rows = all_rows[:limit]
        observations_by_id = await self._observations_for_claims(
            tenant_id=tenant_id,
            investigation_id=context.investigation_id,
            claims=rows,
        )
        # Contradictions are checked against the bounded case result set, including rows
        # on pages before/after the current cursor.
        claims = [
            self._claim_view(case_id, row, all_relation_ids, observations_by_id)
            for row in rows
        ]
        next_cursor = _cursor_encode(rows[-1].created_at, rows[-1].relation_id) if has_more and rows else None
        return {
            "claims": claims,
            "next_cursor": next_cursor,
            "truncated": truncated,
            "source_of_truth": "postgres:relation_claim",
        }

    @staticmethod
    def _claim_view(
        case_id: str,
        row: RelationClaim,
        all_relation_ids: set[str] | None = None,
        observations_by_id: Mapping[str, Observation] | None = None,
    ) -> dict[str, Any]:
        observations = [str(ref) for ref in _json_list(row.observation_refs) if str(ref)]
        assertions = [str(ref) for ref in _json_list(row.assertion_refs) if str(ref)]
        evidence = list(dict.fromkeys([*observations, *assertions]))
        stored_observations = observations_by_id or {}
        primary_observation = next(
            (stored_observations[ref] for ref in observations if ref in stored_observations),
            None,
        )
        if primary_observation is not None:
            source_ref = (
                f"{primary_observation.source_id}: {primary_observation.uri}"
                if primary_observation.source_id and primary_observation.uri
                else str(primary_observation.uri or primary_observation.source_id or primary_observation.observation_id)
            )
        else:
            # Missing observation join is visible; the evidence ref stays available
            # in evidence_refs rather than being mislabeled as a source URL.
            source_ref = "unresolved observation reference" if observations else "no observation source linked"
        return {
            "claim_id": row.relation_id,
            "case_id": case_id,
            "claim_family": f"relation:{row.relation_type}",
            "subject_mention": row.subject_ref,
            "predicate": row.relation_type,
            "object_payload": {
                "object_ref": row.object_ref,
                "role_bindings": _json_list(row.role_bindings),
                "evidence_grade": row.evidence_grade,
                "confidence": row.confidence,
                "source_independence_groups": _json_list(row.source_independence_groups),
            },
            # RelationClaim has no polarity column; don't invent one.
            "polarity": "unknown",
            "epistemic_state": _epistemic_state(row, all_relation_ids or {row.relation_id}),
            "state": _claim_state(row.status),
            "valid_time": _valid_time(row),
            "evidence_refs": evidence,
            "source_ref": source_ref,
            "extractor_ref": row.extraction_version or "relation-claim-store",
            "extractor_version": row.extraction_version or row.schema_version or "unknown",
            "published_at": _iso(row.published_at),
            "observed_at": _iso(row.observed_at),
            "known_from": _iso(row.known_from),
            "known_until": _iso(row.known_until),
            "status": row.status,
            "context_ref": row.context_ref,
            "contradicts": _json_list(row.contradicts),
        }

    async def timeline(
        self,
        *,
        case_id: str,
        tenant_id: str,
        valid_from: str | None = None,
        valid_until: str | None = None,
        as_of: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        rows = await self._claims_for_case(
            case_id=case_id,
            tenant_id=tenant_id,
            as_of=as_of,
            valid_from=valid_from,
            valid_until=valid_until,
            limit=max(1, min(int(limit), 500)),
        )
        relation_ids = {row.relation_id for row in rows}
        items = []
        for row in rows:
            obs_refs = [str(ref) for ref in _json_list(row.observation_refs) if str(ref)]
            assertion_refs = [str(ref) for ref in _json_list(row.assertion_refs) if str(ref)]
            items.append({
                "claim_id": row.relation_id,
                "label": f"{row.subject_ref} — {row.relation_type} → {row.object_ref}",
                "valid_time": _valid_time(row),
                "source_time": {
                    "published_at": _iso(row.published_at),
                    "captured_at": _iso(row.observed_at),
                },
                "epistemic_state": _epistemic_state(row, relation_ids),
                "evidence_refs": list(dict.fromkeys([*obs_refs, *assertion_refs])),
                "conflict_refs": [
                    str(ref) for ref in _json_list(row.contradicts)
                    if str(ref) in relation_ids
                ],
                "knowledge_time": {
                    "from": _iso(row.known_from),
                    "until": _iso(row.known_until),
                },
            })
        items.sort(
            key=lambda item: (
                item["valid_time"]["from"] or item["source_time"]["captured_at"] or "",
                item["claim_id"],
            )
        )
        return {
            "case_id": case_id,
            "timeline": items,
            "as_of": _iso(_instant(as_of)) if as_of else None,
            "source_of_truth": "postgres:relation_claim(valid_time,known_from,known_until)",
        }

    async def graph(
        self,
        *,
        case_id: str,
        tenant_id: str,
        as_of: str | None = None,
        depth: int = 1,
        kinds: list[str] | None = None,
    ) -> dict[str, Any]:
        context, metadata = await self._case(case_id, tenant_id)
        rows = await self._claims_for_case(
            case_id=case_id, tenant_id=tenant_id, as_of=as_of, limit=5000
        )
        if kinds:
            wanted = {str(kind).strip().lower() for kind in kinds if str(kind).strip()}
            rows = [
                row for row in rows
                if row.relation_type.strip().lower() in wanted
                or _edge_kind(row.relation_type).lower() in wanted
            ]
        relation_ids = {row.relation_id for row in rows}
        participant_ids = {
            str(ref)
            for row in rows
            for ref in (row.subject_ref, row.object_ref)
            if ref
        }
        if participant_ids:
            async with self._session_factory() as session:
                try:
                    result = await session.execute(
                        select(Entity).where(
                            Entity.tenant_id == tenant_id,
                            Entity.entity_id.in_(participant_ids),
                        )
                    )
                    entities = list(result.scalars().all())
                except SQLAlchemyError as exc:
                    raise ProjectionUnavailable(
                        f"canonical entity projection read failed ({type(exc).__name__})"
                    ) from exc
        else:
            entities = []
        entity_by_id = {str(entity.entity_id): entity for entity in entities}
        node_claim_refs: dict[str, set[str]] = defaultdict(set)
        unresolved: set[str] = set()
        for row in rows:
            for ref in (str(row.subject_ref), str(row.object_ref)):
                if ref in entity_by_id:
                    node_claim_refs[ref].add(row.relation_id)
                else:
                    unresolved.add(ref)
        nodes: list[dict[str, Any]] = []
        for entity_id, entity in sorted(entity_by_id.items()):
            entity_type = str(entity.entity_type or "").strip().upper()
            node_kind = {
                "ORGANIZATION": "PublicOrganisation",
                "ORGANISATION": "PublicOrganisation",
                "ROLE": "PublicRole",
                "PUBLICATION": "PublicPublication",
                "WORK": "PublicPublication",
                "EVENT": "PublicEvent/Action",
            }.get(entity_type, "AdmittedEntity")
            nodes.append({
                "id": entity_id,
                "kind": node_kind,
                "label": str(entity.canonical_name or entity_id),
                "identity_state": "ADMITTED",
                "claim_refs": sorted(node_claim_refs.get(entity_id, set())),
            })
        edges: list[dict[str, Any]] = []
        skipped_edges = 0
        for row in rows:
            subject, object_ref = str(row.subject_ref), str(row.object_ref)
            if subject not in entity_by_id or object_ref not in entity_by_id:
                skipped_edges += 1
                continue
            edges.append({
                "id": row.relation_id,
                "source": subject,
                "target": object_ref,
                "kind": _edge_kind(row.relation_type),
                "epistemic_state": _epistemic_state(row, relation_ids),
                "valid_time": _valid_time(row),
                "evidence_refs": list(dict.fromkeys([
                    *[str(ref) for ref in _json_list(row.observation_refs)],
                    *[str(ref) for ref in _json_list(row.assertion_refs)],
                ])),
                "lineage_roots": sorted({
                    str(ref)
                    for group in _json_list(row.source_independence_groups)
                    for ref in (_json_list(group) if not isinstance(group, str) else [group])
                    if str(ref)
                }),
                "review_state": str(row.status or "unknown"),
                "relation_type": row.relation_type,
            })
        max_nodes = 500
        # Graph current-state view emits the latest revision for a logical relation.
        # Historical revisions remain available to the claims/timeline projections.
        latest_edges: dict[str, dict[str, Any]] = {}
        row_by_id = {str(row.relation_id): row for row in rows}
        for edge in edges:
            relation = row_by_id[edge["id"]]
            logical_id = str(relation.logical_relation_id)
            previous = latest_edges.get(logical_id)
            if previous is None:
                latest_edges[logical_id] = edge
            else:
                previous_row = row_by_id[previous["id"]]
                if int(relation.revision_number or 0) > int(previous_row.revision_number or 0):
                    latest_edges[logical_id] = edge
        edges = [
            edge for edge in latest_edges.values()
            if str(row_by_id[edge["id"]].status or "active").lower()
            not in {"retracted", "withdrawn", "superseded"}
        ]
        truncated = len(nodes) > max_nodes or len(edges) > 1000
        nodes = nodes[:max_nodes]
        kept = {node["id"] for node in nodes}
        edges = [edge for edge in edges if edge["source"] in kept and edge["target"] in kept][:1000]
        warnings = []
        if unresolved:
            warnings.append(
                f"{len(unresolved)} relation endpoint reference(s) do not resolve to tenant-scoped canonical Entity rows; those edges are omitted."
            )
        if skipped_edges:
            warnings.append(f"{skipped_edges} relation edge(s) omitted because an endpoint is unresolved.")
        if any(_edge_kind(row.relation_type) == "ASSERTS" for row in rows):
            warnings.append("Unknown relation predicates are kept in relation_type; graph edge kind ASSERTS is only a display fallback.")
        if rows and not edges:
            warnings.append("Relation claims exist, but no edge has two materialized canonical entity endpoints.")
        if not rows:
            warnings.append("No canonical relation_claim rows are recorded for this investigation yet.")
        warnings.append(
            "Graph contains stored case-scoped relation claims only; no identity merge or unpersisted relation is inferred."
        )
        return {
            "case_id": case_id,
            "scope_revision": int(metadata.get("scope_revision", 0)),
            "projection_version": "postgres-relation-claim-v1",
            "as_of": _iso(_instant(as_of)) if as_of else datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "truncated": truncated,
            "nodes": nodes,
            "edges": edges,
            "warnings": warnings,
            "max_depth": max(1, min(int(depth), 3)),
            "note": "The projection only emits directly persisted edges; it does not manufacture multi-hop paths without canonical edges.",
            "source_of_truth": "postgres:relation_claim+entities",
        }
