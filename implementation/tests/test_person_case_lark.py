"""Executable tests for the checked-in Lark grammar artifact.

These tests validate grammar structure only. Full AST equivalence tests must run in the
repository after the deterministic transformer is wired to apps/science/context/query_ast.py.
"""
from pathlib import Path

import pytest
from lark import Lark, UnexpectedInput

GRAMMAR = Path(__file__).parents[1] / "person_case.lark"


@pytest.fixture(scope="module")
def parser() -> Lark:
    return Lark(GRAMMAR.read_text(encoding="utf-8"), parser="lalr", start="start", propagate_positions=True)


@pytest.mark.parametrize(
    "query",
    [
        "find person where role = researcher as_of 2026-10-20T00:00:00Z within registered_catalogue return subject, coverage",
        "show academic author where work_count >= 10 within available_sources return subject, supporting_evidence",
        "compare person between 2020-01-01 2026-10-20 within registered_catalogue return subject, contradictions",
        "find person where country in (lt, lv) within registered_catalogue return subject",
        "find \"Jane Example\" within public_official_records return subject, supporting_evidence",
        "trace researcher where publication_count != 0 within registered_chain_sources return subject, blind_spots",
    ],
)
def test_supported_queries_parse(parser: Lark, query: str) -> None:
    tree = parser.parse(query)
    assert tree.data == "start"
    assert tree.meta.start_pos == 0


@pytest.mark.parametrize(
    "query",
    [
        "delete person from registered_catalogue",
        "find person where role = researcher as_of yesterday",
        "find person where role = (researcher)",
        "find person between 2026-10-20 within registered_catalogue",
        "find person return",
    ],
)
def test_unsupported_or_malformed_queries_are_rejected(parser: Lark, query: str) -> None:
    with pytest.raises(UnexpectedInput):
        parser.parse(query)
