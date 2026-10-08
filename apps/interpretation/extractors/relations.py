"""Relation-aware extraction: the cue is the reading (spec 018, T021-T023, FR-017..FR-019).

Spec 007's extractors read *surfaces*. A person is a name-shaped window; an organisation is
a window that ends in a legal form. Those are real grammars and they are honest about their
limits - but it means ``"John Smith became CEO of Acme in 2020."`` yields one mention,
because ``Acme`` carries no legal form, and the orchestrator grew a cue-keyed rule of its
own to compensate. The relation was in the sentence the whole time, and nothing in the
design ever obliged us to finish two entities before reading it.

So this module finds the **cue** first and finds the participants *through* it. ``CEO of`` is
found; the relation it names (``works_for``) is known; and a known relation says what may sit
at its object end - ``schema:Organization``. That is a **semantic affordance**, and it is
what makes ``Acme`` recoverable without a suffix. The legal-form grammar in
:mod:`extractors.orgs` and this one are complementary halves of the same honest
uncertainty, not two implementations of one rule.

**The order is the deliverable, and it is in the shape of the code rather than in a
comment.** :func:`extract_cue_sites` runs first and looks at no participant; the mentions
are then read *through* a site; and the object mention's ``kind`` comes from
:attr:`CueAffordance.object_mention_kind` - the affordance - and from no pattern that the
object's own surface matched. Put the surface grammars back in front and ``Acme`` vanishes
again.

**A cue is a row, not a branch.** :data:`RELATION_CUES` is the whole extension point.
Reading another relation is adding one :class:`RelationCue`; the site reader, the
participant resolution, the spans, the temporal hypothesis and the candidate construction
below are already generic over it. A pile of cue-specific code paths is the failure this
module exists to end, so there is one code path here and no second.

**Extraction does not admit (FR-019, SC-10).** Nothing in this module can mark a reading
``SUPPORTED``: :class:`domain.relation_candidate.CandidateStatus` is not imported here, no
function accepts a status and no field holds one.
:meth:`RelationalReading.to_candidate` builds a
:class:`domain.relation_candidate.RelationCandidate` and leaves ``candidate_status`` at the
dataclass default, which is ``PROPOSE``. Admission is a later layer's decision about a
checked hypothesis, and the strongest way to keep it that way is for this package to hold
no vocabulary for it at all. The two references the extractor may not invent - the evidence
``context_ref`` and the ``semantic_regime_ref`` - are required arguments of
:meth:`RelationalReading.to_candidate`, because a frame and a regime are somebody else's
decisions and a default here would be a silent substitution (FR-015, FR-016).

Deterministic: no clock, no randomness, no network, no model, no I/O. Offsets are UTF-8
byte offsets through :mod:`extractors.util`, as everywhere else in this package, and no id
is minted here - identity is a later layer's business.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from domain.relation_candidate import (
    ExtractionStrategy,
    RelationCandidate,
    SpanRef,
    TemporalHypothesis,
)
from domain.relation_claim import RelationRoleBinding
from domain.relation_identity import RelationArityMode
from domain.relation_schema import TemporalSemantics
from semantic.blocking import AffordanceLike, RelationRole, TypeHypothesis, affordance_kinds
from semantic.contracts import RelationRef

from extractors.persons import extract_persons
from extractors.types import TypedMention
from extractors.util import byte_offset

EXTRACTOR_ID = "relations"
EXTRACTOR_VERSION = "relations@1"
RELATION_RULE_ID = "relation_cue_affordance@1"
ROLE_TARGET_ORG_EXTRACTOR_ID = "role_target_orgs"
CUE_CONFIDENCE = 0.5

_TRIM = " .,;:"


@dataclass(frozen=True)
class CueSpan:
    """A region of the source in UTF-8 byte offsets, before a segment is named.

    A :class:`domain.relation_candidate.SpanRef` needs a ``segment_ref`` and refuses an
    empty one, while this extractor is handed a *text*: which segment the text came from
    is the caller's to say. So the span travels without one and :meth:`into` supplies it at
    the moment the caller knows it. The offsets are the same byte offsets
    ``TypedMention.offset`` carries, so a span and a mention address the same region.
    """

    start: int
    end: int
    surface: str = ""
    mention_ref: str = ""

    @property
    def identity(self) -> tuple[int, int, str]:
        """The order key of a span, over what is resolvable without a segment."""
        return (self.start, self.end, self.mention_ref)

    def into(self, segment_ref: str) -> SpanRef:
        """This span, addressed against ``segment_ref``."""
        return SpanRef(
            segment_ref=segment_ref,
            start=self.start,
            end=self.end,
            mention_ref=self.mention_ref,
        )


@dataclass(frozen=True)
class CueParticipant:
    """One end of a reading, as the cue found it.

    ``mention`` is the mention itself and ``mention_ref`` is what the caller will call it.
    The extractor cannot mint that id - it is derived from the caller's segment, its
    registry and its scheme - so when the caller supplies none the reading falls back to a
    positional name that is stable for the same text, and never to a content address
    dressed up as a durable record id.
    """

    role: str
    mention: TypedMention
    mention_ref: str = ""
    afforded_kinds: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "afforded_kinds", tuple(self.afforded_kinds))

    @property
    def span(self) -> CueSpan:
        """Where this participant's surface sits, in the segment's byte offsets."""
        return CueSpan(
            start=self.mention.offset,
            end=self.mention.end_offset,
            surface=self.mention.value,
            mention_ref=self.mention_ref,
        )


@dataclass(frozen=True)
class CueAffordance:
    """What a cue says may sit at each of its two ends, in the platform's own vocabulary.

    The kind tuples are the *operator's* declared classes (``schema:Person``,
    ``schema:Organization``) spelled exactly as
    :class:`domain.relation_schema.RelationSchema` spells them, because those are the
    strings :func:`semantic.blocking.affordance_kinds` reads off an operator derived from
    that schema. This dataclass is a structural :class:`semantic.blocking.AffordanceLike` -
    two tuple fields, and no import of :mod:`semantic.operators` at all - so
    ``affordance_kinds(cue_affordance(...), role)`` is already the correct call and there
    is no conversion layer in which the two vocabularies could drift apart.

    ``subject_mention_kind`` / ``object_mention_kind`` are the *extraction* layer's spelling
    of the same statement (``"person"``, ``"org"``), and they are what the recovered
    mentions are stamped with. Holding both in one record is what makes the inversion
    checkable: the object mention's kind is read off the affordance, not off the object's
    surface.
    """

    subject_role: str
    object_role: str
    subject_kinds: tuple[str, ...]
    object_kinds: tuple[str, ...]
    subject_mention_kind: str = ""
    object_mention_kind: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "subject_kinds", tuple(self.subject_kinds))
        object.__setattr__(self, "object_kinds", tuple(self.object_kinds))

    def kinds_for(self, role: RelationRole = RelationRole.OBJECT) -> tuple[str, ...]:
        """The endpoint kinds in ``semantic.blocking``'s own comparison form.

        Note this is the *comparison* form, and it is not a type reference:
        ``semantic.blocking.normalize_kind`` case-folds, so ``schema:Organization`` arrives
        here as ``schema: organization``. Use :meth:`declared_kind_for` when a reference has
        to be written down rather than compared.
        """
        return affordance_kinds(self, role)

    def declared_kind_for(self, role: RelationRole = RelationRole.OBJECT) -> str:
        """The operator's declared class at this end, spelled as the schema spells it.

        The canonical single reference for a role binding: empty when the cue declares
        more than one class or none, because naming an arbitrary one of several would be a
        choice this layer is not making.
        """
        kinds = (
            self.subject_kinds
            if RelationRole(role) is RelationRole.SUBJECT
            else self.object_kinds
        )
        return kinds[0] if len(kinds) == 1 else ""

    def role_for(self, role: RelationRole = RelationRole.OBJECT) -> str:
        """The operator's role name at this end: ``person``, ``organization``."""
        if RelationRole(role) is RelationRole.SUBJECT:
            return self.subject_role
        return self.object_role

    def mention_kind_for(self, role: RelationRole = RelationRole.OBJECT) -> str:
        """The extraction-layer kind this end is read as; ``""`` when the cue names none."""
        if RelationRole(role) is RelationRole.SUBJECT:
            return self.subject_mention_kind
        return self.object_mention_kind

    def type_hypotheses(self, role: RelationRole = RelationRole.OBJECT) -> tuple[
        TypeHypothesis, ...
    ]:
        """The same kinds as blocking's ``TYPE`` stage, ready for ``block_for_relation``."""
        return tuple(TypeHypothesis(type_ref=kind) for kind in self.kinds_for(role))


