#!/usr/bin/env python3
"""Bidirectional reference-integrity checker for a Speckit feature artefact set.

This is spec tooling, not product code. It lives under ``repair/tools/`` so it never
pollutes ``apps/``.

The checker's contract is deliberately narrow and loud:

* a reference that is **cited but never defined** is a FAIL (this is the ``FR-103`` class
  of defect that previously passed a gate);
* a definition that is **defined but never cited** is an ORPHAN and a FAIL;
* anything that cannot be parsed is a finding, never an exception;
* a run that produces no FAIL is the only way to say "this artefact set is sound".

Standard library only. Python >= 3.11.

Usage
-----
    python specs/<feature>/repair/tools/reference_check.py            # text report
    python specs/<feature>/repair/tools/reference_check.py --json     # machine report
    python specs/<feature>/repair/tools/reference_check.py --warn-only
    python specs/<feature>/repair/tools/reference_check.py --compare old.json

Exit codes: 0 = no FAIL, 1 = FAIL findings present, 2 = could not run.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TOOL_VERSION = "1.2.0"

# --------------------------------------------------------------------------------------
# Severity
# --------------------------------------------------------------------------------------

FAIL = "FAIL"
WARN = "WARN"
INFO = "INFO"
SEVERITIES = (FAIL, WARN, INFO)
SEVERITY_RANK = {FAIL: 0, WARN: 1, INFO: 2}


# --------------------------------------------------------------------------------------
# Finding / check registry
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CheckSpec:
    """Static metadata for one addressable check."""

    check_id: str
    title: str
    severity: str
    rule: str


@dataclass
class Finding:
    check_id: str
    severity: str
    code: str
    message: str
    locations: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "locations": list(self.locations),
            "data": self.data,
        }


CHECKS: tuple[CheckSpec, ...] = (
    CheckSpec(
        "RI-00-INPUT",
        "Artefact set is present, decodable and non-empty",
        FAIL,
        "Every scanned artefact and every authority file exists, decodes as UTF-8 and has "
        "content. A missing or empty artefact makes every other check meaningless, so this "
        "is FAIL and it is reported first.",
    ),
    CheckSpec(
        "RI-01-FR-DEF",
        "Every cited FR is defined exactly once in spec.md",
        FAIL,
        "An `FR-nnn` (or suffixed `FR-034a`) token appearing in any artefact must have "
        "exactly one `- **FR-nnn**:` definition in spec.md. Cited-but-undefined and "
        "defined-twice are both FAIL.",
    ),
    CheckSpec(
        "RI-01b-FR-SHAPE",
        "FR identifier shape and duplicate suffixes",
        FAIL,
        "FR ids must be `FR-` + 3 digits, except for deliberately letter-suffixed variants "
        "that are defined exactly once. Two FRs sharing a base and a suffix, or a base "
        "carrying two different suffixes, is FAIL. Malformed (unpadded) FR tokens are WARN.",
    ),
    CheckSpec(
        "RI-02-TASK-REF",
        "Every cited task id exists in tasks.md",
        FAIL,
        "Any `Tnnn` (optionally letter-suffixed) token cited in any artefact must be defined "
        "by a `- [ ] Tnnn` bullet in tasks.md. Phantom task ids are FAIL: a checklist row "
        "gated on T007f is a gate on nothing.",
    ),
    CheckSpec(
        "RI-03-FR-ORPHAN",
        "No orphan FR (defined, cited by neither tasks.md nor the checklist)",
        FAIL,
        "An FR is an ORPHAN when spec.md defines it and neither tasks.md nor "
        "checklists/requirements.md references it. An orphan requirement has no "
        "implementation and no gate.",
    ),
    CheckSpec(
        "RI-03b-FR-UNCITED",
        "No FR is cited by no artefact at all",
        FAIL,
        "Stricter than RI-03: the FR appears in no other artefact, so it is not merely "
        "ungated, it is unreferenced prose wearing a requirement id.",
    ),
    CheckSpec(
        "RI-03c-FR-COLUMN",
        "The checklist maps requirements to FRs",
        FAIL,
        "checklists/requirements.md must carry an FR/requirement column and map at least one "
        "FR per row. A checklist with no FR column maps zero requirements and is a FAIL in "
        "its own right, distinct from the orphan count.",
    ),
    CheckSpec(
        "RI-04-TASK-FR",
        "Every task cites at least one FR",
        FAIL,
        "A task with no FR citation cannot be traced to a requirement, so nothing enforces "
        "it and nothing can fail if it is wrong.",
    ),
    CheckSpec(
        "RI-04b-ROW-TASK",
        "Every checklist row cites at least one defined task",
        FAIL,
        "Each checklist row's Task column must name at least one task that exists in "
        "tasks.md. Free text (`existing suites`) is a FAIL because it cannot be run.",
    ),
    CheckSpec(
        "RI-04c-ROW-FR",
        "Every checklist row cites at least one FR",
        FAIL,
        "Each checklist row must name at least one FR so that the item is traceable to a "
        "requirement. Reported per row; the aggregate is RI-03c.",
    ),
    CheckSpec(
        "RI-04d-FR-OWNER",
        "Every FR has exactly one semantic owner",
        WARN,
        "An FR cited by zero tasks is an orphan (RI-03). An FR cited by two or more tasks has "
        "no single semantic owner: a change to the FR has no single blast radius. WARN, "
        "because shared ownership is sometimes intentional.",
    ),
    CheckSpec(
        "RI-05-MISCITE",
        "FR mis-citation suspicion (heuristic, never a hard failure)",
        WARN,
        "An FR citation is SUSPECT when the citing line and the cited FR share no "
        "meaningful term (identifier, code span, dotted path, enum member). Reported as a "
        "ranked list. Purely heuristic: 0 shared terms is evidence of a bad citation, not "
        "proof, so severity is WARN.",
    ),
    CheckSpec(
        "RI-05b-INVERSE-CITE",
        "A task citing an FR in order to violate it",
        WARN,
        "When the citing line forbids or removes a literal that the cited FR places inside a "
        "MUST-contain clause, the citation is inverted: the task is a counterexample to the "
        "requirement it names. WARN because the intent may be deliberate.",
    ),
    CheckSpec(
        "RI-06-TASK-ORDER",
        "Task ids are contiguous, ascending and unsuffixed",
        FAIL,
        "Task ids must run T001..Tnnn with no gap, no reordering and no letter suffix. A "
        "letter-suffixed task id is by definition not in the file's own definition set, so "
        "it is a phantom waiting to happen.",
    ),
    CheckSpec(
        "RI-06b-FR-ORDER",
        "FR numbering is monotonic within its requirement section",
        FAIL,
        "Within each spec.md requirement section, FR numbers must be strictly increasing, and "
        "in document order across the whole file. A gap, a rewind, or an FR bullet dangling "
        "after a table rather than grouped with the other requirements is FAIL.",
    ),
    CheckSpec(
        "RI-07-SC-COVER",
        "Every SC is referenced by at least one checklist item",
        FAIL,
        "Each `SC-nnn` defined in spec.md must be named by at least one checklist row. An "
        "uncovered success criterion is a success criterion nobody is measured against.",
    ),
    CheckSpec(
        "RI-07b-INV-COVER",
        "Every INV is referenced by at least one checklist item",
        FAIL,
        "Each `INV-nnn` defined in spec.md must be named by at least one checklist row. A "
        "constitutional invariant with no checklist row is unenforced by construction.",
    ),
    CheckSpec(
        "RI-07c-ID-SHAPE",
        "SC / INV citations are canonically shaped",
        WARN,
        "A citation to an SC or INV that is not zero-padded to three digits (e.g. `INV-3`) "
        "will not match a canonical id and is therefore a silent phantom. WARN.",
    ),
    CheckSpec(
        "RI-08-SEC-CITE",
        "Every cited section exists as a heading in input.md or in the citing artefact",
        FAIL,
        "A `§N` citation is resolved against two namespaces, because the feature artefacts "
        "number themselves as well as citing the brief. `§0`…`§114` with an integer label is "
        "input.md's namespace and must resolve to a numbered heading there. A token that "
        "instead names a heading *inside the artefact it appears in* (`§1.5` against `### 1.5` "
        "in the same file) is that document's own cross-reference and is not a claim about "
        "input.md, so it is not a phantom. A token that resolves in neither namespace is "
        "FAIL - including a fabricated sub-section label such as `§1B` (input.md's §1 has "
        "unnumbered subsections A and B, so `§1B` is not a section) and an integer that exists "
        "nowhere. When an integer resolves only against the citing artefact, the ambiguity is "
        "reported INFO rather than hidden. Ranges (`§94-§101`) are checked at both endpoints; "
        "a `§N-k` phase qualifier at its base section only.",
    ),
    CheckSpec(
        "RI-08b-SEC-UNCITED",
        "input.md sections that no artefact cites",
        INFO,
        "The reverse direction. A section of the governing brief that no artefact cites is "
        "either deliberately out of scope or silently dropped (e.g. the entity-extractor "
        "expansion). INFO: the report is a review prompt, not a gate.",
    ),
    CheckSpec(
        "RI-09-COUNT",
        "Prose count claims agree with the artefacts",
        FAIL,
        "Numeric and number-word claims in prose are recomputed from the artefacts: file line "
        "counts, section counts, FR/SC/INV/story populations, enumerated member/level/"
        "mutation/field/prefix counts. A claim that can be recomputed and disagrees is FAIL. A "
        "claim that cannot be recomputed is reported INFO as `count-unverifiable` so the gap "
        "is visible rather than silent.",
    ),
    CheckSpec(
        "RI-10-FORBIDDEN",
        "Known-forbidden claims are absent",
        FAIL,
        "Three shapes that a previous repair pass is forbidden to reintroduce: (a) a synonym "
        "/equivalence table inside the identity path, (b) a hypothesis that contains a "
        "*collection of hypotheses*, (c) a vocabulary list with no producer obligation. All "
        "three are FAIL. (b) is decided on the field's *type shape*, not its name: a scalar "
        "`hypothesis_state: HypothesisState` is brief §6's required field and is legal, while "
        "`hypotheses: tuple[TypeHypothesis, ...]` - any collection-typed field whose element is "
        "a `*Hypothesis`, or a `hypotheses`-named field typed as any collection - is a new "
        "epistemic level. A field typed as a plain hypothesis and *not* a collection is out of "
        "scope for this rule by design.",
    ),
    CheckSpec(
        "RI-11-CONST",
        "Constitution reference integrity",
        FAIL,
        "References to the project constitution must resolve. A `CD-n` domain-invariant "
        "label that exists nowhere in the constitution is a phantom (FAIL). A roman-numeral "
        "principle followed by a topic word must share a content word with that principle's "
        "actual title, otherwise the citation is reported as a suspected mis-cite (WARN).",
    ),
    CheckSpec(
        "RI-11b-RESEARCH",
        "Research decision ids (R-nnn) resolve",
        FAIL,
        "An `R-nnn` cited in any artefact must be defined by a `## R-nnn.` heading in "
        "research.md. A phantom R-nnn is FAIL.",
    ),
    CheckSpec(
        "RI-12-STALE",
        "No stale artefact-status claims",
        FAIL,
        "A line claiming a file or directory is `NOT yet created` / `NOT yet generated` while "
        "that path exists is FAIL. The artefact set lies about itself and a reader sizing the "
        "remaining work from it is wrong.",
    ),
    CheckSpec(
        "TOMBSTONED-FR-REF",
        "No artefact cites a tombstoned FR as a live normative target",
        FAIL,
        "`repair/ARBITRATION.md` §2 tombstoned `FR-034a`, `FR-058`, `FR-070`, `FR-079` and "
        "`FR-080`: a tombstone exists for historical traceability only. Every citation of a "
        "tombstoned id in spec.md / plan.md / tasks.md / data-model.md / "
        "checklists/requirements.md / research.md is FAIL - as a citation and as a normative "
        "definition - unless the citing line itself carries a deprecation marker (tombstone, "
        "deprecated, absorbed into, merged into, see ADR, ...). Each violation names the "
        "replacement target the arbitration record assigns.",
    ),
    CheckSpec(
        "FR-NAMESPACE-COLLISION",
        "No FR number is claimed by two owners",
        FAIL,
        "`spec.md` and every `repair/*.md` are scanned for FR *definition* sites. An id defined "
        "at two sites with different requirement text is a namespace collision and is FAIL, "
        "whether both sites are repair documents (the same id invented twice) or one is "
        "`spec.md` and one is a repair document (an FR number claimed by a second owner). Both "
        "texts and both file:line locations are quoted. A fenced code block is quoted material, "
        "never a definition. Two sites whose text is byte-identical after normalisation are "
        "reported INFO, not FAIL.",
    ),
    CheckSpec(
        "EPISTEMIC-AXIS-CONFLATION",
        "The three epistemic axes are not conflated",
        FAIL,
        "`repair/ARBITRATION.md` §3 fixes three distinct states: "
        "`PredicateHypothesis.resolution_state = CONFLICTING` (semantic readings), "
        "`RelationCandidate.assembly_state` (structural readings - arity, direction, polarity, "
        "role slots), and `CandidateStatus.CONTRADICTED` (the assertion itself is denied). Any "
        "prose unit in spec.md, tasks.md or a repair document that associates a structural "
        "disagreement term with `CONTRADICTED` is FAIL, because it instructs writing a "
        "structural disagreement into the denial state; the correct target is "
        "`assembly_state = CONFLICTING`. A sentence that carries a prohibition marker "
        "(forbidden, never, must not, rather than) is stating the rule, not breaking it.",
    ),
    CheckSpec(
        "COUNT-PRECISION",
        "The four authority numbers are never conflated",
        WARN,
        "Four numbers each count one thing and are not interchangeable: 31 foundational entity "
        "types, 13 value types, 7 §8 extraction families, ~4 new instrument modules. WARN on "
        "(a) `32` qualifying an atomic/entity/type/class/extractor/item noun, and (b) "
        "`seven classes` / `all seven classes` / `seven_classes` in a §8 or entity-extractor "
        "context - the correct phrase is `extraction families` or `§8 subsections`. A unit that "
        "carries a refutation marker (corrected, miscount, misreading, renamed, `not 32`) is "
        "stating the correction and is reported INFO, not WARN.",
    ),
    CheckSpec(
        "GHOST-SUFFIX",
        "No live normative citation to a letter-suffixed FR",
        WARN,
        "`FR-034a` and `FR-039a` are a transitional device: they force every id regex to accept "
        "a lowercase suffix and leave the namespace speaking two styles at once. WARN on every "
        "live citation of a `FR-nnn<letter>` id outside a fenced code block and outside a "
        "deprecation-marked line, so the ids can be folded into their allocated slot rather than "
        "left as ghosts. A fence is quotation, on the same rule "
        "`FR-NAMESPACE-COLLISION` uses. WARN, not FAIL: each suffixed id is currently defined "
        "exactly once, so nothing dangles yet.",
    ),
)

CHECK_BY_ID = {c.check_id: c for c in CHECKS}


# --------------------------------------------------------------------------------------
# Artefact set
# --------------------------------------------------------------------------------------

SCANNED_ARTEFACTS: tuple[str, ...] = (
    "spec.md",
    "tasks.md",
    "plan.md",
    "research.md",
    "data-model.md",
    "checklists/requirements.md",
)

# `phase0-results.md` is a prior *review report*, not a spec artefact: it quotes the
# phantom ids it is complaining about, so scanning it by default would double-count
# them. Pass `--artefact phase0-results.md` to include it.
OPTIONAL_ARTEFACTS: tuple[str, ...] = ("phase0-results.md",)

AUTHORITY_ARTEFACTS: tuple[str, ...] = ("input.md",)

CONSTITUTION_RELPATH = Path(".specify/memory/constitution.md")

# `repair/*.md` is the *governance* corpus: the agent reports and the arbitration record.
# It is deliberately NOT part of SCANNED_ARTEFACTS, so no RI-* check changes scope; the
# checks that need it read it through `Context.repair` / `Context.governance`.
REPAIR_DIR_RELPATH = "repair"


@dataclass
class Artefact:
    name: str
    path: Path
    text: str
    lines: list[str]
    read_ok: bool
    error: str = ""

    @property
    def line_count(self) -> int:
        return len(self.lines)

    def loc(self, line_no: int) -> str:
        return f"{self.name}:{line_no}"


def read_artefact(name: str, path: Path) -> Artefact:
    """Read an artefact, degrading every failure mode into a readable object."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return Artefact(name, path, "", [], False, f"unreadable: {exc}")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        text = raw.decode("utf-8", errors="replace")
        return Artefact(name, path, text, text.splitlines(), False, f"not utf-8: {exc}")
    return Artefact(name, path, text, text.splitlines(), True)


def find_spec_dir(start: Path | None = None) -> Path | None:
    """Locate the feature directory: the first ancestor holding spec.md and input.md."""
    here = (start or Path(__file__)).resolve()
    for cand in [here, *here.parents]:
        if cand.is_dir() and (cand / "spec.md").is_file() and (cand / "input.md").is_file():
            return cand
    return None


def find_constitution(spec_dir: Path) -> Path | None:
    for parent in [spec_dir, *spec_dir.parents]:
        cand = parent / CONSTITUTION_RELPATH
        if cand.is_file():
            return cand
    return None


def read_repair_docs(spec_dir: Path) -> list[Artefact]:
    """Every `repair/*.md`, sorted by name, as readable artefacts.

    Missing directory or unreadable file is not an exception: an unreadable artefact simply
    contributes no lines, and a missing `repair/` contributes nothing at all.
    """
    out: list[Artefact] = []
    repair_dir = spec_dir / REPAIR_DIR_RELPATH
    try:
        paths = sorted(repair_dir.glob("*.md")) if repair_dir.is_dir() else []
    except OSError:
        return out
    for p in paths:
        out.append(read_artefact(f"{REPAIR_DIR_RELPATH}/{p.name}", p))
    return out


# --------------------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------------------

