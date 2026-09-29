"""The one extraction contract every relation producer implements.

Feature 019, T024 (FR-022, FR-023).

There is exactly one way to be a relation producer, and :class:`RelationSignalExtractor`
is it. That is the whole point of the module, and the point is negative: the platform's
previous extension point was :data:`extractors.relations.RELATION_CUES`, a table of lexical
cues, so a producer was something you added a *row* to, and every producer that was not
lexical had to either fake being lexical or live outside the contract where nothing could
check it. A table of phrases is not a way of stating a capability.

**What the contract guarantees, and why each clause is there.**

* :meth:`~RelationSignalExtractor.extract` is the only required method, and it returns
  signals. A producer that raised would turn one malformed document into a failed batch; a
  producer that returned ``None`` would be indistinguishable from one that found nothing.
  So the return is always a tuple, possibly empty, and emptiness is an answer.
* :meth:`~RelationSignalExtractor.declares` is required and is *about the producer*, not
  about the world: what it reads, what it cannot read, and what it refuses to conclude.
  :attr:`~ProducerDeclaration.cannot_read` is the half that matters and the half a producer
  is most tempted to leave empty. "I cannot tell a job title from a place name" is
  information; "" is indistinguishable from "I have not thought about it", and the two
  lead to different behaviour when a document says something ambiguous.
* :meth:`~RelationSignalExtractor.budget` states the pair ceiling the producer works under,
  so :func:`~extractors.signals.signal.assert_bounded` has something to check a signal
  against rather than a convention to assume.
* **No producer may write a :class:`~domain.relation_candidate.CandidateStatus`, resolve a
  mention, or emit a :class:`~domain.relation_claim.RelationClaim`.** Not as a style
  preference - as the reason the contract returns signals. The first would put admission
  inside extraction; the second would put identity resolution inside extraction, where no
  audit trail exists; the third would make extraction the producer of assertions. A
  producer that did any of them would be a producer whose output could not be re-derived
  from the evidence, which is the property everything else here exists to protect.

**Why the producer states its own version and ref.** FR-034 counts independent sources,
and "independent" is a claim about *who spoke*, not about what was said. Two producers
sharing a ``producer_ref`` are one source however differently they read the page, and a
producer with no ref cannot be counted at all - so the field is required, and the
assembler's independence count is only as good as it is.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from domain.signal_basis import SignalBasis

from extractors.signals.signal import (
    Neighbourhood,
    RelationSignal,
    SignalContractError,
    SignalKind,
    assert_bounded,
    dedupe_by_content,
)


@dataclass(frozen=True)
class ProducerDeclaration:
    """What one producer reads, and what it declines to conclude.

    Read as the honest limits of one instrument, which is the thing a caller most needs
    before deciding how much to trust what comes back. :attr:`cannot_read` is the field
    that earns the others: a producer that says "I cannot distinguish a role from a place"
    can be trusted *on the cases where it succeeded*, because it has told you what its
    silence means. One that says nothing has told you nothing, and its silence is
    indistinguishable from never having looked.
    """

    producer_ref: str
    producer_version: str
    kinds: tuple[SignalKind, ...]
    #: The observable structures this producer reads, in prose. Required and non-empty:
    #: a producer nobody can describe is a producer nobody can evaluate.
    reads: str
    #: What this producer cannot tell apart, in prose. Required and allowed to be a
    #: considered "nothing in my scope is ambiguous" - but it must be a *statement*, and
    #: the difference between a statement and a blank is the difference between a known
    #: limit and an unexamined one.
    cannot_read: str
    #: The pair ceiling this producer works under, per document. Required: FR-041…FR-043
    #: make a producer's extent load-bearing, and a ceiling nobody stated is a ceiling
    #: nobody checked.
    max_pairs_considered: int
    #: How this producer's observations map onto independence for FR-034. Two producers
    #: sharing a family are one source.
    independence_family: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        for name in ("producer_ref", "producer_version", "reads", "cannot_read"):
            if not str(getattr(self, name)).strip():
                raise SignalContractError(
                    "producer_declaration_incomplete",
                    f"{name} is empty on a producer declaration for "
                    f"{self.producer_ref or '<unnamed>'}. A declaration exists so a caller "
                    "can judge a producer's silence, and a blank field is silence of the "
                    "second kind: unexamined rather than absent",
                )
        if not self.kinds:
            raise SignalContractError(
                "producer_kinds_required",
                f"producer {self.producer_ref!r} declares no signal kinds, so a reader "
                "cannot tell whether its output is empty because the document said nothing "
                "or because the producer looks for nothing",
            )
        if self.max_pairs_considered < 1:
            raise SignalContractError(
                "producer_budget_required",
                f"producer {self.producer_ref!r} declares a pair ceiling of "
                f"{self.max_pairs_considered}. A producer that compares no pairs reads "
                "nothing; if that is genuinely the case, emit no signals and declare no "
                "kinds rather than declaring a budget of zero",
            )
        object.__setattr__(self, "kinds", tuple(SignalKind(k) for k in self.kinds))
        object.__setattr__(self, "independence_family", str(self.independence_family or ""))
        object.__setattr__(self, "notes", str(self.notes or ""))

    def to_dict(self) -> dict[str, Any]:
        return {
            "producer_ref": self.producer_ref,
            "producer_version": self.producer_version,
            "kinds": [str(k) for k in self.kinds],
            "reads": self.reads,
            "cannot_read": self.cannot_read,
            "max_pairs_considered": self.max_pairs_considered,
            "independence_family": self.independence_family,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ExtractionScope:
    """What one extraction call is being run over.

    The tenant, the frame and the regime are *required and keyword-only*, and that is the
    whole reason they are here rather than defaulted. A signal without a
    :attr:`context_ref` cannot say what frame of the document it was read in; without a
    :attr:`semantic_regime_ref` it cannot say which instruments interpreted it. Both are
    somebody else's decisions, and a default in this layer would be a silent substitution
    of one reader's judgement for another's (FR-015, FR-016).

    :attr:`document_ref` is the retrieval the signals come from, so every signal a
    producer emits can be traced to bytes somebody actually obtained (I-3).
    """

    tenant_id: str
    context_ref: str
    semantic_regime_ref: str
    document_ref: str = ""
    investigation_id: str = ""
    recorded_by: str = ""
    #: Producer-specific labels a producer may need and this contract does not model -
    #: a page number, a sheet name, a table id. Carried opaquely so the contract does not
    #: grow a column per producer, which is how a shared contract becomes one producer's
    #: schema.
    labels: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("tenant_id", "context_ref", "semantic_regime_ref"):
            if not str(getattr(self, name)).strip():
                raise SignalContractError(
                    "extraction_scope_reference_required",
                    f"{name} is required and cannot be defaulted: a frame and a regime are "
                    "decisions somebody else made, and inventing one here would put this "
                    "producer's judgement into the record in their place (FR-015, FR-016)",
                )
        object.__setattr__(self, "document_ref", str(self.document_ref or ""))
        object.__setattr__(self, "investigation_id", str(self.investigation_id or ""))
        object.__setattr__(self, "recorded_by", str(self.recorded_by or ""))
        object.__setattr__(self, "labels", dict(self.labels or {}))

    def with_document(self, document_ref: str) -> ExtractionScope:
        """A copy bound to one retrieval, for a producer iterating several documents."""
        return ExtractionScope(
            tenant_id=self.tenant_id,
            context_ref=self.context_ref,
            semantic_regime_ref=self.semantic_regime_ref,
            document_ref=document_ref,
            investigation_id=self.investigation_id,
            recorded_by=self.recorded_by,
            labels=self.labels,
        )


@runtime_checkable
class RelationSignalExtractor(Protocol):
    """One contract for every relation producer (FR-022).

    Structural, so a producer is not forced to inherit a base class and is not forced to
    implement a method it has no use for. The three required members are the ones without
    which a producer's output cannot be judged: what it read, what it cannot tell, and
    what it produced.

    Producers are *not* required to implement
    :meth:`~extractors.signals.signal.dedupe_by_content` or
    :func:`~extractors.signals.signal.assert_bounded`; those are module functions a
    registry calls, and a producer that re-implemented them would be re-implementing them
    wrongly.
    """

    def declares(self) -> ProducerDeclaration:
        """What this producer reads and what it declines to conclude."""
        ...

    def extract(self, record: object, *, scope: ExtractionScope) -> tuple[RelationSignal, ...]:
        """Every relation signal this producer finds in ``record``.

        Returns a tuple, always. An empty tuple means *this producer found nothing in this
        record*, which is an answer a caller can act on; raising would make one malformed
        document a failed batch, and returning ``None`` would be indistinguishable from a
        producer that had not run.

        A signal must be bounded by
        :attr:`ProducerDeclaration.max_pairs_considered` and must carry a
        :class:`~extractors.signals.signal.Neighbourhood` saying what it read. Neither is
        checked here, because a producer is not the right place to police itself -
        :func:`~extractors.signals.signal.assert_bounded` is called by the registry on the
        way out, so a producer that lies about its extent is caught rather than trusted.
        """
        ...


def run_producer(
    producer: RelationSignalExtractor,
    records: Iterable[object],
    *,
    scope: ExtractionScope,
) -> tuple[RelationSignal, ...]:
    """Drive one producer over records, and hold it to its own declaration.

    The single place a producer's output is checked, rather than a check each producer
    remembers to perform. Three things happen here and nowhere else:

    * **The extent is checked against the declared ceiling** with
      :func:`~extractors.signals.signal.assert_bounded`. A producer that reached further
      than it declared is refused at the boundary rather than allowed to fill the database
      with signals whose extent no reader could judge.
    * **Duplicate observations are collapsed** with
      :func:`~extractors.signals.signal.dedupe_by_content`, because two runs of one
      producer over one structure are one observation and FR-034 counts observations.
