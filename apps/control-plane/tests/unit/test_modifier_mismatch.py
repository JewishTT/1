"""Entity/ID mismatch modifier (T094): badge matching, link dedupe, urgency."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from modifier import (
    EntityLink,
    badge_match,
    dedupe_entity_links,
    modify_urgency,
    normalize_value,
)


def test_normalize_fold_and_digits() -> None:
    assert normalize_value("email", "Alice@ABC.Com") == "alice@abc.com"
    assert normalize_value("phone", "+1 (212) 555-0100") == "2125550100"


def test_badge_match_agreement() -> None:
    result = badge_match({"email": "a@x.io"}, {"email": "A@X.io"})
    assert result["matched"] == {"email": "a@x.io"}
    assert not result["mismatched"]


def test_badge_match_conflict() -> None:
    result = badge_match({"email": "a@x.io"}, {"email": "b@x.io"})
    assert "email" in result["mismatched"]


def test_badge_match_new_badge_reason() -> None:
    result = badge_match({"handle": "@nova"}, {})
    assert "handle:new" in result["reasons"]


def test_dedupe_groups_shared_identifier() -> None:
    links = [
        EntityLink("s1", {"handle": "@nova", "email": "a@x.io"}),
        EntityLink("s2", {"handle": "@nova"}),
        EntityLink("s3", {"email": "other@x.io"}),
    ]
    groups = dedupe_entity_links(links)
    assert len(groups) == 2
    merged = {l.entity for l in groups[0]}
    assert merged == {"s1", "s2"}


def test_dedupe_fold_case_insensitive() -> None:
    links = [
        EntityLink("s1", {"email": "a@x.io"}),
        EntityLink("s2", {"email": "A@X.IO"}),
    ]
    groups = dedupe_entity_links(links)
    assert len(groups) == 1


def test_modify_urgency_unary() -> None:
    urgency = modify_urgency("ent-1", [EntityLink("s1", {"email": "a@x.io"})])
    assert urgency["disposition"] == "UNCHANGED"
    assert urgency["urgency"] == "LOW"


def test_modify_urgency_conflict() -> None:
    urgency = modify_urgency(
        "ent-1",
        [
            EntityLink("s1", {"email": "a@x.io"}),
            EntityLink("s2", {"email": "b@x.io"}),
        ],
    )
    assert urgency["urgency"] == "HIGH"
    assert urgency["disposition"] == "CONFLICT"
    assert "email" in urgency["conflict_badges"]


def test_modify_urgency_merge() -> None:
    urgency = modify_urgency(
        "ent-1",
        [
            EntityLink("s1", {"email": "a@x.io", "handle": "@nova"}),
            EntityLink("s2", {"email": "a@x.io"}),
        ],
    )
    assert urgency["urgency"] == "MEDIUM"
    assert urgency["disposition"] == "MODIFY"