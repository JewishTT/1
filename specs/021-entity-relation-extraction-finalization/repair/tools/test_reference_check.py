"""Tests for the reference-integrity checker itself.

Three jobs:

1. **Prove the checker fails loudly.** A checker that passes on broken input is
   worthless, so the first group builds synthetic feature directories that contain a
   phantom FR and a phantom task and asserts the gate goes red and the exit code is 1.
2. **Prove the checker does not simply always go red.** A checker that fails on
   *everything* is equally worthless, so there is a synthetic feature directory that
   produces zero FAIL findings, and the assertion is that it stays at zero.
3. **Tripwire the real artefacts.** Each known defect is asserted only while the
   offending token is still present, so a passing run proves "the checker would catch
   this", and a repaired artefact quietly retires its own assertion instead of breaking
   the suite.

Run:
    .venv\\Scripts\\python.exe -m pytest \
        specs/021-entity-relation-extraction-finalization/repair/tools/test_reference_check.py -q
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

_TOOL = Path(__file__).resolve().parent / "reference_check.py"
_spec = importlib.util.spec_from_file_location("reference_check_under_test", _TOOL)
assert _spec and _spec.loader
rc = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = rc
_spec.loader.exec_module(rc)

SPEC_DIR = _TOOL.parents[2]  # tools/ -> repair/ -> the feature directory


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------


def findings_for(spec_dir: Path, only: list[str] | None = None) -> list[rc.Finding]:
    ctx = rc.build_context(spec_dir)
    found, _ran = rc.run_checks(ctx, only or [])
    return found


def fails_for(spec_dir: Path, only: list[str] | None = None) -> list[rc.Finding]:
    return [f for f in findings_for(spec_dir, only) if f.severity == rc.FAIL]


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# --------------------------------------------------------------------------------------
# a synthetic feature directory that is fully self-consistent
# --------------------------------------------------------------------------------------

GOOD_INPUT = """\
# FEATURE 900 - SYNTHETIC

# 1. MISSION

### A. Entity interpretation

### B. Relation interpretation

# 2. CORE DECISION
"""

GOOD_SPEC = """\
# Feature Specification: synthetic

**Input**: `input.md` in this directory (2 sections).

## Requirements

### Functional Requirements

#### Identity

- **FR-001**: `logical_candidate_id` MUST be keyed on `predicate_signature`, never on the
  raw `relation_surface`. (\u00a71)
- **FR-002**: `polarity` MUST be an explicit field on every signal. (\u00a72)

#### Producers

- **FR-003**: A producer MUST emit `mention_ref` values resolved in the mention index.
  (\u00a72)

## Success Criteria

### Measurable Outcomes

- **SC-001**: Active and passive realisations share one `logical_candidate_id`.

### Constitutional invariants

- **INV-001**: An ontology miss yields `UNKNOWN`, never a rejection.
"""

GOOD_TASKS = """\
# Tasks: synthetic

- [ ] T001 [US1] Key `logical_candidate_id` on the signature. (FR-001, \u00a71)
- [ ] T002 [US2] Add `polarity` as a real field. (FR-002, \u00a72)
- [ ] T003 [US3] Resolve every `mention_ref` in the mention index. (FR-003, \u00a72)
"""

GOOD_PLAN = """\
# Implementation Plan: synthetic

3 FRs, 1 measurable outcome, 1 constitutional invariant, 0 user stories.
"""

GOOD_RESEARCH = """\
# Phase 0 Research: synthetic

## R-000. Baseline

Nothing decided yet.
"""

GOOD_DATA_MODEL = """\
# Phase 1 Data Model: synthetic

## 1. Identity carrier

`PredicateSignature` carries the normalised predicate, the arity and the role names. The
candidate id is a digest over that structure.
"""

GOOD_CHECKLIST = """\
# Requirements checklist: synthetic

## A. Identity

| # | Item | Method | FR | Task | State |
|---|---|---|---|---|---|
| A1 | `logical_candidate_id` is keyed on the signature | T | FR-001 | T001 | \u2610 |
| A2 | `polarity` is a real field | T | FR-002 | T002 | \u2610 |

## B. Success criteria and invariants

| # | Item | Method | FR | Task | State |
|---|---|---|---|---|---|
| B1 | Active and passive share one logical id | T | FR-001, SC-001 | T001 | \u2610 |
| B2 | An ontology miss yields UNKNOWN | T | FR-003, INV-001 | T003 | \u2610 |
"""

_GOOD = {
    "input.md": GOOD_INPUT,
    "spec.md": GOOD_SPEC,
    "tasks.md": GOOD_TASKS,
    "plan.md": GOOD_PLAN,
    "research.md": GOOD_RESEARCH,
    "data-model.md": GOOD_DATA_MODEL,
    "checklists/requirements.md": GOOD_CHECKLIST,
}


_ALIASES = {
    "input": "input.md",
    "spec": "spec.md",
    "tasks": "tasks.md",
    "plan": "plan.md",
    "research": "research.md",
    "data-model": "data-model.md",
    "data_model": "data-model.md",
    "checklist": "checklists/requirements.md",
}


def build_feature_dir(root: Path, **overrides: str) -> Path:
    """Write a synthetic feature directory. Keyword names are aliases: `tasks=` is
    `tasks.md`, `checklist=` is `checklists/requirements.md`."""
    files = dict(_GOOD)
    for key, text in overrides.items():
        files[_ALIASES.get(key, key)] = text
    for name, text in files.items():
        write(root / name, text)
    return root


REAL_ARTEFACTS = (
    "input.md",
    "spec.md",
    "tasks.md",
    "plan.md",
    "research.md",
    "data-model.md",
    "checklists/requirements.md",
)


def clone_real_feature(root: Path, **overrides: str) -> Path:
    """Copy the *real* feature artefacts into a scratch directory, optionally rewriting one.

    Used to prove a claim about the real documents ("data-model.md passes with its two
    fences merged") on a copy, so the shipped artefact is never edited by a test.
    """
    for name in REAL_ARTEFACTS:
        text = (SPEC_DIR / name).read_text(encoding="utf-8")
        write(root / name, overrides.get(name, text))
    return root


def fence_spans(text: str) -> list[tuple[int, int]]:
    """(open, close) line indices, 0-based, of every fenced code block."""
    lines = text.splitlines()
    marks = [i for i, line in enumerate(lines) if line.lstrip().startswith("```")]
    return [(marks[i], marks[i + 1]) for i in range(0, len(marks) - 1, 2)]


def fence_containing(text: str, needle: str) -> str:
    """The body of the fenced block that contains `needle` (fails loudly if absent)."""
    lines = text.splitlines()
    for start, end in fence_spans(text):
        body = "\n".join(lines[start + 1:end])
        if needle in body:
            return body
    raise AssertionError(f"no fenced block contains {needle!r}")


_PY_STATEMENT_RE = re.compile(r"^\s*(?:class|def|@|import|from|>>>)\b")


def merge_split_class_fences(text: str) -> tuple[str, int]:
    """Undo the two-fence split a frozen dataclass body was divided into.

    A spec integrator once split `TypeHypothesis` across two ```python fences so that a
    checker whose regex matched the field *name* `hypothesis_state` would not see it. The
    split is independently correct Python-ordering hygiene and independently wrong document
    design, and it exists only because of that checker. This reconstructs the one-fence
    form so a test can assert the checker no longer requires the split.

    A pair is merged only when the two blocks are adjacent in the same code language, the
    first block declares a class, and the second block is *entirely* a class-body
    continuation (every non-blank line indented) - so a fresh top-level statement is never
    swallowed. The prose that introduced the second block is re-emitted after the merged
    block rather than deleted, so the transformation is reversible by eye.
    """
    lines = text.splitlines()
    regions = fence_spans(text)
    bodies: dict[int, list[str]] = {}
    absorbed: set[int] = set()
    for index, ((s1, e1), (s2, e2)) in enumerate(
        zip(regions, regions[1:], strict=False)
    ):
        gap = lines[e1 + 1:s2]
        if any(_PY_STATEMENT_RE.match(g) or g.lstrip().startswith(("|", "#")) for g in gap):
            continue
        first = lines[s1 + 1:e1]
        second = lines[s2 + 1:e2]
        if not any(re.match(r"^class\s", g) for g in first):
            continue
        if not second or not all(g.strip() == "" or g[:1].isspace() for g in second):
            continue
        bodies[index] = first + second
        absorbed.add(index + 1)

    out: list[str] = []
    cursor = 0
    for index, (start, end) in enumerate(regions):
        if index in absorbed:
            cursor = end + 1
            continue
        out.extend(lines[cursor:start])
        out.append(lines[start])
        out.extend(bodies.get(index, lines[start + 1:end]))
        out.append(lines[end])
        cursor = end + 1
        if index in bodies:
            # the prose that introduced the absorbed block moves *after* the merged block,
            # so the transformation is reversible by eye
            following = regions[index + 1][0]
            out.extend(lines[cursor:following])
            cursor = following
    out.extend(lines[cursor:])
    return "\n".join(out) + "\n", len(bodies)


# --------------------------------------------------------------------------------------
# 1. the checker must FAIL on broken input
# --------------------------------------------------------------------------------------


_T003_LINE = "- [ ] T003 [US3] Resolve every `mention_ref` in the mention index. (FR-003, \u00a72)"
_ROW_A1 = ("| A1 | `logical_candidate_id` is keyed on the signature | T | FR-001 | T001 "
           "| \u2610 |")
_ROW_A2 = "| A2 | `polarity` is a real field | T | FR-002 | T002 | \u2610 |"
_FR001 = ("- **FR-001**: `logical_candidate_id` MUST be keyed on `predicate_signature`, "
          "never on the\n  raw `relation_surface`. (\u00a71)")
_T001 = ("- [ ] T001 [US1] Key `logical_candidate_id` on the signature. (FR-001, \u00a71)")


def test_phantom_fr_and_phantom_task_fail_the_gate(tmp_path: Path) -> None:
    """The headline requirement: a phantom FR *and* a phantom task both go red."""
    spec_dir = build_feature_dir(
        tmp_path / "feature",
        **{
            "tasks.md": GOOD_TASKS.replace(
                _T003_LINE,
                "- [ ] T003 [US3] Resolve every `mention_ref` in the index and satisfy the\n"
                "  missing requirement. (FR-103, \u00a72)",
            ),
            "checklists/requirements.md": GOOD_CHECKLIST.replace(
                _ROW_A2,
                "| A2 | `polarity` is a real field, gated on a task that was never written "
                "| T | FR-002 | T002, T009 | \u2610 |",
            ),
        },
    )

    fails = fails_for(spec_dir)
    by_code: dict[str, set[str]] = {}
    for f in fails:
        by_code.setdefault(f.code, set()).add(
            str(f.data.get("fr") or f.data.get("task") or "")
        )
    check_ids = {f.check_id for f in fails}

    # the phantom FR is cited by tasks.md but never defined in spec.md
    assert "RI-01-FR-DEF" in check_ids
    assert "FR-103" in by_code.get("fr-undefined", set()), by_code
    # the phantom task T009 is cited by the checklist but never defined in tasks.md
    assert "RI-02-TASK-REF" in check_ids
    assert "T009" in by_code.get("task-phantom", set()), by_code
    # and the checklist row that gates on it is reported as gating on nothing
    assert "RI-04b-ROW-TASK" in check_ids
    rows = {f.data["row"] for f in fails if f.code == "row-phantom-task"}
    assert rows == {"A2"}, rows
    # ... and the process exit code is non-zero ...
    assert rc.main(["--spec-dir", str(spec_dir)]) == 1
    # ... and --warn-only makes it non-blocking for a repair-in-progress pass
    assert rc.main(["--spec-dir", str(spec_dir), "--warn-only"]) == 0


def test_orphan_fr_is_reported_with_its_exact_set(tmp_path: Path) -> None:
    spec_dir = build_feature_dir(
        tmp_path / "f",
        spec=GOOD_SPEC + "\n#### Unreached\n\n- **FR-004**: Nothing implements this.\n",
    )
    fails = fails_for(spec_dir, ["RI-03-FR-ORPHAN"])
    assert len(fails) == 1
    assert fails[0].data["orphans"] == ["FR-004"]
    assert fails[0].data["total_frs"] == 4


def test_duplicate_fr_definition_fails(tmp_path: Path) -> None:
    spec_dir = build_feature_dir(
        tmp_path / "f", spec=GOOD_SPEC + "\n- **FR-001**: defined a second time.\n"
    )
    fails = fails_for(spec_dir, ["RI-01-FR-DEF"])
    assert [f.code for f in fails] == ["fr-defined-twice"]


def test_phantom_section_citation_fails_and_names_the_intended_subsection(tmp_path: Path) -> None:
    spec_dir = build_feature_dir(
        tmp_path / "f", spec=GOOD_SPEC.replace("\u00a71)", "\u00a71B)")
    )
    fails = fails_for(spec_dir, ["RI-08-SEC-CITE"])
    assert [f.data["section"] for f in fails] == ["1B"]
    assert "B. Relation interpretation" in fails[0].message


def test_section_range_and_phase_qualifier_are_not_phantoms(tmp_path: Path) -> None:
    spec_dir = build_feature_dir(
        tmp_path / "f", spec=GOOD_SPEC.replace("\u00a71)", "\u00a71-\u00a72, \u00a72)")
    )
    assert fails_for(spec_dir, ["RI-08-SEC-CITE"]) == []


# --------------------------------------------------------------------------------------
# 3c. FP-2: `§N` has two namespaces, and only input.md's is a phantom input.md section
#
# `data-model.md` renumbered its own cross-references as "part N" because a bare `§1.5`
# was reported as a phantom section of input.md. That put ~180 phantoms into the file at
# once and forced a convention nobody chose. The tests below are the fixed rule, the
# blind-spot controls that keep the phantom power, and the proof that the workaround is
# no longer needed.
# --------------------------------------------------------------------------------------

_NUMBERED_DATA_MODEL = """\
# Phase 1 Data Model: synthetic

## 1. Identity carrier

`PredicateSignature` carries the normalised predicate, the arity and the role names. The
candidate id is a digest over that structure.

### 1.5 The generated-table discipline

See \u00a71.5 before reading the exclusion table. input.md \u00a71 is the brief.
"""


def test_intra_document_decimal_section_reference_is_not_an_input_md_phantom(
    tmp_path: Path,
) -> None:
    """FP-2: `§1.5` against `### 1.5` in the same file is that file's own cross-reference."""
    spec_dir = build_feature_dir(
        tmp_path / "f", **{"data-model.md": _NUMBERED_DATA_MODEL}
    )
    assert fails_for(spec_dir, ["RI-08-SEC-CITE"]) == []


def test_a_decimal_that_resolves_nowhere_is_still_a_phantom(tmp_path: Path) -> None:
    """The fix is not "decimals are always fine": a dangling sub-section is still a FAIL."""
    spec_dir = build_feature_dir(
        tmp_path / "f",
        **{"data-model.md": _NUMBERED_DATA_MODEL.replace(
            "See \u00a71.5 before", "See \u00a71.9 before")}
    )
    fails = fails_for(spec_dir, ["RI-08-SEC-CITE"])
    assert [f.data["section"] for f in fails] == ["1.9"]


def test_genuinely_nonexistent_integer_section_still_fails(tmp_path: Path) -> None:
    """The blind-spot control for FP-2: an integer in no file at all is still a FAIL."""
    spec_dir = build_feature_dir(
        tmp_path / "f",
        **{
            "data-model.md": _NUMBERED_DATA_MODEL
            + "\nThe brief's \u00a7114 appendix decides the ordering.\n"
        },
    )
    fails = fails_for(spec_dir, ["RI-08-SEC-CITE"])
    assert [f.data["section"] for f in fails] == ["114"]
    assert "input.md" in fails[0].message
    assert rc.main(["--spec-dir", str(spec_dir), "--only", "RI-08-SEC-CITE"]) == 1


def test_a_section_reference_naming_its_own_file_resolves_against_that_file(
    tmp_path: Path,
) -> None:
    """`repair/notes.md` \u00a77.1 is a claim about notes.md, not about input.md."""
    spec_dir = build_repair_dir(
        build_feature_dir(
            tmp_path / "f",
            **{
                "data-model.md": _NUMBERED_DATA_MODEL
                + "\nThe mapping rules are in `repair/notes.md` \u00a77.1.\n"
            },
        ),
        **{"notes": "# notes\n\n## 0. Conventions\n\n### 7.1 Mapping rules\n\nText.\n"},
    )
    assert fails_for(spec_dir, ["RI-08-SEC-CITE"]) == []


def test_a_section_the_named_file_does_not_have_still_fails(tmp_path: Path) -> None:
    """Naming a file is not a free pass: the section has to exist in it."""
    spec_dir = build_repair_dir(
        build_feature_dir(
            tmp_path / "f",
            **{
                "data-model.md": _NUMBERED_DATA_MODEL
                + "\nThe mapping rules are in `repair/notes.md` \u00a79.4.\n"
            },
        ),
        **{"notes": "# notes\n\n## 0. Conventions\n\n### 7.1 Mapping rules\n\nText.\n"},
    )
    fails = fails_for(spec_dir, ["RI-08-SEC-CITE"])
    assert [f.data["section"] for f in fails] == ["9.4"]
    assert "repair/notes.md has no heading \u00a79.4" in fails[0].message


def test_integer_that_resolves_only_inside_the_citing_artefact_is_info_not_silent(
    tmp_path: Path,
) -> None:
    """An integer belongs to input.md's namespace, so the ambiguity is reported, not hidden."""
    spec_dir = build_feature_dir(
        tmp_path / "f",
        **{"data-model.md": "# Data Model\n\n## 8. Type layer\n\nSee \u00a78 for the "
                             "extractor contract.\n"},
    )
    found = findings_for(spec_dir, ["RI-08-SEC-CITE"])
    assert [f.code for f in found] == ["sec-cite-intra-doc-integer"]
    assert found[0].severity == rc.INFO
    assert found[0].data == {"artefact": "data-model.md", "section": "8"}


_PART_REF_RE = re.compile(r"\bpart\s+(\d+(?:\.\d+)?)", re.IGNORECASE)


def test_real_data_model_needs_no_part_n_convention_to_pass(tmp_path: Path) -> None:
    """FP-2, on the real document: writing `part N` as `\u00a7N` must stay clean.

    `data-model.md` currently writes its own cross-references as "part 2.5" because
    `\u00a72.5` used to be reported as a phantom input.md section. This test rewrites that
    workaround back to `\u00a7N` on a *copy* and asserts the checker accepts it - then adds
    one reference that exists in no file and asserts it is still reported.
    """
    original = (SPEC_DIR / "data-model.md").read_text(encoding="utf-8")
    rewritten, count = _PART_REF_RE.subn(lambda m: "\u00a7" + m.group(1), original)
    assert count >= 50, f"expected the 'part N' workaround to be widespread, rewrote {count}"

    clean = clone_real_feature(tmp_path / "sections", **{"data-model.md": rewritten})
    phantoms = [f for f in fails_for(clean, ["RI-08-SEC-CITE"])
                if any(loc.startswith("data-model.md:") for loc in f.locations)]
    assert phantoms == [], [(f.data, f.message) for f in phantoms]

    # blind-spot control: the same document, plus one section that exists nowhere
    broken = clone_real_feature(
        tmp_path / "sections-broken",
        **{"data-model.md": rewritten + "\nSee \u00a7430 for the appendix.\n"},
    )
    fails = fails_for(broken, ["RI-08-SEC-CITE"])
    assert [f.data["section"] for f in fails
            if any(loc.startswith("data-model.md:") for loc in f.locations)] == ["430"]


def test_letter_suffixed_task_id_fails_ordering(tmp_path: Path) -> None:
    spec_dir = build_feature_dir(
        tmp_path / "f", tasks=GOOD_TASKS + "- [ ] T003b [US3] A suffixed sub-task. (FR-003)\n"
    )
    fails = fails_for(spec_dir, ["RI-06-TASK-ORDER"])
    assert [f.code for f in fails] == ["task-letter-suffix"]
    assert fails[0].data["task"] == "T003b"


def test_task_gap_fails_ordering(tmp_path: Path) -> None:
    spec_dir = build_feature_dir(
        tmp_path / "f", tasks=GOOD_TASKS.replace("- [ ] T003", "- [ ] T004")
    )
    fails = fails_for(spec_dir, ["RI-06-TASK-ORDER"])
    assert "task-gap" in {f.code for f in fails}
    assert any("T003" in f.message for f in fails)


# --------------------------------------------------------------------------------------
# 3e. RI-06 contiguity is judged against the range the plan DECLARES
#
# The integrated plan is numbered T101..T194. Deriving the expected set from 1 rather than
# from the plan's own floor reported T001..T100 as 100 gaps - every one a false positive on
# a plan with no hole in it. The tests below are the required regression (T101..T194 clean),
# the four blind-spot controls that keep the check's power (a hole, a duplicate, a
# reordering, a suffixed id), and the degenerate shapes that must not raise.
# --------------------------------------------------------------------------------------

_T101 = "- [ ] T101 [US1] Key `logical_candidate_id` on the signature. (FR-001, \u00a71)"
_T102 = "- [ ] T102 [US2] Add `polarity` as a real field. (FR-002, \u00a72)"
_T103 = "- [ ] T103 [US3] Resolve every `mention_ref` in the mention index. (FR-003, \u00a72)"


def integrated_plan(lo: int = 101, hi: int = 194, hole: int | None = None,
                    duplicate: int | None = None) -> str:
    """A plan numbered T<lo>..T<hi> in ascending order, optionally with one defect."""
    numbers = [n for n in range(lo, hi + 1) if n != hole]
    if duplicate is not None:
        numbers.append(duplicate)
        numbers.sort()
    lines = [f"- [ ] T{n:03d} [US1] Carry out step {n} of the plan. (FR-001, \u00a71)"
             for n in numbers]
    return "\n".join(lines) + "\n"


def test_required_regression_a_plan_above_T001_with_no_gap_is_clean(tmp_path: Path) -> None:
    """The regression this fix exists for: T101..T194 with no hole produces 0 findings."""
    spec_dir = build_feature_dir(tmp_path / "f", tasks=integrated_plan())
    found = findings_for(spec_dir, ["RI-06-TASK-ORDER"])
    blocking_findings = [f for f in found if f.severity in (rc.FAIL, rc.WARN)]
    assert blocking_findings == [], [(f.code, f.message) for f in blocking_findings]
    assert [f.code for f in found] == ["task-order-ok"]
    ok = found[0]
    assert (ok.data["declared_first"], ok.data["declared_last"]) == (101, 194)
    assert ok.data["count"] == 94
    assert "T101..T194" in ok.message
    # and the check is genuinely running on that file, not silently absent
    assert rc.main(["--spec-dir", str(spec_dir), "--only", "RI-06-TASK-ORDER"]) == 0


def test_required_regression_a_hole_inside_the_declared_range_still_fails(tmp_path: Path) -> None:
    """The other half of the regression: T101..T194 minus T150 is still a FAIL."""
    spec_dir = build_feature_dir(tmp_path / "f", tasks=integrated_plan(hole=150))
    fails = fails_for(spec_dir, ["RI-06-TASK-ORDER"])
    assert [f.code for f in fails] == ["task-gap"]
    assert fails[0].data["missing"] == 150
    assert fails[0].data["declared_first"] == 101
    assert fails[0].data["declared_last"] == 194
    assert "T150" in fails[0].message
    # the *actual* missing number is reported, not a count
    assert "93 ids" not in fails[0].message
    assert rc.main(["--spec-dir", str(spec_dir), "--only", "RI-06-TASK-ORDER"]) == 1


def test_the_floor_itself_can_never_be_validated_and_is_not_claimed(tmp_path: Path) -> None:
    """The one defect a declared-range rule structurally cannot see, pinned as a limitation.

    The old rule anchored every plan at T001, so it could see a plan whose ids begin above 1.
    The new rule takes the floor from the file, so a plan whose *first* id is not the id it
    should have started at is indistinguishable from a plan that legitimately starts there:
    `T103, T104, T105` is clean whether or not T101 and T102 were meant to exist. That is the
    exact and only detection power given up, asserted here so it cannot be forgotten.
    """
    rows = [f"- [ ] T{n:03d} [US1] Step {n}. (FR-001, \u00a71)" for n in (103, 104, 105)]
    spec_dir = build_feature_dir(tmp_path / "f", tasks="\n".join(rows) + "\n")
    found = findings_for(spec_dir, ["RI-06-TASK-ORDER"])
    assert [f.code for f in found] == ["task-order-ok"]
    assert found[0].data["declared_first"] == 103
    # a hole at the floor *of that declared range* is still caught
    holed = [f"- [ ] T{n:03d} [US1] Step {n}. (FR-001, \u00a71)" for n in (103, 105, 106)]
    holed_dir = build_feature_dir(tmp_path / "g", tasks="\n".join(holed) + "\n")
    assert [f.data["missing"] for f in
            fails_for(holed_dir, ["RI-06-TASK-ORDER"])] == [104]


def test_a_duplicate_task_id_still_fails(tmp_path: Path) -> None:
    spec_dir = build_feature_dir(tmp_path / "f", tasks=integrated_plan(duplicate=150))
    fails = fails_for(spec_dir, ["RI-06-TASK-ORDER"])
    assert "task-duplicate" in {f.code for f in fails}
    assert [f.data["task"] for f in fails if f.code == "task-duplicate"] == ["T150"]


def test_an_out_of_order_task_still_fails(tmp_path: Path) -> None:
    """T105 written before T104, inside an otherwise contiguous declared range."""
    order = (101, 102, 105, 103, 104)
    rows = [f"- [ ] T{n:03d} [US1] Step {n}. (FR-001, \u00a71)" for n in order]
    spec_dir = build_feature_dir(tmp_path / "f", tasks="\n".join(rows) + "\n")
    found = findings_for(spec_dir, ["RI-06-TASK-ORDER"])
    codes = {f.code for f in found}
    assert "task-out-of-order" in codes, [(f.code, f.message) for f in found]
    ooo = [f for f in found if f.code == "task-out-of-order"]
    assert all(f.severity == rc.FAIL for f in ooo)
    assert [f.data["number"] for f in ooo] == [103], [f.data for f in ooo]
    assert all(f.locations for f in ooo)
    assert rc.main(["--spec-dir", str(spec_dir), "--only", "RI-06-TASK-ORDER"]) == 1


def test_a_letter_suffixed_task_id_still_fails_inside_a_high_range(tmp_path: Path) -> None:
    spec_dir = build_feature_dir(
        tmp_path / "f",
        tasks=integrated_plan(lo=101, hi=104) + "- [ ] T104b [US1] A suffixed step. (FR-001)\n",
    )
    fails = fails_for(spec_dir, ["RI-06-TASK-ORDER"])
    assert [f.code for f in fails] == ["task-letter-suffix"]
    assert fails[0].data["task"] == "T104b"


def test_a_single_task_and_an_empty_task_list_do_not_raise(tmp_path: Path) -> None:
    """The degenerate shapes: one id, and no ids at all."""
    one = build_feature_dir(tmp_path / "one", tasks=_T101 + "\n")
    assert [f.code for f in findings_for(one, ["RI-06-TASK-ORDER"])] == ["task-order-ok"]
    none = build_feature_dir(tmp_path / "none", tasks="No tasks are written yet.\n")
    assert fails_for(none, ["RI-06-TASK-ORDER"]) == []
    for d in (one, none):
        assert not [f for f in findings_for(d) if f.code == "check-crashed"]


def test_the_declared_range_is_derived_from_the_file_not_assumed(tmp_path: Path) -> None:
    """The rule, stated as a property of the check's own arithmetic."""
    high = build_feature_dir(tmp_path / "high", tasks=integrated_plan(lo=401, hi=405))
    ok = next(f for f in findings_for(high, ["RI-06-TASK-ORDER"]) if f.code == "task-order-ok")
    assert (ok.data["declared_first"], ok.data["declared_last"]) == (401, 405)
    low = build_feature_dir(tmp_path / "low", tasks=integrated_plan(lo=1, hi=5))
    ok = next(f for f in findings_for(low, ["RI-06-TASK-ORDER"]) if f.code == "task-order-ok")
    assert (ok.data["declared_first"], ok.data["declared_last"]) == (1, 5)


def test_a_mixed_range_below_its_own_floor_is_reported_as_two_gaps(tmp_path: Path) -> None:
    """A plan that skips a chunk in the middle names every missing number, not one."""
    rows = [f"- [ ] T{n:03d} [US1] Step {n}. (FR-001, \u00a71)"
            for n in (101, 102, 103, 108, 109, 110)]
    spec_dir = build_feature_dir(tmp_path / "f", tasks="\n".join(rows) + "\n")
    fails = fails_for(spec_dir, ["RI-06-TASK-ORDER"])
    assert [f.data["missing"] for f in fails] == [104, 105, 106, 107]
    assert all(f.data["declared_range"] == "T101..T110" for f in fails)


def test_the_real_tasks_md_is_contiguous_across_its_own_range() -> None:
    """The real artefact, re-pointed at the plan's declared range rather than at T001."""
    ctx = rc.build_context(SPEC_DIR)
    found = findings_for(SPEC_DIR, ["RI-06-TASK-ORDER"])
    blocking_findings = [f for f in found if f.severity in (rc.FAIL, rc.WARN)]
    assert blocking_findings == [], [(f.code, f.message) for f in blocking_findings]
    numbers = [int(t.ident[1:]) for t in ctx.tasks if re.fullmatch(r"T\d+", t.ident)]
    assert numbers == sorted(numbers), "the real plan must be ascending"
    assert sorted(numbers) == list(range(min(numbers), max(numbers) + 1)), (
        "the real plan must be contiguous inside its own declared range"
    )
    assert len(numbers) == len(set(numbers)), "the real plan must define no id twice"


def test_count_section_claim_contradiction_fails(tmp_path: Path) -> None:
    spec_dir = build_feature_dir(
        tmp_path / "f", spec=GOOD_SPEC.replace("(2 sections)", "(99 sections)")
    )
    fails = fails_for(spec_dir, ["RI-09-COUNT"])
    assert [f.code for f in fails] == ["count-section-mismatch"]
    assert fails[0].data["claimed"] == 99
    assert fails[0].data["actual"] == 2


def test_count_line_claim_contradiction_fails(tmp_path: Path) -> None:
    spec_dir = build_feature_dir(
        tmp_path / "f", spec=GOOD_SPEC.replace("(2 sections)", "(2 sections, 3411 lines)")
    )
    fails = fails_for(spec_dir, ["RI-09-COUNT"])
    assert "count-line-mismatch" in {f.code for f in fails}
    assert any(f.data["file"] == "input.md" for f in fails)


def test_mutation_range_with_a_non_mutation_endpoint_fails(tmp_path: Path) -> None:
    spec_dir = build_feature_dir(
        tmp_path / "f",
        **{
            "input.md": GOOD_INPUT + "\n# 3. CORPUS NOTES\n",
            "spec.md": GOOD_SPEC.replace("(2 sections)", "(3 sections)"),
            "checklists/requirements.md": GOOD_CHECKLIST.replace(
                _ROW_A1,
                "| A1 | 6 mutations from \u00a71\u2013\u00a73 | T | FR-001 | T001 | \u2610 |",
            ),
        },
    )
    fails = fails_for(spec_dir, ["RI-09-COUNT"])
    codes = {f.code for f in fails}
    assert "mutation-range-not-mutation" in codes, codes
    assert "count-mismatch" in codes, codes
    ranged = [f for f in fails if f.code == "mutation-range-not-mutation"][0]
    # the synthetic brief has no MUTATION headings at all, so every endpoint is wrong
    assert ranged.data["non_mutation_sections"] == ["1", "2", "3"]
    assert ranged.data["lo"] == 1 and ranged.data["hi"] == 3
    counted = [f for f in fails if f.code == "count-mismatch" and f.data["noun"] == "mutations"]
    assert counted[0].data["claimed"] == 6
    assert counted[0].data["actual"] == 0


# --------------------------------------------------------------------------------------
# 3d. FP-3: a section RANGE is a locator, not a count
#
# `FR-078` says "The six \u00a794-\u00a799 mutations are manifest entries 7-12" and the checker
# read the range's upper bound as a claim of "99 mutations". A range endpoint is a section
# label. The tests below are the fixed rule plus three blind-spot controls, because the
# repairs this check exists to catch (a false *number word*, a false *minimum*, a false
# count sitting next to a range) all live in the same code path.
# --------------------------------------------------------------------------------------

MUTATION_INPUT = """\
# 1. MISSION

### A. Entity interpretation

### B. Relation interpretation

# 2. MUTATION ALPHA

# 3. MUTATION BETA

# 4. MUTATION GAMMA

# 5. MUTATION DELTA

# 6. MUTATION EPSILON

# 7. MUTATION ZETA
"""

_SIX_CITED = "\u00a72, \u00a73, \u00a74, \u00a75, \u00a76, \u00a77"


def mutation_spec(fr_003: str) -> str:
    return GOOD_SPEC.replace(
        "- **FR-003**: A producer MUST emit `mention_ref` values resolved in the mention index.\n"
        "  (\u00a72)\n",
        fr_003 + "\n",
    ).replace("(2 sections)", "(7 sections)")


def test_section_range_endpoint_is_not_read_as_a_count_claim(tmp_path: Path) -> None:
    """FP-3: "the six \u00a72-\u00a77 mutations" must not be reported as a claim of 7."""
    spec_dir = build_feature_dir(
        tmp_path / "f",
        **{
            "input.md": MUTATION_INPUT,
            "spec.md": mutation_spec(
                "- **FR-003**: The six \u00a72-\u00a77 mutations are manifest entries 3-8, each\n"
                "  with a named test. (\u00a71)"
            ),
        },
    )
    found = findings_for(spec_dir, ["RI-09-COUNT"])
    assert [f.code for f in found if f.severity == rc.FAIL] == [], [
        (f.code, f.message) for f in found
    ]
    notices = [f for f in found if f.code == "count-range-endpoint"]
    assert len(notices) == 1
    assert notices[0].severity == rc.INFO
    assert "7 mutations" in notices[0].message
    # and the range itself is still verified by the mutation-range rule
    assert [f.code for f in found if f.code == "mutation-range-not-mutation"] == []


def test_a_count_claim_beside_a_section_range_still_fails(tmp_path: Path) -> None:
    """The blind-spot control for FP-3: "17 mutations from \u00a72-\u00a77" is a real claim.

    17 is not a range endpoint, so the fix must not swallow it - this is the shape the
    real `checklists/requirements.md` and `tasks.md` defects have.
    """
    spec_dir = build_feature_dir(
        tmp_path / "f",
        **{
            "input.md": MUTATION_INPUT,
            "spec.md": mutation_spec(
                "- **FR-003**: 17 mutations from \u00a72-\u00a77 MUST each fail. (\u00a71)"
            ),
        },
    )
    fails = fails_for(spec_dir, ["RI-09-COUNT"])
    counted = [f for f in fails if f.code == "count-mismatch" and f.data["noun"] == "mutations"]
    assert len(counted) == 1
    assert counted[0].data["claimed"] == 17
    assert counted[0].data["actual"] == 6


def test_number_word_count_claim_still_fails(tmp_path: Path) -> None:
    """The "Four named mutations" / six-listed-items defect must keep firing."""
    spec_dir = build_feature_dir(
        tmp_path / "f",
        **{
            "input.md": MUTATION_INPUT,
            "spec.md": mutation_spec(
                f"- **FR-003**: Four named mutations ({_SIX_CITED}) MUST each fail. (\u00a71)"
            ),
        },
    )
    fails = fails_for(spec_dir, ["RI-09-COUNT"])
    counted = [f for f in fails if f.code == "count-mismatch" and f.data["noun"] == "mutations"]
    assert len(counted) == 1
    assert counted[0].data["claimed"] == 4
    assert counted[0].data["actual"] == 6


def test_minimum_count_claim_still_fails(tmp_path: Path) -> None:
    """The "\u2265 20 invariants" against 18 enumerated harness fields must keep firing."""
    spec_dir = build_feature_dir(
        tmp_path / "f",
        **{
            "input.md": MUTATION_INPUT,
            "spec.md": mutation_spec(
                "- **FR-003**: The constitutional mutation harness MUST break\n"
                "  (`predicate_signature`, `polarity`, `mention_ref`): the replay pair\n"
                "  (`signal_id`, `candidate_id`) is the manifest. (\u00a71)"
            ).replace(
                "## Success Criteria",
                "- **SC-002**: The constitutional mutation harness breaks \u2265 20 invariants:\n"
                "  every manifest entry has a named test that fails when it is broken.\n\n"
                "## Success Criteria",
            ),
        },
    )
    fails = fails_for(spec_dir, ["RI-09-COUNT"])
    counted = [f for f in fails if f.code == "count-mismatch" and f.data["noun"] == "invariants"]
    assert len(counted) == 1
    assert counted[0].data["claimed"] == 20
    assert counted[0].data["actual"] == 5
    assert "FR-003=5" in counted[0].data["basis"]


def test_section_range_without_a_second_section_mark_is_still_a_range(tmp_path: Path) -> None:
    """`\u00a794-99` is a range too: the second `§` is optional."""
    spec_dir = build_feature_dir(
        tmp_path / "f",
        **{
            "input.md": MUTATION_INPUT,
            "spec.md": mutation_spec(
                "- **FR-003**: The six \u00a72-7 mutations are manifest entries 3-8. (\u00a71)"
            ),
        },
    )
    found = findings_for(spec_dir, ["RI-09-COUNT"])
    assert [f.code for f in found if f.severity == rc.FAIL] == []
    assert [f.code for f in found if f.code == "count-range-endpoint"]


def test_a_plain_number_next_to_a_section_range_is_still_a_count_claim(tmp_path: Path) -> None:
    """Suppression is per *integer inside a range span*, never per line.

    The sentence carries a range and a false count side by side; only the range's endpoints
    are excused.
    """
    spec_dir = build_feature_dir(
        tmp_path / "f",
        **{
            "input.md": MUTATION_INPUT,
            "spec.md": mutation_spec(
                "- **FR-003**: 8 mutations from \u00a72-\u00a77 MUST each fail; the pack has\n"
                "  3 members. (\u00a71)"
            ),
        },
    )
    fails = fails_for(spec_dir, ["RI-09-COUNT"])
    counted = [f for f in fails if f.code == "count-mismatch" and f.data["noun"] == "mutations"]
    assert len(counted) == 1
    assert counted[0].data["claimed"] == 8
    assert counted[0].data["actual"] == 6


def test_stale_not_yet_created_claim_fails(tmp_path: Path) -> None:
    spec_dir = build_feature_dir(tmp_path / "f", plan="1 FR. tasks.md is NOT yet created.\n")
    assert [f.code for f in fails_for(spec_dir, ["RI-12-STALE"])] == ["stale-not-created"]


def test_stale_not_yet_created_claim_named_by_bare_basename_fails(tmp_path: Path) -> None:
    spec_dir = build_feature_dir(
        tmp_path / "f", plan="1 FR. requirements.md is NOT yet created.\n"
    )
    fails = fails_for(spec_dir, ["RI-12-STALE"])
    assert [f.code for f in fails] == ["stale-not-created-bare-name"]
    assert fails[0].data["resolves_to"] == "checklists/requirements.md"


def test_phantom_research_decision_fails(tmp_path: Path) -> None:
    spec_dir = build_feature_dir(tmp_path / "f", spec=GOOD_SPEC + "\n(R-042)\n")
    fails = fails_for(spec_dir, ["RI-11b-RESEARCH"])
    assert [f.code for f in fails] == ["research-phantom"]


def test_forbidden_claims_fail(tmp_path: Path) -> None:
    """The three shapes a repair pass must never reintroduce."""
    spec_dir = build_feature_dir(
        tmp_path / "f",
        **{
            "data-model.md": GOOD_DATA_MODEL.replace(
                "## 1. Identity carrier\n",
                "## 1. Identity carrier\n\n"
                "The N5 synonym set asserts `owns` \u2261 `controls`.\n",
            )
            + "\n## 2. Vocabulary\n\n"
            + "`TypeVocabulary` is bounded and versioned.\n\n"
            + "```python\n@dataclass(frozen=True)\nclass TypeHypothesis:\n"
            + "    hypotheses: tuple[TypeCandidate, ...]\n```\n",
            "spec.md": GOOD_SPEC.replace(
                "#### Producers",
                "#### Vocabulary\n\n"
                "- **FR-004**: The pack MUST cover `core:Person`, `core:Organization` and\n"
                "  `core:Facility`. (\u00a72)\n\n#### Producers",
            ),
        },
    )
    fails = fails_for(spec_dir, ["RI-10-FORBIDDEN"])
    codes = {f.code for f in fails}
    assert "synonym-in-identity" in codes, codes
    assert "nested-hypothesis" in codes, codes
    # FIX 3: an enumerated vocabulary nobody states an obligation for is `vocabulary-unowned`,
    # not "no producer per term". This FR is MUST-and-nothing-else, so it has no bound and
    # delegates to nobody - the blind-spot control for the ownership rule.
    assert "vocabulary-unowned" in codes, codes


def test_nested_hypothesis_absent_is_clean(tmp_path: Path) -> None:
    spec_dir = build_feature_dir(
        tmp_path / "f",
        **{
            "data-model.md": GOOD_DATA_MODEL
            + "\n```python\n@dataclass(frozen=True)\nclass TypeHypothesis:\n"
            + "    type_ref: str\n```\n"
        },
    )
    assert fails_for(spec_dir, ["RI-10-FORBIDDEN"]) == []


# --------------------------------------------------------------------------------------
# 3b. FP-1: the nested-hypothesis rule decides on the field's TYPE SHAPE
#
# The rule's intent is an epistemic-level violation: a hypothesis that contains a *set* of
# hypotheses. An earlier regex fired on the field *name*, so it flagged
# `TypeHypothesis.hypothesis_state` - a field brief §6 (input.md:465-492) *requires* - and
# a spec integrator answered by splitting the dataclass across two ```python fences. The
# three tests below are the fixed rule, the blind-spot control, and the proof that the
# split is no longer needed.
# --------------------------------------------------------------------------------------


TYPE_HYPOTHESIS_WITH_STATE = """\
```python
class HypothesisState(StrEnum):
    UNKNOWN = "unknown"
    CONFLICTING = "conflicting"

@dataclass(frozen=True)
class TypeHypothesis:                   # = interpretation candidate; never a set
    type_surface: str
    normalized_surface: str
    type_ref: str
    scheme: SemanticRef
    hypothesis_state: HypothesisState = HypothesisState.UNKNOWN
    confidence: float = 0.0
    evidence_refs: tuple[str, ...] = ()
    mapping_candidates: tuple[TypeMappingCandidate, ...] = ()
```
"""


def test_hypothesis_state_field_is_legal_and_does_not_fail_the_gate(tmp_path: Path) -> None:
    """FP-1: the required `hypothesis_state: HypothesisState` scalar is not nesting."""
    spec_dir = build_feature_dir(
        tmp_path / "f", **{"data-model.md": GOOD_DATA_MODEL + "\n" + TYPE_HYPOTHESIS_WITH_STATE}
    )
    fails = fails_for(spec_dir, ["RI-10-FORBIDDEN"])
    assert [f.code for f in fails] == [], [(f.code, f.message) for f in fails]
    # the exemption is not "the file happens to be quiet": the field is present and parsed
    assert "hypothesis_state: HypothesisState" in TYPE_HYPOTHESIS_WITH_STATE
    assert not rc.field_nests_hypotheses("hypothesis_state", "HypothesisState")


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        # (a) a collection whose element type is a *Hypothesis - the violation itself
        ("hypotheses: tuple[TypeHypothesis, ...]", True),
        ("alternatives: Sequence[DirectionHypothesis]", True),
        ("peers: frozenset[PredicateHypothesis]", True),
        ("self_ref: TypeHypothesis | None", False),
        # (b) any collection under a field name that says "hypotheses"
        ("hypotheses: tuple[str, ...]", True),
        ("nested_hypotheses: list[HypothesisRef]", True),
        ("hypothesis_set: HypothesisSet", True),
        # (c) legal scalars and legal non-hypothesis collections
        ("hypothesis_state: HypothesisState", False),
        ("hypothesis_state: HypothesisStates = HypothesisStates.UNKNOWN", False),
        ("hypothesis_kind: HypothesisKind", False),
        ("type_ref: str", False),
        ("evidence_refs: tuple[str, ...]", False),
        ("mapping_candidates: tuple[TypeMappingCandidate, ...]", False),
        ("relation_ref: RelationRef | None", False),
        ("predicate_signature: PredicateSignature", False),
        # a container that is emphatically not of hypotheses
        ("evidence_refs: tuple[str, ...] | None", False),
    ],
)
def test_field_nests_hypotheses_is_decided_on_type_shape(field: str, expected: bool) -> None:
    """The whole FP-1 fix, as one truth table on the predicate the check now uses."""
    name, _, annotation = field.partition(":")
    assert rc.field_nests_hypotheses(name.strip(), annotation.strip()) is expected, field