@dataclass(frozen=True)
class RelationCue:
    """One relation this package can read, declared as data.

    A row, not a branch: every cue in :data:`RELATION_CUES` is read by the same code.
    ``pattern`` must expose the two named groups :attr:`role_group` and
    :attr:`object_group`; the trigger is the region between them, which is the cue proper -
    ``"CEO of"`` in ``"became CEO of Acme"``. ``role_words`` is the bare role phrase, kept
    separately so a cue can be recognised from its head alone (``cue_affordance("CEO")``)
    without a participant anywhere in sight.
    """

    cue_id: str
    affordance: CueAffordance
    relation_ref: RelationRef
    arity_mode: RelationArityMode
    pattern: re.Pattern[str]
    role_words: re.Pattern[str]
    role_group: str = "role"
    object_group: str = "object"
    temporal_semantics: TemporalSemantics = TemporalSemantics.OPTIONAL_INTERVAL


@dataclass(frozen=True)
class CueSite:
    """Where one cue was found, in character indices, before anything is read through it.

    Character indices rather than byte offsets because every slice taken while reading is a
    slice of the Python string; the conversion to byte offsets happens once, on the way out
    to a mention or a span. ``trigger_end`` is the end of the cue proper and excludes the
    whitespace before the object, so a trigger span covers ``"CEO of"`` rather than
    ``"CEO of "``.
    """

    cue: RelationCue
    role_surface: str
    role_start: int
    object_surface: str
    object_start: int
    object_end: int
    trigger_surface: str
    trigger_end: int

    @property
    def cue_id(self) -> str:
        """The row that read this site."""
        return self.cue.cue_id


