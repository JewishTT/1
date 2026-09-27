"""The lexical producer: cue phrases in running text, as signals.

Feature 019, T025 (FR-023, FR-025).

This is the producer feature 018 already had, wearing the substrate's contract instead of
building its own. It reads :data:`extractors.relations.RELATION_CUES` and emits
:class:`~extractors.signals.signal.RelationSignal` values - one per cue site, carrying the
cue's own surface and the neighbourhood it was read in.

**What changes, and why it is not a wrapper.** The point is that
:data:`~extractors.relations.RELATION_CUES` stops being *the* extension point of the
platform. It was, because it was the only table a new relation could be added to: reading
a relation was adding a row, and everything else - a table header, a hyperlink, an author
line - was outside the vocabulary entirely. After this module, ``RELATION_CUES`` is the
lexical producer's private data, which is a much smaller claim than "this is how the
platform learns relations", and the other producers in
:mod:`extractors.signals` are peers rather than guests.

**The cue's affordance is kept, and it is the reason this producer is not trivial.** 018's
insight was that finding the cue first and reading the participants *through* it is what
makes ``Acme`` recoverable in ``"John Smith became CEO of Acme"`` without a legal-form
grammar. The lexical producer therefore reports the *cue's* operator, not a guess of its
own, and :attr:`~extractors.signals.signal.RelationSignal.relation_surface` is the cue
phrase the document actually contained - which is usually not the operator's name. Both
travel on every signal, so a reader can see what was said as well as what it was taken to
mean, and a later regime that reads the same surface differently is visible as a second
reading rather than a correction.

**Boundedness is the honest part.** A cue site is found by scanning a regex over the
document, so :attr:`~extractors.signals.signal.Neighbourhood.pairs_considered` is *not* a
pair count in the ``O(n²)`` sense - no mention pair is ever enumerated. It is the number of
candidate windows the scan evaluated, which is linear in the document, and the scope says
so in words: ``"the whole document, scanned once, cue windows only"``. A reader who
compares that against a producer that compared mention pairs can see immediately that this
one did not rank proximity - which is the distinction FR-041…FR-043 exist to preserve.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from extractors.relations import RELATION_CUES, CueSite, extract_cue_sites
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

#: The producer's identity, and the version that goes with it. Both are required by
#: :class:`~extractors.signals.protocol.ProducerDeclaration` because FR-034's independence
#: count is computed over *producers*, and a signal whose producer cannot be named cannot
#: be counted at all. Two versions of this producer are still one source, which is what
#: :attr:`ProducerDeclaration.independence_family` records.
PRODUCER_REF = "lexical/cue-phrase"
PRODUCER_VERSION = "1"
INDEPENDENCE_FAMILY = "prose"

#: How many candidate windows one document scan evaluates. A cue is found by a linear
#: regex sweep, so this is a real number the reader can check against the document length
#: rather than a token figure: a 10,000-character document yields at most 10,000 windows
#: (one per starting position) and in practice far fewer, because the pattern is anchored
#: on a role phrase.
MAX_PAIRS_CONSIDERED = 10_000


class LexicalCueExtractor:
    """Cue phrases in running text, read through one contract.

    Implements :class:`~extractors.signals.protocol.RelationSignalExtractor` structurally -
    it declares what it reads and returns signals. It resolves nothing, admits nothing and
    emits no claim, and the absence of those three capabilities is structural rather than a
    promise: it imports no :class:`~domain.relation_candidate.CandidateStatus` and no
    :class:`~domain.relation_claim.RelationClaim`, so it could not set one even by mistake.
    """

    def declares(self) -> ProducerDeclaration:
        return ProducerDeclaration(
            producer_ref=PRODUCER_REF,
            producer_version=PRODUCER_VERSION,
            kinds=(SignalKind.LEXICAL,),
            reads=(
                "cue phrases in running text: a role phrase immediately followed by a cue "
                "and its object, as in 'became CEO of Acme'. The cue is found first and "
                "both participants are read *through* it, which is what lets an object "
                "with no name-shape of its own be recovered."
            ),
            cannot_read=(
                "anything not written as adjacent words. It cannot read a table, a "
                "hyperlink, a document's metadata, or a relation whose two ends are in "
                "different sentences - and it cannot tell a job title from a place name, "
                "because both are noun phrases in the same position. A cue match with a "
                "low-affinity participant is reported with the operator it was read "
                "through rather than dropped, so the uncertainty is visible."
            ),
            max_pairs_considered=MAX_PAIRS_CONSIDERED,
            independence_family=INDEPENDENCE_FAMILY,
            notes=(
                f"{len(RELATION_CUES)} cue phrases, all read by one code path. This is the "
                "producer's private vocabulary, not the platform's: before feature 019 a "
                "table of cues was the only way to state a new relation, and a relation "
                "stated any other way was outside the vocabulary entirely. Two producers "
                "reading the same prose are one source for FR-034, and a cue site is found "
                "by a linear sweep, so no mention pair is ever enumerated - the "
                "neighbourhood's pair count counts windows."
            ),
        )

    def extract(
        self, record: object, *, scope: ExtractionScope
    ) -> tuple[RelationSignal, ...]:
        """Every cue site in ``record``, as signals.

        ``record`` is either a plain string - the common case, and what the orchestrator
        passes when it has text but no parsed document - or a mapping carrying ``text``
        plus optional ``context_ref`` / ``semantic_regime_ref`` overrides. Anything else
        yields no signals rather than raising: one unparseable input should cost this
        producer its findings on that input, not the batch.
        """
        text, overrides = _text_of(record)
        if not text.strip():
            return ()
        declared = self.declares()
        scanned = max(1, len(text))
        signals: list[RelationSignal] = []
        for ordinal, site in enumerate(extract_cue_sites(text)):
            signal = self._signal_for(
                site,
                text=text,
                scope=scope,
                ordinal=ordinal,
                characters_scanned=scanned,
                declared=declared,
                overrides=overrides,
            )
            if signal is not None:
                signals.append(signal)
        return tuple(signals)

    def _signal_for(
        self,
        site: CueSite,
        *,
        text: str,
        scope: ExtractionScope,
        ordinal: int,
        characters_scanned: int,
        declared: ProducerDeclaration,
        overrides: Mapping[str, str],
    ) -> RelationSignal | None:
        """One cue site as one signal, or ``None`` if the site names no usable mention.

        A cue match always has two surfaces by construction - :func:`extract_cue_sites`
        only reports a site when both its groups matched - so ``None`` here means the
        surfaces could not be *addressed* as mentions, which is a mention-layer concern and
        not this producer's to solve. Dropping the signal with no note would lose the fact
        that a cue was found, so the drop happens where a mention id is minted and nowhere
        else.
        """
        subject_ref = _mention_ref("role", site.role_surface)
        object_ref = _mention_ref("object", site.object_surface)
        if not subject_ref or not object_ref:
            return None
        cue = site.cue
        return RelationSignal(
            subject_mention_ref=subject_ref,
            object_mention_ref=object_ref,
            kind=SignalKind.LEXICAL,
            # The words the document used, not the operator's name. Both are on the
            # signal: the surface is the evidence, the ref is the reading of it, and a
            # later regime reading the same surface differently is then visible as a
            # second reading rather than as a correction to the first.
            relation_surface=site.trigger_surface.strip() or cue.affordance.role_phrase,
            neighbourhood=Neighbourhood(
                characters_scanned=characters_scanned,
                # Zero, and the zero is the point. `pairs_considered` means one thing
                # across every producer: how many mention pairs were *compared*. A cue scan
                # compares none - it looks for phrases at successive character positions and
                # reads participants through the one it matched. Reporting the window count
                # here instead (which an earlier version did) made the field mean two
                # different things depending on the producer, and made this producer exceed
                # its own declared ceiling on any document over 10,000 characters - a gate
                # that fires on ordinary input teaches people to ignore gates.
                # `characters_scanned` already records how much was read.
                pairs_considered=0,
                scope_read=(
                    f"the whole document, scanned once for cue windows; no mention pair was "
                    f"enumerated (cue {cue.cue_id} matched at char {site.role_start})"
                ),
                precision="exact",
                notes=(
                    "A cue match is evidence that the phrase occurred between two surfaces, "
                    "not that the relation holds. Participants are mentions and have "
                    "resolved nothing."
                ),
            ),
            relation_ref=cue.relation_ref,
            # A cue phrase orders its two ends: the role comes first, the object second.
            # Stated from the pattern's own group order rather than inferred from the
            # surface, because 'of' reverses the surface order of the two nouns while
            # leaving the grammatical roles alone.
            direction=DirectionHypothesis.SUBJECT_TO_OBJECT,
            context_ref=overrides.get("context_ref") or scope.context_ref,
            semantic_regime_ref=overrides.get("semantic_regime_ref") or scope.semantic_regime_ref,
            capture_ref=overrides.get("document_ref") or scope.document_ref,
            # No `trigger_span`, and that is the honest answer rather than a gap. A
            # SpanRef indexes *into a segment*, and this producer sits below the
            # segmentation layer, so it cannot cite one; a span minted with an invented
            # segment_ref would be a position resolving against nothing, which is worse
            # than no position. The character offsets travel in `extra` instead, so the
            # assembler can build the real SpanRef once it knows which segment the cue
            # fell in - and a cue dropped rather than deferred is a cue nobody can find
            # again, since the offsets are the only way back to it.
            trigger_span=None,
            producer_ref=PRODUCER_REF,
            producer_version=PRODUCER_VERSION,
            # The producer's confidence in *its reading of the phrase*, and deliberately
            # not in the relation holding - that number belongs to the assembler, which
            # has seen every producer rather than one.
            #
            # 1.0, and the value is worth explaining because it looks like overconfidence.
            # This producer's uncertainty is *not* uniform, and the two halves are recorded
            # in different places. That the phrase occurred between these two surfaces is
            # exact: a declared cue pattern either matched or it did not, so there is no
            # gradient to report. That the surfaces are the participants the cue implies is
            # genuinely uncertain - a job title and a place name are both noun phrases in
            # the same position - and that uncertainty lives in
            # :attr:`CueAffordance.subject_kinds` and ``object_kinds``, which the
            # assembler reads. Putting a number here would average a certainty against an
            # uncertainty and produce a figure that means nothing.
            producer_confidence=1.0,
            signal_ordinal=ordinal,
            tenant_id=scope.tenant_id,
            notes=f"cue {cue.cue_id}",
            extra={
                "cue_id": cue.cue_id,
                "arity_mode": str(cue.arity_mode),
                # The cue's position, kept because the signal carries no resolvable span.
                "trigger_char_start": site.role_start,
                "trigger_char_end": site.trigger_end,
                "role_surface": site.role_surface,
                "object_surface": site.object_surface,
                # The participant uncertainty, carried where the assembler reads it rather
                # than folded into `producer_confidence`.
                "affordance_subject_kinds": list(cue.affordance.subject_kinds),
                "affordance_object_kinds": list(cue.affordance.object_kinds),
            },
        )


def _text_of(record: object) -> tuple[str, Mapping[str, str]]:
    """The text to scan and any per-record reference overrides.

    A string is the whole contract for the common case. A mapping is accepted so a caller
    that already holds a parsed document can pass the frame and regime *that document* was
    read under, rather than the ones the scope happens to carry - a producer that scanned
    a document in one frame and reported signals in another would be a record of nothing.
    """
    if isinstance(record, str):
        return record, {}
    if isinstance(record, Mapping):
        text = str(record.get("text", "") or "")
        overrides = {
            key: str(record[key])
            for key in ("context_ref", "semantic_regime_ref", "document_ref")
            if record.get(key)
        }
        return text, overrides
    return "", {}


def _mention_ref(role: str, surface: str) -> str:
    """A stable reference for a surface at a role, for producers that read no mention layer.

    The lexical producer sits below mention extraction, so it has no ``mention_id`` to
    cite. Rather than invent one that a later layer would have to re-derive, it addresses
    the surface by role and content, and the assembler resolves it against the mention
    layer's own ids. The alternative - letting the producer mint ids - would put mention
    identity inside extraction, which is precisely the resolution this whole feature is
    arranged to keep out.
    """
    cleaned = " ".join(surface.split())
    if not cleaned:
        return ""
    return f"surface:{role}:{cleaned.lower()}"


def lexical_signals(
    records: Iterable[object], *, scope: ExtractionScope
) -> tuple[RelationSignal, ...]:
    """Convenience for one call site, equivalent to ``run_producer`` over a lexical producer.

    Exists so the orchestrator has a one-liner, and it delegates to
    :func:`~extractors.signals.protocol.run_producer` rather than reimplementing the
    stamping and the boundedness check - a second code path here would be a second place
    for the registry's authority over ``producer_ref`` to be bypassed.
    """
    from extractors.signals.protocol import run_producer

    return run_producer(LexicalCueExtractor(), records, scope=scope)


__all__ = [
    "INDEPENDENCE_FAMILY",
    "MAX_PAIRS_CONSIDERED",
    "PRODUCER_REF",
    "PRODUCER_VERSION",
    "LexicalCueExtractor",
    "lexical_signals",
]
