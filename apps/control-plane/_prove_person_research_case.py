"""Live Feature 034 person-case acceptance across PostgreSQL, Redpanda, S3 and report read-back.

This proof is intentionally scoped to public scholarly metadata. It does not enable professional
role or affiliation claims because the current source policy keeps official sources disabled
pending owner attestation. It uses a real monitored Crossref contact from the CI secret; no
placeholder contact is accepted or invented.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ROOT = Path(__file__).resolve().parents[2]
for item in (
    ROOT / "apps" / "control-plane",
    ROOT / "apps" / "acquisition",
    ROOT / "apps" / "interpretation",
    ROOT / "apps" / "shared",
):
    sys.path.insert(0, str(item))

TENANT_ID = "acceptance-person-case"
SOURCE_ID = "crossref_works"
PUBLIC_SUBJECT = "Geoffrey Hinton"
PURPOSE_TEXT = (
    "Locate publicly indexed scholarly publications explicitly associated with the declared "
    "public name. This acceptance case is limited to Crossref public metadata; it does not "
    "investigate private data or assert public roles, appointments or affiliations."
)


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def _crossref_contact_ready() -> bool:
    value = os.environ.get("COGNITIVE_CROSSREF_MAILTO", "").strip()
    return bool(value and "@" in value and not value.casefold().endswith(".local"))


def _start_workers(output_dir: Path) -> list[subprocess.Popen[Any]]:
    """Start the same console workers used by the deployed platform."""
    bin_dir = ROOT / ".venv" / "bin"
    commands = (
        ("acquisition-worker", bin_dir / "cognitive-acquisition-worker"),
        ("observation-consumer", bin_dir / "cognitive-observation-consumer"),
    )
    workers: list[subprocess.Popen[Any]] = []
    env = os.environ.copy()
    env.update(
        {
            "COGNITIVE_ACQUISITION_GROUP": f"person-case-e2e-{os.environ.get('GITHUB_RUN_ID', 'local')}",
            "COGNITIVE_ACQUISITION_OFFSET_RESET": "latest",
            "COGNITIVE_INTERPRETATION_GROUP": f"person-case-e2e-{os.environ.get('GITHUB_RUN_ID', 'local')}",
            "COGNITIVE_INTERPRETATION_OFFSET_RESET": "latest",
            "COGNITIVE_LOG_LEVEL": "INFO",
        }
    )
    try:
        for name, executable in commands:
            if not executable.exists():
                raise RuntimeError(f"required production worker entrypoint is missing: {executable}")
            log_path = output_dir / f"{name}.log"
            log_file = log_path.open("w", encoding="utf-8")
            process = subprocess.Popen(
                [str(executable)],
                cwd=ROOT,
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            # Keep a reference to the stream on the Popen object until shutdown.
            setattr(process, "_acceptance_log", log_file)
            workers.append(process)
    except Exception:
        _stop_workers(workers)
        raise
    # Give both consumers time to join the one canonical Kafka topic before dispatch.
    for _attempt in range(10):
        failed = [process for process in workers if process.poll() is not None]
        if failed:
            raise RuntimeError(
                "a production worker exited during startup; inspect acquisition-worker.log "
                "and observation-consumer.log in the acceptance artifact"
            )
        time.sleep(1)
    if any(process.poll() is not None for process in workers):
        raise RuntimeError("a production worker exited before person-case dispatch")
    return workers


def _stop_workers(workers: list[subprocess.Popen[Any]]) -> None:
    for process in workers:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    for process in workers:
        try:
            process.wait(timeout=12)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
        log_file = getattr(process, "_acceptance_log", None)
        if log_file is not None:
            log_file.close()


async def _seed_budget(session_factory: Any, *, budget_id: str) -> None:
    limits = {
        "person_research_case": {
            "max_requests": 100,
            "max_raw_bytes": 500_000_000,
            "max_records": 5_000,
            "max_concurrency": 3,
            "max_wall_seconds": 30_000,
        }
    }
    async with session_factory() as session:
        async with session.begin():
            await session.execute(
                text(
                    """
                    INSERT INTO budgets
                        (budget_id, tenant_id, investigation_id, limits, current_usage)
                    VALUES
                        (:budget_id, :tenant_id, NULL, CAST(:limits AS jsonb), '{}'::jsonb)
                    ON CONFLICT (budget_id) DO UPDATE SET
                        tenant_id = EXCLUDED.tenant_id,
                        investigation_id = NULL,
                        limits = EXCLUDED.limits,
                        current_usage = '{}'::jsonb
                    """
                ),
                {
                    "budget_id": budget_id,
                    "tenant_id": TENANT_ID,
                    "limits": json.dumps(limits, sort_keys=True),
                },
            )


async def _wait_for_processed_observation(
    session_factory: Any, *, investigation_id: str, task_id: str, timeout_seconds: int = 300
) -> tuple[Any, Any]:
    from db.schema import Observation, ProcessingResultRow

    deadline = time.monotonic() + timeout_seconds
    last_status: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        async with session_factory() as session:
            observations = list(
                (
                    await session.execute(
                        select(Observation)
                        .where(
                            Observation.tenant_id == TENANT_ID,
                            Observation.investigation_id == investigation_id,
                            Observation.task_id == task_id,
                        )
                        .order_by(Observation.created_at.desc(), Observation.observation_id.asc())
                        .limit(20)
                    )
                ).scalars().all()
            )
            results = list(
                (
                    await session.execute(
                        select(ProcessingResultRow)
                        .where(
                            ProcessingResultRow.tenant_id == TENANT_ID,
                            ProcessingResultRow.investigation_id == investigation_id,
                        )
                        .order_by(ProcessingResultRow.processed_at.desc())
                        .limit(20)
                    )
                ).scalars().all()
            )
        last_status = [
            {
                "observation_id": row.observation_id,
                "status": row.status,
                "interpretation": row.interpretation,
                "record_count": row.record_count,
                "mention_count": row.mention_count,
                "failure_code": row.failure_code,
            }
            for row in results
        ]
        processed_by_observation = {
            row.observation_id: row
            for row in results
            if row.status == "processed" and not row.failure_code
        }
        for observation in observations:
            result = processed_by_observation.get(observation.observation_id)
            if result is not None:
                return observation, result
        await asyncio.sleep(2)
    raise TimeoutError(
        "no durably processed Observation arrived for the person case within "
        f"{timeout_seconds}s; last processing ledger state={last_status!r}"
    )


def _has_declared_author_name(item: dict[str, Any]) -> bool:
    """Match the declared public name only against Crossref's author fields.

    A keyword hit elsewhere in a DOI record (title, publisher, references, etc.) is not
    evidence that the named person appears in its author list.
    """
    parts = " ".join(PUBLIC_SUBJECT.casefold().split()).split(" ")
    if len(parts) < 2:
        return False
    given_anchor, family_anchor = parts[0], parts[-1]
    authors = item.get("author") or []
    if not isinstance(authors, list):
        return False
    for author in authors:
        if not isinstance(author, dict):
            continue
        given = " ".join(str(author.get("given") or "").casefold().split())
        family = " ".join(str(author.get("family") or "").casefold().split())
        if family == family_anchor and given.split(" ")[:1] == [given_anchor]:
            return True
        name = " ".join(str(author.get("name") or "").casefold().split())
        if name == " ".join(parts):
            return True
    return False


async def _read_verified_raw(observation: Any) -> dict[str, Any]:
    from storage.s3 import ObjectStore

    raw_ref = str(observation.raw_ref or "")
    parsed = urlsplit(raw_ref)
    store = ObjectStore()
    if parsed.scheme != "s3" or parsed.netloc != store.raw_bucket or not parsed.path:
        raise RuntimeError(f"observation raw_ref is outside configured tenant raw storage: {raw_ref!r}")
    key = parsed.path.lstrip("/")
    if not key.startswith(f"raw/{TENANT_ID}/"):
        raise RuntimeError("observation raw object is outside the case tenant prefix")
    body = await store.read_range(
        bucket=parsed.netloc, key=key, offset=0, length=None
    )
    digest = hashlib.sha256(body).hexdigest()
    if digest != str(observation.content_hash):
        raise RuntimeError(
            f"raw-object digest mismatch: database={observation.content_hash} object={digest}"
        )
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        payload = {}
    message = payload.get("message", {}) if isinstance(payload, dict) else {}
    items = message.get("items", []) if isinstance(message, dict) else []
    valid_items = [
        item for item in items
        if isinstance(item, dict) and item.get("DOI") and item.get("title")
    ] if isinstance(items, list) else []
    return {
        "raw_ref": raw_ref,
        "sha256": digest,
        "byte_length": len(body),
        "content_type": str(observation.content_type or ""),
        "crossref_items": len(items) if isinstance(items, list) else 0,
        "doi_title_records": len(valid_items),
        "anchor_exact_match_records": sum(
            1 for item in valid_items if _has_declared_author_name(item)
        ),
        "sample_records": [
            {
                "doi": str(item.get("DOI") or ""),
                "title": (item.get("title") or [""])[0],
                "publisher": str(item.get("publisher") or ""),
                "author_count": len(item.get("author") or []),
            }
            for item in valid_items[:5]
        ],
    }


async def _run_case(output_path: Path) -> dict[str, Any]:
    from composition import close_platform, get_platform
    from context_engine.person_case_profile import PUBLIC_PROFESSIONAL

    run_id = str(os.environ.get("GITHUB_RUN_ID") or "local")
    budget_id = f"pc-e2e-{run_id}"[:36]
    platform = None
    worker_processes: list[subprocess.Popen[Any]] = []
    result: dict[str, Any] = {
        "schema_version": 1,
        "scope": {
            "launch_profile": PUBLIC_PROFESSIONAL,
            "purpose": "public scholarly publication metadata only",
            "subject_anchor": PUBLIC_SUBJECT,
            "source_id": SOURCE_ID,
            "claim_families": ["public_authorship_or_publication"],
            "excluded_scope": [
                "public professional roles",
                "private contact",
                "precise home address",
                "private relationships",
                "credentials",
                "breach data",
                "biometric identity",
                "individual location tracking",
                "sensitive inference",
            ],
        },
    }
    if not _crossref_contact_ready():
        result.update(
            status="BLOCKED_MISSING_OPERATOR_CONTACT",
            blocker=(
                "Set the repository Actions secret COGNITIVE_CROSSREF_MAILTO to a real, "
                "monitored operator contact address. The proof will not synthesize or use "
                "a placeholder Crossref contact."
            ),
        )
        _write_report(output_path, result)
        raise RuntimeError(result["blocker"])

    try:
        from config.settings import get_settings

        settings = get_settings()
        dsn = str(settings.postgres.dsn or "").strip()
        if not dsn:
            raise RuntimeError("PostgreSQL DSN is missing")
        engine = create_async_engine(dsn, pool_pre_ping=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            await _seed_budget(session_factory, budget_id=budget_id)
            platform = await get_platform(tenant_id=TENANT_ID)
            health = platform.health.as_dict()
            result["platform_health"] = health
            if not platform.research_case_service or not platform.research_case_report_service:
                raise RuntimeError(
                    "Person Research Case service/report service were not composed: "
                    f"{health!r}"
                )

            service = platform.research_case_service
            reports = platform.research_case_report_service
            created = await service.create_case(
                tenant_id=TENANT_ID,
                created_by="github-actions:person-case-acceptance",
                purpose_code="public_professional",
                purpose_text=PURPOSE_TEXT,
                basis_ref=f"ci-acceptance:public-metadata-only:{run_id}",
                launch_profile=PUBLIC_PROFESSIONAL,
                subject_anchors=[
                    {
                        "kind": "public_name",
                        "value": PUBLIC_SUBJECT,
                        "evidence_ref": f"ci-declared-anchor:{run_id}",
                    }
                ],
                jurisdictions=["US"],
                valid_time={"from": None, "until": None, "precision": "unknown"},
                claim_families=["public_authorship_or_publication"],
                allowed_source_ids=[SOURCE_ID],
                denied_claim_families=[],
                budget_ref=budget_id,
                expires_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            )
            if int(created.get("obligation_count", 0)) != 1:
                raise RuntimeError(
                    "Crossref acceptance expects one profile obligation; duplicate explicit "
                    f"question obligations are not allowed: {created!r}"
                )
            case_id = str(created["case_id"])
            context = await platform.store.get_context(case_id)
            if context is None:
                raise RuntimeError("created person case has no canonical InvestigationContext")
            investigation_id = str(context.investigation_id)
            result["case"] = {
                "case_id": case_id,
                "investigation_id": investigation_id,
                "scope_digest": created["scope_digest"],
                "scope_revision": created["scope_revision"],
                "obligation_count": created["obligation_count"],
                "state": created["state"],
            }

            approved = await service.approve_case(
                case_id=case_id,
                tenant_id=TENANT_ID,
                approver_id="github-actions:person-case-acceptance-approver",
                scope_digest=str(created["scope_digest"]),
                scope_revision=int(created["scope_revision"]),
            )
            result["approval"] = approved

            plan = await service.plan_case(case_id=case_id, tenant_id=TENANT_ID)
            action_view = await service.list_actions(case_id=case_id, tenant_id=TENANT_ID)
            actions = list(action_view.get("actions") or [])
            selected = [
                action for action in actions
                if action.get("source_id") == SOURCE_ID
                and action.get("claim_family") == "public_authorship_or_publication"
                and action.get("result_role", "EVIDENCE") == "EVIDENCE"
            ]
            if not selected:
                raise RuntimeError(
                    "source policy/catalogue did not produce an evidence action for the "
                    f"approved publication family: actions={actions!r}; plan={plan!r}"
                )
            if len(selected) != 1:
                raise RuntimeError(
                    "the scoped Crossref publication obligation must resolve to one evidence "
                    f"action, got {len(selected)}: {selected!r}"
                )
            proposed_refs = [str(action["action_id"]) for action in selected]
            result["plan"] = {
                "plan_state": plan.get("plan_state"),
                "capability_gaps": plan.get("capability_gaps", []),
                "source_bound_action_count": len(proposed_refs),
                "source_ids": sorted({str(action.get("source_id")) for action in selected}),
            }

            approved_actions = await service.approve_actions(
                case_id=case_id,
                tenant_id=TENANT_ID,
                approver_id="github-actions:person-case-acceptance-approver",
                action_refs=proposed_refs,
            )
            approved_refs = list(approved_actions["approved_action_refs"])
            result["action_approval"] = {
                "approved_action_count": len(approved_refs),
                "approved_action_refs": approved_refs,
            }

            worker_processes = _start_workers(output_path.parent)
            dispatch = await service.run_case(
                case_id=case_id,
                tenant_id=TENANT_ID,
                idempotency_key=f"pc-e2e-run-{run_id}",
                approved_action_refs=approved_refs,
            )
            result["dispatch"] = dispatch
            if dispatch.get("state") not in {"QUEUED", "PUBLISHED", "ALREADY_REQUESTED"}:
                raise RuntimeError(f"person-case dispatch did not reach the broker: {dispatch!r}")

            dispatch_body = dispatch.get("dispatch") or {}
            published_records = [
                item
                for item in (dispatch_body.get("records") or [])
                if isinstance(item, dict) and item.get("published") is True
            ]
            task_ids = list(dict.fromkeys(
                str(item.get("task_id") or "") for item in published_records
                if str(item.get("task_id") or "")
            ))
            if len(task_ids) != 1 or int(dispatch_body.get("published_count", 0)) != 1:
                raise RuntimeError(
                    "Crossref acceptance must publish exactly one task after duplicate-obligation "
                    f"collapse: dispatch={dispatch!r}"
                )
            result["dispatch"]["expected_task_ids"] = task_ids
            observation, processing = await _wait_for_processed_observation(
                session_factory,
                investigation_id=investigation_id,
                task_id=task_ids[0],
                timeout_seconds=300,
            )
            raw = await _read_verified_raw(observation)
            interpretation = (
                processing.interpretation
                if isinstance(processing.interpretation, dict)
                else {}
            )
            if interpretation.get("status") != "persisted" or interpretation.get("persisted") is not True:
                raise RuntimeError(
                    "Observation parser ran but the canonical interpretation was not persisted: "
                    f"{interpretation!r}"
                )
            result["evidence"] = {
                "observation_id": str(observation.observation_id),
                "source_id": str(observation.source_id or ""),
                "uri": str(observation.uri or ""),
                "content_hash": str(observation.content_hash),
                "status": str(observation.status),
                "processing_result_id": str(processing.processing_result_id),
                "processing_status": str(processing.status),
                "derived_ref": str(processing.derived_ref),
                "record_count": int(processing.record_count),
                "mention_count": int(processing.mention_count),
                "failure_code": str(processing.failure_code or ""),
                "interpretation": interpretation,
                "raw_readback": raw,
            }
            if not processing.derived_ref:
                raise RuntimeError("Observation consumer did not persist a concrete derived_ref")
            if int(processing.record_count) <= 0 or int(raw["doi_title_records"]) <= 0:
                raise RuntimeError(
                    "Crossref returned no DOI/title records accepted by the observation parser"
                )
            if int(raw["anchor_exact_match_records"]) <= 0:
                raise RuntimeError(
                    "Crossref raw records contain no matching given/family author entry for "
                    f"the declared public name {PUBLIC_SUBJECT!r}"
                )

            report = await reports.generate(
                case_id=case_id,
                tenant_id=TENANT_ID,
                actor_id="github-actions:person-case-acceptance-report",
            )
            report_id = str(report.get("report_id") or "")
            if not report_id:
                raise RuntimeError("ResearchCaseReportService did not return a durable report_id")
            readback = await reports.get_report(
                case_id=case_id, report_id=report_id, tenant_id=TENANT_ID
            )
            if readback.get("report_digest") != report.get("report_digest"):
                raise RuntimeError("persisted person-case report read-back digest mismatch")
            if report.get("status") != "COMPLETE":
                raise RuntimeError(
                    "person-case acceptance refuses PARTIAL/BLOCKED reports: "
                    f"status={report.get('status')!r}; coverage={report.get('coverage')!r}"
                )
            actual_obs = report.get("source_inventory", {}).get("actual_observations", [])
            if not any(
                item.get("observation_id") == str(observation.observation_id)
                for item in actual_obs
            ):
                raise RuntimeError(
                    "completion report does not include the Observation committed by the worker"
                )
            findings = list(report.get("findings") or [])
            claims = list(report.get("relation_claims") or [])
            if not claims or not findings:
                raise RuntimeError(
                    "COMPLETE person-case acceptance requires at least one admitted, grounded "
                    f"relation claim and finding; claims={len(claims)} findings={len(findings)}"
                )
            for finding in findings:
                spans = list(finding.get("evidence_spans") or [])
                if not spans or any(span.get("status") != "grounded" for span in spans):
                    raise RuntimeError(
                        f"finding {finding.get('finding_id')!r} lacks fully grounded evidence spans"
                    )
            result["report"] = {
                "report_id": report_id,
                "report_digest": report.get("report_digest"),
                "status": report.get("status"),
                "coverage": report.get("coverage"),
                "source_inventory": report.get("source_inventory"),
                "processing": report.get("processing"),
                "finding_count": len(findings),
                "claim_count": len(claims),
                "all_findings_have_grounded_spans": True,
                "readback_digest_verified": True,
            }
            result["status"] = "PASS"
            _write_report(output_path, result)
            return result
        finally:
            await engine.dispose()
    except Exception as exc:
        result.update(
            status="FAIL",
            error_type=type(exc).__name__,
            error=str(exc),
        )
        _write_report(output_path, result)
        raise
    finally:
        _stop_workers(worker_processes)
        try:
            await close_platform()
        except Exception:
            pass


def main() -> int:
    output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "apps/control-plane/artifacts/person-research-case-e2e.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = asyncio.run(_run_case(output_path))
    except Exception as exc:
        print(f"PERSON_CASE_E2E_FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
