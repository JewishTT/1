"""In-memory content-addressed object store (hermetic substitute for S3).

Mirrors the ``storage.s3.ObjectStore`` raw and derived write surfaces used by
the observation gate, interpretation consumer and lake writer. Both
``put_raw_dedup`` and ``put_derived_dedup`` are idempotent by SHA-256 but use
separate namespaces so derived transforms cannot masquerade as fetched evidence.
Introspection helpers let hermetic tests assert the same immutability and lineage
contracts as a real backend.
"""

from __future__ import annotations

from datetime import UTC, datetime

from storage.s3 import RawObjectRef, sha256_bytes


class MemoryObjectStore:
    """Pure in-memory ObjectStore for deterministic, docker-free tests."""

    def __init__(self, *, raw_bucket: str = "knowledge") -> None:
        self.raw_bucket = raw_bucket
        self._objects: dict[str, bytes] = {}
        self._meta: dict[str, dict] = {}

    def _ym(self, when: datetime | None = None) -> str:
        return (when or datetime.now(UTC)).strftime("%Y%m")

    def ref_uri(
        self, *, sha256: str, tenant_id: str, year_month: str | None = None, kind: str = "raw"
    ) -> str:
        ym = year_month or self._ym()
        return f"s3://{self.raw_bucket}/{kind}/{tenant_id}/{ym}/{sha256}"

    async def put_raw_dedup(
        self, body: bytes, *, tenant_id: str, meta: dict | None = None
    ) -> tuple[RawObjectRef, bool]:
        digest = sha256_bytes(body)
        ym = self._ym()
        key = f"raw/{tenant_id}/{ym}/{digest}"
        existed = key in self._objects
        if not existed:
            self._objects[key] = body
            if meta:
                self._meta[key] = dict(meta)
        return (
            RawObjectRef(
                uri=self.ref_uri(sha256=digest, tenant_id=tenant_id, year_month=ym),
                sha256=digest,
                size=len(body),
                tenant_prefix=f"{tenant_id}/{ym}",
                year_month=ym,
            ),
            existed,
        )


    async def put_immutable_object(
        self,
        key: str,
        body: bytes,
        *,
        tenant_id: str = "",
        meta: dict | None = None,
    ) -> bool:
        """Create an immutable object; byte-identical retries return False."""
        if not isinstance(body, bytes):
            raise TypeError("immutable object body must be bytes")
        existing = self._objects.get(key)
        if existing is not None:
            if existing != body:
                raise ValueError(f"immutable object key collision: {key}")
            return False
        self._objects[key] = body
        if meta:
            self._meta[key] = dict(meta)
        return True

    async def list_objects(self, prefix: str) -> list[str]:
        """Return all object keys that begin with prefix."""
        return sorted(key for key in self._objects if key.startswith(prefix))

    async def put_derived_dedup(
        self, body: bytes, *, tenant_id: str, meta: dict | None = None
    ) -> tuple[RawObjectRef, bool]:
        """Mirror ObjectStore's separate immutable derived-object namespace."""
        if not tenant_id or not tenant_id.strip():
            raise ValueError("tenant_id is required for derived artifact storage")
        if not isinstance(body, bytes):
            raise TypeError("derived artifact body must be bytes")
        digest = sha256_bytes(body)
        ym = self._ym()
        key = f"derived/{tenant_id}/{ym}/{digest}"
        existed = key in self._objects
        if not existed:
            self._objects[key] = body
            if meta:
                self._meta[f"derived-meta/{tenant_id}/{ym}/{digest}.json"] = dict(meta)
        return (
            RawObjectRef(
                uri=self.ref_uri(
                    sha256=digest,
                    tenant_id=tenant_id,
                    year_month=ym,
                    kind="derived",
                ),
                sha256=digest,
                size=len(body),
                tenant_prefix=f"{tenant_id}/{ym}",
                year_month=ym,
            ),
            existed,
        )

    async def exists(self, key: str) -> bool:
        return key in self._objects

    async def get(
        self, *, sha256: str, tenant_id: str, year_month: str | None = None
    ) -> bytes | None:
        ym = year_month or self._ym()
        return self._objects.get(f"raw/{tenant_id}/{ym}/{sha256}")

    # Generic keyed objects (data-lake manifests / row-groups): explicitly keyed,
    # not content-addressed — the lake layer owns key layout.
    async def put_object(
        self, key: str, body: bytes, *, tenant_id: str = "", meta: dict | None = None
    ) -> None:
        self._objects[key] = body
        if meta:
            self._meta[key] = dict(meta)

    async def get_object(self, key: str) -> bytes | None:
        return self._objects.get(key)

    async def exists_object(self, key: str) -> bool:
        return key in self._objects

    def keys(self) -> list[str]:
        return sorted(self._objects)

    def count(self) -> int:
        return len(self._objects)