@dataclass(frozen=True)
class RelationalReading:
    """One cue read as a relation: the trigger, both participants, and what was guessed.

    Everything on this record is *evidence*. It states what was seen, where, and on whose
    authority; it states nothing about whether any of it holds. The
    :class:`~domain.relation_candidate.RelationCandidate` it will mint on request is
    ``PROPOSE`` and cannot be anything else from here (FR-019).

    ``temporal_hypothesis`` is a :class:`domain.relation_candidate.TemporalHypothesis` and
    is ``absent`` rather than missing when the sentence carried no date, because "nothing
    was guessed" is itself the finding an operator with a required interval needs to
    report, and an absent hypothesis never raises.

    ``role_assignment`` is the *title* the cue named - ``CEO`` - and is deliberately not
    the same thing as the operator's role bindings: those bind the two participants to the
    roles ``person`` and ``organization``, and :meth:`role_bindings` builds them.
    """

    cue_id: str
    relation_ref: RelationRef
    affordance: CueAffordance
    arity_mode: RelationArityMode
    subject: CueParticipant
    object: CueParticipant
    trigger_span: CueSpan
    supporting_spans: tuple[CueSpan, ...] = ()
    role_assignment: str = ""
    temporal_hypothesis: TemporalHypothesis = field(default_factory=TemporalHypothesis.absent)
    extraction_method: ExtractionStrategy = ExtractionStrategy.LEXICAL_PATTERN
    extractor_version: str = EXTRACTOR_VERSION
    extraction_rule_id: str = RELATION_RULE_ID
    observation_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    lang: str | None = None
    confidence: float = CUE_CONFIDENCE

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "supporting_spans",
            tuple(sorted(set(self.supporting_spans), key=lambda span: span.identity)),
        )
        object.__setattr__(self, "observation_refs", tuple(sorted({str(r) for r in self.observation_refs})))
        object.__setattr__(self, "evidence_refs", tuple(sorted({str(r) for r in self.evidence_refs})))

    @property
    def relation_type(self) -> str:
        """The operator's relation type, read off the reference rather than restated."""
        return self.relation_ref.relation_type

    @property
    def cue_surface(self) -> str:
        """The cue text itself - ``"CEO of"`` - which is what the trigger span covers."""
        return self.trigger_span.surface

    def mentions(self) -> tuple[TypedMention, ...]:
        """Both participants, subject first, each carrying its own producer's attribution."""
        return (self.subject.mention, self.object.mention)

    def participant_for(self, role: RelationRole) -> CueParticipant:
        """The participant at one end of the relation."""
        if RelationRole(role) is RelationRole.SUBJECT:
            return self.subject
        return self.object

    def role_bindings(
        self, mention_refs: Mapping[str, str] | None = None
    ) -> tuple[RelationRoleBinding, ...]:
        """The operator's role bindings for the two participants.

        A candidate's bindings name *mentions*, because a candidate has resolved nothing;
        a claim's must name admitted participants. That rebuild is the admission layer's
        job and is not attempted here.
        """
        refs = self._mention_refs(mention_refs)
        return tuple(
            RelationRoleBinding(
                self.affordance.role_for(role),
                refs[str(role)],
                self.affordance.declared_kind_for(role),
            )
            for role in (RelationRole.SUBJECT, RelationRole.OBJECT)
        )

    def to_candidate(
        self,
        *,
        segment_ref: str,
        context_ref: str,
        semantic_regime_ref: str,
        mention_refs: Mapping[str, str] | None = None,
        tenant_id: str = "default-tenant",
        investigation_id: str = "",
        observed_at: datetime | None = None,
        recorded_by: str = "",
        confidence: float | None = None,
        temporal_hypothesis: TemporalHypothesis | None = None,
    ) -> RelationCandidate:
        """This reading as a candidate, at ``PROPOSE``.

        ``segment_ref``, ``context_ref`` and ``semantic_regime_ref`` are required and have
        no defaults: the first names where the spans are, the second is the evidence frame
        and the third the semantic regime that interpreted it. None of the three is this
        layer's to choose, and a default for any of them would be a substitution made
        silently (FR-015, FR-016).

        ``mention_refs`` maps ``"subject"`` / ``"object"`` onto the ids the caller minted
        for the two mentions, which is why it exists at all - the ids are derived from the
        caller's segment and registry, and this reading is a map into the caller's
        fan-out rather than a replacement for it.

        ``temporal_hypothesis`` replaces the reading's own guess. It exists because the
        guess here is coarse by construction - a bare year is read as the whole year it
        names - and a caller holding a sharper fact is stating a fact, not overruling this
        layer. ``None`` means "use the reading's", never "use no window": an absent guess is
        carried as :meth:`TemporalHypothesis.absent`.

        There is no ``candidate_status`` parameter, and no path from this module to
        ``SUPPORTED``. The candidate is minted at the dataclass default and left there
        (FR-019, SC-10). Ids are not stamped either: :meth:`RelationCandidate.with_id` is
        the caller's to call, because deriving identity is a layer of its own.
        """
        refs = self._mention_refs(mention_refs)
        return RelationCandidate(
            subject_mention_ref=refs[str(RelationRole.SUBJECT)],
            object_mention_ref=refs[str(RelationRole.OBJECT)],
            relation_ref=self.relation_ref,
            arity_mode=self.arity_mode,
            role_assignments=self.role_bindings(refs),
            context_ref=context_ref,
            semantic_regime_ref=semantic_regime_ref,
            trigger_span=self.trigger_span.into(segment_ref),
            supporting_spans=tuple(span.into(segment_ref) for span in self.supporting_spans),
            extraction_method=self.extraction_method,
            extractor_version=self.extractor_version,
            extraction_rule_id=self.extraction_rule_id,
            observation_refs=self.observation_refs,
            evidence_refs=tuple(sorted({*self.evidence_refs, *refs.values()})),
            temporal_hypothesis=temporal_hypothesis or self.temporal_hypothesis,
            confidence=self.confidence if confidence is None else float(confidence),
            tenant_id=tenant_id,
            investigation_id=investigation_id,
            observed_at=observed_at,
            recorded_by=recorded_by,
        )

    def _mention_refs(self, mention_refs: Mapping[str, str] | None) -> dict[str, str]:
        """Resolved mention refs, preferring the caller's over the positional fallback."""
        given = {str(key): str(value) for key, value in (mention_refs or {}).items()}
        return {
            str(role): given.get(str(role), "") or self.participant_for(role).mention_ref
            for role in (RelationRole.SUBJECT, RelationRole.OBJECT)
        }


