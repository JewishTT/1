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
        digest = sha256_bytes(body)
        ym = self._ym()
        key = f"raw/{tenant_id}/{ym}/{digest}"
        if await self.exists(key):
            # No overwrite: identical content already stored (idempotent by hash).
            return RawObjectRef(
                uri=self.ref_uri(sha256=digest, tenant_id=tenant_id, year_month=ym),
                sha256=digest,
                size=len(body),
                tenant_prefix=f"{tenant_id}/{ym}",
                year_month=ym,
            )
        await self._put(self.raw_bucket, key, body)
        if meta:
            meta_key = f"raw-meta/{tenant_id}/{ym}/{digest}.json"
            await self._put(self.raw_bucket, meta_key, json.dumps(meta, default=str).encode())
        return RawObjectRef(
            uri=self.ref_uri(sha256=digest, tenant_id=tenant_id, year_month=ym),
            sha256=digest,
            size=len(body),
            tenant_prefix=f"{tenant_id}/{ym}",
            year_month=ym,
        )

    async def exists(self, key: str) -> bool:
        if self._session is None:
            self._session = aioboto3.Session().client(
                "s3",
                endpoint_url=self.endpoint,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
            )
        try:
            head = await self._session.head_object(Bucket=self.raw_bucket, Key=key)
            return head.get("ResponseMetadata", {}).get("HTTPStatusCode") == 200
        except Exception:
            return False

    async def _put(self, bucket: str, key: str, body: bytes) -> None:
        if self._session is None:
            self._session = aioboto3.Session().client(
                "s3",
                endpoint_url=self.endpoint,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
            )
        await self._session.put_object(Bucket=bucket, Key=key, Body=body)