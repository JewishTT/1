"""Regenerate the EXPECTED table. Prints the diff first; writes only on request.

Run with --write to actually rewrite the table. Without it, this only reports,
because a baseline that can be rewritten without a human reading the delta is not
a baseline, it is a mirror.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from collections.abc import Mapping
from pathlib import Path

from semantic_path import corpus as C

TARGET = Path("apps/control-plane/semantic_path/corpus_cases.py")
MARKER = "EXPECTED: Mapping[str, CaseExpectation] = MappingProxyType("


def render(value: object) -> str:
    """Repr for one expectation field, with any mapping as a literal.

    ``as_expectation`` hands back a ``mappingproxy``, which is neither a ``dict``
    nor importable under its own name in the generated module - so it is detected as
    a ``Mapping`` and written as a plain literal. The field's declared type stays
    ``Mapping``, so the literal satisfies it and the committed value is a real dict.
    """
    if isinstance(value, Mapping):
        return "{" + ", ".join(f"{k!r}: {render(v)}" for k, v in value.items()) + "}"
    if isinstance(value, tuple):
        inner = ", ".join(render(v) for v in value)
        return f"({inner},)" if len(value) == 1 else f"({inner})"
    return repr(value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    from semantic_path import corpus_cases as CC

    run = C.run_corpus()
    rows: list[str] = []
    moved = 0
    print("committed expectations vs this run")
    print("=" * 78)
    for case in sorted(run.cases, key=lambda c: c.spec.case_id):
        exp = case.trace.as_expectation()
        old = getattr(CC, "EXPECTED", {}).get(case.spec.case_id)
        if old is not None:
            diffs = [
                f.name
                for f in dataclasses.fields(CC.CaseExpectation)
                if getattr(old, f.name) != getattr(exp, f.name)
            ]
            if diffs:
                moved += len(diffs)
                print(f"  {case.spec.case_id:34} {', '.join(diffs)}")
        fields = [
            f"        {f.name}={render(getattr(exp, f.name))},"
            for f in dataclasses.fields(CC.CaseExpectation)
        ]
        rows.append(f"    {exp.case_id!r}: CaseExpectation(\n" + "\n".join(fields) + "\n    ),")
    print("=" * 78)
    print(f"cases: {len(rows)} | fields changed: {moved}")
    print("uncovered graded situations:", [s for s, ids in CC.graded_coverage() if not ids] or "none")

    if not args.write:
        print("\nnothing written; pass --write to regenerate the table")
        return 0

    src = TARGET.read_text(encoding="utf-8")
    head = src[: src.index(MARKER)] if MARKER in src else src
    block = (
        "#: What each case produced when it was recorded, compared on every run.\n"
        "#: Regenerate deliberately after an intentional change, never to make a red run\n"
        "#: green, and read the printed diff first: a moved field is a claim about what the\n"
        "#: change did.\n"
        + MARKER
        + "\n    {\n"
        + "\n".join(rows)
        + "\n    }\n)\n"
    )
    TARGET.write_text(head + block, encoding="utf-8")
    print(f"\nrewritten: {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
