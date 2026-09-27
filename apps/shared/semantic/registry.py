"""Semantic access as a façade, so no caller can tell which vocabulary answered.

Feature 017, FR-015 / T024, US8, SC-7. This module is the *only* way external vocabulary
access is reached. :class:`SemanticRegistry` exposes six operations - ``resolve_term()``,
``get_aliases()``, ``parents()``, ``children()``, ``related()`` and ``mappings()`` - and
behind them may sit any number of backends: a local SKOS scheme, an OBO import, an SSSOM
mapping set, a remote OAK endpoint. A caller written against this module keeps working when
the backend underneath is replaced, and that is the entire claim: the interface is the
contract and a backend is an implementation detail of it. :class:`SemanticBackend` is that
interface, and a backend that does not implement all six capabilities is refused when it is
registered - never at call time, where it would surface as a question the caller cannot answer.

**The interface is uniform, including where it is empty.** A term no backend has heard of
returns exactly the object a backend returns when it resolved to nothing:
:class:`~semantic.vocabularies.Resolution` with ``concepts=()`` and
``semantic_ref=SemanticRef.UNRESOLVED``, plus five empty tuples. Nothing raises for a
legitimately unknown term, because a concept nobody has heard of is admissible content in an
open world rather than an error (FR-001) - and a lookup that raised on an unknown term would
quietly become the admission gate this feature exists to remove (FR-002). A backend that is
not installed therefore behaves exactly like a backend holding no data: the answer is
"unresolved", never an exception and never a different type. That is what makes the façade
backend-agnostic in practice rather than only on paper.

**Identity is never merged, and no method here is capable of merging it.** There is no
``canonical_type()``, no ``best_mapping()``, no ``resolve_to_one()``, and nothing that could
serve as one. :meth:`~SemanticRegistry.resolve_term` returns a *tuple* of concepts, so
ambiguity is representable and a single answer is not; :meth:`~SemanticRegistry.parents` and
its siblings return reference sets, which are hierarchy and association and never identity;
and :meth:`~SemanticRegistry.mappings` returns recorded
:class:`~semantic.mappings.SemanticMapping` claims, each still carrying its predicate,
justification, source and version, so the strongest of them means only that *some* mapping
process claimed alignment. The vocabulary layer's own ``*_match`` links are deliberately not
surfaced as mappings by a scheme backend: those are claims without an audit trail, and the
mapping set is where a citable correspondence lives (FR-009). No method returns "the one true
type" of anything, and a caller that needs a single type must record an
:class:`~semantic.contracts.TypeAssertion` with evidence - a different object, in a different
place, for a different reason (FR-003, FR-004).

**No backend is named to the caller.** Answers are merged in canonical ``backend_id`` order,
which is a pure function of the *set* of registered backends, so two registries built from
the same backends in different registration orders return byte-identical listings
(constitution VI). Nothing in a returned value says where it came from, and
:meth:`~SemanticRegistry.backend_by_id` exists for diagnostics rather than for lookups. A
caller that could ask which backend answered would start depending on the answer, and
swapping backends would stop being free.

**Tenant isolation is structural and fail-closed.** One registry serves one tenant, and a
backend whose ``tenant_id`` disagrees is refused at registration with
:class:`TenantScopeRefused` rather than filed somewhere readable across a boundary. Every
one of the six operations takes an optional ``tenant_id`` and refuses a value other than the
one it serves, so cross-tenant access has no code path instead of having a filter nobody
forgot to add (constitution IV).

The two backends that ship here are wrappers, not new sources of truth:
:class:`ConceptSchemeBackend` presents an existing
:class:`~semantic.vocabularies.ConceptScheme` and :class:`MappingRegistryBackend` presents an
existing :class:`~semantic.mappings.MappingRegistry`. Each answers only the questions it has
data for and returns the canonical empty shape for the rest. :func:`oak_backend` composes the
optional OAK adapter as a third backend, importing it lazily so ``oak`` is never a dependency.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from semantic.contracts import SemanticRef
from semantic.mappings import MappingRegistry, SemanticMapping
from semantic.vocabularies import (
    Concept,
    ConceptScheme,
    MatchPredicate,
    Resolution,
    normalize_type_ref,
)

if TYPE_CHECKING:
    from semantic.oak_adapter import OakBackend

__all__ = [
    "BACKEND_CAPABILITIES",
    "BackendNameCollision",
    "ConceptSchemeBackend",
    "IncompleteBackendError",
    "MappingRegistryBackend",
    "SemanticBackend",
    "SemanticRegistry",
    "SemanticRegistryError",
    "TenantScopeRefused",
    "UnknownBackendError",
    "canonical_labels",
    "canonical_mappings",
    "canonical_refs",
    "check_tenant_scope",
    "missing_capabilities",
    "oak_backend",
]

#: The six semantic operations every backend must implement, in canonical order. This tuple is
#: the definition of the interface: registration refuses a backend missing any of these names,
#: so a capability gap is a wiring error found at wiring time rather than an ``AttributeError``
#: found by a caller mid-request.
BACKEND_CAPABILITIES: tuple[str, ...] = (
    "resolve_term",
    "get_aliases",
    "parents",
    "children",
    "related",
    "mappings",
)


class SemanticRegistryError(Exception):
    """Base for the typed failures this module raises.

    Everything here is a refusal about *wiring or authority* - an incomplete backend, a
    duplicate name, a tenant boundary - and never a judgement about the content a caller asked
    about. Content is open (FR-001); configuration is closed.
    """


class IncompleteBackendError(SemanticRegistryError):
    """A backend was offered that does not implement all six capabilities.

    Raised at registration, deliberately. The alternative - discovering the gap when some
    caller happens to call the missing method - makes a wiring mistake look like a semantic
    answer: the caller gets an ``AttributeError`` where a vocabulary answer belongs, and the
    resulting code tends to grow a ``hasattr`` guard that quietly returns nothing. Naming the
    missing capabilities here means the failure happens while the registry is being built,
    where the person who built it is looking.
    """

    def __init__(self, backend: object, missing: Iterable[str]) -> None:
        self.backend = backend
        self.missing = tuple(sorted({str(name) for name in missing}))
        described = ", ".join(self.missing) or "none"
        super().__init__(
            f"{type(backend).__name__} is missing required semantic capabilities ({described}); "
            f"a backend must implement all of {', '.join(BACKEND_CAPABILITIES)} to be registered"
        )


class BackendNameCollision(SemanticRegistryError):
    """Two backends were registered under one ``backend_id``.

    The name is the merge order, so a duplicate would make the winner depend on registration
    order rather than on the contents of the backends.
    """

    def __init__(self, backend_id: str) -> None:
        self.backend_id = str(backend_id)
        super().__init__(
            f"backend id {self.backend_id!r} is already registered; backend ids are unique"
        )


class UnknownBackendError(SemanticRegistryError):
    """A ``backend_id`` was named that is not registered. A configuration error, not content."""

    def __init__(self, backend_id: str) -> None:
        self.backend_id = str(backend_id)
        super().__init__(f"no backend is registered under id {self.backend_id!r}")


class TenantScopeRefused(SemanticRegistryError):
    """A registration or a query named a tenant this object does not serve.

    Fail-closed in both directions and for the same reason (constitution IV): a cross-tenant
    registration is refused at the write so it is never readable, and a cross-tenant query is
    refused at the read so it is never answerable. There is no code path in which a registry
    serves two tenants, because a registry that could would have to remember which caller was
    which on every one of six methods.
    """

    def __init__(self, requested_tenant: str, registry_tenant: str) -> None:
        self.requested_tenant = str(requested_tenant)
        self.registry_tenant = str(registry_tenant)
        super().__init__(
            f"tenant {self.requested_tenant!r} is not served here; this object serves "
            f"{self.registry_tenant!r}; cross-tenant access is refused"
        )


def missing_capabilities(backend: object) -> tuple[str, ...]:
    """Which of the six required capabilities ``backend`` does not provide, canonically ordered.

    Presence is not enough: a name bound to a non-callable attribute is as unusable as an
    absent one, and both are wiring defects. Returning the list rather than a bare boolean is
    what lets a refusal say *which* capability is missing.
    """
    absent: list[str] = []
    for name in BACKEND_CAPABILITIES:
        if not callable(getattr(backend, name, None)):
            absent.append(name)
    return tuple(absent)


@runtime_checkable
class SemanticBackend(Protocol):
    """What the façade requires of any vocabulary source, local or remote.

    Structural rather than nominal on purpose: a local ``ConceptScheme``, an OBO import and a
    remote OAK endpoint share no base class and should not be made to. Each operation is
    declared with the exact signature and return type the façade promises, and those
    declarations are the contract - :class:`SemanticRegistry` returns whatever a backend
    returns, so a backend whose signature drifts *is* a change to the public API of the
    platform, and would be caught at review rather than at runtime.

    ``tenant_id`` and ``backend_id`` are part of the contract too, though they are not
    semantic operations: the first is what makes a backend refusable across a tenant boundary,
    the second is the canonical merge order. Note what is absent: no capability for "give me
    the one true type", because a backend must not be able to answer that even if it wanted to.
    """

    @property
    def tenant_id(self) -> str:
        """The single tenant this backend serves."""

    @property
    def backend_id(self) -> str:
        """A stable, unique name. It decides merge order and is never shown to a caller."""

    def resolve_term(self, term: str, *, tenant_id: str = "") -> Resolution:
        """Every concept ``term`` reaches, or the unresolved shape when it reaches none."""

    def get_aliases(self, term: str, *, tenant_id: str = "") -> tuple[str, ...]:
        """Surface forms for one concept, or ``()``."""

    def parents(self, term: str, *, tenant_id: str = "") -> tuple[str, ...]:
        """Direct ``broader`` references, never a transitive closure."""

    def children(self, term: str, *, tenant_id: str = "") -> tuple[str, ...]:
        """Direct ``narrower`` references, never a transitive closure."""

    def related(self, term: str, *, tenant_id: str = "") -> tuple[str, ...]:
        """Association references. Never equivalences (FR-008)."""

    def mappings(self, term: str, *, predicate: MatchPredicate | None = None,
                 tenant_id: str = "") -> tuple[SemanticMapping, ...]:
        """Recorded correspondence claims involving ``term``, each with its own provenance."""


def canonical_refs(values: Iterable[object]) -> tuple[str, ...]:
    """A reference set: blank-free, de-duplicated, canonically ordered.

    Reference normalisation is :func:`normalize_type_ref`, which preserves case because a
    reference is an opaque identifier - deciding that ``schema:Person`` and ``schema:person``
    are one thing is a mapping assertion, and mappings are recorded rather than inferred.
    """
    if isinstance(values, str):
        return (normalize_type_ref(values),) if normalize_type_ref(values) else ()
    return tuple(sorted({ref for ref in (normalize_type_ref(v) for v in values) if ref}))


def canonical_labels(values: Iterable[object]) -> tuple[str, ...]:
    """A label list: first occurrence wins, blanks dropped, order preserved.

    Order is preserved rather than sorted because for labels the order is a recorded fact -
    the preferred label comes first, and a caller rendering a pick-list depends on it. Blanks
    are dropped because an absent label is not a label, and de-duplication is by exact text
    because two spellings of a name are two labels.
    """
    if isinstance(values, str):
        values = (values,)
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            ordered.append(text)
    return tuple(ordered)


def canonical_mappings(values: Iterable[SemanticMapping]) -> tuple[SemanticMapping, ...]:
    """A claim list: de-duplicated by content, ordered by content.

    Ordering by the content digest rather than by any field means the result is a pure
    function of the claims themselves, so two backends holding the same claim order it the
    same way and no registration sequence can perturb a listing. Nothing is collapsed: two
    claims about one pair with different predicates are two records and both survive.
    """
    if isinstance(values, (SemanticMapping, str)):
        raise TypeError("mappings must be given as a sequence of SemanticMapping records")
    by_content: dict[str, SemanticMapping] = {}
    for mapping in values:
        by_content.setdefault(mapping.content_key(), mapping)
    return tuple(by_content[key] for key in sorted(by_content))


def _backend_tenant(backend: object) -> str:
    """Read a backend's tenant, refusing one that is absent or not a string.

    A backend whose tenant cannot be read cannot be checked against a registry's, so it is
    refused at registration rather than trusted by default.
    """
    tenant = getattr(backend, "tenant_id", None)
    if not isinstance(tenant, str) or not tenant.strip():
        raise IncompleteBackendError(backend, ("tenant_id",))
    return tenant.strip()


def _backend_identity(backend: object) -> str:
    """Read a backend's id, refusing one that is absent, blank or not a string."""
    name = getattr(backend, "backend_id", None)
    if not isinstance(name, str) or not name.strip():
        raise IncompleteBackendError(backend, ("backend_id",))
    return name.strip()


