"""T038: every constitutional test names its own failure, and can actually fail.

A test that cannot fail is not a test. For a *constitutional* test it is worse than
useless: it gets cited as evidence of a guarantee the platform is not keeping, and nobody
checks, because a test that has never failed has never been examined.

So this file does the unglamorous work of proving the other files work, by **breaking each
invariant on purpose and asserting that a named test notices**. Every mutation below is
applied to a *copy* of the production source in a temporary directory - never to the
repository - and the constitutional suite is then run against the mutated copy. A mutation
that leaves the suite green is a hole in the suite.

The eight mutations map onto the eight invariants this feature defends. They are chosen to
be the *smallest* edit that removes each guarantee, because a large mutation would be caught
by something else and would prove nothing about the specific test.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

#: ``apps/`` — the root the three service packages hang off.
APPS = Path(__file__).resolve().parents[3]
#: ``apps/shared/`` — the package under test, and the working directory for a child run.
SHARED = APPS / "shared"
CONSTITUTION = Path(__file__).resolve().parent

#: Everything a mutated child run has to be able to import. The constitutional suite reaches
#: into ``interpretation`` (the producers) and ``control-plane`` (the assembler), so a copy
#: holding only ``shared`` would fail on imports and every mutation would "pass" for the
#: wrong reason.
_COPIED = (
    ("shared", ("domain", "semantic", "events", "contracts.py")),
    ("interpretation", ("extractors",)),
    ("control-plane", ("semantic_path",)),
)

#: ``(label, relative path, find, replace, test node id that must notice)``
MUTATIONS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "CD-6: let a bare string become an operator type",
        "domain/predicate_hypothesis.py",
        'if isinstance(value, str):\n        raise PredicateContractError(',
        'if isinstance(value, str):\n        return RelationRef(value)\n'
        '    if False:\n        raise PredicateContractError(',
        "test_constitution4_no_fabrication.py"
        "::TestThePlatformDoesNotInventAnOperatorType"
        "::test_a_bare_string_at_a_ref_position_is_refused",
    ),
    (
        "CD-1: let the SUPPORTED label be the only way in again",
        "domain/relation_claim_material.py",
        "if material.candidate_status in CONTRADICTING_CANDIDATE_STATUSES:",
        "if material.candidate_status not in ADMISSIBLE_CANDIDATE_STATUSES:",
        "test_constitution4_no_fabrication.py::TestAdmissionIsNotAFormality::test_a_cd1_reading_admits_on_its_evidence_not_its_label",
    ),
    (
        "IV: let an empty tenant through on a temporal observation",
        "domain/temporal_observation.py",
        '        if not str(self.tenant_id).strip():',
        '        if False:',
        "test_iv_vi_tenancy_and_determinism.py::TestTenantsAreFailClosed::test_an_empty_tenant_is_refused",
    ),
    (
        "VI: let a producer's identity into the signal address",
        "extractors/signals/signal.py",
        '"producer_ref": self.producer_ref,',
        '"producer_ref": "",',
        "test_iv_vi_tenancy_and_determinism.py::TestDeterminism::test_two_producers_reading_the_same_thing_are_two_signals",
    ),
    (
        "CD-7: let the table producer mispair a ragged row",
        "extractors/signals/tables.py",
        "        if len(row) != len(headers):\n            continue",
        "        if len(row) > len(headers) + 99:\n            continue",
        "test_constitution4_no_fabrication.py::TestThePlatformDoesNotRoundAnUnknownToAKnow::test_a_table_row_that_does_not_line_up_is_skipped_not_mispaired",
    ),
    (
        "CD-5: pad a time by accepting a naive instant as UTC",
        "domain/temporal_observation.py",
        'raise TemporalObservationContractError(\n            "stated_value_naive",',
        'raise TemporalObservationContractError(\n            "stated_value_absent",',
        "test_constitution4_no_fabrication.py::TestThePlatformDoesNotPadATime::test_a_naive_instant_is_refused_rather_than_assumed_utc",
    ),
    (
        "I-1: let a carried content address be trusted",
        "domain/relation_candidate.py",
        'raise CandidateContractError(\n                        "candidate_id_mismatch",',
        'raise CandidateContractError(\n                        "never_raised",',
        "test_i1_i3_immutability_and_preservation.py::TestObservationsAreImmutable::test_a_carried_address_that_disagrees_is_refused",
    ),
    (
        "CD-6: round an unknown temporal axis onto a known one",
        "domain/temporal_observation.py",
        'raise TemporalObservationContractError(\n            f"{field}_unknown",',
        'raise TemporalObservationContractError(\n            f"{field}_renamed",',
        "test_constitution4_no_fabrication.py::TestThePlatformDoesNotRoundAnUnknownToAKnow::test_a_seventh_axis_is_refused_and_the_six_are_listed",
    ),
)


def _mutated_tree(relative: str, find: str, replace: str) -> Path:
    """A throwaway copy of the production packages with one edit applied.

    The copy is flat - ``domain``, ``extractors`` and ``semantic_path`` land side by side
    under one root - because that is what a single ``PYTHONPATH`` needs to import all three.
    A faithful directory layout would need three path entries and would be harder to read for
    no gain.
    """
    root = Path(tempfile.mkdtemp(prefix="constitution-mutation-"))
    for package, members in _COPIED:
        for member in members:
            source = APPS / package / member
            if source.is_dir():
                shutil.copytree(
                    source, root / source.name, ignore=shutil.ignore_patterns("__pycache__")
                )
            elif source.exists():
                shutil.copy2(source, root / source.name)

    # **The tests are copied too, and that is what makes the mutation reach the code.**
    # pytest puts the rootdir of the test file it was given at the front of ``sys.path``, so
    # running ``CONSTITUTION / node`` - an absolute path into the *original* tree - imported
    # the original ``domain`` and every mutation silently did nothing. Eight "the invariant
    # is unguarded" failures later, the first version of this file was fixed by copying the
    # suite alongside the packages it exercises.
    shutil.copytree(
        CONSTITUTION, root / "tests" / "constitution",
        ignore=shutil.ignore_patterns("__pycache__"),
    )

    target = (root / relative).resolve()
    if not target.exists():
        # A ``../package/...`` path in the table means the mutation lives outside the first
        # package copied; resolve it against the right service root instead.
        tail = relative.split("../", 1)[1]
        target = root / tail
    text = target.read_text(encoding="utf-8")
    assert find in text, f"mutation anchor not found in {relative}: {find[:60]!r}"
    target.write_text(text.replace(find, replace, 1), encoding="utf-8")
    return root


TEETH = Path(__file__).resolve()


def _child_env(root: Path) -> dict[str, str]:
    """The current environment with only ``PYTHONPATH`` redirected.

    An earlier version passed a hand-built ``{"PYTHONPATH": ..., "PATH": "/usr/bin:/bin"}``
    and every run failed with ``WinError 10106`` from Winsock: on Windows a ``PATH`` without
    the System32 directory is not a smaller environment, it is a broken one. Inheriting and
    overriding the single variable that has to change is both correct and less surprising.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root)
    return env


