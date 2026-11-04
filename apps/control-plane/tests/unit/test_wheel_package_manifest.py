from __future__ import annotations

import tomllib
from pathlib import Path


def test_control_plane_wheel_contains_every_runtime_package_root() -> None:
    project = Path(__file__).resolve().parents[2]
    config = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
    packages = config["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    assert "context_engine" in packages
    assert "semantic_path" in packages
    assert len(packages) == len(set(packages))
    assert all((project / package).is_dir() for package in packages)
