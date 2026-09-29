"""The relation signal: what a producer saw, before anyone decided what it means.

Feature 019, T023 (FR-019, FR-020…FR-031, CD-6, CD-7).

The layer this module introduces sits below :mod:`extractors.relations` and above nothing.
A producer reads *some* observable structure - a cue phrase, a hyperlink, a table header,
a document's own metadata - and states a :class:`RelationSignal`. The signal says: here are
two things, here is the text or the structure that connects them, here is what I observed,
and here is how much of my surroundings I looked at. It does **not** say what the relation
is called, unless the producer genuinely knows, and it never says the relation holds.

**Why a signal is a separate object rather than a parameter of the candidate.** Three
reasons, each of which turned into a real defect without it:

* **A signal has no entity.** It names two *mentions* and a surface. Producers see
  mentions, because that is what is in the document; resolution happens later and may
  resolve neither of them. A producer that had to hand over a candidate would be tempted
  to resolve, and a producer that quietly resolved would be putting an identity decision
  inside extraction, where no audit trail exists.
* **A signal is not a candidate.** Several signals about the same pair are the normal case
  - a table header, a link, and a sentence in the prose all describing one relation - and
  collapsing them at production time loses the fact that there were three independent
  observations, which is the thing FR-034 counts.
* **A signal can name no relation type at all.** CD-6: a relation the platform's vocabulary
  has no entry for is a real relation, and the words that produced it are evidence. So
  :attr:`RelationSignal.relation_ref` is optional and :attr:`relation_surface` is not.

**A signal is bounded or it is not a producer.** :class:`Neighbourhood` is required, and it
records what the producer actually looked at - the character window, the row and column it
came from, the scope it read. This is the load-bearing honesty of the whole module: a
producer that scanned every pair of mentions in a document and reported the two that scored
highest has found something real, but a reader cannot tell it apart from a producer that
read the sentence containing the cue. FR-041…FR-043 make the neighbourhood a first-class
field for that reason, and :func:`assert_bounded` refuses a producer that leaves it out
rather than trusting a convention.

**Phase 4A made this natively n-ary, and made it say why it looked.** Three things were added
here in Phase 4A:

* :attr:`RelationSignal.participants` is now the canonical participant representation, variadic,
  ``MIN_PARTICIPANTS``…N. :attr:`subject_mention_ref` and :attr:`object_mention_ref` survive as
  **derived properties** over ``participants[0]`` and ``participants[1]``. Before this, a
  four-slot reading of ``John sold Acme to Microsoft in 2020`` kept two ends and dropped two with
  no trace, which is indistinguishable from a binary relation that never had more.
* :attr:`RelationSignal.basis` is the closed nine-member :class:`~domain.signal_basis.SignalBasis`,
  and it is what makes a **surface-less** signal legal. The old rule was
  ``relation_surface != '' OR relation_ref IS NOT NULL``, and it was a ceiling dressed as a
  floor: it forbade the one observation a co-mention producer legitimately makes. A signal that
  observed proximity and declined to name it is an honest observation; requiring words of it
  forced an invented word, a fabricated ``related_to``, or a silent drop, and the drop is the
  worst because an unrecorded adjacency and an unexamined one look identical afterwards.
* :attr:`RelationSignal.polarity` is a field, because :attr:`SignalKind.NEGATION` was a polarity
  masquerading as an observation channel. **Phase 4C deleted the member** (``FR-011``,
  ``FR-012``): "Acme did not acquire Beta" is a ``kind=SYNTAX`` signal with
  ``polarity=DENIED``, and a channel that denies beside a field that asserts is a record
  contradicting itself. :attr:`polarity` is now the only way to say it, and the one-line
  bridge that made the *member* overrule the *field* - the phase-4A arrangement, where
  ``kind=negation, polarity=asserted`` was resolved in the kind's favour and the overrule
  written into :attr:`notes` - is gone with it. Nothing is lost and nothing is silently
  reconciled, because there is now one place to disagree with yourself and it is the field
  that owns the question.

**Phase 4B finished the migration and deleted the second construction path.** All seven
un-migrated ``RelationSignal(...)`` sites moved onto ``participants=`` with a real ``basis`` and
a real ``polarity``, and the ``subject_mention_ref=`` / ``object_mention_ref=``
:class:`~dataclasses.InitVar` parameters were **removed in the same commit**. What is left is a
single way to build a signal and a derived reading of its first two ends, which is a different
thing: a reading cannot disagree with the tuple because it is computed from it. The reason this
could be one commit rather than two is the P4A phase split — the additions landed while the old
path still worked, and this phase migrated the callers and closed the door behind them.

What changed in the address, and why it was a defect: :meth:`RelationSignal._material` excluded
:attr:`extra`, which is where arity and role bindings lived, so two signals differing only in the
shape they declared collapsed onto one ``signal_id``. Declared shape is part of what was seen, so
:attr:`participants`, :attr:`basis` and :attr:`polarity` are in the material now.
:attr:`producer_ref` **stays**, and three docstrings in this module that claimed two producers
reading one structure share a ``signal_id`` were wrong: they do not, they are two observations,
which is precisely what FR-034 counts.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

from domain.predicate_hypothesis import PredicateHypothesis
from domain.predicate_signature import Polarity
from domain.relation_candidate import SpanRef
from domain.relation_participant import (
    MIN_PARTICIPANTS,
    ParticipantContractError,
    RelationParticipant,
)
from domain.signal_basis import SIGNAL_BASES_REQUIRING_PREDICATE_WORDS, SignalBasis
from domain.temporal_observation import TemporalAxis
from semantic.contracts import RelationRef

#: Prefix for a signal's content address, so a stored signal is recognisable by eye.
SIGNAL_ID_PREFIX = "SIG-"

#: The **only** value of :attr:`Neighbourhood.precision` that claims an exhaustive scan, and
#: named because Phase 4B changed :attr:`Neighbourhood.is_exhaustive` from a substring test to
#: an equality test against this. The substring was a live hazard rather than a tidiness
#: question: a producer writing ``precision="exact; exhaustive over the header row"`` would
#: have had its signals reported as exhaustive over the *document*, because the word appeared
#: somewhere in a sentence that was talking about something else. The table producer's
#: heuristic string came within one parenthetical of exactly that (FR-041…FR-043).
PRECISION_EXHAUSTIVE = "exhaustive"

#: The note a signal carries when it is **denied and the platform cannot name the predicate**.
#: Declared as a constant rather than written inline because :meth:`RelationSignal.__post_init__`
#: both tests for it and writes it, and a guard that searches for one string while writing a
#: second one is a guard that silently stops guarding. See the note in ``__post_init__`` for why
#: the append is conditional at all.
_DENIED_UNRESOLVED_NOTE = "denied, predicate unresolved"


class SignalKind(StrEnum):
    """The observable structure a producer read (FR-020).

    Closed, and the closure is the design. The old extension point was
    :data:`extractors.relations.RELATION_CUES` - a table of lexical cues - which meant the
    platform could express "a phrase connected these two words" and nothing else. Every
    other way a document states a relation was outside the vocabulary: a table's ``CEO``
    column, a hyperlink, an author line, a breadcrumb.

    Adding a *kind* is how the platform learns a new way of seeing. Adding a member here
    is therefore a real capability change and is reviewed as one, which is the point: the
    set of things the platform can notice is small, visible, and does not grow by
    accident.

    - :attr:`LEXICAL` - a cue phrase between two mentions in running text. The one kind
      018 implemented.
    - :attr:`SYNTAX` - a clause parsed into a structure: a construction, a head lemma and
      argument positions. **Added by the syntactic producer** (brief §29, data-model §6.1),
      and added as a *channel* for the same reason the others are: before it, a parsed frame
      had nowhere to live, so a producer that read grammar had to either fake being lexical
      or live outside the contract. It is not a substitute for :attr:`LEXICAL` and never
      folds into it - a cue phrase and a parse are different observations, and FR-034's
      independence count is computed over producers, so one name for both would make
      corroboration unreadable.
    - :attr:`STRUCTURAL` - non-linguistic document structure read **as structure** (brief
      §31): DOM parent/child, section membership, heading → content block, breadcrumb,
      caption → table, document → subsection. The signal carries the path it read rather than
      a flattened predicate, so ``<h2>Board of Directors</h2><div>John Smith</div>`` is a
      ``STRUCTURAL`` signal naming the two and declining to mint ``member_of_board``.
      **Added by Phase 4C** (``FR-011``; absent since 019).
    - :attr:`EVENT` - an n-ary event structure (brief §39): "John sold Acme to Microsoft in
      2020" is **one** observation with four participants, not two binary pairs. The
      decomposition is a later projection's decision under an explicit policy; the event
      structure is what was seen and it is never discarded to make the observation fit the
      substrate. **Added by Phase 4C** (``FR-011``).
    - :attr:`SEMANTIC` - a reading by an interpretation layer (brief §42): schema.org, JSON-LD,
      a mapping system, a domain vocabulary, a profile annotation - consumed to create
      **predicate/type interpretation candidates** and never to conclude that an ontology match
      makes something true. The channel names the *provenance of the reading*; it is not a
      licence. **Added by Phase 4C** (``FR-011``).
    - :attr:`TEMPORAL` - "this signal is based on a temporal observation" (brief §15). **A
      channel and never a container**: it states the provenance channel and carries no
      temporal payload and no time of its own. The facts live in
      :class:`~domain.temporal_observation.SourceTemporalObservation` and in the signal's
      :attr:`stated_axes`, which is the division that keeps this enum from becoming the
      unstructured dumping ground §15 forbids. **Kept, and the one member a phase may not
      "fix" by deleting** - ``ARBITRATION`` §4 is explicit and overrides the Phase-0
      instruction to leave it out. **Added to the enum by Phase 4C**; it had never been
      present, so "keep" and "add" are the same edit here.
    - :attr:`LINK` - a hyperlink whose anchor and target are the two ends.
    - :attr:`REFERENCE` - a named reference: a footnote marker, a citation, an
      ``as described in`` pointer, a ``see also``.
    - :attr:`TABLE` - a table whose header names one column and whose row supplies the
      other end.
    - :attr:`LIST` - a list whose items are the participants of one stated relation.
    - :attr:`METADATA` - a field the document states about itself: author, publisher,
      parent, path, domain.
    - :attr:`ATTRIBUTE` - a key/value pair, as in ``Role: CTO`` or a YAML front-matter
      block.
    - :attr:`HIERARCHY` - containment by position: a section inside a document, a row
      inside a table, a page inside a site.
    - :attr:`SCHEMA` - a typed slot: an RDF or JSON-LD property whose presence is the
      relation.
    - :attr:`CO_OCCURRENCE` - two mentions in the same sentence, window or block, with no
      cue between them. **A candidate kind, and the one most likely to be abused**: it is
      evidence of proximity and nothing else, and a signal of this kind with an empty
      :attr:`RelationSignal.relation_surface` and :attr:`RelationSignal.basis` of proximity says
      the platform noticed adjacency and declined to name it. That is the honest output, it is
      now constructible (FR-013), and naming it ``related_to`` would be a fabrication with a
      schema. What is still refused is a ``CO_OCCURRENCE`` that claims a *predicate-text* basis
      and supplies no words, because then it is not naming the adjacency either.

    **What Phase 4C removed, and where each of the three went.** A member naming an orthogonal
    aspect is a different question from a member naming an observation channel, so these were
    not channels and no producer ever emitted one - a measurement, not an assumption:
    :func:`rg 'SignalKind.(NEGATION|QUANTITY|COREFERENCE)' apps` reaches docstrings and two
    tests and no construction site. Their landing places were built in 4A and already existed:

    - :attr:`SignalKind.NEGATION` → :attr:`RelationSignal.polarity =
      :attr:`~domain.predicate_signature.Polarity.DENIED`. Read end to end by
      :func:`extractors.signals.syntactic.syntactic_signals`, which threads the parser's own
      polarity, so "John is not the CEO of Acme" is recorded as a denial rather than dropped or
      recorded as an acquisition.
    - :attr:`SignalKind.QUANTITY` →
      :attr:`RelationParticipant.argument_shape = "value"`, which is FR-012's stated mapping and
      the field :mod:`domain.relation_participant` was written to carry.
    - :attr:`SignalKind.COREFERENCE` → **no member**, by design: it was never a channel, it is
      "a reference relation between two mention refs" (FR-012), and the stage that decides two
      mentions are the same thing is coreference with a ``ResolutionDecisionRecord`` behind it.
      A producer below mention extraction has no such decision to make, and minting a kind for
      it would have been the fabrication it looks like.

    **An overlap Phase 4C records rather than resolves.** :attr:`STRUCTURAL` against
    :attr:`HIERARCHY`, and :attr:`SEMANTIC` against :attr:`SCHEMA`, are near-synonyms at this
    revision, and ``repair/A7-migration-021.md`` §5 disagreement 7 already registered that as
    "**my** definition, not the brief's, and needs the brief owner". FR-011's ``MUST`` is
    satisfied by the members being present; **which** of each pair a producer may file under is
    not decided here, because this phase does not have the authority to decide it and guessing
    would produce two names for one observation - the exact defect the closure above exists to
    prevent. Named, unresolved, and reported rather than silently split.
    """

    LEXICAL = "lexical"
    SYNTAX = "syntax"
    STRUCTURAL = "structural"
    EVENT = "event"
    SEMANTIC = "semantic"
    TEMPORAL = "temporal"
    LINK = "link"
    REFERENCE = "reference"
    TABLE = "table"
    LIST = "list"
    METADATA = "metadata"
    ATTRIBUTE = "attribute"
    HIERARCHY = "hierarchy"
    SCHEMA = "schema"
    CO_OCCURRENCE = "co_occurrence"


#: Every kind, for refusals that need to list the vocabulary and for iteration.
SIGNAL_KINDS: tuple[SignalKind, ...] = tuple(SignalKind)

#: The observational basis, re-exported rather than re-declared, so a producer that already
#: imports this module has the closed vocabulary of *why* it saw something in the same place
#: as the vocabulary of *what* it saw. The definition is
#: :class:`domain.signal_basis.SignalBasis`; brief §16 and FR-014 own the nine members.
SIGNAL_BASES: tuple[SignalBasis, ...] = tuple(SignalBasis)

#: The kinds whose signal describes a *structure* rather than a phrase. Used by the corpus
#: and the benchmarks to prove the path is not lexical-only (SC-F), and by anything that
#: wants to reason about what a producer could not have read.
#:
#: **Which of Phase 4C's four new members joined, and why only those two.** The view's subject
#: is *the document's own structure was the observation*, and :attr:`SignalKind.SYNTAX` is
#: already in it - a parsed frame counts - so :attr:`SignalKind.STRUCTURAL` (brief §31: DOM and
#: section structure) and :attr:`SignalKind.EVENT` (brief §39: a parsed n-ary frame) join on
#: the same footing. :attr:`SignalKind.SEMANTIC` and :attr:`SignalKind.TEMPORAL` do not: the
#: first is a reading taken *over* a schema or a mapping rather than off the document's
#: structure, and the second is a temporal channel whose facts live in
#: :class:`~domain.temporal_observation.SourceTemporalObservation`. Putting an interpretation
#: layer in a set whose name says "what the producer read off the page" would make the set
#: answer a different question from the one it declares, and the view is read by the corpus and
#: the benchmarks, so a wrong member is a wrong number rather than a wrong word.
STRUCTURAL_SIGNAL_KINDS: frozenset[SignalKind] = frozenset(
    {
        SignalKind.SYNTAX,
        SignalKind.STRUCTURAL,
        SignalKind.EVENT,
        SignalKind.LINK,
        SignalKind.REFERENCE,
        SignalKind.TABLE,
        SignalKind.LIST,
        SignalKind.METADATA,
        SignalKind.ATTRIBUTE,
        SignalKind.HIERARCHY,
        SignalKind.SCHEMA,
    }
)


class DirectionHypothesis(StrEnum):
    """Which end the producer believes is the subject, and how strongly (FR-024).

    Direction is a *hypothesis* because getting it backwards produces a claim that is
    confidently false, and the evidence for it is often thin: "Alice wrote the report"
    licenses ``Alice --wrote--> report`` and not its converse, but only because of the
    verb, and a table header gives no verb at all.

    The members are the honest answers, and the uncertainty is kept rather than resolved
    by picking a default:

    - :attr:`SUBJECT_TO_OBJECT` / :attr:`OBJECT_TO_SUBJECT` - the producer read a marker
      that orders the two, and says which way.
    - :attr:`UNDIRECTED` - the structure genuinely does not order them. A co-mention has no
      direction; asserting one would be a decision nobody made.
    - :attr:`AMBIGUOUS` - there is a marker and it could be read either way, and the
      producer is declining to choose.
    """

    SUBJECT_TO_OBJECT = "subject_to_object"
    OBJECT_TO_SUBJECT = "object_to_subject"
    UNDIRECTED = "undirected"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class Neighbourhood:
    """What the producer actually looked at, stated so a reader can judge the finding.

    Required on every signal, never defaulted (FR-041…FR-043). The three failures this
    prevents are all invisible in the output and fatal to the trust placed in it:

    * A producer that compared every pair of mentions in a document and reported the best
      is indistinguishable, in its output, from one that read the sentence containing a
      cue. The first has not found a relation; it has found the least implausible pair in a
      large space, and the size of that space is the whole story.
    * A producer that read a table's header row but not its data rows has read a *label*,
      not a value. ``precision`` says which.
    * A producer that read one row of a million-row table has a finding whose generality is
      one row. ``scope_read`` is where that is said out loud.

    The fields are deliberately concrete about *extent* rather than abstract about
    *effort*: :attr:`characters_scanned` and :attr:`pairs_considered` are numbers a reader
    can check against the document, because an unfalsifiable claim of boundedness is not
    boundedness.
    """

    characters_scanned: int
    pairs_considered: int
    scope_read: str
    precision: str = "exact"
    notes: str = ""

    def __post_init__(self) -> None:
        for name in ("characters_scanned", "pairs_considered"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise SignalContractError(
                    "neighbourhood_extent_type",
                    f"{name} must be a whole number a reader can check against the "
                    f"document, got {type(value).__name__}",
                )
            if value < 0:
                raise SignalContractError(
                    "neighbourhood_extent_negative",
                    f"{name} is {value}; a producer that read nothing has found nothing, "
                    "and that is stated by producing no signal rather than by a negative count",
                )
        if not str(self.scope_read).strip():
            raise SignalContractError(
                "neighbourhood_scope_required",
                "a neighbourhood must name what scope the producer read - a character "
                "window, a table row, a whole document. 'The document' is an answer; '' is "
                "not, and a signal whose extent is unstated cannot be weighed against one "
                "whose extent is",
            )
        object.__setattr__(self, "precision", str(self.precision or "exact"))
        object.__setattr__(self, "notes", str(self.notes or ""))

    @property
    def is_exhaustive(self) -> bool:
        """Whether this producer compared every pair in its scope.

        Named rather than inferred, because it is the fact a reader most needs and least
        often gets: an exhaustive producer's findings are *absence* claims as much as
        presence claims, and a reader who does not know which they are looking at will
        read a co-mention as a relation.

        **Equality against :data:`PRECISION_EXHAUSTIVE`, not a substring search.** The
        substring form was ``"exhaustive" in self.precision.lower()``, over a field whose
        documented use is a free sentence describing the extent - so any producer whose
        sentence *mentioned* exhaustiveness, including to deny it, published its findings
        as exhaustive absence claims. That is the one direction a heuristic error must never
        run: over-reporting absence invents the relations the producer says it looked for
        and did not find.
        """
        return self.precision.strip().lower() == PRECISION_EXHAUSTIVE

    def to_dict(self) -> dict[str, Any]:
        return {
            "characters_scanned": self.characters_scanned,
            "pairs_considered": self.pairs_considered,
            "scope_read": self.scope_read,
            "precision": self.precision,
            "notes": self.notes,
            "is_exhaustive": self.is_exhaustive,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Neighbourhood:
        return cls(
            characters_scanned=int(payload["characters_scanned"]),
            pairs_considered=int(payload["pairs_considered"]),
            scope_read=str(payload.get("scope_read", "")),
            precision=str(payload.get("precision", "exact")),
            notes=str(payload.get("notes", "")),
        )


class SignalContractError(ValueError):
    """A signal cannot be stated from these fields.

    A ``ValueError`` carrying a stable snake_case ``code``, matching
    :class:`domain.predicate_hypothesis.PredicateContractError` and the rest of the
    platform so one caller can switch on any of them.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


@dataclass(frozen=True)
class RelationSignal:
    """One observed connection between ``MIN_PARTICIPANTS`` or more mentions, and nothing more.

    Frozen and content-addressed: two observations of the same shape by the same producer
    produce the same id, and two that differ in any load-bearing way produce different ids and
    are not silently merged.

    **On the producer.** :attr:`producer_ref` is in the address, so two *different* producers
    reading one structure do **not** share a ``signal_id``, and must not. FR-034 counts
    independent *sources* and a reader is identified by who it is; collapsing two readers onto
    one address would have the platform report corroboration it does not have. The earlier
    version of this docstring said the opposite, and said it in the direction that looks like a
    safety feature. What *does* collapse onto one address is a repeat run of one producer over
    one structure — which is what :func:`dedupe_by_content` is for, and what the registry does.

    **What every field is for, and what none of them is for.** :attr:`participants` names
    mentions, never entities: this module has not resolved anything and cannot, because
    resolution is a later decision with its own record. :attr:`subject_mention_ref` and
    :attr:`object_mention_ref` are **derived** over the first two participants and are not a
    second source of truth (FR-008). :attr:`relation_ref` is optional and means "the producer
    knows the operator", not "the platform does" - a lexical producer that recognises a verb
    may set it, and a table-header producer must not. :attr:`predicate_hypothesis` carries the
    full reading including alternatives, so a producer that saw two defensible names says so
    here rather than picking one. :attr:`basis` answers "how do you know?", and
    :attr:`polarity` answers "is it denied?" - neither of which is an observation *channel*,
    which is why neither is :attr:`kind`.

    **There is no field for confidence in the relation holding.** Confidence belongs to a
    hypothesis assembled from *several* signals, and a single producer's certainty is not
    evidence about the world - it is evidence about the producer. :attr:`producer_confidence`
    is recorded separately and is named that way for exactly this reason.

    **Both construction paths are gone, and the derived reading survives.** Phase 4A added
    :attr:`participants` and kept ``subject_mention_ref=`` / ``object_mention_ref=`` as
    accepted constructor parameters for one phase, so that a phase which added a field could
    be committed green without migrating seven call sites in the same commit. Phase 4B
    migrated all seven and **deleted the parameters**, so there is no second way to build a
    signal. :attr:`subject_mention_ref` and :attr:`object_mention_ref` are still readable -
    they are :func:`_install_derived_endpoint_accessors`' properties over
    ``participants[0]`` and ``participants[1]`` - because they are a *reading* that every
    downstream consumer uses, and a reading is not a construction path.
    """

    kind: SignalKind
    relation_surface: str
    neighbourhood: Neighbourhood
    #: The canonical, variadic participant representation: ``MIN_PARTICIPANTS``..N, no fake
    #: binary decomposition (FR-008). **Required** as of Phase 4B, and required rather than
    #: defaulted because the default would be an empty tuple, and an empty tuple is not a
    #: legal signal - it is a signal that has not said what it connects, which is refused
    #: three checks later with ``signal_mentions_required``. Defaulting it would move the
    #: error from the constructor to a post-condition nobody reads.
    participants: tuple[RelationParticipant, ...]
    signal_id: str = ""

    relation_ref: RelationRef | None = None
    predicate_hypothesis: PredicateHypothesis | None = None
    direction: DirectionHypothesis = DirectionHypothesis.SUBJECT_TO_OBJECT
    producer_ref: str = ""
    producer_version: str = ""
    context_ref: str = ""
    semantic_regime_ref: str = ""
    capture_ref: str = ""
    trigger_span: SpanRef | None = None
    supporting_spans: tuple[SpanRef, ...] = ()
    stated_axes: tuple[TemporalAxis, ...] = ()
    producer_confidence: float = 0.0
    signal_ordinal: int = 0
    tenant_id: str = "default-tenant"
    notes: str = ""
    extra: Mapping[str, Any] = field(default_factory=dict)
    #: How this producer saw the connection, from the closed nine-member vocabulary
    #: (FR-014, brief §16). ``None`` means **the producer did not say**, and a signal that did
    #: not say and supplied no words is still refused under ``signal_asserts_nothing`` - the
    #: old invariant is narrowed, not deleted, and the narrowing is the one place a surface is
    #: still required (:data:`~domain.signal_basis.SIGNAL_BASES_REQUIRING_PREDICATE_WORDS`).
    basis: SignalBasis | None = None
    #: Whether the assertion stands or is denied. A field rather than a kind, because a kind
    #: answering "how did you see it" with an answer about *what was seen* is a different
    #: question (FR-015, FR-012). **Phase 4C closed that**: :attr:`SignalKind.NEGATION` is
    #: deleted, so this is the only place a signal can say it and there is no second way to say
    #: it that has to be overruled.
    #:
    #: Typed as the platform's existing
    #: :class:`domain.predicate_signature.Polarity` — three members — and **not** a new
    #: signal-local two-member copy. FR-015 requires the domain to be "closed and is
    #: ``Polarity.{ASSERTED, DENIED}`` — two members, not three", and that narrowing is
    #: **still outstanding and is not Phase 4C's to do**: ``domain/relation_candidate.py``
    #: carries :attr:`RelationCandidate.polarity` typed on the same enum and its own docstring
    #: says "``Polarity.UNCERTAIN`` is the explicit value for a held-open reading", and ``A2``'s
    #: band (FR-174…FR-178) owns that vocabulary. Reusing the enum rather than declaring a
    #: second one is what keeps the question visible instead of creating a second answer to it: a
    #: signal-local ``SignalPolarity`` with two members would have been clean-looking, would have
    #: passed every test here, and would have made the conflict invisible and unfixable. The
    #: member is accepted here and means "held open", matching the candidate.
    #:
    #: The axes FR-015 names as the right home for "held open" exist and are narrower —
    #: ``PredicateHypothesis.resolution_state`` for predicates and
    #: ``TypeHypothesis.hypothesis_state`` for types.
    polarity: Polarity = Polarity.ASSERTED

    def __post_init__(self) -> None:
        self._adopt_participants()
        object.__setattr__(self, "kind", SignalKind(self.kind))
        object.__setattr__(self, "direction", DirectionHypothesis(self.direction))
        object.__setattr__(self, "relation_surface", str(self.relation_surface or ""))
        object.__setattr__(self, "producer_ref", str(self.producer_ref or ""))
        object.__setattr__(self, "producer_version", str(self.producer_version or ""))
        object.__setattr__(self, "context_ref", str(self.context_ref or ""))
        object.__setattr__(self, "semantic_regime_ref", str(self.semantic_regime_ref or ""))
        object.__setattr__(self, "capture_ref", str(self.capture_ref or ""))
        object.__setattr__(self, "tenant_id", str(self.tenant_id or ""))
        object.__setattr__(self, "notes", str(self.notes or ""))
        object.__setattr__(
            self, "supporting_spans", tuple(self.supporting_spans or ())
        )
        object.__setattr__(
            self, "stated_axes", tuple(TemporalAxis(a) for a in (self.stated_axes or ()))
        )
        object.__setattr__(self, "signal_ordinal", int(self.signal_ordinal))
        object.__setattr__(self, "producer_confidence", float(self.producer_confidence))
        object.__setattr__(self, "extra", dict(self.extra or {}))
        self._adopt_basis()
        self._adopt_polarity()

        if not self.tenant_id:
            raise SignalContractError(
                "signal_tenant_required",
                "a signal must name its tenant; '' is not a tenant (constitution IV)",
            )
        self._require_something_asserted()

        if not isinstance(self.neighbourhood, Neighbourhood):
            raise SignalContractError(
                "signal_neighbourhood_required",
                "every signal states the neighbourhood it was read in (FR-041…FR-043). A "
                "producer that read a whole document and one that read a single sentence "
                "produce the same shape of output, and nothing downstream could tell them "
                "apart",
            )
        if not 0.0 <= self.producer_confidence <= 1.0:
            raise SignalContractError(
                "signal_confidence_range",
                f"producer_confidence is {self.producer_confidence}; it is a producer's "
                "certainty about its own reading, not a probability that the relation "
                "holds, and it must be a number in [0, 1]",
            )
        if self.relation_ref is not None and not isinstance(self.relation_ref, RelationRef):
            raise SignalContractError(
                "signal_relation_ref_type",
                "relation_ref must be a semantic.contracts.RelationRef naming an operator, "
                f"or None; got {type(self.relation_ref).__name__}. If the producer is "
                "reading an unresolved surface, put it in relation_surface and leave "
                "relation_ref None (CD-6)",
            )
        if self.predicate_hypothesis is not None and not isinstance(
            self.predicate_hypothesis, PredicateHypothesis
        ):
            raise SignalContractError(
                "signal_predicate_type",
                "predicate_hypothesis must be a PredicateHypothesis or None; got "
                f"{type(self.predicate_hypothesis).__name__}",
            )
        if self.predicate_hypothesis is None and (self.relation_surface or self.relation_ref):
            object.__setattr__(
                self,
                "predicate_hypothesis",
                PredicateHypothesis(
                    relation_ref=self.relation_ref, surface_form=self.relation_surface
                ),
            )
        # The note a *denial the platform cannot name* gets, re-keyed onto the field. The member
        # `SignalKind.NEGATION` is gone, so the old condition could not survive literally; the
        # fact it recorded is still true and still worth recording, and `polarity` is now the
        # only thing that can say a signal is denied - which makes it the correct and sufficient
        # trigger. Not a refusal: a denied relation the vocabulary cannot name is still a denied
        # relation, and the surface is what says so.
        #
        # **Appended at most once, and that is not a nicety.** The note is derived state folded
        # into a field the producer also owns, so an unconditional append is not idempotent:
        # `from_dict(signal.to_dict())` would build a *different* record from the one it was
        # given, which is FR-008's "build -> store -> read -> identical object" failing on a
        # field with no business changing. The old kind-keyed branch was accidentally safe only
        # because no producer emitted the kind; re-keying it onto a field producers *do* set
        # made the duplication reachable, and the guard is the fix rather than reverting the
        # re-key. `_DENIED_UNRESOLVED_NOTE` is a constant so the guard and the append cannot
        # drift into testing for one string and writing another.
        if (
            self.polarity is Polarity.DENIED
            and self.predicate_hypothesis is not None
            and self.predicate_hypothesis.resolution_state.value == "unknown"
            and _DENIED_UNRESOLVED_NOTE not in self.notes
        ):
            object.__setattr__(
                self, "notes", f"{self.notes} {_DENIED_UNRESOLVED_NOTE}".strip()
            )

        derived = self._derived_id()
        if self.signal_id and self.signal_id != derived:
            raise SignalContractError(
                "signal_id_mismatch",
                f"signal carries {self.signal_id!r} but its own content addresses to "
                f"{derived!r}; a content address is derived, never trusted",
            )
        object.__setattr__(self, "signal_id", derived)

    def _adopt_participants(self) -> None:
        """Adopt, coerce and check the canonical participant tuple.

        Four things happen, in this order, and the order is the argument for it:

        * **Blank tuple** is refused here with ``signal_mentions_required``. There is no
          second construction path any more, so an empty tuple has no interpretation but
          "this producer did not say what it connects" - and that is a refusal, not a
          default. Phase 4A defaulted it to ``()`` and reconciled a deprecated scalar pair
          into it; Phase 4B deleted those parameters, and with them the reason for the
          default.
        * **Coercion runs before any arity check**, and deliberately: a malformed participant
          must be refused *as a malformed participant*, by the type that owns it, rather
          than counted as a signal of the wrong shape. The ``blanks`` case in particular is
          unreachable here because :class:`RelationParticipant` raises
          ``participant_mention_required`` first - which is the right place for it, since
          "this end has no mention" is a statement about the participant and not about the
          signal's participant count.
        * **Arity below** :data:`MIN_PARTICIPANTS` is ``signal_arity_below_two``, A2's
          ``NO_CONFIGURATION``.
        * **One mention in two slots** is ``signal_self_connection``: a mention is not in a
          relation with itself, and two arguments of one clause that resolve to the same
          mention are a reading this producer should have refused.
        """
        declared = tuple(self.participants or ())
        if not declared:
            raise SignalContractError(
                "signal_mentions_required",
                "a signal connects at least two mentions and needs every reference: a "
                "producer sees surfaces, and a signal naming one end describes no "
                "connection at all. State participants=(...) with one member per end. The "
                "subject_mention_ref=/object_mention_ref= constructor parameters that used "
                "to be accepted here were removed in Phase 4B; the two names are still "
                "readable as derived properties over participants[0] and participants[1]",
            )

        object.__setattr__(
            self, "participants", tuple(RelationParticipant.coerce(p) for p in declared)
        )
        if len(self.participants) < MIN_PARTICIPANTS:
            raise SignalContractError(
                "signal_arity_below_two",
                f"a signal declares {len(self.participants)} participant"
                f"{'' if len(self.participants) == 1 else 's'}; a relational configuration "
                f"needs at least {MIN_PARTICIPANTS} ends. A one-argument clause states a "
                "property of one thing rather than a relation between two, and padding it to "
                f"{MIN_PARTICIPANTS} would invent the missing end. This is A2's "
                "NO_CONFIGURATION, and it is a decision rather than a gap: the parse was fine",
            )
        seen: dict[str, str] = {}
        for participant in self.participants:
            repeated = seen.setdefault(participant.mention_ref, participant.slot.token)
            if repeated != participant.slot.token:
                raise SignalContractError(
                    "signal_self_connection",
                    f"mention {participant.mention_ref!r} fills both {repeated} and "
                    f"{participant.slot.token}; a mention is not in a relation with itself, "
                    "and if the document says it is, that is a different kind of finding. Two "
                    "arguments of one clause that resolve to the same mention are a reading "
                    "this producer should have refused",
                )

    def _adopt_basis(self) -> None:
        """Coerce :attr:`basis` to the closed vocabulary, or refuse with the vocabulary in view.

        A free string is refused rather than accepted, because an unrecognised basis is a
        producer claiming a way of seeing that nobody can audit - and the whole value of the
        field is that "how do you know?" has a checkable answer.
        """
        if self.basis is None or isinstance(self.basis, SignalBasis):
            object.__setattr__(self, "basis", self.basis)
            return
        try:
            object.__setattr__(self, "basis", SignalBasis(self.basis))
        except ValueError as exc:
            raise SignalContractError(
                "signal_basis_unknown",
                f"{self.basis!r} is not an observational basis. The vocabulary is closed and "
                f"has {len(SIGNAL_BASES)} members: "
                f"{', '.join(b.value for b in SIGNAL_BASES)}. A new basis is an explicit "
                "extension with a version bump, not a free string (FR-014)",
            ) from exc

    def _adopt_polarity(self) -> None:
        """Coerce :attr:`polarity` to the platform enum, and nothing else.

        **The Phase-4A bridge is deleted.** For one phase this method also overrode an explicit
        ``polarity`` whenever the kind was :attr:`SignalKind.NEGATION`, wrote the overrule into
        :attr:`notes`, and made the *member* the authority over the *field*. That arrangement
        existed only because a signal could name its polarity twice; with the member gone
        (4C, ``FR-011``) there is nothing to reconcile, so the whole half of the method went
        with it rather than being kept as a no-op that a reader would have to work out.

        What is left is the check that still has teeth: a token nobody can read is refused with
        the vocabulary in view, because a free string here is a producer claiming a polarity
        that no reader can audit, and the whole value of the field is that "was this denied?"
        has a checkable answer.
        """
        try:
            polarity = Polarity(self.polarity)
        except ValueError as exc:
            raise SignalContractError(
                "signal_polarity_unknown",
                f"{self.polarity!r} is not a polarity; the domain is "
                f"{', '.join(p.value for p in Polarity)}. Polarity answers whether the "
                "assertion stands or is denied, which is a different question from the "
                "observation channel the kind names (FR-015)",
            ) from exc
        object.__setattr__(self, "polarity", polarity)

    def _require_something_asserted(self) -> None:
        """The narrowed ``signal_asserts_nothing``, and the one basis that still obliges words.

        Three grounds, and the third is the new one. A signal with a :attr:`basis` has said
        how it knows, which is the positive requirement brief §16 substitutes for the old
        invariant - so a proximity signal with no surface is now legal, because adjacency that
        was seen and not named is a real observation. A signal with **no** basis and no words is
        still refused: it is an unrecorded gap, not a co-occurrence. And a signal whose basis
        is :attr:`~domain.signal_basis.SignalBasis.PREDICATE_TEXT` with no words is refused
        too, because "I read the words" with nothing to show for it is the only claim in the
        vocabulary that is arithmetically impossible.
        """
        if self.relation_surface or self.relation_ref is not None:
            return
        if self.basis is not None:
            if self.basis in SIGNAL_BASES_REQUIRING_PREDICATE_WORDS:
                raise SignalContractError(
                    "signal_predicate_text_basis_requires_words",
                    f"this signal's basis is {self.basis.value!r} - the words between the "
                    "participants are the observation - and it supplies no relation_surface "
                    "and no relation_ref. A producer that read the words has to show them. "
                    "Every other basis can legitimately be observed without predicate words: "
                    "a table slot, a hyperlink, a citation, a metadata field, an event frame, "
                    "an attribute key, a DOM relation and proximity all are observed with "
                    "nothing between the ends",
                )
            return
        raise SignalContractError(
            "signal_asserts_nothing",
            f"a {self.kind.value} signal needs a relation_surface, a relation_ref, or a "
            "basis saying how it saw the connection: with none of the three it records that "
            "two mentions were near each other and declines to say why, which is an "
            "unrecorded gap rather than an honest one. If proximity is genuinely all that "
            "was seen, say so - kind=co_occurrence with basis=proximity and an empty surface "
            "is a legal signal and a better record than a fabricated 'related_to'",
        )

    def _material(self) -> dict[str, Any]:
        """The material the address is taken over.

        **What is in it, and why each addition had to be.** :attr:`producer_confidence` and
        :attr:`notes` are **excluded on purpose**, and the exclusion is the useful part: a
        producer that is slightly more sure of the same reading is not a second, independent
        observation, and letting confidence into the address would let one producer's
        uncertainty manufacture corroboration. The identity of a signal is what was seen, not
        how sure the reader was.

        :attr:`participants` is here because the *declared shape* is part of what was seen.
        Its absence was a live defect rather than an omission: :attr:`extra` is excluded from
        this dict, and :attr:`extra` is where arity and role bindings lived, so a four-slot
        reading and a two-slot reading of the same two mentions addressed to one
        ``signal_id`` - two records of different shapes, indistinguishable, with the extra two
        participants visible in one stored row and absent from the other's identity.
        :attr:`basis` is here because how a producer saw something is a fact about the
        observation, and two producers that saw the same ends by different means (a parsed
        frame and a table slot) are two observations, not one. :attr:`polarity` is here for
        the same reason and more sharply: "Acme did not acquire Beta" and "Acme acquired
        Beta" are opposite claims, and an address that could not tell them apart would be an
        address under which a denial and an assertion were the same row.

        :attr:`producer_ref` **stays**, and the three docstrings in this module that said two
        producers reading one structure share a ``signal_id`` were wrong. FR-034's independence
        count is a count of *sources*, and it is computed downstream over this address - so the
        producer has to be in it, or two readers of one page would arrive as one observation
        and the platform would report corroboration it does not have.

        :attr:`subject_mention_ref` and :attr:`object_mention_ref` are still written here, as a
        derived projection of ``participants[0]``/``participants[1]``. They are redundant
        rather than load-bearing - ``participants`` decides - and they are kept so the stored
        and serialised form keeps the shape every existing consumer reads, including the two
        binary columns that persist until 4C. They cannot disagree with the tuple, because
        :meth:`_adopt_participants` refuses a record where they do.

        The **declared arity is the length of ``participants``** and there is no separate
        ``arity`` key beside it. That is a considered omission rather than an oversight: a
        second key saying the same thing is a value that can disagree with the thing it
        summarises, and the one place it is useful to *say* it - the record a reader opens -
        is :meth:`to_dict`, which is wider than the address by design. An earlier version of
        this dict carried both, and the effect was that the mutation test
        ``test_dropping_participants_from_the_material_collapses_arity_and_is_caught`` could not
        reproduce the defect it was written to catch: with ``arity`` still in the material,
        removing ``participants`` left the two signals distinguishable and the mutation
        appeared to prove nothing. One source per fact, in the layer that needs it.
        """
        return {
            "tenant_id": self.tenant_id,
            "subject_mention_ref": self.subject_mention_ref,
            "object_mention_ref": self.object_mention_ref,
            "participants": [p.to_identity() for p in self.participants],
            "kind": str(self.kind),
            "relation_surface": self.relation_surface,
            "relation_ref": str(self.relation_ref) if self.relation_ref else "",
            "basis": str(self.basis) if self.basis else "",
            "polarity": str(self.polarity),
            "direction": str(self.direction),
            "producer_ref": self.producer_ref,
            "producer_version": self.producer_version,
            "context_ref": self.context_ref,
            "semantic_regime_ref": self.semantic_regime_ref,
            "capture_ref": self.capture_ref,
            "trigger_span": self.trigger_span.to_dict() if self.trigger_span else None,
            "supporting_spans": [s.to_dict() for s in self.supporting_spans],
            "stated_axes": [str(a) for a in self.stated_axes],
            "neighbourhood": self.neighbourhood.to_dict(),
        }

    def _derived_id(self) -> str:
        from domain.relation_identity import canonical_material, digest128

        return SIGNAL_ID_PREFIX + digest128(canonical_material(self._material()))

    @property
    def arity(self) -> int:
        """How many ends the producer declared.

        Named rather than inferred, because the two questions it is confused with have very
        different answers: a producer may have *read* four ends and declared two (its parser
        refused the other two), or declared four and had one unbindable. ``extra`` can record
        what was read; this is what was asserted.
        """
        return len(self.participants)

    @property
    def is_denied(self) -> bool:
        """Whether the document explicitly denied this, as opposed to not stating it.

        Not the negation of "stated": absence of evidence is :attr:`basis` and surface, and
        this is the one place the platform records that a document said *no*.
        """
        return self.polarity is Polarity.DENIED

    @property
    def is_structural(self) -> bool:
        """Whether this signal came from a structure rather than from prose."""
        return self.kind in STRUCTURAL_SIGNAL_KINDS

    @property
    def has_resolved_predicate(self) -> bool:
        """Whether the producer named an operator type."""
        return self.relation_ref is not None

    def with_id(self) -> RelationSignal:
        """A copy carrying its own content address, re-derived from the current contents.

        Returns a **new** signal rather than clearing the field in place. An earlier version
        did the latter - ``object.__setattr__(self, "signal_id", "")`` and return ``self`` -
        which is a genuine bug rather than a style choice: it destroyed the address of the
        record it was called on, so ``signal.with_id().signal_id`` was empty and a caller
        who reached for the method to *recompute* an address got its removal instead. A
        frozen dataclass whose ``with_id`` mutates is worse than one that has no such
        method, because the name promises the opposite of what it does.
        """
        return replace(self, signal_id="")

    def to_dict(self) -> dict[str, Any]:
        """The record projection: every field, and re-readable by :meth:`from_dict`.

        Deliberately **wider** than :meth:`_material`, and the two differ in exactly one place:
        ``participants`` here is the full projection, there it is the three-key identity
        projection. The record has to carry ``role_hypothesis``, ``confidence`` and
        ``argument_shape`` or a round trip would silently drop a producer's role guess and its
        reading of each end's shape - and FR-008's obligation is *build → store → read →
        identical object*, which a lossy record cannot satisfy however complete the address is.
        The address is derived from the identity projection on the way in and never from this
        one, so the extra evidence in the record cannot reach it.
        """
        return {
            **self._material(),
            "participants": [p.to_dict() for p in self.participants],
            # The declared shape, said outright for a reader opening the record rather than
            # counted off a list. Not in the address: see `_material`.
            "arity": self.arity,
            "signal_id": self.signal_id,
            "predicate_hypothesis": (
                self.predicate_hypothesis.content_key() if self.predicate_hypothesis else ""
            ),
            "producer_confidence": self.producer_confidence,
            "signal_ordinal": self.signal_ordinal,
            "notes": self.notes,
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> RelationSignal:
        """Rebuild from :meth:`to_dict`.

        ``participants`` is the only source of the ends. Phase 4A read the two deprecated
        scalars as a fallback for a record written by 019; Phase 4B removed them, so a
        payload that carries only ``subject_mention_ref``/``object_mention_ref`` and no
        ``participants`` is now **refused** with ``signal_mentions_required`` rather than
        quietly reconstructed. A 019-era stored row is a real thing and the migration that
        rewrites it into this shape is a real task; this reader declining to guess at it is
        the honest half of that answer, and guessing would be a record that looks migrated
        without having been.
        """
        ref = str(payload.get("relation_ref") or "")
        basis = payload.get("basis")
        participants = payload.get("participants")
        return cls(
            participants=tuple(RelationParticipant.coerce(p) for p in participants or ()),
            kind=SignalKind(str(payload["kind"])),
            relation_surface=str(payload.get("relation_surface", "")),
            neighbourhood=Neighbourhood.from_dict(payload["neighbourhood"]),
            relation_ref=RelationRef(ref) if ref else None,
            direction=DirectionHypothesis(str(payload.get("direction", "subject_to_object"))),
            producer_ref=str(payload.get("producer_ref", "")),
            producer_version=str(payload.get("producer_version", "")),
            context_ref=str(payload.get("context_ref", "")),
            semantic_regime_ref=str(payload.get("semantic_regime_ref", "")),
            capture_ref=str(payload.get("capture_ref", "")),
            stated_axes=tuple(TemporalAxis(a) for a in payload.get("stated_axes") or ()),
            producer_confidence=float(payload.get("producer_confidence", 0.0)),
            signal_ordinal=int(payload.get("signal_ordinal", 0)),
            tenant_id=str(payload.get("tenant_id", "default-tenant")),
            notes=str(payload.get("notes", "")),
            extra=dict(payload.get("extra") or {}),
            basis=SignalBasis(str(basis)) if basis else None,
            polarity=Polarity(str(payload.get("polarity", Polarity.ASSERTED))),
        )



def _install_derived_endpoint_accessors() -> None:
    """Attach the **derived** ``subject_mention_ref`` / ``object_mention_ref`` properties.

    Still a function, still called once immediately after the class body, and the reason is
    no longer the descriptor trap Phase 4A worked around: with the :class:`~dataclasses.
    InitVar` parameters gone, a ``@property`` of these names in the class body would simply
    be a property. It is attached here anyway for the one property that still has it.

    ``@dataclass`` resolves a field's default from the class attribute of the same name, and
    :attr:`RelationSignal.arity` and :attr:`RelationSignal.is_denied` are properties. Neither
    shares a name with a field, so neither is at risk - but the check that says so is the
    one this function enables, and
    ``test_no_derived_property_shadows_a_field_default`` is the test that runs it. The two
    endpoint names are *not* fields any more, so attaching these properties in the class body
    would be safe too; keeping them here means the whole class body can be diffed against
    Phase 4A and the only difference is a deletion, which is a smaller thing to review than a
    move.

    The properties are data descriptors on the class, so ``getattr`` finds them for instances
    and for :func:`dataclasses.replace`, and the names remain a projection over the tuple
    rather than a second source of truth.
    """
    RelationSignal.subject_mention_ref = property(  # type: ignore[assignment]
        lambda signal: signal.participants[0].mention_ref,
        doc=(
            "**DERIVED** over ``participants[0]``. Not a field and not a constructor\n"
            "parameter since Phase 4B; the reading survives and\n"
            "``participants[0].mention_ref`` is the canonical spelling.\n"
        ),
    )
    RelationSignal.object_mention_ref = property(  # type: ignore[assignment]
        lambda signal: signal.participants[1].mention_ref,
        doc=(
            "**DERIVED** over ``participants[1]``. Not a field and not a constructor\n"
            "parameter since Phase 4B. See :attr:`subject_mention_ref`.\n"
        ),
    )


_install_derived_endpoint_accessors()


def assert_bounded(signals: Iterable[RelationSignal], *, max_pairs_considered: int) -> None:
    """Refuse a batch whose producers each reported an unbounded scan.

    The check is per signal and against a stated ceiling, because the failure this guards
    against is a *producer* reaching too far, and averaging over a batch would let one
    exhaustive scan hide behind many cheap ones. FR-041…FR-043 make the neighbourhood
    load-bearing; this is what makes it more than a field to fill in.
    """
    for signal in signals:
        if signal.neighbourhood.pairs_considered > max_pairs_considered:
            producer = signal.producer_ref or "an unnamed producer"
            considered = signal.neighbourhood.pairs_considered
            raise SignalContractError(
                "signal_neighborhood_unbounded",
                f"signal {signal.signal_id} from {producer} considered {considered} pairs, "
                f"over the ceiling of {max_pairs_considered}. A producer that compares "
                "every pair in a large space has not found a relation; it has ranked "
                "proximity, and the ranking is not the finding. Narrow the scope and say "
                "so in the neighbourhood rather than emitting signals whose extent nobody "
                "can judge",
            )


def dedupe_by_content(signals: Iterable[RelationSignal]) -> tuple[RelationSignal, ...]:
    """Collapse signals that observed the same thing, keeping the first in input order.

    **What it actually collapses, corrected.** This docstring used to say that *two producers*
    reading the same structure produce the same :attr:`~RelationSignal.signal_id` and are one
    observation rather than two. That was wrong, and it was wrong in the direction that looks
    like a safety feature. :attr:`~RelationSignal.producer_ref` is in the address - it has to
    be, or FR-034's independence count is a count of readers rather than of sources - so two
    producers reading one page arrive as two addresses and are correctly two observations.
    What collapses here is **one producer reading one structure twice**: the same
    :func:`~extractors.signals.protocol.run_producer` pass over a document that repeats
    itself, two runs of one extractor, a corpus fixture replayed. Those are one finding
    reported twice, and counting them twice is corroboration the platform did not observe.

    Order is preserved rather than sorted so a caller that cares which producer was seen first
    still can, and the discarded signals are the caller's to keep through the surviving one's
    ``extra`` if it wants to: this function's job is to answer "how many distinct things were
    seen", not to keep a log.
    """
    unique: dict[str, RelationSignal] = {}
    for signal in signals:
        unique.setdefault(signal.signal_id, signal)
    return tuple(unique.values())


__all__ = [
    "PRECISION_EXHAUSTIVE",
    "SIGNAL_BASES",
    "SIGNAL_ID_PREFIX",
    "SIGNAL_KINDS",
    "STRUCTURAL_SIGNAL_KINDS",
    "DirectionHypothesis",
    "Neighbourhood",
    "ParticipantContractError",
    "RelationParticipant",
    "RelationSignal",
    "SignalBasis",
    "SignalContractError",
    "SignalKind",
    "assert_bounded",
    "dedupe_by_content",
]