DEF_RE = re.compile(
    r"^[ \t]{0,10}(?:[-*+]\s+|\d+[.)]\s+)?\*\*"
    r"(?P<ident>(?:FR|SC|INV)-\d+[A-Za-z]?)\*\*\s*[:\u2014-]",
)
TASK_DEF_RE = re.compile(
    r"^[ \t]{0,10}(?:[-*+]\s+)\[[ xX]\]\s*(?P<ident>T\d+[A-Za-z]?)\b(?P<rest>.*)$"
)
CHECKLIST_ROW_RE = re.compile(r"^\|\s*(?P<ident>[A-Za-z]{1,3}\d{1,3})\s*\|(?P<rest>.*)$")
TABLE_SEP_RE = re.compile(r"^\|[\s:|-]+\|$")
FR_TOKEN_RE = re.compile(r"\bFR-\d+[A-Za-z]?\b")
SC_TOKEN_RE = re.compile(r"\bSC-\d+[A-Za-z]?\b")
INV_TOKEN_RE = re.compile(r"\bINV-\d+[A-Za-z]?\b")
TASK_TOKEN_RE = re.compile(r"\bT\d+[A-Za-z]?\b")
RESEARCH_TOKEN_RE = re.compile(r"\bR-\d{3}\b")
CD_TOKEN_RE = re.compile(r"\bCD-\d+\b")
HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<rest>.*?)\s*$")
INPUT_SECTION_RE = re.compile(r"^(?P<num>\d+(?:\.\d+)*)\.?\s+\S")
INPUT_SUBSECTION_RE = re.compile(r"^([A-Z])\.\s+\S")
PRINCIPLE_RE = re.compile(
    r"^#{1,6}\s*(?P<num>[IVXL]+)\.\s*(?P<title>\S.*?)\s*$", re.MULTILINE
)
STORY_RE = re.compile(r"^#{1,6}\s*User\s+Story\s+(\d+)\b", re.MULTILINE)
RESEARCH_DEF_RE = re.compile(r"^#{1,6}\s*R-(?P<num>\d{3})\b", re.MULTILINE)
CODE_SPAN_RE = re.compile(r"`(?P<body>[^`\n]{1,200})`")
DASHES = "-‐‑‒–—―−"
SECTION_RE = re.compile(
    r"§{1,2}\s*(?P<a>\d+(?:\.\d+)?[A-Za-z]?)"
    rf"(?:\s*[{DASHES}]\s*§?\s*(?P<b>\d+(?:\.\d+)?[A-Za-z]?))?"
)
COUNT_CLAUSE_RE = re.compile(r"\b(\d[\d,]*)\s+(?P<noun>lines)\b")
SECTIONS_CLAUSE_RE = re.compile(r"\b(\d[\d,]*)\s+(?P<noun>sections)\b")
MUTATION_RANGE_RE = re.compile(
    r"§\s*(?P<lo>\d+)\s*[" + DASHES + r"]\s*§?\s*(?P<hi>\d+)"
)
# A `§A-§B` / `§A-B` *range* is a locator, not a count. Its endpoints are section numbers,
# so "The six §94-§99 mutations" claims six, not ninety-nine. Any integer inside such a span
# is a section label and must never be read as a claimed population.
SECTION_RANGE_SPAN_RE = re.compile(
    r"§{1,2}\s*\d+(?:\.\d+)?\s*[" + DASHES + r"]\s*§?\s*\d+(?:\.\d+)?"
)
FILE_REF_RE = re.compile(
    r"(?P<path>(?:[A-Za-z0-9_.\-]+[\\/])*[A-Za-z0-9_.\-]+\.(?:md|py|json|ya?ml|txt|toml))"
)
STALE_RE = re.compile(r"\bNOT\s+yet\s+(?:created|generated|written|produced)\b", re.IGNORECASE)
_PATH_TOKEN_RE = re.compile(r"(?:[A-Za-z0-9_.\-]+[\\/]?)+")

_NUMWORDS = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
}
_COUNT_NOUN_RE = re.compile(
    r"(?P<num>\d{1,4}|[A-Za-z]+)"
    r"(?:\s+(?P<qual>distinct|separate|independent|named|top-level|measurable|hard"
    r"|testable|new|existing|open|mandatory|total|complete|constitutional|functional"
    r"|user|golden))?"
    r"\s+(?P<noun>constitutional\s+invariants?|functional\s+requirements?|success\s+criteria"
    r"|measurable\s+outcomes?|user\s+stories|golden\s+cases|FRs?|SCs?|INVs?|stories"
    r"|requirements|levels|members|mutations|invariants|prefixes)\b",
    re.IGNORECASE,
)


@dataclass
class Definition:
    ident: str
    line: int
    body: str
    section: str
    block: str = ""


@dataclass
class TaskDef:
    ident: str
    line: int
    text: str
    section: str
    phase: str = ""


@dataclass
class ChecklistRow:
    ident: str
    line: int
    cells: list[str]
    columns: list[str]
    text: str
    section: str


def _section_walk(lines: Sequence[str]) -> list[tuple[int, str, str]]:
    """Return (line_no, level, title) for every ATX heading, skipping fenced code."""
    out: list[tuple[int, str, str]] = []
    fence: str | None = None
    for i, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            token = stripped[:3]
            if fence is None:
                fence = token
            elif stripped.startswith(fence):
                fence = None
            continue
        if fence is not None:
            continue
        m = HEADING_RE.match(line)
        if m:
            out.append((i, len(m.group("hashes")), m.group("rest")))
    return out


def _enclosing_heading(headings: Sequence[tuple[int, str, str]], line_no: int) -> str:
    stack: list[tuple[int, str]] = []
    for hline, level, title in headings:
        if hline > line_no:
            break
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
    return " > ".join(t for _, t in stack)


def parse_definitions(art: Artefact, heading_depth: int) -> tuple[list[Definition],
                                                                 list[Definition]]:
    """Parse `- **FR-nnn**: body` definitions.

    Returns (unique, occurrences): `unique` keeps the first definition of each id (what
    every other check wants), `occurrences` keeps every definition site so a requirement
    defined twice is still visible.
    """
    headings = _section_walk(art.lines)
    occurrences: list[Definition] = []
    lines = art.lines
    for i, line in enumerate(lines):
        m = DEF_RE.match(line)
        if not m:
            continue
        ident = m.group("ident")
        body_parts = [line[m.end():]]
        for j in range(i + 1, len(lines)):
            nxt = lines[j]
            if not nxt.strip():
                body_parts.append("")
                continue
            if DEF_RE.match(nxt) or TASK_DEF_RE.match(nxt) or HEADING_RE.match(nxt):
                break
            body_parts.append(nxt)
        block = "\n".join(body_parts).strip()
        occurrences.append(
            Definition(
                ident=ident,
                line=i + 1,
                body=block,
                section=_enclosing_heading(headings, i + 1),
                block=block,
            )
        )
    unique: list[Definition] = []
    seen: set[str] = set()
    for d in occurrences:
        if d.ident in seen:
            continue
        seen.add(d.ident)
        unique.append(d)
    _ = heading_depth
    return unique, occurrences


def parse_tasks(art: Artefact) -> list[TaskDef]:
    headings = _section_walk(art.lines)
    fence: str | None = None
    out: list[TaskDef] = []
    for i, line in enumerate(art.lines):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            token = stripped[:3]
            fence = None if fence == token else (token if fence is None else fence)
            continue
        if fence is not None:
            continue
        m = TASK_DEF_RE.match(line)
        if not m:
            continue
        out.append(
            TaskDef(
                ident=m.group("ident"),
                line=i + 1,
                text=(m.group("ident") + m.group("rest")).strip(),
                section=_enclosing_heading(headings, i + 1),
                phase=_phase_of(_enclosing_heading(headings, i + 1)),
            )
        )
    return out


def _phase_of(section: str) -> str:
    for part in section.split(" > "):
        if part.lower().startswith("phase "):
            return part
    return ""


CHECKLIST_HEADER_STARTS = {"#", "item", "item(s)", "checklist item", "id", "no", "no.", "key"}


def parse_checklist(art: Artefact) -> tuple[list[ChecklistRow], list[list[str]]]:
    """Parse the gate checklist's tables. Returns (rows, header_rows_found).

    Table-driven, not guess-driven: a row belongs to the gate checklist when the most
    recent header of its table declares a `Task` column. That is what distinguishes
    `| A5 | Tenancy: no cross-tenant write | T | existing suites |` (a real gate row
    that names no runnable task) from a lookup table in spec.md.
    """
    headings = _section_walk(art.lines)
    rows: list[ChecklistRow] = []
    headers: list[list[str]] = []
    columns: list[str] = []
    has_task_col = False
    fence: str | None = None
    for i, line in enumerate(art.lines, start=1):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            token = stripped[:3]
            fence = None if fence == token else (token if fence is None else fence)
            continue
        if fence is not None:
            continue
        if not line.startswith("|"):
            columns, has_task_col = [], False
            continue
        if TABLE_SEP_RE.match(line.strip()):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and cells[0].lower() in CHECKLIST_HEADER_STARTS:
            columns = cells
            has_task_col = any(re.search(r"\btasks?\b", c, re.IGNORECASE) for c in cells)
            headers.append(cells)
            continue
        if not has_task_col:
            continue
        m = CHECKLIST_ROW_RE.match(line)
        if not m:
            continue
        rows.append(
            ChecklistRow(
                ident=m.group("ident"),
                line=i + 1,
                cells=cells,
                columns=list(columns),
                text=" ".join(cells),
                section=_enclosing_heading(headings, i + 1),
            )
        )
    return rows, headers



# --------------------------------------------------------------------------------------
# Reference extraction
# --------------------------------------------------------------------------------------


def _iter_tokens(art: Artefact, pattern: re.Pattern[str]):
    for i, line in enumerate(art.lines, start=1):
        for m in pattern.finditer(line):
            yield m.group(0), i


def collect_references(arts: Sequence[Artefact]) -> dict[str, dict[str, list[str]]]:
    """refs[artefact_name][token] = sorted list of 'file:line' locations."""
    patterns = {
        "FR": FR_TOKEN_RE,
        "SC": SC_TOKEN_RE,
        "INV": INV_TOKEN_RE,
        "TASK": TASK_TOKEN_RE,
        "RESEARCH": RESEARCH_TOKEN_RE,
        "CD": CD_TOKEN_RE,
    }
    out: dict[str, dict[str, list[str]]] = {}
    for art in arts:
        bucket: dict[str, list[str]] = defaultdict(list)
        for kind, pat in patterns.items():
            for token, line_no in _iter_tokens(art, pat):
                bucket[f"{kind}:{token}"].append(art.loc(line_no))
        for key in bucket:
            bucket[key] = sorted(set(bucket[key]), key=_loc_key)
        out[art.name] = dict(bucket)
    return out


def _loc_key(loc: str) -> tuple[str, int]:
    name, _, line = loc.rpartition(":")
    try:
        return (name, int(line))
    except ValueError:
        return (name, 0)


def collect_sections(art: Artefact) -> list[dict[str, Any]]:
    """Every §-citation with resolved endpoints.

    `§110-8` is a phase qualifier, not a range: the trailing number is *smaller* than
    the base, so only the base section is validated. Recording the qualifier as an
    endpoint would make `§110-8` look like a citation of `§8`.
    """
    out: list[dict[str, Any]] = []
    for i, line in enumerate(art.lines, start=1):
        for m in SECTION_RE.finditer(line):
            a = m.group("a")
            b = m.group("b")
            entry: dict[str, Any] = {"raw": m.group(0), "line": i, "endpoints": [a],
                                     "kind": "single", "offset": m.start()}
            if b is not None:
                entry["raw_pair"] = (a, b)
                if a.isdigit() and b.isdigit() and int(b) < int(a):
                    entry["kind"] = "phase-qualifier"
                else:
                    entry["kind"] = "range"
                    entry["endpoints"].append(b)
            out.append(entry)
    return out


_HEADING_NUM_PREFIX_RE = re.compile(r"^§{1,2}\s*")


def parse_numbered_headings(
    art: Artefact,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Return (numbered_headings, unnumbered_subsection_hints) for any markdown artefact.

    One parser for both namespaces, because the only honest way to tell an input.md
    `§7` from a `data-model.md` `§7` is to read the two files with the same rule.
    `subsection_hints` records a heading like `### B. Relation interpretation` as the
    *unnumbered* subsection `7B` of §7, so a citation of `§7B` can be reported against the
    real name instead of being a bare "no such section".
    """
    sections: dict[str, dict[str, Any]] = {}
    hints: dict[str, str] = {}
    current = "?"
    fence: str | None = None
    for i, line in enumerate(art.lines, start=1):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            token = stripped[:3]
            fence = None if fence == token else (token if fence is None else fence)
            continue
        if fence is not None:
            continue
        m = HEADING_RE.match(line)
        if not m:
            continue
        rest = m.group("rest")
        num = INPUT_SECTION_RE.match(_HEADING_NUM_PREFIX_RE.sub("", rest))
        if num:
            key = num.group("num")
            sections.setdefault(key, {"line": i, "title": rest})
            if "." not in key:
                current = key
            continue
        sub = INPUT_SUBSECTION_RE.match(rest)
        if sub and current != "?":
            hints.setdefault(f"{current}{sub.group(1)}", rest)
    return sections, hints


def parse_input_sections(art: Artefact) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Return (top_level_sections, subsection_hints) for input.md."""
    return parse_numbered_headings(art)


# --------------------------------------------------------------------------------------
# Term extraction for mis-citation heuristic
# --------------------------------------------------------------------------------------

_TERM_STOP = {
    # Normative and grammatical words. Anything in here is never treated as a
    # "meaningful term" for the RI-05 mis-citation heuristic: `MUST` alone must not
    # make every task look like it agrees with every requirement.
    "must", "mustnot", "should", "shall", "may", "never", "not", "only", "the", "and",
    "or", "but", "for", "with", "from", "into", "that", "this", "these", "those", "its",
    "are", "was", "were", "has", "have", "had", "been", "being", "one", "two", "three",
    "all", "any", "every", "each", "such", "than", "then", "when", "where", "which",
    "while", "here", "there", "also", "same", "own", "owndata", "true", "false", "none",
    "yes", "iso", "does", "did", "done", "get", "got", "set", "use", "used", "using",
    "via", "per", "out", "off", "ownref", "ownid", "make", "made", "need", "needs",
    "keep", "kept", "give", "gave", "left", "less", "least", "last", "next",
    "before", "after", "above", "below", "over", "under", "between", "about", "against",
    "because", "since", "until", "during", "again", "further", "once", "both", "few",
    "more", "most", "other", "too", "very", "just", "now", "let", "down",
    "frs", "scs", "invs", "md", "py", "json", "yaml", "yml", "txt", "toml",
}

_REF_STRIP_RE = re.compile(
    r"\b(?:FR|SC|INV|T|R)-\d+[A-Za-z]?\b|§+\s*\d+(?:\.\d+)?[A-Za-z]?|\bT\d+[A-Za-z]?\b"
)


def meaningful_terms(text: str) -> set[str]:
    """Identifier-shaped terms: code spans, dotted paths, snake_case and CamelCase ids."""
    cleaned = _REF_STRIP_RE.sub(" ", text)
    terms: set[str] = set()
    for m in CODE_SPAN_RE.finditer(cleaned):
        terms |= _split_identifier(m.group("body").strip().strip("*_`'\""))
    for m in re.finditer(r"\b[A-Za-z][A-Za-z0-9]*(?:[._/][A-Za-z0-9]+)*\b", cleaned):
        raw = m.group(0)
        if "_" in raw or (len(raw) > 1 and any(c.isupper() for c in raw[1:])):
            terms |= _split_identifier(raw)
        elif raw.isupper() and len(raw) >= 4:
            terms.add(raw.lower())
    out = set()
    for t in terms:
        t = t.strip("._-/").lower()
        if len(t) < 3 or t in _TERM_STOP or t.isdigit():
            continue
        out.add(t)
    return out


def _split_identifier(raw: str) -> set[str]:
    raw = re.sub(r"[^A-Za-z0-9_:./-]", " ", raw)
    raw = re.sub(r"\(.*$", "", raw)
    raw = re.sub(r"[=:].*$", "", raw)
    parts: set[str] = set()
    for chunk in re.split(r"[.:/]+", raw):
        if not chunk:
            continue
        parts.add(chunk)
        for piece in re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]*|[a-z0-9]+", chunk):
            parts.add(piece)
    return parts