@pytest.mark.parametrize(
    "label,relative,find,replace,node",
    MUTATIONS,
    ids=[m[0].split(":")[0].replace(" ", "-").lower() for m in MUTATIONS],
)
def test_each_invariant_is_actually_guarded(
    label: str, relative: str, find: str, replace: str, node: str
) -> None:
    """Break one invariant and prove a named test notices.

    The assertion is deliberately narrow: the *named* test must fail. A suite that fails for
    some other reason - an import error from the mutation, say - would pass this check while
    proving nothing, so the run is inspected for the specific test.
    """
    root = _mutated_tree(relative, find, replace)
    try:
        completed = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                str(root / "tests" / "constitution" / node),
                "-q", "--no-header", "-p", "no:cacheprovider",
            ],
            capture_output=True,
            text=True,
            cwd=str(root),
            env=_child_env(root),
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)
    assert completed.returncode != 0, (
        f"the mutation {label!r} left {node} green, so nothing is guarding that invariant"
    )


def test_the_constitution_suite_is_green_before_any_mutation() -> None:
    """The other half of the check, and the half that is easy to skip.

    If the suite were red to begin with, "the mutation made it redder" would be meaningless,
    and the eight tests above would pass while guarding nothing at all.

    **This file is excluded from its own run, and that exclusion is load-bearing.** Without
    it this test runs the constitution directory, which includes this file, which spawns
    eight subprocesses, one of which runs the directory again — and the suite never returns.
    The first version did exactly that and had to be killed after fifteen minutes. The
    recursion is structural, not accidental, which is worth writing down so the next person
    to "simplify" the argument does not put it back.
    """
    completed = subprocess.run(
        [
            sys.executable, "-m", "pytest", str(CONSTITUTION),
            "-q", "--no-header", "-p", "no:cacheprovider",
            "--ignore", str(TEETH),
        ],
        capture_output=True,
        text=True,
        cwd=str(SHARED),
        env=_child_env(SHARED),
    )
    assert completed.returncode == 0, completed.stdout[-4000:]
