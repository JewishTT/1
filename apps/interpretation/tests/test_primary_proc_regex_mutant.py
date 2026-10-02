"""Proof that the tests in ``test_primary_proc.py`` would **fail** against a ``re.sub`` cleaner.

**Why this file exists.** ``re.sub("<.*?>", "", body)`` is nine characters long, it returns text, and
every casual check of it passes. A test suite that has never been run against the wrong
implementation is a suite that has not been shown to test anything: it may be asserting the
properties of ``html.parser`` while believing it is testing the platform's. So this file builds the
naive implementation, runs **the same properties** against both, and asserts that each one passes on
:class:`~parsers.primproc.PrimaryProcessor` and **fails** on :class:`RegexCleaner`.

Two design choices worth stating, because they decide whether the proof is fair:

*The mutant is given every advantage it could reasonably claim.* It unescapes entities. It collapses
whitespace. It strips a second time for tags the first pass left behind. It decodes UTF-8. It is
therefore **not** a strawman — it is the implementation a competent engineer writes in ten minutes —
and every property below still fails against it. A strawman would make this file worthless.

*Each property is a named callable, not a pytest assertion.* A property is run twice and its two
outcomes compared, so the file reports *which* properties the cheap implementation gets wrong rather
than stopping at the first failure. The properties are written once and used by both runs, which is
what makes this a proof about the properties rather than about two sets of assertions that happen to
look similar.

The one property the mutant **passes** is recorded too, in :meth:`TestRegexMutant.test_the_one_thing
_it_does_get_right`, because a proof that claimed everything fails would be as dishonest as one that
claimed nothing.
"""

from __future__ import annotations

import html
import re
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from parsers.primproc import PrimaryProcessor

HTML_STRIP = re.compile(r"<.*?>", re.DOTALL)
LEFTOVER_STRIP = re.compile(r"<[^>]*>", re.DOTALL)
SPACE_RUN = re.compile(r"[ \t]+")
BLANK_LINES = re.compile(r"\n{2,}")


class RegexCleaner:
    """The implementation the directive rules out, written as fairly as it can be written.

    A drop-in for the stage's public surface as far as a caller is concerned — ``process(bytes,
    content_type=)`` returning a thing with ``.text`` — so the properties below can be run against
    both without a shim that would quietly repair the mutant's failures.

    It is deliberately given: UTF-8 decoding, entity unescaping, whitespace collapsing, blank-line
    removal, and a **second** tag-stripping pass for tags the first pass left open. A ``re.sub``
    implementation that failed only because it forgot one of those would prove nothing about parsing.
    """

    def process(self, body: bytes, *, content_type: str | None = None) -> str:
        text = body.decode("utf-8", errors="replace")
        text = HTML_STRIP.sub("", text)
        text = LEFTOVER_STRIP.sub("", text)
        text = html.unescape(text)
        text = SPACE_RUN.sub(" ", text)
        text = BLANK_LINES.sub("\n", text)
        return text.strip()


CLEANER = RegexCleaner()
PROCESSOR = PrimaryProcessor()


# --------------------------------------------------------------------------- #
# The properties, written once and run twice
# --------------------------------------------------------------------------- #


def real_result(source: str, content_type: str = "text/html"):
    """The real stage's full result — the record, not just the text."""
    return PROCESSOR.process(source.encode("utf-8"), content_type=content_type)


def real(source: str, content_type: str = "text/html") -> str:
    """The real stage's text. The same shape as :func:`mutant`, so a property can use both."""
    return real_result(source, content_type).text


def mutant(source: str, content_type: str = "text/html") -> str:
    return CLEANER.process(source.encode("utf-8"), content_type=content_type)


def property_mathematical_text_survives(run: Callable) -> bool:
    """``a < b > c`` comes out with all nine characters."""
    return run("a < b > c") == "a < b > c"


def property_double_angle_bracket_survives(run: Callable) -> bool:
    """``&lt;&lt;SEE&gt;&gt;`` becomes ``<<SEE>>`` — the escaping is undone and nothing else is lost.

    **This one does not distinguish the two implementations**, and it is not in
    :data:`PROPERTIES` for that reason: the mutant calls :func:`html.unescape` too, so it gets this
    right. It lives in :meth:`TestRegexMutant.test_the_one_thing_it_does_get_right` instead, because a
    proof file that only listed the properties its strawman failed would be hiding the reason the
    strawman ships.
    """
    return run("<p>&lt;&lt;SEE&gt;&gt;</p>") == "<<SEE>>"