def _containment(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


# --------------------------------------------------------------------------------------
# Context
# --------------------------------------------------------------------------------------


@dataclass
class Context:
    spec_dir: Path
    scanned: list[Artefact]
    authority: list[Artefact]
    constitution: Artefact | None
    defs: list[Definition] = field(default_factory=list)
    def_occurrences: list[Definition] = field(default_factory=list)
    tasks: list[TaskDef] = field(default_factory=list)
    rows: list[ChecklistRow] = field(default_factory=list)
    table_headers: list[list[str]] = field(default_factory=list)
    research_defs: set[str] = field(default_factory=set)
    sections: dict[str, dict[str, Any]] = field(default_factory=dict)
    subsection_hints: dict[str, str] = field(default_factory=dict)
    own_sections: dict[str, set[str]] = field(default_factory=dict)
    principles: dict[str, str] = field(default_factory=dict)
    stories: list[int] = field(default_factory=list)
    refs: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    section_cites: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    repair: list[Artefact] = field(default_factory=list)

    def by_name(self, name: str) -> Artefact | None:
        for art in [*self.scanned, *self.authority]:
            if art.name == name:
                return art
        return None

    def def_index(self) -> dict[str, Definition]:
        return {d.ident: d for d in self.defs}

    def task_index(self) -> dict[str, TaskDef]:
        return {t.ident: t for t in self.tasks}

    def readable(self, names: Iterable[str]) -> list[Artefact]:
        """The named artefacts, when they exist and decoded. Never raises."""
        out: list[Artefact] = []
        for name in names:
            art = self.by_name(name)
            if art is not None and art.read_ok:
                out.append(art)
        return out

    def governance(self) -> list[Artefact]:
        """Scanned artefacts + the optional review reports + every `repair/*.md`.

        The widest honest corpus: everything the feature says about itself, including
        `phase0-results.md` even when the run did not ask to scan it, because a review report
        that the spec artefacts contradict is still live text. Used only by the new governance
        checks, never by an RI-* check, so no existing finding changes.
        """
        have = {art.name for art in self.scanned}
        extra = [read_artefact(n, self.spec_dir / n) for n in OPTIONAL_ARTEFACTS
                 if n not in have and (self.spec_dir / n).is_file()]
        return [*self.scanned, *extra, *self.repair]


def build_context(spec_dir: Path, extra_artefacts: Sequence[str] = (),
                  include_all: bool = False) -> Context:
    names = list(SCANNED_ARTEFACTS)
    if include_all:
        names.extend(a for a in OPTIONAL_ARTEFACTS if a not in names)
    for e in extra_artefacts:
        if e not in names:
            names.append(e)
    scanned = [read_artefact(n, spec_dir / n) for n in names]
    authority = [read_artefact(n, spec_dir / n) for n in AUTHORITY_ARTEFACTS]
    const_path = find_constitution(spec_dir)
    constitution = read_artefact(str(CONSTITUTION_RELPATH), const_path) if const_path else None

    ctx = Context(
        spec_dir=spec_dir,
        scanned=scanned,
        authority=authority,
        constitution=constitution,
    )
    spec_art = ctx.by_name("spec.md")
    if spec_art and spec_art.read_ok:
        ctx.defs, ctx.def_occurrences = parse_definitions(spec_art, 4)
    tasks_art = ctx.by_name("tasks.md")
    if tasks_art and tasks_art.read_ok:
        ctx.tasks = parse_tasks(tasks_art)
    cl_art = ctx.by_name("checklists/requirements.md")
    if cl_art and cl_art.read_ok:
        ctx.rows, ctx.table_headers = parse_checklist(cl_art)
    res_art = ctx.by_name("research.md")
    if res_art and res_art.read_ok:
        ctx.research_defs = {f"R-{m.group('num')}" for m in RESEARCH_DEF_RE.finditer(res_art.text)}
    inp = ctx.by_name("input.md")
    if inp and inp.read_ok:
        ctx.sections, ctx.subsection_hints = parse_input_sections(inp)
    # Every scanned artefact numbers itself too, so each one gets its own section
    # namespace under the same parser. Without this, a document's own `§1.5` is
    # indistinguishable from a citation of input.md's §1.5, which does not exist.
    for art in ctx.scanned:
        if not art.read_ok or art.name == "input.md":
            continue
        numbered, hints = parse_numbered_headings(art)
        ctx.own_sections[art.name] = set(numbered) | set(hints)
    if constitution and constitution.read_ok:
        ctx.principles = {
            m.group("num"): m.group("title")
            for m in PRINCIPLE_RE.finditer(constitution.text)
        }
    if spec_art and spec_art.read_ok:
        ctx.stories = sorted({int(m.group(1)) for m in STORY_RE.finditer(spec_art.text)})

    ctx.refs = collect_references(ctx.scanned)
    ctx.section_cites = {art.name: collect_sections(art) for art in ctx.scanned}
    ctx.repair = read_repair_docs(spec_dir)
    return ctx


# --------------------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------------------

CheckFn = Callable[[Context], Iterable[Finding]]


def _f(ctx: Context, cid: str, code: str, msg: str, locs: Iterable[str] = (), **data) -> Finding:
    return Finding(
        check_id=cid,
        severity=CHECK_BY_ID[cid].severity,
        code=code,
        message=msg,
        locations=list(locs),
        data=data,
    )


def _ok(ctx: Context, cid: str, code: str, msg: str, **data) -> Finding:
    return Finding(check_id=cid, severity=INFO, code=code, message=msg, data=data)


# --- RI-00 ---------------------------------------------------------------------------


def check_input(ctx: Context) -> Iterable[Finding]:
    for art in [*ctx.scanned, *ctx.authority]:
        if not art.path.exists():
            yield _f(ctx, "RI-00-INPUT", "missing", f"required artefact is missing: {art.name}",
                    [art.name])
        elif not art.read_ok:
            yield _f(ctx, "RI-00-INPUT", "unreadable", f"{art.name}: {art.error}", [art.name])
        elif not art.text.strip():
            yield _f(ctx, "RI-00-INPUT", "empty", f"{art.name} is empty", [art.name])
    if ctx.constitution is None:
        yield Finding(
            check_id="RI-00-INPUT", severity=WARN, code="constitution-missing",
            message=("project constitution not found at .specify/memory/constitution.md; "
                     "RI-11-CONST cannot be evaluated in this workspace"),
            locations=[str(CONSTITUTION_RELPATH)],
        )


# --- RI-01 / RI-01b ------------------------------------------------------------------


def check_fr_definitions(ctx: Context) -> Iterable[Finding]:
    index = ctx.def_index()
    cited: dict[str, list[str]] = defaultdict(list)
    for art_name, bucket in ctx.refs.items():
        if art_name == "spec.md":
            continue
        for key, locs in bucket.items():
            if key.startswith("FR:"):
                cited[key[3:]].extend(locs)

    for fr in sorted(cited):
        if fr not in index:
            locs = sorted(cited[fr], key=_loc_key)
            yield _f(
                ctx, "RI-01-FR-DEF", "fr-undefined",
                f"{fr} is cited but never defined in spec.md ({len(locs)} citation(s))",
                locs, fr=fr, citation_count=len(locs),
                citing_files=sorted({loc.rpartition(':')[0] for loc in locs}),
            )

    for fr in sorted({d.ident for d in ctx.def_occurrences}):
        sites = [d for d in ctx.def_occurrences if d.ident == fr]
        if len(sites) > 1:
            spec = ctx.by_name("spec.md")
            yield _f(ctx, "RI-01-FR-DEF", "fr-defined-twice",
                     f"{fr} is defined {len(sites)} times",
                     [spec.loc(d.line) for d in sites], fr=fr, definition_sites=len(sites))


def check_fr_shape(ctx: Context) -> Iterable[Finding]:
    index = ctx.def_index()
    by_base: dict[str, set[str]] = defaultdict(set)
    for ident in index:
        m = re.match(r"^FR-(\d{3})([A-Za-z]?)$", ident)
        if m:
            by_base[m.group(1)].add(m.group(2))
    for base, suffixes in sorted(by_base.items()):
        non_empty = sorted(s for s in suffixes if s)
        if len(non_empty) > 1:
            yield _f(ctx, "RI-01b-FR-SHAPE", "suffix-collision",
                    f"FR-{base} carries {len(non_empty)} different suffixes: {non_empty}",
                    [], base=base, suffixes=non_empty)

    suffixed = sorted(i for i in index if re.match(r"^FR-\d{3}[A-Za-z]$", i))
    if suffixed:
        yield _ok(ctx, "RI-01b-FR-SHAPE", "suffixed-fr-ok",
                  f"{len(suffixed)} letter-suffixed FRs, each defined exactly once: "
                  f"{', '.join(suffixed)}",
                  frs=suffixed)

    for art in ctx.scanned:
        for i, line in enumerate(art.lines, start=1):
            for m in re.finditer(r"\bFR-(\d{1,2})\b", line):
                canonical = f"FR-{m.group(1).zfill(3)}"
                yield Finding(
                    check_id="RI-01b-FR-SHAPE", severity=WARN, code="fr-id-malformed",
                    message=(f"{art.loc(i)} cites `{m.group(0)}`; FR ids are FR- + 3 digits, "
                             f"so this will never match a definition ({canonical})"),
                    locations=[art.loc(i)],
                    data={"raw": m.group(0), "canonical": canonical},
                )


# --- RI-02 -----------------------------------------------------------------------------


def check_task_refs(ctx: Context) -> Iterable[Finding]:
    index = ctx.task_index()
    cited: dict[str, list[str]] = defaultdict(list)
    for art in ctx.scanned:
        for i, line in enumerate(art.lines, start=1):
            # A task bullet's own id is a definition, not a citation. Everything else in
            # tasks.md -- prose, dependency graphs, the open-questions table -- is a
            # citation, which is how T009f / T010d / T010f / T013a are caught.
            if art.name == "tasks.md" and TASK_DEF_RE.match(line):
                continue
            for m in TASK_TOKEN_RE.finditer(line):
                cited[m.group(0)].append(art.loc(i))
    for tid in sorted(cited):
        if tid not in index:
            locs = sorted(set(cited[tid]), key=_loc_key)
            yield _f(
                ctx, "RI-02-TASK-REF", "task-phantom",
                f"{tid} is cited but not defined in tasks.md ({len(locs)} citation(s))",
                locs, task=tid, citation_count=len(locs),
                citing_files=sorted({loc.rpartition(':')[0] for loc in locs}),
            )


# --- RI-03 / RI-03b / RI-03c -------------------------------------------------------------


def check_fr_orphans(ctx: Context) -> Iterable[Finding]:
    tasks = ctx.by_name("tasks.md")
    checklist = ctx.by_name("checklists/requirements.md")
    if not (tasks and tasks.read_ok and checklist and checklist.read_ok):
        return
    covered: set[str] = set(FR_TOKEN_RE.findall(tasks.text))
    covered |= set(FR_TOKEN_RE.findall(checklist.text))
    frs = [d.ident for d in ctx.defs if d.ident.startswith("FR-")]
    orphans = [fr for fr in frs if fr not in covered]
    if orphans:
        spec = ctx.by_name("spec.md")
        locs = [spec.loc(d.line) for d in ctx.defs if d.ident in set(orphans)] if spec else []
        yield _f(
            ctx, "RI-03-FR-ORPHAN", "fr-orphan",
            f"{len(orphans)} of {len(frs)} FRs are defined in spec.md and referenced by "
            f"neither tasks.md nor checklists/requirements.md",
            [], orphans=orphans, orphan_count=len(orphans), total_frs=len(frs),
            definition_lines=sorted(locs, key=_loc_key),
        )
    else:
        yield _ok(ctx, "RI-03-FR-ORPHAN", "no-orphans",
                  f"all {len(frs)} FRs are referenced by tasks.md or the checklist",
                  total_frs=len(frs))


def check_fr_uncited_anywhere(ctx: Context) -> Iterable[Finding]:
    index = ctx.def_index()
    cited: set[str] = set()
    for bucket in ctx.refs.values():
        for key in bucket:
            if key.startswith("FR:"):
                cited.add(key[3:])
    for fr in sorted(i for i in index if i.startswith("FR-")):
        if fr not in cited:
            yield _f(ctx, "RI-03b-FR-UNCITED", "fr-uncited",
                     f"{fr} is defined in spec.md and cited by no artefact at all", [], fr=fr)


def check_checklist_fr_column(ctx: Context) -> Iterable[Finding]:
    if not ctx.rows:
        return
    fr_total = len([d for d in ctx.defs if d.ident.startswith("FR-")])
    header_names: list[str] = []
    for cols in ctx.table_headers:
        header_names.extend(c.lower() for c in cols)
    fr_cols = [h for h in header_names if re.search(r"\bfr\b|requirement", h)]
    mapped = {fr for row in ctx.rows for fr in FR_TOKEN_RE.findall(row.text)}
    if not fr_cols:
        observed = sorted(set(header_names))
        yield _f(
            ctx, "RI-03c-FR-COLUMN", "no-fr-column",
            f"checklists/requirements.md has no FR/requirement column "
            f"(columns found: {observed or 'none'}); it maps zero of the "
            f"{fr_total} FRs",
            [], observed_columns=observed, frs_mapped=sorted(mapped), total_frs=fr_total,
        )
    elif not mapped:
        yield _f(ctx, "RI-03c-FR-COLUMN", "fr-column-empty",
                 "the checklist has an FR column but no row names an FR", [])
    else:
        yield _ok(ctx, "RI-03c-FR-COLUMN", "fr-column-present",
                  f"checklist maps {len(mapped)} distinct FRs via column(s) {fr_cols}",
                  frs_mapped=sorted(mapped))


# --- RI-04 family -----------------------------------------------------------------------


def check_task_cites_fr(ctx: Context) -> Iterable[Finding]:
    for t in ctx.tasks:
        frs = FR_TOKEN_RE.findall(t.text)
        if not frs:
            yield _f(ctx, "RI-04-TASK-FR", "task-without-fr",
                     f"{t.ident} cites no FR; it cannot be traced to a requirement",
                     [ctx.by_name("tasks.md").loc(t.line)], task=t.ident,
                     phase=t.phase, text=t.text[:180])


def check_rows_cite_tasks(ctx: Context) -> Iterable[Finding]:
    index = ctx.task_index()
    cl = ctx.by_name("checklists/requirements.md")
    for row in ctx.rows:
        tasks = TASK_TOKEN_RE.findall(row.text)
        if not tasks:
            cell = row.cells[3] if len(row.cells) > 3 else ""
            yield _f(ctx, "RI-04b-ROW-TASK", "row-without-task",
                     f"checklist row {row.ident} names no task",
                     [cl.loc(row.line)], row=row.ident, task_cell=cell)
        for tid in sorted(set(tasks)):
            if tid not in index:
                yield _f(ctx, "RI-04b-ROW-TASK", "row-phantom-task",
                         f"checklist row {row.ident} cites {tid}, which is not in tasks.md",
                         [cl.loc(row.line)], row=row.ident, task=tid)


def check_rows_cite_fr(ctx: Context) -> Iterable[Finding]:
    cl = ctx.by_name("checklists/requirements.md")
    fr_index = ctx.def_index()
    without = []
    for row in ctx.rows:
        if not FR_TOKEN_RE.findall(row.text):
            without.append(row.ident)
            yield _f(ctx, "RI-04c-ROW-FR", "row-without-fr",
                     f"checklist row {row.ident} cites no FR",
                     [cl.loc(row.line)], row=row.ident)
    unknown = sorted({fr for row in ctx.rows for fr in FR_TOKEN_RE.findall(row.text)
                      if fr not in fr_index})
    for fr in unknown:
        yield _f(ctx, "RI-04c-ROW-FR", "row-cites-unknown-fr",
                 f"checklist cites {fr}, which is not defined in spec.md", [], fr=fr)
    if without:
        yield _f(ctx, "RI-04c-ROW-FR", "row-without-fr-total",
                 f"{len(without)} of {len(ctx.rows)} checklist rows cite no FR", [],
                 rows=without, total_rows=len(ctx.rows))


def check_fr_owners(ctx: Context) -> Iterable[Finding]:
    owners: dict[str, set[str]] = defaultdict(set)
    for t in ctx.tasks:
        for fr in FR_TOKEN_RE.findall(t.text):
            owners[fr].add(t.ident)
    defined = [d.ident for d in ctx.defs if d.ident.startswith("FR-")]
    no_owner = [fr for fr in defined if not owners.get(fr)]
    shared = {fr: sorted(owners[fr]) for fr in defined if len(owners.get(fr, ())) > 1}
    if no_owner:
        yield Finding(
            check_id="RI-04d-FR-OWNER", severity=FAIL, code="fr-no-owner",
            message=(f"{len(no_owner)} FRs have no task owner at all: they are the per-FR "
                     f"expansion of the RI-03 orphan set and are individually unactionable"),
            data={"frs": no_owner, "count": len(no_owner)},
        )
    else:
        yield _ok(ctx, "RI-04d-FR-OWNER", "all-owned",
                  f"every one of the {len(defined)} FRs is owned by at least one task")
    if shared:
        yield Finding(
            check_id="RI-04d-FR-OWNER", severity=WARN, code="fr-multiple-owners",
            message=(f"{len(shared)} FRs are cited by two or more tasks, so a change to them "
                     f"has no single blast radius"),
            data={"frs": {k: v for k, v in sorted(shared.items())}, "count": len(shared)},
        )
    else:
        yield _ok(ctx, "RI-04d-FR-OWNER", "single-owner",
                  "every FR cited by a task is cited by exactly one task")


# --- RI-05 mis-citation heuristic --------------------------------------------------------


def _citing_lines(ctx: Context) -> list[tuple[str, int, str, set[str]]]:
    """(artefact, line, text) for every line that cites an FR, excluding spec.md."""
    out = []
    for art in ctx.scanned:
        if art.name == "spec.md":
            continue
        for i, line in enumerate(art.lines, start=1):
            if FR_TOKEN_RE.search(line):
                out.append((art, i, line, FR_TOKEN_RE.findall(line)))
    return out


def check_miscitations(ctx: Context) -> Iterable[Finding]:
    index = ctx.def_index()
    rows: list[dict[str, Any]] = []
    unjudgeable = 0
    for art, line_no, line, frs in _citing_lines(ctx):
        task_terms = meaningful_terms(line)
        for fr in frs:
            definition = index.get(fr)
            if definition is None:
                continue
            fr_terms = meaningful_terms(definition.body)
            # The task side needs enough vocabulary for absence to mean something; the
            # requirement side needs only one real term, because a single shared
            # identifier is decisive and a single-term requirement is *easier* to
            # mismatch, not harder.
            if len(task_terms) < 2 or not fr_terms:
                unjudgeable += 1
                continue
            shared = sorted(task_terms & fr_terms)
            score = _containment(task_terms, fr_terms)
            rows.append({
                "artefact": art.name,
                "line": line_no,
                "fr": fr,
                "task_terms": len(task_terms),
                "fr_terms": len(fr_terms),
                "shared": shared,
                "containment": round(score, 3),
                "line_excerpt": line.strip()[:150],
            })
    suspects = [r for r in rows if r["containment"] == 0.0]
    suspects.sort(key=lambda r: (-r["task_terms"], -r["fr_terms"], r["artefact"], r["line"]))
    for r in suspects:
        yield Finding(
            check_id="RI-05-MISCITE", severity=WARN, code="miscite-suspect",
            message=(
                f"{r['artefact']}:{r['line']} cites {r['fr']} but shares no meaningful term "
                f"with it ({r['task_terms']} task terms vs {r['fr_terms']} FR terms)"
            ),
            locations=[f"{r['artefact']}:{r['line']}"],
            data=r,
        )
    yield _ok(
        ctx, "RI-05-MISCITE", "miscite-summary",
        f"{len(suspects)} of {len(rows)} judgeable FR citations share no meaningful term "
        f"with the FR they cite; {len(rows) - len(suspects)} share at least one; "
        f"{unjudgeable} citations were not judgeable (too few terms on either side)",
        judgeable=len(rows), suspects=len(suspects), unjudgeable=unjudgeable,
    )


def _must_literals(fr_body: str) -> set[str]:
    """Closed vocabularies the FR mandates: enum members inside MUST-contain clauses.

    Deliberately narrow. A sentence like "the `document:current` fallback MUST be removed"
    is a *repair* obligation, not a membership list, and a task that removes the forbidden
    symbol is complying with it -- flagging that would invert the check.
    """
    out: set[str] = set()
    for sentence in re.split(r"(?<=[.;])\s+", fr_body.replace("\n", " ")):
        if not re.search(r"\bMUST\s+(?:contain|include)\b", sentence):
            continue
        tail = re.split(r"\b(?:MAY|SHOULD|MUST NOT|Never|but)\b", sentence, maxsplit=1)[0]
        for m in CODE_SPAN_RE.finditer(tail):
            lit = m.group("body").strip().strip("`'\"*")
            if re.fullmatch(r"[A-Z][A-Z0-9_]*", lit):
                out.add(lit)
    return out


_DIRECTIVE_RE = re.compile(
    r"\b(?:Remove|remove|Delete|delete|drop|Drop|forbid|never|never add|Do NOT|do not|"
    r"MUST NOT|must not|without|no longer)\b"
)


_ADDITIVE_PROHIBITION_RE = re.compile(
    r"\b(?:Do\s+NOT|do\s+not|MUST\s+not|must\s+not|NEVER|never)\s+"
    r"(?:add|introduce|create|re-?introduce|re-?add|extend)\b(?P<tail>[^.;|]{0,80})",
    re.IGNORECASE,
)


def check_inverse_citations(ctx: Context) -> Iterable[Finding]:
    """A citing line that forbids *adding* a member the cited FR mandates.

    Deliberately scoped to additive prohibitions. "Remove `NEGATION` from
    `SignalKind`" against an FR that mandates `SignalKind` membership is a legitimate
    refactor of existing code, not a citation of an FR being violated; flagging it
    would be noise. The failure worth catching is a task forbidding the introduction of
    a member the requirement says MUST be present.
    """
    index = ctx.def_index()
    for art, line_no, line, frs in _citing_lines(ctx):
        for fr in frs:
            definition = index.get(fr)
            if definition is None:
                continue
            literals = _must_literals(definition.body)
            if not literals:
                continue
            for prohib in _ADDITIVE_PROHIBITION_RE.finditer(line):
                tail = prohib.group("tail")
                for lit in sorted(literals):
                    if not re.search(rf"\b{re.escape(lit)}\b", tail):
                        continue
                    yield Finding(
                        check_id="RI-05b-INVERSE-CITE", severity=WARN,
                        code="inverse-citation",
                        message=(
                            f"{art.name}:{line_no} cites {fr} while forbidding the addition of "
                            f"`{lit}`, which {fr} places in a MUST-contain clause: the task is a "
                            f"counterexample to the requirement it names"
                        ),
                        locations=[f"{art.name}:{line_no}", f"spec.md:{definition.line}"],
                        data={"literal": lit, "fr": fr, "artefact": art.name, "line": line_no,
                              "cited_text": prohib.group(0).strip()[:160],
                              "fr_clause": definition.body[:240]},
                    )
                    break


# --- RI-06 task ordering ------------------------------------------------------------------


def check_task_order(ctx: Context) -> Iterable[Finding]:
    tasks = ctx.by_name("tasks.md")
    idents = [t.ident for t in ctx.tasks]
    seen: set[str] = set()
    dups: list[str] = []
    for tid in idents:
        if tid in seen:
            dups.append(tid)
        seen.add(tid)
    for tid in sorted(set(dups)):
        lines = [t.line for t in ctx.tasks if t.ident == tid]
        yield _f(ctx, "RI-06-TASK-ORDER", "task-duplicate",
                 f"{tid} is defined {len(lines)} times",
                 [tasks.loc(n) for n in lines], task=tid)

    numbers = [int(re.match(r"^T(\d+)", t).group(1)) for t in idents if re.match(r"^T\d+$", t)]
    if numbers:
        expected = list(range(1, max(numbers) + 1))
        missing = sorted(set(expected) - set(numbers))
        out_of_order = sorted({b for a, b in zip(numbers, numbers[1:], strict=False)
                               if b <= a})
        for n in missing:
            yield _f(ctx, "RI-06-TASK-ORDER", "task-gap", f"T{n:03d} is missing from tasks.md",
                     [tasks.name], missing=n)
        for n in out_of_order:
            locs = [tasks.loc(t.line) for t in ctx.tasks
                    if re.fullmatch(r"T\d+", t.ident)
                    and int(t.ident[1:]) == n]
            yield _f(ctx, "RI-06-TASK-ORDER", "task-out-of-order",
                     f"T{n:03d} appears after a higher task number", locs, number=n)
        if not missing and not out_of_order:
            yield _ok(ctx, "RI-06-TASK-ORDER", "task-order-ok",
                      f"task ids are contiguous and ascending: "
                      f"T{numbers[0]:03d}..T{numbers[-1]:03d} "
                      f"({len(numbers)} ids, 0 gaps, 0 reorderings)",
                      first=numbers[0], last=numbers[-1], count=len(numbers))

    for tid in sorted({t.ident for t in ctx.tasks if re.match(r"^T\d+[A-Za-z]$", t.ident)}):
        lines = [t.line for t in ctx.tasks if t.ident == tid]
        yield _f(ctx, "RI-06-TASK-ORDER", "task-letter-suffix",
                 f"{tid} is defined with a letter suffix; task ids must be T + 3 digits",
                 [tasks.loc(n) for n in lines], task=tid)


# --- RI-06b FR ordering ---------------------------------------------------------------------


def check_fr_order(ctx: Context) -> Iterable[Finding]:
    spec = ctx.by_name("spec.md")
    lines = spec.lines if spec else []
    by_section: dict[str, list[Definition]] = defaultdict(list)
    for d in ctx.defs:
        if not d.ident.startswith("FR-"):
            continue
        by_section[d.section].append(d)
    known_sections = set(by_section)
    for d in ctx.defs:
        if not d.ident.startswith("FR-"):
            continue
        # A requirement bullet that dangles after a table is not grouped with the
        # requirement list it appears to belong to. This document mixes `###` and `####`
        # heading levels, so heading ancestry is not a sound signal; "what is directly
        # above this bullet" is.
        j = d.line - 2
        while 0 <= j < len(lines) and not lines[j].strip():
            j -= 1
        if 0 <= j < len(lines) and lines[j].lstrip().startswith("|"):
            yield _f(ctx, "RI-06b-FR-ORDER", "fr-dangles-after-table",
                     f"{d.ident} is a requirement bullet dangling after a table at "
                     f"spec.md:{j + 1}, not grouped under "
                     f"'{d.section.split(' > ')[-1] or d.section}' with the other "
                     f"requirements",
                     [spec.loc(d.line), spec.loc(j + 1)], fr=d.ident, section=d.section,
                     after_table_line=j + 1)
    for section in sorted(known_sections):
        defs = by_section[section]
        if len(defs) < 2:
            continue
        nums = [int(re.match(r"^FR-(\d{3})", d.ident).group(1)) for d in defs]
        for a, b, da, db in zip(nums, nums[1:], defs, defs[1:], strict=False):
            if b < a:
                yield _f(ctx, "RI-06b-FR-ORDER", "fr-non-monotonic",
                         f"{db.ident} ({b:03d}) follows {da.ident} ({a:03d}) in "
                         f"'{section.split(' > ')[-1] or section}': numbering rewinds",
                         [spec.loc(db.line), spec.loc(da.line)],
                         section=section, first=da.ident, second=db.ident)
            elif b > a + 1:
                yield _f(ctx, "RI-06b-FR-ORDER", "fr-gap",
                         f"{db.ident} ({b:03d}) follows {da.ident} ({a:03d}) in "
                         f"'{section.split(' > ')[-1] or section}': "
                         f"FR-{a + 1:03d}..FR-{b - 1:03d} are not in this section",
                         [spec.loc(da.line), spec.loc(db.line)],
                         section=section, gap_from=f"FR-{a + 1:03d}", gap_to=f"FR-{b - 1:03d}")

    # document order, across section boundaries
    seq = [d for d in ctx.defs if d.ident.startswith("FR-")]
    nums = [int(re.match(r"^FR-(\d+)", d.ident).group(1)) for d in seq]
    for a, b, da, db in zip(nums, nums[1:], seq, seq[1:], strict=False):
        if b < a:
            yield _f(ctx, "RI-06b-FR-ORDER", "fr-non-monotonic-document-order",
                     f"{db.ident} appears at spec.md:{db.line} after {da.ident} at "
                     f"spec.md:{da.line}: the document-order FR sequence rewinds by "
                     f"{a - b}",
                     [spec.loc(db.line), spec.loc(da.line)],
                     first=da.ident, second=db.ident, rewind=a - b)
        elif b > a + 1:
            missing = [f"FR-{n:03d}" for n in range(a + 1, b)]
            yield _f(ctx, "RI-06b-FR-ORDER", "fr-gap-document-order",
                     f"{db.ident} at spec.md:{db.line} follows {da.ident} at spec.md:{da.line}: "
                     f"{', '.join(missing)} appear(s) nowhere between them in document order",
                     [spec.loc(da.line), spec.loc(db.line)],
                     first=da.ident, second=db.ident, missing=missing)


# --- RI-07 family --------------------------------------------------------------------------


def _checklist_refs(ctx: Context) -> set[str]:
    cl = ctx.by_name("checklists/requirements.md")
    if not cl or not cl.read_ok:
        return set()
    return set(SC_TOKEN_RE.findall(cl.text)) | set(INV_TOKEN_RE.findall(cl.text))


def check_sc_coverage(ctx: Context) -> Iterable[Finding]:
    covered = _checklist_refs(ctx)
    scs = [d.ident for d in ctx.defs if d.ident.startswith("SC-")]
    uncovered = [s for s in scs if s not in covered]
    if uncovered:
        spec = ctx.by_name("spec.md")
        locs = [spec.loc(d.line) for d in ctx.defs if d.ident in set(uncovered)]
        yield _f(ctx, "RI-07-SC-COVER", "sc-uncovered",
                 f"{len(uncovered)} of {len(scs)} success criteria are referenced by no "
                 f"checklist item", locs, uncovered=uncovered, total_scs=len(scs))
    else:
        yield _ok(ctx, "RI-07-SC-COVER", "sc-covered",
                  f"all {len(scs)} success criteria are referenced by a checklist item")


def check_inv_coverage(ctx: Context) -> Iterable[Finding]:
    covered = _checklist_refs(ctx)
    invs = [d.ident for d in ctx.defs if d.ident.startswith("INV-")]
    uncovered = [i for i in invs if i not in covered]
    if uncovered:
        spec = ctx.by_name("spec.md")
        locs = [spec.loc(d.line) for d in ctx.defs if d.ident in set(uncovered)]
        yield _f(ctx, "RI-07b-INV-COVER", "inv-uncovered",
                 f"{len(uncovered)} of {len(invs)} constitutional invariants are referenced "
                 f"by no checklist item", locs, uncovered=uncovered, total_invs=len(invs))
    else:
        yield _ok(ctx, "RI-07b-INV-COVER", "inv-covered",
                  f"all {len(invs)} constitutional invariants are referenced by a checklist item")


def check_id_shape(ctx: Context) -> Iterable[Finding]:
    for art in ctx.scanned:
        if art.name == "spec.md":
            continue
        for i, line in enumerate(art.lines, start=1):
            for m in re.finditer(r"\b(?:SC|INV)-(\d{1,2})\b", line):
                padded = f"{m.group(1).zfill(3)}"
                yield Finding(
                    check_id="RI-07c-ID-SHAPE", severity=WARN, code="id-malformed",
                    message=(f"{art.name}:{i} cites `{m.group(0)}`; the canonical form is "
                             f"`{m.group(1).split('-')[0]}-{padded}` and will not match it"),
                    locations=[art.loc(i)],
                    data={"raw": m.group(0), "canonical": f"{m.group(1).split('-')[0]}-{padded}"},
                )


# --- RI-08 section citations ------------------------------------------------------------------

# A clause break between a file reference and a `§N` reference means the two are unrelated:
# inside a table cell or after a semicolon, the file named to the left is not the file the
# section number belongs to.
_CLAUSE_BREAK_RE = re.compile(r"[;|]|(?<=[a-z0-9`\"])\.(?:\s|$)")


def _governing_file(ctx: Context, line: str, offset: int) -> str | None:
    """The file a `§N` at `offset` on `line` is attributed to, if the line names one.

    "`repair/A6-fr-triage.md` §2.5" attributes §2.5 to that document, not to input.md. The
    nearest file reference to the left on the same line wins, and only if no clause break
    separates it - otherwise a table row or a semicolon would misattribute the reference.
    """
    left = line[:offset]
    best: tuple[int, str] | None = None
    for m in FILE_REF_RE.finditer(left):
        if _CLAUSE_BREAK_RE.search(left[m.end():]):
            continue
        resolved = _resolve_in_spec_dir(ctx, m.group("path"))
        if resolved:
            best = (m.end(), resolved)
    return best[1] if best else None


class _SectionIndex:
    """Numbered headings of any file a reference names, read on demand and cached.

    This does not widen what RI-08 scans: a file is read only when a citation attributes a
    section to it by name, which is the reference's own declared target.
    """

    def __init__(self, ctx: Context) -> None:
        self._ctx = ctx
        self._cache: dict[str, set[str] | None] = {}

    def headings(self, relpath: str) -> set[str] | None:
        if relpath in self._cache:
            return self._cache[relpath]
        art = read_artefact(relpath, self._ctx.spec_dir / relpath)
        result: set[str] | None = None
        if art.read_ok:
            numbered, hints = parse_numbered_headings(art)
            result = set(numbered) | set(hints)
        self._cache[relpath] = result
        return result


def check_section_citations(ctx: Context) -> Iterable[Finding]:
    """Resolve every `§N` against input.md, the citing artefact, and any file it names.

    Three namespaces, one citation mark. input.md's is `§0`…`§114` plus its one dotted
    sub-heading; every feature artefact numbers its own sections the same way, so `§1.5`
    inside data-model.md is that document's cross-reference to its own `### 1.5`, not a
    claim about a brief section that does not exist; and a reference that names its target
    ("`repair/A6-fr-triage.md` §2.5") is a claim about that file. A reference that resolves
    in none of them is a phantom - which is still true of a fabricated sub-section label
    like `§1B` (input.md's §1 carries unnumbered subsections A and B, so `§1B` is not a
    section) and of an integer that exists in no file.
    """
    if not ctx.sections:
        yield _f(ctx, "RI-08-SEC-CITE", "no-section-authority",
                 "input.md has no numbered headings; no § citation can be verified", [])
        return
    known = set(ctx.sections)
    seen: set[tuple[str, str, int]] = set()
    intra_doc: set[tuple[str, str]] = set()
    index = _SectionIndex(ctx)
    for art_name, cites in ctx.section_cites.items():
        if art_name == "input.md":
            continue
        art = ctx.by_name(art_name)
        own = ctx.own_sections.get(art_name, set())
        for cite in cites:
            line = art.lines[cite["line"] - 1]
            for ep in cite["endpoints"]:
                key = (art_name, ep, cite["line"])
                if key in seen:
                    continue
                seen.add(key)
                if ep in known:
                    continue
                if ep in own:
                    # An *integer* is inside input.md's namespace, so an integer that only
                    # the citing artefact defines is genuinely ambiguous. The power the
                    # check gives up here is reported, not hidden.
                    if ep.isdigit() and (art_name, ep) not in intra_doc:
                        intra_doc.add((art_name, ep))
                        yield _ok(
                            ctx, "RI-08-SEC-CITE", "sec-cite-intra-doc-integer",
                            f"{art_name} cites §{ep}, which is a numbered heading inside "
                            f"{art_name} but not a section of input.md: read as "
                            f"{art_name}'s own §{ep}, not as a phantom brief section",
                            artefact=art_name, section=ep,
                        )
                    continue
                named = _governing_file(ctx, line, cite["offset"])
                if named:
                    target = index.headings(named)
                    if target is not None and ep in target:
                        continue
                hint = ""
                if ep in ctx.subsection_hints:
                    hint = (f" (input.md has unnumbered subsection "
                            f"'{ctx.subsection_hints[ep]}' under §{ep[:-1]}; the citation "
                            f"should be §{ep[:-1]} or the subsection should be numbered)")
                else:
                    others = [f"{art_name} has no heading §{ep}"]
                    if named:
                        others.append(f"{named} has no heading §{ep}")
                    hint = f", and {' and '.join(others)}"
                yield _f(ctx, "RI-08-SEC-CITE", "section-phantom",
                         f"{art_name}:{cite['line']} cites §{ep}, which is not a numbered "
                         f"heading in input.md{hint}",
                         [art.loc(cite["line"])], section=ep, kind=cite["kind"],
                         raw=cite["raw"])



def check_uncited_sections(ctx: Context) -> Iterable[Finding]:
    if not ctx.sections:
        return
    cited: set[str] = set()
    for cites in ctx.section_cites.values():
        for cite in cites:
            for ep in cite["endpoints"]:
                cited.add(ep)
    top = {k: v for k, v in ctx.sections.items() if "." not in k}
    uncited = sorted((k for k in top if k not in cited), key=lambda s: int(s))
    if uncited:
        yield _ok(ctx, "RI-08b-SEC-UNCITED", "sections-uncited",
                  f"{len(uncited)} of {len(top)} input.md sections are cited by no artefact: "
                  f"{', '.join(uncited)}",
                  uncited=uncited, total_sections=len(top))
    else:
        yield _ok(ctx, "RI-08b-SEC-UNCITED", "sections-all-cited",
                  f"all {len(top)} input.md sections are cited",
                  total_sections=len(top))


# --- RI-09 count claims --------------------------------------------------------------------


@dataclass
class CountContext:
    line_count: dict[str, int]
    fr_count: int
    sc_count: int
    inv_count: int
    story_count: int
    section_count: int
    section_spans: dict[str, tuple[int, int]]
    mutation_sections: dict[str, str]
    member_enumerations: list[tuple[str, int, int, str]] = field(default_factory=list)
    level_chains: list[tuple[str, int, int]] = field(default_factory=list)
    harness_fields: dict[str, int] = field(default_factory=dict)
    prefix_count: int = 0


def _resolve_in_spec_dir(ctx: Context, ref: str) -> str | None:
    cleaned = ref.strip().lstrip("./\\")
    cand = ctx.spec_dir / cleaned
    try:
        cand.relative_to(ctx.spec_dir)
    except ValueError:
        return None
    if cand.is_file():
        return cleaned
    return None


def _line_of(art: Artefact, offset: int) -> int:
    """1-based line number of a character offset in the artefact text."""
    offsets = getattr(art, "_line_offsets", None)
    if offsets is None:
        offsets = [0]
        for n, ch in enumerate(art.text):
            if ch == "\n":
                offsets.append(n + 1)
        art._line_offsets = offsets  # type: ignore[attr-defined]
    lo, hi = 0, len(offsets) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if offsets[mid] <= offset:
            lo = mid
        else:
            hi = mid - 1
    return lo + 1


def _claim_window(art: Artefact, line_no: int, defs: Sequence[Definition]) -> str:
    """The tightest honest context for a claim on `line_no`.

    * a table row is its own context (the row *is* the assertion);
    * otherwise the claim's paragraph, or the whole definition body when the claim
      sits inside an FR/SC/INV definition.
    """
    line = art.lines[line_no - 1]
    if line.strip().startswith("|"):
        return line
    for d in defs:
        if d.line <= line_no <= d.line + len(d.body.split("\n")) - 1:
            return d.body
    lo = line_no - 1
    hi = line_no
    while lo > 0 and art.lines[lo - 1].strip() and not art.lines[lo - 1].lstrip().startswith("#") \
            and not art.lines[lo - 1].strip().startswith("|"):
        lo -= 1
    while hi < len(art.lines) and art.lines[hi].strip() \
            and not art.lines[hi].lstrip().startswith("#") \
            and not art.lines[hi].strip().startswith("|"):
        hi += 1
    return "\n".join(art.lines[lo:hi])


def _mutation_sections(ctx: Context) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, meta in ctx.sections.items():
        if "MUTATION" in meta["title"].upper():
            out[key] = meta["title"]
    return out


def _section_spans(ctx: Context) -> dict[str, tuple[int, int]]:
    inp = ctx.by_name("input.md")
    if not inp or not inp.read_ok:
        return {}
    keys = sorted(
        ((k, v["line"]) for k, v in ctx.sections.items() if "." not in k),
        key=lambda kv: kv[1],
    )
    spans: dict[str, tuple[int, int]] = {}
    for idx, (key, start) in enumerate(keys):
        end = keys[idx + 1][1] - 1 if idx + 1 < len(keys) else inp.line_count
        spans[key] = (start, end)
    return spans


def _harness_field_counts(ctx: Context) -> dict[str, int]:
    """Fields each `... MUST break ...` requirement enumerates.

    Counted as comma-separated items inside the requirement's parenthesised field
    lists, so prose items ("producer identity", "claim provenance") count alongside
    backticked ones (`predicate_signature`). The FR's own trailing "(§93)" locator is
    excluded.
    """
    out: dict[str, int] = {}
    for d in ctx.defs:
        if not d.ident.startswith("FR-"):
            continue
        if not re.search(r"\bMUST\s+break\b", d.body, re.IGNORECASE):
            continue
        counted = 0
        for group in re.findall(r"\(([^()]*)\)", d.body):
            for piece in group.split(","):
                cleaned = re.sub(r"[`*_]", "", piece).strip()
                if not cleaned or cleaned.startswith("\u00a7"):
                    continue
                if re.search(r"[A-Za-z0-9]", cleaned):
                    counted += 1
        if counted:
            out[d.ident] = counted
    return out


def _first_sentence(text: str, from_pos: int) -> str:
    """`text` truncated at the first sentence terminator at/after `from_pos`."""
    m = re.search(r"\.\s", text[from_pos:])
    return text[: from_pos + m.start()] if m else text


def _member_enumerations(ctx: Context) -> list[tuple[str, int, int, str]]:
    """(file:line, claimed, enumerated, how) for `N members` claims.

    Resolution order: enum-like code spans inside the declaring sentence, else the
    contiguous table immediately below the claim (a cell that is a single bare token,
    or a comma-separated list of code spans, declares a member). `enumerated == -1`
    means the claim is not a machine-checkable enum list (e.g. "11 workspace members").
    """
    out: list[tuple[str, int, int, str]] = []
    for art in ctx.scanned:
        for i, line in enumerate(art.lines, start=1):
            m = re.search(r"\b(\d{1,3})\s+members\b", line)
            if not m:
                continue
            claimed = int(m.group(1))
            sentence = _first_sentence(line, m.start())
            spans = {c for c in CODE_SPAN_RE.findall(sentence)
                     if re.fullmatch(r"[A-Z][A-Z0-9_]*", c.strip().strip("`"))}
            if spans:
                out.append((art.loc(i), claimed, len(spans),
                            "enum code spans in the declaring sentence"))
                continue
            j = i
            while j < len(art.lines) and not art.lines[j].strip():
                j += 1
            counted = 0
            rows = 0
            if j < len(art.lines) and art.lines[j].strip().startswith("|"):
                k = j
                while k < len(art.lines) and art.lines[k].strip().startswith("|"):
                    if TABLE_SEP_RE.match(art.lines[k].strip()):
                        k += 1
                        continue
                    cells = [c.strip() for c in art.lines[k].strip().strip("|").split("|")]
                    if cells and cells[0] in {"#", "Item", "Today", "Kind", "Name"}:
                        k += 1
                        continue
                    rows += 1
                    has_span = bool(CODE_SPAN_RE.search(cells[0]))
                    for piece in cells[0].split(","):
                        piece = piece.strip().strip("`").strip()
                        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", piece) and (
                            piece.isupper() or has_span
                        ):
                            counted += 1
                    k += 1
            if rows:
                out.append((art.loc(i), claimed, counted,
                            f"first column of the {rows}-row table below the claim"))
            else:
                out.append((art.loc(i), claimed, -1, "not an enumerable member list"))
    return out


