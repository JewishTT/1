"""OAK as an optional backend behind :mod:`semantic.registry`, never as a dependency.

Feature 017, FR-015 / T025, US8, SC-7. The ``oak`` package is not installed here and is not
required: plan D4 makes external tooling an adapter, and constitution III keeps semantic access
a static vocabulary lookup. So this module imports ``oak`` **lazily, inside a call, inside
``try: ... except ImportError``** - never at module scope - and
:func:`oak_available` answers "could it be imported?" through
:func:`importlib.util.find_spec`, which probes without importing. A health check, a capability
banner or a skip condition can therefore be expressed without a missing dependency becoming an
exception at the wrong moment, and without paying for an import nobody needed (the same
discipline :mod:`semantic.shacl` applies to pySHACL).

**The degradation is the load-bearing part.** An :class:`OakBackend` with no in-process
implementation answers all six operations with the canonical *unresolved* shapes -
:class:`~semantic.vocabularies.Resolution` with ``concepts=()`` and
``semantic_ref=SemanticRef.UNRESOLVED``, and empty tuples for the other five. It never raises
and never returns a different type. That is what makes the façade backend-agnostic in practice
rather than only on paper: a caller written against :class:`~semantic.registry.SemanticRegistry`
cannot tell "the OAK backend is not installed" from "the OAK backend knows nothing about this
term", because both are the same answer, and the same answer a local SKOS scheme gives for a
term it has never seen. The absence of a capability is reportable, not exceptional.

**Present an implementation, do not invent one.** This adapter does not re-implement OAK's
index and does not guess at its API: an OAK-backed implementation is a *delegate* - an
already-constructed object that satisfies :class:`~semantic.registry.SemanticBackend` - handed
in by whoever holds the real thing, whether that is a remote handle, an in-process index or a
test double. :meth:`OakBackend.around` is the path, and it is the reason the adapter's own call
sites never change when OAK is swapped in: the delegate is answered through the same six
methods, in the same order, with the same argument shape. A delegate missing any capability is
refused at construction by the same check the registry applies, so an incomplete implementation
cannot reach a caller as a runtime surprise.

**What a delegate is not allowed to do to the answer.** The adapter re-derives ordering and
status rather than trusting them, because those are the two things that would otherwise let a
backend be *felt* through the façade: concepts come back canonically ordered by id, mappings
come back ordered and de-duplicated by content, and ``semantic_ref`` is recomputed from whether
anything was reached. A delegate also cannot invent an identity: every one of the six operations
returns the canonical type, and nothing here can be made to answer with a single "true" type
(FR-008, FR-015).
"""

from __future__ import annotations

import importlib
import importlib.util
from collections.abc import Iterable
from dataclasses import dataclass
from types import ModuleType

from semantic.contracts import SemanticRef
from semantic.mappings import SemanticMapping
from semantic.registry import (
    IncompleteBackendError,
    SemanticBackend,
    SemanticRegistryError,
    TenantScopeRefused,
    canonical_labels,
    canonical_mappings,
    canonical_refs,
    check_tenant_scope,
    missing_capabilities,
)
from semantic.vocabularies import Concept, MatchPredicate, Resolution

__all__ = ["OakAdapterError", "OakBackend", "load_oak", "oak_available"]

#: The module name this adapter would import lazily, named so a caller can report or stub it
#: without repeating the string.
OAK_MODULE = "oak"


class OakAdapterError(SemanticRegistryError):
    """A delegate answered with something the interface does not allow.

    Raised only for a *present* implementation answering wrongly, which is a programming
    error rather than a missing capability: the absent case degrades silently, so anything that
    does reach this exception is a real defect in a delegate somebody wrote. A bare string where
    a sequence of references was contracted is the case worth catching - iterating it would
    quietly yield one character per reference, and the answer would look like data.
    """

    def __init__(self, operation: str, expected: str, received: type) -> None:
        self.operation = str(operation)
        self.expected = str(expected)
        self.received = received
        super().__init__(
            f"OAK delegate answered {self.operation!r} with {self.received.__name__}; "
            f"{self.expected} was contracted"
        )