def check_tenant_scope(serving: str, tenant_id: str) -> str:
    """Resolve the tenant a call was made under, refusing anything but ``serving``.

    A blank ``tenant_id`` means "the one this object serves" rather than "any tenant": there
    is deliberately no way to pass a wildcard, because a wildcard tenant is how a shared cache
    becomes a cross-tenant read.
    """
    wanted = str(tenant_id).strip() or serving
    if wanted != serving:
        raise TenantScopeRefused(wanted, serving)
    return wanted


@dataclass(frozen=True)
class ConceptSchemeBackend:
    """A local SKOS :class:`~semantic.vocabularies.ConceptScheme` behind the backend interface.

    Frozen and value-semantic, like the scheme it presents, so one scheme can be handed to
    several registries and to several callers without any of them being able to change it for
    the others. It is a *hint* surface, never a gate: a concept the scheme does not contain
    resolves to the unresolved shape and raises nothing, so a caller can bring its own
    vocabulary to the table without permission (FR-001, FR-002).

    :meth:`mappings` returns ``()`` and that is not a gap. A scheme records ``*_match`` *links*
    - correspondence claims with no audit trail - while :class:`~semantic.mappings.SemanticMapping`
    is a claim that can be cited, versioned and re-evaluated (FR-009). This backend answers
    only the questions it has citable data for; the mapping set is a separate backend, and the
    two compose. Transitivity is absent by design: ``parents``/``children`` are the direct
    single-hop links, because widening a query is a per-operation decision belonging to
    :mod:`semantic.expansion` (FR-008).
    """

    scheme: ConceptScheme
    tenant_id: str = ""
    backend_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", str(self.tenant_id).strip() or "default-tenant")
        object.__setattr__(
            self,
            "backend_id",
            str(self.backend_id).strip() or f"skos:{self.scheme.scheme_id}",
        )

    def _guard(self, term: str, tenant_id: str) -> str:
        check_tenant_scope(self.tenant_id, tenant_id)
        return str(term)

    def resolve_term(self, term: str, *, tenant_id: str = "") -> Resolution:
        """Every concept the term reaches, canonically ordered; unresolved shape if none.

        A surface form reaching several concepts is ambiguity being reported, not an error:
        :attr:`Resolution.is_ambiguous` exists for exactly that, and picking one here would
        turn a property of the vocabulary into a coin flip.
        """
        return self.scheme.resolve(self._guard(term, tenant_id))

    def get_aliases(self, term: str, *, tenant_id: str = "") -> tuple[str, ...]:
        """Preferred label first, then alternative labels and notation; ``()`` if unknown."""
        return self.scheme.get_aliases(self._guard(term, tenant_id))

    def parents(self, term: str, *, tenant_id: str = "") -> tuple[str, ...]:
        """Direct ``broader`` references. Hierarchy, never identity."""
        return canonical_refs(self.scheme.parents(self._guard(term, tenant_id)))

    def children(self, term: str, *, tenant_id: str = "") -> tuple[str, ...]:
        """Direct ``narrower`` references, completed from what the children declared."""
        return canonical_refs(self.scheme.children(self._guard(term, tenant_id)))

    def related(self, term: str, *, tenant_id: str = "") -> tuple[str, ...]:
        """Symmetrically completed association links. Never equivalences, never transitive."""
        return canonical_refs(self.scheme.related(self._guard(term, tenant_id)))

    def mappings(self, term: str, *, predicate: MatchPredicate | None = None,
                 tenant_id: str = "") -> tuple[SemanticMapping, ...]:
        """``()``: this backend holds no citable correspondences. See the class docstring."""
        self._guard(term, tenant_id)
        if predicate is not None:
            MatchPredicate(predicate)
        return ()