def _level_chains(ctx: Context) -> list[tuple[str, int, int]]:
    out = []
    for art in ctx.scanned:
        for i, line in enumerate(art.lines, start=1):
            m = re.search(r"\b(\d{1,2}|[A-Za-z]+)\s+(?:distinct\s+)?levels?\b", line)
            if not m:
                continue
            num = _as_int(m.group(1))
            if num is None:
                continue
            window = _claim_window(art, i, [])
            m_chain = re.search(r"[\w`]+(?:\s*\u2192\s*[\w`/*]+)+",
                                " ".join(window.split("\n")))
            if not m_chain:
                out.append((art.loc(i), num, -1))
                continue
            items = [p.strip() for p in m_chain.group(0).split("\u2192") if p.strip()]
            out.append((art.loc(i), num, len(items)))
    return out


def _as_int(token: str) -> int | None:
    token = token.strip().lower()
    if token.isdigit():
        return int(token)
    return _NUMWORDS.get(token)


def _prefix_count(ctx: Context) -> int:
    dm = ctx.by_name("data-model.md")
    if not dm:
        return 0
    return len({m.group("body") for m in CODE_SPAN_RE.finditer(dm.text)
                if re.fullmatch(r"[a-z][a-z\-]*:\*", m.group("body").strip())})
