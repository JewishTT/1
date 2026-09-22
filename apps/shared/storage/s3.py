"""Content-addressed object storage (T011, `contracts/storage.md`, I-1).

Address = content hash (``put_raw`` dedups identical bytes by sha256). Objects
are immutable: no overwrite semantics. Prefixes are tenant-scoped for isolation.
Kafka events carry refs, never blobs (I-5).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from config.settings import get_settings

try:  # pragma: no cover - heavy async client
    import aioboto3
except Exception:  # pragma: no cover - optional at import time for unit tests
    aioboto3 = None  # type: ignore[assignment]


@dataclass(frozen=True)
class RawObjectRef:
    uri: str
    sha256: str
    size: int
    tenant_prefix: str
    year_month: str


@dataclass(frozen=True)
class RawObject:
    ref: RawObjectRef
    body: bytes
    meta: dict


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


class ObjectStore:
    def __init__(
        self,
        *,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        raw_bucket: str | None = None,
    ) -> None:
        s = get_settings().storage
        self.endpoint = endpoint or s.endpoint
        self.access_key = access_key or s.access_key
        self.secret_key = secret_key or s.secret_key
        self.raw_bucket = raw_bucket or s.raw_bucket
        self._session = None

    def _ym(self, when: datetime | None = None) -> str:
        return (when or datetime.now(UTC)).strftime("%Y%m")

    def ref_uri(
        self, *, sha256: str, tenant_id: str, year_month: str | None = None, kind: str = "raw"
    ) -> str:
        ym = year_month or self._ym()
        return f"s3://{self.raw_bucket}/{kind}/{tenant_id}/{ym}/{sha256}"

    async def put_raw(self, body: bytes, *, tenant_id: str, meta: dict | None = None) -> RawObjectRef:
        """Store raw bytes content-addressed; dedup on hash; immutability guard."""
        ref, _existed = await self.put_raw_dedup(body, tenant_id=tenant_id, meta=meta)
        return ref

    async def put_raw_dedup(
        self, body: bytes, *, tenant_id: str, meta: dict | None = None
    ) -> tuple[RawObjectRef, bool]:
        """Store raw bytes content-addressed; return ``(ref, existed)`` so the
        gate can classify lifecycle (duplicate vs. fresh) from storage (R-08)."""
        digest = sha256_bytes(body)
        ym = self._ym()
        key = f"raw/{tenant_id}/{ym}/{digest}"
        if await self.exists(key):
            # No overwrite: identical content already stored (idempotent by hash).
            return (
                RawObjectRef(
                    uri=self.ref_uri(sha256=digest, tenant_id=tenant_id, year_month=ym),
                    sha256=digest,
                    size=len(body),
                    tenant_prefix=f"{tenant_id}/{ym}",
                    year_month=ym,
                ),
                True,
            )
        await self._put(self.raw_bucket, key, body)
        if meta:
            meta_key = f"raw-meta/{tenant_id}/{ym}/{digest}.json"
            await self._put(self.raw_bucket, meta_key, json.dumps(meta, default=str).encode())
        return (
            RawObjectRef(
                uri=self.ref_uri(sha256=digest, tenant_id=tenant_id, year_month=ym),
                sha256=digest,
                size=len(body),
                tenant_prefix=f"{tenant_id}/{ym}",
                year_month=ym,
            ),
            False,
        )

    async def exists(self, key: str) -> bool:
        async with self._s3() as s3:
            try:
                head = await s3.head_object(Bucket=self.raw_bucket, Key=key)
                return head.get("ResponseMetadata", {}).get("HTTPStatusCode") == 200
            except Exception:
                return False

    async def _put(self, bucket: str, key: str, body: bytes) -> None:
        async with self._s3() as s3:
            await s3.put_object(Bucket=bucket, Key=key, Body=body)

    async def read_range(self, *, bucket: str, key: str, offset: int = 0, length: int | None = None) -> bytes:
        """Range read without loading the whole object (T093 archive retrieval).

        ``length=None`` streams from ``offset`` to the end (Open-ended HTTP range
        is handed to S3; a missing object surfaces as a ClientError).
        """
        rng = f"bytes={offset}-" if length is None else f"bytes={offset}-{offset + length - 1}"
        async with self._s3() as s3:
            got = await s3.get_object(Bucket=bucket, Key=key, Range=rng)
            return await got["Body"].read()

    def _s3(self):
        """A fresh aioboto3 S3 client context (entered per operation)."""
        return aioboto3.Session().client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
        )