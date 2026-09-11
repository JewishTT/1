"""Evidence vault: SHA-256 integrity + immutable stored copy — adapted from
NetForensicAI (MIT).

Source: donors/NetForensicAI/netforensicai/core/evidence.py.
Changes: ``EvidenceManager`` -> ``EvidenceVault`` / ``Evidence`` ->
``EvidenceItem``; case scope renamed to investigation scope; the optional audit
hook is replaced with structured logging; no external dependencies.

On ingest the source file is copied into the investigation's evidence directory,
hashed, and made read-only. Every later parser/event/finding traces back to this
stored copy - the original at its source location is never opened for writing,
so provenance stays intact (I-1 immutability).

Layout per evidence item:
    investigations/<ID>/evidence/<EV-ID>/
        manifest.json
        original/<original filename>
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import os
import re
import shutil
import stat
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

EVIDENCE_ID_PATTERN = re.compile(r"^EV-(\d{4,})$")
HASH_CHUNK_SIZE = 1024 * 1024

EVIDENCE_KIND_BY_EXTENSION = {
    ".pcap": "pcap",
    ".pcapng": "pcap",
    ".json": "json",
    ".csv": "csv",
    ".evtx": "evtx",
}


class EvidenceError(Exception):
    """Raised for evidence-vault failures: missing source, not found, corrupt manifest."""


@dataclasses.dataclass
class EvidenceItem:
    evidence_id: str
    investigation_id: str
    filename: str
    evidence_type: str
    sha256: str
    size_bytes: int
    imported_at: str
    source_path: str
    stored_path: str
    source_modified_at: str

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> EvidenceItem:
        return cls(**data)


def sha256_of_file(path: Path) -> str:
    """Compute the SHA-256 of a file, streaming so large files never fit in memory."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(HASH_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def infer_evidence_type(filename: str) -> str:
    return EVIDENCE_KIND_BY_EXTENSION.get(Path(filename).suffix.lower(), "unknown")


class EvidenceVault:
    """Manages evidence storage under a single investigation's evidence directory."""

    def __init__(self, investigation_dir: str | Path) -> None:
        self.investigation_dir = Path(investigation_dir)
        self.evidence_dir = self.investigation_dir / "evidence"

    def _evidence_path(self, evidence_id: str) -> Path:
        return self.evidence_dir / evidence_id

    def _next_evidence_id(self) -> str:
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        max_n = 0
        for entry in self.evidence_dir.iterdir():
            if entry.is_dir():
                match = EVIDENCE_ID_PATTERN.match(entry.name)
                if match:
                    max_n = max(max_n, int(match.group(1)))
        return f"EV-{max_n + 1:04d}"

    def add(self, source_path: str | Path, investigation_id: str) -> EvidenceItem:
        """Copy source_path into evidence storage, hash it, and record a manifest.

        The original file is only ever opened for reading (via ``shutil.copy2``);
        the returned item's sha256 is computed from the stored copy, so it
        reflects exactly what was preserved.
        """
        source = Path(source_path)
        if not source.is_file():
            raise EvidenceError(f"Evidence source not found or not a regular file: {source_path}")

        filename = source.name
        if not filename or filename in (".", ".."):
            raise EvidenceError(f"Invalid evidence filename derived from: {source_path}")

        source_stat = source.stat()
        evidence_id = self._next_evidence_id()
        evidence_path = self._evidence_path(evidence_id)
        if evidence_path.exists():
            raise EvidenceError(f"Evidence directory already exists: {evidence_path}")

        original_dir = evidence_path / "original"
        original_dir.mkdir(parents=True)
        dest_file = original_dir / filename

        shutil.copy2(source, dest_file)

        sha256 = sha256_of_file(dest_file)
        os.chmod(dest_file, stat.S_IREAD)

        now = datetime.now(UTC).isoformat()
        item = EvidenceItem(
            evidence_id=evidence_id,
            investigation_id=investigation_id,
            filename=filename,
            evidence_type=infer_evidence_type(filename),
            sha256=sha256,
            size_bytes=source_stat.st_size,
            imported_at=now,
            source_path=str(source.resolve()),
            stored_path=str(dest_file.relative_to(self.investigation_dir)).replace(os.sep, "/"),
            source_modified_at=datetime.fromtimestamp(
                source_stat.st_mtime, tz=UTC
            ).isoformat(),
        )

        manifest_file = evidence_path / "manifest.json"
        manifest_file.write_text(json.dumps(item.to_dict(), indent=2), encoding="utf-8")

        logger.info("Ingested evidence %s (%s, sha256=%s...)", evidence_id, filename, sha256[:12])
        return item

    def load(self, evidence_id: str) -> EvidenceItem:
        manifest_file = self._evidence_path(evidence_id) / "manifest.json"
        if not manifest_file.exists():
            raise EvidenceError(f"Evidence not found: {evidence_id}")
        try:
            data = json.loads(manifest_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise EvidenceError(f"Evidence manifest for {evidence_id} is corrupt: {e}") from e
        return EvidenceItem.from_dict(data)

    def list(self) -> list[EvidenceItem]:
        """Return all valid evidence items, sorted by evidence_id. Skips corrupt entries."""
        if not self.evidence_dir.exists():
            return []
        items = []
        for entry in sorted(self.evidence_dir.iterdir()):
            if entry.is_dir() and (entry / "manifest.json").exists():
                try:
                    items.append(self.load(entry.name))
                except EvidenceError as e:
                    logger.warning("Skipping unreadable evidence directory %s: %s", entry.name, e)
        return items

    def stored_file_path(self, evidence_id: str) -> Path:
        """Absolute path to the stored (read-only) copy of the evidence file."""
        item = self.load(evidence_id)
        return self.investigation_dir / item.stored_path

    def verify(self, evidence_id: str) -> bool:
        """Recompute the stored copy's SHA-256 and compare against the manifest."""
        item = self.load(evidence_id)
        file_path = self.investigation_dir / item.stored_path
        if not file_path.exists():
            raise EvidenceError(f"Stored evidence file missing for {evidence_id}: {file_path}")
        return sha256_of_file(file_path) == item.sha256