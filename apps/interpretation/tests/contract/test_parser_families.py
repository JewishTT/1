"""Contract: a parser family is a response *shape*, not a vendor (spec 025 §33).

The catalogue declares 92 distinct ``parser:`` names and implemented two. This suite pins
the replacement: six families, chosen by the shape of the response rather than by whose API
produced it.

**Why shapes and not vendors.** Shodan's ``hostnames`` and OpenAlex's ``authorships`` are
the same problem — walk a list, read named fields. Keying on shape is what keeps 145
integrations from becoming 145 code paths that drift apart, and it is why adding a new
source is a YAML block rather than a Python module.

**Missing is not null.** A field the payload omitted and a field the payload reported as
``null`` are different facts: the first is usually a schema change, the second is an honest
empty. Collapsing them makes a broken path look like a quiet source.

**Wildcards collect; they do not pick.** ``results[*].ip`` returns every match. A path
pointing at ``[0]`` when the source returned three records silently drops two thirds of what
was fetched.

**Nothing is invented.** This layer resolves paths to values. It does not decide that an
IP-shaped string in a field declared ``country`` is really an IP — that judgement belongs
to the domain layer, and a parser that made it would be a parser with two vocabularies.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import ClassVar

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from parsers.families import (
    FAMILIES,
    LEGACY_FAMILIES,
    FieldSpec,
    family_of,
    parse_body,
    parse_source,
)
from parsers.paths import MISSING, collect_path, path_exists, resolve_path

pytestmark = pytest.mark.contract


# -- paths -------------------------------------------------------------------


class TestPaths:
    DOC: ClassVar[dict] = {
        "data": {"asns": [{"asn": 13335, "org": "Cloudflare"}, {"asn": 15169, "org": "Google"}]},
        "results": [{"ip": "1.1.1.1"}, {"ip": "8.8.8.8"}],
        "reported_null": None,
    }

    def test_a_nested_value_resolves(self) -> None:
        assert resolve_path(self.DOC, "data.asns[0].org") == "Cloudflare"

    def test_a_wildcard_collects_every_match(self) -> None:
        assert collect_path(self.DOC, "data.asns[*].org") == ["Cloudflare", "Google"]

    def test_a_wildcard_over_a_list_of_objects(self) -> None:
        assert collect_path(self.DOC, "results[*].ip") == ["1.1.1.1", "8.8.8.8"]

    def test_an_absent_path_is_missing_not_none(self) -> None:
        # The distinction the whole module exists for.
        assert resolve_path(self.DOC, "data.nope") is MISSING
        assert resolve_path(self.DOC, "reported_null") is None
        assert not path_exists(self.DOC, "data.nope")
        assert path_exists(self.DOC, "reported_null")

    def test_a_numeric_index_on_a_mapping_is_refused(self) -> None:
        # Silently indexing a dict by position is how a source's "first" record becomes
        # whatever happened to be first in the JSON.
        assert collect_path({"a": {"0": "zero", "1": "one"}}, "a[0]") == []

    def test_an_out_of_range_index_resolves_to_nothing(self) -> None:
        assert collect_path({"a": [1]}, "a[5]") == []

    def test_paths_never_transform_or_default(self) -> None:
        # A parser config that could compute could also lie. Read-only, or nothing.
        assert resolve_path(self.DOC, "data.asns[0].org.upper()") is MISSING
        assert resolve_path(self.DOC, "$$$.nope") is MISSING


# -- families ----------------------------------------------------------------


class TestFamilyResolution:
    def test_a_known_vendor_name_resolves_to_its_shape(self) -> None:
        assert family_of("shodan_internetdb") == "json_object"
        assert family_of("ipinfo") == "json_rows"
        assert family_of("sublist3r_lines") == "text_lines"
        assert family_of("whatweb_text") == "cali_text"

    def test_a_family_name_passes_through(self) -> None:
        assert all(family_of(name) == name for name in FAMILIES)

    def test_an_unclassified_name_defaults_to_the_most_likely_shape(self) -> None:
        # Not refused: the catalogue carries names nobody has classified, and reporting a
        # refusal for all of them would be noise. ``parse_failed`` still surfaces when the
        # guess is wrong, so the default cannot hide a mistake.
        assert family_of("something-nobody-classified") == "json_rows"

    def test_every_mapped_name_lands_on_a_real_family(self) -> None:
        assert set(LEGACY_FAMILIES.values()) <= set(FAMILIES)


class TestJsonRows:
    BODY = json.dumps({"results": [
        {"asn": 13335, "org": "Cloudflare", "country": "US"},
        {"asn": 15169, "org": "Google", "country": "US"},
    ]}).encode()

    FIELDS = (
        FieldSpec("asn", "asn", "asn"),
        FieldSpec("org", "org", "organization"),
        FieldSpec("country", "country", "country"),
    )

    def test_every_record_becomes_a_parsed_record(self) -> None:
        outcome = parse_body(self.BODY, parser="ipinfo", list_path="results", fields=self.FIELDS)
        assert outcome.status == "ok"
        assert outcome.record_count == 2

    def test_field_values_and_kinds_are_kept_separate(self) -> None:
        # A value is what the source said; the kind is what we call it. Keeping them apart is
        # what lets a later typing pass revise the kind without re-reading the source.
        outcome = parse_body(self.BODY, parser="ipinfo", list_path="results", fields=self.FIELDS)
        record = outcome.records[0]
        assert record.get("org") == "Cloudflare"
        assert record.kind_of("org") == "organization"

    def test_values_can_be_read_back_by_kind(self) -> None:
        outcome = parse_body(self.BODY, parser="ipinfo", list_path="results", fields=self.FIELDS)
        assert outcome.values_for("organization") == ("Cloudflare", "Google")

    def test_an_empty_list_is_empty_not_failed(self) -> None:
        # The source answered. Nothing matched is an answer, not a crash.
        outcome = parse_body(b'{"results": []}', parser="ipinfo", list_path="results",
                             fields=self.FIELDS)
        assert outcome.status == "empty"

    def test_a_missing_list_path_is_a_failure_with_a_reason(self) -> None:
        outcome = parse_body(self.BODY, parser="ipinfo", list_path="nope", fields=self.FIELDS)
        assert outcome.status == "parse_failed"
        assert "nope" in outcome.detail

    def test_a_single_object_where_a_list_was_expected_is_accepted(self) -> None:
        # The most common real shape change, handled rather than refused.
        body = json.dumps({"results": {"asn": 13335, "org": "Cloudflare"}}).encode()
        outcome = parse_body(body, parser="ipinfo", list_path="results", fields=self.FIELDS)
        assert outcome.status == "ok"
        assert outcome.record_count == 1

    def test_a_required_field_that_is_missing_is_unresolved(self) -> None:
        body = json.dumps({"results": [{"asn": 1}]}).encode()
        outcome = parse_body(
            body, parser="ipinfo", list_path="results",
            fields=(FieldSpec("asn", "asn", "asn"), FieldSpec("org", "org", "organization",
                                                              required=True)),
        )
        assert "org" in outcome.unresolved

    def test_an_optional_field_that_is_missing_is_not_an_error(self) -> None:
        body = json.dumps({"results": [{"asn": 1}]}).encode()
        outcome = parse_body(body, parser="ipinfo", list_path="results", fields=self.FIELDS)
        assert outcome.unresolved == ()

    def test_declaring_no_fields_is_empty_not_failed(self) -> None:
        # Blaming the endpoint for a definition's silence would be backwards.
        assert parse_body(self.BODY, parser="ipinfo").status == "empty"


class TestJsonObject:
    BODY = json.dumps({
        "hostnames": ["a.example.com"],
        "ip_str": "1.1.1.1",
        "org": "Cloudflare",
        "vulns": [{"id": "CVE-2021-1"}, {"id": "CVE-2021-2"}],
    }).encode()

    def test_top_level_fields_read_directly(self) -> None:
        outcome = parse_body(self.BODY, parser="shodan_internetdb", fields=(
            FieldSpec("ip", "ip_str", "ip"),
            FieldSpec("org", "org", "organization"),
        ))
        assert outcome.values_for("ip") == ("1.1.1.1",)

    def test_a_list_field_collapses_to_distinct_values(self) -> None:
        outcome = parse_body(self.BODY, parser="shodan_internetdb", fields=(
            FieldSpec("domain", "hostnames[*]", "domain", many=True),
            FieldSpec("cve", "vulns[*].id", "cve", many=True),
        ))
        assert outcome.values_for("cve") == ("CVE-2021-1", "CVE-2021-2")

    def test_a_field_declared_single_that_returns_many_is_reported(self) -> None:
        # Not silently collapsed: a shape change is an event, and taking the first element
        # would make a source that grew a list look like one that lost a value.
        outcome = parse_body(self.BODY, parser="shodan_internetdb", fields=(
            FieldSpec("cve", "vulns[*].id", "cve", many=False),
        ))
        assert "cve" in outcome.ambiguous

    def test_html_where_json_was_expected_is_parse_failed(self) -> None:
        outcome = parse_body(b"<html>error</html>", parser="shodan_internetdb",
                             fields=(FieldSpec("ip", "ip_str", "ip"),))
        assert outcome.status == "parse_failed"
        assert "not JSON" in outcome.detail

    def test_truncated_json_says_where(self) -> None:
        outcome = parse_body(b'{"ip": "1.1.1.1"', parser="x", fields=(FieldSpec("ip", "ip", "ip"),))
        assert outcome.status == "parse_failed"
        assert "line" in outcome.detail


class TestTextLines:
    BODY = b"# a comment\n1.1.1.1\n8.8.8.8\nnot-an-address\n"

    def test_only_lines_matching_a_pattern_become_records(self) -> None:
        outcome = parse_body(self.BODY, parser="text_lines", fields=(
            FieldSpec("ip", "", "ip", pattern=re.compile(r"^(\d+\.\d+\.\d+\.\d+)$")),
        ))
        assert outcome.values_for("ip") == ("1.1.1.1", "8.8.8.8")

    def test_comments_are_skipped(self) -> None:
        # Treating "# comment" as a hostname is worse than not parsing that line.
        outcome = parse_body(self.BODY, parser="text_lines", fields=(FieldSpec("any", "", "unknown"),))
        assert "#" not in outcome.records[0].get("any")

    def test_a_field_without_a_pattern_takes_the_whole_line(self) -> None:
        outcome = parse_body(b"example.com\n", parser="text_lines",
                             fields=(FieldSpec("domain", "", "domain"),))
        assert outcome.values_for("domain") == ("example.com",)

    def test_a_body_with_no_matching_line_is_empty(self) -> None:
        outcome = parse_body(b"nothing here\n", parser="text_lines", fields=(
            FieldSpec("ip", "", "ip", pattern=re.compile(r"^(\d+\.\d+\.\d+\.\d+)$")),
        ))
        assert outcome.status == "empty"


class TestHonestStatuses:
    def test_a_non_2xx_is_upstream_down(self) -> None:
        assert parse_source(object(), b"", status_code=503).status == "upstream_down"

    def test_a_definition_without_a_parse_block_is_empty_with_that_reason(self) -> None:
        # Not ``parse_failed``: nothing was declared, so the endpoint is not at fault.
        definition = type("D", (), {"parser": "shodan_internetdb", "definition": {}})()
        outcome = parse_source(definition, b'{"ip": "1.1.1.1"}')
        assert outcome.status == "empty"
        assert "no parse block" in outcome.detail

    def test_a_declaration_from_the_definition_is_used(self) -> None:
        definition = type("D", (), {
            "parser": "ipinfo",
            "definition": {"parse": {
                "family": "json_rows", "list_path": "results",
                "fields": {"asn": {"path": "asn", "kind": "asn"}},
            }},
        })()
        outcome = parse_source(definition, json.dumps(
            {"results": [{"asn": 13335}, {"asn": 15169}]}).encode())
        assert outcome.status == "ok"
        assert outcome.values_for("asn") == ("13335", "15169")

    def test_the_shorthand_field_form_carries_a_path(self) -> None:
        definition = type("D", (), {
            "parser": "x", "definition": {"parse": {"fields": {"org": "org"}}},
        })()
        outcome = parse_source(definition, b'{"org": "Cloudflare"}')
        assert outcome.record_count == 1
        assert outcome.kinds_seen() == {"unknown": 1}

    def test_a_sibling_kinds_block_types_the_fields(self) -> None:
        # Two short lines for the common case. The shorthand stays ``name: path`` because
        # ``org: organization`` alone is ambiguous, and resolving that guess silently is how
        # a source starts declaring types it does not have.
        definition = type("D", (), {
            "parser": "x",
            "definition": {"parse": {"fields": {"org": "org"}, "kinds": {"org": "organization"}}},
        })()
        outcome = parse_source(definition, b'{"org": "Cloudflare"}')
        assert outcome.kinds_seen() == {"organization": 1}

    def test_an_explicit_kind_beats_the_sibling_block(self) -> None:
        definition = type("D", (), {
            "parser": "x",
            "definition": {"parse": {
                "fields": {"org": {"path": "org", "kind": "isp"}},
                "kinds": {"org": "organization"},
            }},
        })()
        outcome = parse_source(definition, b'{"org": "Cloudflare"}')
        assert outcome.kinds_seen() == {"isp": 1}

    def test_an_unknown_kind_is_carried_not_dropped(self) -> None:
        # The opposite of the document adapter's rule, on purpose: there an unknown kind
        # means the extractor produced something unrecognisable and guessing would corrupt
        # a candidate; here it means the source declared a fact the platform has not learned
        # to name yet, and dropping it would lose evidence.
        outcome = parse_body(b'{"x": "1"}', parser="x", fields=(FieldSpec("a", "x", "asn-unknown"),))
        assert outcome.status == "ok"
        assert outcome.kinds_seen() == {"asn-unknown": 1}

    def test_an_outcome_serializes_its_honest_counts(self) -> None:
        outcome = parse_body(b'{"org": "CF"}', parser="x", fields=(FieldSpec("org", "org", "organization"),))
        payload = outcome.as_dict()
        assert payload["status"] == "ok"
        assert payload["records"] == 1
        assert payload["kinds"] == {"organization": 1}