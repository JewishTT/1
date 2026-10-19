"""Donor registry supply-chain gate (spec 030, FR-113, tasks T039/T040).

The registry at ``donors/registry.yaml`` is a legal record, not a manifest of good intentions.
Two failure modes matter and they pull in opposite directions:

* **A dependency arrives with no record.** Nobody ever established what licence it is. This is
  the failure the gate exists to stop: it makes the build red.
* **A licence is written down on a guess.** The record looks complete and is worse than empty,
  because an AGPL-versus-MIT error is a legal conclusion somebody will later rely on. This
  gate also polices: a ``verified`` entry must cite the file it was read from, and an
  ``unverified`` entry must say *nothing* about the licence and must explain what was tried.

The gate therefore has two halves. The first half fails when a record is missing. The second
fails when a record is dishonest, including dishonestly empty.

Several tests here are about the tests. ``test_the_checker_rejects_*`` feed the checker a
deliberately broken input and assert it notices, because a coverage gate that cannot fail is
indistinguishable from a coverage gate that always passes -- and on a supply-chain control
that distinction is the whole risk.
"""

from __future__ import annotations

import re
import sys
import tomllib
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = pytest.mark.contract

#: Fields every ``donors:`` entry must carry. Null is a legitimate value; absence is not.
REQUIRED_ENTRY_FIELDS = (
    "id",
    "path",
    "upstream",
    "version",
    "license",
    "license_source",
    "status",
    "verification_note",
    "role",
    "vendored",
)

VALID_STATUSES = frozenset({"verified", "unverified", "removed"})


# ---------------------------------------------------------------------------
# Locating the repository
# ---------------------------------------------------------------------------


def repo_root() -> Path:
    """The directory holding ``donors/``, found by walking up from this file.

    Walking beats a fixed ``parents[n]``: the test package has already been nested once per
    rename since this was written, and a gate that cannot find the repository is a gate that
    silently stops gating.
    """
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "donors").is_dir() and (candidate / "pyproject.toml").is_file():
            return candidate
    raise RuntimeError("could not locate the repository root above this file")


ROOT = repo_root()
REGISTRY_PATH = ROOT / "donors" / "registry.yaml"


# ---------------------------------------------------------------------------
# Name normalisation
# ---------------------------------------------------------------------------

#: PEP 503: runs of ``-``, ``_`` and ``.`` collapse to a single ``-``, and case is irrelevant.
#: Without this, ``python-docx``, ``python_docx`` and ``Python.DOCX`` are three dependencies.
_NORMALISE = re.compile(r"[-_.]+")


def canonical(name: str) -> str:
    """Reduce a distribution name or a requirement string to its canonical key."""
    cleaned = _NORMALISE.sub("-", name.strip().lower())
    return cleaned


def requirement_name(requirement: str) -> str:
    """Pull the distribution name out of a PEP 508 requirement string.

    ``splink>=4.0.10,<5`` -> ``splink``; ``sqlalchemy[asyncio]>=2.0`` -> ``sqlalchemy``;
    ``uvicorn[standard]>=0.30`` -> ``uvicorn``. A direct reference (no version, no extras) is
    the workspace's own name and comes back unchanged.
    """
    return canonical(re.split(r"[\s\[<>=!~;@]", requirement.strip(), maxsplit=1)[0])


# ---------------------------------------------------------------------------
# Reading the workspace
# ---------------------------------------------------------------------------


