"""Scoped, versioned semantic profiles with inheritance, and no gate anywhere (FR-007).

Feature 017, FR-007 / T010, T011. A :class:`SemanticProfile` is a *bundle of instruments*: a
versioned, scoped set of type references, relation references, vocabulary references,
constraint references and mapping references, tied together by ``parent_profile`` inheritance
and scoped by ``applies_to`` to a source, a domain, an extractor or an investigation. It says
"under this regime, these instruments were in play". It does not say what may exist.

**The one constraint that outranks every other in this file: a profile mismatch is never a
rejection reason.** There is deliberately no ``validate``, no ``check``, no ``permits``, no
``allows_*`` and no ``rejects`` method here, and adding one would be a defect rather than a
feature. The reason is structural, not stylistic: this platform's world is open, so content that
falls outside a profile is not content that is *wrong* - it is content interpreted under a
different regime, or under none. US1 is the case that settles it: an extractor surfaces
``local:shell_company_shell``, no profile declares it, and the record is admitted with a
first-class local type and no error. The only thing a profile may ever produce is a *hint* -
something to widen a query along, to rank a candidate with, or to attach to a validation report
as context. Every membership method in this module says so in its own docstring, because a
membership check whose docstring does not say it is precisely the method that gets mistaken for
a gate six months later. Validation of content against a profile belongs to
:mod:`semantic.validation` and produces graded :class:`~semantic.contracts.ValidationFinding`
objects attached to assertions, never deletions (FR-012).

**Several profiles apply at once, and that is the normal case.**
:meth:`ProfileRegistry.applicable_profiles` returns a ``tuple`` of *every* matching profile,
canonically ordered, and there is no argument to it and no sibling method that narrows the
answer to one. A "best match" would have to rank
profiles, and ranking implies a profile is more *correct* than another, which is the ontology-
as-truth the spec's scope guard forbids. An entity from one source in one domain under one
extractor legitimately sits inside three profiles at the same time (US2, FR-003), and all three
are needed: one supplies the types, another the constraints, a third the mappings. Determinism
is supplied instead of ranking - the order is total, value-based and independent of registration
order, so the same registry state always answers the same question the same way (constitution VI).

**Inheritance is a pure, memoised, cycle-safe walk.** :meth:`ProfileRegistry.resolve` returns a
:class:`ProfileResolution` holding the whole lineage, root ancestor first, with the five
collections already unioned. The walk is iterative with an explicit visited set, so a cyclic
``parent_profile`` chain cannot hang and cannot exhaust the interpreter stack: it raises
:class:`ProfileCycleError` naming the cycle. That is the specified behaviour for a malformed
chain - a typed error, deterministically, on the first call that meets it - and it is the right
call because a cycle in a parent chain is a *configuration* bug, not world content, and
silently truncating the walk would produce a profile that quietly claims fewer instruments than
any of its members declared.

Resolution failures are not memoised, only successes are. A projection rebuilt from an event log
registers children before parents (constitution VII), so ``child.parent = base`` legitimately
fails on the first pass and succeeds once ``base`` arrives; caching the failure would make that
rebuild permanently broken. Successes *are* safe to cache forever, because profiles are frozen
and content-addressed: a chain that resolved once can never resolve differently, so the registry
needs no invalidation path at all.

**A version reference is explicit or it is refused.** ``profile_id`` alone is resolved only when
exactly one version of that id is registered; several versions is a genuine ambiguity (there is
no principled way to prefer ``3`` over ``10`` or over ``draft``) and raises
:class:`AmbiguousProfileVersionError` rather than guessing. This mirrors how
:class:`~semantic.mappings.MappingRegistry` refuses to pick a mapping-set version, and it is the
same discipline: an answer that had to be guessed should be reported as unanswerable.

**Deterministic and order-insensitive throughout.** Every collection is de-duplicated and
canonically sorted in ``__post_init__``, so two profiles declaring the same instruments in
different orders are the *same value* and share a :meth:`~SemanticProfile.content_key`. Typing
preserves case (``schema:Person`` and ``schema:person`` are different references) while scope
*kinds* are case-folded, reusing the package's two normalisers for the two different jobs they
do. ``@`` is reserved in a ``profile_id`` for the same reason it is in a
:class:`~semantic.contracts.RelationRef`: it separates a name from a version in a textual
reference, and a name that can contain the separator cannot be read back.

**Dependency reality.** Plain frozen dataclasses over strings and enums. No SHACL, no LinkML, no
template engine, no reasoner - a profile is a bundle of references, and validating the bundle's
shape needs nothing more than this.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from semantic.contracts import content_key
from semantic.vocabularies import normalize_surface_form, normalize_type_ref

__all__ = [
    "MAX_INHERITANCE_DEPTH",
    "AmbiguousProfileVersionError",
    "ProfileCycleError",
    "ProfileError",
    "ProfileIdCollision",
    "ProfileInheritanceTooDeep",
    "ProfileRefKind",
    "ProfileRegistry",
    "ProfileResolution",
    "ProfileScopeTag",
    "ScopeTag",
    "SemanticProfile",
    "TenantScopeRefused",
    "UnknownProfileError",
    "normalise_scope_tags",
]


#: Ceiling on how many profiles one inheritance chain may contribute. Generous enough for any
#: realistic layering and small enough that a malformed or generated chain cannot turn one
#: resolution into an unbounded walk (constitution VIII). Exceeding it raises rather than
#: truncating, for the same reason the mappings payload refuses to truncate: a resolved profile
#: that quietly stopped early would report fewer instruments than were declared, and nobody
#: would be able to tell.
MAX_INHERITANCE_DEPTH = 32


class ProfileScopeTag(StrEnum):
    """The four kinds of scope a profile may be declared against (FR-007).

    The vocabulary is closed because the spec names it, but nothing *enforces* it: an
    unrecognised kind in :attr:`SemanticProfile.applies_to` is retained and reported by
    :meth:`SemanticProfile.unrecognised_scope_tags` rather than refused. A profile declaring a
    scope this build does not recognise is a record the next build can still read, and
    rejecting it at load time would be a closed world in the one place that must not have one.
    """

    SOURCE = "source"
    DOMAIN = "domain"
    EXTRACTOR = "extractor"
    INVESTIGATION = "investigation"


#: The kinds this build knows, in declaration order.
KNOWN_SCOPE_TAGS: tuple[ProfileScopeTag, ...] = tuple(ProfileScopeTag)


@dataclass(frozen=True, order=True)
class ScopeTag:
    """One scope a profile is scoped by: a kind, and optionally the value within that kind.

    The grammar is deliberately two-level because the two halves of a scope are two different
    kinds of string. The **kind** is a coarse class, so it is case-folded and normalised through
    :func:`~semantic.vocabularies.normalize_surface_form` - ``Source``, ``source`` and ``SOURCE``
    are one kind. The **value** is an opaque identifier, so it keeps its case through
    :func:`~semantic.vocabularies.normalize_type_ref` - ``source=CommonCrawl`` and
    ``source=commoncrawl`` are two values, because deciding they name the same thing is a
    mapping assertion and mappings are recorded, never inferred (FR-009).

    An **empty value means any value of that kind**: ``source`` alone is the statement "any
    source", which is what a profile scoped by source but not by a particular feed needs to say.
    A non-empty value is exact. :meth:`satisfied_by` states the whole matching rule, and it is
    a rule about *which instruments were in play*, not about whether content is acceptable.
    """

    kind: str
    value: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", normalize_surface_form(self.kind))
        object.__setattr__(self, "value", normalize_type_ref(self.value))

    @classmethod
    def from_value(cls, value: str | ScopeTag | ProfileScopeTag) -> ScopeTag:
        """Parse ``"kind"`` or ``"kind=value"`` into a tag; pass a tag or enum through unchanged.

        A bare kind is the "any value of this kind" form, so ``"domain"`` scopes by domain
        generally while ``"domain=finance"`` scopes to one. A ``"="`` with nothing after it is
        the bare form written oddly rather than a scope on the empty value, and is read as the
        bare form - an empty value is never a real scope, and treating it as one would produce
        a profile that matches nothing while appearing to be scoped.
        """
        if isinstance(value, ScopeTag):
            return value
        text = str(value).strip()
        kind, separator, scope_value = text.partition("=")
        return cls(kind, scope_value if separator and scope_value.strip() else "")

    def __str__(self) -> str:
        return f"{self.kind}={self.value}" if self.value else self.kind

    @property
    def known_kind(self) -> ProfileScopeTag | None:
        """The :class:`ProfileScopeTag` this kind names, or ``None`` if this build never heard it.

        Matching is on the normalised kind, so the enum's spelling and the tag's need not agree
        on case for the lookup to succeed.
        """
        wanted = self.kind
        for tag in KNOWN_SCOPE_TAGS:
            if normalize_surface_form(str(tag)) == wanted:
                return tag
        return None

    def satisfied_by(self, tags: Iterable[ScopeTag]) -> bool:
        """Whether a supplied scope set covers this tag. Matching only - never a gate.

        An untagged tag (``source``) is satisfied by *any* tag of the same kind, because
        "any source" is what it means. A valued tag (``source=finance``) is satisfied only by
        that exact kind-and-value, because the whole content of the claim is the value. An
        untagged supplied tag never satisfies a valued one: a bare ``domain`` says the regime
        knows about domains, not which domain this record came from, and pretending otherwise
        would scope a profile far more widely than whoever declared it asked for.
        """
        supplied = tags if isinstance(tags, frozenset) else normalise_scope_tags(tags)
        if not self.value:
            return any(candidate.kind == self.kind for candidate in supplied)
        return self in supplied


def normalise_scope_tags(
    values: Iterable[str | ScopeTag | ProfileScopeTag] | str | ScopeTag | ProfileScopeTag,
) -> frozenset[ScopeTag]:
    """Canonicalise any mix of tags, enum members and ``"kind=value"`` strings into a set.

    Accepts a single value as well as an iterable, because a caller supplying one scope should
    not have to remember to wrap it. The result is a ``frozenset``, so membership tests are
    cheap and two profiles declaring the same scopes compare equal regardless of order.
    """
    if isinstance(values, str | ScopeTag | ProfileScopeTag):
        values = (values,)
    return frozenset(ScopeTag.from_value(value) for value in values)


def _canonical_refs(values: Iterable[str]) -> tuple[str, ...]:
    """A reference set: blank-free, de-duplicated, canonically ordered.

    Reuses :func:`~semantic.vocabularies.normalize_type_ref` because every ref in a profile is
    an opaque identifier whose case is load-bearing. Sorting is what makes a profile
    content-addressable without regard to the order its producer collected refs in
    (constitution VI), and dropping a blank ref is right because a missing instrument is not an
    instrument named by the empty string.
    """
    if isinstance(values, str):
        values = (values,)
    return tuple(sorted({ref for ref in (normalize_type_ref(v) for v in values) if ref}))


class ProfileError(Exception):
    """Base for every typed failure this module raises.

    A caller can catch all profile problems with one ``except`` and cannot accidentally swallow
    an unrelated ``ValueError`` from elsewhere in the stack - which matters here, because every
    exception this module raises is about *configuration* (a malformed parent chain, a
    duplicated key, a tenant boundary) and none of them is ever about content being unacceptable.
    """


class ProfileCycleError(ProfileError):
    """A ``parent_profile`` chain returns to a profile it already visited.

    The specified failure mode for a malformed chain: a typed error naming the whole cycle, on
    the first resolution that meets it, rather than a hang or a blown stack. A one-profile cycle
    (a profile that names itself as its own parent) is a cycle of length one and lands here too,
    which is why self-parenting is not detected separately.
    """

    def __init__(self, chain: Iterable[str]) -> None:
        self.chain = tuple(str(step) for step in chain)
        super().__init__(
            f"profile parent chain is cyclic: {' -> '.join(self.chain)}; "
            "a profile may not be its own ancestor"
        )


class UnknownProfileError(ProfileError):
    """A referenced profile is not registered - typically a dangling ``parent_profile``.

    Raised during resolution rather than registration, because a projection rebuilt from an event
    log registers children before their parents, so a dangling parent is a temporarily normal
    state and a load-time refusal would make that rebuild fail. The consequence is that
    resolution failures are never memoised, so registering the missing parent makes the very next
    call succeed.
    """

    def __init__(self, profile_id: str, version: str | None = None) -> None:
        self.profile_id = str(profile_id)
        self.version = None if version is None else str(version)
        wanted = self.profile_id if self.version is None else f"{self.profile_id}@{self.version}"
        super().__init__(f"profile {wanted!r} is not registered")


class AmbiguousProfileVersionError(ProfileError):
    """A reference named a ``profile_id`` but not a version, and several versions exist.

    Refused rather than resolved. There is no principled ordering over version labels -
    ``10`` does not come after ``3`` as a string, ``draft`` is not a number, and the registry
    has no standing to declare one of them active - so a store that picked one would be making
    the "which profile regime is in force" question a coin flip and recording no sign of it.
    """

    def __init__(self, profile_id: str, versions: Iterable[str]) -> None:
        self.profile_id = str(profile_id)
        self.versions = tuple(str(version) for version in versions)
        super().__init__(
            f"profile {self.profile_id!r} has versions {list(self.versions)}; "
            "reference one explicitly as profile_id@version"
        )


class ProfileInheritanceTooDeep(ProfileError):
    """An inheritance chain is longer than :data:`MAX_INHERITANCE_DEPTH`.

    A bound rather than a diagnosis: the walk is already cycle-safe, so this fires only on a
    genuinely very long chain, which is a generated or accidental structure rather than a
    designed layering. It raises instead of truncating, because a truncated chain resolves to a
    profile that reports fewer instruments than were declared and looks entirely normal.
    """

    def __init__(self, profile_ref: str, limit: int) -> None:
        self.profile_ref = str(profile_ref)
        self.limit = int(limit)
        super().__init__(
            f"profile parent chain exceeds the {self.limit}-profile depth bound at "
            f"{self.profile_ref!r}"
        )


class ProfileIdCollision(ProfileError):
    """Two different profile contents were offered under one ``(profile_id, version)``.

    That pair is the store key, so accepting the second would leave one key addressing two
    bundles, and any resolution naming it would become ambiguous without anything reporting it.
    A re-registration of *identical* content is not this - it is idempotent and returns the
    stored profile.
    """

    def __init__(self, profile_id: str, version: str) -> None:
        self.profile_id = str(profile_id)
        self.version = str(version)
        super().__init__(
            f"profile {self.profile_id}@{self.version} is already registered with different "
            "content; versioned keys are never rebound"
        )


class TenantScopeRefused(ProfileError):
    """A profile was offered to a registry serving a different tenant.

    Refused at the write, so cross-tenant visibility has no code path at all rather than being
    filtered on every read (constitution IV, fail-closed). Note the shape of the refusal: it is
    about *who may read the profile*, never about whether the content the profile describes is
    acceptable.
    """

    def __init__(self, profile_tenant: str, registry_tenant: str) -> None:
        self.profile_tenant = str(profile_tenant)
        self.registry_tenant = str(registry_tenant)
        super().__init__(
            f"profile belongs to tenant {self.profile_tenant!r}, registry serves "
            f"{self.registry_tenant!r}; cross-tenant registration is refused"
        )


class ProfileRefKind(StrEnum):
    """The five collections of instruments a profile carries, named for callers that iterate them.

    Exists so that :meth:`ProfileResolution.declared_by` can be asked "which profile in the
    lineage contributed this ref?" without a caller reaching into a field name. The order is the
    declaration order from the spec and has no ranking meaning - none of these five is more
    fundamental than another.
    """

    TYPE = "type"
    RELATION = "relation"
    VOCABULARY = "vocabulary"
    CONSTRAINT = "constraint"
    MAPPING = "mapping"


_REF_FIELDS: dict[ProfileRefKind, str] = {
    ProfileRefKind.TYPE: "type_refs",
    ProfileRefKind.RELATION: "relation_refs",
    ProfileRefKind.VOCABULARY: "vocabulary_refs",
    ProfileRefKind.CONSTRAINT: "constraint_refs",
    ProfileRefKind.MAPPING: "mapping_refs",
}

#: Every collection a profile carries, in declaration order. Canonicalised in ``__post_init__``.
_REF_COLLECTIONS: tuple[str, ...] = tuple(_REF_FIELDS.values())


def _order_key(profile: SemanticProfile) -> tuple[str, str]:
    """The total, value-based order every listing in this module uses.

    Sorting on values rather than arrival keeps ``applicable_profiles`` and the profile listings
    reproducible across processes and rebuilds, so a diff between two runs means the registry
    changed rather than that a dict iterated differently (constitution VI).
    """
    return (profile.profile_id, profile.version)


def _split_reference(reference: str) -> tuple[str, str | None]:
    """Split a ``"profile_id@version"`` reference; a bare id yields ``None`` for the version."""
    name, separator, version = str(reference).rpartition("@")
    if separator and name.strip() and version.strip():
        return (name.strip(), version.strip())
    return (str(reference).strip(), None)


@dataclass(frozen=True)
class SemanticProfile:
    """One versioned, scoped bundle of the semantic instruments available in a regime.

    The five ref collections are the whole payload: types, relations, vocabularies, constraints
    and mappings that were in play when something was interpreted. They are **references to
    instruments, not assertions about records** - a profile saying ``schema:Person`` is in play
    says nothing whatever about any entity, and there is no field here able to assert that two
    refs denote one thing. Identity is established in the graph by evidence, as a different kind
    of object entirely (spec scope guard).

    ``applies_to`` is a *scope declaration*, not a filter on content. ``parent_profile`` chains
    this profile to a base whose instruments it shares, resolved by
    :class:`ProfileRegistry` - this class never walks a chain itself, because cycle-safety is a
    property of a walk over *registered* profiles and a profile cannot see the registry.

    ``tenant_id`` is here because a regime is a reading of one tenant's data and leaking it
    across a boundary would leak what instruments that tenant had (constitution IV).

    Canonicalised on construction: every ref collection is blank-free, de-duplicated and sorted,
    and ``applies_to`` is a ``frozenset``, so two profiles declaring the same bundle in different
    orders are the same value with the same :meth:`content_key` (constitution VI).
    """

    profile_id: str
    parent_profile: str | None = None
    version: str = "1"

    type_refs: tuple[str, ...] = ()
    relation_refs: tuple[str, ...] = ()
    vocabulary_refs: tuple[str, ...] = ()
    constraint_refs: tuple[str, ...] = ()
    mapping_refs: tuple[str, ...] = ()

    applies_to: frozenset[ScopeTag] = frozenset()
    description: str = ""
    tenant_id: str = "default-tenant"

    def __post_init__(self) -> None:
        object.__setattr__(self, "profile_id", str(self.profile_id).strip())
        parent = str(self.parent_profile).strip() if self.parent_profile is not None else ""
        object.__setattr__(self, "parent_profile", parent or None)
        object.__setattr__(self, "version", str(self.version).strip())
        object.__setattr__(self, "description", str(self.description))
        object.__setattr__(self, "tenant_id", str(self.tenant_id).strip())
        for name in _REF_COLLECTIONS:
            object.__setattr__(self, name, _canonical_refs(getattr(self, name)))
        object.__setattr__(self, "applies_to", normalise_scope_tags(self.applies_to))

    @property
    def identity(self) -> tuple[str, str]:
        """``(profile_id, version)`` - the store key, per the spec's data requirements.

        Deliberately the key and not the full record: ``parent_profile`` is part of the profile's
        *content* (and so of its :meth:`content_key`) but not part of its address, because a
        profile that inherits from a different base is still version 1 of itself.
        """
        return (self.profile_id, self.version)

    @property
    def version_ref(self) -> str:
        """``"profile_id@version"`` - how a profile is named in a parent reference or a report.

        ``@`` is reserved in a ``profile_id`` for exactly this reason, so a rendered reference
        always reads back: :meth:`parent_target` splits on the same separator.
        """
        return f"{self.profile_id}@{self.version}"

    @property
    def is_root(self) -> bool:
        """True when this profile names no parent, and so contributes its own bundle only."""
        return self.parent_profile is None

    @property
    def scope_tags(self) -> tuple[ScopeTag, ...]:
        """The declared scopes, canonically ordered by ``(kind, value)``.

        A tuple rather than the ``frozenset`` itself, because a caller rendering "which regimes
        is this profile scoped by?" needs a stable order and iterating a set does not give one.
        """
        return tuple(sorted(self.applies_to))

    def parent_target(self) -> tuple[str, str | None] | None:
        """The parent's ``(profile_id, version)``; ``None`` if a root, version ``None`` if bare."""
        if self.parent_profile is None:
            return None
        return _split_reference(self.parent_profile)

    def unrecognised_scope_tags(self) -> tuple[ScopeTag, ...]:
        """Declared scopes whose *kind* this build has no name for, canonically ordered.

        Diagnostic, and the reason :attr:`applies_to` tolerates them: a profile declaring a scope
        kind this version does not know is still a readable record, and the tag that will not
        match anything is better reported than refused at load. Note what this says about the
        profile: it is scoped by something we cannot evaluate, not that it is invalid.
        """
        return tuple(tag for tag in self.scope_tags if tag.known_kind is None)

    def scoped_to(self, tags: Iterable[str | ScopeTag | ProfileScopeTag]) -> bool:
        """Whether this profile's declared scope covers the supplied scopes. A hint, not a gate.

        A profile with **no** declared scope covers everything, because "not scoped" is what a
        baseline bundle means: it is the instrument set every regime inherits. A profile with
        declared scopes covers a tag set when *every* declared tag is satisfied - declared
        scopes are a conjunction ("this source, in this domain"), so a profile scoped to
        ``source=common_crawl`` and ``domain=finance`` does not apply to a record from another
        source even when the domain matches.

        The result answers one question: *which instruments were in play for this record?* It is
        never a statement about the record. A ``False`` here means the record was interpreted
        under a different regime, which is a fact to record in the context (FR-014) and never a
        reason to reject, refuse or drop anything (FR-007, FR-012).
        """
        if not self.applies_to:
            return True
        supplied = normalise_scope_tags(tags)
        return all(tag.satisfied_by(supplied) for tag in self.applies_to)

    def declares_type(self, type_ref: str) -> bool:
        """Whether this profile's *own* bundle lists a type ref. A widening hint, never a gate.

        ``False`` means "this profile did not list it", which is not a claim that the type is
        wrong, does not exist, or may not be recorded. Use it to decide whether a query could be
        usefully widened along this profile's vocabulary, or to attach regime context to a
        finding - nothing else. An entity whose type is absent from every profile is admitted
        with no error at all (FR-001, US1).
        """
        return normalize_type_ref(type_ref) in self.type_refs

    def declares_relation(self, relation_ref: str) -> bool:
        """Whether this profile's own bundle lists a relation ref. A widening hint, never a gate.

        Same reading as :meth:`declares_type`: it reports what the regime *carried*, and an
        unlisted relation is an admissible relation with no operator profile attached (FR-013).
        """
        return normalize_type_ref(relation_ref) in self.relation_refs

    def own_refs(self, kind: ProfileRefKind) -> tuple[str, ...]:
        """One of the five collections, this profile's own contribution, canonically ordered."""
        return tuple(getattr(self, _REF_FIELDS[ProfileRefKind(kind)]))

    def content_key(self) -> str:
        """Order-insensitive identity of the whole bundle, via the shared digest convention.

        Reuses :func:`semantic.contracts.content_key` so profiles, mappings, type assertions and
        relational objects are all addressed the same way in one graph rather than growing a
        second hashing dialect (constitution VII). Excludes ``mapping_id``-style bookkeeping and
        covers the parent, so a profile that changes its base is a different value - recorded as
        a new version rather than by mutating this one.
        """
        return content_key(
            {
                "profile": self.profile_id,
                "version": self.version,
                "parent": self.parent_profile,
                "tenant": self.tenant_id,
                "applies_to": [str(tag) for tag in self.scope_tags],
                "description": self.description,
                **{
                    name: list(getattr(self, name))
                    for name in _REF_COLLECTIONS
                },
            }
        )

    def __repr__(self) -> str:
        return (
            f"SemanticProfile(profile_id={self.profile_id!r}, version={self.version!r}, "
            f"types={len(self.type_refs)}, relations={len(self.relation_refs)}, "
            f"scopes={[str(tag) for tag in self.scope_tags]})"
        )


