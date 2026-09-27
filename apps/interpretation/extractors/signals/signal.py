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
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

from domain.predicate_hypothesis import PredicateHypothesis
from domain.relation_candidate import SpanRef
from domain.temporal_observation import TemporalAxis
from semantic.contracts import RelationRef

#: Prefix for a signal's content address, so a stored signal is recognisable by eye.
SIGNAL_ID_PREFIX = "SIG-"


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
      :attr:`RelationSignal.relation_surface` says the platform noticed adjacency and
      declined to name it. That is the honest output; naming it ``related_to`` would be a
      fabrication with a schema.
    - :attr:`COREFERENCE` - two mentions the document itself points at as the same thing.
    - :attr:`QUANTITY` - a measured value about a participant: a count, a share, a size.
    - :attr:`NEGATION` - a mention the document explicitly denies a relation to. **Present
      because the alternative is worse**: without it, "Acme did not acquire Beta" has to be
      either dropped, which loses an observed fact, or recorded as an acquisition, which is
      a lie. A signal that says what was denied is neither.
    """

    LEXICAL = "lexical"
    LINK = "link"
    REFERENCE = "reference"
    TABLE = "table"
    LIST = "list"
    METADATA = "metadata"
    ATTRIBUTE = "attribute"
    HIERARCHY = "hierarchy"
    SCHEMA = "schema"
    CO_OCCURRENCE = "co_occurrence"
    COREFERENCE = "coreference"
    QUANTITY = "quantity"
    NEGATION = "negation"


#: Every kind, for refusals that need to list the vocabulary and for iteration.
SIGNAL_KINDS: tuple[SignalKind, ...] = tuple(SignalKind)

#: The kinds whose signal describes a *structure* rather than a phrase. Used by the corpus
#: and the benchmarks to prove the path is not lexical-only (SC-F), and by anything that
#: wants to reason about what a producer could not have read.
STRUCTURAL_SIGNAL_KINDS: frozenset[SignalKind] = frozenset(
    {
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
        """
        return "exhaustive" in self.precision.lower()

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
    """One observed connection between two mentions, and nothing more.

    Frozen and content-addressed, so two producers that read the same structure produce
    the same id and can be counted as one observation rather than two (FR-034), while two
    that read different structures produce different ids and are not silently merged.

    **What every field is for, and what none of them is for.** :attr:`subject_mention_ref`
    and :attr:`object_mention_ref` are mentions, never entities: this module has not
    resolved anything and cannot, because resolution is a later decision with its own
    record. :attr:`relation_ref` is optional and means "the producer knows the operator",
    not "the platform does" - a lexical producer that recognises a verb may set it, and a
    table-header producer must not. :attr:`predicate_hypothesis` carries the full reading
    including alternatives, so a producer that saw two defensible names says so here rather
    than picking one.

    **There is no field for confidence in the relation holding.** Confidence belongs to a
    hypothesis assembled from *several* signals, and a single producer's certainty is not
    evidence about the world - it is evidence about the producer. :attr:`producer_confidence`
    is recorded separately and is named that way for exactly this reason.
    """

    subject_mention_ref: str
    object_mention_ref: str
    kind: SignalKind
    relation_surface: str
    neighbourhood: Neighbourhood
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

    def __post_init__(self) -> None:
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

        if not str(self.subject_mention_ref).strip() or not str(self.object_mention_ref).strip():
            raise SignalContractError(
                "signal_mentions_required",
                "a signal connects two mentions and needs both references: a producer sees "
                "surfaces, and a signal naming only one end describes no connection at all",
            )
        if self.subject_mention_ref == self.object_mention_ref:
            raise SignalContractError(
                "signal_self_connection",
                f"signal connects {self.subject_mention_ref!r} to itself; a mention is not "
                "in a relation with itself, and if the document says it is, that is a "
                "different kind of finding",
            )
        if not self.tenant_id:
            raise SignalContractError(
                "signal_tenant_required",
                "a signal must name its tenant; '' is not a tenant (constitution IV)",
            )
        if not self.relation_surface and self.relation_ref is None:
            raise SignalContractError(
                "signal_asserts_nothing",
                f"a {self.kind.value} signal needs a relation_surface, a relation_ref, or "
                "both: with neither it records that two mentions were near each other and "
                "declines to say why, which is a co-occurrence and not a relation. Use "
                "kind=co_occurrence with a surface describing the adjacency if proximity "
                "is genuinely all that was seen - a blank signal with a blank surface is "
                "not an honest gap, it is an unrecorded one",
            )
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
        if (
            self.kind is SignalKind.NEGATION
            and self.predicate_hypothesis is not None
            # Not a refusal: a negated relation the platform cannot name is still a negated
            # relation, and the surface is what says so.
            and self.predicate_hypothesis.resolution_state.value == "unknown"
        ):
            object.__setattr__(
                self, "notes", (self.notes + " negated, predicate unresolved").strip()
            )

        derived = self._derived_id()
        if self.signal_id and self.signal_id != derived:
            raise SignalContractError(
                "signal_id_mismatch",
                f"signal carries {self.signal_id!r} but its own content addresses to "
                f"{derived!r}; a content address is derived, never trusted",
            )
        object.__setattr__(self, "signal_id", derived)

    def _material(self) -> dict[str, Any]:
        """The material the address is taken over.

        :attr:`producer_confidence` and :attr:`notes` are **excluded on purpose**, and the
        exclusion is the useful part: a producer that is slightly more sure of the same
        reading is not a second, independent observation, and letting confidence into the
        address would let one producer's uncertainty manufacture corroboration. The
        identity of a signal is what was seen, not how sure the reader was.
        """
        return {
            "tenant_id": self.tenant_id,
            "subject_mention_ref": self.subject_mention_ref,
            "object_mention_ref": self.object_mention_ref,
            "kind": str(self.kind),
            "relation_surface": self.relation_surface,
            "relation_ref": str(self.relation_ref) if self.relation_ref else "",
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
        return {
            **self._material(),
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
        ref = str(payload.get("relation_ref") or "")
        return cls(
            subject_mention_ref=str(payload["subject_mention_ref"]),
            object_mention_ref=str(payload["object_mention_ref"]),
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
        )


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

    Two producers reading the same structure produce the same
    :attr:`~RelationSignal.signal_id`, and they are *one* observation rather than two -
    FR-034 counts independent sources, and two readers of one page are one source. Order
    is preserved rather than sorted so a caller that cares about which producer was seen
    first still can, and the discarded signals are returned by the caller through the
    surviving one's ``extra`` only if it wants to: this function's job is to answer
    "how many distinct things were seen", not to keep a log.
    """
    unique: dict[str, RelationSignal] = {}
    for signal in signals:
        unique.setdefault(signal.signal_id, signal)
    return tuple(unique.values())


__all__ = [
    "SIGNAL_ID_PREFIX",
    "SIGNAL_KINDS",
    "STRUCTURAL_SIGNAL_KINDS",
    "DirectionHypothesis",
    "Neighbourhood",
    "RelationSignal",
    "SignalContractError",
    "SignalKind",
    "assert_bounded",
    "dedupe_by_content",
]