def check_count_claims(ctx: Context) -> Iterable[Finding]:
    cc = CountContext(
        line_count={a.name: a.line_count for a in [*ctx.scanned, *ctx.authority]},
        fr_count=len([d for d in ctx.defs if d.ident.startswith("FR-")]),
        sc_count=len([d for d in ctx.defs if d.ident.startswith("SC-")]),
        inv_count=len([d for d in ctx.defs if d.ident.startswith("INV-")]),
        story_count=len(ctx.stories),
        section_count=len([k for k in ctx.sections if "." not in k]),
        section_spans=_section_spans(ctx),
        mutation_sections=_mutation_sections(ctx),
        member_enumerations=_member_enumerations(ctx),
        level_chains=_level_chains(ctx),
        harness_fields=_harness_field_counts(ctx),
        prefix_count=_prefix_count(ctx),
    )

    for art in ctx.scanned:
        ranges = [(m.start(), m.end()) for m in SECTION_RANGE_SPAN_RE.finditer(art.text)]
        for m in COUNT_CLAUSE_RE.finditer(art.text):
            yield from _check_line_count(ctx, cc, art, m.start(), m, ranges)
        for m in SECTIONS_CLAUSE_RE.finditer(art.text):
            yield from _check_section_count(ctx, cc, art, m.start(), m, ranges)
        for m in _COUNT_NOUN_RE.finditer(art.text):
            yield from _check_noun_count(ctx, cc, art, m.start(), m, ranges)
        for m in MUTATION_RANGE_RE.finditer(art.text):
            yield from _check_mutation_range(ctx, cc, art, m)


def _in_section_range(ranges: Sequence[tuple[int, int]], m: re.Match[str]) -> bool:
    """True when the matched *number* is one endpoint of a `§A-§B` section range."""
    start, end = m.start(), m.end()
    return any(start < r_end and r_start < end for r_start, r_end in ranges)


def _range_endpoint_notice(ctx: Context, art: Artefact, m: re.Match[str],
                           offset: int) -> Finding:
    line_no, _ = _own_line(art, offset)
    return _ok(
        ctx, "RI-09-COUNT", "count-range-endpoint",
        f"{art.loc(line_no)} does not claim a count: {m.group(0).strip()!r} reads its number "
        f"off a § section range, and a range endpoint is a section label rather than a "
        f"population. The range itself is still verified by the mutation-range rule.",
        file=art.name, line=line_no, claim=m.group(0).strip(),
    )


def _own_line(art: Artefact, offset: int) -> tuple[int, str]:
    line_no = _line_of(art, offset)
    return line_no, art.lines[line_no - 1]


def _check_line_count(ctx: Context, cc: CountContext, art: Artefact, offset: int,
                      m: re.Match[str],
                      ranges: Sequence[tuple[int, int]] = ()) -> Iterable[Finding]:
    if _in_section_range(ranges, m):
        yield _range_endpoint_notice(ctx, art, m, offset)
        return
    claimed = int(m.group(1).replace(",", ""))
    line_no, line = _own_line(art, offset)
    ref = _nearest_file_ref(ctx, art, line_no, offset)
    if ref is None:
        section = _section_in_line(line)
        if section and section in cc.section_spans:
            lo, hi = cc.section_spans[section]
            yield _ok(ctx, "RI-09-COUNT", "count-section-scoped",
                      f"{art.loc(line_no)} claims input.md §{section} is '{m.group(0)}'; this "
                      f"checker cannot settle it because the heading-to-heading convention is "
                      f"undefined (counting the heading line gives {hi - lo + 1}, excluding it "
                      f"gives {hi - lo})",
                      section=section, claimed=claimed, with_heading=hi - lo + 1,
                      without_heading=hi - lo)
            return
        yield _ok(ctx, "RI-09-COUNT", "count-unverifiable",
                  f"{art.loc(line_no)} claims '{m.group(0)}' but no artefact file is named on "
                  f"the same or preceding line, so the count cannot be recomputed here",
                  file=art.name, line=line_no, claimed=claimed, claim=m.group(0))
        return
    actual = cc.line_count.get(ref)
    if actual is None:
        actual = len((ctx.spec_dir / ref).read_text(encoding="utf-8",
                                                    errors="replace").splitlines())
    if claimed != actual:
        yield _f(ctx, "RI-09-COUNT", "count-line-mismatch",
                 f"{art.loc(line_no)} claims {ref} is '{m.group(0)}'; it is actually "
                 f"{actual} lines",
                 [art.loc(line_no)], file=ref, claimed=claimed, actual=actual, claim=m.group(0))
    else:
        yield _ok(ctx, "RI-09-COUNT", "count-line-ok",
                  f"{art.loc(line_no)} claim '{m.group(0)}' for {ref} verified",
                  file=ref, claimed=claimed, actual=actual)


def _nearest_file_ref(ctx: Context, art: Artefact, line_no: int, offset: int) -> str | None:
    """The file the count is about: nearest reference on the claim line, else the line above."""
    for probe in (line_no, line_no - 1):
        if probe < 1 or probe > len(art.lines):
            continue
        text = art.lines[probe - 1]
        matches = list(FILE_REF_RE.finditer(text))
        resolved = [(m, _resolve_in_spec_dir(ctx, m.group("path"))) for m in matches]
        resolved = [(m, r) for m, r in resolved if r]
        if not resolved:
            continue
        if probe == line_no:
            before = [(m, r) for m, r in resolved if m.end() <= offset]
            if before:
                return max(before, key=lambda mr: mr[0].end())[1]
            return resolved[0][1]
        return resolved[-1][1]
    return None


def _section_in_line(line: str) -> str | None:
    m = SECTION_RE.search(line)
    return m.group("a") if m else None


def _check_section_count(ctx: Context, cc: CountContext, art: Artefact, offset: int,
                         m: re.Match[str],
                         ranges: Sequence[tuple[int, int]] = ()) -> Iterable[Finding]:
    if _in_section_range(ranges, m):
        yield _range_endpoint_notice(ctx, art, m, offset)
        return
    claimed = int(m.group(1).replace(",", ""))
    line_no, _ = _own_line(art, offset)
    ref = _nearest_file_ref(ctx, art, line_no, offset)
    if ref != "input.md":
        return
    if claimed != cc.section_count:
        yield _f(ctx, "RI-09-COUNT", "count-section-mismatch",
                 f"{art.loc(line_no)} claims input.md has {claimed} sections; it has "
                 f"{cc.section_count} numbered top-level sections",
                 [art.loc(line_no)], file="input.md", claimed=claimed, actual=cc.section_count)
    else:
        yield _ok(ctx, "RI-09-COUNT", "count-section-ok",
                  f"{art.loc(line_no)} claim '{m.group(0)}' for input.md verified",
                  file="input.md", claimed=claimed, actual=cc.section_count)


def _check_noun_count(ctx: Context, cc: CountContext, art: Artefact, offset: int,
                      m: re.Match[str],
                      ranges: Sequence[tuple[int, int]] = ()) -> Iterable[Finding]:
    if _in_section_range(ranges, m):
        yield _range_endpoint_notice(ctx, art, m, offset)
        return
    claimed = _as_int(m.group("num"))
    if claimed is None:
        return
    line_no, _ = _own_line(art, offset)
    noun = re.sub(r"\s+", " ", m.group("noun").lower())
    window = _claim_window(art, line_no, ctx.defs)
    actual, basis = _counter_for(cc, noun, window, art.name, line_no, art.lines[line_no - 1])
    if actual is None or actual < 0:
        yield _ok(ctx, "RI-09-COUNT", "count-unverifiable",
                  f"{art.loc(line_no)} claims '{m.group(0).strip()}' but this checker has no "
                  f"counter for '{noun}' in the artefact set",
                  file=art.name, line=line_no, claimed=claimed, noun=noun,
                  claim=m.group(0).strip())
        return
    if claimed != actual:
        yield _f(ctx, "RI-09-COUNT", "count-mismatch",
                 f"{art.loc(line_no)} claims '{m.group(0).strip()}' but {basis} is {actual}",
                 [art.loc(line_no)], file=art.name, line=line_no, claimed=claimed, actual=actual,
                 noun=noun, basis=basis, claim=m.group(0).strip())
    else:
        yield _ok(ctx, "RI-09-COUNT", "count-ok",
                  f"{art.loc(line_no)} claim '{m.group(0).strip()}' verified ({basis} = {actual})",
                  file=art.name, line=line_no, claimed=claimed, actual=actual, noun=noun,
                  basis=basis)


def _check_mutation_range(ctx: Context, cc: CountContext, art: Artefact,
                          m: re.Match[str]) -> Iterable[Finding]:
    """A `§A-§B` range used as a mutation range must actually be all mutation sections."""
    line_no, line = _own_line(art, m.start())
    if not re.search(r"mutation", line, re.IGNORECASE):
        return
    lo, hi = int(m.group("lo")), int(m.group("hi"))
    inside = sorted((k for k in cc.mutation_sections if lo <= int(k) <= hi), key=int)
    outside = [str(k) for k in range(lo, hi + 1) if str(k) not in cc.mutation_sections]
    if outside:
        titles = "; ".join(
            f"§{n} = {ctx.sections[n]['title']}" for n in outside if n in ctx.sections
        )
        yield _f(ctx, "RI-09-COUNT", "mutation-range-not-mutation",
                 f"{art.loc(line_no)} uses §{lo}-§{hi} as a mutation range, but "
                 f"{len(outside)} of its {hi - lo + 1} sections are not mutation sections: "
                 f"{titles}",
                 [art.loc(line_no)], lo=lo, hi=hi, mutation_sections=inside,
                 non_mutation_sections=outside)