def oak_available() -> bool:
    """Whether the ``oak`` package could be imported - probed, not imported.

    ``find_spec`` reads the import system's metadata and stops there, so this costs no module
    execution and cannot raise ``ImportError`` for a missing package. The two failure modes
    are both answered ``False`` rather than propagated: a missing package and a broken finder
    both mean "this capability is not usable", and neither is a reason to fail a health check.
    """
    try:
        return importlib.util.find_spec(OAK_MODULE) is not None
    except (ImportError, ValueError):
        return False


def load_oak() -> ModuleType | None:
    """Import ``oak`` now and return it, or ``None`` when it is not installed.

    This is the only place the import happens, and it is inside a ``try: ... except
    ImportError`` so an absent optional dependency is a ``None`` rather than a traceback
    escaping into a caller that only wanted a vocabulary lookup. No name from the module is
    used or guessed at here - the adapter presents an implementation, it does not re-implement
    one, so having the module is a capability fact and nothing more.
    """
    try:
        return importlib.import_module(OAK_MODULE)
    except ImportError:
        return None


def _as_resolution(value: object, surface: str, operation: str) -> Resolution:
    """Coerce a delegate's answer into the one canonical :class:`Resolution` shape.

    Accepts a ``Resolution``, a single ``Concept`` or a sequence of them, and rebuilds the
    result: concepts canonically ordered by id, ``surface_form`` echoing the term as it was
    asked, and ``semantic_ref`` recomputed from whether anything was reached. Recomputing is
    the point - a delegate that reported a third reference kind, or reported ``UNRESOLVED``
    while holding concepts, would otherwise be able to signal its own presence through the
    façade.
    """
    if isinstance(value, Resolution):
        concepts: list[Concept] = list(value.concepts)
    elif isinstance(value, Concept):
        concepts = [value]
    elif isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise OakAdapterError(
            operation, "Resolution, Concept or a sequence of Concept", type(value)
        )
    else:
        found = list(value)
        for item in found:
            if not isinstance(item, Concept):
                raise OakAdapterError(operation, "a sequence of Concept", type(item))
        concepts = found
    ordered = {concept.concept_id: concept for concept in concepts}
    by_id = tuple(ordered[concept_id] for concept_id in sorted(ordered))
    return Resolution(
        surface_form=surface,
        concepts=by_id,
        scheme_id=value.scheme_id if isinstance(value, Resolution) else "",
        semantic_ref=SemanticRef.SKOS if by_id else SemanticRef.UNRESOLVED,
    )


def _as_refs(value: object, operation: str) -> tuple[str, ...]:
    """Coerce a delegate's answer into a canonically ordered reference set.

    A bare string is refused rather than iterated, because iterating ``"local:X"`` yields one
    reference per character and the result would be a plausible-looking wrong answer rather
    than an error.
    """
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise OakAdapterError(operation, "a sequence of str", type(value))
    for item in value:
        if not isinstance(item, str):
            raise OakAdapterError(operation, "a sequence of str", type(item))
    return canonical_refs(value)


def _as_labels(value: object, operation: str) -> tuple[str, ...]:
    """Coerce a delegate's answer into a label list, preserving the order it recorded.

    Order is kept rather than sorted because for labels the order is data - a preferred label
    comes first and callers render it that way - and a delegate that recorded one has earned
    the right to have it honoured. Blanks are dropped and duplicates collapsed, since neither
    is information.
    """
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise OakAdapterError(operation, "a sequence of str", type(value))
    for item in value:
        if not isinstance(item, str):
            raise OakAdapterError(operation, "a sequence of str", type(item))
    return canonical_labels(value)


