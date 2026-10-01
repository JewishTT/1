"""Airbyte protocol correctness, without Docker (§39's fixture half).

§39 splits the requirement deliberately: a fixture proves the *protocol bridge*
and a live connector proves the *integration*. This file is the first half, and
it earns its place by being the only place several of these behaviours can be
exercised at all - a real connector will not, on demand, emit an unknown message
type, a malformed line, or a RECORD with no stream name.

The live half lives in ``_prove_airbyte.py`` and is not optional.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from domain.acquisition_artifact import AcquisitionArtifact  # noqa: E402
from runtime import RuntimeError_  # noqa: E402
from runtime.airbyte import (  # noqa: E402
    FAIL_CHECK,
    FAIL_DISCOVER,
    FAIL_PROTOCOL_MALFORMED,
    FAIL_RECORD_INVALID,
    FAIL_SPEC,
    FAIL_STATE_INVALID,
    LOCATOR_PREFIX,
    AirbyteRuntime,
)


class _FakeProc:
    """Stands in for the docker process, yielding a scripted stdout."""

    def __init__(self, lines: list[str], returncode: int = 0) -> None:
        self._lines = list(lines)
        self._rc = returncode
        self.stdout = self
        self.stderr = asyncio.StreamReader()

    async def readline(self) -> bytes:
        if not self._lines:
            return b""
        return (self._lines.pop(0) + "\n").encode()

    async def wait(self) -> int:
        return self._rc

    def kill(self) -> None:
        pass


def _msg(kind: str, **body) -> str:
    return json.dumps({"type": kind, **body})


def _runtime(lines: list[str], **kw) -> tuple[AirbyteRuntime, list[list[str]]]:
    """A runtime whose ``_execute`` yields scripted messages instead of spawning."""
    rt = AirbyteRuntime(image="fixture/connector:v1", image_digest="sha256:fixture", **kw)
    seen: list[list[str]] = []

    async def fake_execute(argv):
        seen.append(list(argv))
        for line in lines:
            yield json.loads(line)

    rt._execute = fake_execute  # type: ignore[method-assign]
    return rt, seen


RECORD = {
    "type": "RECORD",
    "record": {
        "namespace": "public",
        "stream": "widgets",
        "data": {"id": 1, "name": "acme"},
        "emitted_at": 1767225600000,
    },
}


class TestSpecCheckDiscover:
    @pytest.mark.asyncio
    async def test_spec_returns_the_connector_spec(self):
        rt, _ = _runtime(
            [_msg("SPEC", spec={"documentationUrl": "u", "connectionSpecification": {}})]
        )
        run = await rt.spec()
        assert run.spec["documentationUrl"] == "u"

    @pytest.mark.asyncio
    async def test_spec_without_a_spec_message_fails_by_name(self):
        rt, _ = _runtime([_msg("LOG", log={"message": "hi"})])
        with pytest.raises(RuntimeError_) as exc:
            await rt.spec()
        assert exc.value.code == FAIL_SPEC

    @pytest.mark.asyncio
    async def test_check_succeeds_only_on_succeeded(self):
        rt, _ = _runtime([_msg("CONNECTION_STATUS", connectionStatus={"status": "SUCCEEDED"})])
        assert (await rt.check("/cfg/config.json")).connection_status == "SUCCEEDED"

    @pytest.mark.asyncio
    async def test_check_failure_is_named_and_carries_the_reason(self):
        """§104: check failed is not 'no records'."""
        rt, _ = _runtime(
            [
                _msg(
                    "CONNECTION_STATUS",
                    connectionStatus={"status": "FAILED", "message": "bad host"},
                )
            ]
        )
        with pytest.raises(RuntimeError_) as exc:
            await rt.check("/cfg/config.json")
        assert exc.value.code == FAIL_CHECK
        assert "bad host" in exc.value.message

    @pytest.mark.asyncio
    async def test_discover_records_stream_count(self):
        rt, _ = _runtime([_msg("CATALOG", catalog={"streams": [{"name": "a"}, {"name": "b"}]})])
        run = await rt.discover("/cfg/config.json")
        assert len(run.catalog["streams"]) == 2
        assert run.to_dict()["stream_count"] == 2

    @pytest.mark.asyncio
    async def test_discover_without_a_catalog_fails_by_name(self):
        rt, _ = _runtime([_msg("LOG", log={"message": "x"})])
        with pytest.raises(RuntimeError_) as exc:
            await rt.discover("/cfg/config.json")
        assert exc.value.code == FAIL_DISCOVER

    @pytest.mark.asyncio
    async def test_commands_pass_the_official_flags(self):
        """§27: the documented Docker boundary."""
        rt, seen = _runtime([_msg("CONNECTION_STATUS", connectionStatus={"status": "SUCCEEDED"})])
        await rt.check("/cfg/config.json")
        assert seen[0][-2:] == ["--config", "/cfg/config.json"]


class TestRecordHandling:
    @pytest.mark.asyncio
    async def test_record_becomes_an_artifact(self):
        rt, _ = _runtime([_msg("RECORD", record=RECORD["record"])])
        got = [a async for a in rt.acquire({"config_path": "c", "catalog_path": "k"})]
        assert len(got) == 1
        assert isinstance(got[0], AcquisitionArtifact)
        assert json.loads(got[0].body) == {"id": 1, "name": "acme"}

    @pytest.mark.asyncio
    async def test_locator_carries_namespace_stream_and_index(self):
        """§10 and §33: the message index, because streams are multiplexed."""
        rt, _ = _runtime([_msg("RECORD", record=RECORD["record"])])
        got = [a async for a in rt.acquire({"config_path": "c", "catalog_path": "k"})]
        assert got[0].locator == f"{LOCATOR_PREFIX}public/widgets:0"

    @pytest.mark.asyncio
    async def test_multiplexed_streams_get_distinct_locators(self):
        """§33: records of two streams are interleaved and must stay separable."""
        a = {"namespace": "s1", "stream": "x", "data": {"k": 1}, "emitted_at": 1}
        b = {"namespace": "s2", "stream": "y", "data": {"k": 2}, "emitted_at": 2}
        rt, _ = _runtime([_msg("RECORD", record=a), _msg("RECORD", record=b)])
        got = [x async for x in rt.acquire({"config_path": "c", "catalog_path": "k"})]
        assert [x.locator for x in got] == [
            f"{LOCATOR_PREFIX}s1/x:0",
            f"{LOCATOR_PREFIX}s2/y:1",
        ]

    @pytest.mark.asyncio
    async def test_identical_record_data_in_two_streams_is_two_artifacts(self):
        """§34: the same JSON in two streams is two observed occurrences."""
        same = {"k": "same"}
        a = {"namespace": "s1", "stream": "x", "data": same, "emitted_at": 1}
        b = {"namespace": "s2", "stream": "y", "data": same, "emitted_at": 2}
        rt, _ = _runtime([_msg("RECORD", record=a), _msg("RECORD", record=b)])
        got = [x async for x in rt.acquire({"config_path": "c", "catalog_path": "k"})]
        assert got[0].body == got[1].body
        assert got[0].record_digest() == got[1].record_digest()

    @pytest.mark.asyncio
    async def test_record_without_a_stream_is_quarantined_not_yielded(self):
        rt, _ = _runtime(
            [
                _msg("RECORD", record={"namespace": "public", "data": {}}),
                _msg("RECORD", record=RECORD["record"]),
            ]
        )
        got = [x async for x in rt.acquire({"config_path": "c", "catalog_path": "k"})]
        assert len(got) == 1
        assert rt.run.quarantined[0]["code"] == FAIL_RECORD_INVALID

    @pytest.mark.asyncio
    async def test_oversized_record_is_refused_by_name(self):
        big = {"namespace": "p", "stream": "s", "data": {"blob": "x" * 5000}, "emitted_at": 1}
        rt, _ = _runtime([_msg("RECORD", record=big)], max_record_bytes=100)
        got = [x async for x in rt.acquire({"config_path": "c", "catalog_path": "k"})]
        assert got == []
        assert rt.run.quarantined[0]["code"] == "resource_limit_exceeded"


class TestStateIsControlPlane:
    """§28 and §160: STATE is a checkpoint and never evidence."""

    @pytest.mark.asyncio
    async def test_state_yields_no_artifact(self):
        rt, _ = _runtime([_msg("STATE", state={"stream": {"x": 1}})])
        got = [x async for x in rt.acquire({"config_path": "c", "catalog_path": "k"})]
        assert got == []
        assert rt.run.states == 1

    @pytest.mark.asyncio
    async def test_a_state_before_any_record_is_the_resume_point(self):
        """§93: the checkpoint a run *starts* from is state_before."""
        rt, _ = _runtime([_msg("STATE", state={"stream": {"s": 1}})])
        [x async for x in rt.acquire({"config_path": "c", "catalog_path": "k"})]
        assert rt.run.state_before == {"stream": {"s": 1}}
        assert rt.run.state_after is None

    @pytest.mark.asyncio
    async def test_a_state_after_records_is_the_new_checkpoint(self):
        """§93: the checkpoint a run *leaves behind* is state_after."""
        rt, _ = _runtime(
            [
                _msg("RECORD", record=RECORD["record"]),
                _msg("RECORD", record={**RECORD["record"], "data": {"id": 2}}),
                _msg("STATE", state={"stream": {"s": 7}}),
            ]
        )
        [x async for x in rt.acquire({"config_path": "c", "catalog_path": "k"})]
        assert rt.run.state_after == {"stream": {"s": 7}}
        assert rt.run.state_before is None

    @pytest.mark.asyncio
    async def test_state_is_not_counted_as_a_record(self):
        """§138: observation_count == record_count, STATE excluded."""
        rt, _ = _runtime(
            [_msg("RECORD", record=RECORD["record"]), _msg("STATE", state={"stream": {}})]
        )
        got = [x async for x in rt.acquire({"config_path": "c", "catalog_path": "k"})]
        assert rt.run.records == len(got) == 1
        assert rt.run.states == 1

    @pytest.mark.asyncio
    async def test_malformed_state_is_quarantined(self):
        rt, _ = _runtime([_msg("STATE", state="not-an-object")])
        [x async for x in rt.acquire({"config_path": "c", "catalog_path": "k"})]
        assert rt.run.quarantined[0]["code"] == FAIL_STATE_INVALID


class TestOtherMessageClasses:
    @pytest.mark.asyncio
    async def test_logs_are_counted_and_never_yielded(self):
        rt, _ = _runtime([_msg("LOG", log={"level": "INFO", "message": "x"})])
        got = [x async for x in rt.acquire({"config_path": "c", "catalog_path": "k"})]
        assert got == []
        assert rt.run.logs == 1

    @pytest.mark.asyncio
    async def test_trace_is_recorded_for_diagnosis(self):
        rt, _ = _runtime([_msg("TRACE", trace={"type": "ERROR"})])
        [x async for x in rt.acquire({"config_path": "c", "catalog_path": "k"})]
        assert rt.run.traces == 1
        assert rt.run.quarantined[0]["code"] == "trace"

    @pytest.mark.asyncio
    async def test_unknown_type_is_preserved_never_dropped(self):
        """§32: a protocol that grows a message type is not a failure."""
        rt, _ = _runtime([_msg("SOMETHING_NEW", payload={"a": 1})])
        got = [x async for x in rt.acquire({"config_path": "c", "catalog_path": "k"})]
        assert got == []
        assert rt.run.unknown == 1
        q = rt.run.quarantined[0]
        assert q["code"] == "unknown_message_type"
        assert q["raw"], "the raw line must be kept for replay (§108)"


class TestProtocolFraming:
    @pytest.mark.asyncio
    async def test_non_json_line_fails_by_name(self):
        """§32: malformed output is refused with a reason, not silently skipped."""
        rt = AirbyteRuntime(image="fixture/connector:v1")

        async def fake_execute(argv):
            raise RuntimeError_(FAIL_PROTOCOL_MALFORMED, "stdout line was not JSON")
            yield  # pragma: no cover - makes this an async generator

        rt._execute = fake_execute  # type: ignore[method-assign]
        with pytest.raises(RuntimeError_) as exc:
            [x async for x in rt.acquire({"config_path": "c", "catalog_path": "k"})]
        assert exc.value.code == FAIL_PROTOCOL_MALFORMED

    @pytest.mark.asyncio
    async def test_message_without_a_type_is_refused(self):
        rt = AirbyteRuntime(image="fixture/connector:v1")

        async def fake_execute(argv):
            raise RuntimeError_(FAIL_PROTOCOL_MALFORMED, "stdout line has no message type")
            yield  # pragma: no cover - makes this an async generator

        rt._execute = fake_execute  # type: ignore[method-assign]
        with pytest.raises(RuntimeError_):
            [x async for x in rt.acquire({"config_path": "c", "catalog_path": "k"})]


class TestRuntimeMetadata:
    @pytest.mark.asyncio
    async def test_artifacts_are_version_bound(self):
        """§95: producer and version travel with the output."""
        rt, _ = _runtime([_msg("RECORD", record=RECORD["record"])])
        task = {"config_path": "c", "catalog_path": "k", "runtime_version": "2.7.1"}
        got = [x async for x in rt.acquire(task)]
        assert got[0].producer == "airbyte"
        assert got[0].producer_version == "2.7.1"
        assert got[0].metadata["connector_ref"]

    @pytest.mark.asyncio
    async def test_worker_ref_is_not_http(self):
        """§13: an Airbyte task must not route to the HTTP worker."""
        rt, _ = _runtime([_msg("RECORD", record=RECORD["record"])])
        got = [x async for x in rt.acquire({"config_path": "c", "catalog_path": "k"})]
        assert got[0].worker_ref == "airbyte"

    @pytest.mark.asyncio
    async def test_transport_names_the_process_boundary(self):
        rt, _ = _runtime([_msg("RECORD", record=RECORD["record"])])
        got = [x async for x in rt.acquire({"config_path": "c", "catalog_path": "k"})]
        assert got[0].transport == "docker-stdio"

    @pytest.mark.asyncio
    async def test_digest_is_deterministic(self):
        lines = [_msg("RECORD", record=RECORD["record"])]
        a, _ = _runtime(lines)
        b, _ = _runtime(lines)
        ga = [x async for x in a.acquire({"config_path": "c", "catalog_path": "k"})]
        gb = [x async for x in b.acquire({"config_path": "c", "catalog_path": "k"})]
        assert ga[0].record_digest() == gb[0].record_digest()
        addr = {"tenant_id": "t", "capture_id": "CAP-x"}
        assert ga[0].observation_identity(**addr) == gb[0].observation_identity(**addr)

    def test_image_digest_is_carried_on_the_run(self):
        rt = AirbyteRuntime(image="x/y:1", image_digest="sha256:abc")
        run = rt._new_run("spec")
        assert run.image_digest == "sha256:abc"
        assert run.to_dict()["image_digest"] == "sha256:abc"