def _counter_for(cc: CountContext, noun: str, window: str, art_name: str,
                 line_no: int, line: str) -> tuple[int | None, str]:
    if noun in {"fr", "frs", "functional requirement", "functional requirements",
                "requirement", "requirements"}:
        return cc.fr_count, "the number of FR definitions in spec.md"
    if noun in {"sc", "scs", "success criteria", "measurable outcome", "measurable outcomes",
                "outcome", "outcomes"}:
        return cc.sc_count, "the number of SC definitions in spec.md"
    if noun in {"inv", "invs", "constitutional invariant", "constitutional invariants"}:
        return cc.inv_count, "the number of INV definitions in spec.md"
    if noun in {"user stories", "stories"}:
        return cc.story_count, "the number of User Story headings in spec.md"
    if noun == "sections":
        return cc.section_count, "the number of numbered top-level input.md sections"
    if noun == "members":
        for loc, _claimed, enumerated, how in cc.member_enumerations:
            if loc.startswith(f"{art_name}:") and abs(i_of(loc) - line_no) <= 1:
                if enumerated < 0:
                    return None, "enum members"
                return enumerated, f"the number of enum members counted from {how}"
        return None, "enum members"
    if noun == "levels":
        for loc, _claimed, enumerated in cc.level_chains:
            if loc.startswith(f"{art_name}:") and abs(i_of(loc) - line_no) <= 1:
                if enumerated < 0:
                    return None, "levels"
                return enumerated, "the number of items in the arrow chain beside the claim"
        return None, "levels"
    if noun == "mutations":
        rng = re.search(r"§\s*(\d+)\s*[" + DASHES + r"]\s*§?\s*(\d+)", line) or \
            re.search(r"§\s*(\d+)\s*[" + DASHES + r"]\s*§?\s*(\d+)", window)
        if rng:
            lo, hi = int(rng.group(1)), int(rng.group(2))
            inside = [k for k in cc.mutation_sections if lo <= int(k) <= hi]
            not_mut = [str(k) for k in range(lo, hi + 1) if str(k) not in cc.mutation_sections]
            return len(inside), (
                f"the number of MUTATION sections in input.md §{lo}-§{hi} "
                f"({len(inside)} found; sections in that range which are not mutation "
                f"sections: {', '.join('§' + n for n in not_mut) or 'none'})"
            )
        body_refs = {m.group(1) for m in re.finditer(r"§\s*(\d+)", window)}
        if body_refs:
            found = sorted((r for r in body_refs if r in cc.mutation_sections), key=int)
            return len(found), (
                "the number of MUTATION sections cited in the same claim "
                f"({', '.join('§' + f for f in found) or 'none'})"
            )
        return None, "mutations"
    if noun == "invariants":
        if re.search(r"mutation|harness|break", window, re.IGNORECASE) and cc.harness_fields:
            total = sum(cc.harness_fields.values())
            frs = ", ".join(f"{k}={v}" for k, v in sorted(cc.harness_fields.items()))
            return total, (
                "the number of enumerated fields the constitutional mutation harness is "
                f"required to break ({frs})"
            )
        return cc.inv_count, "the number of INV definitions in spec.md"
    if noun == "prefixes":
        return (cc.prefix_count or None), (
            "the number of synthetic ref prefixes listed in data-model.md"
        )
    return None, noun



def i_of(loc: str) -> int:
    _, _, line = loc.rpartition(":")
    try:
        return int(line)
    except ValueError:
        return 0


# --- RI-10 forbidden claims ----------------------------------------------------------------


def check_forbidden(ctx: Context) -> Iterable[Finding]:
    dm = ctx.by_name("data-model.md")
    if dm and dm.read_ok:
        yield from _forbidden_synonym_in_identity(ctx, dm)
        yield from _forbidden_nested_hypothesis(ctx, dm)
    yield from _forbidden_vocabulary_without_producer(ctx)


def _forbidden_synonym_in_identity(ctx: Context, dm: Artefact) -> Iterable[Finding]:
    """N5-style equivalence inside the identity path is forbidden."""
    in_code = False
    section = ""
    identity_headings = re.compile(
        r"PredicateSignature|Identity|logical_candidate_id|normalisation|Normalisation", re.I
    )
    for i, line in enumerate(dm.lines, start=1):
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if line.startswith("#"):
            section = line
        if not identity_headings.search(section):
            continue
        if re.search(r"[\u2261\u2248]|\bsynonym|\bequivalen|\buni(?:fy|fies)\b|"
                     r"same\s+(?:logical\s+)?(?:candidate|signature)", line, re.I):
            yield _f(ctx, "RI-10-FORBIDDEN", "synonym-in-identity",
                     f"data-model.md:{i} states a synonym/equivalence rule inside the identity "
                     f"path ('{section.strip()}'): a synonym table inside "
                     f"`logical_candidate_id` material makes the table an identity authority",
                     [dm.loc(i)], section=section.strip(), line=line.strip()[:200])


# `hypothesis_state` is brief §6's *required* field on `TypeHypothesis`
# (input.md:465-492): a scalar verdict, not a nested hypothesis. Exempt by name, and
# independently by type shape, so one layer of the exemption cannot be lost.
HYPOTHESIS_STATE_FIELDS: frozenset[str] = frozenset({"hypothesis_state"})

# `HypothesisState` / `HypothesisStatus` / ... are scalar enums. A type whose *name* is
# one of these states a verdict, whatever container word appears in the annotation.
_HYPOTHESIS_SCALAR_TYPE_RE = re.compile(
    r"\b\w*Hypothesis(?:State|Status|Mode|Kind|Verdict|Phase)\b"
)
# A collection type in an annotation, including the `...Hypotheses` / `HypothesisSet`
# spellings, which are containers by name.
_COLLECTION_TYPE_RE = re.compile(
    r"\b(?:tuple|list|set|frozenset|Sequence|MutableSequence|Iterable|Iterator"
    r"|Collection|MutableSet|Mapping|dict|deque|Deque|array|Array|Vector|Generator"
    r"|Hypotheses|HypothesisSet|HypothesisList|HypothesisCollection|HypothesisBundle"
    r"|HypothesisGroup|HypothesisBatch)\b"
)
# Any type whose name says "hypothesis": the element type of a real container.
_HYPOTHESIS_TYPE_RE = re.compile(r"\b\w*Hypothes\w*\b")
_HYPOTHESIS_CONTAINER_NAME_RE = re.compile(r"hypothes", re.IGNORECASE)
_ANY_CLASS_RE = re.compile(r"^[ \t]*class[ \t]+(?P<name>\w+)\s*[:(\[]")
# `    name: Annotation = default   # comment`
_DATACLASS_FIELD_RE = re.compile(r"^[ \t]{1,12}(?P<name>\w+)[ \t]*:[ \t]*(?P<type>[^#=\n]+)")


def _annotation_of(type_text: str) -> str:
    return type_text.split("#")[0].split("=")[0].strip()


def field_nests_hypotheses(name: str, type_text: str) -> bool:
    """Does this field make its enclosing hypothesis a *container of hypotheses*?

    The violation is epistemic, so it is decided on the field's type shape and only then
    on its name. Two ways to earn a FAIL:

    * the annotation is a collection whose element type is a `*Hypothesis`
      (`hypotheses: tuple[TypeHypothesis, ...]`, `alternatives: Sequence[DirectionHypothesis]`);
    * the annotation is any collection and the *field name* says it holds hypotheses
      (`hypotheses: tuple[str, ...]` - the element type may be a ref, the container is
      still a set of hypotheses).

    A scalar hypothesis-adjacent field is legal, so `hypothesis_state: HypothesisState`
    (brief §6, required) and any `*HypothesisState`-typed field do not fire. A scalar
    field typed as a plain `*Hypothesis` and not a collection is out of this rule's scope
    by design; the rule text says so, so the gap is stated rather than silent.
    """
    annotation = _annotation_of(type_text)
    if not annotation or name in HYPOTHESIS_STATE_FIELDS:
        return False
    if _HYPOTHESIS_SCALAR_TYPE_RE.search(annotation):
        return False
    if not _COLLECTION_TYPE_RE.search(annotation):
        return False
    if _HYPOTHESIS_TYPE_RE.search(annotation):
        return True
    return bool(_HYPOTHESIS_CONTAINER_NAME_RE.search(name))


def _forbidden_nested_hypothesis(ctx: Context, dm: Artefact) -> Iterable[Finding]:
    in_code = False
    current = ""
    for i, line in enumerate(dm.lines, start=1):
        if line.lstrip().startswith("```"):
            if not in_code:
                current = ""
            in_code = not in_code
            continue
        cls = _ANY_CLASS_RE.match(line)
        if cls:
            # *Any* `class` line re-anchors the container. A field that follows a
            # non-hypothesis class in the same fence belongs to that class, not to the
            # hypothesis class declared earlier in the fence.
            name = cls.group("name")
            current = name if name.endswith("Hypothesis") else ""
        if not in_code or not current:
            continue
        m = _DATACLASS_FIELD_RE.match(line)
        if not m:
            continue
        name, type_text = m.group("name"), m.group("type")
        if not field_nests_hypotheses(name, type_text):
            continue
        yield _f(ctx, "RI-10-FORBIDDEN", "nested-hypothesis",
                 f"data-model.md:{i} makes `{current}` a container of hypotheses "
                 f"(field `{name}: {type_text.strip()}`): a set of hypotheses is a new "
                 f"epistemic level, not a hypothesis",
                 [dm.loc(i)], container=current, field=name,
                 annotation=type_text.strip())


def _forbidden_vocabulary_without_producer(ctx: Context) -> Iterable[Finding]:
    vocab: dict[str, str] = {}
    for d in ctx.defs:
        for m in CODE_SPAN_RE.finditer(d.body):
            lit = m.group("body").strip()
            if re.match(r"^(?:core|value):[A-Z]", lit):
                vocab[lit] = d.ident
    if not vocab:
        return
    producer_obligations: set[str] = set()
    for d in ctx.defs:
        body = " ".join(CODE_SPAN_RE.sub(lambda m: m.group("body"), d.body))
        if not re.search(r"\bMUST\b", body):
            continue
        if re.search(r"producer|extractor|emit|writes?\s+to", body, re.I):
            producer_obligations.add(d.ident)
    unbacked = sorted(v for v, owner in vocab.items() if owner not in producer_obligations)
    if unbacked:
        owners = sorted({vocab[v] for v in unbacked})
        yield _f(ctx, "RI-10-FORBIDDEN", "vocabulary-without-producer",
                 f"{len(unbacked)} vocabulary terms are mandated by {owners} but no requirement "
                 f"obliges any producer or extractor to emit them: the list has no producer "
                 f"obligation",
                 [], terms=unbacked, owner_frs=owners, count=len(unbacked),
                 producer_obligation_frs=sorted(producer_obligations))


# --- RI-11 constitution ----------------------------------------------------------------------


_TOPIC_STOP = {
    "the", "a", "an", "of", "and", "or", "not", "is", "are", "be", "as", "by", "for",
    "from", "with", "that", "this", "must", "should", "may", "never", "no", "any",
    "every", "all", "only", "its", "their", "his", "her", "our", "your", "one", "two",
    "first", "second", "third", "last", "next", "same", "other", "such", "than", "then",
    "when", "while", "which", "where", "who", "what", "why", "how", "into", "onto", "per",
    "via", "out", "off", "over", "under", "up", "down", "again", "also", "still", "yet",
}
_PRINCIPLE_CITE_RE = re.compile(
    r"\b(?:principle|principles|constitution|clause)\s+"
    r"(?P<roman>[IVXL]{1,4})\s*(?P<dash>[—–-]|:)?\s*(?P<topic>[A-Za-z][A-Za-z\-]*)",
    re.IGNORECASE,
)
_BARE_PRINCIPLE_RE = re.compile(
    r"(?P<start>^|[|(\s])(?P<roman>[IVXL]{1,4})\s+(?P<topic>[a-z][a-z\-]{2,})\s*[|)]",
)
# A roman numeral followed by a verb is not a *topic*: "Constitution III makes the graph a
# projection" cites Principle III correctly and says nothing about what it is called.
_NOT_A_TOPIC = {
    "makes", "make", "made", "making", "is", "are", "was", "were", "has", "have", "had",
    "requires", "require", "required", "forbids", "forbid", "states", "state", "said",
    "says", "demands", "demand", "wins", "supersedes", "supercedes", "rules", "binds",
    "bind", "governs", "govern", "outranks", "overrides", "override", "beats", "beat",
}


def _topic_terms(text: str) -> set[str]:
    return {
        w for w in re.split(r"[^A-Za-z]+", text.lower())
        if len(w) >= 4 and w not in _TOPIC_STOP
    }


def check_constitution(ctx: Context) -> Iterable[Finding]:
    const = ctx.constitution
    if const is None or not const.read_ok:
        return
    const_text = const.text
    for art in ctx.scanned:
        for i, line in enumerate(art.lines, start=1):
            for m in CD_TOKEN_RE.finditer(line):
                pat = rf"\b{re.escape(m.group(0))}\b\s*[:.]?\s*\S"
                defined = bool(re.search(pat, const_text)) or bool(
                    re.search(rf"^#{{1,6}}\s+{re.escape(m.group(0))}\b", const_text,
                              re.MULTILINE)
                )
                if defined:
                    yield _ok(ctx, "RI-11-CONST", "cd-defined",
                              f"{art.name}:{i} cites {m.group(0)}, which exists in the "
                              f"constitution", raw=m.group(0))
                else:
                    yield _f(ctx, "RI-11-CONST", "cd-phantom",
                             f"{art.name}:{i} cites {m.group(0)}, but the constitution defines "
                             f"no such label: its Domain Invariants are an unlabelled numbered "
                             f"list, so {m.group(0)} is a phantom reference",
                             [art.loc(i)], raw=m.group(0))
            for pat in (_PRINCIPLE_CITE_RE, _BARE_PRINCIPLE_RE):
                for m in pat.finditer(line):
                    roman = m.group("roman").upper()
                    topic = m.group("topic")
                    if roman not in ctx.principles or not topic:
                        continue
                    if topic.lower() in _NOT_A_TOPIC:
                        continue
                    title = ctx.principles[roman]
                    claim_terms = _topic_terms(topic)
                    title_terms = _topic_terms(title)
                    if not claim_terms or not title_terms:
                        continue
                    if claim_terms & title_terms:
                        yield _ok(ctx, "RI-11-CONST", "principle-cite-ok",
                                  f"{art.name}:{i} cites Principle {roman} ({topic}); the "
                                  f"constitution's Principle {roman} is '{title}'",
                                  roman=roman, topic=topic, title=title)
                        continue
                    yield Finding(
                        check_id="RI-11-CONST", severity=WARN, code="principle-miscite",
                        message=(
                            f"{art.name}:{i} cites 'Principle {roman} — {topic}' but the "
                            f"constitution's Principle {roman} is '{title}': no content word "
                            f"in the claimed topic appears in the real title"
                        ),
                        locations=[art.loc(i)],
                        data={"roman": roman, "claimed_topic": topic, "actual_title": title,
                              "claim_terms": sorted(claim_terms),
                              "title_terms": sorted(title_terms)},
                    )


def check_research_refs(ctx: Context) -> Iterable[Finding]:
    if not ctx.research_defs:
        yield _f(ctx, "RI-11b-RESEARCH", "no-research-defs",
                 "research.md defines no `## R-nnn` decisions", [])
        return
    for art in ctx.scanned:
        for i, line in enumerate(art.lines, start=1):
            for m in RESEARCH_TOKEN_RE.finditer(line):
                if art.name == "research.md":
                    continue
                if m.group(0) not in ctx.research_defs:
                    yield _f(ctx, "RI-11b-RESEARCH", "research-phantom",
                             f"{art.name}:{i} cites {m.group(0)}, which research.md does not "
                             f"define", [art.loc(i)], raw=m.group(0))


# --- RI-12 stale claims -----------------------------------------------------------------------


def check_stale_claims(ctx: Context) -> Iterable[Finding]:
    known: dict[str, str] = {}
    for path in sorted(ctx.spec_dir.rglob("*")):
        if path.is_file() and "repair" not in path.relative_to(ctx.spec_dir).parts:
            known.setdefault(path.name, str(path.relative_to(ctx.spec_dir)).replace("\\", "/"))
    for art in ctx.scanned:
        for i, line in enumerate(art.lines, start=1):
            for claim in STALE_RE.finditer(line):
                # The path the claim is about is the most path-like token to its left:
                # a token that names a file in this directory wins, then anything with a
                # dot or a slash, then the nearest word. "tasks.md is NOT yet created"
                # must resolve to tasks.md, not to the word "is".
                best, best_score = None, -1
                for token in _PATH_TOKEN_RE.finditer(line[: claim.start()]):
                    raw = token.group(0)
                    text = raw.rstrip("/")
                    score = 0
                    if text in known:
                        score += 4
                    if _resolve_in_spec_dir(ctx, text):
                        score += 2
                    if "." in raw or "/" in raw:
                        score += 1
                    if score >= best_score:
                        best, best_score = text, score
                if best is None or best_score <= 0:
                    yield _ok(ctx, "RI-12-STALE", "stale-unattributable",
                              f"{art.loc(i)} claims something is NOT yet created but names no "
                              f"path, so the claim cannot be checked",
                              file=art.name, line=i, line_text=line.strip()[:160])
                    continue
                if (ctx.spec_dir / best).exists():
                    yield _f(ctx, "RI-12-STALE", "stale-not-created",
                             f"{art.loc(i)} claims `{best}` is NOT yet created, but it exists",
                             [art.loc(i)], path=best)
                elif best in known:
                    yield _f(ctx, "RI-12-STALE", "stale-not-created-bare-name",
                             f"{art.loc(i)} claims `{best}` is NOT yet created, but "
                             f"`{known[best]}` exists (the claim names the file without its "
                             f"directory)",
                             [art.loc(i)], path=best, resolves_to=known[best])
                else:
                    yield _ok(ctx, "RI-12-STALE", "stale-claim-consistent",
                              f"{art.loc(i)} claims `{best}` is NOT yet created, and it does not "
                              f"exist: the claim is currently true",
                              path=best, line=i)


# ------------------------------------------------------------------------------------------
# Governance checks: tombstones, FR namespace, epistemic axes, count precision, ghost suffixes
# ------------------------------------------------------------------------------------------
#
# These five read the `repair/` governance corpus in addition to the spec artefacts. They are
# additive: nothing here is reachable from an RI-* check, and no existing parsing path changed.

# --- TOMBSTONED-FR-REF -----------------------------------------------------------------------

# `repair/ARBITRATION.md` §2. Edit this mapping when the arbitration record moves a tombstone's
# replacement target; the check reads nothing else to learn the set.
TOMBSTONED_FRS: dict[str, str] = {
    "FR-034a": "INV-002",
    "FR-058": "INV-004",
    "FR-070": "design note",
    "FR-079": "FR-078",
    "FR-080": "FR-072",
}

