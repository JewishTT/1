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
