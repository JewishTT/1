"""Contract tests for ObjectStore (T017, I-1, contracts/storage.md).

Content-addressed: dedup by sha256. No overwrite semantics. Provenance refs only on Kafka (I-5).
"""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "apps" / "shared"))

import pytest

from storage.s3 import RawObjectRef, sha256_bytes


@pytest.mark.contract
class TestStorageContract:
    def test_sha256_deterministic(self) -> None:
        body = b"hello cognitive platform"
        h1 = sha256_bytes(body)
        h2 = sha256_bytes(body)
        assert h1 == h2
        assert len(h1) == 64

    def test_sha256_matches_stdlib(self) -> None:
        body = b"test body for content addressing"
        expected = hashlib.sha256(body).hexdigest()
        assert sha256_bytes(body) == expected

    def test_raw_object_ref_frozen(self) -> None:
        ref = RawObjectRef(
            uri="s3://knowledge/raw/tenant/202609/abc123",
            sha256="abc123",
            size=1024,
            tenant_prefix="tenant/202609",
            year_month="202609",
        )
        assert ref.uri.startswith("s3://")
        with pytest.raises(AttributeError):
            ref.sha256 = "changed"

    def test_ref_uri_format(self) -> None:
        ref = RawObjectRef(
            uri="s3://knowledge/raw/tenant/202609/deadbeef",
            sha256="deadbeef",
            size=0,
            tenant_prefix="tenant/202609",
            year_month="202609",
        )
        assert "/raw/" in ref.uri
        assert ref.year_month in ref.uri

    def test_store_constructor_from_settings(self) -> None:
        from storage.s3 import ObjectStore

        store = ObjectStore(endpoint="http://localhost:9000", access_key="demo", secret_key="demo")
        assert store.endpoint == "http://localhost:9000"
        assert store.raw_bucket == "knowledge"

    def test_ym_format(self) -> None:
        from storage.s3 import ObjectStore

        store = ObjectStore()
        assert len(store._ym()) == 6
        assert store._ym().isdigit()

    @pytest.mark.asyncio
    async def test_derived_artifacts_use_a_separate_content_addressed_namespace(monkeypatch) -> None:
        from storage.memory import MemoryObjectStore
        from storage.s3 import ObjectStore

        tenant_id = "tenant-derived-test"
        raw_body = b'{"source":"unaltered raw"}'
        derived_body = b'{"schema":"derived/v1","normalized":true}'
        meta = {"raw_ref": "s3://knowledge/raw/source/202610/raw-digest"}

        # Verify the hermetic adapter preserves the same raw/derived contract.
        memory = MemoryObjectStore()
        raw_ref, raw_existed = await memory.put_raw_dedup(raw_body, tenant_id=tenant_id)
        derived_ref, derived_existed = await memory.put_derived_dedup(
            derived_body, tenant_id=tenant_id, meta=meta
        )
        same_ref, same_existed = await memory.put_derived_dedup(
            derived_body, tenant_id=tenant_id, meta=meta
        )

        assert raw_existed is False
        assert derived_existed is False
        assert same_existed is True
        assert raw_ref.uri != derived_ref.uri
        assert "/raw/" in raw_ref.uri
        assert "/derived/" in derived_ref.uri
        assert same_ref == derived_ref
        assert await memory.get_object(
            f"derived/{tenant_id}/{derived_ref.year_month}/{derived_ref.sha256}"
        ) == derived_body
        assert await memory.get(
            sha256=raw_ref.sha256, tenant_id=tenant_id, year_month=raw_ref.year_month
        ) == raw_body

        # Verify the S3 implementation's key layout and no-overwrite behavior without
        # a running MinIO instance. The test exercises the real ObjectStore method;
        # only the transport calls are replaced.
        s3 = ObjectStore(
            endpoint="http://127.0.0.1:9000",
            access_key="test",
            secret_key="test",
            raw_bucket="knowledge",
        )
        persisted: dict[str, bytes] = {}

        async def exists(key: str) -> bool:
            return key in persisted

        async def put(bucket: str, key: str, body: bytes) -> None:
            assert bucket == "knowledge"
            if key in persisted:
                raise AssertionError(f"derived object attempted overwrite: {key}")
            persisted[key] = body

        monkeypatch.setattr(s3, "exists", exists)
        monkeypatch.setattr(s3, "_put", put)

        s3_ref, s3_existed = await s3.put_derived_dedup(
            derived_body, tenant_id=tenant_id, meta=meta
        )
        s3_replay_ref, s3_replay_existed = await s3.put_derived_dedup(
            derived_body, tenant_id=tenant_id, meta=meta
        )

        object_key = f"derived/{tenant_id}/{s3_ref.year_month}/{s3_ref.sha256}"
        metadata_key = f"derived-meta/{tenant_id}/{s3_ref.year_month}/{s3_ref.sha256}.json"
        assert s3_existed is False
        assert s3_replay_existed is True
        assert s3_ref == s3_replay_ref
        assert object_key in persisted and persisted[object_key] == derived_body
        assert metadata_key in persisted
        assert b'"raw_ref"' in persisted[metadata_key]
        assert "/derived/" in s3_ref.uri
