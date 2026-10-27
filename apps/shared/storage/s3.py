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


    async def put_immutable_object(
        self,
        key: str,
        body: bytes,
        *,
        tenant_id: str = "",
        meta: dict | None = None,
    ) -> bool:
        """Create a content-addressed object; identical retries are no-ops."""
        if not isinstance(body, bytes):
            raise TypeError("immutable object body must be bytes")
        request: dict[str, object] = {
            "Bucket": self.raw_bucket,
            "Key": key,
            "Body": body,
            "IfNoneMatch": "*",
        }
        if meta:
            request["Metadata"] = {str(k): str(v) for k, v in meta.items()}
        try:
            async with self._s3() as s3:
                await s3.put_object(**request)
            return True
        except Exception as exc:
            # A concurrent writer may have won the conditional create. Confirm
            # the durable bytes before treating the failure as a successful retry.
            existing = await self.get_object(key)
            if existing is not None:
                if existing != body:
                    raise ValueError(f"immutable object key collision: {key}") from exc
                return False
            # Older botocore service models may reject IfNoneMatch locally. Use
            # the same digest-derived key with a compatibility fallback; a racing
            # writer can only place the exact same content at that key.
            if type(exc).__name__ == "ParamValidationError":
                await self._put(self.raw_bucket, key, body)
                return True
            raise

    async def get_object(self, key: str) -> bytes | None:
        """Read a generic object-store key; a missing key returns None."""
        async with self._s3() as s3:
            try:
                response = await s3.get_object(Bucket=self.raw_bucket, Key=key)
            except Exception as exc:
                response_data = getattr(exc, "response", {}) or {}
                code = str((response_data.get("Error") or {}).get("Code", ""))
                status = (response_data.get("ResponseMetadata") or {}).get("HTTPStatusCode")
                if code in {"NoSuchKey", "NotFound", "404"} or status == 404:
                    return None
                raise
            return await response["Body"].read()

    async def list_objects(self, prefix: str) -> list[str]:
        """List every key under a prefix, following S3 continuation tokens."""
        keys: list[str] = []
        token: str | None = None
        async with self._s3() as s3:
            while True:
                request: dict[str, object] = {"Bucket": self.raw_bucket, "Prefix": prefix}
                if token:
                    request["ContinuationToken"] = token
                response = await s3.list_objects_v2(**request)
                keys.extend(
                    str(item["Key"])
                    for item in response.get("Contents", [])
                    if "Key" in item
                )
                if not response.get("IsTruncated"):
                    break
                token = response.get("NextContinuationToken")
                if not token:
                    raise RuntimeError(
                        "S3 returned a truncated listing without a continuation token"
                    )
        return sorted(keys)

    async def put_derived_dedup(
        self, body: bytes, *, tenant_id: str, meta: dict | None = None
    ) -> tuple[RawObjectRef, bool]:
        """Store immutable derived bytes in a separate content-addressed namespace.

        Raw evidence writes keep their existing path. Derived output is addressed as
        s3://<bucket>/derived/<tenant>/<yyyymm>/<sha256>, so transforms can never
        overwrite or masquerade as the fetched source bytes. The caller supplies
        provenance metadata such as raw_ref and the transform digest.
        """
        if not tenant_id or not tenant_id.strip():
            raise ValueError("tenant_id is required for derived artifact storage")
        if not isinstance(body, bytes):
            raise TypeError("derived artifact body must be bytes")
        digest = sha256_bytes(body)
        ym = self._ym()
        key = f"derived/{tenant_id}/{ym}/{digest}"
        ref = RawObjectRef(
            uri=self.ref_uri(sha256=digest, tenant_id=tenant_id, year_month=ym, kind="derived"),
            sha256=digest,
            size=len(body),
            tenant_prefix=f"{tenant_id}/{ym}",
            year_month=ym,
        )
        if await self.exists(key):
            return ref, True
        await self._put(self.raw_bucket, key, body)
        if meta:
            meta_key = f"derived-meta/{tenant_id}/{ym}/{digest}.json"
            await self._put(
                self.raw_bucket,
                meta_key,
                json.dumps(meta, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8"),
            )
        return ref, False

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