def property_non_breaking_space_collapses(run: Callable) -> bool:
    """``a&nbsp;&nbsp;b`` is ``a b`` — one space, not two and not two nbsp.

    The mutant unescapes too, so it produces two ``U+00A0`` and its ``[ \\t]+`` rule does not touch
    them. This is the property that catches a cleaner that handles entities but forgets that nbsp
    *is* whitespace — a bug that looks fine until a page is full of it and every downstream tokeniser
    sees two words where there was one.
    """
    return run("<p>a&nbsp;&nbsp;b</p>") == "a b"


def property_script_content_is_gone(run: Callable) -> bool:
    """``<script>evil()</script>`` leaves nothing — not the tags, not the code.

    The mutant's failure mode is the sharpest illustration of the whole file: its first pass removes
    ``<script>`` and ``</script>`` and leaves ``evil()``, which then reads as article text. A cleaner
    that does this is not noisier output — it is a **false statement** about what the page said, with
    no mark anywhere that anything was removed.
    """
    return run("<p>keep</p><script>evil()</script>") == "keep"


def property_style_element_content_is_gone(run: Callable) -> bool:
    return run("<p>keep</p><style>a{color:red}</style>") == "keep"


def property_greater_than_inside_an_attribute(run: Callable) -> bool:
    """``<a href=">">t</a>`` — the ``>`` inside a quoted value is not the end of the tag.

    A ``re.sub`` cannot know that. It stops at the first ``>``, so it removes ``<a href=">`` and
    leaves ``">t</a>`` behind: attribute soup in the output and a lost tag boundary.
    """
    return run('<a href=">">t</a>') == "t"


def property_greater_than_inside_a_style_value(run: Callable) -> bool:
    """``<div style="a>b">keep</div>`` — the same trap inside the very attribute being dropped.

    Separated from the previous property because it catches a different mistake: an implementation
    that drops ``style=`` correctly in the simple case and leaks CSS into the text in the real one.
    """
    return run('<div style="a>b">keep</div>') == "keep"


PROPERTIES: tuple[tuple[str, Callable[[Callable], bool]], ...] = (
    ("a < b > c survives verbatim", property_mathematical_text_survives),
    ("&nbsp; collapses with the rest of the whitespace", property_non_breaking_space_collapses),
    ("<script> content is removed", property_script_content_is_gone),
    ("<style> content is removed", property_style_element_content_is_gone),
    ("> inside an attribute value is not a tag boundary", property_greater_than_inside_an_attribute),
    ("> inside a style value is not a tag boundary", property_greater_than_inside_a_style_value),
)


def test_properties_are_declared_where_they_can_be_seen() -> None:
    """Every property this file proves is named, and every one is reachable.

    Six, not seven, and one property is deliberately excluded — see
    :func:`property_double_angle_bracket_survives`. The count is asserted so that adding a property
    here is a conscious act rather than an accident of editing.
    """
    assert len(PROPERTIES) == 6
    assert all(callable(prop) for _, prop in PROPERTIES)