@dataclass(frozen=True)
class ProfileResolution:
    """One profile with its whole inheritance lineage resolved and the five bundles unioned.

    The lineage is ordered **root ancestor first, requested profile last**, so a caller reading it
    top-down reads the base regime and narrows to the specific one. Each inherited ref appears
    once, canonically ordered, because a child repeating its parent's type list is a restatement
    and not a second declaration.

    What this is *for* is deciding what was in play: which types, relations, vocabularies,
    constraints and mappings a record was interpreted against, and which profile in the lineage
    contributed each one (:meth:`declared_by`). Every query on it is a hint. There is no method
    here that returns a verdict about content, and a resolution that resolved cleanly for one
    record and not another says nothing whatsoever about which record is right.
    """

    profile: SemanticProfile
    lineage: tuple[SemanticProfile, ...] = ()

    type_refs: tuple[str, ...] = ()
    relation_refs: tuple[str, ...] = ()
    vocabulary_refs: tuple[str, ...] = ()
    constraint_refs: tuple[str, ...] = ()
    mapping_refs: tuple[str, ...] = ()

    scope_tags: frozenset[ScopeTag] = frozenset()

    def __post_init__(self) -> None:
        lineage = tuple(self.lineage)
        if not lineage:
            lineage = (self.profile,)
        if lineage[-1] is not self.profile:
            raise ValueError(
                "lineage must end at the resolved profile; got "
                f"{lineage[-1].version_ref!r} for {self.profile.version_ref!r}"
            )
        object.__setattr__(self, "lineage", lineage)
        for name in _REF_COLLECTIONS:
            object.__setattr__(self, name, tuple(sorted(getattr(self, name))))
        object.__setattr__(self, "scope_tags", normalise_scope_tags(self.scope_tags))

    @classmethod
    def build(
        cls, profile: SemanticProfile, lineage: tuple[SemanticProfile, ...]
    ) -> ProfileResolution:
        """Union a lineage's bundles into one resolution. The only path that computes them.

        The union is over the whole lineage, so inheritance needs no special handling at
        read time: a child that redeclares a parent ref changes nothing, and a child that
        declares nothing new still resolves to its parent's full bundle.
        """
        union: dict[str, set[str]] = {name: set() for name in _REF_COLLECTIONS}
        scopes: set[ScopeTag] = set()
        for member in lineage:
            for name in _REF_COLLECTIONS:
                union[name].update(getattr(member, name))
            scopes.update(member.applies_to)
        return cls(
            profile=profile,
            lineage=tuple(lineage),
            scope_tags=frozenset(scopes),
            **{name: tuple(sorted(values)) for name, values in union.items()},
        )

    @property
    def depth(self) -> int:
        """How many ancestors this resolution inherited through; ``0`` for a root profile."""
        return len(self.lineage) - 1

    @property
    def version_refs(self) -> tuple[str, ...]:
        """Every profile in the lineage, root first - the chain a reader can walk to audit it."""
        return tuple(member.version_ref for member in self.lineage)

    def refs(self, kind: ProfileRefKind) -> tuple[str, ...]:
        """One inherited collection, canonically ordered. A hint for widening or context."""
        return tuple(getattr(self, _REF_FIELDS[ProfileRefKind(kind)]))

    def has_type(self, type_ref: str) -> bool:
        """Whether this resolution's regime listed a type ref anywhere in the lineage.

        A **hint and a widening affordance, not a gate**: ``False`` means no profile in the
        lineage listed it, which says nothing about whether the type is correct or admissible
        (FR-001). It is for deciding "could a query widen along this regime?", never for
        deciding whether a record may be stored.
        """
        return normalize_type_ref(type_ref) in self.type_refs

    def has_relation(self, relation_ref: str) -> bool:
        """Whether the lineage listed a relation ref. A hint and a widening affordance, not a gate.

        An unlisted relation is still an admissible relation that simply had no profile attached
        when it arrived (FR-013), and the operator contract - not this profile - is what governs
        how it is extracted and validated (FR-006).
        """
        return normalize_type_ref(relation_ref) in self.relation_refs

    def declared_by(self, kind: ProfileRefKind, reference: str) -> tuple[str, ...]:
        """Which profiles in the lineage declared this ref, nearest first. Provenance, not a gate.

        Attribution rather than a yes/no, because "which regime contributed this type" is a
        question a reader of a finding needs answered and a single name would be a guess when
        several layers declared it. Empty means *no profile in the lineage declared it*, which is
        normal for world content and never a rejection.
        """
        wanted = normalize_type_ref(reference)
        field = _REF_FIELDS[ProfileRefKind(kind)]
        return tuple(
            member.version_ref
            for member in reversed(self.lineage)
            if wanted in getattr(member, field)
        )

    def content_key(self) -> str:
        """Identity of the resolved regime: the lineage plus the unioned bundles it produced.

        Two profiles resolved against the same registry state share this digest, which is what
        makes "did the regime change?" a decidable question when a profile version is promoted.
        """
        return content_key(
            {
                "profile": self.profile.version_ref,
                "lineage": list(self.version_refs),
                "tenant": self.profile.tenant_id,
                "scopes": [str(tag) for tag in sorted(self.scope_tags)],
                **{
                    name: list(getattr(self, name))
                    for name in _REF_COLLECTIONS
                },
            }
        )

    def __repr__(self) -> str:
        return (
            f"ProfileResolution(profile={self.profile.version_ref!r}, "
            f"lineage={list(self.version_refs)}, types={len(self.type_refs)})"
        )


