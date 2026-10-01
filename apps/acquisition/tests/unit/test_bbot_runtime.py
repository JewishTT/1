"""BBOT as a first-class runtime, and the shared record stream (ACQ-14, §47-§50).

BBOT is not a "tool" here, so these test the properties that make it a runtime:
a stable locator, provenance that is carried but never interpreted, SCAN events
kept out of the evidence count, and an identity that survives the fact that BBOT's
event ordering is not reproducible between live runs (§96).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from runtime.bbot import (  # noqa: E402
    BBOT_IMAGE,
    DONOR_EVENT_FIELDS,
    LOCATOR_PREFIX,
    RUN_EVENT_TYPES,
    BbotRuntime,
)
from runtime.record_stream import read_record_stream  # noqa: E402

DNS_EVENT = {
    "type": "DNS_NAME",
    "id": "DNS_NAME:0caaf24ab1a0c33440c06afe99df986365b0781f",
    "uuid": "DNS_NAME:cd2694d8-d0c5-423f-9c4c-9d4e70160a41",
    "data": "example.com",
    "parent": "SCAN:bf4dd1d519ac9df2e85b1d4b9eaf4a63dbf9e39b",
    "parent_uuid": "SCAN:4a241de6-9c90-44e2-9882-997ab7fb961b",
    "timestamp": 1790796299.00802,
    "module": "SEED",
    "module_sequence": "SEED",
    "discovery_path": ["Scan janice seeded with DNS_NAME: example.com"],
    "discovery_context": "Scan janice seeded with DNS_NAME: example.com",
    "parent_chain": ["DNS_NAME:cd2694d8-d0c5-423f-9c4c-9d4e70160a41"],
    "scope_description": "in-scope",
}
SCAN_EVENT = {"type": "SCAN", "uuid": "SCAN:abc", "id": "SCAN:def", "data": {"id": "x"}}


def _rt() -> BbotRuntime:
    rt = BbotRuntime()
    return rt


def _art(message: dict, index: int = 0):
    return rt_art(rt=_rt(), message=message, index=index)


def rt_art(*, rt, message: dict, index: int):
    return rt._to_artifact(message, "TSK-1", "bbot.recon", "example.com", index)


class TestBbotIdentityAndProvenance:
    def test_locator_uses_the_donors_own_event_uuid(self):
        """§96/§97: ordering is not reproducible, so identity must not be the index."""
        a = _art(DNS_EVENT, index=0)
        b = _art(DNS_EVENT, index=17)
        assert a.locator == b.locator, "arrival position must not enter the locator"
        assert a.locator.startswith(LOCATOR_PREFIX)
        assert DNS_EVENT["uuid"] in a.locator

    def test_distinct_events_get_distinct_locators(self):
        a = _art(DNS_EVENT)
        b = _art({**DNS_EVENT, "uuid": "DNS_NAME:other"})
        assert a.locator != b.locator

    def test_falls_back_to_id_then_index(self):
        no_uuid = {**DNS_EVENT, "id": "DNS_NAME:xyz"}
        no_uuid.pop("uuid")
        assert "DNS_NAME:xyz" in _art(no_uuid).locator
        bare = {"type": "X", "data": "y"}
        assert _art(bare, index=5).locator.endswith("seq-5")

    def test_every_section_48_field_is_carried(self):
        meta = _art(DNS_EVENT).metadata
        for name in ("donor_event_type", "donor_event_id", "donor_event_uuid",
                     "donor_module", "donor_parent", "donor_parent_uuid",
                     "donor_discovery_path", "donor_parent_chain", "donor_scope"):
            assert meta.get(name) is not None, f"{name} missing from the artifact"

    def test_the_whole_event_is_the_body(self):
        """§48: preserving only ``data`` would make provenance unrecoverable."""
        body = json.loads(_art(DNS_EVENT).body)
        assert body["parent_chain"] == DNS_EVENT["parent_chain"]
        assert body["discovery_path"] == DNS_EVENT["discovery_path"]

    def test_a_field_the_tool_omitted_stays_absent(self):
        """§21's rule applied to events: absence is not ``None``."""
        meta = _art({**DNS_EVENT, "parent_chain": None}).metadata
        assert "donor_parent_chain" in meta  # explicitly null is carried
        thin = {"type": "X", "data": "y"}
        assert "donor_parent" not in _art(thin).metadata