# A citation that carries one of these is *history*, which the rule allows. Kept small and
# literal on purpose: a broad marker would silently un-break the check.
DEPRECATION_MARKERS: tuple[str, ...] = (
    "tombstone", "tombstoned", "tombstoning",
    "deprecated", "deprecation",
    "absorb", "merged into", "merge target", "merged away",
    "see adr", "see the adr",
    "superseded", "folded into", "fold into",
    "no longer normative", "not normative",
)
DEPRECATION_RE = re.compile("|".join(re.escape(p) for p in DEPRECATION_MARKERS), re.IGNORECASE)


def check_tombstoned_fr_refs(ctx: Context) -> Iterable[Finding]:
    """Gate `TOMBSTONED_FR_MUST_HAVE_ZERO_NORMATIVE_REFERENCES` (ARBITRATION §2)."""
    live = 0
    exempted = 0
    for fr in sorted(TOMBSTONED_FRS):
        replacement = TOMBSTONED_FRS[fr]
        token = re.compile(rf"\b{re.escape(fr)}\b")
        for art in ctx.scanned:
            for i, line in enumerate(art.lines, start=1):
                if fr not in line:
                    continue
                if DEPRECATION_RE.search(line):
                    exempted += len(token.findall(line))
                    continue
                is_definition = bool(
                    DEF_RE.match(line) and DEF_RE.match(line).group("ident") == fr
                )
                live += 1
                yield Finding(
                    check_id="TOMBSTONED-FR-REF", severity=FAIL,
                    code=("tombstoned-fr-defined-normative" if is_definition
                          else "tombstoned-fr-cited-normative"),
                    message=(
                        f"{art.loc(i)} "
                        + ("defines" if is_definition else "cites")
                        + f" {fr}, which `repair/ARBITRATION.md` §2 tombstoned: a tombstone is "
                        f"historical traceability only, and this line points at it as a live "
                        f"normative target. Replacement target: {replacement}."
                    ),
                    locations=[art.loc(i)],
                    data={"fr": fr, "replacement": replacement, "artefact": art.name,
                          "is_definition": is_definition, "quoted": line.strip()[:220]},
                )
    yield _ok(
        ctx, "TOMBSTONED-FR-REF", "tombstone-summary",
        f"{len(TOMBSTONED_FRS)} tombstoned ids ({', '.join(sorted(TOMBSTONED_FRS))}): "
        f"{live} live normative reference(s), {exempted} citation(s) carrying a deprecation "
        f"marker and therefore read as history",
        tombstoned=sorted(TOMBSTONED_FRS), live_references=live, exempted=exempted,
        replacements=dict(sorted(TOMBSTONED_FRS.items())),
    )


# --- FR-NAMESPACE-COLLISION --------------------------------------------------------------------

# A repair document owns a requirement with a *bold title line*: the line opens a bold span with
# the FR id, the span closes on the same line, and nothing but a dash-separated gloss may follow.
# The negative lookahead rejects an id that continues into a range (`FR-001–FR-100`).
REPAIR_FR_DEF_RE = re.compile(
    r"^[ \t>]*(?P<title>\*\*(?P<ident>FR-\d{3}[A-Za-z]?)(?![-\u2010-\u2015\d])[^*]{0,200}\*\*)"
    r"(?P<gloss>[ \t]*(?:[-\u2013\u2014][ \t]*[*_]?[^*\n]{0,140}\*?)?)[ \t]*$"
)


@dataclass
class RepairDefinition:
    ident: str
    line: int
    title: str
    body: str
    artefact: str
    kind: str


def _strip_quote(line: str) -> str:
    return re.sub(r"^[ \t]*(?:>[ \t]?)+", "", line)


def prose_line_flags(art: Artefact) -> list[bool]:
    """Per line: is this prose, or is it inside/adjacent to a fenced code block?

    A fenced block is quoted material, everywhere in this tool. `A7-migration-021.md`
    quotes old requirement text under a "verbatim" heading; a review report quotes the
    defect it is describing; a repair report quotes the FR it proposes. None of those is a
    second claim on the requirement, so none of them counts as one.
    """
    flags: list[bool] = []
    fence: str | None = None
    for line in art.lines:
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            token = stripped[:3]
            fence = None if fence == token else (token if fence is None else fence)
            flags.append(False)
            continue
        flags.append(fence is None)
    return flags


def _definition_kind(title: str) -> str:
    if re.search(r"\(\s*NEW\s*\)", title, re.IGNORECASE):
        return "new-requirement"
    if re.search(r"\(\s*REWRITE\s*\)", title, re.IGNORECASE):
        return "rewrite-proposal"
    return "redefinition"


def parse_repair_definitions(art: Artefact) -> list[RepairDefinition]:
    """Every bold-titled FR definition in a repair document, outside code fences.

    A fenced block is quoted material (a "old text, verbatim" block is a citation of the
    past, not a second claim on the number), so it never yields a definition site. So does a
    title whose body is a fence, a table or a heading: there is no requirement text there.
    """
    out: list[RepairDefinition] = []
    lines = art.lines
    prose = prose_line_flags(art)
    for i, line in enumerate(lines):
        if not prose[i]:
            continue
        m = REPAIR_FR_DEF_RE.match(line)
        if not m:
            continue
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j >= len(lines):
            continue
        head = lines[j].lstrip()
        if (head.startswith("```") or head.startswith("~~~") or head.startswith("|")
                or HEADING_RE.match(lines[j])):
            continue
        body_lines: list[str] = []
        k = j
        while k < len(lines) and lines[k].strip():
            if REPAIR_FR_DEF_RE.match(lines[k]):
                break
            body_lines.append(lines[k])
            k += 1
        body = "\n".join(_strip_quote(b) for b in body_lines).strip()
        if not body:
            continue
        title = m.group("title")
        out.append(RepairDefinition(
            ident=m.group("ident"), line=i + 1, title=title, body=body,
            artefact=art.name, kind=_definition_kind(title),
        ))
    return out


def _normalise_requirement(text: str) -> str:
    """Two texts are 'the same requirement' when they differ only in markdown decoration."""
    cleaned = CODE_SPAN_RE.sub(lambda m: m.group("body"), text)
    cleaned = re.sub(r"[*_>`]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return re.sub(r"[^\w\s]", "", cleaned).strip().lower()


@dataclass
class _DefinitionSite:
    ident: str
    artefact: str
    line: int
    text: str
    kind: str


def collect_fr_definition_sites(ctx: Context) -> dict[str, list[_DefinitionSite]]:
    sites: dict[str, list[_DefinitionSite]] = defaultdict(list)
    spec = ctx.by_name("spec.md")
    if spec is not None and spec.read_ok:
        for d in ctx.def_occurrences:
            if not d.ident.startswith("FR-"):
                continue
            sites[d.ident].append(_DefinitionSite(
                ident=d.ident, artefact=spec.name, line=d.line, text=d.body,
                kind="canonical-definition",
            ))
    for art in ctx.repair:
        for d in parse_repair_definitions(art):
            sites[d.ident].append(_DefinitionSite(
                ident=d.ident, artefact=art.name, line=d.line, text=d.body, kind=d.kind,
            ))
    return sites


def check_fr_namespace_collisions(ctx: Context) -> Iterable[Finding]:
    sites = collect_fr_definition_sites(ctx)
    collisions = 0
    identical = 0
    for ident in sorted(sites):
        group = sites[ident]
        if len(group) < 2:
            continue
        for a_i in range(len(group)):
            for b_i in range(a_i + 1, len(group)):
                first, second = group[a_i], group[b_i]
                if _normalise_requirement(first.text) == _normalise_requirement(second.text):
                    identical += 1
                    yield _ok(
                        ctx, "FR-NAMESPACE-COLLISION", "fr-redefined-identically",
                        f"{ident} is defined at {len(group)} sites "
                        f"({', '.join(f'{s.artefact}:{s.line}' for s in group)}) with "
                        f"byte-identical requirement text after normalisation: a restatement, "
                        f"not a second owner",
                        fr=ident, sites=[f"{s.artefact}:{s.line}" for s in group],
                    )
                    continue
                collisions += 1
                owners = {first.kind, second.kind}
                shape = ("spec-vs-repair" if "canonical-definition" in owners
                         else "repair-vs-repair")
                yield Finding(
                    check_id="FR-NAMESPACE-COLLISION", severity=FAIL,
                    code="fr-namespace-collision",
                    message=(
                        f"{ident} is defined twice with different requirement text "
                        f"({shape}): {first.artefact}:{first.line} says "
                        f"\"{_excerpt(first.text)}\" ({first.kind}) while "
                        f"{second.artefact}:{second.line} says "
                        f"\"{_excerpt(second.text)}\" ({second.kind}). One FR number, two "
                        f"requirement texts, two owners."
                    ),
                    locations=[f"{first.artefact}:{first.line}",
                               f"{second.artefact}:{second.line}"],
                    data={"fr": ident, "shape": shape, "kinds": sorted(owners),
                          "sites": [{"artefact": s.artefact, "line": s.line, "kind": s.kind,
                                     "text": _excerpt(s.text, 320)} for s in (first, second)]},
                )
    yield _ok(
        ctx, "FR-NAMESPACE-COLLISION", "fr-namespace-summary",
        f"{len(sites)} FR ids have a definition site in spec.md or a repair document; "
        f"{collisions} id(s) are defined twice with different text, {identical} site pair(s) "
        f"restate a definition without changing it",
        ids=len(sites), collisions=collisions, identical_restatements=identical,
    )


def _excerpt(text: str, width: int = 150) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= width else flat[: width - 1] + "\u2026"


# --- EPISTEMIC-AXIS-CONFLATION -----------------------------------------------------------------

# Structural disagreement vocabulary (ARBITRATION §3, `RelationCandidate.assembly_state`).
STRUCTURAL_TERMS: tuple[str, ...] = (
    "arity", "direction", "polarity", "role slot", "role-slot", "role slots",
    "role binding", "role bindings", "participant configuration", "participant structure",
    "subject_to_object", "object_to_subject", "incompatible participant",
    "structural disagreement", "structural conflict", "different slots", "two different slots",
)
STRUCTURAL_RE = re.compile(
    "|".join(re.escape(t) for t in STRUCTURAL_TERMS), re.IGNORECASE
)
CONTRADICTED_RE = re.compile(r"\bCONTRADICTED\b")
# A sentence carrying one of these is stating the prohibition, not committing the conflation.
EPISTEMIC_PROHIBITION_MARKERS: tuple[str, ...] = (
    "forbidden", "forbids", "forbid", "never", "must not", "must never", "may not",
    "no artefact may", "rather than", "instead of", "prohibited", "banned", "out of bounds",
    "must not become", "does not",
)
EPISTEMIC_PROHIBITION_RE = re.compile(
    "|".join(re.escape(m) for m in EPISTEMIC_PROHIBITION_MARKERS), re.IGNORECASE
)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.;!?])\s+")
LIST_ITEM_RE = re.compile(r"^[ \t]{0,10}(?:[-*+]\s+|\d+[.)]\s+)")


def prose_units(art: Artefact) -> list[tuple[int, int, str]]:
    """(first_line, last_line, text) per prose unit, skipping fenced code.

    A unit is one table row, one list item, or one paragraph - the smallest block a reader
    would call "a statement". Fenced code is quoted material and is not a statement.
    """
    lines = art.lines
    units: list[tuple[int, int, str]] = []
    fence: str | None = None
    i = 0

    def _opens_block(line: str) -> bool:
        s = line.lstrip()
        return (s.startswith("```") or s.startswith("~~~") or s.startswith("|")
                or bool(HEADING_RE.match(line)) or bool(LIST_ITEM_RE.match(line)))

    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            token = stripped[:3]
            fence = None if fence == token else (token if fence is None else fence)
            i += 1
            continue
        if fence is not None or not line.strip():
            i += 1
            continue
        if line.strip().startswith("|"):
            units.append((i + 1, i + 1, line))
            i += 1
            continue
        j = i + 1
        while j < len(lines) and lines[j].strip() and not _opens_block(lines[j]):
            j += 1
        units.append((i + 1, j, "\n".join(lines[i:j])))
        i = j
    return units


def _sentence_of(text: str, offset: int) -> tuple[str, int]:
    """(sentence, offset of its first character) for the sentence holding `offset`."""
    start = 0
    for m in SENTENCE_SPLIT_RE.finditer(text):
        if m.start() > offset:
            break
        start = m.start()
    return SENTENCE_SPLIT_RE.split(text[start:])[0].strip(), start


def check_epistemic_axis_conflation(ctx: Context) -> Iterable[Finding]:
    """Gate the ARBITRATION §3 three-axis rule on spec.md, tasks.md and `repair/*.md`."""
    corpus = ctx.readable(("spec.md", "tasks.md")) + ctx.repair
    conflations = 0
    restatements = 0
    for art in corpus:
        for first, _last, text in prose_units(art):
            if not CONTRADICTED_RE.search(text) or not STRUCTURAL_RE.search(text):
                continue
            structural = sorted({m.group(0).lower() for m in STRUCTURAL_RE.finditer(text)})
            seen_lines: set[int] = set()
            for m in CONTRADICTED_RE.finditer(text):
                sentence, _offset = _sentence_of(text, m.start())
                line_no = first + text.count("\n", 0, m.start())
                if line_no in seen_lines:
                    continue
                seen_lines.add(line_no)
                if EPISTEMIC_PROHIBITION_RE.search(sentence):
                    restatements += 1
                    continue
                conflations += 1
                yield Finding(
                    check_id="EPISTEMIC-AXIS-CONFLATION", severity=FAIL,
                    code="structural-conflict-as-denied",
                    message=(
                        f"{art.loc(line_no)} writes a structural disagreement "
                        f"({', '.join(structural)}) into `CONTRADICTED`. Per "
                        f"`repair/ARBITRATION.md` §3 a structural reading belongs on the NEW "
                        f"`RelationCandidate.assembly_state = CONFLICTING`; `CONTRADICTED` means "
                        f"the assertion itself is denied. Quoted: \""
                        f"{_excerpt(sentence, 220)}\""
                    ),
                    locations=[art.loc(line_no)],
                    data={"artefact": art.name, "structural_terms": structural,
                          "quoted": _excerpt(sentence, 320)},
                )
    yield _ok(
        ctx, "EPISTEMIC-AXIS-CONFLATION", "epistemic-summary",
        f"{len(corpus)} artefact(s) scanned for the three epistemic axes: "
        f"{conflations} sentence(s) route a structural disagreement into `CONTRADICTED`, "
        f"{restatements} sentence(s) mention both while prohibiting the conflation",
        conflations=conflations, prohibition_restatements=restatements,
        axes=["PredicateHypothesis.resolution_state=CONFLICTING (semantic)",
              "RelationCandidate.assembly_state=CONFLICTING (structural, NEW)",
              "CandidateStatus.CONTRADICTED (the assertion is denied)"],
    )


# --- COUNT-PRECISION ----------------------------------------------------------------------------

# ARBITRATION §10. Four numbers, one job each. The rule cannot tell a number from its context by
# itself, so the three enumerated conflation shapes are matched literally.
ENTITY_COUNT_NOUNS = (
    r"(?:foundational[ \t-]+)?(?:atomic[ \t-]+)?(?:entity[ \t-]+)?"
    r"(?:value[ \t-]+)?(?:type[ \t-]+)?(?:types?|classes|extractors|items?|families)"
)
WRONG_ENTITY_COUNT_RE = re.compile(
    rf"\b(?P<num>32)\b[ \t\u2010-\u2015-]*{ENTITY_COUNT_NOUNS}\b", re.IGNORECASE
)
# `seven_classes` inside a test name is the same defect as "seven classes" in prose, so the
# guard is "not part of a longer alphanumeric token" rather than a word boundary: `_` counts.
SEVEN_CLASSES_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:all[ \t_]+)?seven[ \t_-]+classes(?![A-Za-z0-9])", re.IGNORECASE
)

SECTION8_CONTEXT_RE = re.compile(
    r"\u00a7[ \t]*8\b|entity[ \t_-]*extractor|extractor|entity[ \t_-]*class", re.IGNORECASE
)
COUNT_REFUTATION_MARKERS: tuple[str, ...] = (
    # a correction of the number
    "corrected", "correction", "miscount", "misreading", "misquote", "mis-cite", "miscited",
    "renamed",
    # an assertion that the number is absent
    "is wrong", "does not exist", "nowhere writes", "nowhere states", "no such",
    "does not state", "review-prose",
    # an explicit negation of the number itself
    "not 32", "no 32", "never 32", "rather than 32", "instead of 32",
    "not seven classes", "never classes",
)
COUNT_REFUTATION_RE = re.compile(
    "|".join(re.escape(m) for m in COUNT_REFUTATION_MARKERS), re.IGNORECASE
)
AUTHORITY_NUMBERS: dict[str, int] = {
    "foundational entity types": 31,
    "value types": 13,
    "§8 extraction families": 7,
    "new instrument modules": 4,
}