* **The producer's identity is stamped on every signal**, so a signal cannot arrive
  with no ``producer_ref`` and become uncountable for independence. A producer that set
  its own ref is overwritten, because the registry is the authority on who is speaking
  - a producer that could name itself ``independent-source-7`` would otherwise be able
  to manufacture corroboration, which is the same forgery as letting confidence into
  a signal's address.
* **A signal that arrives with no :attr:`~extractors.signals.signal.RelationSignal.basis`
  is refused**, unless its producer's declaration admits exactly one basis - see
  :func:`_stamp`. A basis answers "how do you know?" and only the producer knows; the
  registry can name what a signal *failed* to say, which is the useful half of the
  job, and it does that with a code rather than a default.

    Failures are not swallowed. A producer that raises propagates: silently dropping one
    producer's output would make "no relations here" and "this producer crashed" the same
    observation, and that is the one confusion a substrate for evidence cannot afford.
    """
    declaration = producer.declares()
    found: list[RelationSignal] = []
    for record in records:
        found.extend(producer.extract(record, scope=scope))
    assert_bounded(found, max_pairs_considered=declaration.max_pairs_considered)
    stamped = tuple(
        _stamp(signal, declaration, scope) for signal in found
    )
    return dedupe_by_content(stamped)


def _stamp(
    signal: RelationSignal,
    declaration: ProducerDeclaration,
    scope: ExtractionScope,
) -> RelationSignal:
    """Overwrite the fields the registry owns, and **carry the two the producer must not
    lose**.

    The producer owns what it *saw*; the registry owns *who spoke* and *in what frame*.
    Splitting them this way is what keeps a producer from being able to assert its own
    independence or read outside the frame it was given.

    **Why ``basis`` and ``polarity`` are re-stamped rather than merely re-addressed.** Before
    Phase 4B this function was:

    .. code-block:: python

        return _replace(signal, signal_id="", **changes)

    which re-derives the address and **loses nothing** - ``basis`` and ``polarity`` are in
    the address material, so they survive a ``replace``. The loss was different and worse:
    a producer that emitted a signal with ``basis=None`` and ``polarity=ASSERTED`` (the two
    defaults, so a producer written before Phase 4A could not get them wrong) had its output
    stamped by a registry that knew, from the producer's own declaration, exactly how the
    producer saw things - and did nothing about it. The registry is the authority on who is
    speaking; the declaration is the authority on what that speaker reads; and a declared
    basis of ``None`` is a declaration that says nothing, so there was nothing to restate.

    What is restated now is narrower and real: a signal that reached the registry with **no
    basis at all** is stamped with the *single* basis its producer's declaration implies,
    and is **refused** if the producer reads more than one kind of structure. The refusal
    matters more than the fill: a producer that reads cue phrases *and* proximity is
    genuinely two producers, and papering over that with a default is how FR-034's
    independence count gets corrupted. A signal that reached the registry with a basis is
    left alone, because a producer that stated its basis and a registry that overrode it
    would be a record disagreeing with itself.

    ``polarity`` is **never** restated. It is a claim about the document - "this was denied"
    - and no registry can know it. A producer that reads a negator states
    ``polarity=Polarity.DENIED`` on the signal and that is the one authority on the question;
    anything else here would be the registry guessing. Phase 4C deleted
    ``SignalKind.NEGATION``, so there is no second place a producer could have said it and no
    overrule this layer has to perform.
    """
    from dataclasses import replace as _replace

    changes: dict[str, Any] = {
        "producer_ref": declaration.producer_ref,
        "producer_version": declaration.producer_version,
        "tenant_id": scope.tenant_id,
        "context_ref": scope.context_ref,
        "semantic_regime_ref": scope.semantic_regime_ref,
        "capture_ref": scope.document_ref,
    }
    if signal.kind not in declaration.kinds:
        raise SignalContractError(
            "producer_kind_not_declared",
            f"producer {declaration.producer_ref!r} declared kinds "
            f"{[str(k) for k in declaration.kinds]} but emitted a {signal.kind.value} "
            "signal. A producer that emits a kind it did not declare is either two "
            "producers wearing one name - which corrupts FR-034's independence count - or "
            "a declaration nobody maintains",
        )
    if signal.basis is None:
        implied = _implied_bases(declaration)
        if len(implied) == 1:
            changes["basis"] = next(iter(implied))
        else:
            raise SignalContractError(
                "producer_basis_undeclared",
                f"signal {signal.signal_id} from {declaration.producer_ref!r} carries no "
                f"basis, and the kinds it declared ({[str(k) for k in declaration.kinds]}) "
                f"do not imply exactly one observational basis ({sorted(str(b) for b in implied) or 'none'}). "
                "A basis answers 'how do you know?' and it has to be stated by the producer "
                "that knows: a registry cannot infer one from a signal kind, because "
                "'a table slot' and 'an attribute key' are both reached by reading markup and "
                "only the producer knows which it did. Fill basis= on the signal, or narrow "
                "the declaration so the two agree (FR-014)",
            )
    if signal.tenant_id and signal.tenant_id != scope.tenant_id:
        raise SignalContractError(
            "signal_tenant_mismatch",
            f"producer {declaration.producer_ref!r} was run for tenant "
            f"{scope.tenant_id!r} and emitted a signal belonging to {signal.tenant_id!r}; "
            "cross-tenant output is refused fail-closed (constitution IV)",
        )
    return _replace(signal, signal_id="", **changes)


#: Which observational basis each declared :class:`~extractors.signals.signal.SignalKind`
#: implies, and **not** a decision the registry acts on - the registry *refuses* whenever this
#: maps to anything other than exactly one basis, which is every multi-kind producer here.
#:
#: It exists so the refusal can *name* what it found rather than say "some basis", and so
#: the single-kind case has one authority rather than a chain of ``if``s. A kind that maps to
#: nothing (``CO_OCCURRENCE``, and the three of Phase 4C's additions below) is genuinely
#: ambiguous, and the registry's answer to an ambiguous kind is the refusal above rather than
#: a guess: proximity is the usual basis for a co-mention but the kind does not say so, and
#: the platform does not get to decide it on the producer's behalf.
#:
#: **Which of 4C's four new members are mapped, and why only :attr:`SignalKind.EVENT`.** A
#: ``STRUCTURAL`` signal (brief §31) is reached by reading markup, and ``dom_relation``,
#: ``table_slot``, ``hyperlink``, ``citation``, ``metadata_field`` and ``attribute_key`` are
#: all reachable that way - six answers, so a single entry would be a fabrication. A
#: ``SEMANTIC`` signal (brief §42) reads a schema, a mapping system or a profile and never the
#: words between two mentions, so ``predicate_text`` is wrong and so is everything else. A
#: ``TEMPORAL`` signal states the channel and its facts live in
#: :class:`~domain.temporal_observation.SourceTemporalObservation`, so the basis is whatever
#: produced the observation rather than anything the kind implies. Only ``EVENT`` (brief §39)
#: is one thing read one way, and it is the same frame ``SYNTAX`` already names, so it maps to
#: the same basis. All three unmapped kinds are therefore refused when a producer declares them
#: and states no basis, which is the fail-closed answer and the one a reader can act on.
_IMPLIED_BASIS: Mapping[SignalKind, frozenset[SignalBasis]] = MappingProxyType(
    {
        SignalKind.LEXICAL: frozenset({SignalBasis.PREDICATE_TEXT}),
        SignalKind.SYNTAX: frozenset({SignalBasis.EVENT_FRAME}),
        SignalKind.EVENT: frozenset({SignalBasis.EVENT_FRAME}),
        SignalKind.LINK: frozenset({SignalBasis.HYPERLINK}),
        SignalKind.REFERENCE: frozenset({SignalBasis.CITATION}),
        SignalKind.TABLE: frozenset({SignalBasis.TABLE_SLOT}),
        SignalKind.LIST: frozenset({SignalBasis.ATTRIBUTE_KEY}),
        SignalKind.ATTRIBUTE: frozenset({SignalBasis.ATTRIBUTE_KEY}),
        SignalKind.METADATA: frozenset({SignalBasis.METADATA_FIELD}),
        SignalKind.SCHEMA: frozenset({SignalBasis.ATTRIBUTE_KEY}),
        SignalKind.HIERARCHY: frozenset({SignalBasis.METADATA_FIELD}),
    }
)


def _implied_bases(declaration: ProducerDeclaration) -> frozenset[SignalBasis]:
    """Every basis the declared kinds jointly admit, which is all of them jointly."""
    implied: set[SignalBasis] = set()
    for kind in declaration.kinds:
        implied |= _IMPLIED_BASIS.get(kind, frozenset())
    return frozenset(implied)


def synthesise_neighbourhood(
    *,
    characters_scanned: int,
    pairs_considered: int,
    scope_read: str,
    precision: str = "exact",
) -> Neighbourhood:
    """Build a :class:`~extractors.signals.signal.Neighbourhood` for a producer.

    A convenience rather than a shortcut, and it exists so that constructing one is a
    single obvious call in every producer instead of a four-field literal each of them
    might fill in differently. It adds no defaults: all four quantities must be stated, so
    a producer cannot reach for it and inherit a zero.
    """
    return Neighbourhood(
        characters_scanned=characters_scanned,
        pairs_considered=pairs_considered,
        scope_read=scope_read,
        precision=precision,
    )


__all__ = [
    "ExtractionScope",
    "ProducerDeclaration",
    "RelationSignalExtractor",
    "run_producer",
    "synthesise_neighbourhood",
]