def _as_mappings(value: object, operation: str) -> tuple[SemanticMapping, ...]:
    """Coerce a delegate's answer into canonically ordered, de-duplicated mapping claims.

    Claims are never collapsed: two records about one pair with different predicates both
    survive, ordered by content digest so the listing is a pure function of the claims rather
    than of the delegate's iteration order.
    """
    if isinstance(value, (SemanticMapping, str, bytes)) or not isinstance(value, Iterable):
        raise OakAdapterError(operation, "a sequence of SemanticMapping", type(value))
    for item in value:
        if not isinstance(item, SemanticMapping):
            raise OakAdapterError(operation, "a sequence of SemanticMapping", type(item))
    return canonical_mappings(value)


@dataclass(frozen=True)
class OakBackend:
    """An OAK-backed backend for :class:`~semantic.registry.SemanticRegistry`, optional throughout.

    Constructed with nothing, it is a fully formed backend that answers every question with the
    unresolved shape. That is the default state on purpose: the adapter is safe to register
    unconditionally, and a deployment that never installs ``oak`` behaves exactly as though it
    had registered nothing - no exception, no missing method, no second code path in callers.

    ``delegate`` is how OAK is actually presented: an already-constructed implementation of
    :class:`~semantic.registry.SemanticBackend`, passed in rather than constructed here,
    because this adapter does not own an OAK index and will not pretend to. A delegate that
    lacks any of the six capabilities, or that serves a different tenant, is refused at
    construction - the same rule the registry applies, enforced early so an incomplete
    implementation cannot reach a caller.

    ``available()`` is a capability query, not a gate: it reports whether a call would reach
    an implementation, and :attr:`degradation_reason` says why one would not, so an operator
    can distinguish "oak is not installed" from "oak is installed but nothing was handed to the
    adapter". Neither ever raises, which is what makes it usable from a health check.
    """

    tenant_id: str = "default-tenant"
    backend_id: str = "oak"
    delegate: SemanticBackend | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", str(self.tenant_id).strip())
        object.__setattr__(self, "backend_id", str(self.backend_id).strip() or "oak")
        if self.delegate is None:
            return
        absent = missing_capabilities(self.delegate)
        if absent or not isinstance(self.delegate, SemanticBackend):
            raise IncompleteBackendError(self.delegate, absent)
        serving = getattr(self.delegate, "tenant_id", None)
        if not isinstance(serving, str) or not serving.strip():
            raise IncompleteBackendError(self.delegate, ("tenant_id",))
        if serving.strip() != self.tenant_id:
            raise TenantScopeRefused(serving.strip(), self.tenant_id)

    @classmethod
    def around(
        cls,
        delegate: SemanticBackend,
        *,
        tenant_id: str = "",
        backend_id: str = "oak",
    ) -> OakBackend:
        """Wrap an already-constructed in-process implementation, adopting its tenant.

        The ergonomic half of :class:`OakBackend` and the one that matters for swapping: an
        implementation that already satisfies the interface is handed over whole, and the
        adapter's call sites do not change when it arrives. The tenant is adopted rather than
        restated so an implementation cannot be wrapped under a tenant it does not serve, and
        the capability check still runs before anything is returned.
        """
        serving = getattr(delegate, "tenant_id", "")
        return cls(
            tenant_id=str(tenant_id).strip() or str(serving).strip() or "default-tenant",
            backend_id=backend_id,
            delegate=delegate,
        )

    @property
    def oak_module(self) -> ModuleType | None:
        """The imported ``oak`` module, or ``None``. Evaluated per access, never at import time.

        A property rather than a module constant so the answer reflects the process as it is
        now, and so importing this module stays free of side effects.
        """
        return load_oak()

    def available(self) -> bool:
        """Whether a call would reach a real implementation. Probed without importing ``oak``.

        The delegate is the implementation, so its presence is the whole answer. The installed
        ``oak`` package is deliberately *not* sufficient on its own: a library being importable
        says the capability could be built, not that this adapter has anything to present, and
        reporting otherwise would be a green light for a backend that answers nothing.
        """
        return self.delegate is not None

    @property
    def degradation_reason(self) -> str:
        """Why calls are degrading, or ``""`` when this backend has an implementation.

        Distinguishing the two absent-implementation cases matters in operation: one is a
        missing dependency and the other is a wiring mistake, and they need different fixes.
        Neither is an error, so this is a string and not an exception.
        """
        if self.available():
            return ""
        if oak_available():
            return (
                "the oak package is importable but no in-process OAK-backed implementation was "
                "supplied; supply one with OakBackend(delegate=...) to answer through OAK"
            )
        return (
            f"the {OAK_MODULE} package is not installed, so this backend answers every "
            "operation with the unresolved shape rather than raising"
        )

    def _guard(self, term: str, tenant_id: str) -> str:
        check_tenant_scope(self.tenant_id, tenant_id)
        return str(term)

    def resolve_term(self, term: str, *, tenant_id: str = "") -> Resolution:
        """Concepts the term reaches via OAK, or the canonical unresolved shape.

        Ambiguity is preserved end to end: a term reaching several concepts returns all of
        them, ordered by id, and a caller that wants one is a caller that should be recording a
        typing with evidence rather than asking a lookup to decide (FR-003, FR-008).
        """
        surface = self._guard(term, tenant_id)
        if self.delegate is None:
            return Resolution(
                surface_form=surface,
                concepts=(),
                scheme_id="",
                semantic_ref=SemanticRef.UNRESOLVED,
            )
        return _as_resolution(
            self.delegate.resolve_term(surface, tenant_id=self.tenant_id), surface, "resolve_term"
        )

    def get_aliases(self, term: str, *, tenant_id: str = "") -> tuple[str, ...]:
        """Surface forms for one concept, in the order the implementation recorded them."""
        surface = self._guard(term, tenant_id)
        if self.delegate is None:
            return ()
        return _as_labels(
            self.delegate.get_aliases(surface, tenant_id=self.tenant_id), "get_aliases"
        )

    def parents(self, term: str, *, tenant_id: str = "") -> tuple[str, ...]:
        """Direct ``broader`` references as OAK reports them, canonically ordered."""
        surface = self._guard(term, tenant_id)
        if self.delegate is None:
            return ()
        return _as_refs(self.delegate.parents(surface, tenant_id=self.tenant_id), "parents")

    def children(self, term: str, *, tenant_id: str = "") -> tuple[str, ...]:
        """Direct ``narrower`` references as OAK reports them, canonically ordered."""
        surface = self._guard(term, tenant_id)
        if self.delegate is None:
            return ()
        return _as_refs(self.delegate.children(surface, tenant_id=self.tenant_id), "children")

    def related(self, term: str, *, tenant_id: str = "") -> tuple[str, ...]:
        """Association references as OAK reports them. Never read as equivalences."""
        surface = self._guard(term, tenant_id)
        if self.delegate is None:
            return ()
        return _as_refs(self.delegate.related(surface, tenant_id=self.tenant_id), "related")

    def mappings(self, term: str, *, predicate: MatchPredicate | None = None,
                 tenant_id: str = "") -> tuple[SemanticMapping, ...]:
        """Correspondence claims as OAK reports them, uncollapsed and content-ordered.

        ``predicate`` narrows what is *reported* and never discards a record: filtering a
        correspondence set is a question about the current query, not an act of forgetting, and
        a caller that filtered once can still ask again (FR-004).
        """
        surface = self._guard(term, tenant_id)
        if predicate is not None:
            MatchPredicate(predicate)
        if self.delegate is None:
            return ()
        return _as_mappings(
            self.delegate.mappings(
                surface, predicate=predicate, tenant_id=self.tenant_id
            ),
            "mappings",
        )