@dataclass(frozen=True)
class MappingRegistryBackend:
    """An existing :class:`~semantic.mappings.MappingRegistry` behind the backend interface.

    The counterpart to :class:`ConceptSchemeBackend`, and the reason the two compose rather
    than compete: this one answers correspondence and no vocabulary questions at all, so it
    resolves nothing and reports no hierarchy. Registering both gives a caller a full answer
    without either store having to know about the other, which is the point of the façade.

    :meth:`mappings` reports claims from *either* side of a correspondence, because a caller
    holding ``schema:Person`` upstream and a caller holding an internal ref are asking the
    same question and neither knows which side is "internal" in the other vocabulary. Both
    directions are returned, still uncollapsed: disagreeing predicates for one pair are two
    records (:class:`~semantic.mappings.MappingConflict` is how a caller notices), and a
    ``predicate`` argument narrows what is being *reported* without discarding anything.
    """

    registry: MappingRegistry
    tenant_id: str = ""
    backend_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "tenant_id", str(self.tenant_id).strip() or self.registry.tenant_id
        )
        object.__setattr__(self, "backend_id", str(self.backend_id).strip() or "sssom")

    def _guard(self, term: str, tenant_id: str) -> str:
        check_tenant_scope(self.tenant_id, tenant_id)
        return str(term)

    def resolve_term(self, term: str, *, tenant_id: str = "") -> Resolution:
        """The unresolved shape, always: a mapping set resolves no surface forms.

        A correspondence says a term *aligns to* something; it says nothing about what the
        term is, and turning an alignment into a resolution is precisely the merge of identity
        this façade refuses to perform.
        """
        surface = self._guard(term, tenant_id)
        return Resolution(
            surface_form=surface,
            concepts=(),
            scheme_id="",
            semantic_ref=SemanticRef.UNRESOLVED,
        )

    def get_aliases(self, term: str, *, tenant_id: str = "") -> tuple[str, ...]:
        """``()``: a mapping registry records correspondences, not labels."""
        self._guard(term, tenant_id)
        return ()

    def parents(self, term: str, *, tenant_id: str = "") -> tuple[str, ...]:
        """``()``: hierarchy is a vocabulary fact, and a mapping set does not hold one."""
        self._guard(term, tenant_id)
        return ()

    def children(self, term: str, *, tenant_id: str = "") -> tuple[str, ...]:
        """``()``: see :meth:`parents`."""
        self._guard(term, tenant_id)
        return ()

    def related(self, term: str, *, tenant_id: str = "") -> tuple[str, ...]:
        """``()``: a correspondence is a claim about alignment, not about association."""
        self._guard(term, tenant_id)
        return ()

    def mappings(self, term: str, *, predicate: MatchPredicate | None = None,
                 tenant_id: str = "") -> tuple[SemanticMapping, ...]:
        """Every recorded claim this term appears in, from either side, uncollapsed."""
        surface = self._guard(term, tenant_id)
        claims = (*self.registry.resolve_external(surface, predicate),
                  *self.registry.resolve_internal(surface, predicate))
        return canonical_mappings(claims)


