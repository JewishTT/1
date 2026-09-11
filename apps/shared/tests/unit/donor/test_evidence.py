import json
import os
import stat
from pathlib import Path

import pytest

from donor.evidence import EvidenceError, EvidenceVault, sha256_of_file


@pytest.fixture
def vault(tmp_path: Path) -> EvidenceVault:
    return EvidenceVault(tmp_path / "investigations" / "INV-1")


def _write_source(tmp_path: Path, name: str = "report.json", content: bytes = b'{"a": 1}') -> Path:
    src = tmp_path / name
    src.write_bytes(content)
    return src


def test_add_creates_manifest_and_immutable_copy(vault: EvidenceVault, tmp_path: Path) -> None:
    src = _write_source(tmp_path)
    item = vault.add(src, investigation_id="INV-1")
    assert item.evidence_id.startswith("EV-")
    assert item.investigation_id == "INV-1"
    stored = vault.stored_file_path(item.evidence_id)
    assert stored.exists()
    assert stored.read_bytes() == b'{"a": 1}'
    mode = stored.stat().st_mode
    assert mode & stat.S_IREAD
    manifest = vault._evidence_path(item.evidence_id) / "manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["sha256"] == sha256_of_file(stored)


def test_verify_true_and_tamper_detection(vault: EvidenceVault, tmp_path: Path) -> None:
    item = vault.add(_write_source(tmp_path), investigation_id="INV-1")
    assert vault.verify(item.evidence_id) is True
    tampered = vault.stored_file_path(item.evidence_id)
    os.chmod(tampered, stat.S_IWRITE | stat.S_IREAD)  # drop immutability guard to simulate attack
    tampered.write_bytes(b'{"a": 2}')
    assert vault.verify(item.evidence_id) is False


def test_evidence_ids_increment(vault: EvidenceVault, tmp_path: Path) -> None:
    first = vault.add(_write_source(tmp_path, "a.json"), investigation_id="INV-1")
    second = vault.add(_write_source(tmp_path, "b.json"), investigation_id="INV-1")
    assert second.evidence_id == f"EV-{int(first.evidence_id[3:]) + 1:04d}"


def test_list_skips_corrupt_manifests(vault: EvidenceVault, tmp_path: Path) -> None:
    vault.add(_write_source(tmp_path, "ok.json"), investigation_id="INV-1")
    bad_dir = vault._evidence_path("EV-9999")
    bad_dir.mkdir(parents=True)
    (bad_dir / "manifest.json").write_text("{not json", encoding="utf-8")
    items = vault.list()
    assert len(items) == 1
    assert items[0].filename == "ok.json"


def test_missing_source_raises(vault: EvidenceVault, tmp_path: Path) -> None:
    with pytest.raises(EvidenceError, match="not found"):
        vault.add(tmp_path / "nope.txt", investigation_id="INV-1")


def test_load_missing_ev_dis_raises(vault: EvidenceVault) -> None:
    with pytest.raises(EvidenceError, match="Evidence not found"):
        vault.verify("EV-0001")


def test_infer_evidence_type(vault: EvidenceVault, tmp_path: Path) -> None:
    src = _write_source(tmp_path, "capture.pcapng")
    item = vault.add(src, investigation_id="INV-1")
    assert item.evidence_type == "pcap"
    assert vault.investigation_dir.parent.name == "investigations"