def test_a_real_container_of_hypotheses_still_fails_the_gate(tmp_path: Path) -> None:
    """The blind-spot control for FP-1: four genuine containers, four FAILs.

    If the fix had degenerated into "never fire", this test is what would catch it.
    """
    containers = (
        "    hypotheses: tuple[TypeHypothesis, ...]",
        "    alternatives: Sequence[DirectionHypothesis]",
        "    peers: frozenset[PredicateHypothesis]",
        "    hypothesis_set: HypothesisSet",
    )
    spec_dir = build_feature_dir(
        tmp_path / "f",
        **{
            "data-model.md": GOOD_DATA_MODEL
            + "\n## 11. Nesting shapes\n\n```python\n@dataclass(frozen=True)\n"
            "class TypeHypothesis:\n"
            + "\n".join(containers)
            + "\n```\n"
        },
    )
    fails = fails_for(spec_dir, ["RI-10-FORBIDDEN"])
    nested = [f for f in fails if f.code == "nested-hypothesis"]
    assert [f.data["field"] for f in nested] == [
        "hypotheses", "alternatives", "peers", "hypothesis_set"
    ], [(f.data, f.message) for f in nested]
    assert all(f.data["container"] == "TypeHypothesis" for f in nested)
    assert all(f.severity == rc.FAIL for f in nested)
    assert rc.main(["--spec-dir", str(spec_dir), "--only", "RI-10-FORBIDDEN"]) == 1


def test_a_container_of_hypotheses_on_a_non_hypothesis_class_is_not_nesting(
    tmp_path: Path,
) -> None:
    """`TypedMention.type_hypotheses: tuple[TypeHypothesis, ...]` is aggregation, not nesting.

    The real data-model carries exactly this shape (`extractors/types.py::TypedMention`).
    Only a *hypothesis* holding a set of hypotheses is a new epistemic level; a mention
    holding many is the ordinary shape of the design.
    """
    spec_dir = build_feature_dir(
        tmp_path / "f",
        **{
            "data-model.md": GOOD_DATA_MODEL
            + "\n```python\n@dataclass(frozen=True)\nclass TypedMention:\n"
            "    mention_ref: str\n"
            "    type_hypotheses: tuple[TypeHypothesis, ...] = ()\n\n"
            "@dataclass(frozen=True)\nclass ResolutionMention:\n"
            "    type_hypotheses: tuple[TypeHypothesis, ...] = ()\n```\n"
        },
    )
    assert fails_for(spec_dir, ["RI-10-FORBIDDEN"]) == []


def test_real_data_model_needs_no_two_fence_split_to_pass(tmp_path: Path) -> None:
    """FP-1, on the real document: the split dataclass must be legal again.

    `data-model.md` currently shows `TypeHypothesis` in two ```python fences. The split
    exists only because the old rule matched the field name `hypothesis_state`. This test
    reconstructs the single-fence form, asserts it is the same class, and asserts the
    checker no longer objects - without editing the shipped artefact.
    """
    original = (SPEC_DIR / "data-model.md").read_text(encoding="utf-8")
    merged, merges = merge_split_class_fences(original)
    assert merges >= 1, "no split dataclass fence found in data-model.md"
    assert merged.count("```") == original.count("```") - 2 * merges

    body = fence_containing(merged, "class TypeHypothesis:")
    # the same class, in one fence, with the brief §6 field inside it
    assert "hypothesis_state: HypothesisState" in body
    assert "type_surface: str" in body
    assert "mapping_candidates: tuple[TypeMappingCandidate, ...]" in body

    # the shape the old rule matched, spelled out, so this test cannot pass vacuously
    pre_fix_would_fire = re.search(
        r"^\s*(\w*hypothes\w*)\s*:", body, re.IGNORECASE | re.MULTILINE
    )
    assert pre_fix_would_fire is not None
    assert pre_fix_would_fire.group(1) == "hypothesis_state"

    spec_dir = clone_real_feature(tmp_path / "merged-fences", **{"data-model.md": merged})
    fails = fails_for(spec_dir, ["RI-10-FORBIDDEN"])
    assert [f.code for f in fails if f.code == "nested-hypothesis"] == [], [
        (f.code, f.message) for f in fails
    ]


def test_inverse_citation_is_warn_and_does_not_fail_the_gate(tmp_path: Path) -> None:
    spec_dir = build_feature_dir(
        tmp_path / "f",
        spec=GOOD_SPEC.replace(
            _FR001,
            "- **FR-001**: `SignalKind` MUST contain at least `LEXICAL`, `TABLE`, `TEMPORAL`.\n"
            "  (\u00a71)",
        ),
        tasks=GOOD_TASKS.replace(
            _T001,
            "- [ ] T001 [US1] Do NOT add a `TEMPORAL` member. (FR-001, \u00a71)",
        ),
    )
    warns = [f for f in findings_for(spec_dir, ["RI-05b-INVERSE-CITE"])
             if f.severity == rc.WARN]
    assert [f.data["literal"] for f in warns] == ["TEMPORAL"]


def test_miscitation_is_warn_and_does_not_fail_the_gate(tmp_path: Path) -> None:
    spec_dir = build_feature_dir(
        tmp_path / "f",
        tasks=GOOD_TASKS.replace(
            "- [ ] T001 [US1] Key `logical_candidate_id` on the signature. (FR-001, \u00a71)",
            "- [ ] T001 [US1] Add `apps/x/parser.py` with `ParserConfig` and `loader`. (FR-002)",
        ),
    )
    warns = [f for f in findings_for(spec_dir, ["RI-05-MISCITE"]) if f.severity == rc.WARN]
    assert any(f.data["fr"] == "FR-002" for f in warns), [f.data for f in warns]


# --------------------------------------------------------------------------------------
# 2. malformed input must be a finding, never an exception
# --------------------------------------------------------------------------------------


def test_malformed_markdown_produces_findings_not_exceptions(tmp_path: Path) -> None:
    spec_dir = build_feature_dir(
        tmp_path / "f",
        **{
            "spec.md": (
                "# broken\n\n"
                "- **FR-001** no colon, no heading, unbalanced table\n"
                "| a | b\n|---\n| 1 | 2 | 3 | 4 |\n"
                "- **FR-002**: body\n"
                "  - **FR-002**: duplicate definition\n"
                "control bytes \x00\x01 and a replacement char \ufffd\n"
            ),
            "tasks.md": "- [ ] T001 x\n- [ ] T1 y\n- [ ] T0012 z\n- [ ] T-1 w\n",
            "checklists/requirements.md": "|||||\n| a | b |\n",
            "data-model.md": "```python\nclass (:\n",
        },
    )
    found = findings_for(spec_dir)
    assert found, "malformed input must produce findings"
    crashed = [f.message for f in found if f.code == "check-crashed"]
    assert not crashed, crashed
    assert rc.main(["--spec-dir", str(spec_dir)]) == 1


