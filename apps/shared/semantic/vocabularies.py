"""SKOS-style controlled vocabularies that never encode concept equality.

Feature 017, FR-008 / T015. A :class:`ConceptScheme` is a retrieval accelerator: it
gives a surface form somewhere to resolve to, and it gives hierarchy
(``broader``/``narrower``) and association (``related``) that a query can widen along. It
is deliberately *not* a type system, and this module is deliberately not an ontology
(spec scope guard): no reasoner, no class hierarchy with inherited properties, no
admission gate.

**No equality, anywhere.** This module never asserts that one concept *is* another, and
there is no ``equivalent_to`` / ``same_as`` field, link or helper with which to express
one. The closest thing present is :attr:`Concept.exact_match`, and it means something
strictly weaker: it records that *some mapping process, recorded elsewhere* (the
SSSOM-style mapping set, FR-009) asserted an alignment between two concepts in two
vocabularies. ``exactMatch`` is therefore a **mapping assertion carrying provenance,
justification and a version, re-evaluable and withdrawable** - not a type identity. The
fact that it is a field on ``Concept`` must not be read as this module making the claim;
this module only *holds* it, and the honest provenance of an alignment always lives in
the mapping set that produced it.

Hierarchy is ``skos:broader``: ``PublicCompany`` is a kind of ``Company`` being a kind of
``Organization``, and walking that chain is what lets a query recall more while the
concepts stay distinct the whole way up (SC-6). Nothing here collapses them, and only a
recorded mapping set may ever bridge two vocabularies - never inference.

Three further properties are load-bearing:

* **Ambiguity is information.** :meth:`ConceptScheme.resolve_surface_form` returns
  *every* concept a surface form reaches, canonically ordered. Silently taking the first
  would turn a fact about the vocabulary ("this string is two things here") into a coin
  flip, and the caller could never tell it happened.
* **Symmetry is derived, not demanded.** ``narrower`` is the inverse of ``broader``, so
  a producer states whichever direction it happens to hold and
  :meth:`ConceptScheme.children` / :meth:`ConceptScheme.parents` return the completed
  pair. ``related`` is completed to a symmetric relation and deliberately *not* completed
  transitively: a platform that invents links to tidy up a vocabulary is a platform that
  can no longer distinguish what was recorded from what it derived.
* **Unknown resolves to nothing, quietly.** A term the scheme does not contain yields an
  empty result and a :attr:`~semantic.contracts.SemanticRef.UNRESOLVED` reference. It
  never raises and never guesses, because a term no vocabulary has heard of is
  admissible content, not an error (FR-001).

Transitivity is intentionally absent here. :meth:`ConceptScheme.parents` and
:meth:`ConceptScheme.children` are the direct, single-hop links; walking them is the job
of :mod:`semantic.expansion`, which makes that decision per operation instead of baking
it into the vocabulary (FR-008).
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from types import MappingProxyType

from semantic.contracts import SemanticRef, content_key

__all__ = [
    "Concept",
    "ConceptMatch",
    "ConceptScheme",
    "MatchPredicate",
    "Resolution",
    "normalize_surface_form",
    "normalize_type_ref",
]


def normalize_surface_form(value: str) -> str:
    """Canonical form of a human surface form, for matching only.

    The transform is NFKC, a Unicode-aware camel-case word split, ``_`` and ``-`` read as
    spaces, case folding, and whitespace collapse. It exists so that ``ПАО``, ``пао``,
    ``public_company`` and ``Public Company`` all reach the same index bucket instead of
    requiring a hand-maintained synonym list.

    Two things it deliberately does not do. It makes no judgement about what the form
    *means* - it is a string normalisation, never a type inference. And because
    normalisation can merge genuinely distinct labels (``AB`` and ``A B``), a merged lookup
    returns *all* concepts sharing the key rather than picking one: the collision is
    reported as ambiguity, which is the honest answer.

    Camel splitting is a deterministic string heuristic, not a linguistic claim, and it is
    Unicode-aware because schemes are multilingual. The single rule: a space goes before an
    upper-case character that is immediately followed by a lower-case one, because that is
    where a new word starts. It handles ``PublicCompany`` and ``HTTPServer`` alike, and
    leaves all-caps forms such as ``ПАО`` untouched. A form that genuinely mixes case
    mid-word (``eMail``) still splits, so schemes that care carry the literal form as an
    alternative label - the cost of a heuristic is always a documented edge case, and
    reporting both concepts for a key is the safe way to be wrong.
    """
    text = unicodedata.normalize("NFKC", "" if value is None else str(value))
    pieces: list[str] = []
    for index, char in enumerate(text):
        if index and char.isupper() and text[index + 1 : index + 2].islower():
            pieces.append(" ")
        pieces.append(char)
    folded = "".join(pieces).casefold()
    return " ".join(folded.replace("_", " ").replace("-", " ").split())


def normalize_type_ref(value: str) -> str:
    """Canonical form of a type/identifier reference, for matching only.

    NFKC and whitespace trim, but case is **preserved**: a reference is an opaque
    identifier, and ``schema:Person`` and ``schema:person`` are different references. The
    platform has no standing to decide they are the same - deciding that two references
    denote one thing is a mapping assertion, and mappings are recorded, not inferred.
    """
    if value is None:
        return ""
    return unicodedata.normalize("NFKC", str(value)).strip()


def _sorted_refs(values: Iterable[str]) -> tuple[str, ...]:
    """A link set: de-duplicated, blank-free, canonically ordered.

    Sorting is what makes a concept content-addressable and order-insensitive
    (constitution VI): two producers stating the same links in different orders produce the
    same object and the same ``content_key``. A blank reference is a missing link, not a
    link to the empty string, so it is dropped rather than stored.
    """
    if isinstance(values, str):
        values = (values,)
    return tuple(sorted({str(value).strip() for value in values if str(value).strip()}))


class MatchPredicate(StrEnum):
    """Cross-vocabulary match predicates, and the *weakest* thing this module asserts.

    These name a relationship asserted **by a recorded mapping set** (FR-009) between a
    concept here and a concept in some other vocabulary. They are not derived from
    hierarchy, not derived from label similarity, and not derived from this module at all.

    Read them with their provenance in mind. ``EXACT_MATCH`` says a mapping process claimed
    the two concepts align; it does **not** say the platform treats them as one type, and it
    certainly does not license collapsing them. Re-evaluating or withdrawing the mapping is
    expected and leaves both concepts exactly where they were. ``BROAD_MATCH`` and
    ``NARROW_MATCH`` are weaker still - the target is wider or narrower than the source -
    and honouring them widens recall rather than recording identity.
    """

    EXACT_MATCH = "exact_match"
    CLOSE_MATCH = "close_match"
    BROAD_MATCH = "broad_match"
    NARROW_MATCH = "narrow_match"


@dataclass(frozen=True)
class ConceptMatch:
    """One cross-vocabulary match link: a target reference plus the predicate claimed.

    ``target_ref`` is an opaque reference in *another* vocabulary. Nothing in this module
    imports, resolves or validates it; that is the mapping set's business. And the honest
    answer to "are these two the same?" is always "the mapping set says so, here is its
    provenance" - never "yes, therefore merge them".
    """

    concept_id: str
    predicate: MatchPredicate
    target_ref: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "concept_id", str(self.concept_id))
        object.__setattr__(self, "predicate", MatchPredicate(self.predicate))
        object.__setattr__(self, "target_ref", str(self.target_ref))

    def as_reference(self) -> str:
        """Render as ``<predicate>:<target>`` so a log line carries the claim, not a verdict."""
        return f"{self.predicate}:{self.target_ref}"


#: Fields holding reference sets, de-duplicated and canonically ordered on construction.
_LINK_FIELDS = (
    "alt_labels",
    "notation",
    "broader",
    "narrower",
    "related",
    "exact_match",
    "close_match",
    "broad_match",
    "narrow_match",
)

_MATCH_FIELDS: dict[MatchPredicate, str] = {
    MatchPredicate.EXACT_MATCH: "exact_match",
    MatchPredicate.CLOSE_MATCH: "close_match",
    MatchPredicate.BROAD_MATCH: "broad_match",
    MatchPredicate.NARROW_MATCH: "narrow_match",
}


@dataclass(frozen=True)
class Concept:
    """One concept in one scheme: a label, a place in a hierarchy, and some links.

    A concept is a *vocabulary* object, not a type, and the difference is load-bearing. A
    type is something a record is asserted to be, and asserting one creates a
    :class:`~semantic.contracts.TypeAssertion` carrying evidence. A concept is something a
    record is *compared against* during a query, which asserts nothing about the record. So
    this class carries no status, no evidence and no entity, and a concept existing has no
    effect on any record anywhere.

    ``broader`` and ``narrower`` are two spellings of one relation and either may be left
    empty - :class:`ConceptScheme` completes the other from what other concepts declared.
    ``related`` is unordered association. The four ``*_match`` fields hold references in
    *other* vocabularies; see :class:`MatchPredicate` for what they do and emphatically do
    not claim. There is no field here able to express "these two concepts are equal", and
    that omission is the point (FR-008).
    """

    concept_id: str
    scheme_id: str = ""
    pref_label: str = ""
    alt_labels: tuple[str, ...] = ()
    notation: tuple[str, ...] = ()
    broader: tuple[str, ...] = ()
    narrower: tuple[str, ...] = ()
    related: tuple[str, ...] = ()
    exact_match: tuple[str, ...] = ()
    close_match: tuple[str, ...] = ()
    broad_match: tuple[str, ...] = ()
    narrow_match: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "concept_id", str(self.concept_id).strip())
        object.__setattr__(self, "scheme_id", str(self.scheme_id).strip())
        object.__setattr__(self, "pref_label", str(self.pref_label).strip())
        for name in _LINK_FIELDS:
            object.__setattr__(self, name, _sorted_refs(getattr(self, name)))

    @property
    def labels(self) -> tuple[str, ...]:
        """Surface forms for display: ``pref_label`` first, then alt labels, then notation.

        The ordering is fixed and meaningful - a caller rendering a pick-list must show the
        preferred label first - while a caller *matching* must not rely on it at all, because
        :func:`normalize_surface_form` makes matching order-independent.
        """
        forms = [self.pref_label, *self.alt_labels, *self.notation]
        seen: set[str] = set()
        ordered: list[str] = []
        for form in forms:
            if form and form not in seen:
                seen.add(form)
                ordered.append(form)
        return tuple(ordered)

    @property
    def surface_keys(self) -> tuple[str, ...]:
        """Every normalised form this concept is findable by, including its own id.

        Including ``concept_id`` is deliberate: a caller holding ``schema:Person`` from
        upstream has every right to look it up by that reference without knowing it is also
        labelled "Person".
        """
        keys: set[str] = set()
        for form in (self.concept_id, *self.labels):
            key = normalize_surface_form(form)
            if key:
                keys.add(key)
        return tuple(sorted(keys))

    @property
    def match_predicates(self) -> tuple[ConceptMatch, ...]:
        """Every cross-vocabulary match this concept records, canonically ordered."""
        matches = [
            ConceptMatch(self.concept_id, predicate, target)
            for predicate, field_name in _MATCH_FIELDS.items()
            for target in getattr(self, field_name)
        ]
        return tuple(sorted(matches, key=lambda match: (str(match.predicate), match.target_ref)))

    def matches(self, predicate: MatchPredicate | None = None) -> tuple[ConceptMatch, ...]:
        """Match links, optionally filtered to one predicate. Never an identity claim."""
        wanted = MatchPredicate(predicate) if predicate is not None else None
        links = self.match_predicates
        return tuple(link for link in links if wanted is None or link.predicate is wanted)

    def in_hierarchy(self) -> bool:
        """True when the concept declares any typed link at all.

        A cheap pre-check before an expansion: a leaf has nothing to expand into, so saying
        so up front avoids reporting a truncated closure that was never going to widen
        anything.
        """
        return bool(self.broader or self.narrower or self.related)

    def content_key(self) -> str:
        """Order-insensitive identity of the concept as declared.

        Reuses the feature 016/017 canonical-JSON convention rather than inventing a second
        hashing dialect, so a concept is compared across stores the way a relation already
        is.
        """
        return content_key(
            {
                "concept": self.concept_id,
                "scheme": self.scheme_id,
                "pref_label": self.pref_label,
                "alt_labels": list(self.alt_labels),
                "notation": list(self.notation),
                "broader": list(self.broader),
                "narrower": list(self.narrower),
                "related": list(self.related),
                "exact_match": list(self.exact_match),
                "close_match": list(self.close_match),
                "broad_match": list(self.broad_match),
                "narrow_match": list(self.narrow_match),
            }
        )


@dataclass(frozen=True)
class Resolution:
    """The outcome of resolving one surface form against a scheme.

    ``semantic_ref`` is :attr:`SemanticRef.SKOS` when at least one concept was reached and
    :attr:`SemanticRef.UNRESOLVED` when none was - the two states a caller actually has to
    tell apart. ``concepts`` may hold more than one entry and that is not an error: it is
    the honest report, and :attr:`is_ambiguous` lets a caller decide whether its question
    tolerates ambiguity. Resolving nothing never raises (FR-001).
    """

    surface_form: str
    concepts: tuple[Concept, ...] = ()
    scheme_id: str = ""
    semantic_ref: SemanticRef = SemanticRef.UNRESOLVED

    def __post_init__(self) -> None:
        object.__setattr__(self, "surface_form", str(self.surface_form))
        object.__setattr__(self, "concepts", tuple(self.concepts))
        object.__setattr__(self, "scheme_id", str(self.scheme_id))
        object.__setattr__(self, "semantic_ref", SemanticRef(self.semantic_ref))

    @property
    def is_resolved(self) -> bool:
        return bool(self.concepts)

    @property
    def is_ambiguous(self) -> bool:
        """True when one surface form reached several concepts - information, not a defect."""
        return len(self.concepts) > 1

    def concept_ids(self) -> tuple[str, ...]:
        return tuple(concept.concept_id for concept in self.concepts)


def _freeze_index(index: Mapping[str, set[str]]) -> Mapping[str, tuple[str, ...]]:
    """Freeze a derived link index into an immutable, canonically ordered view."""
    return MappingProxyType({key: tuple(sorted(value)) for key, value in sorted(index.items())})


@dataclass(frozen=True)
class ConceptScheme:
    """An immutable registry of :class:`Concept` objects with derived lookup indexes.

    Frozen and value-semantic: :meth:`register` and :meth:`extend` return a *new* scheme
    rather than mutating this one, so a scheme handed to two callers cannot change under
    either of them and a scheme can be shared as the immutable thing it is meant to be.

    Concepts are stored canonically ordered by ``concept_id``, which makes two schemes built
    from the same concepts in different orders the *same* value: they compare equal and share
    a ``content_key`` (constitution VI - the same input always yields the same output,
    whatever order it arrived in).

    The scheme is a *hint* surface, never a gate. A concept it does not contain is not a
    concept that cannot exist, and every lookup for an unknown reference returns an empty
    result instead of raising, so a caller can bring its own vocabulary to the table without
    permission (FR-001, FR-002).

    Derived indexes are built once in ``__post_init__`` and stored as private attributes:
    ``_parents`` and ``_children`` (mutually inverse, so ``narrower`` is always derivable
    from ``broader`` and the producer never has to state both), ``_related`` (symmetrically
    completed) and ``_surface_index`` (normalised surface form to concept ids). Keeping them
    derived rather than stored is what stops the two directions of one relation from ever
    disagreeing with each other.

    Two construction-time invariants raise :class:`ValueError`, both because they are caller
    bugs that would silently corrupt lookups rather than content the platform should
    tolerate: a repeated ``concept_id``, and a concept naming a *different* scheme than the
    one being built. A concept that names no scheme is adopted by this one.
    """

    scheme_id: str
    concepts: tuple[Concept, ...] = ()
    version: str = "1"

    def __post_init__(self) -> None:
        scheme_id = str(self.scheme_id).strip()
        by_id: dict[str, Concept] = {}
        for concept in self.concepts:
            bound = _bind_to_scheme(concept, scheme_id)
            if bound.concept_id in by_id:
                raise ValueError(
                    f"scheme {scheme_id!r}: duplicate concept id {bound.concept_id!r}"
                )
            by_id[bound.concept_id] = bound
        ordered = tuple(by_id[concept_id] for concept_id in sorted(by_id))

        parents: dict[str, set[str]] = {c.concept_id: set(c.broader) for c in ordered}
        children: dict[str, set[str]] = {c.concept_id: set(c.narrower) for c in ordered}
        related: dict[str, set[str]] = {c.concept_id: set(c.related) for c in ordered}
        for concept in ordered:
            for parent in concept.broader:
                children.setdefault(parent, set()).add(concept.concept_id)
            for child in concept.narrower:
                parents.setdefault(concept.concept_id, set()).add(child)
            for peer in concept.related:
                related.setdefault(peer, set()).add(concept.concept_id)

        surface_index: dict[str, set[str]] = {}
        for concept in ordered:
            for key in concept.surface_keys:
                surface_index.setdefault(key, set()).add(concept.concept_id)

        object.__setattr__(self, "scheme_id", scheme_id)
        object.__setattr__(self, "version", str(self.version))
        object.__setattr__(self, "concepts", ordered)
        object.__setattr__(self, "_by_id", MappingProxyType(by_id))
        object.__setattr__(self, "_parents", _freeze_index(parents))
        object.__setattr__(self, "_children", _freeze_index(children))
        object.__setattr__(self, "_related", _freeze_index(related))
        object.__setattr__(
            self,
            "_surface_index",
            MappingProxyType(
                {key: frozenset(ids) for key, ids in sorted(surface_index.items())}
            ),
        )

    @classmethod
    def from_concepts(
        cls, scheme_id: str, concepts: Iterable[Concept], version: str = "1"
    ) -> ConceptScheme:
        """Build a scheme in one pass - prefer this over repeated :meth:`register`."""
        return cls(scheme_id, tuple(concepts), version)

    @property
    def concept_ids(self) -> tuple[str, ...]:
        return tuple(concept.concept_id for concept in self.concepts)

    def __len__(self) -> int:
        return len(self.concepts)

    def __iter__(self) -> Iterator[Concept]:
        return iter(self.concepts)

    def __contains__(self, concept_id: object) -> bool:
        return str(concept_id) in self._by_id

    def __repr__(self) -> str:
        return f"ConceptScheme(scheme_id={self.scheme_id!r}, concepts={len(self)})"

    def register(self, concept: Concept) -> ConceptScheme:
        """A new scheme with ``concept`` added. The scheme received is untouched."""
        if concept.concept_id in self._by_id:
            raise ValueError(
                f"scheme {self.scheme_id!r}: duplicate concept id {concept.concept_id!r}"
            )
        return ConceptScheme(self.scheme_id, (*self.concepts, concept), self.version)

    def extend(self, concepts: Iterable[Concept]) -> ConceptScheme:
        """A new scheme with several concepts added at once.

        One rebuild rather than one per concept, so importing a vocabulary stays linear in
        its size instead of quadratic.
        """
        return ConceptScheme(self.scheme_id, (*self.concepts, *concepts), self.version)

    def get(self, concept_id: str) -> Concept | None:
        """The concept, or ``None``. An unknown reference is a normal answer, not an error."""
        return self._by_id.get(str(concept_id).strip())

    def has(self, concept_id: str) -> bool:
        return str(concept_id).strip() in self._by_id

    def resolve_surface_form(self, surface_form: str) -> tuple[Concept, ...]:
        """Every concept this surface form reaches, canonically ordered by ``concept_id``.

        Returns all matches, never a single pick, and returns ``()`` for a term the scheme
        does not contain. Both behaviours are deliberate: collapsing ambiguity hides a real
        property of the vocabulary, and raising on an unknown term would make a lookup double
        as an admission gate (FR-001, FR-008).

        Matching runs through :func:`normalize_surface_form`, so it is case-, width-, camel-
        and underscore-insensitive but otherwise exact. It is *surface* matching: a form that
        looks like a concept reaches it for comparison, which asserts nothing whatsoever
        about the record that supplied the form.
        """
        key = normalize_surface_form(surface_form)
        if not key:
            return ()
        return tuple(self._by_id[cid] for cid in sorted(self._surface_index.get(key, ())))

    def resolve(self, surface_form: str) -> Resolution:
        """:meth:`resolve_surface_form` plus the resolved/unresolved state a caller branches on."""
        concepts = self.resolve_surface_form(surface_form)
        return Resolution(
            surface_form=str(surface_form),
            concepts=concepts,
            scheme_id=self.scheme_id,
            semantic_ref=SemanticRef.SKOS if concepts else SemanticRef.UNRESOLVED,
        )

    def parents(self, concept_id: str) -> tuple[str, ...]:
        """Direct ``broader`` links, completed from what other concepts declared as ``narrower``.

        Single hop by design - transitivity is :mod:`semantic.expansion`'s per-operation
        decision, not a property of the vocabulary. An unknown or unregistered
        ``concept_id`` yields ``()``.
        """
        return self._parents.get(str(concept_id).strip(), ())

    def children(self, concept_id: str) -> tuple[str, ...]:
        """Direct ``narrower`` links, completed from what other concepts declared as ``broader``.

        This is what lets a producer state only ``broader`` on the child it owns and still get
        a usable ``children`` query for free. An unknown or unregistered ``concept_id`` yields
        ``()``.
        """
        return self._children.get(str(concept_id).strip(), ())

    def related(self, concept_id: str) -> tuple[str, ...]:
        """``related`` links, completed to a symmetric relation.

        Symmetric because ``skos:related`` is unordered, so a one-sided declaration is a
        statement about a pair. Deliberately *not* completed transitively: inferring "related
        to a thing related to" manufactures association nobody recorded, and association is
        exactly the sort of claim that quietly becomes a fact downstream.
        """
        return self._related.get(str(concept_id).strip(), ())

    def get_aliases(self, concept_id: str) -> tuple[str, ...]:
        """Preferred label, alt labels and notation for one concept; ``()`` if unknown.

        Preferred label first because callers render these; the remainder is canonically
        ordered so the result is stable across calls, processes and runs.
        """
        concept = self.get(concept_id)
        return concept.labels if concept is not None else ()

    def matches(
        self, concept_id: str, predicate: MatchPredicate | None = None
    ) -> tuple[ConceptMatch, ...]:
        """Cross-vocabulary match links recorded *by a mapping set*, for one concept.

        Every one of these is a claim some external process made, and none of them is this
        module deciding anything. A concept the scheme does not know has no recorded matches
        here, which is not evidence that it has none anywhere.
        """
        concept = self.get(concept_id)
        return concept.matches(predicate) if concept is not None else ()

    def content_key(self) -> str:
        """Order-insensitive identity of the whole scheme, usable as a vocabulary version.

        Two schemes holding the same concepts in different orders share this digest, which is
        what makes "the vocabulary changed" a decidable question instead of a guess.
        """
        return content_key(
            {
                "scheme": self.scheme_id,
                "version": self.version,
                "concepts": {
                    concept_id: self._by_id[concept_id].content_key()
                    for concept_id in sorted(self._by_id)
                },
            }
        )


def _bind_to_scheme(concept: Concept, scheme_id: str) -> Concept:
    """Attach a concept to the scheme that is registering it."""
    if concept.scheme_id and concept.scheme_id != scheme_id:
        raise ValueError(
            f"concept {concept.concept_id!r} belongs to scheme "
            f"{concept.scheme_id!r}, not {scheme_id!r}"
        )
    if concept.scheme_id == scheme_id:
        return concept
    return replace(concept, scheme_id=scheme_id)
