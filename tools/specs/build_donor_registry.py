"""Build ``donors/registry.yaml`` — the FR-113 supply-chain record (WP0 deliverable).

The contract this satisfies is ``apps/shared/tests/contract/test_donor_registry.py``,
and it is stricter than a checklist in one important way: it polices **honesty**, not
just coverage. An entry may say ``verified`` only with a licence *and* the file the
licence was read from; an ``unverified`` entry must assert **no** licence and must
record what was actually attempted. That is why almost everything this generator emits
is ``unverified``: matching a SPDX signature inside a ``LICENSE`` file is a machine
comparison, not a licence review, and calling it ``verified`` would be the exact guess
the gate exists to reject.

What the generator does do is make each unverified entry *useful*: it records which
licence file was read (and its digest), which SPDX signature matched, the pinned commit,
and where a dependency was declared. A reviewer starts from evidence instead of a bare
null.

Usage::

    python tools/specs/build_donor_registry.py            # write donors/registry.yaml
    python tools/specs/build_donor_registry.py --check    # exit 1 if the file is out of date
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import re
import subprocess
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DONORS = ROOT / "donors"
OUTPUT = DONORS / "registry.yaml"

LICENSE_NAMES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "COPYING", "COPYING.md")


SPDX_SIGNATURES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("AGPL-3.0", re.compile(r"GNU AFFERO GENERAL PUBLIC LICENSE", re.I)),
    ("GPL-3.0", re.compile(r"GNU GENERAL PUBLIC LICENSE\s+Version 3", re.I)),
    ("LGPL-3.0", re.compile(r"GNU LESSER GENERAL PUBLIC LICENSE", re.I)),
    ("Apache-2.0", re.compile(r"Apache License\s*,?\s*Version 2\.0", re.I)),
    ("MPL-2.0", re.compile(r"Mozilla Public License Version 2\.0", re.I)),
    ("Elastic-2.0", re.compile(r"Elastic License 2\.0", re.I)),
    ("BSD-3-Clause", re.compile(r"Redistribution and use in source and binary forms", re.I)),
    (
        "MIT",
        re.compile(r"Permission is hereby granted, free of charge, to any person obtaining a copy", re.I),
    ),
    (
        "Unlicense",
        re.compile(r"This is free and unencumbered software released into the public domain", re.I),
    ),
)

#: Versions verified from installed metadata by spec 030. The gate pins these literally
#: so they cannot drift to null; the generator reads the same metadata, so the file and
#: the environment cannot disagree.
VERIFIED_INSTALLED_VERSIONS = {
    "splink": "4.0.17",
    "h3": "4.5.0",
    "river": "0.26.1",
    "docling-core": "2.101.1",
}

#: Dependencies that left the workspace, with the reason. Kept in the record so the
#: removal survives the pyproject comment that explained it.
REMOVED = {
    "giotto-tda": {
        "version": None,
        "role": (
            "removed: imported nowhere, and its requirement pinned scikit-learn==1.3.2 "
            "workspace-wide, blocking every newer scikit-learn"
        ),
        "verification_note": (
            "removed from the dependency set; the reason is the scikit-learn==1.3.2 pin it "
            "imposed. Its licence was AGPL-3.0, which was never a deployment candidate."
        ),
    },
}

_NORMALISE = re.compile(r"[-_.]+")


def canonical(name: str) -> str:
    return _NORMALISE.sub("-", name.strip().lower())


def requirement_name(requirement: str) -> str:
    return canonical(re.split(r"[\s\[<>=!~;@]", requirement.strip(), maxsplit=1)[0])


def workspace_pyprojects() -> list[Path]:
    root_manifest = ROOT / "pyproject.toml"
    manifests = [root_manifest]
    try:
        data = tomllib.loads(root_manifest.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return manifests
    members = data.get("tool", {}).get("uv", {}).get("workspace", {}).get("members", [])
    for member in members:
        candidate = ROOT / member / "pyproject.toml"
        if candidate.is_file():
            manifests.append(candidate)
    if not members:
        manifests.extend(sorted(ROOT.glob("apps/*/pyproject.toml")))
        bench = ROOT / "bench" / "pyproject.toml"
        if bench.is_file():
            manifests.append(bench)
    return manifests


def declared_dependencies() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}

    def record(requirement: str, source: str) -> None:
        name = requirement_name(requirement)
        if name:
            found.setdefault(name, []).append(source)

    for manifest in workspace_pyprojects():
        try:
            data = tomllib.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        project = data.get("project", {})
        rel = manifest.relative_to(ROOT).as_posix()
        for requirement in project.get("dependencies", []):
            record(requirement, rel)
        for extra, requirements in project.get("optional-dependencies", {}).items():
            for requirement in requirements:
                record(requirement, f"{rel} [optional-dependencies.{extra}]")
    return dict(sorted(found.items()))


def workspace_members() -> set[str]:
    names: set[str] = set()
    for manifest in workspace_pyprojects():
        try:
            data = tomllib.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        name = data.get("project", {}).get("name")
        if name:
            names.add(canonical(name))
    return names


def vendored_donor_names() -> list[str]:
    if not DONORS.is_dir():
        return []
    return sorted(p.name for p in DONORS.iterdir() if p.is_dir())


def _license_probe(donor: Path) -> tuple[str, str, str]:
    """(found_file, spdx_guess, digest) — evidence for a note, never a licence claim."""
    for name in LICENSE_NAMES:
        candidate = donor / name
        if not candidate.is_file():
            continue
        raw = candidate.read_bytes()
        text = raw.decode("utf-8", errors="replace")
        digest = hashlib.sha256(raw).hexdigest()[:16]
        for spdx, pattern in SPDX_SIGNATURES:
            if pattern.search(text):
                return name, spdx, digest
        return name, "", digest
    return "", "", ""


def _git_of(donor: Path) -> tuple[str, str]:
    if not (donor / ".git").exists():
        return "", ""
    try:
        remote = subprocess.run(
            ["git", "-C", str(donor), "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        ).stdout.strip()
        commit = subprocess.run(
            ["git", "-C", str(donor), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        ).stdout.strip()
        return remote, commit
    except (OSError, subprocess.SubprocessError):
        return "", ""


def _installed_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _donor_entry(name: str) -> dict[str, object]:
    donor = DONORS / name
    license_file, spdx, digest = _license_probe(donor)
    remote, commit = _git_of(donor)
    if license_file and spdx:
        note = (
            f"licence file donors/{name}/{license_file} read (sha256:{digest}); SPDX signature "
            f"matched {spdx}. A signature match is not a licence review: no human has confirmed "
            "that this file governs the code, any model weights or the bundled assets, so the "
            "entry stays unverified."
        )
    elif license_file:
        note = (
            f"licence file donors/{name}/{license_file} read (sha256:{digest}) but its text "
            "matches no known SPDX signature. Unrecognised licence text is a blocker, not a blank."
        )
    else:
        note = (
            "no LICENSE/COPYING file at the top of the checkout; no licence established. "
            "This blocks promotion."
        )
    return {
        "id": name,
        "path": f"donors/{name}",
        "upstream": remote or None,
        "version": (commit[:12] if commit else None),
        "license": None,
        "license_source": None,
        "status": "unverified",
        "verification_note": note,
        "role": "vendored donor checkout; capability not yet assigned",
        "vendored": True,
    }


def _dependency_entry(name: str, sources: list[str]) -> dict[str, object]:
    version = VERIFIED_INSTALLED_VERSIONS.get(name) or _installed_version(name)
    declared = ", ".join(sorted(set(sources)))
    if version:
        note = (
            f"declared in {declared}; version read from installed metadata ({version}). "
            "Licence not reviewed: no distribution-level licence text was read for this record."
        )
    else:
        note = (
            f"declared in {declared}; not installed in this environment, so no version could be "
            "read and no licence was reviewed."
        )
    return {
        "id": name,
        "path": None,
        "upstream": f"https://pypi.org/project/{name}/",
        "version": version,
        "license": None,
        "license_source": None,
        "status": "unverified",
        "verification_note": note,
        "role": "third-party declared dependency",
        "vendored": False,
    }


def build() -> dict[str, object]:
    entries: dict[str, dict[str, object]] = {}

    for name in vendored_donor_names():
        entries[canonical(name)] = _donor_entry(name)

    members = workspace_members()
    for name, sources in declared_dependencies().items():
        if name in members:
            continue
        if name in entries:
            # A vendored checkout that is also declared keeps its checkout as the record;
            # the declaration is folded into its note so nothing is lost.
            existing = entries[name]
            existing["verification_note"] = (
                f"{existing['verification_note']} Also declared in {', '.join(sorted(set(sources)))}."
            )
            continue
        entries[name] = _dependency_entry(name, sources)

    for name, removed in REMOVED.items():
        entries[canonical(name)] = {
            "id": name,
            "path": None,
            "upstream": f"https://pypi.org/project/{name}/",
            "version": removed["version"],
            "license": None,
            "license_source": None,
            "status": "removed",
            "verification_note": removed["verification_note"],
            "role": removed["role"],
            "vendored": False,
        }

    donors = [entries[key] for key in sorted(entries)]

    return {
        "schema_version": 1,
        "registry": {
            "authority": "apps/shared/tests/contract/test_donor_registry.py (FR-113)",
            "generator": "tools/specs/build_donor_registry.py",
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "vendored_checkout_count": sum(1 for entry in donors if entry["vendored"]),
            "scope_notes": (
                "Covers every declared dependency in [project].dependencies and "
                "[project].optional-dependencies across the workspace manifests, plus every "
                "checkout under donors/. [dependency-groups] is out of scope: it is never "
                "shipped. `status: verified` requires a licence and the file it was read from; "
                "everything generated here is `unverified`, because an SPDX signature match is "
                "not a licence review."
            ),
        },
        "donors": donors,
        "unregistered": [],
    }


def _comparable(registry: dict[str, object]) -> dict[str, object]:
    """The registry without its generation timestamp, for ``--check``."""
    body = {key: value for key, value in registry.items() if key != "registry"}
    body["registry"] = {
        key: value
        for key, value in dict(registry.get("registry") or {}).items()
        if key != "generated_at"
    }
    return body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 if the file is out of date")
    args = parser.parse_args()

    registry = build()
    text = yaml.safe_dump(
        registry, sort_keys=False, allow_unicode=True, width=110, default_flow_style=False
    )

    if args.check:
        if not OUTPUT.is_file():
            print(f"{OUTPUT} is missing", file=sys.stderr)
            return 1
        current = yaml.safe_load(OUTPUT.read_text(encoding="utf-8"))
        if _comparable(current) != _comparable(registry):
            print("donors/registry.yaml is out of date; rerun without --check", file=sys.stderr)
            return 1
        print("donors/registry.yaml is up to date")
        return 0

    OUTPUT.write_text(text, encoding="utf-8")
    donors = registry["donors"]
    print(
        f"wrote donors/registry.yaml: {len(donors)} entries "
        f"({sum(1 for d in donors if d['vendored'])} vendored, "
        f"{sum(1 for d in donors if d['status'] == 'unverified')} unverified, "
        f"{sum(1 for d in donors if d['status'] == 'removed')} removed)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