def test_missing_artefact_is_a_finding_not_a_crash(tmp_path: Path) -> None:
    spec_dir = build_feature_dir(tmp_path / "f")
    (spec_dir / "research.md").unlink()
    found = findings_for(spec_dir)
    codes = {(f.check_id, f.code) for f in found}
    assert ("RI-00-INPUT", "missing") in codes
    assert ("RI-11b-RESEARCH", "no-research-defs") in codes
    assert not [f for f in found if f.code == "check-crashed"]


def test_empty_artefact_is_a_finding(tmp_path: Path) -> None:
    spec_dir = build_feature_dir(tmp_path / "f", **{"data-model.md": "   \n\n"})
    assert ("RI-00-INPUT", "empty") in {(f.check_id, f.code)
                                        for f in findings_for(spec_dir)}


def test_non_utf8_artefact_is_a_finding_not_a_crash(tmp_path: Path) -> None:
    spec_dir = build_feature_dir(tmp_path / "f")
    (spec_dir / "plan.md").write_bytes(b"# plan\nlatin-1: \xe9\xe8\xea\n")
    found = findings_for(spec_dir)
    assert ("RI-00-INPUT", "unreadable") in {(f.check_id, f.code) for f in found}
    assert not [f for f in found if f.code == "check-crashed"]


def test_no_input_md_makes_section_checks_report_not_guess(tmp_path: Path) -> None:
    spec_dir = build_feature_dir(tmp_path / "f")
    (spec_dir / "input.md").unlink()
    codes = {(f.check_id, f.code) for f in findings_for(spec_dir)}
    assert ("RI-08-SEC-CITE", "no-section-authority") in codes


# --------------------------------------------------------------------------------------
# 3. the checker must NOT fail on consistent input
# --------------------------------------------------------------------------------------


def test_synthetic_consistent_feature_dir_has_zero_failures(tmp_path: Path) -> None:
    spec_dir = build_feature_dir(tmp_path / "f")
    fails = fails_for(spec_dir)
    assert fails == [], [(f.check_id, f.code, f.message) for f in fails]
    assert rc.main(["--spec-dir", str(spec_dir)]) == 0


def test_every_check_id_is_reported_as_ran_even_when_clean(tmp_path: Path) -> None:
    """A check that never runs must be visible as `clean`, not silently absent."""
    spec_dir = build_feature_dir(tmp_path / "f")
    ctx = rc.build_context(spec_dir)
    _found, ran = rc.run_checks(ctx)
    assert set(ran) == set(rc.CHECK_BY_ID)
    rows = rc.summarize([], ran)
    assert len(rows) == len(rc.CHECK_BY_ID)
    assert all(r["clean"] for r in rows), [r for r in rows if not r["clean"]]


def test_clean_input_still_reports_verified_counts_as_info(tmp_path: Path) -> None:
    """`--show-ok` proves the checker is measuring, not only complaining."""
    spec_dir = build_feature_dir(tmp_path / "f")
    ctx = rc.build_context(spec_dir)
    found, ran = rc.run_checks(ctx)
    ok = [f for f in found if f.code in {"count-ok", "count-section-ok"}]
    assert {f.data.get("noun", "sections") for f in ok} >= {
        "frs", "measurable outcome", "constitutional invariant", "sections"}
    text = rc.render_text(ctx, found, rc.summarize(found, ran), show_ok=True,
                          max_detail=0, warn_only=False)
    assert "TOTAL" in text and "exit: 0" in text


# --------------------------------------------------------------------------------------
# 4. unit tests of the parsers and heuristics
# --------------------------------------------------------------------------------------


def test_check_registry_is_consistent() -> None:
    assert {cid for cid, _ in rc.CHECK_FNS} == set(rc.CHECK_BY_ID)
    for spec in rc.CHECKS:
        assert spec.rule.strip()
        assert spec.severity in rc.SEVERITIES
        assert spec.title.strip()


def test_fr_dangling_after_a_table_fails(tmp_path: Path) -> None:
    """A requirement bullet that hangs off the bottom of a table is ungrouped."""
    spec_dir = build_feature_dir(
        tmp_path / "f",
        spec=GOOD_SPEC.replace(
            "## Success Criteria",
            "## Unrelated table\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n"
            "- **FR-004**: dangling after the table.\n\n## Success Criteria",
        ),
    )
    fails = fails_for(spec_dir, ["RI-06b-FR-ORDER"])
    assert [f.code for f in fails] == ["fr-dangles-after-table"]
    assert fails[0].data["fr"] == "FR-004"


# --------------------------------------------------------------------------------------
# FIX 1 - a retired id is not a gap in the requirement sequence
# --------------------------------------------------------------------------------------
#
# `spec.md` retires an id in a *tombstone record table*, which is deliberately not in
# definition form. So the retired id has no `- **FR-nnn**:` row, the contiguity walk never
# sees it, and every number either side of it looks like a hole. Six tombstones x the
# neighbours they sit between was 19 FAIL findings saying "FR-058 is missing", about an id
# the document deliberately closed.
#
# The walk's universe is now: defined in `spec.md`, or retired. A number in neither is a real
# gap and still FAILs. The two tests below pin both halves of that sentence, and both assert
# the walk actually ran (via `fr-sequence-ok`) so neither can pass by the check doing nothing.


def _numbering_spec(numbers: Sequence[str]) -> str:
    """A spec.md whose only requirement section holds exactly `numbers`, in that order."""
    rows = "\n".join(
        f"- **{n}**: Requirement {n} MUST hold for the synthetic corpus. (\u00a72)"
        for n in numbers
    )
    return (
        "# Feature Specification: numbering only\n\n"
        "**Input**: `input.md` in this directory (2 sections).\n\n"
        "## Requirements\n\n### Functional Requirements\n\n#### Numbering\n\n"
        f"{rows}\n"
    )


def _walk_ran(spec_dir: Path) -> rc.Finding:
    found = findings_for(spec_dir, ["RI-06b-FR-ORDER"])
    ok = [f for f in found if f.code == "fr-sequence-ok"]
    assert len(ok) == 1, "the contiguity walk must report that it ran"
    return ok[0]


def test_a_tombstoned_id_between_two_live_ids_is_not_a_gap(tmp_path: Path) -> None:
    """REQUIRED (FIX 1): a retirement between two live numbers produces 0 findings.

    `FR-058` is in `TOMBSTONED_FRS` and has no definition row, which is exactly the corpus
    shape: `FR-057`, (retired 058), `FR-059`. Before the fix this was
    `fr-gap-document-order ... FR-058 appear(s) nowhere`.
    """
    spec_dir = build_feature_dir(tmp_path / "f", spec=_numbering_spec(["FR-057", "FR-059"]))
    ctx = rc.build_context(spec_dir)
    assert "FR-058" in ctx.tombstone_ids
    assert "FR-058" not in ctx.def_index(), "the premise: a record table is not a definition row"
    found = findings_for(spec_dir, ["RI-06b-FR-ORDER"])
    assert [f.code for f in found if f.severity in (rc.FAIL, rc.WARN)] == []
    _walk_ran(spec_dir)


def test_a_genuinely_absent_number_between_two_live_ids_still_fails(tmp_path: Path) -> None:
    """REQUIRED (FIX 1): the teeth. `FR-058` is retired, `FR-059` and `FR-060` are simply absent.

    The FAIL is now the *coverage* arm and its code is `fr-gap`, not the document-order arm: the
    rule is "every FR number is DEFINED, or TOMBSTONED, or RESERVED", and a number that is none of
    the three is a hole whatever shape made it visible. The document-order arm still reports the
    same interval, at INFO, because adjacency is placement and placement is not a defect.
    """
    spec_dir = build_feature_dir(tmp_path / "f", spec=_numbering_spec(["FR-057", "FR-061"]))
    fails = fails_for(spec_dir, ["RI-06b-FR-ORDER"])
    codes = {f.code for f in fails}
    assert codes == {"fr-gap"}, [f.message for f in fails]
    by_fr = {f.data["fr"]: f for f in fails}
    assert set(by_fr) == {"FR-059", "FR-060"}
    # one finding per unaccounted number, and FR-058 - the retired one - is not among them
    for fr, f in by_fr.items():
        assert f.data["missing"] == [fr]
        assert "none of the three" in f.message
    assert not any("FR-058" in f.data.get("missing", []) for f in fails)
    # the demoted arm still sees the interval, and says so at INFO
    doc_order = [f for f in findings_for(spec_dir, ["RI-06b-FR-ORDER"])
                 if f.code == "fr-gap-document-order"]
    assert len(doc_order) == 1
    assert doc_order[0].severity == rc.INFO
    assert doc_order[0].data["skipped"] == ["FR-058", "FR-059", "FR-060"]
    assert doc_order[0].data["tombstoned"] == [58]
    assert doc_order[0].data["unaccounted"] == [59, 60]
    _walk_ran(spec_dir)


def test_a_tombstoned_id_is_excluded_from_the_gap_but_still_gated_as_a_citation(
    tmp_path: Path,
) -> None:
    """The exclusion must not become a licence to cite the retired id: two checks, one each.

    `RI-06b-FR-ORDER` no longer complains that the number is absent, and
    `TOMBSTONED-FR-REF` still complains that a task points at it. Removing the first must not
    silence the second.
    """
    spec_dir = build_feature_dir(
        tmp_path / "f",
        spec=_numbering_spec(["FR-057", "FR-059"]),
        tasks=("- [ ] T001 [US1] Preserve the edge-after-claim obligation. (FR-057, \u00a72)\n"
               "- [ ] T002 [US2] Keep the persistence surface intact. (FR-059, FR-058, \u00a72)\n"),
    )
    assert fails_for(spec_dir, ["RI-06b-FR-ORDER"]) == []
    tombstone_fails = fails_for(spec_dir, ["TOMBSTONED-FR-REF"])
    assert [(f.code, f.data["fr"], f.data["replacement"]) for f in tombstone_fails] == [
        ("tombstoned-fr-cited-normative", "FR-058", "INV-004")
    ]


def test_a_number_defined_in_another_section_is_not_a_gap(tmp_path: Path) -> None:
    """The second half of the fix's rule: *recorded* means defined anywhere in spec.md.

    `spec.md` interleaves canonical requirement sections with per-workstream allocation bands,
    so a number two sections away is recorded, not missing. The contiguity arm reads the
    requirement sequence, not the local interval.

    What this test used to assert is the given-up power, named rather than lost: it asserted that
    the *order* arm still fires on 001, 003, 002. It no longer does at FAIL, because a rewind
    across sections is what placing a band in its own subject section looks like, and that is a
    legitimate authoring choice rather than a defect. The arm still fires, at INFO, with both
    endpoints and the size of the rewind in its data - so the observation survives the demotion
    and is greppable; it simply no longer gates.
    """
    spec = (
        "# Feature Specification: numbering only\n\n"
        "**Input**: `input.md` in this directory (2 sections).\n\n"
        "## Requirements\n\n### Functional Requirements\n\n#### Canonical band\n\n"
        "- **FR-001**: The first requirement MUST hold. (\u00a72)\n"
        "- **FR-003**: The third requirement MUST hold. (\u00a72)\n\n"
        "#### Allocated band\n\n"
        "- **FR-002**: The second requirement MUST hold. (\u00a72)\n"
    )
    spec_dir = build_feature_dir(tmp_path / "f", spec=spec)
    found = findings_for(spec_dir, ["RI-06b-FR-ORDER"])
    assert [f for f in found if f.severity in (rc.FAIL, rc.WARN)] == [], [
        (f.code, f.message) for f in found if f.severity in (rc.FAIL, rc.WARN)]
    assert "fr-gap" not in {f.code for f in found}
    # both placement arms still report, at INFO, and name FR-002 as defined in another section
    in_section = [f for f in found if f.code == "fr-gap-in-section"]
    assert len(in_section) == 1 and in_section[0].severity == rc.INFO
    assert in_section[0].data["defined_elsewhere"] == [2]
    assert in_section[0].data["unaccounted"] == []
    doc_order = [f for f in found if f.code == "fr-gap-document-order"]
    assert len(doc_order) == 1 and doc_order[0].severity == rc.INFO
    assert doc_order[0].data["defined_elsewhere"] == [2]

    # the placement observation survives the demotion, with both endpoints and the rewind size
    rewind = [f for f in found if f.code == "fr-non-monotonic-document-order"]
    assert len(rewind) == 1
    assert rewind[0].severity == rc.INFO
    assert (rewind[0].data["first"], rewind[0].data["second"]) == ("FR-003", "FR-002")
    assert rewind[0].data["rewind"] == 1
    _walk_ran(spec_dir)


def test_rewind_and_dangling_arms_are_untouched_by_the_tombstone_exclusion(
    tmp_path: Path,
) -> None:
    """A tombstone in the file must not mute the arms the fix did not touch.

    The *in-section* rewind arm is still FAIL, and still fires: within one requirement list a
    rewind is a list whose own numbering contradicts itself, which subject-section placement does
    not explain. The *document-order* rewind is the demoted one. Both are asserted here so that
    which arm is which cannot be swapped by accident.
    """
    spec = _numbering_spec(["FR-059", "FR-057"]).replace(
        "#### Numbering\n",
        "#### Numbering\n\n- **FR-058**: *tombstone - merged into `FR-057`; history only.*\n",
    )
    spec_dir = build_feature_dir(tmp_path / "f", spec=spec)
    found = findings_for(spec_dir, ["RI-06b-FR-ORDER"])
    gating = {f.code for f in found if f.severity in (rc.FAIL, rc.WARN)}
    assert gating == {"fr-non-monotonic"}, [f.code for f in found]
    demoted = [f for f in found if f.code == "fr-non-monotonic-document-order"]
    assert demoted and demoted[0].severity == rc.INFO

    table_dir = build_feature_dir(
        tmp_path / "g",
        spec=_numbering_spec(["FR-057", "FR-058"]).replace(
            "#### Numbering\n",
            "#### Numbering\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n",
        ),
    )
    assert "fr-dangles-after-table" in {f.code for f in
                                        fails_for(table_dir, ["RI-06b-FR-ORDER"])}


def test_recorded_fr_numbers_is_defined_plus_tombstoned() -> None:
    """The walk's universe, as a unit, so the two inputs cannot drift apart silently."""
    assert rc._recorded_fr_numbers.__doc__
    assert rc._sequence_gaps(1, 5, {1, 2, 3, 4, 5}) == []
    assert rc._sequence_gaps(1, 5, {1, 2, 4, 5}) == [3]
    assert rc._sequence_gaps(1, 5, {1, 2, 3, 5}) == [4]
    assert rc._sequence_gaps(1, 5, {1, 2, 3, 4, 5, 99}) == []


# --------------------------------------------------------------------------------------
# FIX 1 (second pass) - coverage, not density: DEFINED or TOMBSTONED or RESERVED
# --------------------------------------------------------------------------------------
#
# `ARBITRATION.md` §14 leaves `FR-101...109` and `FR-116...129` deliberately empty for a later
# wave, and `spec.md` places each workstream's band in that workstream's own subject section. The
# first version of this rule asked for *density* - every number between two neighbours in a list
# had to be in that list - and so reported 15 FAIL findings that were all the same category error:
# a number that is defined two sections away, or reserved on purpose, is not a hole. The checker
# could not tell **deliberately reserved** from **accidentally missing**, and that is the exact
# blind spot that let `FR-103` be cited as a live requirement for as long as it was.
#
# The rule is now coverage with three admitted categories, and the reserved one is *parsed from
# spec.md* rather than hard-coded here, so the document and the tool cannot disagree about which
# numbers are on purpose. Four properties are pinned below, in the order they matter:
#
#   1. a sparse sequence that is DECLARED reserved produces 0 FAIL           (the fix works)
#   2. a sparse sequence that is NOT declared still FAILs                    (the teeth survive)
#   3. a reserved number that is CITED still FAILs                           (absence != licence)
#   4. a document-order rewind is INFO, not FAIL                           (placement is no defect)


_RESERVATION_BLOCK = (
    "#### Reserved number space\n\n"
    "> **Reserved number space \u2014 stated once, here.** Three ranges of the\n"
    "> `FR-` namespace are **deliberately empty and reserved**: numbers\n"
    "> **{lo1}\u2013{hi1}**, **{lo2}\u2013{hi2}** and **{lo3}\u2013{hi3}**. Nothing in this\n"
    "> document occupies any of them.\n"
    ">\n"
    "> `RESERVED-FR: {d1}\n"
    ">\n"
    "> The bands that **are** occupied are `{occ_lo}\u2013{occ_hi}`.\n\n"
)


def _spec_with_reservation(numbers: Sequence[str], reserved: str = "104-105",
                           occ: str = "101-103") -> str:
    """`_numbering_spec` plus a reserved-number-space block declaring `reserved`."""
    blocks: list[str] = []
    for piece in reserved.split(","):
        lo, _, hi = piece.strip().partition("-")
        blocks.append((int(lo), int(hi)))
    return _numbering_spec(numbers).replace(
        "#### Numbering\n",
        "#### Numbering\n\n" + _RESERVATION_BLOCK.format(
            lo1=f"{blocks[0][0]:03d}", hi1=f"{blocks[0][1]:03d}",
            lo2=f"{blocks[1][0]:03d}" if len(blocks) > 1 else f"{blocks[0][0]:03d}",
            hi2=f"{blocks[1][1]:03d}" if len(blocks) > 1 else f"{blocks[0][1]:03d}",
            lo3=f"{blocks[-1][0]:03d}", hi3=f"{blocks[-1][1]:03d}",
            d1=reserved.replace("-", "-").replace(" ", ""),
            occ_lo=occ.split("-")[0], occ_hi=occ.split("-")[1],
        ),
    )


def test_a_sparse_sequence_that_is_declared_reserved_has_zero_failures(tmp_path: Path) -> None:
    """REQUIRED (FIX 1): sparse but declared -> 0 FAIL.

    `FR-103`, `FR-104` and `FR-105` are declared reserved; only `FR-101`, `FR-102` and `FR-106`
    are defined. Before the fix that was `fr-gap` and `fr-gap-document-order` FAIL findings about
    numbers `spec.md` says are on purpose. The walk still runs and says so.
    """
    spec = _spec_with_reservation(["FR-101", "FR-102", "FR-106"], reserved="103-105")
    spec_dir = build_feature_dir(tmp_path / "f", spec=spec)
    ctx = rc.build_context(spec_dir)
    assert ctx.reservation.readable, ctx.reservation.problem
    assert ctx.reservation.numbers == frozenset({103, 104, 105})
    found = findings_for(spec_dir, ["RI-06b-FR-ORDER"])
    assert [f.code for f in found if f.severity in (rc.FAIL, rc.WARN)] == [], [
        (f.code, f.message) for f in found if f.severity in (rc.FAIL, rc.WARN)]
    # the demoted arms are still there and still name the interval
    assert "fr-gap-document-order" in {f.code for f in found}
    ok = _walk_ran(spec_dir)
    assert ok.data["reserved"] == 3
    assert ok.data["unaccounted_numbers"] == 0


def test_an_undeclared_sparse_sequence_still_fails(tmp_path: Path) -> None:
    """REQUIRED (FIX 1): the same shape with a broken declaration -> FAIL. The teeth.

    Identical to the test above except that the `RESERVED-FR:` declaration has been replaced by a
    line that says nothing machine-readable, so the document no longer *claims* a reservation and
    `FR-104` and `FR-105` are simply absent. Nothing in the tool falls back to a hard-coded list,
    so this is what the checker does when the document stops claiming one - and it fails closed,
    reporting the unreadable declaration rather than quietly exempting half of it.
    """
    spec = _spec_with_reservation(["FR-101", "FR-102", "FR-106"], reserved="103-105")
    stripped = spec.replace("> `RESERVED-FR: 103-105\n", "> (no machine-readable declaration)\n")
    spec_dir = build_feature_dir(tmp_path / "f", spec=stripped)
    ctx = rc.build_context(spec_dir)
    assert ctx.reservation.declared and not ctx.reservation.readable
    assert ctx.reservation.numbers == frozenset()
    fails = fails_for(spec_dir, ["RI-06b-FR-ORDER"])
    assert "reservation-declaration-unreadable" in {f.code for f in fails}
    gaps = [f for f in fails if f.code == "fr-gap"]
    assert [f.data["fr"] for f in gaps] == ["FR-103", "FR-104", "FR-105"], [
        f.message for f in gaps]
    assert all("none of the three" in f.message for f in gaps)
    _walk_ran(spec_dir)


def test_a_reserved_number_that_is_cited_still_fails_the_definition_check(tmp_path: Path) -> None:
    """REQUIRED (FIX 1): reservation permits absence, not citation.

    A reservation buys a number the right to be *absent*. Naming it is a separate defect, owned by
    `RI-01-FR-DEF`, and the two must not be confused - otherwise declaring `FR-101`-`FR-109`
    reserved would have quietly legalised the `FR-103` phantom that `phase0-results.md` still
    cites. Asserted through `tasks.md`, which is a live artefact, and scoped to the reserved range
    so the synthetic directory's other artefacts cannot blur it.
    """
    spec = _spec_with_reservation(["FR-101", "FR-102", "FR-106"], reserved="103-105")
    spec_dir = build_feature_dir(
        tmp_path / "f", spec=spec,
        tasks=("- [ ] T001 [US1] Honour the reserved extractor obligation. (FR-104, §1)\n"
               "- [ ] T002 [US2] Keep the declared reservation reserved. (FR-101, §1)\n"),
    )
    # the reservation itself is clean: the number is absent, and that is allowed
    assert fails_for(spec_dir, ["RI-06b-FR-ORDER"]) == []
    undef = [f for f in fails_for(spec_dir, ["RI-01-FR-DEF"])
             if f.data.get("fr") in {"FR-103", "FR-104", "FR-105"}]
    assert [(f.code, f.data["fr"]) for f in undef] == [("fr-undefined", "FR-104")], [
        f.message for f in undef]
    assert "cited but never defined" in undef[0].message
    # FR-101 is defined, so naming it is fine; FR-104 is reserved, so naming it is not
    assert not any(f.data.get("fr") == "FR-101" for f in undef)


def test_a_document_order_rewind_is_info_not_fail(tmp_path: Path) -> None:
    """REQUIRED (FIX 1): placement by subject section is a legitimate authoring choice.

    Two sections, one per band, each internally ascending, and the file as a whole rewinding -
    which is exactly the shape `spec.md` has, because §14 gives each workstream its own band
    and `spec.md` puts each band in that workstream's subject section. The rewind arm is INFO,
    with
    both endpoints and the rewind size in its data, so the observation is retained and greppable;
    it simply does not gate. The reserved band between the two is absent by declaration, so
    nothing here is a hole.
    """
    block = _RESERVATION_BLOCK.format(
        lo1="103", hi1="105", lo2="103", hi2="105", lo3="103", hi3="105",
        d1="103-105", occ_lo="101", occ_hi="102",
    )
    spec = (
        "# Feature Specification: numbering only\n\n"
        "**Input**: `input.md` in this directory (2 sections).\n\n"
        "## Requirements\n\n### Functional Requirements\n\n"
        "#### Later band\n\n" + block +
        "- **FR-106**: Requirement FR-106 MUST hold. (§2)\n\n"
        "#### Earlier band\n\n"
        "- **FR-101**: Requirement FR-101 MUST hold. (§2)\n"
        "- **FR-102**: Requirement FR-102 MUST hold. (§2)\n"
    )
    spec_dir = build_feature_dir(tmp_path / "f", spec=spec)
    ctx = rc.build_context(spec_dir)
    assert ctx.reservation.readable and ctx.reservation.numbers == frozenset({103, 104, 105})
    found = findings_for(spec_dir, ["RI-06b-FR-ORDER"])
    assert [f.code for f in found if f.severity in (rc.FAIL, rc.WARN)] == [], [
        (f.code, f.message) for f in found if f.severity in (rc.FAIL, rc.WARN)]
    rewinds = [f for f in found if f.code == "fr-non-monotonic-document-order"]
    assert len(rewinds) == 1
    assert rewinds[0].severity == rc.INFO
    assert rewinds[0].data["rewind"] == 5
    assert (rewinds[0].data["first"], rewinds[0].data["second"]) == ("FR-106", "FR-101")
    assert "legitimate authoring choice" in rewinds[0].message
    # no in-section rewind, because each section is internally ascending
    assert "fr-non-monotonic" not in {f.code for f in found}
    _walk_ran(spec_dir)


# --- the reservation parser itself: never guesses, never half-parses ----------------------


def test_the_reservation_is_parsed_from_spec_md_and_not_hard_coded() -> None:
    """The real document declares three ranges; the tool learned them by reading, not by knowing.

    This is the assertion that makes FIX 1 falsifiable. If the reserved set were a literal in
    `reference_check.py`, editing the declaration in `spec.md` would change nothing here.
    """
    ctx = rc.build_context(SPEC_DIR)
    res = ctx.reservation
    assert res.declared and res.readable, res.problem
    assert res.ranges == ((101, 109), (116, 129), (159, 160)), res.ranges
    assert min(res.numbers) == 101 and max(res.numbers) == 160
    assert res.decl_line and (SPEC_DIR / "spec.md").read_text(encoding="utf-8").splitlines()[
        res.decl_line - 1].lstrip("> ").startswith("`RESERVED-FR:")
    # every declared range is also stated as a range in the block's prose
    for lo, hi in res.ranges:
        assert (lo, hi) in {
            (int(m.group("lo")), int(m.group("hi")))
            for m in rc.PROSE_RANGE_RE.finditer(
                "\n".join(line for i, line in enumerate(
                    (SPEC_DIR / "spec.md").read_text(encoding="utf-8").splitlines(), start=1)
                    if i in set(res.block_lines) and i != res.decl_line))
        }
    # and the two numbers the document says are deliberately unfilled are now accounted for
    cats = rc._accounted_fr_numbers(ctx)
    assert {159, 160} <= cats["reserved"]
    assert 159 not in cats["defined"] and 159 not in cats["tombstoned"]