class SemanticRegistry:
    """The façade: six semantic operations over any number of interchangeable backends.

    Construct one per tenant, register backends, and call the six operations. Nothing above
    this class needs to know which are registered, and this class never reports it either -
    a caller that could ask which backend answered would begin to depend on the answer, and
    swapping backends would stop being free (FR-015, SC-7).

    The registry is a mutable *configuration* object, unlike the frozen values it returns: a
    backend is wiring, and wiring is changed by whoever builds the process. Its results are
    nevertheless a pure function of the set of registered backends rather than of their
    registration order, because every merge walks backends in ``backend_id`` order (constitution
    VI). Swapping a backend is therefore two administrative calls - :meth:`unregister` and
    :meth:`register` - and no change whatsoever to calling code.

    Registration order of checks is deliberate: capability, then identity, then tenant, then
    name. A backend that is not a backend at all is reported as not a backend, whatever its
    tenant or its name, because that is the defect the caller has to fix first.
    """

    def __init__(
        self, tenant_id: str = "default-tenant", backends: Iterable[SemanticBackend] = ()
    ) -> None:
        self._tenant_id = str(tenant_id).strip()
        self._backends: dict[str, SemanticBackend] = {}
        for backend in backends:
            self.register(backend)

    @property
    def tenant_id(self) -> str:
        return self._tenant_id

    def __len__(self) -> int:
        return len(self._backends)

    def __iter__(self) -> Iterator[str]:
        """Registered backend ids, canonically ordered. Deliberately ids, not objects."""
        return iter(self.backend_ids())

    def __contains__(self, backend_id: object) -> bool:
        return str(backend_id) in self._backends

    def __repr__(self) -> str:
        return (
            f"SemanticRegistry(tenant_id={self._tenant_id!r}, backends={self.backend_ids()!r})"
        )

    def backend_ids(self) -> tuple[str, ...]:
        """Registered ids in canonical order - the order every merge walks them in."""
        return tuple(sorted(self._backends))

    def backend_by_id(self, backend_id: str) -> SemanticBackend:
        """One registered backend, for diagnostics and capability checks.

        Exposed so an operator can answer "is the OAK backend wired?" without every caller
        doing so. A lookup that wanted an *answer* from a named backend would defeat the
        façade, which is why nothing in the six operations takes a backend selector.
        """
        wanted = str(backend_id).strip()
        found = self._backends.get(wanted)
        if found is None:
            raise UnknownBackendError(wanted)
        return found

    def register(self, backend: SemanticBackend) -> str:
        """Admit a backend, returning its id. Refuses rather than degrades.

        Four refusals, all configuration-shaped: an incomplete backend
        (:class:`IncompleteBackendError`), a missing or non-string identity, a tenant other
        than this registry's (:class:`TenantScopeRefused`) and a name already bound
        (:class:`BackendNameCollision`). None of them is a judgement about the content the
        backend holds, because a vocabulary may contain anything at all (FR-001).
        """
        absent = missing_capabilities(backend)
        if absent or not isinstance(backend, SemanticBackend):
            raise IncompleteBackendError(backend, absent)
        backend_id = _backend_identity(backend)
        tenant = _backend_tenant(backend)
        if tenant != self._tenant_id:
            raise TenantScopeRefused(tenant, self._tenant_id)
        if backend_id in self._backends:
            raise BackendNameCollision(backend_id)
        self._backends[backend_id] = backend
        return backend_id

    def unregister(self, backend_id: str) -> SemanticBackend:
        """Remove a backend and hand it back, so a swap can be done without a lookup table.

        The returned object is the one that was registered. Nothing is refactored, rebuilt or
        invalidated on the way out, which is what makes swapping a backend a pure wiring
        operation rather than a data migration.
        """
        wanted = str(backend_id).strip()
        found = self._backends.pop(wanted, None)
        if found is None:
            raise UnknownBackendError(wanted)
        return found

    def _ordered(self) -> tuple[SemanticBackend, ...]:
        """Registered backends in canonical ``backend_id`` order - never registration order."""
        return tuple(self._backends[backend_id] for backend_id in self.backend_ids())

    def _guard(self, term: str, tenant_id: str) -> str:
        check_tenant_scope(self._tenant_id, tenant_id)
        return str(term)

    def resolve_term(self, term: str, *, tenant_id: str = "") -> Resolution:
        """Every concept ``term`` reaches across every backend, canonically ordered by id.

        The returned :class:`~semantic.vocabularies.Resolution` always has the same shape, so
        the only two states a caller has to tell apart are *reached something* and *reached
        nothing*, whichever backends were registered and whether they were installed at all.
        ``semantic_ref`` is therefore derived here rather than taken from a backend: a resolved
        answer is :attr:`SemanticRef.SKOS` whatever answered it, because a third value that
        named the transport would be a leak of exactly the kind this façade exists to prevent.

        Ambiguity survives: a term reaching three concepts in three backends returns three
        concepts, and the result is the same tuple whether one backend or three answered.
        ``scheme_id`` names the single contributing scheme when there was exactly one, and is
        empty when the answer is a merge - there is no honest single name for several schemes,
        and inventing one would name a vocabulary that does not exist.
        """
        surface = self._guard(term, tenant_id)
        concepts: dict[str, Concept] = {}
        schemes: set[str] = set()
        for backend in self._ordered():
            answer = backend.resolve_term(surface, tenant_id=self._tenant_id)
            for concept in answer.concepts:
                concepts.setdefault(concept.concept_id, concept)
                if concept.scheme_id:
                    schemes.add(concept.scheme_id)
        ordered = tuple(concepts[concept_id] for concept_id in sorted(concepts))
        return Resolution(
            surface_form=surface,
            concepts=ordered,
            scheme_id=next(iter(schemes)) if len(schemes) == 1 else "",
            semantic_ref=SemanticRef.SKOS if ordered else SemanticRef.UNRESOLVED,
        )

    def get_aliases(self, term: str, *, tenant_id: str = "") -> tuple[str, ...]:
        """Every backend's labels for one concept, de-duplicated, preferred label first.

        Backends are walked in canonical order and first occurrence wins, so the answer is
        reproducible across processes and independent of registration order. Labels are the one
        listing where order carries meaning - a caller renders a preferred label first - so
        unlike the reference sets below this is not re-sorted.
        """
        surface = self._guard(term, tenant_id)
        labels: list[str] = []
        for backend in self._ordered():
            labels.extend(backend.get_aliases(surface, tenant_id=self._tenant_id))
        return canonical_labels(labels)

    def parents(self, term: str, *, tenant_id: str = "") -> tuple[str, ...]:
        """Direct ``broader`` references from every backend, as one canonically ordered set.

        Union rather than intersection on purpose: a reference one vocabulary records and
        another has never heard of is still a recorded reference, and dropping it because
        another backend is silent would make a fuller vocabulary look like a sparser one.
        """
        surface = self._guard(term, tenant_id)
        refs: list[str] = []
        for backend in self._ordered():
            refs.extend(backend.parents(surface, tenant_id=self._tenant_id))
        return canonical_refs(refs)

    def children(self, term: str, *, tenant_id: str = "") -> tuple[str, ...]:
        """Direct ``narrower`` references from every backend, canonically ordered."""
        surface = self._guard(term, tenant_id)
        refs: list[str] = []
        for backend in self._ordered():
            refs.extend(backend.children(surface, tenant_id=self._tenant_id))
        return canonical_refs(refs)

    def related(self, term: str, *, tenant_id: str = "") -> tuple[str, ...]:
        """Association references from every backend, canonically ordered. Never equivalences.

        ``related`` is the weakest link in the SKOS hierarchy and the one most often mistaken
        for identity, which is why the return value is reference strings with no predicate
        and no claim attached: a caller can widen a query along it and cannot conclude
        anything from it. Walking it transitively is refused here as firmly as anywhere else -
        a platform that invents "related to a thing related to" cannot later tell what was
        recorded from what it derived (FR-008).
        """
        surface = self._guard(term, tenant_id)
        refs: list[str] = []
        for backend in self._ordered():
            refs.extend(backend.related(surface, tenant_id=self._tenant_id))
        return canonical_refs(refs)

    def mappings(self, term: str, *, predicate: MatchPredicate | None = None,
                 tenant_id: str = "") -> tuple[SemanticMapping, ...]:
        """Every recorded correspondence claim this term appears in, from every backend.

        The claims are returned whole - predicate, justification, source, version and
        provenance intact - because a caller deciding what to type an entity as needs to be
        able to see *on what grounds* a term was aligned, and to be able to say "these two
        claims disagree" instead of receiving a silently chosen winner. Even
        :attr:`MatchPredicate.EXACT_MATCH` is only a mapping process's claim, and it is
        re-evaluable: withdrawing it removes a claim and leaves both terms exactly where they
        were (FR-009, FR-012).
        """
        surface = self._guard(term, tenant_id)
        claims: list[SemanticMapping] = []
        for backend in self._ordered():
            claims.extend(
                backend.mappings(surface, predicate=predicate, tenant_id=self._tenant_id)
            )
        return canonical_mappings(claims)


def oak_backend(
    tenant_id: str = "default-tenant",
    *,
    delegate: SemanticBackend | None = None,
    backend_id: str = "oak",
) -> OakBackend:
    """Compose the optional OAK-backed backend as a third registerable backend.

    The import is local to this function on purpose. ``oak`` is not installed and must never
    be required (plan D4, constitution III), so nothing at module scope may touch it and
    nothing may import :mod:`semantic.oak_adapter` until a caller asks for an OAK backend.
    A caller that never does never pays for it, and - more to the point - a caller that does
    gets an adapter that degrades to the unresolved shape instead of raising.

    ``delegate`` is the escape hatch for an already-constructed in-process implementation, and
    it is the reason the adapter's call sites never change when OAK arrives: hand the same
    object to the same methods and it answers through them.
    """
    from semantic.oak_adapter import OakBackend

    return OakBackend(tenant_id=tenant_id, delegate=delegate, backend_id=backend_id)