#: Role vocabulary for the English ``role_of`` grammar.
#:
#: Extended because the table's coverage, not its machinery, was the limit: the original
#: alternation read "is deputy chairman of X" and nothing else. Three shapes were added,
#: each a real English construction rather than a variation on one:
#:
#: * case - the cue pattern is now matched case-insensitively. "President of Russia" did
#:   not match the alternation `president`, because the pattern carried no IGNORECASE
#:   while ``role_words`` did. A title is capitalised at the start of a clause and
#:   lowercase mid-sentence, so the original could only ever read one of the two.
#: * multi-word titles - ``chief executive officer``, ``chief financial officer``,
#:   ``deputy chairman``, ``vice president``. The old ``chief\s+[A-Za-z]+`` matched two
#:   words and then demanded a preposition, so a three-word title could not match.
#: * ownership and equity - ``owns``, ``owner of``, ``majority stake``. Ownership is not
#:   employment; it is reported as ``owns`` rather than ``works_for``, because claiming a
#:   founder is an employee would be a claim the text does not make.
_EN_TITLE = (
    # The trailing noun is part of the title, not filler: without it "chief executive
    # officer" captured the role as "chief executive" and the bridge swallowed
    # "officer of". A role is metadata an analyst reads, so it has to be the whole title.
    r"(?:chief\s+(?:executive|financial|operating|technical|information|marketing)"
    r"(?:\s+(?:officer|director))?"
    r"|chief\s+[A-Za-z]+(?:\s+(?:officer|director))?|"
    r"(?:deputy|assistant|acting|interim|co-)?"
    r"(?:president|chair(?:man|woman|person)|director|manager|partner|owner"
    r"|head|supervisor|administrator|treasurer|secretary|officer)"
    r"(?:\s+(?:of|for|deputy|assistant))*)"
)
_EN_ROLE = (
    r"CEO|" + _EN_TITLE + r"|owns?|owned|holder\s+of|majority\s+(?:stake|shareholder)"
)

