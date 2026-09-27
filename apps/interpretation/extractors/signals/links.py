"""The link producer: what a hyperlink says, and nothing it does not.

Feature 019, T027 (FR-027, SC-F).

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

**What it will not do.** It does not follow the link, so it cannot say the target exists,
and it does not compare the target against the corpus, so it cannot say the target is
anything at all. Both are separate producers' work, and both would be inferences.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from extractors.signals.protocol import (
    ExtractionScope,
    ProducerDeclaration,
)
from extractors.signals.signal import (
    DirectionHypothesis,
    Neighbourhood,
    RelationSignal,
    SignalKind,
)

PRODUCER_REF = "structural/hyperlink"
PRODUCER_VERSION = "1"
INDEPENDENCE_FAMILY = "markup"

#: One element's worth of anchors. The producer is scoped per element, so its ceiling is
#: small and it says so - a document with 4,000 links is 4,000 producer calls, not one
#: call that ranked 8,000,000 pairs.
MAX_PAIRS_CONSIDERED = 512

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
    match = _HREF.search(attrs)
    return match.group("href").strip() if match else ""


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
            kinds=(SignalKind.LINK, SignalKind.REFERENCE),
            reads=(
                "the <a href> elements of one element of markup. For each, the href and the "
                "anchor's visible text. Two signals come from one anchor: a LINK for the "
                "traversable connection and a REFERENCE for the anchor's own naming of its "
                "target, because 'see the 2019 filing' is a reference whatever the href "
                "resolves to."
            ),
            cannot_read=(
                "whether the target exists, and what the target is. It does not follow "
                "the link, so it cannot say the page is there; it does not compare the "
                "target against anything, so it cannot say the target is a document about "
                "a company rather than the company. It also cannot tell an author's "
                "link to their own site from a link a document makes to a third party, "
                "which is the difference between authorship and citation."
            ),
            max_pairs_considered=MAX_PAIRS_CONSIDERED,
            independence_family=INDEPENDENCE_FAMILY,
            notes=(
                "relation_ref is always None. A hyperlink states a document structure, not "
                "a world relation, and naming an operator here would be the fabrication "
                "CD-6 exists to prevent - this producer is CD-6's first real user. Direction "
                "is UNDIRECTED for the same reason: a reader traverses a link either way "
                "and the markup points one way, and the platform does not get to pick."
            ),
        )

    def extract(
        self, record: object, *, scope: ExtractionScope
    ) -> tuple[RelationSignal, ...]:
        """Every anchor in ``record``'s markup, as LINK and REFERENCE signals.

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
            href = href_of(match.group("attrs"))
            if not href:
                continue
            surface = anchor_text_of(match.group("text"))
            if not surface:
                continue
            ends = _ends_for(href, surface)
            if ends is None:
                continue
            subject, target = ends
            for kind, relation_surface, note in (
                (SignalKind.LINK, surface, f"href {href}"),
                (SignalKind.REFERENCE, surface, f"named reference, href {href}"),
            ):
                found.append(
                    RelationSignal(
                        subject_mention_ref=subject,
                        object_mention_ref=target,
                        kind=kind,
                        # The anchor's own words. When they name nothing - "click here" -
                        # that text *is* the surface, and no name is recovered from the
                        # URL: the document chose not to say, and guessing is worse than
                        # recording the silence.
                        relation_surface=relation_surface,
                        neighbourhood=Neighbourhood(
                            characters_scanned=scanned,
                            pairs_considered=max(1, scanned // 16),
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
                        notes=note,
                        extra={
                            "href": href,
                            "anchor_informative": is_informative(surface),
                            "target_scheme": href.split(":", 1)[0] if ":" in href else "",
                        },
                    )
                )
        # A producer that read markup and found no anchors is a real answer, and an empty
        # tuple says so. A producer that exceeded its declared ceiling is caught by the
        # registry on the way out, not here - a producer is not the right place to police
        # itself.
        return tuple(found)


def _ends_for(href: str, surface: str) -> tuple[str, str] | None:
    """The two mention addresses one anchor connects, or ``None`` if it has none.

    Both ends are addressed as surfaces rather than as invented ids, for the same reason
    the lexical producer does it: this producer is below the mention layer, and minting
    mention ids here would put mention identity inside extraction. The *target* is
    addressed by its href, which is a thing the document states, and the *subject* by the
    anchor's own text.

    An in-page anchor (``#section``) is refused rather than reported: it points inside the
    same document, so it is a containment fact about one artefact rather than a connection
    between two, and reporting it as a link would put a document in a relation with itself.
    """
    href = href.strip()
    if not href or href.startswith("#"):
        return None
    cleaned = " ".join(surface.split()).lower()
    if not cleaned:
        return None
    subject = f"anchor:{cleaned}"
    target = f"href:{href}"
    return subject, target


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
    "INDEPENDENCE_FAMILY",
    "MAX_PAIRS_CONSIDERED",
    "PRODUCER_REF",
    "PRODUCER_VERSION",
    "UNINFORMATIVE_ANCHORS",
    "HyperlinkExtractor",
    "anchor_text_of",
    "href_of",
    "is_informative",
    "link_signals",
]
