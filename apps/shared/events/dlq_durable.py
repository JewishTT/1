"""Tenant-scoped durable quarantine backed by immutable object storage."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import quote, urlsplit

from events.dlq import DLQRecord, QuarantineStore

RAW_BUCKET = "knowledge-raw"
META_PREFIX = "dlq/index"
_RECORD_ID = re.compile(r"^DLQ-[a-f0-9]{24}$")


class QuarantineSink(Protocol):
    def put(self, record: DLQRecord) -> str: ...
    def load(self, record_id: str) -> DLQRecord | None: ...
    def index(self) -> list[dict]: ...


@dataclass
class ObjectStoreSink:
    """Store original payloads and metadata in an isolated tenant namespace."""

    store: Any
    tenant_id: str
    raw_bucket: str | None = None

    def __post_init__(self) -> None:
        self.tenant_id = str(self.tenant_id).strip()
        if not self.tenant_id:
            raise ValueError("tenant_id is required for durable quarantine")
        if self.raw_bucket is None:
            self.raw_bucket = str(getattr(self.store, "raw_bucket", RAW_BUCKET))

    @property
    def tenant_prefix(self) -> str:
        return f"{META_PREFIX}/{quote(self.tenant_id, safe='')}/"

    def _meta_key(self, record_id: str) -> str:
        self._validate_record_id(record_id)
        return f"{self.tenant_prefix}{record_id}.json"

    @staticmethod
    def _validate_record_id(record_id: str) -> None:
        if _RECORD_ID.fullmatch(str(record_id)) is None:
            raise ValueError("invalid quarantine record id")

    def _payload_key(self, uri: str) -> str:
        parsed = urlsplit(str(uri))
        if parsed.scheme != "s3" or parsed.netloc != self.raw_bucket:
            raise ValueError("quarantine payload ref has an unexpected object-store URI")
        key = parsed.path.lstrip("/")
        if not key.startswith(f"raw/{quote(self.tenant_id, safe='')}/"):
            raise ValueError("quarantine payload ref is outside the tenant raw namespace")
        return key

    async def aput(self, record: DLQRecord) -> dict[str, Any]:
        tenant_id = record.tenant_id or self.tenant_id
        if tenant_id != self.tenant_id:
            raise PermissionError("quarantine record tenant does not match sink tenant")
        if not isinstance(record.payload, bytes):
            raise TypeError("quarantine payload must be bytes")
        if len(record.payload) > 5 * 1024 * 1024:
            raise ValueError("quarantine payload exceeds the 5 MiB retention limit")

        ref = await self.store.put_raw(
            record.payload,
            tenant_id=self.tenant_id,
            meta={
                "dlq_record_id": record.record_id,
                "topic": record.topic,
                "reason": record.reason,
            },
        )
        payload_key = self._payload_key(ref.uri)
        metadata = {
            "schema_version": 1,
            "record_id": record.record_id,
            "tenant_id": self.tenant_id,
            "reason": record.reason,
            "topic": record.topic,
            "partition": record.partition,
            "preserved": True,
            "fingerprint": record.fingerprint(),
            "payload_sha256": ref.sha256,
            "payload_ref": ref.uri,
            "payload_key": payload_key,
            "payload_size": ref.size,
            "investigation_id": record.investigation_id,
            "source_id": record.source_id,
            "task_id": record.task_id,
            "original_event_id": record.original_event_id,
            "original_event_type": record.original_event_type,
            "status": record.status,
            "detail": dict(record.detail),
        }
        body = json.dumps(
            metadata,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        key = self._meta_key(record.record_id)
        await self.store.put_immutable_object(
            key,
            body,
            tenant_id=self.tenant_id,
            meta={"record_id": record.record_id, "kind": "quarantine-index"},
        )
        return {
            "record_id": record.record_id,
            "tenant_id": self.tenant_id,
            "payload_ref": ref.uri,
            "payload_size": ref.size,
            "metadata_ref": f"s3://{self.raw_bucket}/{key}",
        }

    async def aget_metadata(self, record_id: str) -> dict[str, Any] | None:
        body = await self.store.get_object(self._meta_key(record_id))
        if body is None:
            return None
        metadata = json.loads(body.decode("utf-8"))
        if metadata.get("tenant_id") != self.tenant_id:
            raise PermissionError("quarantine index tenant does not match request tenant")
        if metadata.get("record_id") != record_id:
            raise ValueError("quarantine index record id mismatch")
        return metadata

    async def aload(self, record_id: str) -> DLQRecord | None:
        metadata = await self.aget_metadata(record_id)
        if metadata is None:
            return None
        payload_key = metadata.get("payload_key")
        if not isinstance(payload_key, str) or not payload_key.startswith(
            f"raw/{quote(self.tenant_id, safe='')}/"
        ):
            # Older sidecars stored only an s3:// URI. Parse and validate it instead
            # of passing the URI to an API that expects a bare object key.
            payload_key = self._payload_key(metadata.get("payload_ref", ""))
        payload = await self.store.get_object(payload_key)
        if payload is None:
            raise RuntimeError("quarantine payload object is missing")
        return DLQRecord(
            record_id=metadata["record_id"],
            reason=metadata["reason"],
            payload=payload,
            topic=metadata["topic"],
            partition=int(metadata.get("partition", 0)),
            preserved=bool(metadata.get("preserved", True)),
            tenant_id=metadata["tenant_id"],
            investigation_id=str(metadata.get("investigation_id", "")),
            source_id=str(metadata.get("source_id", "")),
            task_id=str(metadata.get("task_id", "")),
            original_event_id=str(metadata.get("original_event_id", "")),
            original_event_type=str(metadata.get("original_event_type", "")),
            status=int(metadata.get("status", 0)),
            detail=dict(metadata.get("detail") or {}),
        )

    async def alist_page(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        topic: str | None = None,
    ) -> dict[str, Any]:
        if not 1 <= int(limit) <= 100:
            raise ValueError("quarantine page limit must be between 1 and 100")
        token = cursor
        items: list[dict[str, Any]] = []
        next_token: str | None = None
        pages_scanned = 0
        # Topic filtering is bounded to ten S3 pages; the returned continuation token
        # resumes exactly after the last scanned key rather than skipping filtered entries.
        while len(items) < limit and pages_scanned < 10:
            keys, next_token = await self.store.list_objects_page(
                self.tenant_prefix,
                limit=max(50, min(250, limit * 2)),
                continuation_token=token,
            )
            pages_scanned += 1
            for key in keys:
                body = await self.store.get_object(key)
                if body is None:
                    continue
                metadata = json.loads(body.decode("utf-8"))
                if metadata.get("tenant_id") != self.tenant_id:
                    raise PermissionError("cross-tenant quarantine index entry detected")
                if topic is not None and metadata.get("topic") != topic:
                    continue
                items.append({
                    k: v for k, v in metadata.items()
                    if k not in {"payload_ref", "payload_key"}
                })
                if len(items) >= limit:
                    break
            if not next_token:
                break
            token = next_token
        return {"items": items, "next_cursor": next_token, "pages_scanned": pages_scanned}

    async def aindex(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            page = await self.alist_page(limit=100, cursor=cursor)
            result.extend(page["items"])
            cursor = page["next_cursor"]
            if not cursor:
                return result

    def put(self, record: DLQRecord) -> str:
        import anyio

        async def run():
            return await self.aput(record)

        return str(anyio.run(run)["record_id"])

    def load(self, record_id: str) -> DLQRecord | None:
        import anyio

        async def run():
            return await self.aload(record_id)

        return anyio.run(run)

    def index(self) -> list[dict]:
        import anyio

        async def run():
            return await self.aindex()

        return anyio.run(run)


class DurableQuarantineStore(QuarantineStore):
    def __init__(self, sink: ObjectStoreSink) -> None:
        super().__init__(sink=sink)

    def get(self, record_id: str) -> DLQRecord | None:
        found = super().get(record_id)
        return found if found is not None else self.sink.load(record_id)

    def list(self, topic: str | None = None) -> list[dict]:
        records = self.sink.index()
        return records if topic is None else [r for r in records if r.get("topic") == topic]

    def purge(self, record_id: str) -> bool:
        raise RuntimeError(
            "durable quarantine records cannot be purged outside a governed retention workflow"
        )


__all__ = ["DurableQuarantineStore", "RAW_BUCKET", "META_PREFIX", "ObjectStoreSink", "QuarantineSink"]