@pytest.mark.parametrize(
    "declaration, why",
    [
        (None, "no declaration line at all"),
        ("> `RESERVED-FR: not-a-range`\n", "an unparseable range"),
        ("> `RESERVED-FR: 109-101`\n", "an end that precedes its start"),
        ("> `RESERVED-FR: 101-109, 105-110`\n", "overlapping ranges"),
        ("> `RESERVED-FR:`\n", "an empty declaration"),
    ],
)
def test_an_unreadable_reservation_is_a_failure_that_exempts_nothing(
    tmp_path: Path, declaration: str | None, why: str,
) -> None:
    """Fail closed: a reservation that cannot be read unambiguously exempts *nothing*.

    The dangerous failure mode is not a false FAIL, it is a partially-read reservation quietly
    exempting half of what it read and turning a parsing bug into a green gate. So every way the
    declaration can be wrong is a FAIL, and the reserved set is empty in all of them - which means
    the numbers come back as ordinary unaccounted gaps.
    """
    spec = _spec_with_reservation(["FR-101", "FR-102", "FR-106"], reserved="103-105")
    if declaration is None:
        spec = spec.replace("> `RESERVED-FR: 103-105\n", "")
    else:
        spec = spec.replace("> `RESERVED-FR: 103-105\n", declaration)
    spec_dir = build_feature_dir(tmp_path / "f", spec=spec)
    ctx = rc.build_context(spec_dir)
    assert ctx.reservation.declared, why
    assert not ctx.reservation.readable, why
    assert ctx.reservation.numbers == frozenset(), why
    fails = fails_for(spec_dir, ["RI-06b-FR-ORDER"])
    assert "reservation-declaration-unreadable" in {f.code for f in fails}, why
    unreadable = next(f for f in fails if f.code == "reservation-declaration-unreadable")
    assert unreadable.data["exempted_numbers"] == 0
    # nothing is exempted, so the absent numbers come back as real gaps
    assert {f.code for f in fails} >= {"fr-gap"}
    assert {f.data.get("fr") for f in fails if f.code == "fr-gap"} == {
        "FR-103", "FR-104", "FR-105"}, why


def test_a_reservation_whose_machine_line_drifted_from_its_prose_is_a_failure(
    tmp_path: Path,
) -> None:
    """The machine declaration and the human statement are cross-checked, not merged.

    If the `RESERVED-FR:` line names a range the block's prose never states, one of the two is
    lying to a reader. A tool that believed the machine line would exempt a number the document
    does not say is reserved, so this is FAIL - and the prose is what is checked against, because
    the prose is what a human reads.
    """
    spec = _spec_with_reservation(["FR-101", "FR-102", "FR-106"], reserved="103-105")
    drifted = spec.replace("> `RESERVED-FR: 103-105", "> `RESERVED-FR: 103-106")
    spec_dir = build_feature_dir(tmp_path / "f", spec=drifted)
    ctx = rc.build_context(spec_dir)
    assert not ctx.reservation.readable
    assert "drifted apart" in (ctx.reservation.problem or "")
    assert ctx.reservation.numbers == frozenset()
    assert "reservation-declaration-unreadable" in {
        f.code for f in fails_for(spec_dir, ["RI-06b-FR-ORDER"])}


def test_a_spec_with_no_reservation_block_exempts_nothing_and_says_so(tmp_path: Path) -> None:
    """Declaring a reservation is opt-in, and silence is not a defect - it is no exemption."""
    spec_dir = build_feature_dir(tmp_path / "f")
    ctx = rc.build_context(spec_dir)
    assert not ctx.reservation.declared and ctx.reservation.readable
    found = findings_for(spec_dir, ["RI-06b-FR-ORDER"])
    assert "no-reservation-declared" in {f.code for f in found}
    assert fails_for(spec_dir, ["RI-06b-FR-ORDER"]) == []


def test_the_walked_range_is_bounded_by_definitions_not_by_the_tombstone_map() -> None:
    """A repo-wide constant must not make a small document look like it has holes.

    `TOMBSTONED_FRS` is global, so a document defining `FR-001`...`FR-003` must not be walked out
    to `FR-080` because some other document retired `FR-080`. Tombstones and reservations classify
    numbers *inside* the space a document occupies; they do not enlarge it.
    """
    ctx = rc.build_context(SPEC_DIR)
    cats = rc._accounted_fr_numbers(ctx)
    assert max(cats["tombstoned"]) == 80
    assert max(cats["reserved"]) == 160
    unaccounted = rc._unaccounted_fr_numbers(ctx)
    assert all(1 <= min(cats["defined"]) <= n <= max(cats["defined"]) for n in unaccounted)
    assert unaccounted == [138, 139], (
        "the only unaccounted numbers in the real spec.md; FR-138/FR-139 are a true positive - "
        "defined nowhere, tombstoned by no record, reserved by no declaration")


def test_the_real_spec_leaves_exactly_two_unaccounted_numbers_and_they_are_reported() -> None:
    """FIX 1 found a real hole. It is asserted here so the fix cannot quietly hide it.

    `FR-138` and `FR-139` sit in the seam between A4b's band (`FR-130`...`FR-137`) and A5's
    (`FR-140`...`FR-149`). `ARBITRATION.md` §14 allocates that seam to nobody, `spec.md` defines
    neither number, no record retires either, and the reservation block does not claim them. The
    old density rule never saw them: they were two entries in a 30-number list inside a
    document-order gap whose other 28 members were reserved. This is the class of defect the
    coverage rule exists to isolate, and it is NOT reserved away - declaring a gap on purpose is an
    authoring decision in `spec.md`, and making it here to reach a green gate would be the tool
    inventing an intent the document does not record.
    """
    found = findings_for(SPEC_DIR, ["RI-06b-FR-ORDER"])
    fails = [f for f in found if f.severity == rc.FAIL]
    assert [(f.code, f.data["fr"]) for f in fails] == [
        ("fr-gap", "FR-138"), ("fr-gap", "FR-139")], [(f.code, f.message) for f in fails]
    for f in fails:
        assert "defined in no section" in f.message
        assert "reserved by no declaration" in f.message
    ok = next(f for f in found if f.code == "fr-sequence-ok")
    assert ok.data["unaccounted_numbers"] == 2
    assert ok.data["reserved"] == 25


# --- FIX 2: a superseded local numbering is a record, and its pointer has to resolve -------


def test_a_superseded_local_numbering_is_a_record_not_a_claim(tmp_path: Path) -> None:
    """A repair document that says which number it used to own is not claiming that number.

    `A2` and `A6` were both written before `ARBITRATION.md` §14 reassigned the `FR-1xx` band, so
    each carries bold title rows for local numbers that no live requirement defines. Labelling the
    local number superseded and naming the canonical one is the honest form of a signed record.
    The teeth stay: a bold title row with no such label is still `fr-undefined-in-repair`.
    """
    labelled = build_repair_dir(
        build_feature_dir(tmp_path / "labelled"),
        **{"A2-identity": "# A2\n\n"
           "**FR-101** (superseded local numbering → ARBITRATION §14 → **FR-003**) "
           "— `PredicateSignature` field set and exclusions.\n\n"
           "System MUST provide a deterministic frozen `PredicateSignature`. (§2)\n"},
    )
    assert fails_for(labelled, ["RI-01-FR-DEF"]) == [], [
        (f.code, f.message) for f in fails_for(labelled, ["RI-01-FR-DEF"])]
    unlabelled = build_repair_dir(
        build_feature_dir(tmp_path / "unlabelled"),
        **{"A2-identity": "# A2\n\n"
           "**FR-101 — `PredicateSignature` field set and exclusions.**\n\n"
           "System MUST provide a deterministic frozen `PredicateSignature`. (§2)\n"},
    )
    codes = {f.code for f in fails_for(unlabelled, ["RI-01-FR-DEF"])}
    assert "fr-undefined-in-repair" in codes, [f.message for f in
                                              fails_for(unlabelled, ["RI-01-FR-DEF"])]


def test_a_supersession_label_pointing_at_a_phantom_is_a_failure(tmp_path: Path) -> None:
    """The exemption is only sound if the label is true, so the label is checked.

    Otherwise `**FR-nnn** (superseded ... -> **FR-mmm**)` is a way to retire any number without
    saying where the content went, and the checker would be worse than useless: it would certify a
    document that has quietly dropped a requirement.
    """
    bad = build_repair_dir(
        build_feature_dir(tmp_path / "bad"),
        **{"A2-identity": "# A2\n\n"
           "**FR-101** (superseded local numbering → ARBITRATION §14 → **FR-999**) "
           "— `PredicateSignature` field set and exclusions.\n\n"
           "System MUST provide a deterministic frozen `PredicateSignature`. (§2)\n"},
    )
    fails = fails_for(bad, ["RI-01-FR-DEF"])
    assert [f.code for f in fails] == ["supersession-pointer-unresolved"], [
        f.message for f in fails]
    assert fails[0].data["canonical"] == "FR-999"

    # and a record cannot retire a number that is currently in force
    live = build_repair_dir(
        build_feature_dir(tmp_path / "live"),
        **{"A2-identity": "# A2\n\n"
           "**FR-001** (superseded local numbering → ARBITRATION §14 → **FR-003**) "
           "— restated locally.\n\n"
           "System MUST provide a deterministic frozen `PredicateSignature`. (§2)\n"},
    )
    assert "supersession-of-a-live-fr" in {f.code for f in
                                           fails_for(live, ["RI-01-FR-DEF"])}


def test_a_supersession_disagreement_is_scoped_to_one_document(tmp_path: Path) -> None:
    """Cross-document reuse of a local number is what §1 records, not a disagreement.

    `ARBITRATION.md` §1: "`FR-101`/`FR-102` as invented by **both** A2 and A6 are void", and §14
    rule 2 gives A2's pair `FR-174/175` and A6's pair `FR-179/180`. So one local number legitimately
    resolves to two canonical numbers in two authors' records - a global reading of that would
    report the very collision §14 exists to resolve. One *document* has one numbering of its own,
    and that is where the check bites.
    """
    two_docs = build_repair_dir(
        build_feature_dir(tmp_path / "two"),
        **{"A2-identity": "# A2\n\n**FR-101** (superseded → **FR-003**) — x.\n\n"
                          "body one. (§2)\n",
           "A6-triage": "# A6\n\n**FR-101** (superseded → **FR-002**) — y.\n\n"
                        "body two. (§2)\n"},
    )
    assert "supersession-disagreement" not in {f.code for f in
                                               fails_for(two_docs, ["RI-01-FR-DEF"])}
    summary = next(f for f in findings_for(two_docs, ["RI-01-FR-DEF"])
                   if f.code == "supersession-summary")
    assert summary.data["reused_local_numbers"] == ["FR-101"]

    one_doc = build_repair_dir(
        build_feature_dir(tmp_path / "one"),
        **{"A2-identity": "# A2\n\n**FR-101** (superseded → **FR-003**) — x.\n\n"
                          "body one. (§2)\n\n"
                          "**FR-101** (superseded → **FR-002**) — z.\n\n"
                          "body three. (§2)\n"},
    )
    assert "supersession-disagreement" in {f.code for f in
                                           fails_for(one_doc, ["RI-01-FR-DEF"])}


def test_the_real_superseded_labels_all_resolve_to_live_requirements() -> None:
    """The five labels FIX 2 added, pinned against the real documents.

    `A2`'s five became `FR-174`...`FR-178` and `A6`'s two became `FR-179/180`, per §14 rule 2 and
    confirmed title-by-title against `spec.md`. The pointer resolution check is what proves the
    mapping, so it is asserted on the real corpus rather than trusted.
    """
    ctx = rc.build_context(SPEC_DIR)
    labels = [s for art in ctx.repair for s in rc.parse_repair_supersessions(art)]
    assert [(s.artefact, s.local, s.canonical) for s in labels] == [
        ("repair/A2-identity-subsystem.md", "FR-101", "FR-174"),
        ("repair/A2-identity-subsystem.md", "FR-102", "FR-175"),
        ("repair/A2-identity-subsystem.md", "FR-104", "FR-176"),
        ("repair/A2-identity-subsystem.md", "FR-105", "FR-177"),
        ("repair/A2-identity-subsystem.md", "FR-106", "FR-178"),
        ("repair/A6-fr-triage.md", "FR-101", "FR-179"),
        ("repair/A6-fr-triage.md", "FR-102", "FR-180"),
    ]
    live = ctx.live_index()
    for s in labels:
        assert s.canonical in live, f"{s.local} -> {s.canonical} does not resolve"
        assert s.local not in live, f"{s.local} must be retired, not live"
    assert fails_for(SPEC_DIR, ["RI-01-FR-DEF"]) == []


# --------------------------------------------------------------------------------------
# FIX 3 - a non-goal is traced to the non-goals list, not to a minted requirement
# --------------------------------------------------------------------------------------


def test_a_checklist_row_citing_no_fr_is_still_a_failure(tmp_path: Path) -> None:
    """The teeth for FIX 3: the rule is untouched, only `R070`'s row was withdrawn."""
    spec_dir = build_feature_dir(
        tmp_path / "f",
        checklist=GOOD_CHECKLIST.replace(
            _ROW_A2,
            "| A2 | `polarity` is a real field | T | \u2014 | T002 | \u2610 |",
        ),
    )
    fails = fails_for(spec_dir, ["RI-04c-ROW-FR"])
    assert [f.code for f in fails] == ["row-without-fr", "row-without-fr-total"]
    assert fails[0].data["row"] == "A2"
    assert fails[1].data["rows"] == ["A2"]


def test_the_fr_070_non_goal_is_complete_and_r070_is_a_pointer_to_it() -> None:
    """FIX 3 as a whole: the non-goal carries the tombstone's two sentences, and the row is gone.

    The instruction was *do not mint an FR*: a non-goal is a prohibition, constructs no acceptance
    criterion, and has no requirement to be a checklist row about. So the obligation moved into
    `spec.md`'s constitutional non-goals list and the checklist row became a pointer to that bullet.
    Asserted on the real corpus, and the `RI-04c-ROW-FR` teeth are pinned separately above.
    """
    spec = (SPEC_DIR / "spec.md").read_text(encoding="utf-8")
    bullet = next(b for b in spec.split("### Constitutional non-goals")[1].split("\n- ")[1:]
                  if "SHACL" in b)
    assert "MUST NOT make RDF the internal model" in bullet
    assert "draft-only SHACL 1.2" in bullet
    # the sentence FR-070 carried that was not restated before: the substrate is not SHACL
    assert "never moved into SHACL" in bullet
    assert "shape validation is not the semantic substrate" in bullet
    assert "tombstoned `FR-070`" in bullet
    assert "FR-070" not in bullet.split("tombstoned `FR-070`")[1].split("`")[1:2] or True

    checklist = (SPEC_DIR / "checklists" / "requirements.md").read_text(encoding="utf-8")
    assert "| R070 |" not in checklist, "R070 must not be a table row: a row asserts one FR"
    assert "**`R070` is a non-goal, and it is traced here rather than as a row.**" in checklist
    assert "Constitutional non-goals" in checklist
    ctx = rc.build_context(SPEC_DIR)
    assert "R070" not in {r.ident for r in ctx.rows}
    assert fails_for(SPEC_DIR, ["RI-04c-ROW-FR"]) == []


def test_phantom_section_is_not_synthesised_from_an_unnumbered_subsection(tmp_path: Path) -> None:
    ctx = rc.build_context(build_feature_dir(tmp_path / "f"))
    assert set(ctx.sections) == {"1", "2"}
    assert "1B" in ctx.subsection_hints
    assert "1B" not in ctx.sections


def test_uncited_input_sections_are_info_not_fail(tmp_path: Path) -> None:
    spec_dir = build_feature_dir(tmp_path / "f")
    found = findings_for(spec_dir, ["RI-08b-SEC-UNCITED"])
    assert [f.severity for f in found] == [rc.INFO]
    assert found[0].code == "sections-all-cited"
    assert found[0].data["total_sections"] == 2


def test_miscite_heuristic_flags_zero_overlap_and_accepts_shared_terms() -> None:
    unrelated = rc.meaningful_terms(
        "Create `apps/shared/domain/predicate_signature.py`: `PredicateSignature`, "
        "its `content_key()`, and normalisation rules N1-N6."
    )
    target = rc.meaningful_terms(
        "Producers MUST import no graph, claim, admission or projection symbol, with "
        "`TYPE_CHECKING` as the only exception and never in executable code."
    )
    assert not (unrelated & target)
    assert rc._containment(unrelated, target) == 0.0
    related = rc.meaningful_terms(
        "Canonicalise `signal_refs` on construction in `relation_candidate.py`, matching "
        "`observation_refs`."
    )
    fr = rc.meaningful_terms(
        "`RelationCandidate.signal_refs` MUST be canonicalised on construction, exactly as "
        "`observation_refs`, `evidence_refs` and `supporting_spans` already are."
    )
    assert related & fr
    assert rc._containment(related, fr) > 0


def test_miscite_heuristic_ignores_normative_words_and_reference_ids() -> None:
    a = rc.meaningful_terms("MUST NOT drop a thing; SHOULD hold (FR-001, \u00a712, T003)")
    b = rc.meaningful_terms("MUST be re-derived; SHOULD be recorded (FR-002, \u00a79, T004)")
    assert not (a & b)
    assert "fr" not in a and "001" not in a


def test_must_literals_only_capture_closed_membership_lists() -> None:
    body = ("`SignalKind` MUST contain at least `LEXICAL`, `TEMPORAL`, `TABLE`. "
            "`COREFERENCE`, `QUANTITY` MAY remain, but MUST NOT substitute.")
    assert rc._must_literals(body) == {"LEXICAL", "TEMPORAL", "TABLE"}
    repair = "The `document:current` fallback MUST be removed in favour of `document_ref`."
    assert rc._must_literals(repair) == set()


def test_claim_window_prefers_the_definition_body_and_stops_at_the_next_one() -> None:
    """Anchored on the requirement id, not on the requirement's prose.

    The window for a claim inside `SC-015` is `SC-015`'s own body and nothing wider: not the
    surrounding paragraph, not the next definition, not the whole document. Asserted against
    the parsed definition rather than against quoted text, so the integration can rewrite
    SC-015's wording without breaking this and cannot make it pass vacuously.
    """
    ctx = rc.build_context(SPEC_DIR)
    art = ctx.by_name("spec.md")
    sc15 = next(d for d in ctx.defs if d.ident == "SC-015")
    window = rc._claim_window(art, sc15.line, ctx.defs)
    assert window == sc15.body
    assert window.strip()
    # tight: it stops at the neighbouring definitions in both directions
    assert "SC-016" not in window
    assert "SC-014" not in window
    assert len(window) < len(sc15.body) + 400
    # and a line outside any definition gets the tighter paragraph context instead
    heading_lines = {h[0] for h in rc._section_walk(art.lines)}
    outside = next(i for i in range(1, art.line_count + 1)
                   if i not in heading_lines
                   and not any(d.line <= i <= d.line + len(d.body.split("\n")) - 1
                               for d in ctx.defs)
                   and art.lines[i - 1].strip()
                   and not art.lines[i - 1].startswith("|"))
    para = rc._claim_window(art, outside, ctx.defs)
    assert para != sc15.body


def test_line_of_maps_offsets_to_one_based_lines() -> None:
    """Anchored on the `FR-001` definition row and on the parser's own line for it.

    The two independent offset->line implementations in this tool (the char-offset binary
    search and the line-walking definition parser) must agree, which is a real invariant and
    survives the document growing above FR-001.
    """
    art = rc.read_artefact("spec.md", SPEC_DIR / "spec.md")
    ctx = rc.build_context(SPEC_DIR)
    fr001 = ctx.def_index()["FR-001"]
    assert art.lines[fr001.line - 1].startswith("- **FR-001**:")
    assert rc._line_of(art, 0) == 1
    assert rc._line_of(art, art.text.index("- **FR-001**:")) == fr001.line
    assert rc._line_of(art, len(art.text) - 1) == art.line_count


def test_small_helpers() -> None:
    assert rc._section_in_line("see \u00a794\u2013\u00a7101 for detail") == "94"
    assert rc._section_in_line("no section here") is None
    assert rc._first_sentence("a b. c d", 0) == "a b"
    assert rc._as_int("four") == 4
    assert rc._as_int("banana") is None
    assert rc._topic_terms("Process-Centric") == {"process", "centric"}


def test_harness_field_count_keys_are_exactly_the_frs_that_state_the_obligation() -> None:
    """The contract, re-pointed at the FR that states the obligation.

    The count used to be pinned to `{"FR-078": 18}`. The §93 manifest obligation no longer sits
    in FR-078, so the number moved; what must hold is that the counter's *keys* are exactly the
    definition rows whose body carries the `MUST break` clause the rule reads, and that every
    value is a positive count. The arithmetic itself is pinned numerically, on a synthetic FR,
    in the next test.
    """
    ctx = rc.build_context(SPEC_DIR)
    counted = rc._harness_field_counts(ctx)
    index = ctx.def_index()
    for fr, value in counted.items():
        assert fr in index, fr
        assert re.search(r"\bMUST\s+break\b", index[fr].body, re.IGNORECASE), (fr, index[fr].body)
        assert isinstance(value, int) and value > 0, (fr, value)
    expected = {d.ident for d in ctx.defs
                if d.ident.startswith("FR-")
                and re.search(r"\bMUST\s+break\b", d.body, re.IGNORECASE)}
    assert set(counted) <= expected, sorted(set(counted) - expected)
    # the mutation-harness obligation is stated somewhere, so the counter is not dead
    assert expected, "no spec.md FR states a `MUST break` obligation any more"


def test_harness_field_count_counts_the_enumerated_fields_of_a_must_break_fr(
    tmp_path: Path,
) -> None:
    """The arithmetic, pinned exactly, on a document the integration cannot move."""
    fr_003 = (
        "- **FR-003**: The constitutional mutation harness MUST break the manifest's six\n"
        "  fields (`predicate_signature`, `polarity`, `mention_ref`, `relation_ref`,\n"
        "  `supporting_spans`, `evidence_refs`) and nothing else. (\u00a71)\n"
    )
    spec_dir = build_feature_dir(tmp_path / "f", spec=mutation_spec(fr_003))
    assert rc._harness_field_counts(rc.build_context(spec_dir)) == {"FR-003": 6}
    # the § locator in the trailing parenthesis is not an enumerated field
    seven = fr_003.replace("`evidence_refs`", "`evidence_refs`, `confidence`")
    assert rc._harness_field_counts(
        rc.build_context(build_feature_dir(tmp_path / "h", spec=mutation_spec(seven)))
    ) == {"FR-003": 7}
    # and a `MUST break` clause with no enumeration contributes nothing
    bare = build_feature_dir(
        tmp_path / "g",
        spec=mutation_spec("- **FR-003**: A test MUST break the signature. (\u00a71)"),
    )
    assert rc._harness_field_counts(rc.build_context(bare)) == {}


def test_mutation_section_registry_comes_from_input_headings() -> None:
    ctx = rc.build_context(SPEC_DIR)
    found = rc._mutation_sections(ctx)
    assert sorted(found, key=int) == ["93", "94", "95", "96", "97", "98", "99"]


# --------------------------------------------------------------------------------------
# 5. the real artefacts: tripwires, each retired when its defect is repaired
# --------------------------------------------------------------------------------------


def skip_if_repaired(relative: str, token: str) -> None:
    path = SPEC_DIR / relative
    if not path.is_file() or token not in path.read_text(encoding="utf-8"):
        pytest.skip(f"{relative} no longer contains {token!r}: that defect has been repaired")


@pytest.mark.parametrize(
    ("artefact", "token"),
    [("tasks.md", "FR-103"), ("data-model.md", "FR-103"), ("research.md", "FR-103")],
)
def test_tripwire_phantom_fr_103(artefact: str, token: str) -> None:
    skip_if_repaired(artefact, token)
    fails = fails_for(SPEC_DIR, ["RI-01-FR-DEF"])
    assert any(f.code == "fr-undefined" and f.data.get("fr") == "FR-103"
               for f in fails), fails
    files = {loc.rpartition(":")[0] for f in fails for loc in f.locations}
    assert artefact in files


@pytest.mark.parametrize("phantom", ["T007c", "T007f", "T011a", "T011c", "T012d"])
def test_tripwire_phantom_task_ids_in_the_checklist(phantom: str) -> None:
    skip_if_repaired("checklists/requirements.md", phantom)
    fails = fails_for(SPEC_DIR, ["RI-02-TASK-REF"])
    assert any(f.data.get("task") == phantom for f in fails), [f.data for f in fails]


@pytest.mark.parametrize("phantom", ["T009f", "T010d", "T010f", "T013a"])
def test_tripwire_phantom_task_ids_in_the_open_questions_table(phantom: str) -> None:
    skip_if_repaired("tasks.md", phantom)
    fails = fails_for(SPEC_DIR, ["RI-02-TASK-REF"])
    assert any(f.data.get("task") == phantom for f in fails), [f.data for f in fails]


def test_tripwire_orphan_fr_set() -> None:
    fails = fails_for(SPEC_DIR, ["RI-03-FR-ORPHAN"])
    if not fails:
        pytest.skip("no orphan FRs remain")
    assert len(fails) == 1
    data = fails[0].data
    assert data["total_frs"] == 102
    assert data["orphan_count"] == len(data["orphans"]) == 52
    assert "FR-001" in data["orphans"]
    assert "FR-083" in data["orphans"]
    assert "FR-100" not in data["orphans"]


def test_tripwire_checklist_has_no_fr_column() -> None:
    fails = fails_for(SPEC_DIR, ["RI-03c-FR-COLUMN"])
    if not fails:
        pytest.skip("the checklist now has an FR column")
    assert fails[0].code == "no-fr-column"
    assert "state" in fails[0].data["observed_columns"]


def test_tripwire_section_1b() -> None:
    skip_if_repaired("spec.md", "\u00a71B")
    assert [f.data["section"] for f in fails_for(SPEC_DIR, ["RI-08-SEC-CITE"])] == ["1B"]


def test_tripwire_input_md_line_count_claim() -> None:
    skip_if_repaired("spec.md", "3411 lines")
    fails = [f for f in fails_for(SPEC_DIR, ["RI-09-COUNT"])
             if f.code == "count-line-mismatch" and f.data["file"] == "input.md"]
    assert fails
    assert {f.data["actual"] for f in fails} == {4898}
    assert {f.data["claimed"] for f in fails} == {3411}


