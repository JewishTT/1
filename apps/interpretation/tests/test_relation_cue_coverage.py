"""Coverage tests for the relation cue table.

The engine was always capable; the table had one row and two cue grammars, so a real
sentence about a senior person matched nothing. These pin the coverage that motivated
extending the role vocabulary, because "one cue" is indistinguishable from "no
capability" at the call site.

Two rules are asserted alongside the counts, and both are about not lying:

* a cue must not produce a reading whose object is not an organisation name. An
  IGNORECASE flag applied to the whole pattern let ``[A-Z]`` match lowercase and
  "owns 51 percent of the stake in Bank Rossiya" resolved to "the stake in Bank". A
  false assertion is worse than an absence, so the name group is case-scoped.
* a relation is only reported when both participants were actually mentioned. "Putin
  serves as chairman of the board of Gazprom" matches the cue but names only a surname,
  which the person extractor will not claim; that is a recall gap in the mention
  extractor and is asserted as absent rather than papered over with a guessed subject.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP.parents[1] / "apps" / "shared"))

from extractors.relations import (  # noqa: E402
    RELATION_CUES,
    extract_relational_mentions,
    extract_relational_readings,
)


def readings(text: str) -> list[tuple[str, str, str]]:
    return [
        (r.relation_ref.relation_type, r.subject.mention.value, r.object.mention.value)
        for r in extract_relational_readings(text, lang_hint="en")
    ]


@pytest.mark.parametrize(
    ("text", "subject", "obj"),
    [
        ("Igor Sechin is deputy chairman of Gazprom.", "Igor Sechin", "Gazprom"),
        ("Vladimir Putin is the President of Russia.", "Vladimir Putin", "Russia"),
        (
            "Yuri Kovalchuk owns 51 percent of the stake in Bank Rossiya.",
            "Yuri Kovalchuk",
            "Bank Rossiya",
        ),
        ("Tim Cook is chief executive officer of Apple Inc.", "Tim Cook", "Apple Inc"),
    ],
)
def test_ordinary_senior_role_sentences_yield_a_relation(
    text: str, subject: str, obj: str
) -> None:
    """The coverage that was missing. Capitalised titles, multi-word titles and
    ownership all read now; the role group must carry the whole title, not its last
    word."""
    got = readings(text)
    assert got, f"no relation read from {text!r}"
    assert (got[0][1], got[0][2]) == (subject, obj)


def test_title_is_the_whole_phrase_not_its_last_word() -> None:
    """"chief executive officer" must not resolve as role "officer"."""
    role = RELATION_CUES[0].pattern.search("Tim Cook is chief executive officer of Apple Inc.")
    assert role is not None
    assert "chief executive officer" in role.group("role").lower()


def test_ownership_object_is_the_organisation_not_the_phrase() -> None:
    """The regression from an unscoped IGNORECASE: the object came back as
    "the stake in Bank". A cue naming the wrong organisation is a false assertion."""
    got = readings("Yuri Kovalchuk owns 51 percent of the stake in Bank Rossiya.")
    assert got[0][2] == "Bank Rossiya"


def test_article_and_bridge_material_do_not_become_the_object() -> None:
    for text in (
        "Igor Sechin is deputy chairman of Gazprom.",
        "Vladimir Putin is the President of Russia.",
    ):
        obj = readings(text)[0][2]
        assert not obj.lower().startswith(("the ", "a ", "of ")), obj


def test_a_surname_only_subject_is_not_guessed() -> None:
    """The cue matches; the mention extractor will not claim a bare surname. Recorded as
    a known recall gap rather than papered over -- inventing "Putin" as a person from
    one word is exactly the name-derived-identity defect resolution.py refuses."""
    text = "Putin serves as chairman of the board of Gazprom."
    assert RELATION_CUES[0].pattern.search(text) is not None, "the cue should match"
    assert extract_relational_mentions(text, "en") == [], (
        "if this now yields a bare-surname mention, the recall gap closed and this "
        "test should be replaced by one asserting the relation"
    )
    assert readings(text) == []


def test_no_relation_is_invented_from_text_without_a_cue() -> None:
    assert readings("Gazprom reported quarterly revenue on Monday.") == []


def test_cue_table_is_the_extension_point() -> None:
    """Two cue grammars for one relation: the shape a new relation must take."""
    assert len(RELATION_CUES) >= 2
    assert {c.relation_ref.relation_type for c in RELATION_CUES} == {"works_for"}
    assert all(c.affordance.subject_mention_kind == "person" for c in RELATION_CUES)
    assert all(c.affordance.object_mention_kind == "org" for c in RELATION_CUES)