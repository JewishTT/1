"""What a source says is not automatically a fact about the subject we asked about.

Three ways a live sweep put a sentence into a dossier that the sources never supported,
all found by running the real 145-source catalogue against ``example.com``:

* **echo** -- an API that has no answer for the query returns the query in a result field.
  ``ipapi`` asked about a domain answers with ``ip: "example.com"``. Recording that yields a
  dossier claiming the domain *is* its own IP address.
* **shape** -- a source declares ``ip`` and answers with a hostname. The value is real and
  the declared type is wrong; the pair must not become a fact.
* **attribution** -- a search API answers with *things it found*. ``organization:
  "Wikipedia"`` there describes the hit, not the domain that was queried. Asserting it
  about the subject is a fabrication with a plausible-looking value in it.

Each is refused with the refusal recorded, never silently dropped, so a dossier can show
that a source answered something other than what it promised.
"""

from __future__ import annotations

from parsers.families import ParsedRecord, ParseOutcome
from parsers.to_entities import interpret_parse

QUERY = "example.com"


def outcome(values: dict[str, object], kinds: dict[str, str]) -> ParseOutcome:
    return ParseOutcome(status="ok", records=(ParsedRecord(values=values, kinds=kinds),))


def run(out: ParseOutcome, query: str = QUERY):
    return interpret_parse(out, source_name="t", tenant_id="t-test", query=query)


def test_a_source_echoing_the_query_is_not_a_finding() -> None:
    r = run(outcome({"ip": QUERY}, {"ip": "ip"}))

    assert r.entities == (), "the query returned as an answer must not become an entity"
    assert r.rejected_echoes, "a refusal that leaves no trace is indistinguishable from silence"
    assert any(QUERY in line for line in r.rejected_echoes)


def test_echo_matching_is_case_and_space_insensitive() -> None:
    r = run(outcome({"ip": "  Example.COM  "}, {"ip": "ip"}))

    assert r.entities == ()
    assert r.rejected_echoes


def test_a_value_whose_shape_contradicts_its_declared_type_is_refused() -> None:
    r = run(outcome({"ip": "not-an-address"}, {"ip": "ip"}))

    assert r.entities == (), "a hostname is not an IP address, however confidently declared"
    assert r.rejected_shapes


def test_a_hit_from_a_search_is_about_the_hit_not_the_subject() -> None:
    r = run(
        outcome(
            {"url": "https://en.wikipedia.org/wiki/Example.com", "organization": "Wikipedia"},
            {"url": "url", "organization": "organization"},
        )
    )

    assert r.entities == (), "the hit's organization must not be asserted about the subject"
    assert [e.canonical for e in r.about_result] == ["Wikipedia"]
    assert "organization" not in r.values
    assert "url" in r.result_values


def test_an_attribute_api_echoing_its_own_subject_keeps_the_fields() -> None:
    r = run(
        outcome(
            {"url": QUERY, "organization": "IANA"},
            {"url": "url", "organization": "organization"},
        )
    )

    assert [e.canonical for e in r.entities] == ["IANA"]
    assert r.about_result == ()


def test_a_registry_handle_does_not_reclassify_the_subject_as_a_result() -> None:
    # Verified against rdap.com: a domain object carries its own registry ``handle``, which
    # differs from the query. When handles counted as subject references, the registrant's
    # organization was filed as a found-thing and dropped from the subject.
    r = run(
        outcome(
            {"handle": "EXAMPLECOM", "organization": "Reserved"},
            {"handle": "handle", "organization": "organization"},
        )
    )

    assert "Reserved" in [e.canonical for e in r.entities]
    assert r.about_result == (), "a registry handle must not reclassify the subject"


def test_unverifiable_attribution_keeps_the_field_rather_than_discarding_it() -> None:
    # No query given, so the record cannot be shown to point elsewhere. Losing a fact is
    # visible in the dossier; a fabricated one is not, so ambiguity resolves toward the
    # subject and the value stays available.
    r = interpret_parse(
        outcome({"organization": "Somebody"}, {"organization": "organization"}),
        source_name="t",
        tenant_id="t-test",
    )

    assert [e.canonical for e in r.entities] == ["Somebody"]
    assert r.about_result == ()


def test_several_hits_stay_separate_and_all_survive() -> None:
    records = (
        ParsedRecord(values={"url": "https://a.example.org", "organization": "A"}, kinds={"url": "url", "organization": "organization"}),
        ParsedRecord(values={"url": "https://b.example.net", "organization": "B"}, kinds={"url": "url", "organization": "organization"}),
    )
    r = run(ParseOutcome(status="ok", records=records))

    assert sorted(e.canonical for e in r.about_result) == ["A", "B"]
    assert r.entities == ()


def test_kinds_the_ontology_cannot_name_are_carried_not_dropped() -> None:
    r = run(outcome({"mystery": "somenewthing"}, {"mystery": "mystery"}))

    assert r.unclassified == ("mystery",)
    assert len(r.entities) + len(r.about_result) == 1, "an unnamed kind is still an observation"


def test_an_empty_payload_yields_nothing_and_says_so() -> None:
    r = run(ParseOutcome(status="ok"))

    assert r.entities == () and r.about_result == ()
    assert r.record_count == 0
