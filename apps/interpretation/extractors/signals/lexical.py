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

**Boundedness is the honest part, and the ceiling is live.** A cue site is found by scanning
a regex over the document, so :attr:`~extractors.signals.signal.Neighbourhood.pairs_considered`
is *not* a pair count in the ``O(n²)`` sense - no mention pair is ever enumerated, and the
count is a stated ``0`` for exactly that reason. What a reader can check is
:attr:`~extractors.signals.signal.Neighbourhood.characters_scanned`, and it is the length of
the text this producer actually swept. :data:`MAX_PAIRS_CONSIDERED` is the ceiling that
sweep is held to, and it is compared against something the producer reports rather than
against a literal: before Phase 4B this constant was declared here and against a hard-coded
``0`` in :func:`~extractors.signals.signal.assert_bounded`, which meant a gate that could
never fire and a ceiling that could never be exceeded - the appearance of a bound with none
underneath it (FR-093). It is now the ceiling the registry checks, and
``test_the_declared_ceiling_is_live_and_a_real_scan_trips_it`` is the test that says so.

**Its two participants are occurrences, addressed whole.** Phase 4B replaced
``surface:role:acme`` with :func:`~extractors.signals.mentions.deferred_occurrence` over the
cue site's own character offsets. The old address was a fabrication in two ways: the word
``role`` was a label this producer chose rather than a position anything in the document
declares, and the address carried no position, so the same person named twice in one document
was one participant and the second cue corroborated the first.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from domain.predicate_signature import ArgumentSlot, Polarity
from domain.relation_participant import RelationParticipant
from domain.signal_basis import SignalBasis
from semantic.blocking import RelationRole

from extractors.relations import RELATION_CUES, CueSite, extract_cue_sites
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

#: The producer's identity, and the version that goes with it. Both are required by
#: :class:`~extractors.signals.protocol.ProducerDeclaration` because FR-034's independence
#: count is computed over *producers*, and a signal whose producer cannot be named cannot
#: be counted at all. Two versions of this producer are still one source, which is what
#: :attr:`ProducerDeclaration.independence_family` records.
PRODUCER_REF = "lexical/cue-phrase"
PRODUCER_VERSION = "2"
INDEPENDENCE_FAMILY = "prose"

#: The character ceiling one document sweep is held to, and the number a reader checks
#: ``Neighbourhood.characters_scanned`` against.
#:
#: It is a ceiling on *characters swept*, which is what this producer's ``scope_read``
#: describes and the only extent it has, and it is live in two directions: the registry
#: refuses a signal whose ``characters_scanned`` exceeds it, and a document longer than the
#: ceiling is refused by the sweep with :data:`DOCUMENT_TOO_LONG_CODE` rather than
#: half-read. Before Phase 4B the constant existed and was compared against a hard-coded
#: ``0`` in the neighbourhood, so it was a number in a declaration and a bound on nothing.
MAX_PAIRS_CONSIDERED = 10_000

#: The named refusal for a document too long to sweep whole. A code rather than a truncated
#: read, because a producer that scanned the first 10,000 characters of a 200,000-character
#: page and reported the cues it found would be reporting a different document's worth of
#: evidence under the document's own ``capture_ref``.
DOCUMENT_TOO_LONG_CODE = "lexical_document_exceeds_sweep_ceiling"

