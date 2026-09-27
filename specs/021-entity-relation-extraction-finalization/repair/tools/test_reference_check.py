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
    codes = {f.code for f in fails_for(spec_dir, ["RI-10-FORBIDDEN"])}
    assert "synonym-in-identity" in codes, codes
    assert "nested-hypothesis" in codes, codes
    assert "vocabulary-without-producer" in codes, codes


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
    ctx = rc.build_context(SPEC_DIR)
    art = ctx.by_name("spec.md")
    sc15 = next(d for d in ctx.defs if d.ident == "SC-015")
    window = rc._claim_window(art, sc15.line, ctx.defs)
    assert window.startswith("The constitutional mutation harness breaks")
    assert "SC-016" not in window
    assert "SC-014" not in window


def test_line_of_maps_offsets_to_one_based_lines() -> None:
    art = rc.read_artefact("spec.md", SPEC_DIR / "spec.md")
    assert rc._line_of(art, 0) == 1
    assert rc._line_of(art, art.text.index("FR-001")) == 376
    assert rc._line_of(art, len(art.text) - 1) == art.line_count


def test_small_helpers() -> None:
    assert rc._section_in_line("see \u00a794\u2013\u00a7101 for detail") == "94"
    assert rc._section_in_line("no section here") is None
    assert rc._first_sentence("a b. c d", 0) == "a b"
    assert rc._as_int("four") == 4
    assert rc._as_int("banana") is None
    assert rc._topic_terms("Process-Centric") == {"process", "centric"}


def test_harness_field_count_matches_the_enumerated_list() -> None:
    ctx = rc.build_context(SPEC_DIR)
    assert rc._harness_field_counts(ctx) == {"FR-078": 18}


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
    labels = {f.data["raw"] for f in findings_for(SPEC_DIR, ["RI-11-CONST"])
              if f.code == "cd-phantom"}
    if not labels:
        pytest.skip("no phantom CD labels remain")
    assert labels == {"CD-6", "CD-7"}


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
    assert rc.TOMBSTONED_FRS == {
        "FR-034a": "INV-002",
        "FR-058": "INV-004",
        "FR-070": "design note",
        "FR-079": "FR-078",
        "FR-080": "FR-072",
    }


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


def test_fr_defined_twice_in_two_repair_documents_fails(tmp_path: Path) -> None:
    """The real defect: A2 and A6 each invented FR-101 with a different requirement."""
    spec_dir = build_repair_dir(build_feature_dir(tmp_path / "f"),
                               **{"A2-identity": _A2_STYLE, "A6-triage": _A6_STYLE})
    fails = fails_for(spec_dir, ["FR-NAMESPACE-COLLISION"])
    assert [f.code for f in fails] == ["fr-namespace-collision"]
    assert fails[0].data["fr"] == "FR-101"
    assert fails[0].data["shape"] == "repair-vs-repair"
    assert fails[0].data["kinds"] == ["new-requirement", "redefinition"]
    assert fails[0].locations == ["repair/A2-identity.md:3", "repair/A6-triage.md:3"]
    # both texts are quoted, so a reader can adjudicate without opening either file
    texts = {s["artefact"]: s["text"] for s in fails[0].data["sites"]}
    assert "PredicateSignature" in texts["repair/A2-identity.md"]
    assert "entity extraction layer" in texts["repair/A6-triage.md"]


def test_repair_document_redefining_a_spec_fr_fails(tmp_path: Path) -> None:
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
    fails = fails_for(spec_dir, ["FR-NAMESPACE-COLLISION"])
    assert [f.data["fr"] for f in fails] == ["FR-004"]
    assert fails[0].data["shape"] == "spec-vs-repair"
    assert fails[0].data["kinds"] == ["canonical-definition", "rewrite-proposal"]
    assert fails[0].locations == ["spec.md:20", "repair/A6-triage.md:1"]


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
    spec_dir = build_repair_dir(
        build_feature_dir(tmp_path / "f"),
        **{"A6-triage": "> producers/readers for all seven classes of §8:\n"},
    )
    warns = [f for f in findings_for(spec_dir, ["COUNT-PRECISION"]) if f.severity == rc.WARN]
    assert [f.code for f in warns] == ["count-seven-classes"]
    assert warns[0].data["phrase"] == "all seven classes"
    assert warns[0].locations == ["repair/A6-triage.md:1"]


def test_count_precision_flags_seven_classes_in_a_test_name(tmp_path: Path) -> None:
    spec_dir = build_repair_dir(
        build_feature_dir(tmp_path / "f"),
        **{"A6-triage": ("| T114 | entity extractor expansion | "
                         "`test_entity_extractor_covers_all_seven_classes` |\n")},
    )
    warns = [f for f in findings_for(spec_dir, ["COUNT-PRECISION"]) if f.severity == rc.WARN]
    assert [f.code for f in warns] == ["count-seven-classes"]


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


def test_tripwire_tombstone_gate_is_red_today() -> None:
    fails = fails_for(SPEC_DIR, ["TOMBSTONED-FR-REF"])
    if not fails:
        pytest.skip("the tombstone set has no normative reference left")
    cited = {(f.data["fr"], f.locations[0]) for f in fails}
    assert ("FR-058", "tasks.md:143") in cited
    assert ("FR-034a", "spec.md:514") in cited
    assert next(f for f in fails if f.data["fr"] == "FR-079").data["replacement"] == "FR-078"


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


def test_tripwire_a6_routes_structural_conflict_into_contradicted() -> None:
    fails = fails_for(SPEC_DIR, ["EPISTEMIC-AXIS-CONFLATION"])
    if not fails:
        pytest.skip("no epistemic-axis conflation remains")
    locs = {loc for f in fails for loc in f.locations}
    assert {"repair/A6-fr-triage.md:187", "spec.md:737", "tasks.md:128"} <= locs


def test_tripwire_d7_miscount_and_the_seven_classes_phrase() -> None:
    warns = [f for f in findings_for(SPEC_DIR, ["COUNT-PRECISION"]) if f.severity == rc.WARN]
    if not warns:
        pytest.skip("the four authority numbers are no longer conflated")
    phrases = {f.data["phrase"] for f in warns}
    assert "32 type classes" in phrases
    assert "all seven classes" in phrases


def test_tripwire_ghost_suffixes_are_still_cited() -> None:
    warns = [f for f in findings_for(SPEC_DIR, ["GHOST-SUFFIX"]) if f.severity == rc.WARN]
    if not warns:
        pytest.skip("every letter-suffixed FR has been folded")
    assert {f.data["fr"] for f in warns} == {"FR-034a", "FR-039a"}
    assert all(f.locations for f in warns)