def check_count_precision(ctx: Context) -> Iterable[Finding]:
    conflations = 0
    refuted = 0
    for art in ctx.governance():
        for first, last, text in prose_units(art):
            shapes: list[tuple[int, str, str, str]] = []
            for m in WRONG_ENTITY_COUNT_RE.finditer(text):
                shapes.append((m.start(), "count-32-as-entity-types", "32",
                               m.group(0).strip()))
            for m in SEVEN_CLASSES_RE.finditer(text):
                if not SECTION8_CONTEXT_RE.search(text):
                    continue
                shapes.append((m.start(), "count-seven-classes", "7", m.group(0).strip()))
            if not shapes:
                continue
            is_refutation = bool(COUNT_REFUTATION_RE.search(text))
            for offset, code, claimed, raw in shapes:
                line_no = first + text.count("\n", 0, offset)
                location = art.loc(line_no)
                if is_refutation:
                    refuted += 1
                    yield Finding(
                        check_id="COUNT-PRECISION", severity=INFO, code="count-refutation",
                        message=(
                            f"{location} carries the conflated phrase {raw!r} inside a passage "
                            f"that corrects it; reported as history, not as a live claim"
                        ),
                        locations=[location],
                        data={"code_hint": code, "artefact": art.name,
                              "quoted": _excerpt(text, 200)},
                    )
                    continue
                conflations += 1
                yield Finding(
                    check_id="COUNT-PRECISION", severity=WARN, code=code,
                    message=(
                        f"{location} says {raw!r} in a §8 / entity-extractor context. The "
                        f"authority is 31 foundational entity types, 13 value types, 7 §8 "
                        f"extraction families and ~4 new instrument modules - four numbers, four "
                        f"jobs. 'seven classes' is wrong vocabulary: the correct phrase is "
                        f"'seven extraction families' or '§8 subsections'."
                    ),
                    locations=[location],
                    data={"artefact": art.name, "claimed": claimed, "phrase": raw,
                          "unit_lines": [first, last],
                          "quoted": _excerpt(
                              art.lines[line_no - 1].strip() if line_no - 1 < len(art.lines)
                              else text, 240)},
                )
    yield _ok(
        ctx, "COUNT-PRECISION", "count-precision-summary",
        "four authority numbers checked: "
        + ", ".join(f"{n} {what}" for what, n in AUTHORITY_NUMBERS.items())
        + f". {conflations} live conflation(s), {refuted} conflated phrase(s) inside a "
          f"passage that corrects them",
        conflations=conflations, refutation_mentions=refuted,
        authority_numbers=dict(AUTHORITY_NUMBERS),
    )


# --- GHOST-SUFFIX ---------------------------------------------------------------------------------

GHOST_SUFFIX_RE = re.compile(r"\bFR-\d{3}(?P<suffix>[A-Za-z])\b")


def check_ghost_suffix(ctx: Context) -> Iterable[Finding]:
    live: dict[str, list[str]] = defaultdict(list)
    exempted = 0
    fenced = 0
    for art in ctx.governance():
        prose = prose_line_flags(art)
        for i, line in enumerate(art.lines, start=1):
            hits = [m.group(0) for m in GHOST_SUFFIX_RE.finditer(line)]
            if not hits:
                continue
            if not prose[i - 1]:
                fenced += len(hits)
                continue
            if DEPRECATION_RE.search(line):
                exempted += len(hits)
                continue
            for ident in sorted(set(hits)):
                live[ident].append(art.loc(i))
    for ident in sorted(live):
        locs = sorted(set(live[ident]), key=_loc_key)
        by_file: dict[str, int] = defaultdict(int)
        for loc in locs:
            by_file[loc.rpartition(":")[0]] += 1
        yield Finding(
            check_id="GHOST-SUFFIX", severity=WARN, code="suffixed-fr-citation",
            message=(
                f"{ident} is cited normatively at {len(locs)} line(s) across "
                f"{len(by_file)} file(s). A letter suffix is a transitional device: it forces "
                f"every id regex to accept two styles and leaves the namespace speaking two "
                f"languages at once. Fold it into its allocated slot rather than leaving a "
                f"ghost. Files: "
                + ", ".join(f"{name} x{n}" for name, n in sorted(by_file.items()))
            ),
            locations=locs,
            data={"fr": ident, "citation_count": len(locs),
                  "by_file": dict(sorted(by_file.items()))},
        )
    total = sum(len(v) for v in live.values())
    yield _ok(
        ctx, "GHOST-SUFFIX", "ghost-suffix-summary",
        f"{len(live)} letter-suffixed FR id(s) carry {total} live normative citation(s) across "
        f"{len({loc.rpartition(':')[0] for v in live.values() for loc in v})} file(s); "
        f"{exempted} citation(s) sit on a deprecation-marked line and {fenced} inside a fenced "
        f"block, so read as quotation rather than as a live claim",
        suffixed_frs=sorted(live), citations=total, exempted=exempted, fenced=fenced,
        per_id={ident: len(set(v)) for ident, v in sorted(live.items())},
    )


# ------------------------------------------------------------------------------------------
# Runner
# ------------------------------------------------------------------------------------------

CHECK_FNS: tuple[tuple[str, CheckFn], ...] = (
    ("RI-00-INPUT", check_input),
    ("RI-01-FR-DEF", check_fr_definitions),
    ("RI-01b-FR-SHAPE", check_fr_shape),
    ("RI-02-TASK-REF", check_task_refs),
    ("RI-03-FR-ORPHAN", check_fr_orphans),
    ("RI-03b-FR-UNCITED", check_fr_uncited_anywhere),
    ("RI-03c-FR-COLUMN", check_checklist_fr_column),
    ("RI-04-TASK-FR", check_task_cites_fr),
    ("RI-04b-ROW-TASK", check_rows_cite_tasks),
    ("RI-04c-ROW-FR", check_rows_cite_fr),
    ("RI-04d-FR-OWNER", check_fr_owners),
    ("RI-05-MISCITE", check_miscitations),
    ("RI-05b-INVERSE-CITE", check_inverse_citations),
    ("RI-06-TASK-ORDER", check_task_order),
    ("RI-06b-FR-ORDER", check_fr_order),
    ("RI-07-SC-COVER", check_sc_coverage),
    ("RI-07b-INV-COVER", check_inv_coverage),
    ("RI-07c-ID-SHAPE", check_id_shape),
    ("RI-08-SEC-CITE", check_section_citations),
    ("RI-08b-SEC-UNCITED", check_uncited_sections),
    ("RI-09-COUNT", check_count_claims),
    ("RI-10-FORBIDDEN", check_forbidden),
    ("RI-11-CONST", check_constitution),
    ("RI-11b-RESEARCH", check_research_refs),
    ("RI-12-STALE", check_stale_claims),
    ("TOMBSTONED-FR-REF", check_tombstoned_fr_refs),
    ("FR-NAMESPACE-COLLISION", check_fr_namespace_collisions),
    ("EPISTEMIC-AXIS-CONFLATION", check_epistemic_axis_conflation),
    ("COUNT-PRECISION", check_count_precision),
    ("GHOST-SUFFIX", check_ghost_suffix),
)

assert {cid for cid, _ in CHECK_FNS} == set(CHECK_BY_ID), "check registry mismatch"


def run_checks(ctx: Context, only: Sequence[str] = ()) -> tuple[list[Finding], list[str]]:
    wanted = set(only)
    findings: list[Finding] = []
    ran: list[str] = []
    for cid, fn in CHECK_FNS:
        if wanted and cid not in wanted:
            continue
        ran.append(cid)
        try:
            for item in fn(ctx):
                if item.check_id not in CHECK_BY_ID:
                    continue
                findings.append(item)
        except Exception as exc:  # a checker that crashes on bad input is useless
            findings.append(
                Finding(
                    check_id="RI-00-INPUT", severity=FAIL, code="check-crashed",
                    message=f"check {cid} raised {type(exc).__name__}: {exc}",
                    data={"check_id": cid, "exception": type(exc).__name__},
                )
            )
    findings.sort(key=lambda f: (SEVERITY_RANK[f.severity], f.check_id, f.code,
                                 tuple(f.locations)))
    return findings, ran


def summarize(findings: Sequence[Finding], ran: Sequence[str]) -> list[dict[str, Any]]:
    per: dict[str, Counter] = defaultdict(Counter)
    for f in findings:
        per[f.check_id][f.severity] += 1
        per[f.check_id]["total"] += 1
    rows = []
    for spec in CHECKS:
        if spec.check_id not in ran:
            continue
        c = per.get(spec.check_id, Counter())
        rows.append({
            "check_id": spec.check_id,
            "title": spec.title,
            "default_severity": spec.severity,
            "fail": c.get(FAIL, 0),
            "warn": c.get(WARN, 0),
            "info": c.get(INFO, 0),
            "total": c.get("total", 0),
            "clean": c.get("total", 0) == 0,
        })
    return rows


# ------------------------------------------------------------------------------------------
# Reporting
# ------------------------------------------------------------------------------------------

_RULE = "  | "


def _force_utf8_stdout() -> None:
    """Windows consoles default to a legacy codepage; never die on a box character."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass



def _wrap(text: str, width: int, indent: str, first: str | None = None) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    lead = first if first is not None else indent
    for w in words:
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= width:
            cur = f"{cur} {w}"
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    out = []
    for i, ln in enumerate(lines):
        out.append(f"{lead if i == 0 else indent}{ln}" if lead is not None else f"{indent}{ln}")
    return out or [indent]


def _fmt_data(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        if not value:
            return ""
        return ", ".join(str(v) for v in value)
    return str(value)


def render_text(
    ctx: Context,
    findings: Sequence[Finding],
    summary: Sequence[dict[str, Any]],
    *,
    show_ok: bool,
    max_detail: int,
    warn_only: bool,
) -> str:
    out: list[str] = []
    out.append("=" * 100)
    out.append(f"REFERENCE INTEGRITY CHECK  \u2014  {ctx.spec_dir}")
    out.append(f"tool v{TOOL_VERSION}   scanned: {', '.join(a.name for a in ctx.scanned)}")
    out.append(f"authority: {', '.join(a.name for a in ctx.authority)}   "
               f"constitution: {'found' if ctx.constitution else 'NOT FOUND'}")
    out.append("=" * 100)

    counts = Counter(f.severity for f in findings)
    out.append(
        f"verdict: {counts[FAIL]} FAIL, {counts[WARN]} WARN, {counts[INFO]} INFO"
        + ("   (--warn-only: exit 0)" if warn_only else "")
    )
    out.append("")

    by_check: dict[str, list[Finding]] = defaultdict(list)
    for f in findings:
        by_check[f.check_id].append(f)

    for row in summary:
        cid = row["check_id"]
        items = by_check.get(cid, [])
        if not items and not show_ok:
            out.append(f"[{cid}] {CHECK_BY_ID[cid].title}")
            out.append(f"{_RULE}rule: {CHECK_BY_ID[cid].rule}")
            out.append(f"{_RULE}default severity: {CHECK_BY_ID[cid].severity}   "
                       f"this run: FAIL=0 WARN=0 INFO=0  (ran, no findings)")
            out.append("")
            continue
        spec = CHECK_BY_ID[cid]
        out.append(f"[{cid}] {spec.title}")
        out.append(f"{_RULE}rule: {spec.rule}")
        out.append(f"{_RULE}default severity: {spec.severity}   "
                   f"this run: FAIL={row['fail']} WARN={row['warn']} INFO={row['info']}")
        items_sorted = sorted(items, key=lambda f: (SEVERITY_RANK[f.severity], f.code))
        for f in items_sorted:
            out.extend(_wrap(f"{f.severity:<4} {f.code}: {f.message}", 96, "  "))
            shown_locs = f.locations[:max_detail] if max_detail else f.locations
            for loc in shown_locs:
                out.append(f"        at {loc}")
            if max_detail and len(f.locations) > max_detail:
                out.append(f"        ... {len(f.locations) - max_detail} more location(s) "
                           f"suppressed by --max-detail")
            for key, value in f.data.items():
                if key in {"line_excerpt", "fr_clause", "line"}:
                    continue
                text = _fmt_data(value)
                if not text:
                    continue
                out.extend(_wrap(text, 92, "        ", first=f"        {key}: "))
        out.append("")

    out.append("-" * 100)
    out.append(f"{'check id':<20}{'FAIL':>7}{'WARN':>7}{'INFO':>7}{'total':>8}   default severity")
    tot = Counter()
    for row in summary:
        tot["fail"] += row["fail"]
        tot["warn"] += row["warn"]
        tot["info"] += row["info"]
        tot["total"] += row["total"]
        mark = ""
        if row["total"] == 0:
            mark = "   (ran, no findings)"
        elif row["fail"] == 0:
            mark = "   (no FAIL)"
        out.append(f"{row['check_id']:<20}{row['fail']:>7}{row['warn']:>7}{row['info']:>7}"
                   f"{row['total']:>8}   {row['default_severity']}{mark}")
    out.append(f"{'TOTAL':<20}{tot['fail']:>7}{tot['warn']:>7}{tot['info']:>7}{tot['total']:>8}")
    out.append("-" * 100)
    out.append(f"exit: {0 if (warn_only or tot['fail'] == 0) else 1}")
    return "\n".join(out)


def build_payload(
    ctx: Context,
    findings: Sequence[Finding],
    summary: Sequence[dict[str, Any]],
    *,
    warn_only: bool,
) -> dict[str, Any]:
    totals = Counter(f.severity for f in findings)
    return {
        "tool": "reference_check.py",
        "version": TOOL_VERSION,
        "spec_dir": str(ctx.spec_dir),
        "scanned": [a.name for a in ctx.scanned],
        "authority": [a.name for a in ctx.authority],
        "constitution_found": ctx.constitution is not None,
        "warn_only": warn_only,
        "totals": {s: totals.get(s, 0) for s in SEVERITIES},
        "exit_code": 0 if (warn_only or totals.get(FAIL, 0) == 0) else 1,
        "summary": list(summary),
        "findings": [f.to_dict() for f in findings],
    }


# ------------------------------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------------------------------


def _default_spec_dir() -> Path:
    env = None
    found = find_spec_dir()
    if found is None:
        raise SystemExit(
            "reference_check: could not locate the feature directory (a directory containing "
            "spec.md and input.md). Pass --spec-dir explicitly."
        )
    _ = env
    return found


def main(argv: Sequence[str] | None = None) -> int:
    _force_utf8_stdout()
    ap = argparse.ArgumentParser(
        prog="reference_check.py",
        description="Bidirectional reference-integrity gate for Speckit feature artefacts.",
    )
    ap.add_argument("--spec-dir", type=Path, default=None,
                    help="feature directory (default: auto-discover from this file)")
    ap.add_argument("--artefact", action="append", default=[], metavar="REL",
                    help="extra artefact to scan, relative to --spec-dir (repeatable)")
    ap.add_argument("--all-artefacts", action="store_true",
                    help=f"also scan the optional report(s): {', '.join(OPTIONAL_ARTEFACTS)}")
    ap.add_argument("--only", action="append", default=[], metavar="CHECK_ID",
                    help="run only these check ids (repeatable)")
    ap.add_argument("--json", dest="as_json", action="store_true", help="emit JSON")
    ap.add_argument("--format", choices=("text", "json"), default=None)
    ap.add_argument("--warn-only", action="store_true",
                    help="never exit non-zero; for a repair-in-progress pass")
    ap.add_argument("--show-ok", action="store_true",
                    help="also print findings that verified successfully (INFO)")
    ap.add_argument("--max-detail", type=int, default=0, metavar="N",
                    help="cap locations printed per finding (0 = unlimited, default)")
    ap.add_argument("--compare", type=Path, default=None, metavar="JSON",
                    help="compare per-check totals against a previous --json report")
    args = ap.parse_args(argv)

    unknown = [c for c in args.only if c not in CHECK_BY_ID]
    if unknown:
        ap.error(f"unknown check id(s): {unknown}; known: {sorted(CHECK_BY_ID)}")

    try:
        spec_dir = (args.spec_dir or _default_spec_dir()).resolve()
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if not spec_dir.is_dir():
        print(f"reference_check: not a directory: {spec_dir}", file=sys.stderr)
        return 2

    as_json = args.as_json or args.format == "json"
    try:
        ctx = build_context(spec_dir, args.artefact, args.all_artefacts)
    except Exception as exc:
        print(f"reference_check: could not build context: {exc}", file=sys.stderr)
        return 2

    findings, ran = run_checks(ctx, args.only)
    summary = summarize(findings, ran)
    payload = build_payload(ctx, findings, summary, warn_only=args.warn_only)

    if args.compare:
        payload["comparison"] = _compare(args.compare, summary)
        if not as_json:
            print(_render_comparison(payload["comparison"]))

    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=False, default=str))
    else:
        print(render_text(ctx, findings, summary, show_ok=args.show_ok,
                          max_detail=args.max_detail, warn_only=args.warn_only))
    return int(payload["exit_code"])


def _compare(path: Path, summary: Sequence[dict[str, Any]]) -> dict[str, Any]:
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"error": f"could not read baseline {path}: {exc}"}
    prev_rows = {r["check_id"]: r for r in previous.get("summary", [])}
    rows = []
    for row in summary:
        prev = prev_rows.get(row["check_id"], {})
        rows.append({
            "check_id": row["check_id"],
            "fail_now": row["fail"],
            "fail_before": prev.get("fail", 0),
            "fail_delta": row["fail"] - prev.get("fail", 0),
            "warn_now": row["warn"],
            "warn_before": prev.get("warn", 0),
            "info_now": row["info"],
            "info_before": prev.get("info", 0),
        })
    prev_totals = previous.get("totals", {})
    now_totals = {s: sum(r[f"{s.lower()}_now"] for r in rows) for s in SEVERITIES}
    return {
        "baseline": str(path),
        "rows": rows,
        "totals_before": prev_totals,
        "totals_now": now_totals,
    }


def _render_comparison(cmp: dict[str, Any]) -> str:
    if "error" in cmp:
        return f"comparison unavailable: {cmp['error']}"
    out = ["", "-" * 100, "PROGRESS vs BASELINE", "-" * 100,
           f"{'check id':<20}{'FAIL before':>13}{'FAIL now':>11}{'delta':>8}"]
    for r in cmp["rows"]:
        flag = ""
        if r["fail_delta"] < 0:
            flag = "  improved"
        elif r["fail_delta"] > 0:
            flag = "  REGRESSED"
        out.append(f"{r['check_id']:<20}{r['fail_before']:>13}{r['fail_now']:>11}"
                   f"{r['fail_delta']:>+8}{flag}")
    tb, tn = cmp["totals_before"], cmp["totals_now"]
    out.append(f"{'TOTAL FAIL':<20}{tb.get(FAIL, 0):>13}{tn.get(FAIL, 0):>11}"
               f"{tn.get(FAIL, 0) - tb.get(FAIL, 0):>+8}")
    out.append("-" * 100)
    return "\n".join(out)


if __name__ == "__main__":
    raise SystemExit(main())