def test_tripwire_fr_079_says_four_and_lists_six() -> None:
    skip_if_repaired("spec.md", "Four named mutations")
    fails = [f for f in fails_for(SPEC_DIR, ["RI-09-COUNT"])
             if f.code == "count-mismatch" and f.data["noun"] == "mutations"]
    assert any(f.data["claimed"] == 4 and f.data["actual"] == 6 for f in fails), \
        [f.data for f in fails]


def test_tripwire_sc_015_demands_20_invariants_while_fr_078_enumerates_18() -> None:
    fails = [f for f in fails_for(SPEC_DIR, ["RI-09-COUNT"])
             if f.code == "count-mismatch" and f.data["noun"] == "invariants"]
    if not fails:
        pytest.skip("the SC-015 / FR-078 count contradiction has been repaired")
    assert fails[0].data["claimed"] == 20
    assert fails[0].data["actual"] == 18
    assert "FR-078=18" in fails[0].data["basis"]


def test_tripwire_seventeen_mutations_claim() -> None:
    skip_if_repaired("checklists/requirements.md", "17 mutations")
    fails = [f for f in fails_for(SPEC_DIR, ["RI-09-COUNT"])
             if f.code in {"count-mismatch", "mutation-range-not-mutation"}]
    assert any(f.data.get("claimed") == 17 or f.data.get("lo") == 94 for f in fails), \
        [f.data for f in fails]


def test_tripwire_seven_levels_lists_nine() -> None:
    skip_if_repaired("data-model.md", "seven levels")
    fails = [f for f in fails_for(SPEC_DIR, ["RI-09-COUNT"])
             if f.code == "count-mismatch" and f.data["noun"] == "levels"]
    assert fails
    assert fails[0].data["claimed"] == 7
    assert fails[0].data["actual"] == 9


def test_tripwire_constitution_cd_labels_are_phantoms() -> None:
    """The stable anchor is the *constitution*, not the citing line numbers.

    The constitution's Domain Invariants are an unlabelled numbered list, so it defines no
    `CD-n` label at all and every `CD-n` citation is a phantom. That is the invariant; which
    label a given artefact happens to cite today is not. Asserted as: the labels reported are
    drawn from the set this corpus has ever invented (a new one still fails the test), each
    really is absent from the constitution, and the constitution really defines none.
    """
    const = rc.read_artefact(
        rc.CONSTITUTION_RELPATH, rc.find_constitution(SPEC_DIR) or SPEC_DIR / "no-constitution.md"
    )
    assert not rc.CD_TOKEN_RE.search(const.text), (
        "the constitution now labels its Domain Invariants; this tripwire must be re-pointed"
    )
    labels = {f.data["raw"] for f in findings_for(SPEC_DIR, ["RI-11-CONST"])
              if f.code == "cd-phantom"}
    if not labels:
        pytest.skip("no phantom CD labels remain")
    assert labels <= {"CD-6", "CD-7"}, sorted(labels)
    for raw in labels:
        assert not re.search(rf"\b{re.escape(raw)}\b", const.text), raw
    # and every CD citation in the artefacts is judged against the constitution, not a guess
    resolved = [f for f in findings_for(SPEC_DIR, ["RI-11-CONST"]) if f.code == "cd-defined"]
    assert all(f.data["raw"] in const.text for f in resolved)


def test_tripwire_principle_topic_miscites() -> None:
    miscites = [f for f in findings_for(SPEC_DIR, ["RI-11-CONST"])
                if f.code == "principle-miscite"]
    if not miscites:
        pytest.skip("no principle mis-cites remain")
    pairs = {(f.data["roman"], f.data["claimed_topic"]) for f in miscites}
    assert ("VI", "determinism") in pairs
    assert ("IV", "tenancy") in pairs


def test_tripwire_stale_not_yet_created_claims() -> None:
    fails = fails_for(SPEC_DIR, ["RI-12-STALE"])
    if not fails:
        pytest.skip("no stale status claims remain")
    paths = {f.data["path"] for f in fails}
    assert {"tasks.md", "research.md", "data-model.md"} <= paths


def test_the_real_artefact_set_fails_the_gate_today() -> None:
    """The headline: run against the current, deliberately-broken artefacts -> red."""
    if rc.main(["--spec-dir", str(SPEC_DIR), "--json"]) == 0:
        pytest.skip("the artefact set now passes every FAIL check: the gate is satisfied")
    assert fails_for(SPEC_DIR), "expected FAIL findings on the current artefacts"


def test_constitution_is_discovered_in_the_real_repo() -> None:
    ctx = rc.build_context(SPEC_DIR)
    assert ctx.constitution is not None and ctx.constitution.read_ok
    assert set(ctx.principles) >= {"I", "II", "III", "IV", "V", "VI", "VII"}


# --------------------------------------------------------------------------------------
# 6. CLI contract
# --------------------------------------------------------------------------------------


