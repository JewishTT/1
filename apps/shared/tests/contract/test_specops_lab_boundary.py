from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.contract


def repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "donors").is_dir() and (candidate / "pyproject.toml").is_file():
            return candidate
    raise RuntimeError("could not locate repository root")


def test_specops_lab_host_ports_are_loopback_bound_and_network_is_internal() -> None:
    root = repo_root()
    compose = (root / "deploy/specops/lab/docker-compose.yml").read_text(encoding="utf-8")
    assert '"127.0.0.1:8888:8888"' in compose, "Caldera API must not publish on all host interfaces"
    assert '"127.0.0.1:8080:8080"' in compose, "PhishSlayer API must not publish on all host interfaces"
    assert "internal: true" in compose, "the SpecOps lab network must remain isolated"
    assert "caldera/core:latest" in compose and "phishslayer/lab:latest" in compose, (
        "image tags must remain visible to the audit until they are replaced by immutable digests"
    )