#: Bridge between a role and its organisation.
#:
#: English puts material between them constantly - "chairman of the board of Gazprom",
#: "owns 51 percent of the stake in Bank Rossiya". A cue that required the preposition to
#: touch the name read none of those, which is most real sentences about senior people.
_EN_BRIDGE = (
    # Repeated rather than single-pass: English stacks material without limit -
    # "of the board of", "of 51 percent of the class A shares of". One optional pass
    # read none of the stacked forms, which is most of them. Non-greedy so the engine
    # stops at the first preposition that a capitalised name follows, rather than
    # swallowing the name into the filler.
    r"(?:(?:of|in|at|for)\s+)?"
    r"(?:(?:the|a|an|its|their|his|her)\s+)?"
    r"(?:\d+(?:\.\d+)?\s*(?:percent|per\s+cent|%)\s*)?"
    r"(?:[A-Za-z]+\s+){0,4}?"
    r"(?:of|in|at)\s+"
)
#: An organisation name: capitalised tokens only.
#:
#: The ``(?-i:...)`` groups are load-bearing. The cue pattern carries IGNORECASE so a
#: capitalised title like "President" matches its lowercase alternation, but that flag
#: must not reach the name: without the scoped reset `[A-Z]` also matches lowercase and
#: "owns 51 percent of the stake in Bank Rossiya" resolved its object as
#: "the stake in Bank". A cue that names the wrong organisation is worse than no cue,
#: because it is a false assertion rather than an absence.
_EN_NAME = (
    r"(?-i:[A-Z][A-Za-z0-9&.'-]*(?:\s+(?-i:[A-Z])[A-Za-z0-9&.'-]*){0,3})"
)
_RU_ROLE = (
    r"генеральный\s+директор(?:ом|а|у|е)?|директор(?:ом|а|у|е)?|президент(?:ом|а|у|е)?"
    r"|руководител(?:ем|я|ю|е|и)?|владелец(?:ом|а|у|е)?"
)
_RU_NAME = r"[А-ЯЁ][А-Яа-яёЁ0-9&.'-]*(?:\s+[А-ЯЁ][А-Яа-яёЁ0-9&.'-]*){0,2}"

_WORKS_FOR_AFFORDANCE = CueAffordance(
    subject_role="person",
    object_role="organization",
    subject_kinds=("schema:Person",),
    object_kinds=("schema:Organization",),
    subject_mention_kind="person",
    object_mention_kind="org",
)

RELATION_CUES: tuple[RelationCue, ...] = (
    RelationCue(
        cue_id="works_for.role_of_en",
        affordance=_WORKS_FOR_AFFORDANCE,
        relation_ref=RelationRef("works_for", "1"),
        arity_mode=RelationArityMode.NARY,
        # No leading verb. An earlier revision required one ("is", "serves as") and
        # matched none of the corpus, because the cue is read as a role phrase wherever
        # it sits: "the President of Russia" and a bare caption "chairman of Gazprom"
        # are the same cue. Requiring a verb made the table read only full clauses.
        pattern=re.compile(
            rf"(?<![A-Za-z])(?P<role>{_EN_ROLE})\s+{_EN_BRIDGE}(?P<object>{_EN_NAME})",
            re.IGNORECASE,
        ),
        role_words=re.compile(rf"\b(?:{_EN_ROLE})\b", re.IGNORECASE),
        temporal_semantics=TemporalSemantics.POINT,
    ),
    RelationCue(
        cue_id="works_for.role_of_ru",
        affordance=_WORKS_FOR_AFFORDANCE,
        relation_ref=RelationRef("works_for", "1"),
        arity_mode=RelationArityMode.NARY,
        pattern=re.compile(rf"\b(?P<role>{_RU_ROLE})\s+(?:в\s+|при\s+)?(?P<object>{_RU_NAME})"),
        role_words=re.compile(rf"\b(?:{_RU_ROLE})\b", re.IGNORECASE),
        temporal_semantics=TemporalSemantics.POINT,
    ),
)
"""Every cue this package reads. Two rows, one relation, two cue grammars.

The two rows are there to make the shape of the extension point visible rather than
theoretical: the second is the same relation read from a different surface, and nothing
below :data:`RELATION_CUES` knows or cares which row it is running. What is *not* here is
a relation the table cannot read - an ungrammatical cue row would be a claim of
capability that does not exist, which is the one thing a table of affordances must never
be.
"""

_YEAR = re.compile(r"\b(?:19|20|21)\d{2}\b")


