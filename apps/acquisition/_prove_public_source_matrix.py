"""Live acceptance for public Layer-0 sources and the canonical zero-layer harvester.

Every selected catalogue source is exercised through SourceConnector + SecureFetcher +
the production ArtifactSink. PASS requires a successful response, declared parser output,
raw S3 SHA-256 read-back, PostgreSQL Capture/Observation rows, and Redpanda event read-back.
The separate public-document wave is bounded, HTTPS-only, robots-aware, same-origin, and
persists raw captures before DISCOVERY_ONLY stage observations.

This is an acceptance sample, not a claim that every catalogue source is live or that the
internet can be exhaustively collected.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time
import uuid
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
for directory in ("apps/shared", "apps/acquisition", "apps/control-plane", "apps/interpretation", "apps/zero"):
    sys.path.insert(0, str(ROOT / directory))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from artifact_sink import ArtifactSink
from evidence_writer import PostgresAcquisitionEvidenceWriter
from _prove_readback import read_back
from sources.catalogue import CONTACT_LEVELS, load_catalogue
from sources.connector import SourceConnector, tasks_for
from parsers.families import parse_source
from config.settings import get_settings
from domain.capture import CaptureTimeBasis
from events.content_router import ContentRouter
from events.kafka import IdempotentProducer
from events.observation_gate import ObservationGate
from storage.s3 import ObjectStore
from zero.enrichment.feedback import FeedbackLoop
from zero.evidence import ZeroLayerEvidenceSink
from zero.harvest_wave import HarvestWave
from zero.harvesters.public_document import PublicDocumentHarvester
from zero.harvesters.registry import HarvesterRegistry
from zero.harvesters.transport import SecurePublicTransport
from zero.public_policy import allow_public_candidate
from zero.type_detector import TypeDetector


TENANT = os.environ.get("COGNITIVE_TENANT", "acceptance-public-sources")
INVESTIGATION = "INV-PUBLIC-SOURCE-MATRIX"
BROKERS = os.environ.get("COGNITIVE_KAFKA_BROKERS", "localhost:19092")
S3_ENDPOINT = os.environ.get("COGNITIVE_MINIO_ENDPOINT", "http://localhost:9000")
S3_ACCESS = os.environ.get("COGNITIVE_MINIO_ACCESS_KEY", "demo")
S3_SECRET = os.environ.get("COGNITIVE_MINIO_SECRET_KEY", "demopass")
S3_BUCKET = os.environ.get("COGNITIVE_MINIO_RAW_BUCKET", "knowledge-raw")
OUTPUT = Path(os.environ.get(
    "COGNITIVE_PROOF_OUTPUT",
    str(ROOT / "apps/acquisition/artifacts/acquisition-integration"),
))
MINIMUM_SOURCE_PASSES = int(os.environ.get("COGNITIVE_PUBLIC_SOURCE_MIN_PASSES", "6"))

# Public domain/topic/product queries only. CISA KEV is explicitly a global feed.
LIVE_QUERIES = (
    ("rdap_domain", "python.org", "PUBLIC_DOMAIN"),
    ("dns_google", "python.org", "PUBLIC_DOMAIN"),
    ("certspotter_issuances", "python.org", "PUBLIC_DOMAIN"),
    ("crt_sh_certificates", "python.org", "PUBLIC_DOMAIN"),
    ("wayback_machine_cdx", "https://www.python.org/*", "PUBLIC_DOMAIN"),
    ("wayback_machine_snapshot", "https://www.python.org/about/", "PUBLIC_URL"),
    ("urlscan_public", "domain:python.org", "PUBLIC_DOMAIN"),
    ("wikipedia_search", "Python programming language", "PUBLIC_TOPIC"),
    ("duckduckgo_instant", "Python programming language", "PUBLIC_TOPIC"),
    ("crossref_doi", "Python programming language", "PUBLIC_TOPIC"),
    ("openalex_work", "Python programming language", "PUBLIC_TOPIC"),
    ("arxiv_search", "Python programming language", "PUBLIC_TOPIC"),
    ("github_repos", "python", "PUBLIC_REPOSITORY_SEARCH"),
    ("reddit_subreddit", "python", "PUBLIC_COMMUNITY_SEARCH"),
    ("github_advisories", "requests", "PUBLIC_PACKAGE_ADVISORIES"),
    ("nvd_cve", "Python", "PUBLIC_TECHNOLOGY_VULNERABILITIES"),
    ("cve_search_circl", "Python", "PUBLIC_TECHNOLOGY_VULNERABILITIES"),
    ("cisa_kev_recent", "", "GLOBAL_FEED"),
)


def _write_json(name: str, value: dict) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / name).write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )


def _split_s3_ref(ref: str) -> tuple[str, str]:
    bucket, sep, key = str(ref or "").removeprefix("s3://").partition("/")
    if not sep or not bucket or not key:
        raise ValueError("invalid content-addressed raw_ref")
    return bucket, key


async def _read_raw(store: ObjectStore, raw_ref: str, expected_digest: str) -> tuple[bool, int]:
    bucket, key = _split_s3_ref(raw_ref)
    body = await store.read_range(bucket=bucket, key=key)
    digest = hashlib.sha256(body).hexdigest()
    return digest == expected_digest, len(body)


async def _db_rows(session_factory, tenant_id: str, capture_id: str, observation_id: str) -> tuple[bool, bool]:
    async with session_factory() as session:
        capture = await session.execute(
            text("SELECT 1 FROM public.captures WHERE tenant_id=:tenant AND capture_id=:id"),
            {"tenant": tenant_id, "id": capture_id},
        )
        observation = await session.execute(
            text("SELECT 1 FROM public.observations WHERE tenant_id=:tenant AND observation_id=:id"),
            {"tenant": tenant_id, "id": observation_id},
        )
        return capture.first() is not None, observation.first() is not None


async def _run_source(
    *,
    connector: SourceConnector,
    session_factory,
    store: ObjectStore,
    definition,
    query: str,
    query_scope: str,
) -> dict:
    started = time.monotonic()
    item = {
        "source": definition.name,
        "source_id": definition.source_id,
        "category": definition.category,
        "source_family": definition.source_family,
        "runtime_ref": definition.runtime_ref,
        "contact": definition.contact,
        "query": query,
        "query_scope": query_scope,
        "status": "NOT_RUN",
        "http_status": None,
        "parser": definition.parser,
        "parse_status": None,
        "records": 0,
        "unresolved_required_fields": [],
        "capture_id": None,
        "observation_id": None,
        "raw_ref": None,
        "raw_sha256_readback": False,
        "postgres_capture": False,
        "postgres_observation": False,
        "event_id": None,
        "event_topic": None,
        "event_published": False,
        "event_readback": False,
    }

    if not definition.enabled:
        item["status"] = "DISABLED"
        return item
    if definition.requires_key:
        item["status"] = "CREDENTIAL_REQUIRED"
        return item
    if definition.kind != "http" or definition.runtime_ref:
        item["status"] = "NON_HTTP_RUNTIME_NOT_IN_PUBLIC_HTTP_PROFILE"
        return item
    if definition.contact not in CONTACT_LEVELS or CONTACT_LEVELS[definition.contact] > 3:
        item["status"] = "CONTACT_LEVEL_OUTSIDE_PUBLIC_PROFILE"
        return item
    if definition.contact_inferred or not definition.source_family or not definition.time_basis:
        item["status"] = "SOURCE_PROVENANCE_UNDECLARED"
        return item

    stream = connector.collect(tasks_for(
        definition,
        query,
        tenant_id=TENANT,
        investigation_id=INVESTIGATION,
    ))
    try:
        capture, event = await asyncio.wait_for(anext(stream), timeout=45.0)
    finally:
        await stream.aclose()

    item["http_status"] = int(capture.status)
    parsed = parse_source(
        definition,
        bytes(capture.body or b""),
        status_code=int(capture.status),
    )
    item["parse_status"] = parsed.status
    item["records"] = parsed.record_count
    item["unresolved_required_fields"] = list(parsed.unresolved)
    item["capture_id"] = str(event.get("capture_id") or "")
    item["observation_id"] = str(event.get("observation_id") or "")
    item["raw_ref"] = str(event.get("raw_ref") or "")
    item["event_id"] = str(event.get("event_id") or "")
    item["event_topic"] = str(event.get("event_topic") or "")
    item["event_published"] = bool(event.get("event_published"))

    problems = []
    if not 200 <= int(capture.status) < 300:
        problems.append("PROVIDER_HTTP_STATUS")
    if parsed.status != "ok" or parsed.record_count < 1:
        problems.append("PARSER_EMPTY_OR_FAILED")
    if parsed.unresolved:
        problems.append("REQUIRED_FIELDS_UNRESOLVED")
    if not all((item["capture_id"], item["observation_id"], item["raw_ref"])):
        problems.append("CAPTURE_IDENTITY_INCOMPLETE")
    if item["raw_ref"] and item["capture_id"] and item["observation_id"]:
        try:
            raw_ok, raw_length = await _read_raw(
                store, item["raw_ref"], str(event.get("content_digest") or "")
            )
            item["raw_sha256_readback"] = raw_ok
            item["raw_byte_length"] = raw_length
            if not raw_ok:
                problems.append("RAW_SHA256_READBACK_FAILED")
        except Exception as exc:
            item["raw_readback_error"] = type(exc).__name__
            problems.append("RAW_READBACK_FAILED")
        try:
            cap_ok, obs_ok = await _db_rows(
                session_factory, TENANT, item["capture_id"], item["observation_id"]
            )
            item["postgres_capture"] = cap_ok
            item["postgres_observation"] = obs_ok
            if not cap_ok or not obs_ok:
                problems.append("POSTGRES_CAPTURE_OBSERVATION_MISSING")
        except Exception as exc:
            item["postgres_error"] = type(exc).__name__
            problems.append("POSTGRES_READBACK_FAILED")
    if not item["event_published"] or not item["event_id"] or not item["event_topic"]:
        problems.append("OBSERVATION_EVENT_NOT_ACKNOWLEDGED")

    item["pre_broker_status"] = "PASS_PENDING_EVENT_READBACK" if not problems else problems[0]
    item["problems"] = problems
    item["elapsed_ms"] = round((time.monotonic() - started) * 1000, 1)
    return item


async def _run_zero_layer(
    *, gate: ObservationGate, store: ObjectStore, writer: PostgresAcquisitionEvidenceWriter,
    session_factory,
) -> tuple[dict, list[dict]]:
    seed_url = "https://www.python.org/about/"
    transport = SecurePublicTransport(
        user_agent="COGNITIVE-PublicResearch-Acceptance/1.0",
        max_response_bytes=1_500_000,
        minimum_host_interval_s=1.0,
        max_requests=12,
        max_concurrency=2,
    )
    transport.set_source_metadata(
        seed_url,
        parent_observation_id="",
        discovery_source_id="analyst_public_url_seed",
        action_ref="L0-PUBLIC-ACCEPTANCE-PYTHON-ORG",
    )
    registry = HarvesterRegistry(max_workers=2)
    registry.register(PublicDocumentHarvester())
    wave = HarvestWave(
        detector=TypeDetector(),
        registry=registry,
        transport=transport,
        max_depth=2,
        min_new_seeds=1,
        enable_enrichment=True,
        feedback=FeedbackLoop(kinds=frozenset({"public_page_link"})),
        seed_context={
            seed_url: {
                "discovery_observation_id": "",
                "source_id": "analyst_public_url_seed",
            }
        },
        candidate_allowed=allow_public_candidate,
        max_seed_workers=2,
        max_total_seeds=4,
    )
    artifact_sink = ArtifactSink(
        gate=gate,
        store=store,
        source_family="zero_layer_public_web",
        evidence_writer=writer,
    )
    zero_sink = ZeroLayerEvidenceSink(
        artifact_sink,
        source_id="zero-layer",
        worker_ref="zero-layer-public-web",
    )
    summaries, accepted = await wave.run_and_persist(
        [seed_url],
        evidence_sink=zero_sink,
        tenant_id=TENANT,
        investigation_id=INVESTIGATION,
    )

    observation_ids = []
    checks = []
    for item in accepted:
        capture_id = str(getattr(item, "capture_id", "") or "")
        observation_id = str(getattr(item, "observation_id", "") or "")
        raw_ref = str(getattr(item, "raw_ref", "") or "")
        digest = str(getattr(item, "content_digest", "") or "")
        check = {
            "capture_id": capture_id,
            "observation_id": observation_id,
            "raw_ref": raw_ref,
            "raw_readback": False,
            "postgres_capture": False,
            "postgres_observation": False,
            "event_id": str(getattr(item, "event_id", "") or ""),
            "event_published": bool(getattr(item, "event_id", "") and getattr(item, "topic", "")),
            "stage": str(getattr(item, "stage", "") or ""),
        }
        try:
            check["raw_readback"], check["raw_byte_length"] = await _read_raw(store, raw_ref, digest)
        except Exception as exc:
            check["raw_error"] = type(exc).__name__
        try:
            check["postgres_capture"], check["postgres_observation"] = await _db_rows(
                session_factory, TENANT, capture_id, observation_id
            )
        except Exception as exc:
            check["postgres_error"] = type(exc).__name__
        if observation_id:
            observation_ids.append(observation_id)
        checks.append(check)

    stages = Counter(item["stage"] for item in checks if item["stage"])
    raw_captures = sum(1 for item in accepted if getattr(getattr(item, "artifact", None), "locator", "").startswith("zero-layer/raw/"))
    candidate_types = Counter(
        candidate.kind
        for record in wave.stage_records
        for candidate in record.candidates
    )
    summary = {
        "seed_url": seed_url,
        "waves": len(summaries),
        "physical_http_requests_including_robots": transport.requests_used,
        "raw_page_captures": len(transport.captures),
        "raw_capture_observations": raw_captures,
        "stage_observations": sum(stages.values()),
        "stage_counts": dict(sorted(stages.items())),
        "candidate_types_after_public_policy": dict(sorted(candidate_types.items())),
        "transport_failure_count": len(transport.failures),
        "transport_failure_codes": sorted({
            str(item.get("code") or item.get("error") or "unknown")
            for item in transport.failures
        }),
        "persisted_items": checks,
        "observation_ids": observation_ids,
    }
    return summary, checks


async def main() -> int:
    run_id = str(uuid.uuid4())
    definitions, rejected = load_catalogue()
    by_name = {item.name: item for item in definitions}
    inventory = {
        "accepted_definitions": len(definitions),
        "catalogue_rejections": rejected,
        "by_category": dict(sorted(Counter(d.category for d in definitions).items())),
        "by_contact_level": dict(sorted(Counter(d.contact for d in definitions).items())),
        "by_runtime": dict(sorted(Counter(d.runtime_ref or "http_or_system" for d in definitions).items())),
        "credential_required": sum(1 for d in definitions if d.requires_key),
        "enabled": sum(1 for d in definitions if d.enabled),
    }

    settings = get_settings()
    engine = create_async_engine(settings.postgres.dsn, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    # Fail at startup with the actual runtime connection/schema instead of allowing
    # a later EvidenceWriter insert to obscure a migration/search_path mismatch.
    async with engine.connect() as connection:
        schema_state = (await connection.execute(text("""
            SELECT current_database() AS database,
                   current_schema() AS schema,
                   current_setting('search_path') AS search_path,
                   to_regclass('public.captures')::text AS captures,
                   to_regclass('public.observations')::text AS observations
        """))).mappings().one()
        print(json.dumps({"postgres_schema_preflight": dict(schema_state)}, sort_keys=True, default=str))
        if schema_state["captures"] is None or schema_state["observations"] is None:
            raise RuntimeError(
                "Canonical public evidence schema is incomplete: "
                f"captures={schema_state['captures']!r}, "
                f"observations={schema_state['observations']!r}, "
                f"database={schema_state['database']!r}, "
                f"search_path={schema_state['search_path']!r}"
            )
    producer = IdempotentProducer(bootstrap_servers=BROKERS)
    store = ObjectStore(
        endpoint=S3_ENDPOINT,
        access_key=S3_ACCESS,
        secret_key=S3_SECRET,
        raw_bucket=S3_BUCKET,
    )
    gate = ObservationGate(store=store, router=ContentRouter(), producer=producer)
    writer = PostgresAcquisitionEvidenceWriter(session_factory)
    sink_factory = lambda definition: ArtifactSink(
        gate=gate,
        store=store,
        source_family=definition.source_family,
        evidence_writer=writer,
    )
    connector = SourceConnector(gate=gate, artifact_sink_factory=sink_factory)

    matrix_rows: list[dict] = []
    zero_summary: dict = {}
    zero_checks: list[dict] = []
    readback = None
    try:
        for source_name, query, scope in LIVE_QUERIES:
            definition = by_name.get(source_name)
            if definition is None:
                matrix_rows.append({"source": source_name, "status": "MISSING_FROM_CATALOGUE"})
                continue
            try:
                row = await _run_source(
                    connector=connector,
                    session_factory=session_factory,
                    store=store,
                    definition=definition,
                    query=query,
                    query_scope=scope,
                )
            except asyncio.TimeoutError:
                row = {"source": source_name, "status": "TIMEOUT", "query": query, "query_scope": scope}
            except Exception as exc:
                row = {
                    "source": source_name,
                    "status": "TRANSPORT_OR_ADAPTER_ERROR",
                    "query": query,
                    "query_scope": scope,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:240],
                }
            matrix_rows.append(row)
            await asyncio.sleep(0.35)

        zero_summary, zero_checks = await _run_zero_layer(
            gate=gate, store=store, writer=writer, session_factory=session_factory
        )
        producer.flush(timeout_s=60)

        wanted = {
            str(row.get("observation_id"))
            for row in matrix_rows
            if row.get("observation_id")
        }
        wanted.update(str(item.get("observation_id")) for item in zero_checks if item.get("observation_id"))
        if wanted:
            group = "public-source-matrix-" + run_id
            readback = read_back(
                BROKERS,
                "observation",
                wanted,
                group=group,
                timeout=120,
                parse_envelope=True,
            )
        found = set(readback.found) if readback else set()
        for row in matrix_rows:
            observation_id = str(row.get("observation_id") or "")
            row["event_readback"] = bool(observation_id and observation_id in found)
            if row.get("pre_broker_status") == "PASS_PENDING_EVENT_READBACK":
                row["status"] = "PASS" if row["event_readback"] else "OBSERVATION_EVENT_READBACK_FAILED"
            else:
                row.setdefault("status", row.get("pre_broker_status") or "NOT_RUN")
        for item in zero_checks:
            item["event_readback"] = bool(item.get("observation_id") and item["observation_id"] in found)

        source_passes = sum(1 for row in matrix_rows if row.get("status") == "PASS")
        source_counts = Counter(row.get("status", "UNKNOWN") for row in matrix_rows)
        zero_ok = (
            int(zero_summary.get("raw_page_captures") or 0) >= 1
            and int(zero_summary.get("stage_observations") or 0) >= 1
            and bool(zero_checks)
            and all(
                item.get("raw_readback")
                and item.get("postgres_capture")
                and item.get("postgres_observation")
                and item.get("event_published")
                and item.get("event_readback")
                for item in zero_checks
            )
        )
        all_readback = bool(wanted) and wanted.issubset(found)
        matrix_report = {
            "run_id": run_id,
            "tenant_id": TENANT,
            "investigation_id": INVESTIGATION,
            "target_profile": "public Python ecosystem (python.org / Python topic / requests package)",
            "inventory": inventory,
            "selected_source_count": len(LIVE_QUERIES),
            "source_pass_count": source_passes,
            "minimum_required_source_passes": MINIMUM_SOURCE_PASSES,
            "source_status_counts": dict(sorted(source_counts.items())),
            "redpanda_observation_readback": {
                "wanted": len(wanted),
                "found": len(found),
                "foreign_consumed": getattr(readback, "foreign", 0) if readback else 0,
                "undecodable": getattr(readback, "undecodable", []) if readback else [],
                "elapsed_seconds": round(getattr(readback, "elapsed", 0.0), 3) if readback else 0.0,
                "all_found": all_readback,
            },
            "sources": matrix_rows,
            "zero_layer_live": {
                "status": "PASS" if zero_ok else "FAIL",
                "raw_first_persistence": zero_summary,
                "checks": zero_checks,
            },
        }
        _write_json("public-source-matrix.json", matrix_report)
        _write_json("zero-layer-live.json", matrix_report["zero_layer_live"])

        print(json.dumps({
            "catalogue_definitions": len(definitions),
            "selected_sources": len(LIVE_QUERIES),
            "source_passes": source_passes,
            "source_status_counts": dict(source_counts),
            "zero_layer_status": matrix_report["zero_layer_live"]["status"],
            "observation_readback": len(found),
            "observation_wanted": len(wanted),
            "reports": [
                str(OUTPUT / "public-source-matrix.json"),
                str(OUTPUT / "zero-layer-live.json"),
            ],
        }, indent=2, sort_keys=True))
        return 0 if (
            len(definitions) == 152
            and source_passes >= MINIMUM_SOURCE_PASSES
            and zero_ok
            and all_readback
        ) else 1
    finally:
        try:
            await connector.aclose()
        except Exception:
            pass
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
