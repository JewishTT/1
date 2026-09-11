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