def relation_cue(surface: str) -> RelationCue | None:
    """The cue row whose role phrase ``surface`` names; ``None`` when no cue reads it.

    Matched on the role alone, so an affordance is available from ``"CEO"`` with no
    participant and no sentence around it - which is the order the blocking stage wants
    to be able to ask in.
    """
    text = str(surface or "").strip()
    if not text:
        return None
    for cue in RELATION_CUES:
        if cue.role_words.search(text):
            return cue
    return None


def cue_affordance(surface: str) -> CueAffordance | None:
    """The affordance of the cue named by ``surface``; ``None`` when the text names no cue.

    The returned object is a ``semantic.blocking.AffordanceLike``, so the kinds a caller
    hands to :func:`semantic.blocking.affordance_kinds` later are the very kinds this
    extractor read the object with.
    """
    cue = relation_cue(surface)
    return cue.affordance if cue is not None else None


def matches_operator(affordance: CueAffordance, operator: AffordanceLike | None) -> bool:
    """Whether ``operator`` affords exactly the kinds ``affordance`` does, at both ends.

    The check to run before trusting a narrowing: it compares the extraction layer's
    vocabulary with the operator's own *through* the one function that reads both, so
    "the cue said organization and the operator affords organization" is verified rather
    than assumed. ``False`` for no operator at all, because an operator that declares
    nothing narrows nothing and agreeing with it by accident is not agreement.
    """
    if operator is None:
        return False
    return all(
        affordance.kinds_for(role) == affordance_kinds(operator, role)
        for role in (RelationRole.SUBJECT, RelationRole.OBJECT)
    )


def extract_cue_sites(text: str) -> tuple[CueSite, ...]:
    """Find the cues in ``text``, in surface order. This runs first and decides nothing.

    Relation-first, literally: a site is found with no participant in sight, so a cue whose
    participants extraction cannot name is still a cue and its affordance is still
    available to whoever asks. Sites are ordered by position and then by cue id, so the
    sequence is a function of the text alone.
    """
    body = str(text or "")
    sites: list[CueSite] = []
    for cue in RELATION_CUES:
        for match in cue.pattern.finditer(body):
            site = _site_from(cue, match)
            if site is not None:
                sites.append(site)
    return tuple(sorted(sites, key=lambda site: (site.role_start, site.cue_id)))


def extract_relational_readings(
    text: str,
    *,
    lang_hint: str | None = None,
    observation_refs: Iterable[str] = (),
) -> list[RelationalReading]:
    """Read every cue in ``text`` as a relation, in three passes.

    Pass one is :func:`extract_cue_sites`: the cue, found with no participant in sight.
    Pass two reads the participants *through* each site - the object from the region the
    cue points at, typed by the cue's affordance, and the subject from the nearest mention
    to the left whose kind the cue affords at its subject end, which is where ``became``
    puts it. Pass three assembles the reading: spans, the role the cue named, the temporal
    hypothesis.

    A site missing either participant yields no reading. That is not a rejection of
    anything: the site stays reportable through :func:`extract_cue_sites`, every mention
    involved is still reported by whichever extractor found it, and a half-relation is not
    a thing this layer may invent an endpoint for.
    """
    body = str(text or "")
    sites = extract_cue_sites(body)
    if not sites:
        return []
    subjects = extract_persons(body, lang_hint=lang_hint)
    readings: list[RelationalReading] = []
    for site in sites:
        reading = _read_site(
            body,
            site,
            subjects,
            lang_hint=lang_hint,
            observation_refs=tuple(observation_refs),
        )
        if reading is not None:
            readings.append(reading)
    return readings


def extract_relational_mentions(text: str, lang_hint: str | None = None) -> list[TypedMention]:
    """The mentions a cue reading recovered, in surface order.

    The drop-in form for a :class:`extractors.registry.DeterministicExtractorSet`: the same
    ``(text, lang_hint) -> list[TypedMention]`` shape as every other producer there, so the
    relation-aware readings ride the ordinary fan-out instead of being handed to a caller
    separately. Both participants are returned, each with the attribution of whichever
    extractor actually found it - the person came from :mod:`extractors.persons`, the
    organisation came from here because the cue found it.
    """
    found: list[TypedMention] = []
    for reading in extract_relational_readings(text, lang_hint=lang_hint):
        found.extend(reading.mentions())
    return _dedup(found)


