"""Primary content processing: the stage's own claims, and whether it keeps them.

**The order these tests are in is the order they were written in**, and several of them fail
against the obvious cheaper implementation. That is the point of this file: a
``re.sub("<.*?>", "", body)`` cleaner is nine characters long, it produces text, and it silently
destroys the evidence it was built to clean. So every test here names the specific way the cheap
implementation is wrong, and
``test_primary_proc_regex_mutant.py`` runs a real ``re.sub`` implementation against the same
properties and asserts they **fail** — a guard that has never been observed to fail has not been
shown to guard anything.

The properties, in the order the directive names them:

* ``a < b > c`` and ``&lt;&lt;SEE&gt;&gt;`` survive (:class:`TestMathematicalTextSurvives`)
* ``<script>evil()</script>`` is gone, with its content (:class:`TestRemovedElements`)
* ``<div style="x" onclick="y">`` keeps its text and loses both attributes
  (:class:`TestAttributes`)
* JSON comes back byte-identical (:class:`TestPassthroughRoutes`)
* the offsets of surviving text are correct (:class:`TestOffsets`) — by **rebuilding the whole
  source out of the ledger** and comparing it to the body that went in
* truncated and malformed HTML yields usable text plus a recorded reason
  (:class:`TestMalformed`)
* every removal is attributable to exactly one reason code (:class:`TestLedger`)

And the stage-level guarantees: the decode rules and their refusals
(:class:`TestDecode`), the route table (:class:`TestRoutes`), the extraction strategies
(:class:`TestExtraction`), and determinism (:class:`TestDeterminism`).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from parsers.primproc import (
    ENTITY_SYNTAX_REASON,
    MIN_DENSITY_CHARS,
    NOTE_CODES,
    PRIMARY_PROC_SCHEMA,
    PRIMARY_PROC_VERSION,
    REMOVAL_REASONS,
    REPLACEMENT_REASONS,
    SKIP_TAGS,
    DecodeRefusal,
    DecodeRule,
    ExtractStrategy,
    NoteCode,
    PrimaryProcessor,
    RemovalReason,
    Route,
    SpanVerdict,
    TilingError,
    assert_tiling,
    parse_markup,
    scan_tag_attributes,
)
from parsers.primproc.reasons import DECODE_REFUSALS, DECODE_RULES, EXTRACT_STRATEGIES
from parsers.primproc.result import PrimProcContractError


def processor(**kwargs) -> PrimaryProcessor:
    return PrimaryProcessor(**kwargs)


def clean(source: str, content_type: str = "text/html", **kwargs):
    return processor(**kwargs).process(source.encode("utf-8"), content_type=content_type)


# --------------------------------------------------------------------------- #
# 1. The mathematical text the directive names
# --------------------------------------------------------------------------- #


class TestMathematicalTextSurvives:
    def test_less_than_between_words_survives_html_verbatim(self):
        """``a < b > c`` is text, and comes out of an HTML payload unchanged.

        The first event the tokenizer reports for this source is the data region ``a ``, the second
        is the data region ``<``, the third is `` b > c``. Three regions of *text* — because ``<``
        followed by a space is not a tag start, by HTML's own rules and therefore by any conforming
        parser's. ``re.sub("<.*?>", "", …)`` matches ``< b >`` as a tag and returns ``ac``, which is
        a sentence with the mathematics deleted and no mark that anything happened.
        """
        result = clean("a < b > c")
        assert result.text == "a < b > c"
        assert result.removed_bytes_total == 0

    def test_double_angle_bracket_round_trips_through_entities(self):
        """``&lt;&lt;SEE&gt;&gt;`` — the spelling a real page uses — becomes ``<<SEE>>`` exactly.

        Each ``&lt;`` is one entity construct with a four-character source span and a one-character
        expansion, so the four references are four ledger spans of the ``replaced`` verdict and the
        text they produce is ``<<SEE>>`` with no character invented and none lost.
        """
        result = clean("<p>&lt;&lt;SEE&gt;&gt;</p>")
        assert result.text == "<<SEE>>"
        assert result.unescaped is True
        assert result.entity_expansion_bytes == 4
        replaced = [span for span in result.ledger if span.verdict is SpanVerdict.REPLACED]
        assert len(replaced) == 4
        assert all(span.reason == ENTITY_SYNTAX_REASON for span in replaced)
        assert sum(span.source_chars for span in replaced) == 16

    def test_raw_double_bracket_is_markup_and_that_is_recorded_not_hidden(self):
        """``<<SEE>>`` in **raw** source is ``<SEE>`` — an unknown element — and no parser can save it.

        Pinned here so the choice is a fact rather than an accident. A conforming tokenizer reports a
        start tag named ``see``; the ``<`` before it and the ``>`` after it survive as text, and the
        five bytes of the tag itself are counted as :attr:`RemovalReason.ELEMENT_MARKUP`. The spelling
        that carries the text is the escaped one, which is why the previous test is the one that
        asserts survival, and why this test exists to say out loud that the raw form is not
        recoverable rather than letting a reader assume it is.
        """
        result = clean("<<SEE>>")
        assert result.text == "<>"
        assert result.removed_bytes_by_reason[str(RemovalReason.ELEMENT_MARKUP)] == 5
        assert NoteCode.HTML_UNCLOSED_ELEMENT in result.note_codes

    def test_double_angle_bracket_in_plain_text_is_byte_identical(self):
        """On the plain-text route nothing is parsed, so ``<<SEE>>`` is returned untouched."""
        source = "x << y >> z &amp; more"
        result = clean(source, content_type="text/plain")
        assert result.text == source
        assert result.verbatim_body == source.encode("utf-8")

    def test_bare_ampersand_survives(self):
        """``a & b`` is not an entity and is not mangled into one."""
        assert clean("<p>a & b</p>").text == "a & b"

    def test_unknown_entity_is_kept_verbatim_and_not_reported_as_unescaping(self):
        """``&frobnicate;`` round-trips, and the record does not claim an unescape happened.

        The tokenizer reports it as an entity reference, so the naive reading is "this stage
        unescaped something". Comparing the expansion to the source is what tells the two apart: an
        entity the table does not know expands to itself, and reporting that as a transformation
        would make "how many entities did you unescape" a number this stage inflates.
        """
        result = clean("<p>&frobnicate;</p>")
        assert result.text == "&frobnicate;"
        assert result.unescaped is False
        assert result.entity_expansion_bytes == 0
        assert not [span for span in result.ledger if span.verdict is SpanVerdict.REPLACED]

    def test_html5_legacy_entity_prefix_matching_is_honoured_and_recorded(self):
        """``&notanentity;`` is ``¬anentity;`` — ``&not`` is a real entity under HTML5.

        Pinned because it is the case where "did you unescape" and "did you see an ``&``" come apart
        in the other direction: the tokenizer calls it an entity reference, ``html.unescape`` expands
        the longest matching prefix, and the stage reports what actually happened rather than what it
        guessed was happening. A stage that checked only for the presence of ``&`` would miss this.
        """
        result = clean("<p>&notanentity;</p>")
        assert result.text == "¬anentity;"
        assert result.unescaped is True
        assert result.entity_expansion_bytes > 0


# --------------------------------------------------------------------------- #
# 2. Removed elements, with their content
# --------------------------------------------------------------------------- #


class TestRemovedElements:
    def test_script_is_removed_with_its_content(self):
        result = clean("<p>keep</p><script>evil()</script>")
        assert result.text == "keep"
        assert "evil" not in result.text
        assert result.removed_bytes_by_reason[str(RemovalReason.SKIP_ELEMENT)] == len(
            "<script>evil()</script>"
        )

    @pytest.mark.parametrize("tag", sorted(SKIP_TAGS))
    def test_every_skip_tag_is_removed_whole(self, tag):
        """The pinned skip set is a claim about every member, not about ``<script>``."""
        source = f"<p>keep</p><{tag}>hidden</{tag}>"
        result = clean(source)
        assert result.text == "keep"
        assert "hidden" not in result.text

    def test_comment_is_removed_and_counted_separately_from_markup(self):
        """A comment gets its own code, so "the tags are gone" and "the comments are gone" stay
        two counts. Both are removals; conflating them would make a page with a 40 KB comment
        indistinguishable from a page with a 40 KB nested ``<div>``."""
        result = clean("<p>a</p><!-- secret --><p>b</p>")
        assert result.text == "a\nb"
        assert result.removed_bytes_by_reason[str(RemovalReason.HTML_COMMENT)] == len(
            "<!-- secret -->"
        )

    def test_doctype_is_a_declaration_not_a_comment(self):
        result = clean("<!DOCTYPE html><html><body><p>x</p></body></html>")
        assert result.text == "x"
        assert result.removed_bytes_by_reason[str(RemovalReason.MARKUP_DECLARATION)] == len(
            "<!DOCTYPE html>"
        )
        assert result.removed_bytes_by_reason[str(RemovalReason.HTML_COMMENT)] == 0

    def test_nested_skip_element_does_not_leak_its_tail(self):
        """``<svg><script>x</script></svg>`` is removed whole, not up to the first end tag.

        A depth counter rather than a boolean, which is the difference between removing a region and
        removing a substring — and the donors' ``_skip_depth`` pattern is why this works.
        """
        result = clean("<div><svg><script>a</script>still hidden</svg><p>out</p></div>")
        assert result.text == "out"
        assert "hidden" not in result.text

    def test_a_skip_element_containing_another_element_closes_at_its_own_end_tag(self):
        """``<head><title>t</title></head>`` — one region, and every byte of it is the region's.

        The regression this pins is a real one that shipped in the first version of this stage: the
        depth counter was decremented on **every** end tag while it was positive, so ``</title>``
        popped the depth that ``<head>`` had opened and ``</head>`` was then counted as ordinary
        element markup. The byte total was still correct — which is precisely why a summed count
        cannot be the only check, and why this test asserts the *reason* rather than the total.
        """
        source = "<html><head><title>t</title></head><body><p>body</p></body></html>"
        result = clean(source)
        head = "<head><title>t</title></head>"
        assert result.removed_bytes_by_reason[str(RemovalReason.SKIP_ELEMENT)] == len(head)
        assert result.text == "body"
        removed = [
            source[span.start_char : span.end_char]
            for span in result.ledger
            if span.verdict is SpanVerdict.REMOVED
            and span.reason == str(RemovalReason.SKIP_ELEMENT)
        ]
        assert "".join(removed) == head

    def test_link_text_is_kept_and_only_the_attribute_soup_is_dropped(self):
        """``<a href="…">read this</a>`` keeps the words and loses the URL.

        The directive is explicit — do not strip links' text — and it is the difference between
        evidence and a list of URLs.
        """
        result = clean('<p>see <a href="https://example.invalid/x">read this</a> now</p>')
        assert result.text == "see read this now"
        assert "example.invalid" not in result.text


# --------------------------------------------------------------------------- #
# 3. Attributes
# --------------------------------------------------------------------------- #


class TestAttributes:
    def test_style_and_handler_are_dropped_and_the_text_stays(self):
        source = '<div style="x" onclick="y">keep</div>'
        result = clean(source)
        assert result.text == "keep"
        assert result.removed_bytes_by_reason[str(RemovalReason.ATTRIBUTE)] == len(
            ' style="x"'
        ) + len(' onclick="y"')
        assert result.removed_bytes_by_reason[str(RemovalReason.ELEMENT_MARKUP)] == len("<div") + len(
            ">"
        ) + len("</div>")

    @pytest.mark.parametrize("name", ["style", "STYLE", "onclick", "ONCLICK", "onerror", "on"])
    def test_dropped_attribute_names_are_case_insensitive_and_prefixed(self, name):
        result = clean(f'<p class="k" {name}="v">text</p>')
        assert result.text == "text"
        assert result.removed_bytes_by_reason[str(RemovalReason.ATTRIBUTE)] > 0

    def test_kept_attribute_is_still_counted_as_markup_not_as_a_drop(self):
        """``class="k"`` is removed as **markup**, not as a dropped attribute.

        The distinction is small and the reason it is kept is not: "we dropped zero attributes" must
        not be reported on a tag that had attributes in it, or the attribute count stops measuring
        what it claims to measure.
        """
        result = clean('<p class="k" id="i">text</p>')
        assert result.removed_bytes_by_reason[str(RemovalReason.ATTRIBUTE)] == 0
        assert result.removed_bytes_by_reason[str(RemovalReason.ELEMENT_MARKUP)] > 0

    def test_empty_and_unquoted_attribute_values_are_located(self):
        """The scanner handles ``a=``, ``a=b`` and ``a='b'`` — the three shapes that break a
        ``attrs``-list-driven byte count, because the list carries values and not source spans."""
        for source in (
            '<p data-x="v">t</p>',
            "<p data-x=v>t</p>",
            "<p data-x>t</p>",
            "<p data-x=''>t</p>",
        ):
            result = clean(source)
            assert result.text == "t"
            assert result.removed_bytes_by_reason[str(RemovalReason.ELEMENT_MARKUP)] == len(
                source.encode("utf-8")
            ) - 1

    def test_greater_than_inside_an_attribute_value_is_not_a_tag_boundary(self):
        """``<a href=">">t</a>`` — a ``>`` inside a quoted value. A regex that stops at the first
        ``>`` would truncate the tag and leave the rest of the page as text."""
        result = clean('<a href=">">t</a>')
        assert result.text == "t"

    def test_the_scanner_is_total_over_the_shapes_real_pages_use(self):
        """Every character of the tag lands in the name region, an attribute, or the tail.

        Total over this corpus, which is the property that matters: a byte the scan does not claim is
        a byte the ledger cannot attribute to a reason. The third case is the one a live Wikipedia page
        supplied — a **space before the closing ``>``**, which belongs to the tail and which an earlier
        version of the scanner left unclaimed, so the whole tag silently fell back to being counted as
        one undifferentiated blob.
        """
        for raw, expected_names in (
            ("<div>", []),
            ('<div style="x">', ["style"]),
            ('<div  id="a"   class="b" >', ["id", "class"]),
            ("<br/>", []),
            ("<div a=1 b>", ["a", "b"]),
            ("<div a='1' b=\"2\" c>", ["a", "b", "c"]),
            ("<div data-x>", ["data-x"]),
            ("<input type=checkbox checked>", ["type", "checked"]),
        ):
            scanned = scan_tag_attributes(raw)
            assert scanned is not None, raw
            region_start, attributes = scanned
            assert tuple(sorted(a.name for a in attributes)) == tuple(sorted(expected_names)), raw
            covered = region_start
            for attribute in attributes:
                assert attribute.start == covered, f"{raw}: gap before {attribute.name}"
                covered = attribute.end
            assert 0 <= region_start <= len(raw)
            assert all(0 <= a.start < a.end <= len(raw) for a in attributes)

    def test_a_tag_whose_attributes_disagree_with_the_tokenizer_is_counted_whole(self):
        """The reachable branch: a tag where the two readers do not agree.

        ``<div ="x">`` has no attribute *name*, so this stage's scanner and :mod:`html.parser` read
        the tag differently. The disagreement is detected, the tag is counted as one blob of element
        markup, and a note says so — no byte is lost and no split is claimed that could not be
        justified.
        """
        result = clean('<div ="x">t</div>')
        assert NoteCode.HTML_ATTRIBUTE_SCAN_INCOMPLETE in result.note_codes
        assert result.text == "t"
        assert result.input_bytes == result.removed_bytes_total + result.source_bytes_kept
        assert result.removed_bytes_by_reason[str(RemovalReason.ELEMENT_MARKUP)] == len(
            '<div ="x">t</div>'
        ) - 1

    def test_the_attribute_scan_does_not_degrade_an_ordinary_page(self):
        """No scan-completeness note on shapes real pages are made of.

        The guard on the previous test: a fallback that fired on ordinary markup would make the note
        worthless as a signal, since a reader would learn to ignore it.
        """
        source = (
            '<!DOCTYPE html><html><head><title>t</title></head><body>'
            '<div id="a"   class="b"  title="Main menu" >'
            '<p style="color:red" onclick="go()">body text</p>'
            "<img src=x alt=y><br> text</div></body></html>"
        )
        result = clean(source)
        assert NoteCode.HTML_ATTRIBUTE_SCAN_INCOMPLETE not in result.note_codes
        assert result.removed_bytes_by_reason[str(RemovalReason.ATTRIBUTE)] == len(
            ' style="color:red"'
        ) + len(' onclick="go()"')


# --------------------------------------------------------------------------- #
# 4. Per-type routes, and the ones that change nothing
# --------------------------------------------------------------------------- #


class TestPassthroughRoutes:
    def test_json_is_returned_byte_identical(self):
        """Not re-serialised, not re-encoded, not whitespace-collapsed. **Byte-identical**.

        ``json.dumps(json.loads(body))`` would return a document that parses to the same value and
        differs from the source in key order, number formatting and spacing — which means the
        ``content_digest`` of a cleaned "JSON" artefact would not be the digest of anything the
        source sent.
        """
        body = b'{"z": 1e3, "a":  [1, 2], "s": "x  y", "u": "caf\\u00e9"}'
        result = processor().process(body, content_type="application/json")
        assert result.verbatim_body == body
        assert result.artifact_body() == body
        assert result.unchanged is True
        assert result.removed_bytes_total == 0
        assert result.input_bytes == result.output_bytes == len(body)

    def test_ndjson_is_returned_byte_identical(self):
        body = b'{"a":1}\n{"a":2}\n{"a":3}\n'
        result = processor().process(body, content_type="application/x-ndjson")
        assert result.verbatim_body == body
        assert result.route is Route.NDJSON

    def test_plain_text_is_returned_byte_identical(self):
        body = b"a < b > c\n\n   indented\ttab\r\n"
        result = processor().process(body, content_type="text/plain")
        assert result.verbatim_body == body

    def test_a_non_utf8_payload_is_not_re_encoded_on_a_passthrough_route(self):
        """windows-1251 JSON comes back as windows-1251 bytes.

        The bug this pins is the one where "unchanged" is implemented as "re-encode the decoded text
        as UTF-8": the bytes differ, the digest differs, and the result still reports
        ``input_bytes == output_bytes`` because both numbers were computed from the re-encoding.
        """
        body = '{"name": "Анна"}'.encode("windows-1251")
        result = processor().process(body, content_type="application/json; charset=windows-1251")
        assert result.decode.charset == "windows-1251"
        assert result.verbatim_body == body
        assert result.input_bytes == result.output_bytes == len(body)

    def test_an_unaddressed_media_type_is_named_rather_than_guessed(self):
        """An image the stage has no route for is passed through and **named**.

        Not refused and not read as text: this stage has no opinion about a PNG, and a route that
        exists precisely so "we did not touch this" is distinguishable from "we read this as text".
        """
        body = b"PNG-ish bytes that happen to be valid UTF-8"
        result = processor().process(body, content_type="image/png")
        assert result.route is Route.PASSTHROUGH
        assert result.verbatim_body == body

    def test_an_undecodable_unaddressed_payload_is_refused_not_guessed(self):
        """Bytes that are neither declared nor decodable stop at the decode, whatever the route.

        The refusal is a decode refusal rather than a route refusal, and that ordering is the point:
        a stage that picked a route first and then reported a routing problem would be reporting a
        problem it does not have.
        """
        body = b"\x89PNG\r\n\x1a\n\xff\xfe"
        result = processor().process(body, content_type="image/png")
        assert result.ok is False
        assert result.decode.refusal == str(DecodeRefusal.CHARSET_UNDECLARED)
        assert result.route is Route.PASSTHROUGH

    def test_unchanged_is_a_recorded_decision_with_a_version_on_it(self):
        """The route, the strategy, the schema and the version are all present on a passthrough.

        "This stage decided to change nothing" has to be a decision somebody can read back, not the
        absence of a record — otherwise "we did not clean it" and "we never saw it" are the same
        observation.
        """
        result = processor().process(b"{}", content_type="application/json")
        assert result.version == PRIMARY_PROC_VERSION
        assert result.schema == PRIMARY_PROC_SCHEMA
        assert result.route is Route.JSON
        assert result.strategy is ExtractStrategy.WHOLE_DOCUMENT
        assert result.to_dict()["unchanged"] is True


class TestRoutes:
    @pytest.mark.parametrize(
        ("content_type", "route"),
        [
            ("text/html", Route.HTML),
            ("text/html; charset=utf-8", Route.HTML),
            ("TEXT/HTML", Route.HTML),
            ("application/xhtml+xml", Route.HTML),
            ("application/xml", Route.XML),
            ("application/rss+xml", Route.XML),
            ("application/atom+xml", Route.XML),
            # ``application/xhtml+xml`` also ends in ``+xml``, and the HTML check runs first. The
            # charset parameter makes this a distinct case from the bare one above while pinning the
            # same ordering decision.
            ("application/xhtml+xml; charset=utf-8", Route.HTML),
            ("application/json", Route.JSON),
            ("application/ld+json", Route.JSON),
            ("application/x-ndjson", Route.NDJSON),
            ("text/plain", Route.TEXT),
            ("text/markdown", Route.TEXT),
            ("image/png", Route.PASSTHROUGH),
            (None, Route.TEXT),
        ],
    )
    def test_route_table(self, content_type, route):
        assert processor().route_for(content_type) is route

    def test_is_cleaning_route_answers_only_for_the_two_that_work(self):
        proc = processor()
        assert proc.is_cleaning_route("text/html") is True
        assert proc.is_cleaning_route("application/xml") is True
        assert proc.is_cleaning_route("application/json") is False
        assert proc.is_cleaning_route("image/png") is False

    def test_json_detection_is_delegated_to_the_existing_seam_not_reimplemented(self):
        """A payload that is JSON under a declared non-JSON type is **not** upgraded.

        :func:`parsers.payload.detect.detect_json_text` rule 2 exists precisely for this and this
        stage routes on the media type rather than on the first byte, so a source that returns JSON
        under ``text/plain`` is read as text and stays byte-identical — the declared-type-first
        behaviour, not a sniff.
        """
        body = b'{"looks": "like json"}'
        result = processor().process(body, content_type="text/plain")
        assert result.route is Route.TEXT
        assert result.verbatim_body == body


# --------------------------------------------------------------------------- #
# 5. Offsets — the reason a re.sub was never acceptable
# --------------------------------------------------------------------------- #


class TestOffsets:
    def test_the_ledger_rebuilds_the_original_source_byte_for_byte(self):
        """Every byte of the body is claimed by exactly one span, at the right offset.

        The strongest form of the claim, and the one that catches both failure modes at once: a span
        that is **mispositioned** (rebuilding gives the wrong bytes) and a byte that is **unclaimed**
        (rebuilding gives fewer bytes). ``rebuilt == body`` fails for either. A ``re.sub`` result
        cannot be tested this way at all, because it has no ledger to rebuild from.
        """
        source = (
            "<!DOCTYPE html><html><head><title>T</title><style>a{}</style></head>"
            "<body><nav>chrome</nav><article><p>caf\u00e9 &amp; cr\u00e8me</p>"
            '<div style="display:none" onclick="go()">deep</div></article>'
            "<!--c--><script>evil()</script></body></html>"
        )
        body = source.encode("utf-8")
        result = processor().process(body, content_type="text/html")
        rebuilt = b"".join(
            body[span.source_byte_start : span.source_byte_end] for span in result.ledger
        )
        assert rebuilt == body
        assert sum(span.source_bytes for span in result.ledger) == len(body)

    def test_the_ledger_tiles_the_decoded_source_with_no_gap_and_no_overlap(self):
        source = "<p>a<!--c-->b</p><script>x</script><p>c &amp; d</p>"
        result = clean(source)
        cursor = 0
        for span in result.ledger:
            assert span.start_char == cursor, f"gap or overlap at {span.start_char} != {cursor}"
            cursor = span.end_char
        assert cursor == len(source)

    def test_each_removed_span_names_exactly_one_reason_from_the_closed_vocabulary(self):
        source = (
            "<!DOCTYPE html><body><script>e()</script><p style='a'>t</p>"
            "<!--c--><nav>n</nav></body>"
        )
        result = clean(source)
        removed = [span for span in result.ledger if span.verdict is SpanVerdict.REMOVED]
        assert removed
        for span in removed:
            assert span.reason in {str(reason) for reason in REMOVAL_REASONS}
            assert span.reason != ""
        for span in result.ledger:
            if span.verdict is SpanVerdict.REPLACED:
                assert span.reason in REPLACEMENT_REASONS
            if span.verdict is SpanVerdict.KEPT:
                assert span.reason == ""

    def test_the_reason_vocabulary_is_closed_and_every_key_is_present(self):
        source = "<p style='a'>t</p><script>e</script><!--c-->"
        result = clean(source)
        assert set(result.removed_bytes_by_reason) == {str(reason) for reason in REMOVAL_REASONS}
        for reason in REMOVAL_REASONS:
            assert result.removed_bytes_by_reason[str(reason)] >= 0

    def test_input_bytes_equal_removed_plus_kept(self):
        """The headline reconciliation, and the one that makes "the stage ate content" checkable."""
        source = (
            "<html><head><title>t</title></head><body><article><p>a  b\n\nc</p></article>"
            "<nav>x</nav><script>e</script></body></html>"
        )
        for content_type in ("text/html", "application/xhtml+xml", "text/plain"):
            body = source.encode("utf-8")
            result = processor().process(body, content_type=content_type)
            assert result.input_bytes == result.removed_bytes_total + result.source_bytes_kept

    def test_ledger_output_characters_reconcile_with_the_output_lines(self):
        """The one documented asymmetry, asserted rather than left to the reader.

        Line breaks produced by a **block tag** are synthesised — the tag was removed as
        ``element_markup`` and the newline behind it belongs to nothing. So the ledger sums to
        ``len(text) - (len(lines) - 1)``, and this test is what makes that a checked statement.
        """
        result = clean("<div><p>one</p><p>two</p></div>")
        assert len(result.lines) == 2
        assert sum(span.output_chars for span in result.ledger) == len(result.text) - 1
        assert sum(span.output_chars for span in result.ledger) == sum(
            len(line.text) for line in result.lines
        )

    def test_each_output_line_names_the_raw_bytes_it_came_from(self):
        """The Raw\u2194line mapping: line N points at a byte range of the **original body**.

        ``evidence/rawPayload.ts``'s ``buildLineIndex`` numbers lines from 1 and resolves a locator to
        a line span; this is the other half of that pair — a line of cleaned text naming the raw bytes
        it was read from, so the two views are one object.
        """
        source = "<html><body><article><p>alpha</p><p>beta</p></article></body></html>"
        body = source.encode("utf-8")
        result = processor().process(body, content_type="text/html")
        assert [line.text for line in result.lines] == ["alpha", "beta"]
        assert [line.line_number for line in result.lines] == [1, 2]
        for line in result.lines:
            raw = body[line.source_byte_start : line.source_byte_end]
            assert line.text in raw.decode("utf-8")

    def test_a_line_number_can_be_looked_up_from_a_source_byte(self):
        source = "<article><p>alpha</p><p>beta</p></article>"
        body = source.encode("utf-8")
        result = processor().process(body, content_type="text/html")
        offset = body.index(b"beta")
        assert result.line_number_of_source_byte(offset) == 2
        assert result.line_number_of_source_byte(len(body)) is None

    def test_offsets_are_in_the_declared_codec_not_utf8(self):
        """A windows-1251 page's byte offsets are windows-1251 byte offsets.

        Computing them as though the body were UTF-8 puts every offset after the first non-ASCII
        character in the middle of a multi-byte sequence — not off by one, but pointing at a
        different character entirely.
        """
        source = "<html><body><article><p>\u0410\u043d\u043d\u0430</p></article></body></html>"
        body = source.encode("windows-1251")
        result = processor().process(body, content_type="text/html; charset=windows-1251")
        assert result.text == "\u0410\u043d\u043d\u0430"
        line = result.lines[0]
        assert body[line.source_byte_start : line.source_byte_end].decode("windows-1251") == "\u0410\u043d\u043d\u0430"

    def test_a_multi_byte_character_does_not_shift_the_offsets_after_it(self):
        source = "<p>\u4e2d\u6587 caf\u00e9 tail</p>"
        body = source.encode("utf-8")
        result = processor().process(body, content_type="text/html")
        assert result.text == "\u4e2d\u6587 caf\u00e9 tail"
        assert result.input_bytes == len(body)
        assert result.input_bytes == result.removed_bytes_total + result.source_bytes_kept


# --------------------------------------------------------------------------- #
# 6. Whitespace
# --------------------------------------------------------------------------- #


class TestWhitespace:
    def test_runs_of_spaces_collapse_to_one(self):
        result = clean("<p>a     b</p>")
        assert result.text == "a b"
        assert result.removed_bytes_by_reason[str(RemovalReason.WHITESPACE)] == 4

    def test_a_leading_run_is_dropped_entirely_and_still_counted(self):
        result = clean("<p>   a</p>")
        assert result.text == "a"
        assert result.removed_bytes_by_reason[str(RemovalReason.WHITESPACE)] == 3

    def test_blank_lines_between_blocks_are_dropped_and_counted(self):
        result = clean("<p>a</p>\n\n\n<p>b</p>")
        assert result.text == "a\nb"
        assert result.lines and all(line.text for line in result.lines)

    def test_nbsp_folds_to_a_space_and_the_swap_is_recorded(self):
        """``&nbsp;`` becomes ``U+0020`` and its source syntax is counted as replaced.

        The stated cost of this rule is that it destroys the difference between "may not split here"
        and "is one word"; the test pins the behaviour so the cost is a decision on record rather
        than something a reader discovers in the output.
        """
        result = clean("<p>a&nbsp;b</p>")
        assert result.text == "a b"
        assert result.entity_expansion_bytes == 1
        assert result.unescaped is True

    def test_two_adjacent_nbsp_collapse_rather_than_producing_two_spaces(self):
        result = clean("<p>a&nbsp;&nbsp;b</p>")
        assert result.text == "a b"

    def test_a_collapsed_run_keeps_the_byte_it_accounts_for(self):
        """The surviving space is a **kept** character at the last source position of the run.

        Not a synthesised one: synthesising it would put an output character in the output with no
        source character behind it, and the ledger would no longer be a partition with an exact byte
        count. This test asserts both halves.
        """
        result = clean("<p>a   b</p>")
        kept_spaces = [
            span
            for span in result.ledger
            if span.verdict is SpanVerdict.KEPT and span.text == " " and span.source_chars == 1
        ]
        assert len(kept_spaces) == 1
        assert kept_spaces[0].output_chars == 1

    def test_tabs_and_non_breaking_spaces_are_whitespace_too(self):
        result = clean("<p>a\t\t\u2009b</p>")
        assert result.text == "a b"


# --------------------------------------------------------------------------- #
# 7. Malformed and truncated input
# --------------------------------------------------------------------------- #


class TestMalformed:
    def test_truncated_markup_still_yields_text_and_records_a_reason(self):
        result = clean("<html><body><article><p>the text that arrived")
        assert "the text that arrived" in result.text
        assert NoteCode.HTML_UNCLOSED_ELEMENT in result.note_codes
        assert result.ok is True

    def test_a_stray_end_tag_is_recorded_and_does_not_eat_the_text(self):
        result = clean("</p>text")
        assert result.text == "text"
        assert NoteCode.HTML_UNMATCHED_END_TAG in result.note_codes

    def test_implied_end_tags_are_recorded(self):
        result = clean("<p>one<p>two")
        assert result.text == "one\ntwo"
        assert NoteCode.HTML_IMPLIED_END_TAG in result.note_codes

    def test_a_declared_angle_bracket_the_tokenizer_declined_is_recorded(self):
        """``a </ b`` — a ``<`` that opened nothing, followed by a ``/`` that cannot start text.

        ``html.parser`` hands a declined ``<`` back as a data run containing exactly ``<``, so this
        is the reachable signature: a ``<`` run immediately followed by a run starting with ``!``,
        ``/`` or ``?``, none of which is valid HTML outside a construct. The characters stay in the
        output — they are text as far as the evidence is concerned — and a note says the page wrote
        markup it never closed.
        """
        result = clean("a </ b")
        assert result.text == "a </ b"
        assert NoteCode.HTML_MARKUP_LEFT_AS_TEXT in result.note_codes

    def test_a_bare_less_than_in_prose_is_not_reported_as_malformation(self):
        """``a < b`` produces the same lone ``<`` run and must **not** be flagged.

        The guard on the previous test. A heuristic that flagged every lone ``<`` would fire on
        ordinary mathematical prose, which is precisely the corruption this stage exists to avoid.
        """
        result = clean("a < b")
        assert result.text == "a < b"
        assert NoteCode.HTML_MARKUP_LEFT_AS_TEXT not in result.note_codes

    def test_an_unterminated_comment_keeps_its_text_and_records_the_unclosed_element(self):
        """``<p>text<!--unterminated`` — the note that does fire is the honest one.

        The comment opener is *not* reported as un-tokenised markup: ``html.parser`` splits the ``<``
        off and the following run starts with ``!``, so both signals are present, and the unclosed
        element is the one that is genuinely actionable. The text is kept either way.
        """
        result = clean("<p>text<!--unterminated")
        assert "unterminated" in result.text
        assert NoteCode.HTML_UNCLOSED_ELEMENT in result.note_codes

    def test_a_bound_is_hit_and_recorded_rather_than_silently_truncating(self):
        source = "<article><p>" + ("word " * 500) + "</p></article>"
        result = processor(max_source_chars=64).process(
            source.encode("utf-8"), content_type="text/html"
        )
        assert NoteCode.SOURCE_BOUND_HIT in result.note_codes
        assert len(result.text) < len(source)

    def test_the_note_vocabulary_is_closed(self):
        for note in clean("<p>trunc").notes:
            assert note.code in {str(code) for code in NOTE_CODES}

    def test_every_malformed_case_still_reconciles(self):
        for source in (
            "<p>trunc",
            "<div",
            "</p>text",
            "<b><i>x</b></i>",
            "<p>a<",
            "<a href='>'>t</a>",
            "text<!--unterminated",
            "<!weird>",
            "",
            "   ",
            "<>",
        ):
            result = clean(source)
            assert result.ok is True
            assert result.input_bytes == result.removed_bytes_total + result.source_bytes_kept
            assert sum(span.output_chars for span in result.ledger) == sum(
                len(line.text) for line in result.lines
            )


# --------------------------------------------------------------------------- #
# 8. Decode: the rules, and the refusal that is the point
# --------------------------------------------------------------------------- #


class TestDecode:
    def test_declared_content_type_charset_wins(self):
        body = "<p>\u00e9</p>".encode("windows-1252")
        result = processor().process(body, content_type="text/html; charset=windows-1252")
        assert result.decode.rule is DecodeRule.CONTENT_TYPE_CHARSET
        assert result.decode.charset == "windows-1252"
        assert result.text == "\u00e9"

    def test_the_declared_header_is_kept_verbatim_beside_its_essence(self):
        """``Text/HTML; charset=\u2026`` and ``text/html`` are the same decision, different facts.

        Both are carried, because a reader checking the decision wants to see the header that was
        actually sent rather than a normalised form of it \u2014 the same contract
        :class:`parsers.payload.detect.Detection` keeps.
        """
        result = processor().process(
            b"<p>x</p>", content_type="Text/HTML;  charset=Windows-1252"
        )
        assert result.decode.declared == "Text/HTML;  charset=Windows-1252"
        assert result.decode.media_type == "text/html"
        assert result.decode.charset == "windows-1252"

    def test_meta_probe_runs_only_when_declared(self):
        body = b'<html><head><meta charset="windows-1251"></head><body><p>x</p></body></html>'
        without = processor(probe_meta_charset=False).process(body, content_type="text/html")
        assert without.decode.charset == "utf-8"
        with_probe = processor(probe_meta_charset=True).process(body, content_type="text/html")
        assert with_probe.decode.rule is DecodeRule.META_CHARSET
        assert with_probe.decode.charset == "windows-1251"
        assert with_probe.decode.probe_offset is not None

    def test_utf8_is_the_default_and_is_stated(self):
        result = processor().process(b"<p>x</p>", content_type="text/html")
        assert result.decode.rule is DecodeRule.UTF8_DEFAULT
        assert result.decode.charset == "utf-8"

    def test_ascii_is_not_guessed_at_it_is_a_subset_of_utf8(self):
        result = processor().process(b"<p>plain ascii</p>", content_type="text/html")
        assert result.ok is True
        assert result.decode.rule is DecodeRule.UTF8_DEFAULT

    def test_an_unknown_declared_charset_is_refused_and_not_worked_around(self):
        body = b"<p>x</p>"
        result = processor().process(body, content_type="text/html; charset=definitely-not-a-codec")
        assert result.ok is False
        assert result.decode.refusal == str(DecodeRefusal.CHARSET_UNKNOWN_IN_CONTENT_TYPE)
        assert result.text == ""

    def test_a_declared_charset_the_bytes_do_not_satisfy_is_refused(self):
        body = "<p>\u0410</p>".encode("utf-8")
        result = processor().process(body, content_type="text/html; charset=ascii")
        assert result.ok is False
        assert result.decode.refusal == str(DecodeRefusal.CHARSET_FAILED_IN_CONTENT_TYPE)

    def test_the_mojibake_refusal(self):
        """Undeclared and not UTF-8: **refused**, not guessed.

        This is the single most important test in the file. A charset detector would return an answer
        here, and the answer would be text that reads as text while every name, number and address
        in it is wrong. The refusal is recorded as a code and a reason on the result rather than
        raised, so a corpus run can count them.
        """
        body = "<p>\u0410\u043d\u043d\u0430</p>".encode("windows-1251")
        result = processor().process(body, content_type="text/html")
        assert result.ok is False
        assert result.decode.refusal == str(DecodeRefusal.CHARSET_UNDECLARED)
        assert result.text == ""
        assert result.output_bytes == 0
        assert "guess" in result.decode.refusal_detail

    def test_require_text_raises_with_the_code_rather_than_returning_empty(self):
        body = "<p>\u0410</p>".encode("windows-1251")
        result = processor().process(body, content_type="text/html")
        with pytest.raises(PrimProcContractError) as caught:
            result.require_text()
        assert caught.value.code == str(DecodeRefusal.CHARSET_UNDECLARED)

    def test_a_non_bytes_body_is_refused_rather_than_coerced(self):
        result = processor().process("not bytes", content_type="text/html")  # type: ignore[arg-type]
        assert result.ok is False
        assert result.decode.refusal == str(DecodeRefusal.BODY_NOT_BYTES)

    def test_the_decode_vocabularies_are_closed(self):
        assert len(DECODE_RULES) == 3
        assert len(DECODE_REFUSALS) == 6
        assert {str(rule) for rule in DECODE_RULES} == {
            "content_type_charset",
            "meta_charset",
            "utf8_default",
        }


# --------------------------------------------------------------------------- #
# 9. Extraction strategies
# --------------------------------------------------------------------------- #


class TestExtraction:
    def test_article_wins_and_is_recorded(self):
        result = clean(
            "<body><nav>chrome</nav><article><p>content</p></article><footer>more chrome</footer></body>"
        )
        assert result.strategy is ExtractStrategy.ARTICLE
        assert result.text == "content"
        assert result.removed_bytes_by_reason[str(RemovalReason.OUTSIDE_MAIN)] > 0

    def test_main_wins_when_there_is_no_article(self):
        result = clean("<body><nav>n</nav><main><p>content</p></main></body>")
        assert result.strategy is ExtractStrategy.MAIN
        assert result.text == "content"

    def test_role_main_wins_when_there_is_no_tag(self):
        result = clean('<body><div>n</div><div role="main"><p>content</p></div></body>')
        assert result.strategy is ExtractStrategy.ROLE_MAIN
        assert result.text == "content"

    def test_content_class_is_borrowed_from_the_donor_and_recorded_as_its_own_strategy(self):
        result = clean('<body><div id="sidebar">n</div><div class="entry-content">content</div></body>')
        assert result.strategy is ExtractStrategy.CONTENT_CLASS
        assert result.text == "content"

    def test_density_is_the_last_resort_and_says_so(self):
        result = clean("<body><div><p>a longer run of text here</p></div><div><p>tiny</p></div></body>")
        assert result.strategy is ExtractStrategy.DENSITY
        assert "a longer run of text here" in result.text

    def test_whole_document_is_the_weakest_answer_and_is_said_out_loud(self):
        """A payload with no elements at all gets ``WHOLE_DOCUMENT`` and nothing better.

        A single short ``<p>`` also gets it, because
        :data:`~parsers.primproc.reasons.MIN_DENSITY_CHARS` puts a twelve-character page under the
        density floor — and reporting ``DENSITY`` for the container around twelve characters would
        read as a measurement of the page's main content when nothing was measured.
        """
        assert clean("nothing here").strategy is ExtractStrategy.WHOLE_DOCUMENT
        short = clean("<p>nothing here</p>")
        assert short.strategy is ExtractStrategy.WHOLE_DOCUMENT
        assert short.text == "nothing here"
        assert MIN_DENSITY_CHARS > len("nothing here")

    def test_article_beats_main_which_beats_role_main(self):
        """The strategy order is the contract, so it is asserted as an order."""
        assert EXTRACT_STRATEGIES.index(ExtractStrategy.ARTICLE) < EXTRACT_STRATEGIES.index(
            ExtractStrategy.MAIN
        )
        assert EXTRACT_STRATEGIES.index(ExtractStrategy.MAIN) < EXTRACT_STRATEGIES.index(
            ExtractStrategy.ROLE_MAIN
        )
        assert EXTRACT_STRATEGIES.index(ExtractStrategy.ROLE_MAIN) < EXTRACT_STRATEGIES.index(
            ExtractStrategy.CONTENT_CLASS
        )
        assert EXTRACT_STRATEGIES.index(ExtractStrategy.CONTENT_CLASS) < EXTRACT_STRATEGIES.index(
            ExtractStrategy.DENSITY
        )
        both = clean(
            '<body><div role="main"><p>from role</p></div><main><p>from main</p></main>'
            "<article><p>from article</p></article></body>"
        )
        assert both.strategy is ExtractStrategy.ARTICLE
        assert both.text == "from article"

    def test_first_in_document_order_wins_within_a_strategy(self):
        result = clean(
            "<body><article><p>first</p></article><article><p>second</p></article></body>"
        )
        assert result.text == "first"

    def test_the_donor_chrome_heuristics_are_available_but_off_by_default(self):
        """The opt-in, and why it is off, are both asserted.

        ``<nav>`` and ``class="sidebar"`` are **kept** by default: dropping them is a semantic
        judgement about what a page means, and the directive did not authorise it. The heuristic is
        wired and reachable so the decision is reversible, and the default is pinned by a test so
        nobody changes it silently.
        """
        source = '<div class="sidebar">chrome</div><nav>also chrome</nav>'
        default = clean(source)
        assert default.text == "chrome\nalso chrome"
        opted_in = processor(opt_in_irrelevant_tags=True).process(
            source.encode("utf-8"), content_type="text/html"
        )
        assert opted_in.text == ""
        assert "nav" in processor(opt_in_irrelevant_tags=True).skip_tags


# --------------------------------------------------------------------------- #
# 10. XML
# --------------------------------------------------------------------------- #


class TestXml:
    def test_an_rss_document_yields_its_text(self):
        result = clean(
            "<rss><channel><title>Feed</title><item><title>Entry</title></item></channel></rss>",
            content_type="application/rss+xml",
        )
        assert result.route is Route.XML
        assert "Entry" in result.text
        assert "Feed" in result.text

    def test_comments_and_processing_instructions_are_removed(self):
        result = clean(
            '<?xml version="1.0"?><r><!--note--><t>text</t></r>',
            content_type="application/xml",
        )
        assert result.text == "text"
        assert result.removed_bytes_by_reason[str(RemovalReason.MARKUP_DECLARATION)] > 0
        assert result.removed_bytes_by_reason[str(RemovalReason.HTML_COMMENT)] == len("<!--note-->")

    def test_cdata_is_kept_as_text_and_recorded(self):
        result = clean(
            "<r><![CDATA[raw < text]]></r>", content_type="application/xml"
        )
        assert "raw < text" in result.text
        assert NoteCode.XML_CDATA_KEPT in result.note_codes


# --------------------------------------------------------------------------- #
# 11. Determinism, and the absence of a clock
# --------------------------------------------------------------------------- #


DETERMINISM_CORPUS: tuple[tuple[str, str], ...] = (
    ("<html><body><article><p>a &amp; b</p></article><nav>n</nav></body></html>", "text/html"),
    ("<p>plain</p>", "text/html"),
    ("{ \"a\": 1 }", "application/json"),
    ("line\nline", "text/plain"),
    ("<p>trunc", "text/html"),
    ("<rss><item><title>t</title></item></rss>", "application/rss+xml"),
    ("<p>caf\u00e9 \u4e2d\u6587</p>", "text/html"),
    ("<div style='a' onclick='b'>t</div>", "text/html"),
    ("", "text/html"),
    ("<p>a</p><!--c--><script>e</script>", "text/html"),
)


class TestDeterminism:
    def test_same_bytes_give_byte_identical_output(self):
        proc = processor(probe_meta_charset=True)
        for source, content_type in DETERMINISM_CORPUS:
            body = source.encode("utf-8")
            first = proc.process(body, content_type=content_type)
            second = proc.process(body, content_type=content_type)
            assert first.artifact_body() == second.artifact_body()
            assert first.to_dict() == second.to_dict()

    def test_the_determinism_digest_is_stable_across_a_second_processor_instance(self):
        """Two separately-constructed processors must agree, or the config is not the only input."""
        for source, content_type in DETERMINISM_CORPUS:
            body = source.encode("utf-8")
            assert (
                processor().process(body, content_type=content_type).to_dict()
                == processor().process(body, content_type=content_type).to_dict()
            )

    def test_a_different_configuration_is_a_different_named_thing(self):
        source = "<body><article><p>c</p></article><nav>n</nav></body>"
        assert processor().process(
            source.encode(), content_type="text/html"
        ).to_dict() != processor(opt_in_irrelevant_tags=True).process(
            source.encode(), content_type="text/html"
        ).to_dict()

    def test_there_is_no_clock_no_randomness_and_no_uuid_on_the_path(self):
        """Checked by reading the module's **AST**, not its text and not the reviewer's eye.

        ``time``, ``random``, ``uuid``, ``datetime`` and ``os.urandom`` on this path would make the
        stage's output depend on when it ran, which is the one thing an evidence artefact cannot
        afford. A text search is not good enough — the word ``time.`` appears in this package's prose
        — so the check parses the module and looks at what is actually imported and called.
        """
        import ast

        import parsers.primproc.decode as decode_module
        import parsers.primproc.markup as markup_module
        import parsers.primproc.processor as processor_module
        import parsers.primproc.reasons as reasons_module
        import parsers.primproc.result as result_module

        banned_modules = {"time", "random", "uuid", "secrets", "datetime", "calendar"}
        banned_calls = {"urandom", "monotonic", "now", "today", "time_ns"}
        for module in (
            decode_module,
            markup_module,
            processor_module,
            reasons_module,
            result_module,
        ):
            tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert alias.name.split(".")[0] not in banned_modules, (
                            f"{module.__name__} imports {alias.name}"
                        )
                elif isinstance(node, ast.ImportFrom) and node.module:
                    assert node.module.split(".")[0] not in banned_modules, (
                        f"{module.__name__} imports from {node.module}"
                    )
                elif isinstance(node, ast.Attribute):
                    assert node.attr not in banned_calls, (
                        f"{module.__name__} reads {node.attr} at line {node.lineno}"
                    )

    def test_no_set_or_dict_iteration_reaches_the_output(self):
        """Every reason key, rule and strategy is emitted in declared tuple order.

        ``removed_bytes_by_reason`` is rebuilt from :data:`REMOVAL_REASONS` on the way out, so a
        ``set`` somewhere in the pipeline cannot reorder a result's keys between processes — which is
        the only way set-iteration order leaks into a serialised artefact.
        """
        result = clean("<p style='a'>t</p><script>e</script>")
        keys = list(result.to_dict()["removed_bytes_by_reason"])
        assert keys == [str(reason) for reason in REMOVAL_REASONS]

    def test_the_tokenizer_tiling_check_is_enforced_on_every_parse(self):
        """The invariant the whole accounting rests on, checked on every call, not in a test.

        :func:`~parsers.primproc.markup.assert_tiling` raises when a character belongs to no
        construct. The test proves the guard is wired by feeding it a hand-built gap.
        """
        from parsers.primproc.markup import Construct

        gap = (Construct(kind="data", start_char=3, end_char=9, text="x"),)
        with pytest.raises(TilingError):
            assert_tiling(gap, 9)
        with pytest.raises(TilingError):
            assert_tiling((), 5)


# --------------------------------------------------------------------------- #
# 12. §3 — the boundary, and the serialisable record
# --------------------------------------------------------------------------- #


class TestBoundaryAndRecord:
    def test_no_field_can_hold_an_entity_a_claim_a_type_or_a_relation(self):
        """§3 enforced by shape: the record has no slot for a semantic judgement.

        Not a style preference. A cleaner that can carry a type is a cleaner whose output a consumer
        cannot audit against its input, and the absence is cheaper to assert than the discipline is
        to maintain. The check is on **exact key names** at every level of the record, because a
        substring test would trip over ``entity_expansion_bytes`` — which is a count of bytes, and
        which is the only reason the assertion is not the obvious one.
        """
        result = clean("<p>Acme Holdings Limited, London</p>")
        forbidden = {
            "entity",
            "entity_id",
            "entity_type",
            "claim",
            "claim_id",
            "relation",
            "relation_id",
            "mention",
            "mention_id",
            "resolution",
            "type",
            "confidence",
            "score",
            "salience",
        }
        record = result.to_dict()
        assert not forbidden & set(record)
        assert not forbidden & set(record["decode"])
        assert not forbidden & set(record["notes"][0] if record["notes"] else {})
        for line in record["lines"]:
            assert not forbidden & set(line)
        for span in record["ledger"]:
            assert not forbidden & set(span)

    def test_the_output_line_record_carries_exactly_the_four_offset_pairs_it_needs(self):
        """A published width, so a field added for convenience becomes a change to a number.

        The same mechanism :data:`parsers.payload.records.OBSERVED_FIELD_KEY_COUNT` uses for a
        record: two shapes of different width cannot be compared by accident, and a sixth field
        nobody updated the count for is then a visible diff rather than a silent one.
        """
        line = clean("<p>x</p>").lines[0]
        assert len(line.to_dict()) == 8
        assert set(line.to_dict()) == {
            "line_number",
            "text",
            "output_char_start",
            "output_char_end",
            "output_byte_start",
            "output_byte_end",
            "source_byte_start",
            "source_byte_end",
        }

    def test_the_record_is_json_serialisable_and_digestible(self):
        """``to_dict`` in declared field order — the form a determinism test hashes."""
        import hashlib

        result = clean("<article><p>caf\u00e9 &amp; cr\u00e8me</p></article><nav>n</nav>")
        payload = json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=False)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        again = json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=False)
        assert hashlib.sha256(again.encode("utf-8")).hexdigest() == digest

    def test_the_version_and_the_schema_are_both_carried(self):
        """§133 needs somewhere to put "raw through parser v1 versus v2"."""
        result = clean("<p>x</p>")
        assert result.version == "primproc-1"
        assert result.schema == "primary-content/v1"
        assert result.to_dict()["version"] == result.version
        assert result.to_dict()["schema"] == result.schema

    def test_the_processor_publishes_its_own_version_and_schema(self):
        proc = processor()
        assert proc.version == PRIMARY_PROC_VERSION
        assert proc.schema == PRIMARY_PROC_SCHEMA
        assert proc.skip_tags == tuple(sorted(SKIP_TAGS))


class TestParserFacade:
    def test_parse_markup_is_reachable_and_returns_a_document(self):
        document = parse_markup(
            "<html><body><article><p>x</p></article></body></html>",
            codec="utf-8",
            skip_tags=SKIP_TAGS,
        )
        assert document.index.char_length == len(
            "<html><body><article><p>x</p></article></body></html>"
        )
        assert [element.tag for element in document.elements][:3] == ["html", "body", "article"]
        assert document.elements[2].end_char > document.elements[2].start_char