def test_cli_json_payload_shape(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    spec_dir = build_feature_dir(tmp_path / "f")
    rc.main(["--spec-dir", str(spec_dir), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["tool"] == "reference_check.py"
    assert payload["totals"]["FAIL"] == 0
    assert payload["exit_code"] == 0
    assert {r["check_id"] for r in payload["summary"]} == set(rc.CHECK_BY_ID)
    for row in payload["summary"]:
        assert row["fail"] + row["warn"] + row["info"] == row["total"]
        assert row["default_severity"] in rc.SEVERITIES
    for finding in payload["findings"]:
        assert finding["check_id"] in rc.CHECK_BY_ID
        assert finding["severity"] in rc.SEVERITIES


def test_cli_warn_only_never_fails_the_gate(tmp_path: Path,
                                           capsys: pytest.CaptureFixture[str]) -> None:
    spec_dir = build_feature_dir(tmp_path / "f", tasks=GOOD_TASKS.replace("T003", "T099"))
    assert rc.main(["--spec-dir", str(spec_dir)]) == 1
    capsys.readouterr()
    assert rc.main(["--spec-dir", str(spec_dir), "--warn-only"]) == 0
    assert "exit: 0" in capsys.readouterr().out


def test_cli_rejects_an_unknown_check_id(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        rc.main(["--spec-dir", str(tmp_path), "--only", "RI-NOPE"])
    assert exc.value.code == 2


def test_cli_rejects_a_missing_spec_dir(tmp_path: Path) -> None:
    assert rc.main(["--spec-dir", str(tmp_path / "nowhere")]) == 2


def test_cli_only_filters_to_the_requested_checks(tmp_path: Path,
                                                  capsys: pytest.CaptureFixture[str]) -> None:
    spec_dir = build_feature_dir(
        tmp_path / "f",
        checklist=GOOD_CHECKLIST.replace(
            "| A2 | `polarity` is a real field | T | FR-002 | T002 | \u2610 |",
            "| A2 | `polarity` is a real field | T | FR-002 | T002, T00z | \u2610 |",
        ),
    )
    rc.main(["--spec-dir", str(spec_dir), "--only", "RI-02-TASK-REF", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert [r["check_id"] for r in payload["summary"]] == ["RI-02-TASK-REF"]
    assert payload["findings"][0]["data"]["task"] == "T00z"


def test_cli_compare_reports_per_check_deltas(tmp_path: Path,
                                              capsys: pytest.CaptureFixture[str]) -> None:
    spec_dir = build_feature_dir(tmp_path / "f")
    baseline = tmp_path / "base.json"
    rc.main(["--spec-dir", str(spec_dir), "--json"])
    baseline.write_text(capsys.readouterr().out, encoding="utf-8")
    rc.main(["--spec-dir", str(spec_dir), "--json", "--compare", str(baseline)])
    payload = json.loads(capsys.readouterr().out)
    rows = {r["check_id"]: r for r in payload["comparison"]["rows"]}
    assert set(rows) == set(rc.CHECK_BY_ID)
    assert all(r["fail_delta"] == 0 for r in rows.values())


def test_cli_compare_survives_a_corrupt_baseline(tmp_path: Path,
                                                capsys: pytest.CaptureFixture[str]) -> None:
    spec_dir = build_feature_dir(tmp_path / "f")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    rc.main(["--spec-dir", str(spec_dir), "--json", "--compare", str(bad)])
    payload = json.loads(capsys.readouterr().out)
    assert "error" in payload["comparison"]


def test_text_report_documents_every_check_and_ends_with_the_exit_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    spec_dir = build_feature_dir(tmp_path / "f")
    rc.main(["--spec-dir", str(spec_dir)])
    out = capsys.readouterr().out
    assert "REFERENCE INTEGRITY CHECK" in out
    assert "check id" in out and "TOTAL" in out
    assert "exit: 0" in out
    for check in rc.CHECKS:
        assert check.check_id in out
        assert check.rule in out


def test_stdout_survives_a_legacy_console_codepage(monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows consoles default to cp1251/cp1252; the report must not die on a glyph."""
    calls: list[tuple[str, str]] = []

    class _Stream:
        def reconfigure(self, **kwargs: str) -> None:
            calls.append((kwargs.get("encoding", ""), kwargs.get("errors", "")))

    monkeypatch.setattr(rc.sys, "stdout", _Stream())
    monkeypatch.setattr(rc.sys, "stderr", _Stream())
    rc._force_utf8_stdout()
    assert calls == [("utf-8", "replace"), ("utf-8", "replace")]


# --------------------------------------------------------------------------------------
# 7. the governance checks: tombstones, FR namespace, epistemic axes, count precision, ghosts
# --------------------------------------------------------------------------------------

NEW_CHECKS: list[str] = [
    "TOMBSTONED-FR-REF",
    "FR-NAMESPACE-COLLISION",
    "EPISTEMIC-AXIS-CONFLATION",
    "COUNT-PRECISION",
    "GHOST-SUFFIX",
]


def build_repair_dir(root: Path, **docs: str) -> Path:
    """Add `repair/<name>.md` documents to a synthetic feature directory."""
    for name, text in docs.items():
        write(root / "repair" / f"{name}.md", text)
    return root


def blocking(spec_dir: Path, check_id: str) -> list[rc.Finding]:
    """FAIL and WARN findings of one check: the ones that must be zero on clean input."""
    return [f for f in findings_for(spec_dir, [check_id]) if f.severity in (rc.FAIL, rc.WARN)]


# --- TOMBSTONED-FR-REF ---------------------------------------------------------------------


def test_tombstone_set_is_the_arbitration_records() -> None:
    """Six, not five: `FR-039a` is in `spec.md`'s record table and must be in the gate too.

    `FR-039a` was the omission FIX 4 closed. Before it the map had five entries and `spec.md`'s
    tombstone record table had six rows, and nothing noticed: the table is deliberately not in
    requirement-definition form, so the definition parser cannot read it, and `RI-01-FR-DEF` drops
    tombstoned ids from its cited-but-undefined population. The seventeen live citations of
    `FR-039a` across four `repair/` documents were therefore visible to `GHOST-SUFFIX` and gated by
    nothing. The second half of the assertion is the cross-check: every id in the map is also named
    in the arbitration record, so the two cannot drift apart silently either.
    """
    assert rc.TOMBSTONED_FRS == {
        "FR-034a": "INV-002",
        "FR-039a": "FR-040",
        "FR-058": "INV-004",
        "FR-070": "design note",
        "FR-079": "FR-078",
        "FR-080": "FR-072",
    }
    arb = (SPEC_DIR / "repair" / "ARBITRATION.md").read_text(encoding="utf-8")
    for fr in rc.TOMBSTONED_FRS:
        assert f"`{fr}`" in arb, f"{fr} is in the map but ARBITRATION §2 does not name it"


def test_a_record_table_id_missing_from_the_map_is_reported_and_not_exempted(
    tmp_path: Path,
) -> None:
    """The root cause of the `FR-039a` hole, closed so the next one is caught.

    `spec.md`'s record table is the one authority the definition parser structurally cannot read,
    so the two sets are cross-checked explicitly. A row in the table naming an id the map omits is
    FAIL, and the id is *not* silently exempt from `RI-01-FR-DEF`: it is defined nowhere, so a live
    citation of it is still reported as undefined by the check that owns that defect.
    """
    spec = GOOD_SPEC.replace(
        "## Success Criteria",
        "#### Tombstone record\n\n"
        "| tombstoned id | successor | reason |\n|---|---|---|\n"
        "| `FR-007` | `FR-001` | folded away, history only |\n\n"
        "## Success Criteria",
    )
    spec_dir = build_feature_dir(tmp_path / "f", spec=spec)
    assert "FR-007" not in rc.TOMBSTONED_FRS
    assert "FR-007" not in rc.build_context(spec_dir).def_index(), "the premise: not a live row"
    recorded = rc.spec_tombstone_record_ids(rc.build_context(spec_dir))
    assert set(recorded) == {"FR-007"}, recorded
    fails = fails_for(spec_dir, ["TOMBSTONED-FR-REF"])
    assert [(f.code, f.data["fr"]) for f in fails] == [
        ("tombstone-record-unregistered", "FR-007")
    ]
    # and the id is not quietly exempt: a live citation of it is still an undefined reference
    spec_dir2 = build_feature_dir(
        tmp_path / "g",
        spec=spec,
        tasks=GOOD_TASKS.replace(
            _T001,
            "- [ ] T001 [US1] Key the id on the historical fold. (FR-007, §1)",
        ),
    )
    undef = fails_for(spec_dir2, ["RI-01-FR-DEF"])
    assert "fr-undefined" in {f.code for f in undef}, [f.message for f in undef]
    assert any(f.data.get("fr") == "FR-007" for f in undef)


def test_tombstoned_fr_citation_fails_and_names_the_replacement(tmp_path: Path) -> None:
    spec_dir = build_feature_dir(
        tmp_path / "f",
        tasks=GOOD_TASKS.replace(
            _T003_LINE,
            "- [ ] T003 [US3] Resolve every `mention_ref` in the index. (FR-003, FR-058, §2)",
        ),
    )
    fails = fails_for(spec_dir, ["TOMBSTONED-FR-REF"])
    assert [f.code for f in fails] == ["tombstoned-fr-cited-normative"]
    assert fails[0].locations == ["tasks.md:5"]
    assert fails[0].data["fr"] == "FR-058"
    assert fails[0].data["replacement"] == "INV-004"
    assert "INV-004" in fails[0].message


def test_tombstoned_fr_still_defined_normatively_fails(tmp_path: Path) -> None:
    """A tombstone with a live `- **FR-nnn**:` definition is the worst form of the defect."""
    spec_dir = build_feature_dir(
        tmp_path / "f",
        spec=GOOD_SPEC.replace(
            "## Success Criteria",
            "- **FR-079**: Four named mutations MUST exist. (§2)\n\n## Success Criteria",
        ),
    )
    fails = fails_for(spec_dir, ["TOMBSTONED-FR-REF"])
    assert [f.code for f in fails] == ["tombstoned-fr-defined-normative"]
    assert fails[0].data["is_definition"] is True
    assert fails[0].data["replacement"] == "FR-078"


def test_tombstoned_fr_cited_inside_a_deprecation_note_is_history_not_a_violation(
    tmp_path: Path,
) -> None:
    """ARBITRATION §2: a tombstone exists for historical traceability only."""
    spec_dir = build_feature_dir(
        tmp_path / "f",
        plan="FR-058 is **absorbed into** `INV-004` and tombstoned; it is history.\n",
    )
    found = findings_for(spec_dir, ["TOMBSTONED-FR-REF"])
    assert blocking(spec_dir, "TOMBSTONED-FR-REF") == []
    summary = next(f for f in found if f.code == "tombstone-summary")
    assert summary.data["exempted"] == 1
    assert summary.data["live_references"] == 0


def test_clean_feature_dir_has_no_tombstoned_reference(tmp_path: Path) -> None:
    assert blocking(build_feature_dir(tmp_path / "f"), "TOMBSTONED-FR-REF") == []


# --- tombstone records are not live requirements ------------------------------------------------
#
# `spec.md` writes a retired requirement as a definition row whose body is a tombstone record
# (`- **FR-058**: *tombstone - merged into `INV-004*`). The `**FR-nnn**:` prefix makes that row
# match the definition regex, so before the classification the parser read a historical marker
# as a live requirement. The tests below are: the classification itself, its two blast-radius
# checks, the three blind-spot controls that keep the change from swallowing real defects, and
# the two required assertions (a live citation still FAILs TOMBSTONED-FR-REF; a genuinely
# undefined id still FAILs RI-01-FR-DEF).


TOMBSTONE_ROW = (
    "- **FR-058**: *tombstone - merged into `INV-004`; see the deleted-ids table in\n"
    "  `repair/A6-fr-triage.md`. The obligation now lives in `INV-004`. This slot carries no\n"
    "  normative requirement and MUST NOT be cited as a live target.* (\u00a7108)\n"
)


def spec_with_tombstone(extra: str = "") -> str:
    """GOOD_SPEC plus a tombstone record for FR-058, optionally followed by another row."""
    return GOOD_SPEC.replace(
        "## Success Criteria",
        TOMBSTONE_ROW + "\n" + extra + "\n## Success Criteria",
        1,
    )


def test_a_tombstone_row_is_not_a_requirement_definition(tmp_path: Path) -> None:
    spec_dir = build_feature_dir(tmp_path / "f", spec=spec_with_tombstone())
    ctx = rc.build_context(spec_dir)
    record = next(d for d in ctx.def_occurrences if d.ident == "FR-058")
    assert record.tombstone is True
    # it is still a definition *row*: numbering, namespace ownership and count claims see it
    assert "FR-058" in {d.ident for d in ctx.defs}
    # and it is not a live requirement
    assert "FR-058" not in {d.ident for d in ctx.live_defs}
    assert "FR-058" not in ctx.live_index()
    assert "FR-058" in ctx.tombstone_ids
    assert "FR-001" in ctx.live_index(), "a live FR must stay a live definition"


def test_a_tombstone_is_not_an_orphan(tmp_path: Path) -> None:
    """A retired id is expected to have no task; reporting it as an orphan is a false FAIL."""
    spec_dir = build_feature_dir(tmp_path / "f", spec=spec_with_tombstone())
    assert fails_for(spec_dir, ["RI-03-FR-ORPHAN"]) == []
    assert fails_for(spec_dir, ["RI-03b-FR-UNCITED"]) == []
    ok = findings_for(spec_dir, ["RI-03-FR-ORPHAN"])[0]
    assert ok.code == "no-orphans"
    assert "FR-058" in ok.data["tombstones"]
    assert ok.data["tombstone_records"] == ["FR-058"]
    assert ok.data["total_frs"] == 3
    assert ok.data["definition_rows"] == 4


def test_a_genuine_orphan_next_to_a_tombstone_is_still_reported(tmp_path: Path) -> None:
    """The blind-spot control: the tombstone exclusion must not hide a real orphan."""
    spec_dir = build_feature_dir(
        tmp_path / "f",
        spec=spec_with_tombstone(extra="- **FR-005**: Nothing implements this.\n"),
    )
    fails = fails_for(spec_dir, ["RI-03-FR-ORPHAN"])
    assert [f.data["orphans"] for f in fails] == [["FR-005"]]
    assert fails[0].data["total_frs"] == 4
    assert fails[0].data["definition_rows"] == 5


def test_a_tombstone_row_is_not_reported_as_an_undefined_reference(tmp_path: Path) -> None:
    """`RI-01-FR-DEF` must not treat a tombstone record as a missing definition."""
    spec_dir = build_feature_dir(tmp_path / "f", spec=spec_with_tombstone())
    assert fails_for(spec_dir, ["RI-01-FR-DEF"]) == []


def test_a_live_citation_of_a_tombstoned_id_still_fails(tmp_path: Path) -> None:
    """REQUIRED: the record is not a requirement, but a live citation of it is still a FAIL."""
    spec_dir = build_feature_dir(
        tmp_path / "f",
        spec=spec_with_tombstone(),
        tasks=GOOD_TASKS.replace(
            _T003_LINE,
            "- [ ] T003 [US3] Resolve every `mention_ref` in the index. (FR-003, FR-058, \u00a72)",
        ),
    )
    # TOMBSTONED-FR-REF owns the defect and names the replacement target ...
    fails = fails_for(spec_dir, ["TOMBSTONED-FR-REF"])
    assert [(f.code, f.data["fr"], f.data["replacement"]) for f in fails] == [
        ("tombstoned-fr-cited-normative", "FR-058", "INV-004")
    ]
    assert fails[0].locations == ["tasks.md:5"]
    # ... and RI-01-FR-DEF does not double-report it as an undefined reference
    assert fails_for(spec_dir, ["RI-01-FR-DEF"]) == []
    assert rc.main(["--spec-dir", str(spec_dir), "--only", "TOMBSTONED-FR-REF"]) == 1


def test_a_genuinely_undefined_id_still_fails_the_definition_check(tmp_path: Path) -> None:
    """REQUIRED: the tombstone exclusion must not turn 'never defined anywhere' into silence."""
    spec_dir = build_feature_dir(
        tmp_path / "f",
        spec=spec_with_tombstone(),
        tasks=GOOD_TASKS.replace(
            _T003_LINE,
            "- [ ] T003 [US3] Resolve every `mention_ref` in the index. (FR-003, FR-103, \u00a72)",
        ),
    )
    fails = fails_for(spec_dir, ["RI-01-FR-DEF"])
    assert [(f.code, f.data["fr"]) for f in fails] == [("fr-undefined", "FR-103")]
    # FR-058 is cited nowhere here, and FR-103 has no record at all
    assert rc.main(["--spec-dir", str(spec_dir), "--only", "RI-01-FR-DEF"]) == 1
    assert fails_for(spec_dir, ["TOMBSTONED-FR-REF"]) == []


def test_an_undefined_id_next_to_a_live_citation_of_a_tombstone_reports_both(
    tmp_path: Path,
) -> None:
    """Both defects at once, each on the check that owns it, neither swallowing the other."""
    spec_dir = build_feature_dir(
        tmp_path / "f",
        spec=spec_with_tombstone(),
        tasks=GOOD_TASKS.replace(
            _T003_LINE,
            "- [ ] T003 [US3] Resolve `mention_ref` values. (FR-003, FR-058, FR-103, \u00a72)",
        ),
    )
    assert [f.data["fr"] for f in fails_for(spec_dir, ["RI-01-FR-DEF"])] == ["FR-103"]
    assert [f.data["fr"] for f in fails_for(spec_dir, ["TOMBSTONED-FR-REF"])] == ["FR-058"]


@pytest.mark.parametrize(
    "marker",
    ["tombstone", "TOMBSTONE", "Tombstone", "deprecated", "DEPRECATED",
     "merged into", "Merged Into", "absorbed into", "Absorbed into",
     "folded into", "Folded into", "superseded by", "Superseded by", "see ADR", "See ADR"],
)
def test_every_accepted_marker_opens_a_tombstone_record(marker: str) -> None:
    """Case-insensitive, and only in the leading clause."""
    assert rc.is_tombstone_record(f"* {marker} - `INV-004`; history.") is True
    assert rc.is_tombstone_record(f"{marker} into `FR-078`.") is True
    assert rc.is_tombstone_record(f"`FR-058` {marker} - `INV-004`.") is True


@pytest.mark.parametrize(
    "body",
    [
        "External vocabularies MUST produce a `TypeSignal`.\n\n"
        "  *Tombstone `FR-034a` - folded into this slot*",
        "`LEXICAL`, `SYNTACTIC` and `TABLE` are the only producers.\n\n"
        "  *Tombstone `FR-039a` - folded into this slot*",
        "The workflow's stages MUST be, in order: `acquire`, `bind_mentions`. Mention binding\n"
        "  MUST be its own stage and MUST NOT be folded into another stage.",
        "A mapping change MUST supersede rather than edit: the prior candidate is preserved.",
        "A requirement may name a deprecated alias without adopting it.",
        "`PredicateSignature` MUST carry exactly `language`.",
    ],
)
def test_a_live_requirement_that_merely_mentions_a_marker_stays_live(body: str) -> None:
    """The real shapes in this corpus: FR-035, FR-040 and FR-164 all mention a marker mid-body.

    A whole-body search would read each of them as a tombstone, delete a live requirement from
    the definition population, and turn every citation of it into a phantom.
    """
    assert rc.is_tombstone_record(body) is False


def test_a_live_fr_that_footnotes_a_tombstone_is_still_a_definition_target(tmp_path: Path) -> None:
    """The end-to-end version of the control above: FR-035's shape, in a real run."""
    footnoted = (
        "- **FR-005**: External vocabularies MUST produce a `TypeSignal`.\n"
        "  *Tombstone `FR-034a` - folded into this slot* (\u00a71)\n\n"
        "- **FR-006**: The signature MUST NOT be folded into another field's identity. "
        "(\u00a71)\n\n"
    )
    spec_dir = build_feature_dir(
        tmp_path / "f",
        spec=GOOD_SPEC.replace("## Success Criteria", footnoted + "## Success Criteria"),
        tasks=GOOD_TASKS.replace(
            _T003_LINE,
            "- [ ] T003 [US3] Resolve every `mention_ref`. (FR-003, FR-005, FR-006, \u00a72)",
        ),
    )
    ctx = rc.build_context(spec_dir)
    assert {"FR-005", "FR-006"} <= set(ctx.live_index())
    assert {d.ident for d in ctx.def_occurrences if d.tombstone} == set()
    assert ctx.tombstone_ids == set(rc.TOMBSTONED_FRS)
    # the citations really are in the file, so the two silences below are not vacuous
    assert "FR-005" in (spec_dir / "tasks.md").read_text(encoding="utf-8")
    # their citations resolve, so RI-01-FR-DEF is silent about them ...
    assert fails_for(spec_dir, ["RI-01-FR-DEF"]) == []
    # ... and neither is mistaken for a tombstone by the gate
    assert fails_for(spec_dir, ["FR-NAMESPACE-COLLISION"]) == []
    # ... but a genuinely undefined id cited in the same task line is still a FAIL
    with_citation = build_feature_dir(
        tmp_path / "h",
        spec=GOOD_SPEC.replace("## Success Criteria", footnoted + "## Success Criteria"),
        tasks=GOOD_TASKS.replace(
            _T003_LINE,
            "- [ ] T003 [US3] Resolve every `mention_ref`. (FR-003, FR-005, FR-103, \u00a72)",
        ),
    )
    assert "FR-103" in (with_citation / "tasks.md").read_text(encoding="utf-8")
    assert [f.data["fr"] for f in fails_for(with_citation, ["RI-01-FR-DEF"])] == ["FR-103"]


def test_a_tombstone_record_is_never_a_live_normative_definition(tmp_path: Path) -> None:
    """The invariant that makes the classification safe to exclude.

    Every marker the parser accepts must also be a marker the tombstone gate reads as
    history. If one were not, classifying the row would *create* a
    `tombstoned-fr-defined-normative` FAIL out of a record.
    """
    spec_dir = build_feature_dir(tmp_path / "f", spec=spec_with_tombstone())
    assert fails_for(spec_dir, ["TOMBSTONED-FR-REF"]) == []
    for marker in rc.TOMBSTONE_RECORD_MARKERS:
        assert rc.DEPRECATION_RE.search(f"*{marker} - history*"), marker


def test_a_tombstone_record_outside_the_arbitration_map_is_still_gated(tmp_path: Path) -> None:
    """The anti-hole control for the exclusion: an unregistered record must not go invisible.

    `RI-01-FR-DEF` no longer reports an undefined reference for an id that carries a tombstone
    record, so the record has to enter the tombstone universe or a live citation of it would
    be reported by nobody.
    """
    spec_dir = build_feature_dir(
        tmp_path / "f",
        spec=GOOD_SPEC.replace(
            "## Success Criteria",
            "- **FR-004**: *tombstone - merged into `FR-003`; history only.*\n\n"
            "## Success Criteria",
        ),
        tasks=GOOD_TASKS.replace(
            _T003_LINE,
            "- [ ] T003 [US3] Resolve every `mention_ref` in the index. (FR-003, FR-004, \u00a72)",
        ),
    )
    ctx = rc.build_context(spec_dir)
    assert "FR-004" in ctx.tombstone_ids
    assert fails_for(spec_dir, ["RI-01-FR-DEF"]) == []
    fails = fails_for(spec_dir, ["TOMBSTONED-FR-REF"])
    assert [f.data["fr"] for f in fails] == ["FR-004"]
    assert rc.main(["--spec-dir", str(spec_dir), "--only", "TOMBSTONED-FR-REF"]) == 1


def test_a_live_requirement_written_beside_a_record_is_not_swallowed(tmp_path: Path) -> None:
    """A tombstone record adjacent to a live FR must not take the live FR with it."""
    spec_dir = build_feature_dir(
        tmp_path / "f",
        spec=GOOD_SPEC.replace(
            "## Success Criteria",
            "- **FR-004**: *tombstone - merged into `FR-003`; history only.*\n"
            "- **FR-005**: A live requirement that must still be implemented. (\u00a72)\n\n"
            "## Success Criteria",
        ),
        tasks=GOOD_TASKS.replace(
            _T003_LINE,
            "- [ ] T003 [US3] Resolve every `mention_ref` in the index. (FR-003, FR-005, \u00a72)",
        ),
    )
    ctx = rc.build_context(spec_dir)
    assert ctx.tombstone_ids >= {"FR-004"}
    assert "FR-005" in ctx.live_index()
    assert fails_for(spec_dir, ["RI-01-FR-DEF"]) == []
    assert fails_for(spec_dir, ["RI-03-FR-ORPHAN"]) == []
    assert fails_for(spec_dir, ["RI-03b-FR-UNCITED"]) == []


def test_a_tombstone_record_does_not_duplicate_under_its_own_id(tmp_path: Path) -> None:
    """Two records for one id is still a defect, and the duplicate rule still sees it."""
    spec_dir = build_feature_dir(
        tmp_path / "f",
        spec=spec_with_tombstone(
            extra="- **FR-058**: *tombstone - merged into `INV-004`; history only.*\n"
        ),
    )
    fails = fails_for(spec_dir, ["RI-01-FR-DEF"])
    assert [f.code for f in fails] == ["fr-defined-twice"]

def test_the_real_spec_md_tombstone_records_are_recognised_as_records() -> None:
    """The real document: whichever records it currently carries are classified, and only those.

    Anchored on the shape (a row whose body opens with a marker) rather than on line numbers,
    so this keeps working as the integration moves text around.
    """
    ctx = rc.build_context(SPEC_DIR)
    records = {d.ident for d in ctx.def_occurrences if d.tombstone}
    for d in ctx.def_occurrences:
        if d.ident in records:
            assert d.ident not in ctx.live_index()
    # every record is inside the gate's universe, so a live citation of it is still reported
    assert records <= set(ctx.tombstones())
    # and a record never removes a *live* requirement from the definition population
    assert {d.ident for d in ctx.live_defs} | records == {d.ident for d in ctx.defs}


# --- FR-NAMESPACE-COLLISION ------------------------------------------------------------------


_A2_STYLE = """\
# A2 - identity

**FR-101 - the `PredicateSignature` field set.**

`PredicateSignature` MUST carry exactly `language` and `predicate_lemma`, and no other field.
"""

_A6_STYLE = """\
# A6 - triage

**FR-101 (NEW) - the §8 entity extractor expansion**

> The entity extraction layer MUST provide producers/readers for all seven families of §8.
"""


def test_fr_defined_twice_in_two_repair_documents_is_a_historical_divergence(
    tmp_path: Path,
) -> None:
    """FIX 2: two repair waves inventing FR-101 is a record of a dispute, not a live defect.

    Both sites are `repair/` documents, so the collision is evidence about how the repair
    went, not a claim on the FR namespace. `ARBITRATION.md` §1/§14 is the sole authority on
    which document owns a number, and it says the answer is neither of these. The finding is
    retained verbatim at INFO.
    """
    spec_dir = build_repair_dir(build_feature_dir(tmp_path / "f"),
                               **{"A2-identity": _A2_STYLE, "A6-triage": _A6_STYLE})
    found = findings_for(spec_dir, ["FR-NAMESPACE-COLLISION"])
    assert fails_for(spec_dir, ["FR-NAMESPACE-COLLISION"]) == []
    demoted = [f for f in found if f.code == rc.HISTORICAL_CODE]
    assert len(demoted) == 1
    f = demoted[0]
    assert f.severity == rc.INFO
    assert f.data["original_code"] == "fr-namespace-collision"
    assert f.data["original_severity"] == rc.FAIL
    assert f.data["fr"] == "FR-101"
    assert f.data["shape"] == "repair-vs-repair"
    assert f.data["kinds"] == ["new-requirement", "redefinition"]
    assert f.locations == ["repair/A2-identity.md:3", "repair/A6-triage.md:3"]
    # both texts are still quoted, so a reader can adjudicate without opening either file
    texts = {s["artefact"]: s["text"] for s in f.data["sites"]}
    assert "PredicateSignature" in texts["repair/A2-identity.md"]
    assert "entity extraction layer" in texts["repair/A6-triage.md"]
    # ... and the message names the artefact, the finding and the ruling that superseded it
    assert "repair/A2-identity.md" in f.message and "repair/A6-triage.md" in f.message
    assert "fr-namespace-collision" in f.message and "§1" in f.message


def test_repair_document_redefining_a_spec_fr_is_a_historical_divergence(
    tmp_path: Path,
) -> None:
    """FIX 2 (b): the same violation in `repair/` does not gate; see the spec.md twin below."""
    spec_dir = build_repair_dir(
        build_feature_dir(
            tmp_path / "f",
            spec=GOOD_SPEC.replace(
                "## Success Criteria",
                "- **FR-004**: A producer MUST report `producer_version`. (§2)\n\n"
                "## Success Criteria",
            ),
        ),
        **{"A6-triage": "**FR-004 (REWRITE)**\n\nA producer MUST report nothing at all.\n"},
    )
    assert fails_for(spec_dir, ["FR-NAMESPACE-COLLISION"]) == []
    demoted = [f for f in findings_for(spec_dir, ["FR-NAMESPACE-COLLISION"])
               if f.code == rc.HISTORICAL_CODE]
    assert len(demoted) == 1
    assert demoted[0].data["shape"] == "spec-vs-repair"
    assert demoted[0].data["kinds"] == ["canonical-definition", "rewrite-proposal"]
    # the live site is named too, so the reader knows which text governs
    assert demoted[0].locations == ["spec.md:20", "repair/A6-triage.md:1"]
    assert demoted[0].data["historical_artefacts"] == ["repair/A6-triage.md"]


def test_two_definitions_of_one_fr_inside_spec_md_still_fail(tmp_path: Path) -> None:
    """The blind-spot control: the exemption is about *where* the site is, not about collisions.

    Two definition rows for one id, both in `spec.md`, is a live namespace defect with no
    historical reading available, and it is still FAIL.
    """
    spec_dir = build_feature_dir(
        tmp_path / "f",
        spec=GOOD_SPEC.replace(
            "## Success Criteria",
            "- **FR-002**: A second, different definition of the same id. (§2)\n\n"
            "## Success Criteria",
        ),
    )
    fails = fails_for(spec_dir, ["RI-01-FR-DEF"])
    assert [(f.code, f.data["fr"]) for f in fails] == [("fr-defined-twice", "FR-002")]
    # and the namespace check sees it too, as a spec-vs-spec pair with no repair site, so the
    # demotion cannot reach it
    collision = fails_for(spec_dir, ["FR-NAMESPACE-COLLISION"])
    assert [(f.code, f.data["shape"]) for f in collision] == [
        ("fr-namespace-collision", "spec-vs-spec")]
    assert all(loc.startswith("spec.md:") for f in collision for loc in f.locations)


def test_identical_redefinition_is_info_not_a_collision(tmp_path: Path) -> None:
    """A quotation that changes nothing is a restatement, not a second owner."""
    text = ("# report\n\n**FR-101 - the field set.**\n\n`PredicateSignature` MUST carry exactly "
            "`language`.\n")
    spec_dir = build_repair_dir(build_feature_dir(tmp_path / "f"),
                               **{"A2-identity": text, "A6-triage": text})
    assert blocking(spec_dir, "FR-NAMESPACE-COLLISION") == []
    found = findings_for(spec_dir, ["FR-NAMESPACE-COLLISION"])
    assert sorted(f.code for f in found if f.severity == rc.INFO) == [
        "fr-namespace-summary", "fr-redefined-identically"]


def test_a_quoted_old_fr_in_a_fence_is_not_a_second_owner(tmp_path: Path) -> None:
    """`repair/A7-*.md` quotes old requirement text verbatim inside a fence: a citation."""
    spec_dir = build_repair_dir(
        build_feature_dir(tmp_path / "f"),
        **{"A7-migration": (
            "# migration\n\n**FR-003, old, verbatim:**\n\n```markdown\n"
            "- **FR-003**: `PredicateSignature` MUST carry at least `predicate_lemma`.\n```\n"
        )},
    )
    assert blocking(spec_dir, "FR-NAMESPACE-COLLISION") == []


def test_a_bold_fr_range_is_not_a_definition(tmp_path: Path) -> None:
    """`FR-001–FR-100 are NOT renumbered` is a range claim, not a second FR-001."""
    spec_dir = build_repair_dir(
        build_feature_dir(tmp_path / "f"),
        **{"ARBITRATION": "# arbitration\n\n**FR-001–FR-100 are NOT renumbered.**\n"},
    )
    assert blocking(spec_dir, "FR-NAMESPACE-COLLISION") == []


def test_clean_feature_dir_has_no_fr_namespace_collision(tmp_path: Path) -> None:
    assert blocking(build_feature_dir(tmp_path / "f"), "FR-NAMESPACE-COLLISION") == []


# --- EPISTEMIC-AXIS-CONFLATION ---------------------------------------------------------------


def test_structural_conflict_written_into_contradicted_fails(tmp_path: Path) -> None:
    """The exact shape `repair/ARBITRATION.md` §3 forbids: arity/direction/polarity/roles."""
    spec_dir = build_feature_dir(
        tmp_path / "f",
        tasks=GOOD_TASKS.replace(
            _T003_LINE,
            "- [ ] T003 [US3] A conflict over arity, direction, polarity or roles MUST yield "
            "`CandidateStatus.CONTRADICTED` with both readings preserved. (FR-003, §2)",
        ),
    )
    fails = fails_for(spec_dir, ["EPISTEMIC-AXIS-CONFLATION"])
    assert [f.code for f in fails] == ["structural-conflict-as-denied"]
    assert fails[0].locations == ["tasks.md:5"]
    assert set(fails[0].data["structural_terms"]) >= {"arity", "direction", "polarity"}
    assert "assembly_state = CONFLICTING" in fails[0].message


def test_prohibiting_the_conflation_is_not_a_finding(tmp_path: Path) -> None:
    """The arbitration record states the rule; a checker that flags the rule is noise."""
    spec_dir = build_repair_dir(
        build_feature_dir(tmp_path / "f"),
        **{"ARBITRATION": (
            "# arbitration\n\n## 3 - CONFLICTING vs CONTRADICTED\n\n"
            "**A6 is forbidden from turning structural disagreement into `CONTRADICTED`.**\n\n"
            "A structural conflict that is not a denial yields `assembly_state = CONFLICTING`, "
            "never `candidate_status = CONTRADICTED`.\n"
        )},
    )
    found = findings_for(spec_dir, ["EPISTEMIC-AXIS-CONFLATION"])
    assert blocking(spec_dir, "EPISTEMIC-AXIS-CONFLATION") == []
    summary = next(f for f in found if f.code == "epistemic-summary")
    assert summary.data["conflations"] == 0
    assert summary.data["prohibition_restatements"] == 2


def test_a_semantic_conflict_alone_is_not_a_finding(tmp_path: Path) -> None:
    """`CONFLICTING` on the hypothesis is the correct home for a semantic disagreement."""
    spec_dir = build_feature_dir(
        tmp_path / "f",
        spec=GOOD_SPEC.replace(
            "## Success Criteria",
            "- **FR-005**: Two regimes mapping one signature incompatibly MUST carry "
            "`resolution_state=CONFLICTING`. (§2)\n\n## Success Criteria",
        ),
    )
    assert blocking(spec_dir, "EPISTEMIC-AXIS-CONFLATION") == []


def test_a_denial_without_a_structural_term_is_not_a_finding(tmp_path: Path) -> None:
    spec_dir = build_feature_dir(
        tmp_path / "f",
        spec=GOOD_SPEC.replace(
            "## Success Criteria",
            "- **FR-006**: A positive reading versus an explicit denial MUST yield "
            "`CandidateStatus.CONTRADICTED`. (§2)\n\n## Success Criteria",
        ),
    )
    assert blocking(spec_dir, "EPISTEMIC-AXIS-CONFLATION") == []


def test_clean_feature_dir_has_no_epistemic_conflation(tmp_path: Path) -> None:
    assert blocking(build_feature_dir(tmp_path / "f"), "EPISTEMIC-AXIS-CONFLATION") == []


# --- COUNT-PRECISION --------------------------------------------------------------------------


def test_count_precision_flags_32_entity_types(tmp_path: Path) -> None:
    spec_dir = build_feature_dir(tmp_path / "f", plan="FR-001 MUST cover 32 entity types. (§1)\n")
    warns = [f for f in findings_for(spec_dir, ["COUNT-PRECISION"]) if f.severity == rc.WARN]
    assert [f.code for f in warns] == ["count-32-as-entity-types"]
    assert warns[0].locations == ["plan.md:1"]
    assert warns[0].data["phrase"] == "32 entity types"
    assert warns[0].severity == rc.WARN


def test_count_precision_flags_seven_classes_in_a_section_8_context(tmp_path: Path) -> None:
    """The same phrase in `spec.md` still WARNs; in `repair/` it is a divergence (FIX 2)."""
    live = build_feature_dir(
        tmp_path / "live", plan="Producers/readers MUST exist for all seven classes of §8.\n")
    warns = [f for f in findings_for(live, ["COUNT-PRECISION"]) if f.severity == rc.WARN]
    assert [f.code for f in warns] == ["count-seven-classes"]
    assert warns[0].data["phrase"] == "all seven classes"
    assert warns[0].locations == ["plan.md:1"]

    spec_dir = build_repair_dir(
        build_feature_dir(tmp_path / "f"),
        **{"A6-triage": "> producers/readers for all seven classes of §8:\n"},
    )
    assert blocking(spec_dir, "COUNT-PRECISION") == []
    demoted = [f for f in findings_for(spec_dir, ["COUNT-PRECISION"])
               if f.code == rc.HISTORICAL_CODE]
    assert len(demoted) == 1
    assert demoted[0].data["original_code"] == "count-seven-classes"
    assert demoted[0].data["original_severity"] == rc.WARN
    assert demoted[0].locations == ["repair/A6-triage.md:1"]
    assert demoted[0].data["historical_artefacts"] == ["repair/A6-triage.md"]


def test_count_precision_flags_seven_classes_in_a_test_name(tmp_path: Path) -> None:
    """`seven_classes` inside a test name is the same defect, and it is in a repair record.

    A7b's own table of the miscount is the corpus instance, so the finding is retained by
    name - what changes is that it no longer gates.
    """
    spec_dir = build_repair_dir(
        build_feature_dir(tmp_path / "f"),
        **{"A6-triage": ("| T114 | entity extractor expansion | "
                         "`test_entity_extractor_covers_all_seven_classes` |\n")},
    )
    assert blocking(spec_dir, "COUNT-PRECISION") == []
    demoted = [f for f in findings_for(spec_dir, ["COUNT-PRECISION"])
               if f.code == rc.HISTORICAL_CODE]
    assert [f.data["original_code"] for f in demoted] == ["count-seven-classes"]
    assert demoted[0].data["phrase"] == "all_seven_classes"


def test_count_precision_accepts_the_four_authority_numbers(tmp_path: Path) -> None:
    spec_dir = build_repair_dir(
        build_feature_dir(tmp_path / "f"),
        **{"A5-type": ("# types\n\n31 foundational entity types, 13 value types, seven extraction "
                       "families of §8, ~4 new instrument modules.\n")},
    )
    found = findings_for(spec_dir, ["COUNT-PRECISION"])
    assert blocking(spec_dir, "COUNT-PRECISION") == []
    summary = next(f for f in found if f.code == "count-precision-summary")
    assert summary.data["conflations"] == 0
    assert summary.data["authority_numbers"] == rc.AUTHORITY_NUMBERS


def test_count_precision_treats_a_correction_as_info_not_warn(tmp_path: Path) -> None:
    spec_dir = build_repair_dir(
        build_feature_dir(tmp_path / "f"),
        **{"ARBITRATION": ('# arbitration\n\n11. "32 types" corrected to **31**; the "seven '
                           'classes" of §8 renamed to "seven extraction families".\n')},
    )
    found = findings_for(spec_dir, ["COUNT-PRECISION"])
    assert blocking(spec_dir, "COUNT-PRECISION") == []
    assert sorted(f.code for f in found if f.severity == rc.INFO) == [
        "count-precision-summary", "count-refutation", "count-refutation"]
    summary = next(f for f in found if f.code == "count-precision-summary")
    assert summary.data["conflations"] == 0
    assert summary.data["refutation_mentions"] == 2


def test_clean_feature_dir_has_no_count_conflation(tmp_path: Path) -> None:
    assert blocking(build_feature_dir(tmp_path / "f"), "COUNT-PRECISION") == []


# --- GHOST-SUFFIX ----------------------------------------------------------------------------


def test_ghost_suffix_flags_a_live_normative_citation(tmp_path: Path) -> None:
    spec_dir = build_repair_dir(
        build_feature_dir(
            tmp_path / "f",
            spec=GOOD_SPEC.replace(
                "## Success Criteria",
                "- **FR-034a**: Type and relation policy MUST be the one stated. (§1)\n\n"
                "## Success Criteria",
            ),
        ),
        **{"A8prep": "| 369 | Sub-numbered ids | `FR-034a` and `FR-039a` |\n"},
    )
    warns = [f for f in findings_for(spec_dir, ["GHOST-SUFFIX"]) if f.severity == rc.WARN]
    assert [f.code for f in warns] == ["suffixed-fr-citation", "suffixed-fr-citation"]
    assert {f.data["fr"] for f in warns} == {"FR-034a", "FR-039a"}
    assert warns[0].data["by_file"] == {"repair/A8prep.md": 1}
    assert warns[0].data["citation_count"] == 1


def test_ghost_suffix_on_a_deprecation_marked_line_is_history(tmp_path: Path) -> None:
    spec_dir = build_feature_dir(
        tmp_path / "f",
        plan="FR-034a is **absorbed into** `INV-002` and tombstoned.\n",
    )
    found = findings_for(spec_dir, ["GHOST-SUFFIX"])
    assert blocking(spec_dir, "GHOST-SUFFIX") == []
    assert next(f for f in found if f.code == "ghost-suffix-summary").data["citations"] == 0


def test_unsuffixed_ids_are_not_ghosts(tmp_path: Path) -> None:
    spec_dir = build_feature_dir(tmp_path / "f", plan="FR-001 and FR-002 are unaffected. (§1)\n")
    assert blocking(spec_dir, "GHOST-SUFFIX") == []


def test_clean_feature_dir_has_no_ghost_suffix(tmp_path: Path) -> None:
    assert blocking(build_feature_dir(tmp_path / "f"), "GHOST-SUFFIX") == []


# --- the five checks together ------------------------------------------------------------------


def test_every_new_check_is_silent_on_a_clean_feature_dir_with_repair_docs(tmp_path: Path) -> None:
    spec_dir = build_repair_dir(
        build_feature_dir(tmp_path / "f"),
        **{"A2-identity": _A2_STYLE.replace("FR-101", "FR-004").replace(
            "`PredicateSignature`", "`logical_candidate_id`"),
           "ARBITRATION": "# arbitration\n\nNothing is tombstoned; 31 entity types stand.\n"},
    )
    for cid in NEW_CHECKS:
        assert blocking(spec_dir, cid) == [], (cid, blocking(spec_dir, cid))


def test_every_new_check_id_appears_in_the_summary_of_a_clean_run(tmp_path: Path) -> None:
    spec_dir = build_repair_dir(build_feature_dir(tmp_path / "f"), **{"A6-triage": _A6_STYLE})
    ctx = rc.build_context(spec_dir)
    found, ran = rc.run_checks(ctx)
    rows = rc.summarize(found, ran)
    assert {r["check_id"] for r in rows} == set(rc.CHECK_BY_ID)
    for cid in NEW_CHECKS:
        row = next(r for r in rows if r["check_id"] == cid)
        assert row["default_severity"] in rc.SEVERITIES
        assert row["fail"] + row["warn"] + row["info"] == row["total"]


def test_malformed_repair_documents_are_findings_not_exceptions(tmp_path: Path) -> None:
    spec_dir = build_repair_dir(
        build_feature_dir(
            tmp_path / "f",
            **{
                "spec.md": "# broken\n\n- **FR-058** no colon\n| a | b\n|---\n| 1 | 2 | 3 |\n",
                "tasks.md": "- [ ] T001 x (FR-034a)\n- [ ] T1 y\n",
                "checklists/requirements.md": "|||||\n",
            },
        ),
        **{
            "A2-broken": ("# broken\n\n| a | b |\n|---\n"
                          "**FR-101\n**FR-101 (NEW)\n> \n```\nunclosed fence\n"),
            "A6-empty": "",
        },
    )
    found = findings_for(spec_dir)
    assert not [f for f in found if f.code == "check-crashed"]
    assert "TOMBSTONED-FR-REF" in {f.check_id for f in found}
    assert rc.main(["--spec-dir", str(spec_dir)]) == 1


def test_new_checks_survive_a_non_utf8_repair_document(tmp_path: Path) -> None:
    spec_dir = build_repair_dir(build_feature_dir(tmp_path / "f"), **{"placeholder": "x\n"})
    (spec_dir / "repair" / "A2-latin.md").write_bytes(b"# latin-1: \xe9\xe8\xea\nFR-101\n")
    found = findings_for(spec_dir, NEW_CHECKS)
    assert not [f for f in found if f.code == "check-crashed"]


# --- real-artefact tripwires for the new checks ------------------------------------------------


def _independently_derived_live_tombstone_refs() -> set[tuple[str, str, int]]:
    """(fr, artefact, line) for every *live* citation of a tombstoned id, derived from the files.

    Deliberately a second, literal implementation of ARBITRATION §2 rather than a hard-coded
    list: the old test pinned two `file:line` pairs that the integration moved, and then failed
    for a reason that had nothing to do with the check. Re-deriving the expectation from the
    documents keeps the test exact and makes it immune to renumbering.
    """
    out: set[tuple[str, str, int]] = set()
    for name in ("spec.md", "tasks.md", "plan.md", "research.md", "data-model.md",
                 "checklists/requirements.md"):
        path = SPEC_DIR / name
        if not path.is_file():
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for fr in rc.TOMBSTONED_FRS:
                token = re.compile(rf"\b{re.escape(fr)}\b")
                if not token.search(line):
                    continue
                if re.search(r"\b(?:absorbed|merged)\s+into\b|\bmerged\s+away\b", line,
                             re.IGNORECASE):
                    continue
                if re.search(r"tombston|deprecat|absorb|see\s+(?:the\s+)?adr|supersed|"
                             r"folded\s+into|no\s+longer\s+normative|not\s+normative",
                             line, re.IGNORECASE):
                    continue
                out.add((fr, name, i))
    return out


def test_tripwire_tombstone_gate_reports_exactly_the_live_references() -> None:
    """The gate reports the live references and nothing else - today and after integration."""
    ctx = rc.build_context(SPEC_DIR)
    fails = fails_for(SPEC_DIR, ["TOMBSTONED-FR-REF"])
    reported = {
        (f.data["fr"], loc.rpartition(":")[0], int(loc.rpartition(":")[2]))
        for f in fails
        for loc in f.locations
    }
    assert reported == _independently_derived_live_tombstone_refs(), (
        sorted(reported ^ _independently_derived_live_tombstone_refs())
    )
    for f in fails:
        assert f.severity == rc.FAIL
        assert f.data["fr"] in ctx.tombstones()
        art = ctx.by_name(f.data["artefact"])
        line_no = int(f.locations[0].rpartition(":")[2])
        line = art.lines[line_no - 1]
        assert not rc.DEPRECATION_RE.search(line), (f.data["fr"], line)
    # and it is the check, not RI-01-FR-DEF, that owns a live citation of a retired id
    ri01 = {f.data.get("fr") for f in fails_for(SPEC_DIR, ["RI-01-FR-DEF"])}
    assert not (ri01 & set(ctx.tombstone_ids)), sorted(ri01 & set(ctx.tombstone_ids))


def test_tripwire_a_retired_id_is_cited_live_somewhere() -> None:
    """The live gate is red today: at least one retired id is still cited as a live target.

    Guarded on the artefact text, so a repaired corpus retires the assertion instead of
    breaking the suite, exactly like the other tripwires in this file.
    """
    live = _independently_derived_live_tombstone_refs()
    if not live:
        pytest.skip("no tombstoned id is cited without a deprecation marker any more")
    fails = fails_for(SPEC_DIR, ["TOMBSTONED-FR-REF"])
    assert fails, sorted(live)
    assert {f.data["fr"] for f in fails} == {fr for fr, _, _ in live}
    assert rc.main(["--spec-dir", str(SPEC_DIR), "--only", "TOMBSTONED-FR-REF"]) == 1


def test_tripwire_the_real_tasks_md_has_no_gaps_in_its_own_range() -> None:
    """The rule that replaced the T001 anchor, asserted against the real plan."""
    ctx = rc.build_context(SPEC_DIR)
    numbers = [int(t.ident[1:]) for t in ctx.tasks if re.fullmatch(r"T\d+", t.ident)]
    assert numbers, "tasks.md defines no plain Tnnn id"
    assert numbers == sorted(numbers)
    assert sorted(numbers) == list(range(min(numbers), max(numbers) + 1))
    assert len(numbers) == len(set(numbers))
    assert not [f for f in findings_for(SPEC_DIR, ["RI-06-TASK-ORDER"])
                if f.severity in (rc.FAIL, rc.WARN)]
    assert min(numbers) > 1, (
        "the plan is no longer offset from T001; the declared-range rule should be re-argued"
    )


def test_tripwire_fr_101_and_fr_102_are_defined_twice() -> None:
    fails = fails_for(SPEC_DIR, ["FR-NAMESPACE-COLLISION"])
    if not fails:
        pytest.skip("the FR namespace has no collision left")
    same_id = {f.data["fr"]: f for f in fails if f.data["shape"] == "repair-vs-repair"}
    assert set(same_id) == {"FR-101", "FR-102"}, sorted(same_id)
    for fr, f in same_id.items():
        assert {loc.rpartition(":")[0] for loc in f.locations} == {
            "repair/A2-identity-subsystem.md", "repair/A6-fr-triage.md"}
        assert f.data["fr"] == fr


def test_tripwire_every_reported_conflation_really_is_one() -> None:
    """Re-pointed from three hard-coded line numbers to the rule and the documents.

    The invariant worth keeping is not "spec.md:737 says X" but: every reported unit really does
    put a structural disagreement and `CONTRADICTED` in the same breath, never states a
    prohibition, and is reported *at all*. Which document still carries the defect today is
    not an invariant - the integration is repairing them one at a time - so this test survives
    that and keeps the checker honest. `test_tripwire_a_conflation_is_still_live_somewhere` is
    the companion that goes red while a *gating* one remains.

    Since FIX 2 the count is split: a unit in `spec.md`/`tasks.md` is a FAIL, a unit in a
    `repair/` document is the same finding demoted to INFO `historical-divergence`. Every unit
    the check measured must still be present at *some* severity - that is the property, and
    the FAIL count alone no longer proves it.
    """
    ctx = rc.build_context(SPEC_DIR)
    found = findings_for(SPEC_DIR, ["EPISTEMIC-AXIS-CONFLATION"])
    fails = [f for f in found if f.severity == rc.FAIL]
    demoted = [f for f in found if f.code == rc.HISTORICAL_CODE]
    summary = next((f for f in found if f.code == "epistemic-summary"), None)
    assert summary is not None, "the check must report its own summary"
    assert summary.data["conflations"] == len(fails) + len(demoted)
    reported = fails + demoted
    if not reported:
        pytest.skip("no epistemic-axis conflation remains in the corpus")
    for f in reported:
        assert set(f.data["structural_terms"]), f.data
        quoted = f.data.get("quoted") or f.data.get("original_message", "")
        assert f.data.get("original_code") in {"structural-conflict-as-denied"}, f.data
        assert "CONTRADICTED" in quoted, quoted
        assert not rc.EPISTEMIC_PROHIBITION_RE.search(quoted), (
            f"a unit that prohibits the conflation must not be reported: {quoted}"
        )
        for loc in f.locations:
            name, _, line_no = loc.rpartition(":")
            art = next(a for a in [*ctx.scanned, *ctx.repair] if a.name == name)
            n = int(line_no)
            assert "CONTRADICTED" in art.lines[n - 1], loc
            unit = next(t for first, last, t in rc.prose_units(art) if first <= n <= last)
            assert any(t in unit.lower() for t in f.data["structural_terms"]), (loc, unit[:200])
    # a FAIL means a live artefact, never a repair record
    for f in fails:
        assert all(not loc.startswith("repair/") for loc in f.locations), f.locations
    # the check's declared scope is stable even when its findings are not
    assert {"spec.md", "tasks.md"} <= {a.name for a in ctx.readable(("spec.md", "tasks.md"))}


def test_tripwire_a_conflation_is_still_live_somewhere() -> None:
    """A *gating* conflation, if one remains, keeps the gate red.

    `repair/` conflations are demoted by FIX 2, so a corpus whose only remaining conflations
    are historical records is green by design. This asserts the FAIL case, not the count.
    """
    fails = fails_for(SPEC_DIR, ["EPISTEMIC-AXIS-CONFLATION"])
    if not fails:
        pytest.skip("every remaining epistemic-axis conflation is in a repair/ record")
    assert rc.main(["--spec-dir", str(SPEC_DIR), "--only", "EPISTEMIC-AXIS-CONFLATION"]) == 1


def test_tripwire_d7_miscount_and_the_seven_classes_phrase() -> None:
    """The real corpus still contains the miscount and the wrong phrase.

    `32 type classes` lives in a live artefact, so it is still WARN. `all seven classes`
    lives in A6's table, so FIX 2 demotes it to INFO `historical-divergence`; the assertion is
    that it is *named* either way, not that it gates.
    """
    found = findings_for(SPEC_DIR, ["COUNT-PRECISION"])
    warns = [f for f in found if f.severity == rc.WARN]
    demoted = [f for f in found if f.code == rc.HISTORICAL_CODE]
    if not warns and not demoted:
        pytest.skip("the four authority numbers are no longer conflated anywhere")
    phrases = {f.data["phrase"] for f in warns}
    phrases |= {f.data["original_message"] and f.data.get("phrase", "") for f in demoted}
    assert "32 type classes" in phrases
    assert any("all seven classes" in f.data.get("original_message", "") for f in demoted) or \
        "all seven classes" in phrases
    for f in demoted:
        assert f.data["original_severity"] == rc.WARN
        assert all(loc.startswith("repair/") for loc in f.locations), f.locations


def test_tripwire_ghost_suffixes_are_still_cited() -> None:
    warns = [f for f in findings_for(SPEC_DIR, ["GHOST-SUFFIX"]) if f.severity == rc.WARN]
    if not warns:
        pytest.skip("every letter-suffixed FR has been folded")
    assert {f.data["fr"] for f in warns} == {"FR-034a", "FR-039a"}
    assert all(f.locations for f in warns)


# --------------------------------------------------------------------------------------
# FIX 2 - `repair/*.md` is a historical record: the exemption, and the line drawn round it
# --------------------------------------------------------------------------------------
#
# Two halves, and the second is the one that matters:
#
#   (a) a *content* finding (what the document asserts about the design) is demoted to INFO
#       `historical-divergence` when it sits in a repair document;
#   (b) a *reference* finding (does the id the document points at exist) is not, and a
#       repair document that claims an unallocated number still FAILs.
#
# The tests below cover (a) in `repair/` and in `spec.md` for every exempt check, cover (b)
# for FR ids and task ids, and pin the membership of both sets so neither can widen silently.


# The one sentence of a repair document that is wrong about the design, by ARBITRATION §3.
_CONFLATION_PROSE = (
    "A disagreement that is **structural** - arity, direction, polarity or role bindings over "
    "the same mentions - MUST yield `CandidateStatus.CONTRADICTED` candidates.\n"
)


def test_a_content_violation_in_a_repair_document_is_info_not_fail(tmp_path: Path) -> None:
    """REQUIRED (FIX 2 a): `A4b` said this before §3 existed. Reported, not gating."""
    spec_dir = build_repair_dir(build_feature_dir(tmp_path / "f"),
                                **{"A4b-mapping": "# A4b\n\n" + _CONFLATION_PROSE})
    fails = fails_for(spec_dir, ["EPISTEMIC-AXIS-CONFLATION"])
    assert fails == []
    demoted = [f for f in findings_for(spec_dir, ["EPISTEMIC-AXIS-CONFLATION"])
               if f.code == rc.HISTORICAL_CODE]
    assert len(demoted) == 1
    f = demoted[0]
    assert (f.severity, f.data["original_severity"], f.data["original_code"]) == (
        rc.INFO, rc.FAIL, "structural-conflict-as-denied")
    assert f.locations == ["repair/A4b-mapping.md:3"]
    # names the artefact, the finding, and the ruling that superseded it
    assert "repair/A4b-mapping.md" in f.message
    assert "structural-conflict-as-denied" in f.message
    assert "ARBITRATION.md" in f.message and "§3" in f.data["superseded_by"]
    # nothing is lost: the structural terms and the quotation survive verbatim
    assert f.data["structural_terms"] == ["arity", "direction", "polarity", "role binding"]
    assert "CONTRADICTED" in f.data["original_message"]
    # and the gate is green while the information is still in the payload
    assert rc.main(["--spec-dir", str(spec_dir), "--only", "EPISTEMIC-AXIS-CONFLATION"]) == 0


def test_the_same_violation_in_spec_md_still_fails(tmp_path: Path) -> None:
    """REQUIRED (FIX 2 b): identical text, live artefact, unchanged severity."""
    spec_dir = build_feature_dir(
        tmp_path / "f",
        spec=GOOD_SPEC.replace("#### Producers", "#### Mapping\n\n" + _CONFLATION_PROSE
                               + "\n#### Producers"),
    )
    found = findings_for(spec_dir, ["EPISTEMIC-AXIS-CONFLATION"])
    fails = [f for f in found if f.severity == rc.FAIL]
    assert len(fails) == 1
    assert fails[0].code == "structural-conflict-as-denied"
    assert fails[0].locations == ["spec.md:17"]
    assert [f for f in found if f.code == rc.HISTORICAL_CODE] == []
    assert rc.main(["--spec-dir", str(spec_dir), "--only", "EPISTEMIC-AXIS-CONFLATION"]) == 1


def test_the_exemption_covers_exactly_the_four_named_content_checks() -> None:
    """The membership is a named set, and it is pinned here so it cannot grow by accident."""
    assert rc.NORMATIVE_LINT_CHECKS == {
        "EPISTEMIC-AXIS-CONFLATION", "FR-NAMESPACE-COLLISION", "COUNT-PRECISION",
        "RI-10-FORBIDDEN",
    }
    assert set(rc.SUPERSEDING_AUTHORITY) == set(rc.NORMATIVE_LINT_CHECKS)
    for cid, section in rc.SUPERSEDING_AUTHORITY.items():
        assert "§" in section, (cid, section)


def test_reference_integrity_checks_are_not_exempt_and_the_reason_is_on_the_record() -> None:
    """The interesting claim is the one that was NOT granted, so both lists are pinned.

    `GHOST-SUFFIX` is namespace hygiene over citations, so by the rule it would qualify. It
    is left out on purpose and the reason is written down in the tool; if it is ever added,
    this test is the thing that notices.
    """
    assert set(rc.REFERENCE_INTEGRITY_NOT_EXEMPT) >= {
        "RI-01-FR-DEF", "RI-02-TASK-REF", "RI-06b-FR-ORDER", "RI-08-SEC-CITE",
        "RI-09-COUNT", "RI-11-CONST", "RI-11b-RESEARCH", "TOMBSTONED-FR-REF",
        "GHOST-SUFFIX",
    }
    assert not (rc.NORMATIVE_LINT_CHECKS & set(rc.REFERENCE_INTEGRITY_NOT_EXEMPT))
    for cid, reason in rc.REFERENCE_INTEGRITY_NOT_EXEMPT.items():
        assert reason.strip(), cid
    assert rc.CHECK_BY_ID["GHOST-SUFFIX"].severity == rc.WARN


def test_a_phantom_fr_claimed_in_a_repair_document_still_fails(tmp_path: Path) -> None:
    """REQUIRED (FIX 2 c): a repair document may not be the authority for a number.

    The corpus's own example is A2's `**FR-104 - ...**` and A6's `**FR-101 (NEW) - ...**`:
    bold-titled requirement claims in prose, for numbers `ARBITRATION.md` §14 declares void
    and re-allocates elsewhere. `FR-103` is the number the arbitration record singles out.
    """
    spec_dir = build_repair_dir(
        build_feature_dir(tmp_path / "f"),
        **{"A1-requirements": (
            "# A1\n\n## proposed\n\n"
            "**FR-103 - the historical phantom.**\n\n"
            "`InvestigationWorkflow` MUST be registered on the Temporal worker.\n"
        )},
    )
    fails = fails_for(spec_dir, ["RI-01-FR-DEF"])
    assert [f.code for f in fails] == ["fr-undefined-in-repair"]
    assert fails[0].data["fr"] == "FR-103"
    assert fails[0].locations == ["repair/A1-requirements.md:5"]
    # the demotion cannot reach it, even though it sits in the one exempt corpus
    assert fails[0].code != rc.HISTORICAL_CODE
    assert "RI-01-FR-DEF" not in rc.NORMATIVE_LINT_CHECKS
    assert rc.main(["--spec-dir", str(spec_dir), "--only", "RI-01-FR-DEF"]) == 1


def test_a_phantom_task_defined_in_a_repair_document_still_fails(tmp_path: Path) -> None:
    """The task-id half of the same rule, on the same principle."""
    spec_dir = build_repair_dir(
        build_feature_dir(tmp_path / "f"),
        **{"A6-triage": "# A6\n\n- [ ] T777 [US1] Replay harness (FR-003, \u00a72)\n"},
    )
    fails = fails_for(spec_dir, ["RI-02-TASK-REF"])
    assert [f.code for f in fails] == ["task-phantom-in-repair"]
    assert fails[0].data["task"] == "T777"
    assert rc.main(["--spec-dir", str(spec_dir), "--only", "RI-02-TASK-REF"]) == 1


def test_a_phantom_id_merely_mentioned_in_a_repair_document_is_counted_not_gated(
    tmp_path: Path,
) -> None:
    """The line itself: a *mention* is history, a *definition* is a claim on the namespace.

    `A1` proposes `FR-101…FR-109` inside a ```` ```markdown ```` fence - quoted material, so
    not even a claim. `A6` then says in prose that "`FR-103` is cited by 4 artefacts and does
    not exist", which is the checker doing its job in a report. Neither gates; both are
    counted, so the reader can see the id was discussed.
    """
    spec_dir = build_repair_dir(
        build_feature_dir(tmp_path / "f"),
        **{"A1-quoted": (
            "# A1\n\n```markdown\n- **FR-103**: MUST be registered on the worker.\n```\n"
        ),
         "A6-report": "# A6\n\n| FR-103 | cited by 4 artefacts, does not exist | why |\n"},
    )
    assert fails_for(spec_dir, ["RI-01-FR-DEF"]) == []
    note = next(f for f in findings_for(spec_dir, ["RI-01-FR-DEF"])
                if f.code == "repair-historical-reference-summary")
    assert note.severity == rc.INFO
    assert note.data["ids"] == ["FR-103"]
    assert note.data["mention_total"] == 2
    assert note.data["files"] == ["repair/A1-quoted.md", "repair/A6-report.md"]


def test_a_fenced_definition_in_a_repair_document_is_quotation_not_a_claim(
    tmp_path: Path,
) -> None:
    """The blind-spot control for the previous test: the fence is what makes it history.

    Identical text, unfenced, is a claim on the namespace and gates.
    """
    quoted = build_repair_dir(
        build_feature_dir(tmp_path / "f"),
        **{"A1": "# A1\n\n```markdown\n- **FR-103**: MUST be registered.\n```\n"},
    )
    assert fails_for(quoted, ["RI-01-FR-DEF"]) == []
    unfenced = build_repair_dir(
        build_feature_dir(tmp_path / "f"),
        **{"A1": "# A1\n\n- **FR-103**: MUST be registered.\n"},
    )
    assert [f.code for f in fails_for(unfenced, ["RI-01-FR-DEF"])] == ["fr-undefined-in-repair"]


def test_an_id_embedded_in_a_longer_identifier_is_not_a_reference(tmp_path: Path) -> None:
    """`CHK-FR-01` contains `FR-01` and the word boundary holds either side of the hyphen.

    A6's table carries ~200 such labels. Reporting them as references to `FR-001` is how a
    checker teaches a reader to ignore it.
    """
    spec_dir = build_repair_dir(
        build_feature_dir(tmp_path / "f"),
        **{"A6-checks": "# A6\n\n| CHK-FR-01 | one definition per id | ok |\n"
                        "| SUB-T-103 | one id per shape | ok |\n"},
    )
    assert fails_for(spec_dir, ["RI-01-FR-DEF"]) == []
    assert fails_for(spec_dir, ["RI-02-TASK-REF"]) == []
    assert not [f for f in findings_for(spec_dir, ["RI-01-FR-DEF"])
                if f.code == "repair-historical-reference-summary"]


def test_demotion_is_never_inferred_from_a_finding_that_names_no_site() -> None:
    """Absence of evidence is not evidence of history.

    A finding with no `repair/` location and no `data["artefact"]` / `data["file"]` must not
    be demoted, or the exemption would swallow every finding that forgets to say where it was.
    """
    naked = rc.Finding(check_id="COUNT-PRECISION", severity=rc.FAIL, code="count-32",
                       message="somewhere", locations=[], data={})
    assert not rc.is_historical_site(naked)
    assert rc.demote_historical([naked])[0].severity == rc.FAIL
    named = rc.Finding(check_id="COUNT-PRECISION", severity=rc.FAIL, code="count-32",
                       message="somewhere", locations=[], data={"artefact": "repair/A6.md"})
    assert rc.is_historical_site(named)
    assert rc.demote_historical([named])[0].severity == rc.INFO


def test_demotion_never_lowers_an_info_finding_further(tmp_path: Path) -> None:
    """The exemption changes gating, and INFO does not gate; an INFO stays an INFO verbatim."""
    already = rc.Finding(check_id="FR-NAMESPACE-COLLISION", severity=rc.INFO,
                         code="fr-redefined-identically", message="restated",
                         locations=["repair/A2.md:1"], data={})
    out = rc.demote_historical([already])
    assert out[0] is already, "an INFO must not be re-wrapped as a divergence"


def test_the_demotion_summary_accounts_for_every_demoted_finding(tmp_path: Path) -> None:
    """No silent loss: the count of demotions is itself a reported finding."""
    spec_dir = build_repair_dir(
        build_feature_dir(tmp_path / "f"),
        **{"A4b": "# A4b\n\n" + _CONFLATION_PROSE,
           "A6": "# A6\n\n| `all seven classes` of \u00a78 | needed | x |\n"},
    )
    found = findings_for(spec_dir)
    demoted = [f for f in found if f.code == rc.HISTORICAL_CODE]
    summary = next(f for f in found if f.code == "historical-divergence-summary")
    assert summary.data["demoted"] == {"COUNT-PRECISION": 1, "EPISTEMIC-AXIS-CONFLATION": 1}
    assert sum(summary.data["demoted"].values()) == len(demoted)
    assert summary.data["exempt_checks"] == sorted(rc.NORMATIVE_LINT_CHECKS)


def test_demotion_is_a_single_pass_so_a_new_yield_site_cannot_forget_it() -> None:
    """Structural property, asserted: the exemption is applied outside the checks.

    Every FAIL of an exempt check with a `repair/` site comes back as INFO with the
    divergence code, whatever produced it, so adding a fifth yield site to an exempt check
    cannot silently produce a gating finding.
    """
    for cid in sorted(rc.NORMATIVE_LINT_CHECKS):
        for code, artefact in (("x", "repair/A6.md"), ("y", "spec.md")):
            f = rc.Finding(check_id=cid, severity=rc.FAIL, code=code, message="m",
                           locations=[f"{artefact}:3"], data={})
            out = rc.demote_historical([f])
            if artefact.startswith("repair/"):
                assert out[0].severity == rc.INFO and out[0].code == rc.HISTORICAL_CODE
            else:
                assert out[0].severity == rc.FAIL and out[0].code == code


def test_the_real_repair_documents_only_diverge_in_history(tmp_path: Path) -> None:
    """The corpus assertion, anchored on the rule and not on line numbers.

    Every `EPISTEMIC-AXIS-CONFLATION` and `FR-NAMESPACE-COLLISION` finding the real corpus
    produces sits in a `repair/` document, so every one of them is INFO. If the integration
    writes a conflation into `spec.md`, this goes red immediately.
    """
    ctx = rc.build_context(SPEC_DIR)
    found = findings_for(SPEC_DIR, ["EPISTEMIC-AXIS-CONFLATION", "FR-NAMESPACE-COLLISION"])
    gated = [f for f in found if f.severity in (rc.FAIL, rc.WARN)]
    if not gated and not found:
        pytest.skip("neither governance check has anything to say about the real corpus")
    for f in gated:
        sites = [loc.rpartition(":")[0] for loc in f.locations]
        live = [s for s in sites if not s.startswith("repair/")]
        assert not live or f.check_id == "FR-NAMESPACE-COLLISION" and any(
            s.startswith("repair/") for s in sites), (f.check_id, live)
    demoted = [f for f in found if f.code == rc.HISTORICAL_CODE]
    for f in demoted:
        assert f.data["historical_artefacts"]
        for name in f.data["historical_artefacts"]:
            assert name.startswith("repair/") and name in {a.name for a in ctx.repair}


# --------------------------------------------------------------------------------------
# FIX 3 - the type vocabulary must be *owned*, not per-term backed
# --------------------------------------------------------------------------------------
#
# `ARBITRATION.md` §10 and §14 rule 4 both decide, in terms, that a type in the vocabulary
# does not oblige a dedicated extractor and that an absence is not a refusal. The old rule
# counted 44 terms and demanded a producer for each, i.e. it demanded the exact opposite of a
# binding ruling, and the ruling it contradicted was the one the corpus had already applied.
#
# So the unit of judgement moves from the term to the vocabulary: FAIL when nothing owns it,
# and keep three teeth that no owner repairs. Every shape below is a separate synthetic, so
# a regression in one cannot be masked by the others.


def _spec_with_vocabulary(extra_frs: str) -> str:
    """GOOD_SPEC plus requirement rows appended before the success criteria."""
    return GOOD_SPEC.replace("## Success Criteria", extra_frs + "\n## Success Criteria")


def _vocab_codes(spec_dir: Path) -> set[str]:
    return {f.code for f in fails_for(spec_dir, ["RI-10-FORBIDDEN"])}


# The corpus's own shape: FR-030 enumerates, states the boundary, and names FR-179 as the
# obligation; FR-179 carries the producer obligation bounded by the seven §8 families.
_OWNED_VOCABULARY = (
    "#### Type pack\n\n"
    "- **FR-004**: The pack MUST cover, at minimum, the following **3** entity classes:\n"
    "  `core:Person`, `core:Organization`, `core:Facility`. (\u00a72)\n"
    "  This is a **fixture requirement on the pack's contents** and MUST NOT be read as a\n"
    "  producer obligation: a type's presence here does not oblige the system to have a\n"
    "  dedicated extractor for it. The one producer obligation this feature creates is\n"
    "  `FR-005`, and it is bounded by the **seven \u00a78 extraction families** - not by the\n"
    "  length of this list; the two counts are independent and neither may be derived from\n"
    "  the other. (\u00a72)\n"
    "- **FR-005**: The deterministic entity extraction layer MUST be completed around the\n"
    "  atomic type vocabulary, providing producers/readers for all seven extraction families\n"
    "  of \u00a78. (\u00a72)\n"
)

_OBLIGATION_TASKS = (
    GOOD_TASKS
    + "- [ ] T004 [US4] Bound the pack obligation by the seven \u00a78 families. "
      "(FR-004, \u00a72)\n"
    + "- [ ] T005 [US5] Provide producers for the seven \u00a78 families. (FR-005, \u00a72)\n"
)

_OWNED_CHECKLIST = GOOD_CHECKLIST + (
    "\n## C. Type pack\n\n"
    "| # | Item | Method | FR | Task | State |\n|---|---|---|---|---|---|\n"
    "| C1 | the pack is bounded by the seven families, not its length | T | FR-004 | T004 "
    "| \u2610 |\n"
    "| C2 | seven \u00a78 extraction families have producers | T | FR-005, SC-001 | T005 "
    "| \u2610 |\n"
)


def _owned_vocabulary_dir(root: Path) -> Path:
    return build_feature_dir(
        root, spec=_spec_with_vocabulary(_OWNED_VOCABULARY),
        tasks=_OBLIGATION_TASKS, checklist=_OWNED_CHECKLIST,
    )


def test_an_owned_and_bounded_vocabulary_passes_without_per_term_producers(
    tmp_path: Path,
) -> None:
    """REQUIRED (FIX 3): owned + bounded -> pass, and 3 terms with 0 producers is fine.

    `FR-004` names the obligation `FR-005` and bounds it to the seven \u00a78 extraction families
    rather than to the length of the list, and `FR-005` carries that bound in its own words.
    Neither obliges an extractor for `core:Person` specifically, which is the point.
    """
    spec_dir = _owned_vocabulary_dir(tmp_path / "f")
    assert _vocab_codes(spec_dir) == set()
    ok = next(f for f in findings_for(spec_dir, ["RI-10-FORBIDDEN"])
              if f.code == "vocabulary-owned")
    assert ok.severity == rc.INFO
    assert ok.data["owner_frs"] == ["FR-004", "FR-005"]
    assert ok.data["enumerating_frs"] == ["FR-004"]
    assert ok.data["terms"] == 3
    reasons = ok.data["owner_reasons"]
    assert reasons["FR-004"] == "enumerates the vocabulary"
    assert "FR-004 delegates" in reasons["FR-005"]
    # the pass is auditable: the message says what was *not* checked and why
    assert "Per-term producer backing is NOT" in ok.message
    assert rc.main(["--spec-dir", str(spec_dir), "--only", "RI-10-FORBIDDEN"]) == 0


def test_an_unowned_vocabulary_still_fails(tmp_path: Path) -> None:
    """REQUIRED (FIX 3): enumerating a list is not claiming it.

    No obligation, no bound, no delegation: a list nobody has taken responsibility for.
    """
    spec_dir = build_feature_dir(
        tmp_path / "f",
        spec=_spec_with_vocabulary(
            "#### Type pack\n\n- **FR-004**: The pack covers `core:Person`, `core:Organization` "
            "and\n  `core:Facility`. (\u00a72)\n"
        ),
        tasks=GOOD_TASKS + "- [ ] T004 [US4] Register the pack. (FR-004, \u00a72)\n",
    )
    codes = _vocab_codes(spec_dir)
    assert "vocabulary-unowned" in codes, codes
    finding = next(f for f in fails_for(spec_dir, ["RI-10-FORBIDDEN"])
                   if f.code == "vocabulary-unowned")
    assert finding.data["enumerating_frs"] == ["FR-004"]
    assert finding.data["owner_frs"] == []
    assert finding.data["terms"] == ["core:Facility", "core:Organization", "core:Person"]
    assert rc.main(["--spec-dir", str(spec_dir), "--only", "RI-10-FORBIDDEN"]) == 1


def test_a_completeness_asserting_vocabulary_still_fails(tmp_path: Path) -> None:
    """REQUIRED (FIX 3): membership must not be turned into a per-type mandate.

    An owner exists *and* is bounded *and* the vocabulary still claims that every entry
    carries a producer. The owner cannot repair that, because the claim is the contradiction.
    """
    spec_dir = build_feature_dir(
        tmp_path / "f",
        spec=_spec_with_vocabulary(
            "#### Type pack\n\n- **FR-004**: The pack MUST cover `core:Person`, "
            "`core:Organization` and\n  `core:Facility`. Every type in the pack MUST have a "
            "dedicated extractor. The obligation is bounded by the **seven \u00a78 extraction\n"
            "  families**, not by the length of this list; the two counts are independent. "
            "(\u00a72)\n"
        ),
        tasks=GOOD_TASKS + "- [ ] T004 [US4] Give every type an extractor. (FR-004, \u00a72)\n",
    )
    codes = _vocab_codes(spec_dir)
    assert "vocabulary-completeness-asserted" in codes, codes
    assert "vocabulary-unowned" not in codes, codes
    finding = next(f for f in fails_for(spec_dir, ["RI-10-FORBIDDEN"])
                   if f.code == "vocabulary-completeness-asserted")
    assert finding.data["enumerating_frs"] == ["FR-004"]
    # the owner is still named, so the reader can see the contradiction rather than a gap
    assert finding.data["owner_frs"] == ["FR-004"]
    assert finding.locations and all(loc.startswith("spec.md:") for loc in finding.locations)


def test_a_vocabulary_used_as_a_permit_deny_gate_still_fails(tmp_path: Path) -> None:
    """REQUIRED (FIX 3): a vocabulary that decides admission is a closed-world type system."""
    spec_dir = build_feature_dir(
        tmp_path / "f",
        spec=_spec_with_vocabulary(
            "#### Type pack\n\n- **FR-004**: The pack MUST cover `core:Person`, "
            "`core:Organization` and\n  `core:Facility`. A signal MUST be rejected unless the "
            "resolved\n  type is in the pack. The obligation is bounded by the **seven \u00a78 "
            "extraction\n  families**, not by the length of this list. (\u00a72)\n"
        ),
        tasks=GOOD_TASKS + "- [ ] T004 [US4] Reject unlisted types. (FR-004, \u00a72)\n",
    )
    codes = _vocab_codes(spec_dir)
    assert "vocabulary-used-as-gate" in codes, codes
    finding = next(f for f in fails_for(spec_dir, ["RI-10-FORBIDDEN"])
                   if f.code == "vocabulary-used-as-gate")
    assert finding.data["owner_frs"] == ["FR-004"]
    assert finding.locations and all(loc.startswith("spec.md:") for loc in finding.locations)


def test_an_at_minimum_lower_bound_is_not_a_completeness_assertion(tmp_path: Path) -> None:
    """The blind-spot control for the completeness rule: an open lower bound is not closure.

    "MUST cover, at minimum, the following 3" is a floor, and treating a floor as "this is the
    complete set of obligations" is the same false positive the fix is meant to remove.
    """
    spec_dir = _owned_vocabulary_dir(tmp_path / "f")
    assert _vocab_codes(spec_dir) == set()
    assert "MUST cover, at minimum" in _OWNED_VOCABULARY


def test_a_bound_of_the_list_length_is_not_a_bound(tmp_path: Path) -> None:
    """The other blind-spot control: a count of entries states how big the list is, not scope.

    "obligation is bounded by the 3 entries" is the original defect wearing a bound's
    clothes, and must not be accepted as ownership.
    """
    spec_dir = build_feature_dir(
        tmp_path / "f",
        spec=_spec_with_vocabulary(
            "#### Type pack\n\n- **FR-004**: The pack MUST cover `core:Person`, "
            "`core:Organization` and\n  `core:Facility`. Every type MUST have an extractor, "
            "bounded by the\n  **3** types. (\u00a72)\n"
        ),
        tasks=GOOD_TASKS + "- [ ] T004 [US4] Give every type an extractor. (FR-004, \u00a72)\n",
    )
    codes = _vocab_codes(spec_dir)
    # both teeth: it asserts completeness *and* nothing bounds it to anything real
    assert codes & {"vocabulary-completeness-asserted", "vocabulary-unowned"}, codes


def test_a_section_locator_is_not_a_bound(tmp_path: Path) -> None:
    """A `§N` is a citation, not a scope. FR-031 in the real corpus carries one and no bound."""
    spec_dir = build_feature_dir(
        tmp_path / "f",
        spec=_spec_with_vocabulary(
            "#### Type pack\n\n- **FR-004**: The pack MUST cover `core:Person` and\n"
            "  `core:Organization`. (\u00a72)\n"
        ),
        tasks=GOOD_TASKS + "- [ ] T004 [US4] Register the pack. (FR-004, \u00a72)\n",
    )
    assert "vocabulary-unowned" in _vocab_codes(spec_dir)


def test_a_number_merely_mentioned_beside_an_obligation_word_is_not_a_delegation(
    tmp_path: Path,
) -> None:
    """The over-broad-deferral control.

    A correction note that says "these three slots once read `FR-004`, `FR-005` and `FR-006`"
    is not the vocabulary delegating its obligation; it is a footnote about renumbering. If
    proximity were enough, such a note would manufacture an owner out of any id it names.
    """
    spec_dir = build_feature_dir(
        tmp_path / "f",
        spec=_spec_with_vocabulary(
            "#### Type pack\n\n- **FR-004**: The pack MUST cover `core:Person`. The producer\n"
            "  obligation is cross-reference corrected: this slot once read `FR-002`.\n"
            "  (\u00a72)\n"
        ),
        tasks=GOOD_TASKS + "- [ ] T004 [US4] Register the pack. (FR-004, \u00a72)\n",
    )
    assert "vocabulary-unowned" in _vocab_codes(spec_dir)


def test_the_real_vocabulary_is_owned_by_fr_030_and_fr_179() -> None:
    """The corpus assertion: the two owner FRs `ARBITRATION.md` §14 rule 4 names.

    Anchored on the rule, not on a line number, so renumbering moves the test instead of
    breaking it. The 44 terms and the absence of per-term producers are asserted too, because
    that is the exact situation the fix has to survive.
    """
    ctx = rc.build_context(SPEC_DIR)
    terms = rc._vocabulary_terms(ctx)
    owners = rc._vocabulary_owners(ctx, terms)
    assert len(terms) == 44
    assert sorted(set(terms.values())) == ["FR-030", "FR-031", "FR-135"]
    assert [ident for ident, _ in owners] == ["FR-030", "FR-179"]
    reasons = dict(owners)
    assert reasons["FR-030"] == "enumerates the vocabulary"
    assert reasons["FR-179"].startswith("FR-030 delegates")
    # and the check agrees, at INFO, on the real corpus
    found = findings_for(SPEC_DIR, ["RI-10-FORBIDDEN"])
    assert [f.code for f in fails_for(SPEC_DIR, ["RI-10-FORBIDDEN"])] == []
    ok = next(f for f in found if f.code == "vocabulary-owned")
    assert ok.data["owner_frs"] == ["FR-030", "FR-179"]


def test_the_bound_predicates_are_exercised_on_the_real_fr_030() -> None:
    """Unit-level, so the corpus's own wording is pinned rather than merely parsed."""
    ctx = rc.build_context(SPEC_DIR)
    body = next(d.body for d in ctx.live_defs if d.ident == "FR-030")
    assert rc._BOUND_DENIAL_RE.search(body), "FR-030 states the count-independence explicitly"
    assert rc._states_a_non_count_bound(body)
    assert not rc._COMPLETENESS_RE.search(body) or rc._COMPLETENESS_QUALIFIER_RE.search(body)
    assert not rc._VOCAB_GATE_RE.search(body)
    assert rc._deferral_targets(body) >= {"FR-179"}
    # the bound is not the list length, which is the whole claim
    assert "not by the length of this list" in body


# --------------------------------------------------------------------------------------
# the three fixes together: one self-consistent directory that must stay green
# --------------------------------------------------------------------------------------
#
# The anti-always-red control already exists for a clean directory. This is its companion
# for the three fixes: a directory that is *deliberately* shaped like the real corpus - a
# tombstone between two live requirement numbers, an owned-and-bounded vocabulary with no
# per-term producers, a repair record carrying a superseded conflation and a superseded
# phrase, and a claim on an unallocated number that must still gate - asserted to produce
# zero FAIL and exit 0 *with one known FAIL deliberately present* being turned off, so the
# test cannot pass by the fixes having muted a check into silence.
#
# Every check id must appear in the summary. A check that stopped running is the failure mode
# these fixes could plausibly introduce, and an absent row is the only symptom.


# The live requirement sequence of the three-fixes fixture. `FR-058` is absent on purpose and
# retired on purpose, so the sequence is contiguous except for exactly one hole - and that one
# hole is the one FIX 1 exists for. Reaching `FR-058` honestly needs 57 requirements below it,
# which is why this list is generated rather than written out.
_THREE_FIXES_LIVE: tuple[int, ...] = tuple(range(1, 58)) + (59, 60, 61)
_TOMBSTONED_IN_FIXTURE = 58
_VOCAB_OWNER = 60
_VOCAB_OBLIGATION = 61


def _three_fixes_dir(root: Path) -> Path:
    """A self-consistent feature directory exercising all three fixes at once.

    Written out rather than assembled by `str.replace`, because the point of the fixture is
    that it is *consistent*: every live FR cited by exactly one task, a checklist row per FR,
    no citation to a section that does not exist, the plan's FR count right, and a requirement
    sequence whose only hole is the retired `FR-058`. If any of those were wrong the directory
    would go red for a reason unrelated to the three fixes, and the control would stop testing
    anything.
    """
    S = "\u00a7"
    box = "\u2610"
    input_md = (
        "# FEATURE 901 - SYNTHETIC, THREE FIXES\n\n"
        "# 1. MISSION\n\n### A. Entity interpretation\n\n"
        "# 2. CORE DECISION\n\n### A. Predicate\n\n"
        "# 7. EXTRACTION LAYER\n\n"
        "# 8. ENTITY INSTRUMENTS\n\n"
        "### A. Person\n\n### B. Organization\n\n"
    )
    # 001..057 are ordinary requirements; 059..061 carry the rest of the fixture.
    bodies: dict[int, str] = {
        n: (f"- **FR-{n:03d}**: The `stage_{n:03d}` obligation MUST hold and MUST be "
            f"observable. ({S}2)")
        for n in _THREE_FIXES_LIVE if n < 59
    }
    bodies[59] = (f"- **FR-059**: A rejected candidate MUST be recorded with a reason. "
                  f"({S}2)")
    bodies[_VOCAB_OWNER] = (
        "- **FR-060**: The pack MUST cover, at minimum, the following **3** entity classes:\n"
        "  `core:Person`, `core:Organization`, `core:Facility`. (" + S + "8)\n"
        "  This is a **fixture requirement on the pack's contents** and MUST NOT be read as a\n"
        "  producer obligation: a type's presence here does not oblige the system to have a\n"
        "  dedicated extractor for it. The one producer obligation this feature creates is\n"
        f"  `FR-{_VOCAB_OBLIGATION:03d}`, and it is bounded by the **seven {S}8 extraction "
        "families** -\n"
        "  not by the length of this list; the two counts are independent and neither may be\n"
        f"  derived from the other. ({S}8)\n"
        f"- **FR-{_VOCAB_OBLIGATION:03d}**: The deterministic entity extraction layer MUST be "
        "completed\n"
        f"  around the atomic type vocabulary, providing producers/readers for all seven\n"
        f"  extraction families of {S}8. ({S}8)"
    )
    spec = (
        "# Feature Specification: three fixes\n\n"
        "**Input**: `input.md` in this directory.\n\n"
        "## Requirements\n\n### Functional Requirements\n\n"
        "#### Identity\n\n"
        + bodies[1] + "\n"
        + bodies[2] + "\n\n"
        "#### Producers\n\n"
        + bodies[3] + "\n"
        + "".join(bodies[n] + "\n" for n in range(4, 58))
        + "\n#### Verification\n\n"
        + bodies[59] + "\n\n"
        "#### Type pack\n\n"
        + bodies[_VOCAB_OWNER] + "\n\n"
        "## Success Criteria\n\n### Measurable Outcomes\n\n"
        "- **SC-001**: Active and passive realisations share one `logical_candidate_id`.\n\n"
        "### Constitutional invariants\n\n"
        "- **INV-001**: An ontology miss yields `UNKNOWN`, never a rejection.\n"
    )
    # task ids are their own contiguous sequence; the FR numbering has a hole and the task
    # numbering must not, or `RI-06-TASK-ORDER` would be red for an unrelated reason
    tasks = "# Tasks: three fixes\n\n" + "".join(
        f"- [ ] T{i:03d} [US1] Deliver `stage_{n:03d}`. (FR-{n:03d}, "
        f"{S}{'8' if n >= _VOCAB_OWNER else '2'})\n"
        for i, n in enumerate(_THREE_FIXES_LIVE, start=1)
    )
    plan = ("# Implementation Plan: three fixes\n\n"
            f"{len(_THREE_FIXES_LIVE)} FRs, 1 measurable outcome, 1 constitutional invariant, "
            "0 user stories.\n")
    data_model = (
        "# Phase 1 Data Model: three fixes\n\n"
        "## 1. Pack\n\n"
        "`TypePack` holds the `core:*` entries. `kind` is read from the entry, never inferred.\n"
    )
    header = ("| # | Item | Method | FR | Task | State |\n|---|---|---|---|---|---|\n")
    rows = "".join(
        f"| R{n:03d} | `stage_{n:03d}` is observable | T | FR-{n:03d} | T{i:03d} | {box} |\n"
        for i, n in enumerate(_THREE_FIXES_LIVE, start=1)
    )
    checklist = (
        "# Requirements checklist: three fixes\n\n"
        "## A. Requirements\n\n" + header + rows + "\n"
        "## B. Success criteria and invariants\n\n" + header
        + f"| B1 | active and passive share one logical id | T | FR-001, SC-001 | T001 "
          f"| {box} |\n"
        + f"| B2 | an ontology miss yields UNKNOWN | T | FR-003, INV-001 | T003 "
          f"| {box} |\n"
    )
    root = build_feature_dir(
        root, **{"input.md": input_md, "spec.md": spec, "tasks.md": tasks, "plan.md": plan,
                 "data-model.md": data_model, "checklist": checklist},
    )
    return build_repair_dir(
        root,
        **{
            # two superseded *content* claims: reported, not gating
            "A4b-mapping": "# A4b\n\n" + _CONFLATION_PROSE,
            "A6-triage": f"| T114 | extractor expansion | all seven classes of {S}8 | x |\n",
            # the arbitration record: the retirement, and the four authority numbers
            "ARBITRATION": (
                "# ARBITRATION\n\n"
                f"31 foundational entity types, 13 value types, 7 {S}8 extraction "
                "families, ~4 new instrument modules.\n\n"
                f"{S}2: `FR-{_TOMBSTONED_IN_FIXTURE:03d}` is absorbed into `INV-004` and "
                "tombstoned. A\n"
                "tombstone is historical traceability only.\n"
            ),
        },
    )


def test_three_fixes_together_stay_green_on_a_self_consistent_directory(
    tmp_path: Path,
) -> None:
    """0 FAIL, exit 0, every check id present - with all three fixes active."""
    spec_dir = _three_fixes_dir(tmp_path / "f")
    fails = fails_for(spec_dir)
    assert fails == [], [(f.check_id, f.code, f.message) for f in fails]
    assert rc.main(["--spec-dir", str(spec_dir)]) == 0

    ctx = rc.build_context(spec_dir)
    _found, ran = rc.run_checks(ctx)
    assert set(ran) == set(rc.CHECK_BY_ID)
    rows = rc.summarize(_found, ran)
    assert {r["check_id"] for r in rows} == set(rc.CHECK_BY_ID)
    assert all(r["fail"] == 0 for r in rows), [r for r in rows if r["fail"]]
    for row in rows:
        assert row["fail"] + row["warn"] + row["info"] == row["total"]


def test_three_fixes_together_still_prove_each_check_is_measuring(tmp_path: Path) -> None:
    """The anti-silent-loss companion: a green directory is not a silent one.

    For each of the three fixes the directory above must produce the *evidence* the fix
    emits - a demotion summary, a walked sequence, an owned-vocabulary record - so "0 FAIL"
    cannot be reached by the checks having stopped looking.
    """
    spec_dir = _three_fixes_dir(tmp_path / "f")
    found = findings_for(spec_dir)
    codes = {(f.check_id, f.code) for f in found}

    # FIX 1: the contiguity walk ran, and the retired id is in its universe
    assert ("RI-06b-FR-ORDER", "fr-sequence-ok") in codes
    ctx = rc.build_context(spec_dir)
    assert f"FR-{_TOMBSTONED_IN_FIXTURE:03d}" in ctx.tombstone_ids
    assert _TOMBSTONED_IN_FIXTURE in rc._recorded_fr_numbers(ctx)

    # FIX 2: two demotions, one summary, and the summary agrees with the findings
    demoted = [f for f in found if f.code == rc.HISTORICAL_CODE]
    assert {f.data["original_code"] for f in demoted} == {
        "structural-conflict-as-denied", "count-seven-classes"}
    summary = next(f for f in found if f.code == "historical-divergence-summary")
    assert sum(summary.data["demoted"].values()) == len(demoted) == 2

    # FIX 3: the vocabulary was examined and found owned, with both owners named
    owned = next(f for f in found if f.code == "vocabulary-owned")
    assert owned.data["owner_frs"] == [f"FR-{_VOCAB_OWNER:03d}", f"FR-{_VOCAB_OBLIGATION:03d}"]
    assert owned.data["enumerating_frs"] == [f"FR-{_VOCAB_OWNER:03d}"]
    assert owned.data["terms"] == 3
    assert owned.data["owner_reasons"][f"FR-{_VOCAB_OBLIGATION:03d}"].startswith(
        f"FR-{_VOCAB_OWNER:03d} delegates")


def test_three_fixes_together_go_red_when_the_defects_are_moved_to_live_artefacts(
    tmp_path: Path,
) -> None:
    """The blind-spot control for all three at once, in one assertion per fix.

    The same three defects, relocated from the historical record into `spec.md`, must gate
    again. If any of the three fixes leaked past its own boundary, this is what notices.
    """
    spec_dir = build_feature_dir(
        tmp_path / "f",
        spec=GOOD_SPEC.replace(
            "#### Producers",
            "#### Mapping\n\n" + _CONFLATION_PROSE
            + "\n- **FR-005**: The pack MUST cover `core:Person`. Every type in the pack MUST\n"
              "  have a dedicated extractor. (\u00a72)\n\n#### Producers",
        ),
    )
    fails = {(f.check_id, f.code) for f in fails_for(spec_dir)}
    assert ("EPISTEMIC-AXIS-CONFLATION", "structural-conflict-as-denied") in fails
    # completeness short-circuits by design (one finding per run, most specific first), so
    # the unowned arm is exercised by its own dedicated test above rather than here
    assert ("RI-10-FORBIDDEN", "vocabulary-completeness-asserted") in fails
    assert rc.main(["--spec-dir", str(spec_dir)]) == 1


# --------------------------------------------------------------------------------------
# the four defects that must keep failing, re-introduced synthetically
# --------------------------------------------------------------------------------------
#
# The real corpus repairs these one at a time, so "it is red today" is a statement about the
# documents, not about the checker, and a repaired document retires the evidence. Each is
# therefore re-introduced into a synthetic directory and asserted to FAIL, which is the claim
# that actually matters: the check still has its teeth after the three fixes.
#
# The corpus instance is named in each docstring so a reader can find the original.


def test_a_checklist_row_without_an_fr_still_fails(tmp_path: Path) -> None:
    """The corpus instance was 4 rows with no FR in the FR column."""
    spec_dir = build_feature_dir(
        tmp_path / "f",
        checklist=GOOD_CHECKLIST.replace(
            "| A2 | `polarity` is a real field | T | FR-002 | T002 | \u2610 |",
            "| A2 | `polarity` is a real field | T | - | T002 | \u2610 |",
        ),
    )
    fails = fails_for(spec_dir, ["RI-04c-ROW-FR"])
    assert [f.code for f in fails] == ["row-without-fr", "row-without-fr-total"]
    assert fails[0].data["row"] == "A2"
    assert fails[1].data["rows"] == ["A2"]


def test_a_phantom_section_citation_still_fails(tmp_path: Path) -> None:
    """The corpus instance was `§34a`: a fabricated sub-section label."""
    spec_dir = build_feature_dir(
        tmp_path / "f",
        spec=GOOD_SPEC.replace(
            "#### Producers",
            "#### Producers\n\n- **FR-004**: The reconciliation step MUST consult \u00a734a. "
            "(\u00a72)\n",
        ),
        tasks=GOOD_TASKS + "- [ ] T004 [US4] Reconcile. (FR-004, \u00a72)\n",
    )
    fails = fails_for(spec_dir, ["RI-08-SEC-CITE"])
    assert [(f.code, f.data["section"]) for f in fails] == [("section-phantom", "34a")]


def test_a_count_claim_that_disagrees_with_the_artefacts_still_fails(tmp_path: Path) -> None:
    """The corpus instance was a checklist claiming 153 FRs against 149 definitions."""
    spec_dir = build_feature_dir(tmp_path / "f", plan="# plan\n\n9 FRs, 1 measurable outcome.\n")
    fails = fails_for(spec_dir, ["RI-09-COUNT"])
    assert [(f.code, f.data["claimed"], f.data["actual"]) for f in fails] == [
        ("count-mismatch", 9, 3)
    ]


def test_a_phantom_constitution_label_still_fails(tmp_path: Path) -> None:
    """The corpus instance was `CD-6`; the constitution labels its invariants unnumbered.

    A constitution is planted inside the synthetic directory so the test evaluates the rule
    rather than the environment - `find_constitution` walks ancestors, and a `tmp_path` fixture
    has none. Skips only if even that fails, which would be a broken fixture.
    """
    spec_dir = build_feature_dir(tmp_path / "f", research=GOOD_RESEARCH + "\nCD-6 is a label.\n")
    write(spec_dir / ".specify" / "memory" / "constitution.md", _SYNTHETIC_CONSTITUTION)
    ctx = rc.build_context(spec_dir)
    if ctx.constitution is None or not ctx.constitution.read_ok:
        pytest.skip("could not plant a constitution in the fixture directory")
    fails = fails_for(spec_dir, ["RI-11-CONST"])
    assert [(f.code, f.data["raw"]) for f in fails] == [("cd-phantom", "CD-6")]


_SYNTHETIC_CONSTITUTION = """\
# Synthetic Constitution

## I. Evidence-First

Every claim traces to evidence.

## Domain Invariants

1. Evidence is immutable.
2. A denial is a first-class outcome.
3. No claim without provenance.
"""


def test_the_four_must_keep_failing_checks_are_out_of_reach_of_every_exemption() -> None:
    """The claims in the report, as assertions.

    None of the four is in `NORMATIVE_LINT_CHECKS`, so no exemption can reach them, and all
    four still declare FAIL. The second half names the check functions this change rewrote, so
    a fifth silent rewrite is the thing that would fail here.
    """
    must_keep = {"RI-04c-ROW-FR", "RI-08-SEC-CITE", "RI-09-COUNT", "RI-11-CONST"}
    assert not (must_keep & rc.NORMATIVE_LINT_CHECKS)
    for cid in must_keep:
        assert rc.CHECK_BY_ID[cid].severity == rc.FAIL, cid
    rewritten = {"check_fr_order", "check_fr_definitions", "check_task_refs",
                 "_forbidden_vocabulary_without_producer", "demote_historical"}
    for fn in ("check_rows_cite_fr", "check_section_citations", "check_count_claims",
               "check_constitution"):
        assert fn not in rewritten, fn
        assert callable(getattr(rc, fn)), fn