def extract_role_target_orgs(text: str, lang_hint: str | None = None) -> list[TypedMention]:
    """The cue-keyed organisation rule, moved here out of the semantic path (T021, FR-018).

    The rule is the same one the orchestrator used to hold and its output is the same: the
    proper-noun run a role cue points at, at the pattern tier's confidence, with the cue
    recorded in ``evidence["cue"]`` and the producer recorded as
    :data:`ROLE_TARGET_ORG_EXTRACTOR_ID`. What changed is where it lives - beside the
    grammar it complements, inside the package that owns extraction rules, instead of in
    the one module that was never supposed to hold one (FR-018).

    It is kept as a named entry point because it swaps in without moving a single mention
    id. :func:`extract_relational_mentions` is the same reading plus the relation itself,
    and both are driven by the one :func:`extract_cue_sites`, so the moved rule is not a
    second copy of the cue grammar.
    """
    found: list[TypedMention] = []
    for site in extract_cue_sites(text):
        mention = _object_mention(text, site, lang_hint=lang_hint, extractor_id=(
            ROLE_TARGET_ORG_EXTRACTOR_ID
        ))
        if mention is not None:
            found.append(mention)
    return _dedup(found)


def register_relational_extractors(extractors: Any) -> None:
    """Register the relation-aware producer on an extractor set.

    The seam :func:`extractors.registry.register_deterministic_extractors` already provides
    for a producer that is not one of the five built-ins, used here for a stated reason: a
    relation reading is a *second* reading of the same text, so whether a caller's mention
    list should contain it is a policy about what that list means, and this package does not
    make that choice on the caller's behalf. ``register`` keeps first-registration-wins, so
    calling this twice with one set registers once.
    """
    extractors.register(EXTRACTOR_ID, extract_relational_mentions)


def _site_from(cue: RelationCue, match: re.Match[str]) -> CueSite | None:
    """One site of ``cue``'s grammar, with its surfaces trimmed and its offsets kept true."""
    role = match.group(cue.role_group)
    obj = match.group(cue.object_group)
    if not role or not obj:
        return None
    surface = obj.strip(_TRIM)
    if not surface:
        return None
    start = match.start(cue.object_group) + (len(obj) - len(obj.lstrip(_TRIM)))
    role_start = match.start(cue.role_group)
    gap = match.group(0)[role_start - match.start() : start - match.start()]
    return CueSite(
        cue=cue,
        role_surface=role.strip(),
        role_start=role_start,
        object_surface=surface,
        object_start=start,
        object_end=start + len(surface),
        trigger_surface=gap.strip(),
        trigger_end=role_start + len(gap.rstrip()),
    )


def _read_site(
    text: str,
    site: CueSite,
    subjects: list[TypedMention],
    *,
    lang_hint: str | None,
    observation_refs: tuple[str, ...],
) -> RelationalReading | None:
    """Assemble one reading from one site, or ``None`` when an end has no participant."""
    affordance = site.cue.affordance
    subject = _subject_mention(text, site, subjects)
    obj = _object_mention(text, site, lang_hint=lang_hint, extractor_id=EXTRACTOR_ID)
    if subject is None or obj is None:
        return None
    subject_ref = _fallback_ref(RelationRole.SUBJECT, subject)
    object_ref = _fallback_ref(RelationRole.OBJECT, obj)
    hypothesis, temporal_span = _read_temporal(text, site, subject)
    trigger = CueSpan(
        start=byte_offset(text, site.role_start),
        end=byte_offset(text, site.trigger_end),
        surface=site.trigger_surface,
    )
    supporting = (_span_of(subject, subject_ref), _span_of(obj, object_ref), *temporal_span)
    return RelationalReading(
        cue_id=site.cue_id,
        relation_ref=site.cue.relation_ref,
        affordance=affordance,
        arity_mode=site.cue.arity_mode,
        subject=CueParticipant(
            role=affordance.subject_role,
            mention=subject,
            mention_ref=subject_ref,
            afforded_kinds=affordance.kinds_for(RelationRole.SUBJECT),
        ),
        object=CueParticipant(
            role=affordance.object_role,
            mention=obj,
            mention_ref=object_ref,
            afforded_kinds=affordance.kinds_for(RelationRole.OBJECT),
        ),
        trigger_span=trigger,
        supporting_spans=supporting,
        role_assignment=site.role_surface,
        temporal_hypothesis=hypothesis,
        observation_refs=observation_refs,
        lang=lang_hint,
    )


def _object_mention(
    text: str,
    site: CueSite,
    *,
    lang_hint: str | None,
    extractor_id: str,
) -> TypedMention | None:
    """The object the cue points at, typed by the affordance rather than by its surface.

    This function is the module. A pattern found the *cue*; nothing about ``Acme``
    suggested an organisation; the relation did, by affording ``schema:Organization`` at
    its object end. Confidence stays at the pattern tier for the same reason every other
    grammar in this package keeps it there: a cue is evidence, and evidence is worth what a
    pattern is worth however good the pattern is.
    """
    if not site.object_surface:
        return None
    return TypedMention(
        kind=site.cue.affordance.object_mention_kind,
        value=site.object_surface,
        offset=byte_offset(text, site.object_start),
        end_offset=byte_offset(text, site.object_end),
        extractor=extractor_id,
        lang=lang_hint,
        source="pattern",
        confidence=CUE_CONFIDENCE,
        evidence={
            "cue": site.trigger_surface,
            "cue_id": site.cue_id,
            "reading": "relation_cue",
            "role": site.cue.affordance.object_role,
            "affordance": list(site.cue.affordance.object_kinds),
        },
    )