def workspace_pyprojects(root: Path = ROOT) -> list[Path]:
    """Every ``pyproject.toml`` a dependency can be declared in.

    The root manifest is included unconditionally -- it can declare dependencies even with an
    empty ``members`` list -- and the member list is read from ``[tool.uv.workspace]``. If that
    key is absent the search widens to every ``apps/*`` and ``bench`` manifest rather than
    reporting an empty workspace, because an empty workspace would make the gate vacuous.
    """
    root_manifest = root / "pyproject.toml"
    if not root_manifest.is_file():
        return []

    try:
        root_data = tomllib.loads(root_manifest.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        return [root_manifest]

    members = root_data.get("tool", {}).get("uv", {}).get("workspace", {}).get("members", [])
    paths = [root_manifest]
    for member in members:
        candidate = root / member / "pyproject.toml"
        if candidate.is_file():
            paths.append(candidate)

    if not members:
        paths.extend(sorted(root.glob("apps/*/pyproject.toml")))
        bench = root / "bench" / "pyproject.toml"
        if bench.is_file():
            paths.append(bench)
    return paths


def declared_dependencies(root: Path = ROOT) -> dict[str, list[str]]:
    """Map every declared dependency name to the manifests that declare it.

    ``[project].dependencies`` and ``[project.optional-dependencies]`` are both in scope. The
    ``lang-tiers`` extra is real shipped capability that a consumer can turn on with one flag,
    so it belongs in a supply-chain record. ``[dependency-groups]`` is not: it is never shipped
    and never installed into the runtime the platform publishes. That exclusion is recorded in
    the registry's ``registry.scope_notes`` rather than left implicit here.
    """
    found: dict[str, list[str]] = {}

    def record(requirement: str, source: str) -> None:
        name = requirement_name(requirement)
        if name:
            found.setdefault(name, []).append(source)

    for manifest in workspace_pyprojects(root):
        try:
            data = tomllib.loads(manifest.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:  # pragma: no cover - a broken manifest is loud
            raise AssertionError(f"{manifest} is not valid TOML: {exc}") from exc

        project = data.get("project", {})
        rel = manifest.relative_to(root).as_posix()
        for requirement in project.get("dependencies", []):
            record(requirement, rel)
        for extra, requirements in project.get("optional-dependencies", {}).items():
            for requirement in requirements:
                record(requirement, f"{rel} [optional-dependencies.{extra}]")

    return dict(sorted(found.items()))


def workspace_members(root: Path = ROOT) -> set[str]:
    """Names of the workspace's own packages, which are not third-party supply chain."""
    names: set[str] = set()
    for manifest in workspace_pyprojects(root):
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
        name = data.get("project", {}).get("name")
        if name:
            names.add(canonical(name))
    return names


def vendored_donor_names(root: Path = ROOT) -> list[str]:
    """Every directory under ``donors/``, which is the set the gate must cover."""
    return sorted(p.name for p in (root / "donors").iterdir() if p.is_dir())


# ---------------------------------------------------------------------------
# Reading the registry
# ---------------------------------------------------------------------------


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    if not path.is_file():
        raise AssertionError(
            f"{path} does not exist. The donor registry is mandatory (FR-113); every declared "
            "dependency and every vendored checkout needs a licence/version record in it."
        )
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise AssertionError(f"{path} did not parse into a mapping")
    return data


def registry_index(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Canonical-id -> entry. Extras and punctuation are normalised the same way as deps."""
    index: dict[str, dict[str, Any]] = {}
    for entry in registry.get("donors", []):
        key = canonical(str(entry.get("id", "")))
        if key:
            index.setdefault(key, entry)
    return index


# ---------------------------------------------------------------------------
# The checks themselves
# ---------------------------------------------------------------------------


def missing_dependencies(
    registry: dict[str, Any], dependencies: dict[str, list[str]]
) -> dict[str, list[str]]:
    """Declared dependencies with no registry entry, mapped to the manifests that declare them.

    This is the FR-113 gate. A non-empty result means the build is red.
    """
    index = registry_index(registry)
    internal = workspace_members()
    return {
        name: sources
        for name, sources in dependencies.items()
        if name not in index and name not in internal
    }


def missing_donors(registry: dict[str, Any], donor_names: Iterable[str]) -> list[str]:
    """Vendored checkouts under ``donors/`` with no registry entry."""
    index = registry_index(registry)
    return sorted(name for name in donor_names if canonical(name) not in index)


def _describe(missing: dict[str, list[str]]) -> str:
    lines = [
        "The donor registry is missing entries for declared dependencies.",
        "",
        "Each of these is declared by a workspace pyproject.toml but has no record in "
        "donors/registry.yaml. Record the licence and version you can actually verify, and "
        "use `status: unverified` with `license: null` and a verification_note saying what "
        "you tried where you cannot. A missing entry fails the build; a guessed licence is "
        "worse than either.",
        "",
    ]
    for name, sources in sorted(missing.items()):
        lines.append(f"  {name}  (declared in: {', '.join(sorted(set(sources)))})")
    lines.append("")
    lines.append(f"Add {len(missing)} entry/entries to the `donors:` list in donors/registry.yaml.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The registry itself
# ---------------------------------------------------------------------------


class TestTheRegistryParses:
    def test_registry_is_machine_readable_and_versioned(self):
        registry = load_registry()
        assert isinstance(registry.get("schema_version"), int), (
            "registry.yaml must carry an integer schema_version so a future format change is "
            "detectable rather than silently misread"
        )

    def test_registry_exposes_the_documented_top_level_sections(self):
        registry = load_registry()
        assert isinstance(registry.get("donors"), list), "`donors:` must be a list of entries"
        assert isinstance(registry.get("unregistered"), list), (
            "`unregistered:` must be a list; an honest gap has to be enumerable"
        )

    def test_registry_ids_are_unique(self):
        seen: dict[str, int] = {}
        for entry in load_registry()["donors"]:
            key = canonical(str(entry.get("id", "")))
            seen[key] = seen.get(key, 0) + 1
        duplicates = sorted(k for k, n in seen.items() if n > 1)
        assert not duplicates, (
            f"duplicate registry ids (a later duplicate silently wins): {duplicates}"
        )

    def test_every_entry_carries_the_required_fields(self):
        missing = [
            f"{entry.get('id')!r}: {field}"
            for entry in load_registry()["donors"]
            for field in REQUIRED_ENTRY_FIELDS
            if field not in entry
        ]
        assert not missing, (
            "registry entries must carry every field in REQUIRED_ENTRY_FIELDS. "
            "A missing field is not the same as a null value -- null records a checked "
            f"absence, a missing field records that nobody looked.\n{chr(10).join(missing)}"
        )

    def test_every_entry_has_a_recognised_status(self):
        bad = [
            f"{entry.get('id')}={entry.get('status')!r}"
            for entry in load_registry()["donors"]
            if entry.get("status") not in VALID_STATUSES
        ]
        assert not bad, f"unknown status values: {bad}"

    def test_every_entry_states_its_role(self):
        blank = [entry.get("id") for entry in load_registry()["donors"] if not entry.get("role")]
        assert not blank, f"entries with no recorded role: {blank}"

    def test_the_vendored_flag_agrees_with_the_filesystem(self):
        """`vendored: true` means a real checkout; `vendored: false` means no repo path.

        The on-disk half is only asserted when the checkouts are present, because the donor
        clones are untracked and a bare CI checkout has none of them.
        """
        checkouts_present = bool(vendored_donor_names())
        mismatched = []
        for entry in load_registry()["donors"]:
            path = entry.get("path")
            if entry.get("vendored"):
                if not path or not str(path).startswith("donors/"):
                    mismatched.append(f"{entry.get('id')}: vendored without a donors/ path")
                elif checkouts_present and not (ROOT / path).is_dir():
                    mismatched.append(
                        f"{entry.get('id')}: vendored but {path!r} is not a directory"
                    )
            elif path is not None:
                mismatched.append(f"{entry.get('id')}: not vendored yet carries path {path!r}")
        assert not mismatched, "\n".join(mismatched)


# ---------------------------------------------------------------------------
# The honesty invariant
# ---------------------------------------------------------------------------


class TestTheRegistryIsHonest:
    """`verified` means verified, and `unverified` means nothing was asserted.

    These are the tests that stop the registry from rotting into decoration. A gate that only
    checked for presence would happily accept an entry whose licence was recalled rather than
    read.
    """

    def test_verified_entries_cite_where_the_licence_was_read_from(self):
        bad = [
            f"{entry.get('id')}"
            for entry in load_registry()["donors"]
            if entry.get("status") == "verified"
            and not (entry.get("license") and entry.get("license_source"))
        ]
        assert not bad, (
            "every `status: verified` entry must carry both a licence and the file it was "
            f"read from. These claim verification without evidence: {sorted(bad)}"
        )

    def test_unverified_entries_assert_no_licence(self):
        bad = [
            f"{entry.get('id')}={entry.get('license')!r}"
            for entry in load_registry()["donors"]
            if entry.get("status") == "unverified" and entry.get("license") is not None
        ]
        assert not bad, (
            "`status: unverified` with a licence set is a guess presented as a finding. The "
            "licence field must be null: "
            f"{sorted(bad)}. If the licence really is known, read it and set the status to "
            "`verified` with a license_source."
        )

    def test_unverified_entries_explain_what_was_attempted(self):
        bad = [
            f"{entry.get('id')}"
            for entry in load_registry()["donors"]
            if entry.get("status") == "unverified"
            and not str(entry.get("verification_note") or "").strip()
        ]
        assert not bad, (
            "an unverified entry must record what was actually tried -- which file was read, "
            "which tool was run. A bare null is indistinguishable from not having looked: "
            f"{sorted(bad)}"
        )

    def test_verified_entries_that_cite_a_vendored_file_are_pointing_at_a_real_file(self):
        """A `license_source` naming a file that is not there is an unbacked citation.

        Skipped where the checkouts are absent, because the donor clones are not tracked by
        this repository and a bare CI checkout has no ``donors/<name>/LICENSE`` to check
        against. Not skipped silently on a full tree, which is where it does its work.
        """
        if not vendored_donor_names():
            pytest.skip(
                "no vendored checkouts on disk (they are untracked clones; a bare CI checkout "
                "has an empty donors/ tree). This citation check runs on a full tree."
            )
        bad = []
        for entry in load_registry()["donors"]:
            source = entry.get("license_source")
            if not source:
                continue
            candidate = source.split(" ")[0].split("(")[0].strip()
            if not candidate.startswith("donors/"):
                continue
            if not (ROOT / candidate).exists():
                bad.append(f"{entry.get('id')} cites {candidate}, which does not exist")
        assert not bad, "\n".join(bad)

    def test_removed_dependencies_record_why_they_went_away(self):
        bad = [
            f"{entry.get('id')}"
            for entry in load_registry()["donors"]
            if entry.get("status") == "removed" and not str(entry.get("role") or "").strip()
        ]
        assert not bad, f"removed entries must record the removal reason: {sorted(bad)}"


# ---------------------------------------------------------------------------
# FR-113: the gate itself
# ---------------------------------------------------------------------------


class TestEveryDeclaredDependencyIsRecorded:
    def test_every_declared_dependency_has_a_registry_entry(self):
        registry = load_registry()
        missing = missing_dependencies(registry, declared_dependencies())
        assert not missing, _describe(missing)

    def test_the_workspace_actually_declares_something(self):
        """Guards the gate above against passing because it parsed nothing."""
        dependencies = declared_dependencies()
        assert len(dependencies) > 30, (
            f"only {len(dependencies)} dependencies parsed from the workspace manifests; the "
            "gate would be vacuous if it had silently stopped seeing them"
        )

    def test_the_registry_covers_every_vendored_donor(self):
        registry = load_registry()
        missing = missing_donors(registry, vendored_donor_names())
        assert not missing, (
            "vendored checkouts under donors/ with no entry in donors/registry.yaml:\n  "
            + "\n  ".join(missing)
        )

    def test_the_registry_vendored_paths_match_the_donor_directory_listing(self):
        """Every checkout on disk is registered, and every registered checkout is on disk.

        The donor clones are separate git repositories that this repository does not track,
        so a bare CI checkout sees an empty ``donors/``. When there is nothing on disk the
        check falls back to the inventory the registry records for itself, which is what makes
        the assertion non-vacuous there: emptying the vendor list still fails.
        """
        recorded = {
            entry["path"]
            for entry in load_registry()["donors"]
            if entry.get("vendored") and entry.get("path")
        }
        on_disk = {f"donors/{name}" for name in vendored_donor_names()}

        if on_disk:
            assert on_disk - recorded == set(), (
                "checkouts present under donors/ with no registry entry:\n  "
                + "\n  ".join(sorted(on_disk - recorded))
            )
            assert recorded - on_disk == set(), (
                "registry records vendored paths that are not on disk:\n  "
                + "\n  ".join(sorted(recorded - on_disk))
            )
        else:
            declared = load_registry()["registry"]["vendored_checkout_count"]
            assert recorded, (
                "donors/ is empty on this machine AND the registry records no vendored "
                "checkouts. One of the two is wrong; the registry is the recorded inventory."
            )
            assert len(recorded) == declared, (
                f"the registry records {len(recorded)} vendored checkouts but "
                f"vendored_checkout_count says {declared}"
            )

    def test_registry_vendored_paths_are_well_formed(self):
        bad = [
            f"{entry.get('id')}: {entry.get('path')!r}"
            for entry in load_registry()["donors"]
            if entry.get("vendored")
            and not str(entry.get("path") or "").startswith("donors/")
        ]
        assert not bad, f"vendored entries must record a donors/ path: {bad}"

    def test_giotto_tda_is_recorded_as_removed(self):
        """It was declared, imported nowhere, and pinned scikit-learn==1.3.2 workspace-wide.

        Recorded so the removal and its reason survive the pyproject comment that explains it.
        """
        entries = {canonical(str(e.get("id"))): e for e in load_registry()["donors"]}
        entry = entries.get("giotto-tda")
        assert entry is not None, "giotto-tda must remain in the registry as a removed dependency"
        assert entry.get("status") == "removed"
        assert entry.get("license") is None
        note = str(entry.get("verification_note") or "") + str(entry.get("role") or "")
        assert "scikit-learn" in note, "the removal reason must name the pin that caused it"

    def test_the_donor_work_installed_packages_carry_their_real_versions(self):
        """The spec-030 additions are verifiable exactly; they must not drift to nulls."""
        entries = {canonical(str(e.get("id"))): e for e in load_registry()["donors"]}
        expected = {
            "splink": "4.0.17",
            "h3": "4.5.0",
            "river": "0.26.1",
            "docling-core": "2.101.1",
        }
        bad = {
            name: entries.get(name, {}).get("version")
            for name, version in expected.items()
            if entries.get(name, {}).get("version") != version
        }
        assert not bad, (
            "these versions were verified from installed metadata and must match: "
            f"{bad}"
        )


# ---------------------------------------------------------------------------
# Non-vacuity: prove the gate can actually fail
# ---------------------------------------------------------------------------


class TestTheGateIsNotVacuous:
    """A gate that cannot fail is decoration. These break the input on purpose."""

    def test_the_checker_rejects_a_synthetic_missing_dependency(self):
        synthetic = "totally-not-a-real-dependency-xyzzy==9.9.9"
        assert synthetic not in declared_dependencies(), "sentinel collision; pick another name"

        missing = missing_dependencies(load_registry(), {synthetic: ["synthetic/pyproject.toml"]})
        assert synthetic in missing, "the gate failed to notice a dependency with no entry"
        assert "synthetic/pyproject.toml" in missing[synthetic], (
            "the report must name the manifest that declares the unregistered dependency"
        )
        report = _describe(missing)
        assert report.splitlines()[0].startswith("The donor registry is missing")
        assert synthetic in report

    def test_the_checker_rejects_a_synthetic_missing_donor(self):
        registry = load_registry()
        assert "synthetic-absent-donor" not in vendored_donor_names(), "sentinel collision"

        missing = missing_donors(registry, [*vendored_donor_names(), "synthetic-absent-donor"])
        assert missing == ["synthetic-absent-donor"], (
            f"the gate failed to notice an unregistered donor; got {missing}"
        )

    def test_the_checker_still_passes_on_the_real_inputs(self):
        """If this failed, the three tests above would pass for the wrong reason."""
        registry = load_registry()
        assert missing_dependencies(registry, declared_dependencies()) == {}
        assert missing_donors(registry, vendored_donor_names()) == []

    def test_deleting_a_real_entry_from_the_registry_is_detected(self):
        """Proves the gate reads the file it is pointed at, rather than a cached index."""
        registry = load_registry()
        victim = "numpy"
        index = registry_index(registry)
        assert victim in index, f"{victim} must be registered for this test to mean anything"

        mutated = dict(registry)
        mutated["donors"] = [
            entry for entry in registry["donors"] if canonical(str(entry.get("id"))) != victim
        ]

        missing = missing_dependencies(mutated, declared_dependencies())
        assert victim in missing, (
            "removing a registered dependency from the registry went unnoticed"
        )
        assert missing_donors(mutated, vendored_donor_names()) == [], (
            "numpy is an installed distribution, not a vendored checkout, so the donor-side "
            "check should be unaffected"
        )

    def test_the_honesty_invariant_catches_an_invented_licence(self):
        """The other half of the gate: a guessed licence has to be rejectable too."""
        registry = load_registry()
        mutated = dict(registry)
        mutated["donors"] = [
            dict(entry)
            if canonical(str(entry.get("id"))) != "mottahunter"
            else {**entry, "license": "MIT", "status": "unverified"}
            for entry in registry["donors"]
        ]

        offenders = [
            entry.get("id")
            for entry in mutated["donors"]
            if entry.get("status") == "unverified" and entry.get("license") is not None
        ]
        assert offenders == ["MottaHunter"], (
            "an entry that admits it is unverified while still asserting a licence must be "
            f"flagged; got {offenders}"
        )


# ---------------------------------------------------------------------------
# Script entry point, so CI can run this as a check rather than only as tests
# ---------------------------------------------------------------------------


def main() -> int:
    """Run the FR-113 gate. Returns a POSIX exit status."""
    registry = load_registry()
    missing = missing_dependencies(registry, declared_dependencies())
    if missing:
        print(_describe(missing), file=sys.stderr)
        return 1

    absent = missing_donors(registry, vendored_donor_names())
    if absent:
        print("Vendored donors with no registry entry:", file=sys.stderr)
        for name in absent:
            print(f"  {name}", file=sys.stderr)
        return 1

    total = len(registry.get("donors", []))
    print(f"donor registry OK: {total} entries, no unregistered dependency or donor")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
