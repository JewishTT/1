"""Dynamic platform model: the drift gate and the import-surface ratchets.

``docs/platform/`` is not written by hand. It is generated from the source tree by
``platform_model/build.py``, and this module is the gate that keeps the two in step.
A commit that changes the platform without regenerating the model fails here.

The gate has four halves, and they fail for different reasons:

* **Drift.** The committed artifacts differ from what the tree currently produces. This is
  the ordinary case: someone edited code and forgot the documentation.
* **Broken platform imports.** An import names a platform package that does not exist, or
  names one under a path the platform no longer has. None exist today: the last one was the
  bench harness importing ``evidence.independence``, while the class lives in
  ``apps/admission/independence/independence.py``. The ratchet below is empty, so the first
  new one is a failure.
* **Undeclared dependencies.** An import names a third-party package that is neither
  installed nor declared in any workspace manifest. It works on the machine that grew the
  code and fails on every other machine. None exist today: the three that did
  (``tantivy``, ``pyshacl``, ``pyzbar``) are capability probes -- imports guarded by
  ``try/except ImportError`` -- and the platform is written to work without them, so they
  are counted as optional rather than as undeclared.
* **Tracked gaps.** An import names a platform feature that is documented as not landed
  yet. One exists (T065, ``domain.context_validation``); it is recorded so that a second
  one, or the disappearance of the first, is visible.

The ratchets are exact-match lists rather than thresholds. A threshold on "how many broken
imports are acceptable" is a number that only ever goes up.

The generator is exercised as a library here rather than through a subprocess so that a
failure names the artifact that drifted instead of an exit code.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract


def repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "donors").is_dir() and (candidate / "pyproject.toml").is_file():
            return candidate
    raise RuntimeError("could not locate the repository root above this file")


ROOT = repo_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from platform_model import build as pm  # noqa: E402

#: Pages the generator is expected to produce. A missing page is a broken build, not a
#: smaller build.
EXPECTED_PAGES = (
    "api.md",
    "architecture.json",
    "architecture-evidence.json",
    "architecture-evidence.jsonl",
    "capabilities.md",
    "components.md",
    "contracts.md",
    "data-flow.md",
    "donors.md",
    "findings.md",
    "imports.md",
    "index.md",
    "modules.jsonl",
    "ownership.md",
    "platform-model.json",
    "tests.md",
)

#: Platform imports that name a package which does not exist, or name one under a path the
#: platform no longer has. Empty: the last one was fixed, and the first new one is a
#: failure.
KNOWN_BROKEN_PLATFORM_IMPORTS = frozenset()

#: Platform features the tree documents as not landed yet. The import is guarded and the
#: tests that need it are skipped.
KNOWN_GUARDED_GAPS = frozenset(
    {
        ("apps/shared/tests/unit/test_relation_schema.py", "domain.context_validation"),
    }
)

#: Third-party imports that are neither installed nor declared in any manifest, and are not
#: guarded capability probes either. Empty.
KNOWN_UNDECLARED_DEPENDENCIES = frozenset()

#: Third-party packages the platform probes for and degrades gracefully without. They are
#: imported inside ``try/except ImportError``, so the platform works without them; they
#: are listed here because "the platform can run without it" is a decision someone made,
#: not an accident.
KNOWN_OPTIONAL_PROBES = frozenset({"pyshacl", "pyzbar", "rdflib"})

#: Generated narrative documents that live outside ``docs/platform/``. They are rendered
#: from the model by ``platform_model/narrative.py`` and are part of the drift gate, so a
#: factual change to the tree that is not reflected here fails.
EXPECTED_NARRATIVE_DOCS = (
    "README.md",
    "docs/README.md",
    "docs/CONTRIBUTING.md",
    "docs/architecture/overview.md",
    "docs/architecture/stream-processing.md",
    "docs/architecture/fabric-collection.md",
    "docs/architecture/multi-region.md",
    "docs/architecture/dynamic-entity-invariant.md",
    "docs/architecture/donors/00-INDEX.md",
)

#: Extensions that count as "source" when deciding whether an app dir is a component.
SOURCE_SUFFIXES = (".py", ".ts", ".tsx")


@pytest.fixture(scope="module")
def model() -> dict:
    return pm.build_model(ROOT)


# ---------------------------------------------------------------------------
# drift
# ---------------------------------------------------------------------------


def test_committed_model_matches_the_tree(model: dict) -> None:
    """The committed artifacts are what the current tree produces."""
    drift = pm.check(model)
    assert not drift, (
        "the committed platform model is stale; regenerate it with "
        "`python -m platform_model.build`:\n  " + "\n  ".join(drift)
    )


def test_every_expected_page_is_generated(model: dict) -> None:
    produced = set(pm.artifacts(model))
    missing = sorted(set(EXPECTED_PAGES) - produced)
    assert not missing, f"the generator no longer produces: {missing}"


def test_generated_pages_are_not_empty(model: dict) -> None:
    for name, content in pm.artifacts(model).items():
        assert content.strip(), f"{name} is empty"


def test_narrative_docs_are_generated(model: dict) -> None:
    """The README and the docs index are generated, non-empty, and drift-gated."""
    produced = pm.narrative_artifacts(model)
    missing = sorted(set(EXPECTED_NARRATIVE_DOCS) - set(produced))
    assert not missing, f"the generator no longer produces: {missing}"
    for name, content in produced.items():
        assert content.strip(), f"{name} is empty"


# ---------------------------------------------------------------------------
# scope
# ---------------------------------------------------------------------------


def test_donor_code_is_not_scanned(model: dict) -> None:
    """``donors/`` is excluded from the model: it is vendored third-party code."""
    offenders: list[str] = []
    for lang in ("python", "typescript", "rust"):
        for mod in model[lang]["modules"]:
            if mod["path"].startswith("donors/"):
                offenders.append(mod["path"])
    assert not offenders, f"donor code leaked into the model: {offenders[:5]}"


def test_excluded_directories_are_declared(model: dict) -> None:
    assert "donors" in model["excluded"]
    assert "node_modules" in model["excluded"]


def test_the_model_covers_the_platform(model: dict) -> None:
    """Every app that ships source is a component of the model."""
    app_dirs = {
        p.name
        for p in (ROOT / "apps").iterdir()
        if p.is_dir()
        and any(
            f.suffix in SOURCE_SUFFIXES
            for f in p.rglob("*")
            if f.is_file() and "__pycache__" not in f.parts and "node_modules" not in f.parts
        )
    }
    # ``apps/deploy`` is configuration only (compose, dashboards, k8s), so it
    # carries no module and is correctly absent from the component list.
    app_dirs.discard("deploy")
    components = {c["name"] for c in model["components"]}
    missing = sorted(app_dirs - components)
    assert not missing, f"apps with no component in the model: {missing}"


# ---------------------------------------------------------------------------
# import-surface ratchets
# ---------------------------------------------------------------------------


def test_no_broken_platform_imports(model: dict) -> None:
    broken = {
        (u["from"], u["import"])
        for u in model["import_graph"]["unresolved"]
        if u.get("kind") in ("local", "stale-platform-path", "guarded-local")
    }
    assert broken == set(KNOWN_BROKEN_PLATFORM_IMPORTS), (
        "the set of broken platform imports changed.\n"
        f"  new: {sorted(broken - set(KNOWN_BROKEN_PLATFORM_IMPORTS))}\n"
        f"  gone: {sorted(set(KNOWN_BROKEN_PLATFORM_IMPORTS) - broken)}"
    )


def test_no_undeclared_dependencies(model: dict) -> None:
    undeclared = {
        u["from"] for u in model["import_graph"]["unresolved"] if u.get("kind") == "unknown"
    }
    assert undeclared == set(KNOWN_UNDECLARED_DEPENDENCIES), (
        "the set of undeclared dependencies changed.\n"
        f"  new: {sorted(undeclared - set(KNOWN_UNDECLARED_DEPENDENCIES))}\n"
        f"  gone: {sorted(set(KNOWN_UNDECLARED_DEPENDENCIES) - undeclared)}"
    )


def test_guarded_gaps_are_known(model: dict) -> None:
    """A feature that is not landed yet is a decision, and the decision is recorded."""
    gaps = {
        (u["from"], u["import"])
        for u in model["import_graph"]["unresolved"]
        if u.get("kind") == "guarded-gap"
    }
    assert gaps == set(KNOWN_GUARDED_GAPS), (
        "the set of tracked gaps changed.\n"
        f"  new: {sorted(gaps - set(KNOWN_GUARDED_GAPS))}\n"
        f"  gone: {sorted(set(KNOWN_GUARDED_GAPS) - gaps)}"
    )


def test_optional_probes_are_known(model: dict) -> None:
    """Every capability probe is a recorded decision to degrade, not to fail."""
    probes = set(model["import_graph"]["optional"])
    assert probes == set(KNOWN_OPTIONAL_PROBES), (
        "the set of optional capability probes changed.\n"
        f"  new: {sorted(probes - set(KNOWN_OPTIONAL_PROBES))}\n"
        f"  gone: {sorted(set(KNOWN_OPTIONAL_PROBES) - probes)}"
    )


def test_every_import_resolves_to_something(model: dict) -> None:
    """No import in the platform names something that exists nowhere."""
    unresolved = [u for u in model["import_graph"]["unresolved"] if u.get("kind") == "unknown"]
    assert not unresolved, f"imports that resolve to nothing: {unresolved[:5]}"


def test_every_local_import_resolves(model: dict) -> None:
    """An import that resolves to a platform module must point at a file that exists."""
    known = {m["path"] for m in model["python"]["modules"]}
    dangling = [e for e in model["import_graph"]["edges"] if e["to"] not in known]
    assert not dangling, f"import edges point at files that do not exist: {dangling[:5]}"


# ---------------------------------------------------------------------------
# spec artifacts
# ---------------------------------------------------------------------------


def test_capabilities_all_have_a_module(model: dict) -> None:
    missing = [c["id"] for c in model["capabilities"] if not c.get("exists", True)]
    assert not missing, f"capabilities declared but not implemented: {missing}"


def test_no_capability_is_test_only_by_accident(model: dict) -> None:
    """``TEST_ONLY`` must mean 'tests reach it and production does not'."""
    for cap in model["capabilities"]:
        if cap["status"] == "TEST_ONLY":
            assert not cap.get("production_importers"), (
                f"{cap['id']} is TEST_ONLY but is imported by production code"
            )


def test_ownership_covers_every_object(model: dict) -> None:
    """The owner map is a map, not a list: statuses agree with the writer lists."""
    objects = model["ownership"]
    assert objects, "the owner map is empty"
    for obj in objects:
        writers = obj.get("writers") or []
        status = obj.get("status")
        if status == "COMPETING_WRITERS":
            assert len(writers) >= 2, f"{obj['object']} is marked competing but has {len(writers)} writer(s)"
        elif status == "SINGLE_WRITER":
            assert len(writers) == 1, f"{obj['object']} is marked single but has {len(writers)} writer(s)"
        assert obj.get("table") or obj.get("note") or status == "NO_DIRECT_WRITER_FOUND", (
            f"{obj['object']} names neither a table nor a reason"
        )