class TestRegexMutant:
    @pytest.mark.parametrize(("label", "prop"), PROPERTIES, ids=[label for label, _ in PROPERTIES])
    def test_the_real_stage_passes(self, label, prop):
        assert prop(real) is True, f"the real stage failed: {label}"

    @pytest.mark.parametrize(("label", "prop"), PROPERTIES, ids=[label for label, _ in PROPERTIES])
    def test_the_regex_mutant_fails(self, label, prop):
        """The whole point, one property at a time.

        If a future change made the mutant pass a property, this test fails and says so — which is
        the correct direction for it to fail in. A property both implementations satisfy is a property
        that is not distinguishing anything, and it should be deleted rather than kept.
        """
        assert prop(mutant) is False, (
            f"the re.sub implementation now satisfies {label!r}, so that property no longer "
            "distinguishes parsing from pattern-matching. Either the property or the mutant changed; "
            "read this as a question, not as a pass"
        )

    def test_the_mutation_is_visible_on_the_script_case(self):
        """The concrete corruption, printed rather than asserted, because the assertion is dull.

        ``evil()`` surviving as body text is the single most persuasive argument for a parser over a
        regex, and it is worth a reader seeing the two outputs side by side.
        """
        source = "<p>keep</p><script>evil()</script>"
        assert real(source) == "keep"
        assert mutant(source) == "keepevil()"

    def test_the_mutation_is_visible_on_the_maths_case(self):
        """``a < b > c`` → ``a c``. The comparison operator and two operands are gone.

        Printed rather than merely asserted because the failure mode is worth seeing rather than
        believing: ``a c`` is not obviously wrong at a glance. It is two spaces collapsed into one,
        and the ``< b >`` that used to be a comparison has been read as a tag.
        """
        source = "a < b > c"
        assert real(source) == "a < b > c"
        assert mutant(source) == "a c"

    def test_json_containing_markup_shaped_text_is_mangled_by_the_mutant(self):
        """The strongest argument for the passthrough routes, and it is about JSON.

        A payload whose **data** happens to contain ``a < b > c`` is not markup. ``re.sub`` cannot
        tell, and it edits the evidence: the digit, the name and the comparison operator in a JSON
        field are all one character away from being silently deleted. This is why
        :attr:`~parsers.primproc.reasons.Route.JSON` exists at all.
        """
        payload = '{"expr": "a < b > c", "n": 5}'
        body = payload.encode("utf-8")
        assert PROCESSOR.process(body, content_type="application/json").verbatim_body == body
        assert CLEANER.process(body, content_type="application/json") != payload

    def test_the_mutant_has_no_ledger_so_the_accounting_properties_are_unavailable(self):
        """The properties the mutant cannot even express.

        ``PrimaryResult`` carries a ledger, an output-line mapping and a per-reason byte accounting.
        :class:`RegexCleaner` carries a string. So "every removal is attributable to exactly one
        reason code" and "the ledger rebuilds the source" are not properties the mutant *fails* — they
        are properties it cannot be asked for, which is a stronger statement than failing them.
        """
        result = real_result("<article><p>a</p></article><nav>n</nav><script>e</script>")
        assert result.removed_bytes_by_reason
        assert result.lines
        assert result.ledger

        cleaned = mutant("<article><p>a</p></article><nav>n</nav><script>e</script>")
        assert isinstance(cleaned, str)
        for attribute in ("removed_bytes_by_reason", "ledger", "lines", "input_bytes"):
            assert not hasattr(cleaned, attribute), (
                f"the mutant unexpectedly grew {attribute!r}; if a real implementation has it, this "
                "proof needs updating"
            )

    def test_the_one_thing_it_does_get_right(self):
        """The properties the naive implementation **satisfies**, recorded so this is not a polemic.

        Two, and both are the reason the naive version survives review and ships. On a payload that is
        already clean text with no markup, the two agree. And on ``&lt;lt;SEE&gt;gt;`` the naive
        version's ``html.unescape`` call gets it right too. Neither is evidence of correctness: the
        difference is invisible until the payload contains something a regular expression cannot tell
        apart from markup.
        """
        plain = "plain text with no markup at all"
        assert real(plain, "text/plain") == mutant(plain, "text/plain")
        assert property_double_angle_bracket_survives(real) is True
        assert property_double_angle_bracket_survives(mutant) is True

    def test_the_mutant_is_not_a_strawman(self):
        """Guard on the guard.

        If someone simplifies :class:`RegexCleaner` until it is obviously wrong — dropping the
        unescape, say — then the proofs above stop meaning anything, because they would be catching a
        bug rather than a design. This asserts the mutant really does implement the parts it can.
        """
        assert CLEANER.process(b"&amp;") == "&"
        assert CLEANER.process(b"a     b") == "a b"
        assert CLEANER.process(b"a\n\n\nb") == "a\nb"
        assert CLEANER.process(b"no tags here") == "no tags here"

    def test_reexecuting_the_same_bytes_gives_the_same_mutant_output_too(self):
        """Determinism is not what separates them, and saying so keeps the comparison honest.

        ``re.sub`` is deterministic. The difference between the two implementations is not
        reproducibility — it is that one of them is wrong about the document.
        """
        source = "<article><p>a</p></article><nav>n</nav>"
        assert mutant(source) == mutant(source)
        assert real_result(source).to_dict() == real_result(source).to_dict()
