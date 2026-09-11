"""Registry/runner contract tests (T025-T027, US4, SpiderFoot pattern).

Pinned behaviors:
  - lifecycle: REGISTERED → ACTIVE → STOPPED/FAILED with connector.* emissions
  - deterministic dispatch: module run order is name-sorted, stable across runs
  - bounded runner: backlog bound is enforced; nothing runs after stop()
  - fault containment: a raising module is quarantined and failed; the rest run
  - one shared channel: every module pushes onto the same event channel
  - canonical target normalization via shared/donor/target.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))

import pytest
from registry import (
    ConnectorRegistry,
    ConnectorRunner,
    ConnectorStatus,
    EventChannel,
    ModuleEvent,
    normalize_event_target,
)


def _idle(self) -> None:
    return None


class _PingModule:
    def __init__(self, name: str) -> None:
        self.name = name
        self.runs: list[dict] = []
        self.stopped = False

    def capabilities(self) -> list[str]:
        return ["scan", "harvest"]

    def run(self, task: dict, channel: EventChannel) -> None:
        self.runs.append(dict(task))
        channel.emit(
            ModuleEvent(
                module_name=self.name,
                kind="scan_result",
                target_value=task.get("target", ""),
                normalized=normalize_event_target(str(task.get("target", ""))),
                detail={"repo": "spiderfoot"},
            )
        )

    def stop(self) -> None:
        self.stopped = True


class _RaisingModule(_PingModule):
    def run(self, task: dict, channel: EventChannel) -> None:
        raise RuntimeError("boom")


class _RecordingProducer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def produce(self, topic: str, envelope, key: str = "") -> None:
        self.calls.append((topic, key))


class TestRegistryLifecycle:
    def test_register_activate_deactivate_fail(self) -> None:
        registry = ConnectorRegistry()
        registry.register(_PingModule("http"))
        assert registry.status("http") == ConnectorStatus.REGISTERED
        registry.activate("http")
        assert registry.status("http") == ConnectorStatus.ACTIVE
        registry.deactivate("http")
        assert registry.status("http") == ConnectorStatus.STOPPED
        registry.activate("http")
        registry.fail("http")
        assert registry.status("http") == ConnectorStatus.FAILED

    def test_unknown_module_rejected(self) -> None:
        registry = ConnectorRegistry()
        with pytest.raises(KeyError):
            registry.status("nope")
        with pytest.raises(KeyError):
            registry.activate("nope")

    def test_duplicate_registration_rejected(self) -> None:
        registry = ConnectorRegistry()
        registry.register(_PingModule("dup"))
        with pytest.raises(ValueError):
            registry.register(_PingModule("dup"))

    def test_protocol_violation_rejected(self) -> None:
        registry = ConnectorRegistry()
        with pytest.raises(TypeError):
            registry.register(object())
        with pytest.raises(TypeError):
            bad_module = type(
                "NoRun", (), {"name": "x", "capabilities": str.lower, "stop": _idle}
            )()
            registry.register(bad_module)

    def test_emits_connector_envelopes_with_producer(self) -> None:
        producer = _RecordingProducer()
        registry = ConnectorRegistry(producer=producer)
        registry.register(_PingModule("http"))
        registry.activate("http")
        topics = [topic for topic, _ in producer.calls]
        assert topics == ["connector", "connector"]


class TestDeterministicDispatch:
    def test_dispatch_is_name_sorted(self) -> None:
        registry = ConnectorRegistry()
        for name in ("zebra", "alpha", "mike"):
            registry.register(_PingModule(name))
            registry.activate(name)
        channel = EventChannel()
        for _ in range(2):
            order = registry.dispatch({"target": "example.com"}, channel)
            assert order == ["alpha", "mike", "zebra"]

    def test_dispatch_skips_non_active_and_only_filter(self) -> None:
        registry = ConnectorRegistry()
        registry.register(_PingModule("a"))
        registry.register(_PingModule("b"))
        registry.register(_PingModule("c"))
        registry.activate("a")
        registry.activate("b")
        skip = registry.dispatch({"target": "x"}, EventChannel(), only=["a", "c"])
        assert skip == ["a"]
        assert registry.dispatch({"target": "x"}, EventChannel(), only=["nope"]) == []

    def test_events_share_one_channel(self) -> None:
        registry = ConnectorRegistry()
        for name in ("a", "b"):
            registry.register(_PingModule(name))
            registry.activate(name)
        pings = [registry.module(n) for n in ("a", "b")]
        channel = EventChannel()
        registry.dispatch({"target": "example.com"}, channel)
        events = channel.events()
        assert [e.module_name for e in events] == ["a", "b"]
        assert all(e.kind == "scan_result" for e in events)
        assert events[0].normalized["value"] == "example.com"
        assert pings[0].runs == [{"target": "example.com"}]

    def test_fault_contained_rest_still_runs(self) -> None:
        registry = ConnectorRegistry()
        good = _PingModule("good")
        registry.register(_RaisingModule("bad"))
        registry.register(good)
        registry.activate("bad")
        registry.activate("good")
        order = registry.dispatch({"target": "example.com"}, EventChannel())
        assert order == ["bad", "good"]
        assert registry.status("bad") == ConnectorStatus.FAILED
        assert registry.status("good") == ConnectorStatus.ACTIVE
        assert len(good.runs) == 1


class TestTargetNormalization:
    def test_ip_and_domain_normalized(self) -> None:
        ip = normalize_event_target(" 93.184.216.34 ")
        assert ip["type"] == "IP_ADDRESS"
        assert ip["value"] == "93.184.216.34"
        assert ip["raw"] == "93.184.216.34"

        domain = normalize_event_target("Example.COM.")
        assert domain["type"] == "DOMAIN"
        assert domain["value"] == "example.com"

        empty = normalize_event_target("")
        assert empty["type"] == "UNKNOWN"


class TestBoundedRunner:
    def test_runner_executes_and_is_prompt_to_stop(self) -> None:
        registry = ConnectorRegistry()
        module = _PingModule("a")
        registry.register(module)
        registry.activate("a")
        with ConnectorRunner(registry, max_threads=2, max_queue=4) as runner:
            for i in range(6):
                runner.submit("a", {"target": f"h{i}.example.com"})
        assert len(module.runs) == 6
        assert len(runner.events()) == 6
        module.stop()
        assert module.stopped is True

    def test_submit_rejects_unknown_and_inactive(self) -> None:
        registry = ConnectorRegistry()
        registry.register(_PingModule("a"))
        runner = ConnectorRunner(registry)
        with pytest.raises(KeyError):
            runner.submit("nope", {})
        with pytest.raises(ValueError):
            runner.submit("a", {})

    def test_fault_quarantined_and_other_tasks_complete(self) -> None:
        registry = ConnectorRegistry()
        registry.register(_RaisingModule("bad"))
        registry.register(_PingModule("good"))
        registry.activate("bad")
        registry.activate("good")
        with ConnectorRunner(registry, max_threads=2, max_queue=4) as runner:
            runner.submit("bad", {"target": "a.example"})
            runner.submit("good", {"target": "b.example"})
            runner.submit("good", {"target": "c.example"})
        records = runner.quarantined()
        assert len(records) == 1
        assert "connector.module_fault:bad" in records[0].reason
        assert registry.status("bad") == ConnectorStatus.FAILED
        assert len(registry.module("good").runs) == 2