#: The two ends' address labels, taken from the platform's own
#: :class:`~semantic.blocking.RelationRole` rather than from this producer's cue table.
#:
#: The cue's regex groups are called ``role`` and ``object``, and using them produced
#: ``surface:role:CEO`` - an address whose first component was a word *this module* chose
#: about the world. Two producers labelling one mention differently address it as two
#: participants, so a label has to come from a vocabulary both can read;
#: :class:`~domain.relation_participant.RelationParticipant.slot` already refuses a free-text
#: role for exactly this reason (FR-009). :class:`~semantic.blocking.RelationRole` is that
#: vocabulary and it is the one the 018 cue path addresses its own two ends with
#: (``relations.py``'s ``_fallback_ref``), so a reader comparing the two paths sees one
#: naming scheme rather than two.
SUBJECT_GROUP_LABEL = RelationRole.SUBJECT.value
OBJECT_GROUP_LABEL = RelationRole.OBJECT.value


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
                f"neighbourhood's pair count is a stated 0 and this declaration's ceiling of "
                f"{MAX_PAIRS_CONSIDERED} is checked against the characters the sweep covered, "
                "which is the extent this producer actually has"
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

        A document longer than :data:`MAX_PAIRS_CONSIDERED` characters is **refused with
        :data:`DOCUMENT_TOO_LONG_CODE`** rather than swept to the ceiling. Sweeping half a
        page and reporting the cues found under the page's own ``capture_ref`` would be
        evidence about a shorter document wearing a longer document's name, and the ceiling
        would then be a truncation wearing a bound's name.
        """
        text, overrides = _text_of(record)
        if not text.strip():
            return ()
        scanned = max(1, len(text))
        if scanned > MAX_PAIRS_CONSIDERED:
            raise SignalContractError(
                DOCUMENT_TOO_LONG_CODE,
                f"the record is {scanned} characters and this producer sweeps at most "
                f"{MAX_PAIRS_CONSIDERED} in one call. It is scoped to one document's prose "
                "and cannot decide that the cues it missed in the remainder are absent; a "
                "truncated sweep would report the cues it found and be indistinguishable "
                "from a complete one. Split the record, or declare a higher ceiling and say "
                "why (FR-041…FR-043)",
            )
        signals: list[RelationSignal] = []
        for ordinal, site in enumerate(extract_cue_sites(text)):
            signal = self._signal_for(
                site,
                scope=scope,
                ordinal=ordinal,
                characters_scanned=scanned,
                overrides=overrides,
            )
            if signal is not None:
                signals.append(signal)
        return tuple(signals)

    def _signal_for(
        self,
        site: CueSite,
        *,
        scope: ExtractionScope,
        ordinal: int,
        characters_scanned: int,
        overrides: Mapping[str, str],
    ) -> RelationSignal | None:
        """One cue site as one signal, or ``None`` if the site names no usable occurrence.

        A cue match always has two surfaces by construction - :func:`extract_cue_sites`
        only reports a site when both its groups matched - so ``None`` here means the
        surfaces could not be *addressed*, which is a mention-layer concern and not this
        producer's to solve. Dropping the signal with no note would lose the fact that a cue
        was found, so the drop happens where the address is minted and nowhere else.
        """
        cue = site.cue
        try:
            subject_ref = deferred_occurrence(
                label=SUBJECT_GROUP_LABEL,
                surface=site.role_surface,
                start=site.role_start,
                end=site.role_start + len(site.role_surface),
            )
            object_ref = deferred_occurrence(
                label=OBJECT_GROUP_LABEL,
                surface=site.object_surface,
                start=site.object_start,
                end=site.object_end,
            )
        except SignalContractError:
            # A group that matched with no readable surface is a cue site the producer
            # cannot address. Declining the whole signal is right: a one-ended signal is a
            # property of one thing, and `signal_arity_below_two` would refuse it anyway.
            return None
        return RelationSignal(
            participants=(
                RelationParticipant(
                    mention_ref=subject_ref,
                    slot=ArgumentSlot(0),
                    # The platform's role name for this end, which is a closed vocabulary
                    # and not a guess: "seller" and "vendor" are guesses, and two producers
                    # guessing differently for one slot must produce one logical candidate
                    # (FR-009). The cue's own affordance types travel in `extra`.
                    role_hypothesis=SUBJECT_GROUP_LABEL,
                    ordinal=0,
                    confidence=1.0,
                ),
                RelationParticipant(
                    mention_ref=object_ref,
                    slot=ArgumentSlot(1),
                    role_hypothesis=OBJECT_GROUP_LABEL,
                    ordinal=1,
                    confidence=1.0,
                ),
            ),
            kind=SignalKind.LEXICAL,
            # The words the document used, not the operator's name. Both are on the
            # signal: the surface is the evidence, the ref is the reading of it, and a
            # later regime reading the same surface differently is then visible as a
            # second reading rather than as a correction to the first.
            relation_surface=site.trigger_surface.strip() or cue.affordance.role_phrase,
            # Stated, not defaulted. The cue phrase *is* this producer's observation, so
            # claiming a weaker basis than the one used would be a record understating its
            # own evidence, and claiming a stronger one is not on offer: the basis
            # vocabulary has no "lexical cue" member and `predicate_text` obliges the
            # surface, which this signal carries.
            basis=SignalBasis.PREDICATE_TEXT,
            # Stated by this producer, not defaulted. The sweep finds phrases and has no
            # test for a negation it could apply, so every signal here is asserted by
            # construction; saying so is the honest record, and a producer that later reads
            # a negator has one field to set.
            polarity=Polarity.ASSERTED,
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
                # `characters_scanned` already records how much was read, and it is what
                # this producer's ceiling is now checked against.
                pairs_considered=0,
                scope_read=(
                    f"the whole document, swept once for cue phrases; no mention pair was "
                    f"enumerated (cue {cue.cue_id} matched at char {site.role_start})"
                ),
                precision="exact",
                notes=(
                    "A cue match is evidence that the phrase occurred between two surfaces, "
                    "not that the relation holds. Both participants are deferred occurrence "
                    "references: addressed, unresolved, and resolved by nothing."
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
                # **The role bindings, and the coupling is the point.** The cue declares its
                # ``arity_mode`` above, and a producer that states ``nary`` without naming its
                # slots cannot produce a legal candidate: :class:`RelationCandidate` refuses a
                # ``NARY`` candidate with fewer than two role assignments
                # (``insufficient_role_assignments``), because a claim built on it could never be
                # promoted. That refusal was unreachable while this producer's signals sat in
                # their own address namespace; Phase 4C bound them to real mention ids, and a
                # bound signal reaches assembly, so the coupling became reachable and the
                # omission stopped being latent. The names are the cue's own — the affordance's
                # ``subject_role``/``object_role`` and its single declared class per end — so
                # they are read off the pattern rather than chosen here, and ``declared_kind_for``
                # is empty when the cue admits several classes, which is the honest answer
                # rather than picking one.
                #
                # ``extra`` is excluded from ``RelationSignal._material()``, so this changes no
                # ``signal_id``: it is a completeness fix, not a re-keying.
                "role_bindings": (
                    (
                        cue.affordance.subject_role,
                        subject_ref,
                        cue.affordance.declared_kind_for(RelationRole.SUBJECT),
                    ),
                    (
                        cue.affordance.object_role,
                        object_ref,
                        cue.affordance.declared_kind_for(RelationRole.OBJECT),
                    ),
                ),
                # The cue's position, kept because the signal carries no resolvable span.
                "trigger_char_start": site.role_start,
                "trigger_char_end": site.trigger_end,
                "role_surface": site.role_surface,
                "object_surface": site.object_surface,
                # The two ends' character offsets, so the deferred references above can be
                # bound against the mention layer's own spans without re-running this sweep.
                "subject_char_start": site.role_start,
                "subject_char_end": site.role_start + len(site.role_surface),
                "object_char_start": site.object_start,
                "object_char_end": site.object_end,
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
    "DOCUMENT_TOO_LONG_CODE",
    "INDEPENDENCE_FAMILY",
    "MAX_PAIRS_CONSIDERED",
    "OBJECT_GROUP_LABEL",
    "PRODUCER_REF",
    "PRODUCER_VERSION",
    "SUBJECT_GROUP_LABEL",
    "LexicalCueExtractor",
    "lexical_signals",
]
