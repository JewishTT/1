"""Unit tests: evidence manifest chain (feature 005 US3, NetForensicAI pattern)."""

import hashlib
import io
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "interpretation"))

import pytest

from evidence.manifest import (
    Finding,
    ManifestError,
    build_manifest,
    manifest_envelope,
    sha256_of_bytes,
)


class TestSha256OfBytes:
    def test_binary_payload_matches_hashlib(self):
        payload = b"<html>raw observation bytes</html>"
        assert sha256_of_bytes(payload) == hashlib.sha256(payload).hexdigest()

    def test_string_payload_encoded(self):
        assert sha256_of_bytes(b"hello") == hashlib.sha256(b"hello").hexdigest()

    def test_streams_file_like_input(self):
        stream = io.BytesIO(b"x" * (2 * 1024 * 1024))  # larger than chunk budget mock
        assert sha256_of_bytes(stream) == hashlib.sha256(b"x" * (2 * 1024 * 1024)).hexdigest()


class TestFinding:
    def test_deterministic_stable_id(self):
        a = Finding(kind="email", value="a@b.com", offset=3)
        b = Finding(kind="email", value="a@b.com", offset=3)
        assert a.finding_id == b.finding_id
        assert a.finding_id.startswith("F-")

    def test_different_value_different_id(self):
        assert (
            Finding(kind="email", value="x@y.z").finding_id
            != Finding(kind="email", value="u@v.w").finding_id
        )

    def test_immutable(self):
        f = Finding(kind="url", value="https://x/")
        with pytest.raises(FrozenInstanceError):
            f.value = "other"  # type: ignore[misc]


class TestBuildManifest:
    def test_chain_integrity_finding_evidence_observation_raw(self):
        manifest = build_manifest(
            finding=Finding(kind="cve", value="CVE-2021-44228"),
            evidence_id="EVD-abc",
            observation_id="obs-1",
            raw=b"raw-byte-stream",
        )
        finding_id, evidence_id, observation_id, raw_sha256 = manifest.chain()
        assert finding_id.startswith("F-")
        assert evidence_id == "EVD-abc"
        assert observation_id == "obs-1"
        assert raw_sha256 == hashlib.sha256(b"raw-byte-stream").hexdigest()

    def test_explicit_sha256_accepted(self):
        digest = hashlib.sha256(b"other").hexdigest()
        manifest = build_manifest(
            finding=Finding(kind="x", value="y"),
            evidence_id="EVD-1",
            observation_id="obs-1",
            raw_sha256=digest,
        )
        assert manifest.raw_sha256 == digest

    def test_neither_hash_nor_raw_rejected(self):
        with pytest.raises(ManifestError):
            build_manifest(
                finding=Finding(kind="x", value="y"),
                evidence_id="EVD-1",
                observation_id="obs-1",
            )

    def test_both_hash_and_raw_rejected(self):
        with pytest.raises(ManifestError):
            build_manifest(
                finding=Finding(kind="x", value="y"),
                evidence_id="EVD-1",
                observation_id="obs-1",
                raw_sha256="a" * 64,
                raw=b"bytes",
            )

    def test_refs_only_payload_has_no_blob(self):
        manifest = build_manifest(
            finding=Finding(kind="email", value="a@b.com"),
            evidence_id="EVD-1",
            observation_id="obs-1",
            raw_sha256="a" * 64,
        )
        refs = manifest.to_dict()
        assert "chain" in refs and "raw" not in refs and "payload" not in refs
        assert refs["chain"][3] == "a" * 64

    def test_immutable_chain(self):
        manifest = build_manifest(
            finding=Finding(kind="x", value="y"),
            evidence_id="EVD-1",
            observation_id="obs-1",
            raw_sha256="a" * 64,
        )
        with pytest.raises(FrozenInstanceError):
            manifest.observation_id = "mutated"  # type: ignore[misc]


class TestManifestEnvelope:
    def test_produce_emits_evidence_manifest_created(self):
        sent = []

        class _Producer:
            def produce(self, topic, envelope, key=None, **kwargs):
                sent.append((topic, envelope, key))

        manifest = build_manifest(
            finding=Finding(kind="url", value="https://x/"),
            evidence_id="EVD-1",
            observation_id="obs-1",
            raw_sha256="a" * 64,
            producer=_Producer(),
        )
        assert len(sent) == 1
        topic, envelope, key = sent[0]
        assert topic == "evidence"
        assert envelope.event_type == "evidence.manifest_created"
        assert key == manifest.manifest_id
        assert envelope.observation_id == "obs-1"

    def test_envelope_refs_only_chain(self):
        import json

        manifest = build_manifest(
            finding=Finding(kind="url", value="https://x/"),
            evidence_id="EVD-1",
            observation_id="obs-1",
            raw_sha256="a" * 64,
        )
        envelope = manifest_envelope(manifest)
        decoded = json.loads(envelope.payload.decode("utf-8"))
        assert decoded["chain"][0].startswith("F-")
        assert decoded["chain"][2] == "obs-1"
        assert "value" not in decoded  # no finding value/blob leaks into the envelope refs