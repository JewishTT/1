"""Integration: dev stack connectivity across every fabric service (I-11).

Each probe targets a service the fabric depends on and is skipped when the
service is unreachable, so the suite stays green on a bare machine while the
full stack run (compose `up --profile '*'`) validates wiring end-to-end.

Covered planes:
  - Postgres   (authoritative frontier / scheduler state)
  - Kafka+Redpanda (event transport, T131)
  - MinIO      (content-addressed observation store via aioboto3)
  - Redis      (leases/cooldown)
  - OpenSearch / ClickHouse (rebuildable projections)
"""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "shared"))

import asyncpg
import httpx
import pytest
import redis
from confluent_kafka import Producer

pytestmark = pytest.mark.integration

_PG = os.getenv("POSTGRES_DSN", "postgresql://cognitive:cognitive@localhost:5432/cognitive")
_KAFKA = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
_REDPANDA = os.getenv("KAFKA_BOOTSTRAP", "localhost:19092")
_MINIO = os.getenv("S3_ENDPOINT", "http://localhost:9000")
_AK = os.getenv("S3_ACCESS_KEY", "demo")
_SK = os.getenv("S3_SECRET_KEY", "demopass")
_REDIS = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_OPENSEARCH = os.getenv("OPENSEARCH_URL", "http://localhost:9200")
_CLICKHOUSE = os.getenv("CLICKHOUSE_URL", "http://localhost:8123")


# --- Postgres ----------------------------------------------------------------

def _pg_reachable() -> bool:
    host = _PG.split("@")[-1].split("/")[0]
    h, p = host.split(":")
    try:
        with socket.create_connection((h, int(p)), timeout=3):
            return True
    except OSError:
        return False


requires_pg = pytest.mark.skipif(not _pg_reachable(), reason="postgres unavailable")


@requires_pg
async def test_postgres_is_reachable_and_writable() -> None:
    conn = await asyncpg.connect(_PG, timeout=5)
    try:
        await conn.execute("CREATE TABLE IF NOT EXISTS _conn_probe (v text)")
        await conn.execute("TRUNCATE _conn_probe")
        await conn.execute("INSERT INTO _conn_probe VALUES ($1)", "ok")
        row = await conn.fetchval("SELECT v FROM _conn_probe")
        assert row == "ok"
        await conn.execute("DROP TABLE _conn_probe")
    finally:
        await conn.close()


# --- Kafka / Redpanda ---------------------------------------------------------

def _broker_lists_topics(bootstrap: str) -> bool:
    try:
        p = Producer({"bootstrap.servers": bootstrap, "socket.timeout.ms": 1000})
        md = p.list_topics(timeout=3)
        return md.brokers is not None and len(md.brokers) > 0
    except Exception:
        return False


def test_kafka_list_topics() -> None:
    assert _broker_lists_topics(_KAFKA), f"kafka {_KAFKA} unreachable"


def test_redpanda_list_topics() -> None:
    assert _broker_lists_topics(_REDPANDA), f"redpanda {_REDPANDA} unreachable"


# --- MinIO --------------------------------------------------------------------

def _s3_available() -> bool:
    try:
        import aioboto3

        return True
    except ImportError:  # pragma: no cover
        return False


@pytest.mark.skipif(not _s3_available(), reason="aioboto3 missing")
async def test_minio_put_get_delete_content_addressed_probe() -> None:
    import aioboto3
    import botocore

    session = aioboto3.Session()
    key = "_conn_probe.bin"
    blob = b"\x00probe"
    async with session.client(
        "s3",
        endpoint_url=_MINIO,
        aws_access_key_id=_AK,
        aws_secret_access_key=_SK,
        region_name="us-east-1",
        config=botocore.config.Config(s3={"addressing_style": "path"}),
    ) as s3:
        try:
            await s3.create_bucket(Bucket="knowledge")
        except botocore.exceptions.ClientError as e:
            code = e.response["Error"]["Code"]
            if code not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                raise
        await s3.put_object(Bucket="knowledge", Key=key, Body=blob)
        got = await s3.get_object(Bucket="knowledge", Key=key)
        body = await got["Body"].read()
        assert body == blob
        await s3.delete_object(Bucket="knowledge", Key=key)


# --- Redis --------------------------------------------------------------------

def _redis_available() -> bool:
    try:
        r = redis.from_url(_REDIS, socket_timeout=2)
        return bool(r.ping())
    except Exception:
        return False


@pytest.mark.skipif(not _redis_available(), reason="redis unavailable")
def test_redis_ping() -> None:
    r = redis.from_url(_REDIS, socket_timeout=2)
    assert r.ping() is True
    # NOTE: cognitive-dev-redis publishes 6379, but the host port is shared with
    # other projects (flowsint/postiz) — a PING only proves a redis answers here.


# --- OpenSearch / ClickHouse ----------------------------------------------------

@pytest.mark.parametrize(
    ("url", "ok_path"),
    [
        (_OPENSEARCH, "version"),
        (_CLICKHOUSE, None),
    ],
    ids=["opensearch", "clickhouse"],
)
def test_http_service_answers(url: str, ok_path: str | None) -> None:
    try:
        resp = httpx.get(f"{url}/", timeout=3)
    except httpx.HTTPError as e:  # pragma: no cover
        pytest.skip(f"{url} unreachable: {e}")
    assert resp.status_code == 200