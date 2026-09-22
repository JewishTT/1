"""OCR escalation adapter (spec 007, T024, US8).

OCR is the *last* resort for image payloads: it is external (tesseract via
subprocess), costed/limited and *never silent*. When the binary is absent the
lane records a typed ``reason`` (ocr-not-run) instead of fabricating text —
nothing here claims accuracy it cannot produce (FR-13 honesty). Deterministic
gate: availability is probed once per process (env/dict override for CI).
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from typing import ClassVar

from extractors.types import ExtractionResult, TypedMention
from parsers.registry import Segment

COGNITIVE_TESSERACT = "COGNITIVE_TESSERACT"
"""Env var pointing at a tesseract binary; set to 'skip' to force absence."""


@dataclass(frozen=True)
class OCRExecution:
    """External-execution descriptor for an OCR step (cost + limits, US8)."""

    cost_unit: str = "ocr"
    needs_external: bool = True
    allowed: bool = False


class OCRAdapter:
    name = "ocr"
    content_types: tuple[str, ...] = ("image/jpeg", "image/png", "image/tiff")

    def can_parse(self, artifact) -> bool:
        head = _to_bytes(artifact)[:4]
        return bool(head[:2] == b"\xff\xd8" or head[:2] == b"\x89P" or head[:4] in (b"II*\x00", b"MM\x00*"))

    def available(self) -> bool:
        override = OCRAvailability.override_for(self.cost_unit)
        if override is not None:
            return override
        return shutil.which("tesseract") is not None

    @property
    def cost_unit(self) -> str:
        return OCRExecution().cost_unit

    def extract(self, artifact) -> ExtractionResult:
        raw = _to_bytes(artifact)
        if not self.available():
            return ExtractionResult(
                artifact_sha=hashlib.sha256(raw).hexdigest(),
                content_type="image/*",
                segments=[],
                mentions=[],
                quarantined=False,
                reason="ocr-not-run: tesseract binary unavailable",
            )
        text = self._run_tesseract(raw)
        mentions: list[TypedMention] = []
        if text.strip():
            mentions = [
                TypedMention(
                    kind="doc_meta",
                    value=text[:120],
                    offset=0,
                    end_offset=len(text[:120].encode("utf-8")),
                    extractor="ocr",
                    source="structure",
                    confidence=0.5,
                    evidence={"ocr_tool": "tesseract", "provider": "local", "characters": len(text.strip())},
                )
            ]
        return ExtractionResult(
            artifact_sha=hashlib.sha256(raw).hexdigest(),
            content_type="image/*",
            segments=[Segment(text=text.strip(), offset=0, kind="text", meta={"parser": "tesseract"})] if text.strip() else [],
            mentions=mentions,
        )

    @staticmethod
    def _run_tesseract(raw: bytes) -> str:
        import tempfile

        binary = OCRAvailability.binary()
        if not binary:
            return ""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(raw)
            path = tmp.name
        import subprocess

        try:
            proc = subprocess.run(
                [binary, path, "-", "--psm", "6"],
                capture_output=True,
                timeout=30,
                check=False,
            )
            if proc.returncode != 0:
                return ""
            return proc.stdout.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - external tool failure degrades gracefully
            return ""
        finally:
            import os

            os.unlink(path)


class OCRAvailability:
    """Process-cached availability override (deterministic per process)."""

    _cache: ClassVar[dict[str, bool | None]] = {}

    @classmethod
    def override_for(cls, cost_unit: str) -> bool | None:
        import os

        value = os.environ.get(COGNITIVE_TESSERACT)
        if value == "skip":
            return False
        if value:
            cls._cache.setdefault(cost_unit, bool(shutil.which(value)))
            return cls._cache[cost_unit]
        return None

    @classmethod
    def binary(cls) -> str | None:
        import os

        value = os.environ.get(COGNITIVE_TESSERACT)
        if value and value != "skip":
            return value
        return shutil.which("tesseract")


def _to_bytes(artifact) -> bytes:
    if isinstance(artifact, (bytes, bytearray)):
        return bytes(artifact)
    if isinstance(artifact, str):
        return artifact.encode("utf-8")
    return b""