class TestBbotParentIsNotARelation:
    """§49 and §160: donor derivation context is not a platform RelationClaim."""

    def test_provenance_is_marked_as_donor_context(self):
        meta = _art(DNS_EVENT).metadata
        assert meta["provenance_kind"] == "donor_derivation_context"

    def test_no_relation_is_asserted(self):
        assert _art(DNS_EVENT).metadata["relation_asserted"] is False

    def test_the_runtime_imports_no_graph_or_claim_symbol(self):
        import ast

        tree = ast.parse(Path("apps/acquisition/runtime/bbot.py").read_text("utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        for banned in ("graph", "claims", "admission", "projection", "EntityStore"):
            assert banned not in imported

    def test_scan_events_are_run_metadata_not_evidence(self):
        """§28's discipline, applied to BBOT's vocabulary."""
        assert "SCAN" in RUN_EVENT_TYPES
        from runtime.bbot import _BbotAdapter

        adapter = _BbotAdapter()
        assert adapter.accepts(DNS_EVENT) is True
        assert adapter.accepts(SCAN_EVENT) is False


class TestBbotScopeAndVersioning:
    def test_argv_is_passive_by_default(self):
        """§144: egress is a declared decision, and passive is the default."""
        argv = _rt()._argv("example.com")
        assert "-t" in argv and "example.com" in argv
        assert "-rf" in argv and "passive" in argv
        assert "--json" in argv

    def test_target_is_not_interpreted_as_shell(self):
        argv = _rt()._argv("example.com; rm -rf /")
        joined = " ".join(argv)
        assert "example.com; rm -rf /" in argv, "the target is one token"
        assert joined.count(";") == 1, "no shell metacharacter was consumed"

    def test_image_and_digest_are_pinned(self):
        rt = _rt()
        assert "@sha256:" in BBOT_IMAGE
        assert rt._digest.startswith("sha256:")

    def test_worker_ref_is_not_http(self):
        """§13: a BBOT task must not route to the HTTP worker."""
        assert _art(DNS_EVENT).worker_ref == "bbot"

    def test_transport_names_the_process_boundary(self):
        assert _art(DNS_EVENT).transport == "docker-exec"

    def test_execution_class_is_event_producing(self):
        assert _rt().execution_class == "event_producing"
        assert _rt().runtime_ref == "bbot"


class TestBbotPayloadBoundary:
    def test_json_events_only(self):
        assert _rt().capabilities() and "recon" in _rt().capabilities()

    def test_records_digest_is_deterministic_for_the_same_event(self):
        a = _art(DNS_EVENT)
        b = _art(DNS_EVENT)
        assert a.record_digest() == b.record_digest()
        assert a.observation_identity(tenant_id="t", capture_id="CAP-x") == (
            b.observation_identity(tenant_id="t", capture_id="CAP-x")
        )

    def test_a_timed_event_differs_from_an_untimed_one(self):
        """Two live runs are two acquisitions, not a replay (§12 vs §96)."""
        a = _art(DNS_EVENT)
        b = _art({**DNS_EVENT, "timestamp": DNS_EVENT["timestamp"] + 1})
        assert a.record_digest() != b.record_digest()

    def test_parser_hint_is_declared(self):
        """§63: what reads a BBOT event."""
        assert _art(DNS_EVENT).metadata["parser_hint"] == "structured_fields"

    def test_donor_field_list_covers_the_verified_schema(self):
        for name in ("type", "id", "uuid", "data", "parent", "parent_uuid",
                     "timestamp", "module", "module_sequence", "discovery_path",
                     "parent_chain", "scope_description"):
            assert name in DONOR_EVENT_FIELDS


class TestSharedRecordStream:
    """The unification: one reader, two families."""

    @pytest.mark.asyncio
    async def test_reads_ndjson_and_keeps_order(self):
        async def lines():
            for i in range(3):
                yield json.dumps({"type": "DNS_NAME", "uuid": f"u{i}", "data": i}) + "\n"

        from runtime.bbot import _BbotAdapter

        out = [r async for r in read_record_stream(lines(), _BbotAdapter())]
        assert [r.index for r in out] == [0, 1, 2]
        assert out[0].extra["donor_uuid"] == "u0"

    @pytest.mark.asyncio
    async def test_skips_run_events_without_failing(self):
        async def lines():
            yield json.dumps(SCAN_EVENT)
            yield json.dumps(DNS_EVENT)
            yield json.dumps(SCAN_EVENT)
            yield json.dumps({**DNS_EVENT, "uuid": "DNS_NAME:second"})

        from runtime.bbot import _BbotAdapter

        out = [r async for r in read_record_stream(lines(), _BbotAdapter())]
        assert len(out) == 2

    @pytest.mark.asyncio
    async def test_a_malformed_line_does_not_discard_the_rest(self):
        """§32: one bad line is not a protocol failure."""

        async def lines():
            yield "{not json"
            yield json.dumps(DNS_EVENT)
            yield ""
            yield json.dumps({**DNS_EVENT, "uuid": "DNS_NAME:second"})

        from runtime.bbot import _BbotAdapter

        out = [r async for r in read_record_stream(lines(), _BbotAdapter())]
        assert len(out) == 2

    @pytest.mark.asyncio
    async def test_oversized_record_is_refused_by_name(self):
        from runtime import RuntimeError_
        from runtime.bbot import _BbotAdapter

        async def lines():
            yield json.dumps({**DNS_EVENT, "blob": "x" * 5000})

        with pytest.raises(RuntimeError_) as exc:
            [r async for r in read_record_stream(lines(), _BbotAdapter(), max_record_bytes=100)]
        assert exc.value.code == "resource_limit_exceeded"
