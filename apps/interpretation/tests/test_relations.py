"""Relation extraction tests: predicates, provenance, determinism.

Every relation must be traceable to a document and a character span, must be
reproducible from the same input, and must never be asserted without evidence.
"""

from __future__ import annotations

import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from relations import (
    ATTRIBUTION_CONFIDENCE,
    ATTRIBUTION_PREDICATE,
    SUBJECT_DOCUMENT,
    DocumentContext,
    Relation,
    RelationExtractor,
    relation_id_for,
)

CTX = DocumentContext(
    document_id="WD-abc123",
    record_id="<urn:uuid:rec-1>",
    source_uri="https://acme.example/report",
    warc_date="2024-01-02T03:04:05Z",
    body_sha256="f" * 64,
)


def mentions(*specs: tuple[str, str, int]):
    """Build lightweight mention objects the extractor accepts."""
    from extractors.registry import Mention

    return [Mention(kind=k, value=v, offset=o) for k, v, o in specs]


def extract(text: str, *, window: int = 120, attribution: bool = True, ms=None):
    return RelationExtractor(window=window, include_attribution=attribution).extract(
        text, CTX, mentions=ms
    )


def only(relations: list[Relation], predicate: str) -> Relation:
    matches = [r for r in relations if r.predicate == predicate]
    assert len(matches) == 1, f"expected exactly one {predicate}, got {matches}"
    return matches[0]


class TestPredicateRelations:
    def test_exploits_binds_nearest_endpoint_pair(self):
        edge = only(extract("The host 10.0.0.5 exploits CVE-2021-44228 today."), "exploits")
        assert edge.subject_kind == "ipv4" and edge.subject_value == "10.0.0.5"
        assert edge.object_kind == "cve" and edge.object_value == "CVE-2021-44228"

    def test_reported_by_binds_contact(self):
        # A relation needs both endpoints: the reporter needs a subject mention.
        edge = only(
            extract("The host 1.2.3.4 was reported by abuse@acme.example."), "reported_by"
        )
        assert edge.subject_value == "1.2.3.4"
        assert edge.object_kind == "email"
        assert edge.object_value == "abuse@acme.example"

    def test_predicate_without_a_subject_yields_no_edge(self):
        assert not [
            r for r in extract("It was reported by abuse@acme.example.")
            if r.predicate == "reported_by"
        ]

    def test_operates_in_binds_two_infra_mentions(self):
        edge = only(extract("1.2.3.4 operates in evil.example"), "operates_in")
        assert (edge.subject_value, edge.object_value) == ("1.2.3.4", "evil.example")

    def test_longest_cue_wins_over_shorter_overlap(self):
        relations = extract("1.2.3.4 operates in evil.example")
        assert [r.predicate for r in relations if r.predicate != ATTRIBUTION_PREDICATE] == [
            "operates_in"
        ]

    def test_cue_is_case_insensitive(self):
        assert only(extract("HOST 1.2.3.4 EXPLOITS CVE-2021-44228"), "exploits")

    def test_cue_inside_a_url_does_not_fire(self):
        predicates = [
            r.predicate
            for r in extract("See http://uses.example/x and 1.2.3.4 now")
            if r.predicate != ATTRIBUTION_PREDICATE
        ]
        assert "uses" not in predicates

    def test_wrong_object_kind_yields_no_edge(self):
        # "exploits" requires a CVE object; an email must not satisfy it.
        assert not [
            r for r in extract("The actor 1.2.3.4 exploits nothing@acme.example")
            if r.predicate == "exploits"
        ]


class TestAttribution:
    def test_every_mention_binds_to_its_document(self):
        attributed = [
            r
            for r in extract("1.2.3.4 and 5.6.7.8 and x@y.example", attribution=True)
            if r.predicate == ATTRIBUTION_PREDICATE
        ]
        # The registry legitimately reports the domain nested inside the address
        # too, so assert containment rather than an exact set.
        assert {"1.2.3.4", "5.6.7.8", "x@y.example"} <= {r.object_value for r in attributed}
        assert all(r.subject_kind == SUBJECT_DOCUMENT for r in attributed)
        assert all(r.subject_value == CTX.document_id for r in attributed)

    def test_attribution_confidence_is_lower_than_predicate_confidence(self):
        found = extract("1.2.3.4 exploits CVE-2021-44228")
        assert only(found, "exploits").confidence > ATTRIBUTION_CONFIDENCE

    def test_attribution_can_be_disabled(self):
        found = extract("1.2.3.4 exploits CVE-2021-44228", attribution=False)
        assert {r.predicate for r in found} == {"exploits"}


