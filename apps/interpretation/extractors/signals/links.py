"""The link producer: what a hyperlink says, and nothing it does not.

Feature 019, T027 (FR-027, FR-094, SC-F).

A hyperlink is a relation, and the only relation it can honestly be called. ``<a
href="https://acme.example/about">About Acme</a>`` states that a document points at a
target and that a reader would call the two the same thing or a part of one another. It does
**not** state ``cites``, ``hosts``, ``employs``, ``owned_by`` or ``authored``. Those are
readings, and a producer that emitted one would be asserting a fact about the world from a
piece of markup.

**Why this producer is the one most likely to be abused, and how it is fenced.** It is the
cheapest possible signal to produce - every crawler emits one per link - so it is the
easiest way to make a graph look busy. The temptation is to resolve the target to an entity
and emit ``about``, which requires knowing that the target *is* the organisation rather than
a page describing one. So:

* :attr:`RelationSignal.relation_surface` is the **anchor text**, the document's own words.
  When the anchor is ``About Acme`` the surface carries ``Acme`` and a later regime can
  decide what that means. When the anchor is ``click here`` the surface is that, and the
  signal says so rather than reaching for the URL's last path segment.
* :attr:`RelationSignal.relation_ref` is **left ``None``**. A link genuinely names no
  operator in the platform's vocabulary - ``links_to`` is a document-structure fact, not a
  world relation - and setting one would be the fabrication. CD-6 makes that expressible;
  this producer is its first real user.
* :attr:`DirectionHypothesis` is ``UNDIRECTED``. A hyperlink is traversable both ways by a
  reader and points one way in the markup; the platform does not get to pick, and a
  ``links_to`` in the wrong direction is a confidently false claim.
* The neighbourhood counts the anchors in the *one element* being read, never the links in
  the document. A producer that scanned every ``<a>`` and ranked pairs would be reporting
  the site's link graph rather than what this document says about a target - a real and
  different thing.

**One anchor, one signal, one independence unit.** Before Phase 4B this producer emitted a
``LINK`` *and* a ``REFERENCE`` for every anchor, from the same two references and with the
same surface. They were two records of one observation, and FR-034 counts *independent
sources* - so a page with three anchors read as six sources, and the corroboration count
reported for that page was double the corroboration in it. The two kinds are not merged
because only one is emitted: a ``REFERENCE`` was for a named reference (a footnote, a
citation, a ``see also``), and an ``<a href>`` with anchor text is a traversable connection
first and a naming second. :attr:`SignalKind.REFERENCE` stays in the vocabulary for a
producer that reads an actual reference marker.

**The two ends, and the one that has no mention behind it.** The anchor's visible text is an
occurrence the document contains, and it is one participant. The ``href`` is the second: the
document's own pointer, addressed whole and at its own offsets, and recorded as what it is -
a **deferred pointer to a resource outside the document**, which is the "deferred raw slot"
:mod:`domain.relation_participant` describes. Phase 4B replaced ``href:<url>`` because a URL
was being handed over as though it were a mention of a thing in the world; the URL is still
here, untruncated, in the position and the role a pointer belongs, and the signal says in
:attr:`~extractors.signals.signal.RelationSignal.notes` that the second end is not a mention.
Before Phase 4B it was also the only occurrence of that string, so an anchor whose href
appeared twice on a page addressed one participant and corroborated itself.

**What it will not do.** It does not follow the link, so it cannot say the target exists,
and it does not compare the target against the corpus, so it cannot say the target is
anything at all. Both are separate producers' work, and both would be inferences.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from domain.predicate_signature import ArgumentSlot, Polarity
from domain.relation_participant import RelationParticipant
from domain.signal_basis import SignalBasis

from extractors.signals.mentions import deferred_occurrence
from extractors.signals.protocol import (
    ExtractionScope,
    ProducerDeclaration,
)
from extractors.signals.signal import (
    DirectionHypothesis,
    Neighbourhood,
    RelationSignal,
    SignalContractError,
    SignalKind,
)

PRODUCER_REF = "structural/hyperlink"
PRODUCER_VERSION = "2"
INDEPENDENCE_FAMILY = "markup"

#: One element's worth of anchors. The producer is scoped per element, so its ceiling is
#: small and it says so - a document with 4,000 links is 4,000 producer calls, not one
#: call that ranked 8,000,000 pairs.
MAX_PAIRS_CONSIDERED = 512

#: The two ends' labels, both of them the HTML element that declares the position. A label
#: from the markup rather than from the producer's own account of itself, which is what makes
#: it a fact a re-parse can confirm: before Phase 4B the ends were ``anchor:`` (a word this
#: module chose) and ``href:`` (a URL presented as a mention).
ANCHOR_LABEL = "a_text"
TARGET_LABEL = "a_href"


#: Anchor text that names nothing. When the anchor is one of these, the surface is the
#: text itself and no attempt is made to recover a name from the URL: ``click here`` means
#: the document chose not to say, and inferring ``/about/team`` is a guess dressed as a
#: reading.
UNINFORMATIVE_ANCHORS: frozenset[str] = frozenset(
    {
        "click here",
        "here",
        "read more",
        "more",
        "link",
        "this",
        "this page",
        "see more",
        "details",
        "download",
        "continue",
    }
)

#: One anchor, with the text group allowed to contain markup.
#:
#: The text group is ``(?:(?!</a\b).)*`` rather than ``[^<]*`` and the difference is
#: load-bearing. ``[^<]*`` stops at the first tag, so ``<a href="x">Acme <b>Inc</b></a>``
#: would not match *at all* - and the visible text of that anchor is "Acme Inc", not
#: "Acme". A pattern that silently skips the commonest kind of anchor in real markup is
#: worse than one that is merely narrow: it makes a producer look like it found nothing
#: where it found something. The tempered token consumes anything that is not this
#: anchor's own closing tag, so nesting works and the match still terminates at the right
#: place. :func:`anchor_text_of` then strips the tags.
_ANCHOR = re.compile(
    r"<a\b(?P<attrs>[^>]*)>(?P<text>(?:(?!</a\b).)*)</a\s*>", re.IGNORECASE | re.DOTALL
)
_HREF = re.compile(r"""\bhref\s*=\s*(?P<quote>["'])(?P<href>.*?)(?P=quote)""", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]+>")


def anchor_text_of(html: str) -> str:
    """An anchor's visible text, with markup stripped and whitespace collapsed.

    Strips tags rather than trusting the capture group, because ``<a href="x">Acme <b>Inc</b>
    </a>`` has visible text "Acme Inc" and a naive capture would read "Acme ". A surface
    with a stray space in it would not match the same anchor on a second parse, and the two
    spellings would become two signals for one link - which is exactly the double-counting
    FR-034 is counting against.
    """
    without_tags = _TAG.sub(" ", html)
    return " ".join(without_tags.split())


def href_of(attrs: str) -> str:
    """The ``href`` from an anchor's attribute string, or ``""`` if it has none.

    An anchor without an ``href`` is a placeholder, a button or a scripted control, and it
    is not a link to anything. Returning empty rather than falling back to the element's
    other attributes keeps ``<a name="anchor">`` - a *target* of a link, not a source of
    one - from being reported as a link outward.
    """
    found = href_span_of(attrs)
    return found[0] if found else ""


def href_span_of(attrs: str, base: int = 0) -> tuple[str, int, int] | None:
    """The ``href`` **and where its own text begins**, or ``None``.

    ``base`` is where ``attrs`` starts in the caller's own string, so the returned offsets
    index the document rather than the attribute run. The position is the whole point:
    ``href_span_of`` exists so the target end can be addressed as an *occurrence* at its own
    offset, and an address with no position cannot tell the same URL written twice on one
    page from one link written once. The old target was ``href:<url>`` with no position at
    all, so a navigation bar linking to the same page five times corroborated itself five
    times.
    """
    match = _HREF.search(attrs)
    if match is None:
        return None
    value = match.group("href")
    return value.strip(), base + match.start("href"), base + match.end("href")


def is_informative(surface: str) -> bool:
    """Whether the anchor's own words name something.

    False means the document declined to name it, and the signal keeps the uninformative
    text as its surface so a reader can see that rather than infer a name.
    """
    cleaned = " ".join(surface.split()).strip().lower()
    if not cleaned:
        return False
    return cleaned not in UNINFORMATIVE_ANCHORS


class HyperlinkExtractor:
    """Hyperlinks, as LINK signals, on the same contract as every other producer.

    Reads one element at a time. A caller with a whole document splits it and calls
    :meth:`extract` per element, which is what keeps the neighbourhood honest: the extent
    a signal claims is the extent that was read, and an element-scoped producer cannot
    honestly claim a document-scoped one.
    """

    def declares(self) -> ProducerDeclaration:
        return ProducerDeclaration(
            producer_ref=PRODUCER_REF,
            producer_version=PRODUCER_VERSION,
            kinds=(SignalKind.LINK,),
            reads=(
                "the <a href> elements of one element of markup. For each, the href and the "
                "anchor's visible text, and ONE signal: the traversable connection between "
                "the anchor's own words and the pointer in its href. A second signal per "
                "anchor used to be emitted as a REFERENCE, from the same two references and "
                "the same surface, and FR-034 counts independent sources - so a page with "
                "three anchors was read as six and reported twice the corroboration it had"
            ),
            cannot_read=(
                "whether the target exists, and what the target is. It does not follow "
                "the link, so it cannot say the page is there; it does not compare the "
                "target against anything, so it cannot say the target is a document about "
                "a company rather than the company. It also cannot tell an author's "
                "link to their own site from a link a document makes to a third party, "
                "which is the difference between authorship and citation. And it cannot "
                "say the target is mentioned: no mention of it exists in this document, so "
                "that end is a deferred pointer and the signal records that it is one"
            ),
            max_pairs_considered=MAX_PAIRS_CONSIDERED,
            independence_family=INDEPENDENCE_FAMILY,
            notes=(
                "relation_ref is always None. A hyperlink states a document structure, not "
                "a world relation, and naming an operator here would be the fabrication "
                "CD-6 exists to prevent - this producer is CD-6's first real user. Direction "
                "is UNDIRECTED for the same reason: a reader traverses a link either way "
                "and the markup points one way, and the platform does not get to pick. "
                "pairs_considered is 0 for the same reason it is 0 everywhere else: no "
                "mention pair was compared, and the anchor count in scope_read is the "
                "extent this producer really has"
            ),
        )

    def extract(
        self, record: object, *, scope: ExtractionScope
    ) -> tuple[RelationSignal, ...]:
        """Every anchor in ``record``'s markup, as one ``LINK`` signal each.

        ``record`` is the markup as a string, or a mapping carrying ``html`` (or
        ``markup``) plus the usual reference overrides. Anything else yields nothing, for
        the reason every producer here shares: one unparseable input should cost this
        producer its findings on that input, not the batch.
        """
        markup, overrides = _markup_of(record)
        if not markup.strip():
            return ()
        scanned = max(1, len(markup))
        found: list[RelationSignal] = []
        for ordinal, match in enumerate(_ANCHOR.finditer(markup)):
            span = href_span_of(match.group("attrs"), match.start("attrs"))
            if span is None:
                continue
            href, href_start, href_end = span
            href = href.strip()
            if not href or href.startswith("#"):
                continue
            surface = anchor_text_of(match.group("text"))
            if not surface:
                continue
            text_start, text_end = match.span("text")
            try:
                anchor_ref = deferred_occurrence(
                    label=ANCHOR_LABEL, surface=surface, start=text_start, end=text_end
                )
                target_ref = deferred_occurrence(
                    label=TARGET_LABEL, surface=href, start=href_start, end=href_end
                )
            except SignalContractError:
                # An anchor whose text or href will not address is a pair this producer
                # cannot state, and a one-ended signal would be a property of one thing.
                continue
            found.append(
                RelationSignal(
                    participants=(
                        RelationParticipant(
                            mention_ref=anchor_ref,
                            slot=ArgumentSlot(0),
                            role_hypothesis=ANCHOR_LABEL,
                            ordinal=0,
                            confidence=1.0,
                        ),
                        RelationParticipant(
                            mention_ref=target_ref,
                            slot=ArgumentSlot(1),
                            role_hypothesis=TARGET_LABEL,
                            ordinal=1,
                            confidence=1.0,
                            # The target is a pointer, not an occurrence of a thing in this
                            # document, and saying so is what stops a later layer reading
                            # this end as a mention it may resolve. FR-012's aspect split
                            # has no member for "resource"; `value` is the closest true
                            # answer available and is recorded as a hypothesis, not a fact.
                            argument_shape="value",
                        ),
                    ),
                    kind=SignalKind.LINK,
                    # The anchor's own words. When they name nothing - "click here" -
                    # that text *is* the surface, and no name is recovered from the
                    # URL: the document chose not to say, and guessing is worse than
                    # recording the silence.
                    relation_surface=surface,
                    # `hyperlink` and not `predicate_text`: the words between the ends are
                    # the anchor text, which describes the link rather than the relation,
                    # and a signal claiming to have read predicate words when the words are
                    # the anchor is a record that misstates its own evidence.
                    basis=SignalBasis.HYPERLINK,
                    # Stated, not defaulted: a hyperlink is markup and carries no
                    # proposition for anything to deny.
                    polarity=Polarity.ASSERTED,
                    neighbourhood=Neighbourhood(
                        characters_scanned=scanned,
                        # **Zero, and the zero is the point.** This used to be
                        # `max(1, scanned // 16)`, which counted nothing anybody could
                        # check: the 16 was a divisor with no unit, and a reader could not
                        # say what it divided. This producer compared no mention pairs at
                        # all - it read one element's anchors in document order - so the
                        # honest count is 0 and the extent it really has is the anchor
                        # count, which scope_read states (FR-093).
                        pairs_considered=0,
                        scope_read=(
                            "one element's anchors, in document order; no link graph "
                            "was walked and no target was fetched"
                        ),
                        precision="exact",
                        notes=(
                            "informative anchor"
                            if is_informative(surface)
                            else "anchor text names nothing; the surface records that"
                        ),
                    ),
                    relation_ref=None,
                    direction=DirectionHypothesis.UNDIRECTED,
                    producer_ref=PRODUCER_REF,
                    producer_version=PRODUCER_VERSION,
                    context_ref=overrides.get("context_ref") or scope.context_ref,
                    semantic_regime_ref=(
                        overrides.get("semantic_regime_ref") or scope.semantic_regime_ref
                    ),
                    capture_ref=overrides.get("document_ref") or scope.document_ref,
                    # 1.0 for the same reason the lexical producer uses 1.0: the
                    # markup says there is an anchor with this text and this href, and
                    # that is exact. What the target *is* is not read at all, and no
                    # number here could express it.
                    producer_confidence=1.0,
                    signal_ordinal=ordinal,
                    tenant_id=scope.tenant_id,
                    notes=(
                        "one anchor, one observation. The second end is the href as a "
                        "deferred pointer to a resource outside this document; no mention "
                        "of the target exists here and none was invented"
                    ),
                    extra={
                        "href": href,
                        "anchor_informative": is_informative(surface),
                        "target_scheme": href.split(":", 1)[0] if ":" in href else "",
                        "target_is_deferred_pointer": True,
                        "anchor_char_start": text_start,
                        "anchor_char_end": text_end,
                        "href_char_start": href_start,
                        "href_char_end": href_end,
                    },
                )
            )
        # A producer that read markup and found no anchors is a real answer, and an empty
        # tuple says so. A producer that exceeded its declared ceiling is caught by the
        # registry on the way out, not here - a producer is not the right place to police
        # itself.
        return tuple(found)


def _markup_of(record: object) -> tuple[str, Mapping[str, str]]:
    """The markup to read and any per-element reference overrides."""
    if isinstance(record, str):
        return record, {}
    if isinstance(record, Mapping):
        text = str(record.get("html") or record.get("markup") or record.get("text") or "")
        overrides = {
            key: str(record[key])
            for key in ("context_ref", "semantic_regime_ref", "document_ref")
            if record.get(key)
        }
        return text, overrides
    return "", {}


def link_signals(
    elements: list[object], *, scope: ExtractionScope
) -> tuple[RelationSignal, ...]:
    """Drive the link producer over a list of markup elements."""
    from extractors.signals.protocol import run_producer

    return run_producer(HyperlinkExtractor(), elements, scope=scope)


__all__ = [
    "ANCHOR_LABEL",
    "INDEPENDENCE_FAMILY",
    "MAX_PAIRS_CONSIDERED",
    "PRODUCER_REF",
    "PRODUCER_VERSION",
    "TARGET_LABEL",
    "UNINFORMATIVE_ANCHORS",
    "HyperlinkExtractor",
    "anchor_text_of",
    "href_of",
    "is_informative",
    "link_signals",
]