class ProfileRegistry:
    """A tenant-scoped store of profiles with cycle-safe, memoised inheritance resolution.

    Answers the two questions a regime raises - "what was in play here?" and "which profiles
    apply to this record?" - and returns every answer as a canonically ordered ``tuple``. The
    ordering is total and value-based, so the answers are reproducible across processes and
    event-log rebuilds (constitution VI, VII).

    **There is no gate here, and the absence is the design.** No method asks whether content is
    acceptable against a profile, returns a pass/fail, or names a rejection;
    :meth:`applicable_profiles` and :meth:`not_applicable` are both descriptive of *regime
    membership* and neither is an input to any admission decision. A profile tells a caller
    which instruments were available,
    and a caller who wants to check content does it in :mod:`semantic.validation` and gets a
    graded finding attached to the assertion (FR-012).

    Registration is idempotent on content and refuses to rebind a key. Refusals are
    configuration-shaped only: a cross-tenant profile (:class:`TenantScopeRefused`) and a
    duplicate key with different content (:class:`ProfileIdCollision`). *Nothing* here refuses
    content - a term no profile mentions is a term the platform is required to admit (FR-001).

    Resolutions are memoised on success and re-derived on failure. A chain that resolved once
    cannot resolve differently, because profiles are frozen and content-addressed, so no
    invalidation path exists or is needed. A failure is not cached so that a rebuild registering
    children before parents converges on the next call instead of staying broken.
    """

    def __init__(self, tenant_id: str = "default-tenant") -> None:
        self._tenant_id = str(tenant_id).strip()
        self._by_key: dict[tuple[str, str], SemanticProfile] = {}
        self._by_content: dict[str, SemanticProfile] = {}
        self._by_type: dict[str, set[str]] = {}
        self._by_relation: dict[str, set[str]] = {}
        self._by_scope: dict[ScopeTag, set[tuple[str, str]]] = {}
        self._resolutions: dict[tuple[str, str], ProfileResolution] = {}

    @property
    def tenant_id(self) -> str:
        return self._tenant_id

    def __len__(self) -> int:
        return len(self._by_key)

    def __iter__(self) -> Iterator[SemanticProfile]:
        return iter(self.profiles())

    def __contains__(self, item: object) -> bool:
        needle = str(item).strip()
        if needle in self._by_key or needle in self._by_content:
            return True
        profile_id, version = _split_reference(needle)
        return (profile_id, version) in self._by_key

    def __repr__(self) -> str:
        return f"ProfileRegistry(tenant_id={self._tenant_id!r}, profiles={len(self)})"

    def register(self, profile: SemanticProfile) -> SemanticProfile:
        """Record one profile, or recognise it as already recorded.

        Idempotent on content: an identical profile re-registered is a no-op returning the stored
        object, so replaying a regime declaration cannot inflate the store or perturb any
        listing. A different bundle under the same ``(profile_id, version)`` raises
        :class:`ProfileIdCollision` rather than overwriting, because a version that changed
        underneath its references is precisely the silent rewrite constitution VII forbids -
        publish a new version instead.

        A profile naming a parent that is not yet registered is **accepted**: resolution raises
        :class:`UnknownProfileError` until the parent arrives, and succeeds afterwards. That is
        what makes a forward-only event-log rebuild work.
        """
        if profile.tenant_id and profile.tenant_id != self._tenant_id:
            raise TenantScopeRefused(profile.tenant_id, self._tenant_id)
        key = profile.identity
        existing = self._by_key.get(key)
        if existing is not None:
            if existing.content_key() == profile.content_key():
                return existing
            raise ProfileIdCollision(*key)
        self._by_key[key] = profile
        content = profile.content_key()
        self._by_content[content] = profile
        for ref in profile.type_refs:
            self._by_type.setdefault(ref, set()).add(content)
        for ref in profile.relation_refs:
            self._by_relation.setdefault(ref, set()).add(content)
        for tag in profile.applies_to:
            self._by_scope.setdefault(tag, set()).add(key)
        return profile

    def register_all(self, profiles: Iterable[SemanticProfile]) -> tuple[SemanticProfile, ...]:
        """Record several profiles, returning the stored objects in canonical order.

        Order of the input is irrelevant to the result, which is what makes an import of a
        profile bundle reproducible regardless of how the bundle was walked.
        """
        return tuple(sorted((self.register(profile) for profile in profiles), key=_order_key))

    def get(self, profile_id: str, version: str | None = None) -> SemanticProfile | None:
        """One profile by id, or by ``id@version``; ``None`` when unrecorded.

        Quietly ``None`` rather than raising, because a *query* about an unregistered profile is a
        normal answer in an open world (FR-001). This is a read; use :meth:`resolve` when you want
        a malformed parent chain to be reported rather than ignored.
        """
        name, embedded_version = _split_reference(profile_id)
        wanted_version = version if version is not None else embedded_version
        if wanted_version is None:
            versions = self.versions(name)
            if len(versions) != 1:
                return None
            wanted_version = versions[0]
        return self._by_key.get((name.strip(), str(wanted_version).strip()))

    def has(self, profile_id: str, version: str | None = None) -> bool:
        """Whether a profile is registered. A lookup, not a permit."""
        return self.get(profile_id, version) is not None

    def profiles(self) -> tuple[SemanticProfile, ...]:
        """Every registered profile, canonically ordered by ``(profile_id, version)``."""
        return tuple(sorted(self._by_key.values(), key=_order_key))

    def profile_ids(self) -> tuple[str, ...]:
        """Every registered ``profile_id``, canonically ordered, de-duplicated."""
        return tuple(sorted({profile_id for profile_id, _ in self._by_key}))

    def versions(self, profile_id: str) -> tuple[str, ...]:
        """Every registered version of one ``profile_id``, canonically ordered."""
        wanted = str(profile_id).strip()
        return tuple(sorted(version for pid, version in self._by_key if pid == wanted))

    def _select(self, profile_id: str, version: str | None) -> tuple[str, str]:
        """Resolve a reference to a store key, refusing to guess between several versions.

        ``version=None`` means the caller named a profile but not an iteration, which is
        unambiguous only when exactly one exists. Ambiguity and absence are both raised rather
        than smoothed over, so "which regime is in force" can never become a silent default.
        """
        name, embedded_version = _split_reference(profile_id)
        wanted = str(version).strip() if version is not None else embedded_version
        if wanted is not None:
            key = (name, wanted)
            if key not in self._by_key:
                raise UnknownProfileError(name, wanted)
            return key
        available = self.versions(name)
        if not available:
            raise UnknownProfileError(name)
        if len(available) > 1:
            raise AmbiguousProfileVersionError(name, available)
        return (name, available[0])

    def _lineage(self, key: tuple[str, str]) -> tuple[SemanticProfile, ...]:
        """Walk ``parent_profile`` to the root and return the chain, root first.

        Iterative with an explicit ``seen`` index, which is what makes a cyclic chain a typed
        error rather than a hang or a ``RecursionError``: the depth at which a key was first
        visited is recorded, so a repeat names the cycle exactly from the point it closed. The
        walk is bounded by :data:`MAX_INHERITANCE_DEPTH` and raises past it rather than stopping
        early, because a partially-resolved regime reports fewer instruments than were declared
        and looks perfectly normal.
        """
        chain: list[SemanticProfile] = []
        seen: dict[tuple[str, str], int] = {}
        current: tuple[str, str] | None = key
        while current is not None:
            repeat_at = seen.get(current)
            if repeat_at is not None:
                cycle = [member.version_ref for member in chain[repeat_at:]]
                cycle.append(f"{current[0]}@{current[1]}")
                raise ProfileCycleError(cycle)
            if len(chain) >= MAX_INHERITANCE_DEPTH:
                raise ProfileInheritanceTooDeep(f"{current[0]}@{current[1]}", MAX_INHERITANCE_DEPTH)
            seen[current] = len(chain)
            profile = self._by_key.get(current)
            if profile is None:
                raise UnknownProfileError(current[0], current[1])
            chain.append(profile)
            target = profile.parent_target()
            current = None if target is None else self._select(*target)
        return tuple(reversed(chain))

    def resolve(self, profile_id: str, version: str | None = None) -> ProfileResolution:
        """The profile with its inheritance lineage resolved and bundles unioned. Memoised.

        Every malformed parent chain is reported here as a typed error rather than tolerated: a
        cycle raises :class:`ProfileCycleError` naming the loop, a dangling parent raises
        :class:`UnknownProfileError`, an unqualified reference to a multiply-versioned profile
        raises :class:`AmbiguousProfileVersionError`, and a chain past the depth bound raises
        :class:`ProfileInheritanceTooDeep`. None of them hangs and none of them blows the stack.

        Only successes are memoised. That is safe indefinitely - profiles are frozen and
        content-addressed, so a resolved chain cannot later mean something else - while a failure
        is re-derived every call, so registering a missing parent makes the next call succeed.
        """
        key = self._select(profile_id, version)
        cached = self._resolutions.get(key)
        if cached is not None:
            return cached
        resolution = ProfileResolution.build(self._by_key[key], self._lineage(key))
        self._resolutions[key] = resolution
        return resolution

    def lineage(self, profile_id: str, version: str | None = None) -> tuple[SemanticProfile, ...]:
        """The inheritance chain for one profile, root ancestor first, requested profile last.

        Memoised through :meth:`resolve` so walking a chain and reading its union cost the same
        walk. Ancestors first is the useful order for a reader: it reads as the regime narrowing
        from the general base to the specific child.
        """
        return self.resolve(profile_id, version).lineage

    def applicable_profiles(
        self, tags: Iterable[str | ScopeTag | ProfileScopeTag] | str | ScopeTag | ProfileScopeTag
    ) -> tuple[SemanticProfile, ...]:
        """**Every** profile whose declared scope covers these tags, canonically ordered.

        Several matches are the normal case and this method is built for it: US2's entity is
        ``core:Entity`` observed, ``web:WebProfile`` observed, ``local:Influencer`` inferred and
        ``schema:Person`` mapped all at once, and the profiles that supply those layers are
        several profiles applying simultaneously. So the result is a ``tuple``, every match is in
        it, and there is no argument to narrow it and no sibling method that returns "the best
        match" - ranking would require declaring one profile more correct than another, which is
        the ontology-as-truth the scope guard forbids.

        Ordering is ``(profile_id, version)`` - total, value-based, independent of registration
        order - so the same registry state always produces the same answer (constitution VI).

        A tag set with no match yields ``()``. That is a record about *regime coverage* and never
        about the record it was asked about: an entity whose tags match no profile is admitted
        with a first-class local type and no error, which is US1 and FR-001 exactly.
        """
        supplied = normalise_scope_tags(tags)
        return tuple(
            sorted(
                (profile for profile in self._by_key.values() if profile.scoped_to(supplied)),
                key=_order_key,
            )
        )

    def applicable_resolutions(
        self, tags: Iterable[str | ScopeTag | ProfileScopeTag] | str | ScopeTag | ProfileScopeTag
    ) -> tuple[ProfileResolution, ...]:
        """:meth:`applicable_profiles` with each match's inherited bundle resolved, same order.

        The form to reach for when the question is "which instruments were in play", since it
        unions each profile's lineage rather than reporting one bundle. All matches are resolved
        and all are returned, on the same terms as :meth:`applicable_profiles` - no best match,
        no narrowing - and an empty result means the tag set matched no profile, which is a
        coverage fact and not a defect in anything the tag set was derived from.
        """
        applying = self.applicable_profiles(tags)
        return tuple(self.resolve(p.profile_id, p.version) for p in applying)

    def not_applicable(
        self, tags: Iterable[str | ScopeTag | ProfileScopeTag] | str | ScopeTag | ProfileScopeTag
    ) -> tuple[SemanticProfile, ...]:
        """The profiles whose scope does **not** cover these tags. Diagnostic only, never a gate.

        This is the "why did my profile not apply?" question, and it is worth answering because a
        tag vocabulary can only ever be the wrong way round: a profile scoped by a source name
        this pipeline never emits simply never matches, and without this method that is
        indistinguishable from a typo.

        It is emphatically not an error list. A profile appearing here says the record was
        interpreted under a different regime than that profile describes - a fact to record in
        the context (FR-014) and never a reason to reject, refuse, drop or refuse to project
        anything about the record (FR-007, FR-012). Do not wire this into an admission path; the
        platform has no such path.
        """
        supplied = normalise_scope_tags(tags)
        return tuple(
            sorted(
                (profile for profile in self._by_key.values() if not profile.scoped_to(supplied)),
                key=_order_key,
            )
        )

    def is_declared(self, profile_id: str, type_ref: str, version: str | None = None) -> bool:
        """Whether one profile's *own* bundle lists a type ref. A widening hint, not a gate.

        ``False`` means this profile did not list the type. It does not mean the type is
        inadmissible, incorrect, or should not be stored - a type absent from every profile is
        admitted with no error (FR-001, US1). Reach for this to decide whether widening a query
        along this profile would be useful, or to give a finding its regime context; never as an
        input to a decision about a record.
        """
        profile = self.get(profile_id, version)
        return profile is not None and profile.declares_type(type_ref)

    def hints_for_type(self, type_ref: str) -> tuple[str, ...]:
        """Every profile that lists this type in its own bundle, canonically ordered.

        A **retrieval and expansion affordance**: a caller widening a query, ranking a blocking
        key or rendering "which regimes mention this type?" uses this. It is a statement about
        the profiles, and it is empty for the overwhelming majority of world content, which is
        perfectly fine - an unlisted type is admitted and recorded all the same (FR-001).
        """
        wanted = normalize_type_ref(type_ref)
        return tuple(
            sorted(
                profile.version_ref
                for profile in self.profiles()
                if wanted in profile.type_refs
            )
        )

    def hints_for_relation(self, relation_ref: str) -> tuple[str, ...]:
        """Every profile that lists this relation in its own bundle, canonically ordered.

        A **retrieval and expansion affordance, not a gate**, and the same reading as
        :meth:`hints_for_type`. An unlisted relation is an admissible relation that happens to
        have no profile attached; what governs it is its operator contract (FR-006, FR-013), not
        any profile's silence.
        """
        wanted = normalize_type_ref(relation_ref)
        return tuple(
            sorted(
                profile.version_ref
                for profile in self.profiles()
                if wanted in profile.relation_refs
            )
        )

    def types(self) -> tuple[str, ...]:
        """Every type ref listed by some profile, canonically ordered - the declared inventory."""
        return tuple(sorted(self._by_type))

    def relations(self) -> tuple[str, ...]:
        """Every relation ref listed by some profile, canonically ordered."""
        return tuple(sorted(self._by_relation))

    def scope_tags(self) -> tuple[ScopeTag, ...]:
        """Every scope tag any profile declares, canonically ordered."""
        return tuple(sorted(self._by_scope))

    def scoped(self, tag: str | ScopeTag | ProfileScopeTag) -> tuple[SemanticProfile, ...]:
        """Profiles declaring this exact scope tag, canonically ordered.

        Descriptive of the declarations, not a matching operation: it answers "who declared
        ``source=common_crawl``?", which is different from :meth:`applicable_profiles` and does
        not depend on any tag being supplied by a record.
        """
        wanted = ScopeTag.from_value(tag)
        keys = self._by_scope.get(wanted, frozenset())
        return tuple(
            sorted((self._by_key[key] for key in keys), key=_order_key)
        )

    def content_key(self) -> str:
        """Order-insensitive identity of the whole registry.

        Over the registered ``(profile_id, version) -> content key`` pairs, so two registries that
        received the same profiles in different orders share one digest - which is what makes
        "did the declared regimes change?" a decidable question in a rebuild rather than an
        impression.
        """
        return content_key(
            {
                "tenant": self._tenant_id,
                "profiles": {
                    f"{pid}@{version}": self._by_content[content].content_key()
                    for (pid, version), content in sorted(
                        (key, profile.content_key()) for key, profile in self._by_key.items()
                    )
                },
            }
        )

    def snapshot(self) -> MappingProxyType:
        """An immutable read-only view of the registered profiles, in canonical order.

        A fresh copy rather than a live window, so a caller handed the whole registry cannot see
        it change underneath them - and cannot add to it either.
        """
        return MappingProxyType({profile.version_ref: profile for profile in self.profiles()})
