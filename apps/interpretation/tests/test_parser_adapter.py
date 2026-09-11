"""Unit tests: ParserAdapter can_parse/parse (T027, FR-010, NetForensicAI pattern)."""

import functools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "interpretation"))

import pytest

from parsers.registry import Finding, ParserAdapter, ParserLimitError, ParserRegistry


class _CsvAdapter:
    name = "csv-parser"
    content_types: tuple[str, ...] = ("text/csv",)

    def can_parse(self, artifact) -> bool:
        if not isinstance(artifact, (bytes, bytearray)):
            return False
        head = bytes(artifact[:1])
        return head in (b"a", b"i", b"c", b"id") and b"," in artifact

    def parse(self, artifact) -> list[Finding]:
        text = bytes(artifact).decode("utf-8", errors="replace")
        return [
            Finding(kind="csv_row", value=row, offset=i)
            for i, row in enumerate(text.splitlines())
        ]


class TestParserAdapter:
    def test_adapter_satisfies_protocol(self):
        assert isinstance(_CsvAdapter(), ParserAdapter)

    def test_registration_and_duplicate_rejected(self):
        registry = ParserRegistry()
        registry.register_adapter(_CsvAdapter())
        assert len(registry.adapters()) == 1
        with pytest.raises(ValueError):
            registry.register_adapter(_CsvAdapter())

    def test_can_parse_and_deterministic_findings(self):
        registry = ParserRegistry()
        registry.register_adapter(_CsvAdapter())
        artifact = b"id,name\n1,alice\n2,bob"
        assert registry.can_parse(artifact)
        first = registry.parse_artifact(artifact)
        second = registry.parse_artifact(artifact)
        assert [f.value for f in first] == [f.value for f in second]
        assert first[0].kind == "csv_row"

    def test_no_adapter_match_returns_empty(self):
        registry = ParserRegistry()
        assert registry.parse_artifact(b"\x00binary") == []

    def test_nonconforming_adapter_rejected(self):
        registry = ParserRegistry()

        class _Broken:
            pass

        with pytest.raises(TypeError):
            registry.register_adapter(_Broken())  # type: ignore[arg-type]

    def test_dispatch_is_name_stable_regardless_of_registration_order(self):
        class _Zulu:
            name = "zulu"
            content_types = ("z/x",)

            def can_parse(self, artifact) -> bool:
                return artifact == b"zulu-data"

            def parse(self, artifact) -> list[Finding]:
                return [Finding(kind="zulu", value="hit")]

        class _Alpha:
            name = "alpha"
            content_types = ("a/x",)

            def can_parse(self, artifact) -> bool:
                return True  # claims everything

            def parse(self, artifact) -> list[Finding]:
                return [Finding(kind="alpha", value="hit")]

        registry = ParserRegistry()
        registry.register_adapter(_Zulu())
        registry.register_adapter(_Alpha())
        # The claim-everything adapter is first only if it is also first by name.
        assert registry.parse_artifact(b"zulu-data")[0].kind == "alpha"
        # Same artifact, reversed registration → same adapter.
        other = ParserRegistry()
        other.register_adapter(_Alpha())
        other.register_adapter(_Zulu())
        assert other.parse_artifact(b"zulu-data")[0].kind == "alpha"


class TestParserLimits:
    def test_oversized_artifact_raises_without_sink(self):
        registry = ParserRegistry(max_body_bytes=16)
        with pytest.raises(ParserLimitError):
            registry.parse(b"x" * 1024, "text/plain")

    def test_oversized_artifact_quarantined_when_sink_set(self):
        captured = []

        def sink(record):
            captured.append(record)

        registry = ParserRegistry(max_body_bytes=16, on_quarantine=sink)
        with pytest.raises(ParserLimitError):
            registry.parse(b"x" * 1024, "text/plain")
        assert len(captured) == 1
        assert captured[0].reason.startswith("parser.oversized")
        assert captured[0].payload == b"x" * 1024

    def test_binary_unknown_format_quarantined(self):
        captured = []

        def sink(record):
            captured.append(record)

        registry = ParserRegistry(on_quarantine=sink)
        assert registry.parse_artifact(b"\x00\x01binary-garbage") == []
        assert any(r.reason.startswith("parser.unknown_format") for r in captured)

    def test_deep_json_nesting_quarantined_not_parsed(self):
        captured = []
        registry = ParserRegistry(max_depth=8, on_quarantine=functools.partial(captured.append))
        deep = b"[" * 100 + b"0" + b"]" * 100
        with pytest.raises(ParserLimitError):
            registry.parse(deep, "application/json")
        assert captured and captured[0].reason.startswith("parser.depth_limit")

    def test_faulting_adapter_skipped_and_quarantined(self):
        captured = []

        def sink(record):
            captured.append(record)

        class _Exploding:
            name = "exploding"
            content_types = ("x/y",)

            def can_parse(self, artifact) -> bool:
                return True

            def parse(self, artifact) -> list[Finding]:
                raise RuntimeError("adapter blew up")

        class _Follower:
            name = "follower"
            content_types = ("y/z",)

            def can_parse(self, artifact) -> bool:
                return True

            def parse(self, artifact) -> list[Finding]:
                return [Finding(kind="follower", value="ok")]

        registry = ParserRegistry(on_quarantine=sink)
        registry.register_adapter(_Follower())
        registry.register_adapter(_Exploding())
        findings = registry.parse_artifact(b"whatever")
        # Fault containment (C-7): the exploding adapter is skipped, never crashing.
        kinds = [f.kind for f in findings]
        assert kinds in (["exploding", "follower"], ["follower"])
        assert any(r.reason.startswith("parser.adapter_fault") for r in captured)