class TestProvenance:
    def test_relation_carries_document_context(self):
        edge = only(extract("1.2.3.4 exploits CVE-2021-44228"), "exploits")
        assert edge.context == CTX
        assert edge.document_id == "WD-abc123"
        assert edge.context.body_sha256 == "f" * 64

    def test_relation_carries_exact_spans(self):
        text = "The host 10.0.0.5 exploits CVE-2021-44228 today."
        subject_span, object_span = only(extract(text), "exploits").spans
        assert text[subject_span.start : subject_span.end] == "10.0.0.5"
        assert text[object_span.start : object_span.end] == "CVE-2021-44228"
        assert subject_span.kind == "ipv4" and object_span.kind == "cve"

    def test_provenance_is_frozen(self):
        edge = only(extract("1.2.3.4 exploits CVE-2021-44228"), "exploits")
        with pytest.raises(FrozenInstanceError):
            edge.predicate = "tampered"  # type: ignore[misc]
        with pytest.raises(FrozenInstanceError):
            edge.context.document_id = "other"  # type: ignore[misc]

    def test_serialised_relation_carries_no_document_text(self):
        payload = only(extract("1.2.3.4 exploits CVE-2021-44228"), "exploits").to_dict()
        assert "text" not in payload
        assert payload["context"]["source_uri"] == "https://acme.example/report"
        assert len(payload["spans"]) == 2
        assert payload["relation_id"].startswith("REL-")


class TestDeterminism:
    def test_same_input_same_output(self):
        text = "1.2.3.4 exploits CVE-2021-44228 and was reported by x@y.example"
        assert [r.to_dict() for r in extract(text)] == [r.to_dict() for r in extract(text)]

    def test_relation_ids_are_content_derived(self):
        text = "1.2.3.4 exploits CVE-2021-44228"
        first = only(extract(text), "exploits").relation_id
        assert first == only(extract(text), "exploits").relation_id
        assert first.startswith("REL-")

    def test_different_document_yields_different_relation_id(self):
        text = "The host 1.2.3.4 exploits CVE-2021-44228"
        ms = mentions(("ipv4", "1.2.3.4", 10), ("cve", "CVE-2021-44228", 29))
        other = DocumentContext(document_id="WD-other")
        here = only(extract(text, ms=ms), "exploits").relation_id
        there = only(RelationExtractor().extract(text, other, mentions=ms), "exploits").relation_id
        assert here != there

    def test_output_is_sorted_by_position(self):
        starts = [r.spans[0].start for r in extract("a@b.example then 1.2.3.4 then 5.6.7.8")]
        assert starts == sorted(starts)

    def test_mention_order_does_not_change_output(self):
        text = "1.2.3.4 exploits CVE-2021-44228"
        ms = mentions(("ipv4", "1.2.3.4", 0), ("cve", "CVE-2021-44228", 19))
        forward = [r.to_dict() for r in extract(text, ms=ms)]
        backward = [r.to_dict() for r in extract(text, ms=list(reversed(ms)))]
        assert forward == backward

    def test_relation_id_for_is_stable_and_distinct(self):
        args = ("exploits", "ipv4", "1.2.3.4", "cve", "CVE-2021-44228", "WD-abc123")
        assert relation_id_for(*args) == relation_id_for(*args)
        assert relation_id_for(*args) != relation_id_for(*args[:-1], "WD-other")


class TestScoring:
    def test_confidence_stays_in_unit_interval(self):
        for text in (
            "1.2.3.4 exploits CVE-2021-44228",
            "1.2.3.4 " + "x" * 110 + " exploits CVE-2021-44228",
        ):
            for relation in extract(text):
                assert 0.0 < relation.confidence <= 1.0

    def test_tighter_cue_proximity_scores_higher(self):
        near = only(extract("1.2.3.4 exploits CVE-2021-44228"), "exploits").confidence
        far = only(
            extract("1.2.3.4 " + "x" * 100 + " exploits CVE-2021-44228"), "exploits"
        ).confidence
        assert near > far

    def test_exploits_outranks_a_weaker_predicate(self):
        strong = only(extract("1.2.3.4 exploits CVE-2021-44228"), "exploits").confidence
        weak = only(extract("1.2.3.4 uses evil.example"), "uses").confidence
        assert strong > weak

    def test_duplicate_mentions_merge_into_one_edge_with_all_spans(self):
        text = "1.2.3.4 exploits CVE-2021-44228. Later 1.2.3.4 exploits CVE-2021-44228."
        # Supplied explicitly: the registry dedups repeat values, so it would
        # only ever report the first occurrence of each endpoint.
        ms = mentions(
            ("ipv4", "1.2.3.4", 0),
            ("cve", "CVE-2021-44228", 17),
            ("ipv4", "1.2.3.4", 39),
            ("cve", "CVE-2021-44228", 56),
        )
        edges = [r for r in extract(text, ms=ms) if r.predicate == "exploits"]
        assert len(edges) == 1
        assert len(edges[0].spans) == 4  # two occurrences × two endpoints
        assert [s.start for s in edges[0].spans] == [0, 17, 39, 56]