def _subject_mention(text: str, site: CueSite, subjects: list[TypedMention]) -> TypedMention | None:
    """The mention the cue points back to: the nearest one ending before the cue.

    Bounded on the left of the cue because that is where a subject of ``<role> of <org>``
    lives, and filtered to the kind the cue affords at its subject end because a reading
    whose subject is not subject-like is not a reading this cue supports. The filter is on
    *reading formation*, not on the mention: a mention of another kind is still reported by
    whichever extractor found it, and reading it as this cue's subject would be exactly the
    silent type inference the affordance was introduced to avoid.
    """
    wanted = site.cue.affordance.mention_kind_for(RelationRole.SUBJECT)
    cutoff = byte_offset(text, site.role_start)
    best: TypedMention | None = None
    for mention in subjects:
        if mention.end_offset > cutoff:
            continue
        if wanted and mention.kind != wanted:
            continue
        if best is None or (mention.end_offset, mention.offset) > (
            best.end_offset,
            best.offset,
        ):
            best = mention
    return best


def _read_temporal(
    text: str, site: CueSite, subject: TypedMention
) -> tuple[TemporalHypothesis, list[CueSpan]]:
    """The temporal guess for one reading, and the span it was read from.

    A bare year is the only date this grammar reads, and it is read as a whole-year window
    because ``"in 2020"`` says something was true in 2020 and nothing about which day;
    ``semantics`` is the operator's declared mode, carried rather than inferred, as
    :class:`domain.relation_candidate.TemporalHypothesis` asks. The year is taken from
    after the object first, and from before the subject otherwise, so both ``"... in 2020"``
    and ``"In 2020, ..."`` read. With no year anywhere, the answer is
    :meth:`TemporalHypothesis.absent` and no span - never a raised error, and never a
    window borrowed from a document date nobody cited.
    """
    found = _YEAR.search(text, site.object_end)
    if found is None:
        limit = _char_index(text, subject.offset)
        for earlier in _YEAR.finditer(text, 0, limit):
            found = earlier
    if found is None:
        return TemporalHypothesis.absent(), []
    year = int(found.group(0))
    hypothesis = TemporalHypothesis.explicit(
        valid_from=datetime(year, 1, 1, tzinfo=UTC),
        valid_to=datetime(year, 12, 31, tzinfo=UTC),
        semantics=site.cue.temporal_semantics,
    )
    span = CueSpan(
        start=byte_offset(text, found.start()),
        end=byte_offset(text, found.end()),
        surface=found.group(0),
    )
    return hypothesis, [span]


def _span_of(mention: TypedMention, mention_ref: str) -> CueSpan:
    """The mention's surface as a span, carrying the id its participant is known by."""
    return CueSpan(
        start=mention.offset,
        end=mention.end_offset,
        surface=mention.value,
        mention_ref=mention_ref,
    )


def _fallback_ref(role: RelationRole, mention: TypedMention) -> str:
    """A positional, reproducible stand-in for a mention id the caller has not minted.

    Deliberately not a content address: nothing here may produce something that looks like
    a durable record id, because a caller that stored one would be storing a fiction.
    """
    return f"{role}:{mention.kind}:{mention.offset}-{mention.end_offset}"


def _char_index(text: str, byte_offset_value: int) -> int:
    """The character index of a UTF-8 byte offset - the inverse of ``byte_offset``.

    Needed to bound a text search by a mention whose offsets the extractors report in
    bytes. Exact for any offset :func:`extractors.util.byte_offset` produced, because such
    an offset always falls on a character boundary; a midpoint would raise rather than
    silently address the wrong character.
    """
    if byte_offset_value <= 0:
        return 0
    encoded = text.encode("utf-8")
    if byte_offset_value > len(encoded):
        raise ValueError(f"byte offset {byte_offset_value} is past the end of the text")
    return len(encoded[:byte_offset_value].decode("utf-8"))


def _dedup(mentions: list[TypedMention]) -> list[TypedMention]:
    """Deterministic dedup: keep the first mention per (offset, kind)."""
    seen: dict[tuple[int, str], TypedMention] = {}
    for mention in sorted(mentions, key=lambda m: (m.offset, m.kind, m.value)):
        key = (mention.offset, mention.kind)
        if key in seen:
            continue
        seen[key] = mention
    return [seen[key] for key in sorted(seen, key=lambda key: (seen[key].offset, seen[key].value))]
