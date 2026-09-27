"""Mention -> entity resolution: the machine, in the order the architect named it.

``Mention -> Normalization -> Blocking -> Candidate generation -> Context compatibility ->
Temporal compatibility -> Source compatibility -> Collective/graph resolution -> Entity
hypothesis -> Resolution decision``.

This is a *continuation* of :mod:`semantic.blocking` and sits next to it for that reason.
Blocking answers "which comparisons are cheap"; everything after it answers "which of them are
true", and the second question is not answerable by narrowing. It is pure domain: no I/O, no
network, no clock (every timestamp arrives on the mention or the candidate), no model, no
randomness, no global state. Same input, same versions, same regime, same output ids - in this
process and in a fresh one (constitution VI).

**Why the old shape was wrong, stated as a fact rather than a preference.** The stub derived
the entity id from the mention: ``ENT-`` + digest(tenant, mention). That makes the *mention* the
entity. One mention then becomes one entity by construction, and a second mention can never join
it, because the id it would have to reuse was a function of a surface that is not in the id at
all. No amount of extra code on top of that base fixes it, because the base is what decides the
answer. This module replaces the base, and the replacement is visible in one line of the public
surface: :class:`ResolutionDecision` carries **two** identifiers, and they answer different
questions.

**Two-level identity, the same move the platform already makes elsewhere.** ``RL-``/``RC-`` on
relations, ``TA-``/``TAR-`` on type assertions, ``CAND-``/``CNDR-`` on candidates, and here
``ENT-``/``RES-`` on entities and resolutions:

* :attr:`ResolutionDecision.logical_entity_ref` - **which entity this is about.** Derived from a
  stable *anchor*: the deterministically-first mention that introduced the entity in the
  resolution scope (:func:`logical_entity_ref_for`). It does not change as evidence accumulates,
  because the anchor is **recorded, not recomputed** - see :class:`EntityAnchor`. A second and a
  third mention join the entity the first mention created; they do not re-elect it.
* :attr:`ResolutionDecision.resolution_decision_id` - **which resolution this was.** A content
  address over the merged mention set, the candidates considered, the compatibility evidence, the
  corroboration, the blocking reduction, the collective outcome and the verdict. It *does* change
  as evidence arrives, and that is the point: the audit trail grows while the identity holds.

An entity id derived from any single mention is unstable the moment more evidence arrives, and an
entity id derived from a *name* is unstable the moment a name is reused. Both are refused here.

**Normalization is where the semantic layer earns its keep.** A mention's surface form is turned
into comparison keys through :func:`semantic.vocabularies.normalize_surface_form` and
:func:`semantic.blocking.normalize_kind`, and then *widened* through the vocabulary facade -
:meth:`semantic.registry.SemanticRegistry.resolve_term`, ``.get_aliases()`` and ``.parents()``.
That is how ``"Acme"`` and ``"Acme Corporation"`` meet: not by string surgery here, but by asking a
vocabulary what labels one concept has (FR-015, US6, US8). Widening is a **query-time** decision
and asserts no equality whatsoever: expansion is recorded in the decision's normalisation record
and the two mentions are still two mentions.

**Blocking is delegated, never reimplemented.** :func:`semantic.blocking.block_for_relation` does
the narrowing, with :func:`semantic.blocking.affordance_kinds` reading the operator so the operator
decides what may stand in that role. One call is made per comparison key, because alias expansion
widened the query, and the union of the survivor sets is the candidate set. The reduction is a
**reportable fact** and is carried on the outcome as ``before_count``/``after_count``/
``reduction_ratio`` together with every individual :class:`~semantic.blocking.BlockingResult`
(SC-10, FR-016). Pruning asserts nothing: the pruned candidates come back as the original frozen
:class:`ResolutionCandidate` objects and the outcome records a fingerprint of the input universe so
a caller can verify that byte for byte.

**No filter is silent.** Every compatibility layer - context, temporal, source, type - returns
recorded :class:`CompatibilityReason` values with a graded :class:`ReasonVerdict`, and a candidate
is removed by *naming the reason that removed it*. Context refuses a cross-tenant candidate
outright (constitution IV: refused, not scored down); temporal records the two windows that failed
to overlap; source records how many *independent* groups stand behind the candidate; type records
itself as a hint. The type layer is the one place where the platform could quietly turn a
comparison into an assertion, and it is structurally prevented rather than promised: this module
never constructs a :class:`~semantic.contracts.TypeAssertion` and never rewrites a candidate, so a
pruned candidate cannot have gained a type by being pruned. The type assertions a mention already
carries are **read**, as hints, through the operator's ``subject_kinds``/``object_kinds``.

**The collective step is real, and it is guaranteed to stop.** The mention<->candidate bipartite
graph over the surviving candidates is closed under constraint propagation: a mention with exactly
one feasible candidate is *committed* (a committed mention never moves again), a candidate gains
*support* from the mentions committed to it, a mention whose only candidate is already held by a
committed mention loses it, a mention whose leader holds strictly more support than its runner-up
drops the runner-up, and a candidate that remains feasible for two mutually exclusive mentions is
reported *contested*. Termination is a proof, not a hope: with ``Phi = |E| + |M|`` the number of
graph edges plus the number of uncommitted mentions, a commit removes one mention from ``|M|`` and
each pruning rule removes at least one edge from ``|E|``, while nothing ever adds one - so every
firing strictly decreases a non-negative integer and at most ``|E| + |M|`` firings can happen. The
iteration order is canonical (mentions by ``mention_id``, candidates by sorted ref) so the run is
reproducible. An explicit ``collective_max_iterations`` cap is still honoured, and if it trips the
function returns the **pre-collective** result marked ``collective_applied=False`` and says so,
rather than looping or pretending it converged (constitution VIII).

**Ambiguity is a result, not a mess to be tidied away.** Two equally supported candidates yield
``AMBIGUOUS`` with **both** listed, because ``Mention -> Entity is solved`` must never be implied
by a resolver that quietly picked one. ``UNRESOLVED`` is likewise a first-class answer: a mention
that matches nothing gets no entity ref, not a synthetic one. ``CONFLICTED`` is reserved for a
winning candidate that is itself contested by mutually exclusive mentions - a state no scoring
function should be allowed to average away.

**Where identity is minted.** :class:`ResolutionCandidate` carries the entity's *established* ref
when it has one, and nothing at all when it does not. A candidate with an established ref keeps it,
so resolving against a real table never renames anything. A candidate with no ref gets a ref
minted from the anchor of the canonically-first mention that introduced it, and that minting is
recorded as an :class:`EntityAnchor` in the returned :class:`ResolutionScope` - which is the
mechanism that makes the third mention produce a new decision under the *same* entity.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from semantic.blocking import (
    BlockingResult,
    RelationRole,
    TypeHypothesis,
    UnknownKindPolicy,
    affordance_kinds,
    block_candidates,
    block_for_relation,
    normalize_kind,
)
from semantic.blocking import Candidate as BlockingCandidate
from semantic.contracts import SemanticRef, TypeAssertion, content_key
from semantic.registry import SemanticRegistry, SemanticRegistryError
from semantic.vocabularies import normalize_surface_form

__all__ = [
    "BlockingOutcome",
    "CollectiveOutcome",
    "CollectiveRemoval",
    "CompatibilityEvidence",
    "CompatibilityLayer",
    "CompatibilityReason",
    "EntityAnchor",
    "EntityHypothesis",
    "MentionResolver",
    "NormalizedSurface",
    "ReasonVerdict",
    "ResolutionBatch",
    "ResolutionCandidate",
    "ResolutionDecision",
    "ResolutionMention",
    "ResolutionScope",
    "ResolutionVerdict",
    "analyse_candidate",
    "collective_resolution",
    "logical_entity_ref_for",
    "mutually_exclusive",
    "normalize_mention",
    "resolution_scope_for",
    "vocabulary_name_keys",
]

#: ``ENT-`` names *which entity*; it is anchored on a mention and holds as evidence accumulates.
ENTITY_ID_PREFIX = "ENT-"

#: ``RES-`` names *which resolution*, and is a content address that moves with the evidence.
RESOLUTION_ID_PREFIX = "RES-"

#: The resolution scope's own identifier: the tenant and investigation a resolution is local to.
SCOPE_ID_PREFIX = "SCOPE-"

#: A record in the candidate universe that has no established identity yet.
#:
#: Deliberately **not** ``ENT-``. Minting an ``ENT-`` from a name is the exact defect this module
#: was written to remove, so a candidate without an identity is named by a key that says so and
#: cannot be mistaken for an entity. It exists only to give blocking a stable sort field.
UNIDENTIFIED_PREFIX = "NEW-"

#: The deterministic iteration bound for the collective pass (constitution VIII).
DEFAULT_COLLECTIVE_MAX_ITERATIONS = 16

_CONF_BASE = 0.5
_CONF_DECISIVE = 0.2
_CONF_AMBIGUOUS = -0.1
_CONF_CONTESTED = -0.25
_CONF_NO_SURVIVOR = -0.4
_CONF_CORROBORATION_STEP = 0.05
_CONF_CORROBORATION_CAP = 0.15
_CONF_COLLECTIVE = 0.1
_CONF_SAME_SOURCE_ONLY = -0.1
_CONF_WEAKENED_STEP = -0.05
_CONF_WEAKENED_CAP = 3


class ResolutionVerdict(StrEnum):
    """What a resolution concluded. All four are results; none of them is an error.

    ``RESOLVED`` means one candidate survived decisively. ``AMBIGUOUS`` means more than one did and
    the resolver declined to pick - the honest report, and the one the architect was explicit
    about. ``UNRESOLVED`` means nothing survived, so there is no entity to name. ``CONFLICTED``
    means the best-supported candidate is itself claimed by two mutually exclusive mentions, which
    is a contradiction rather than an ambiguity and must not be averaged into one.
    """

    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"
    CONFLICTED = "conflicted"

    @property
    def is_resolved(self) -> bool:
        """Whether this verdict names exactly one entity. Only ``RESOLVED`` does."""
        return self is ResolutionVerdict.RESOLVED

    @property
    def is_settled(self) -> bool:
        """Whether the resolver is done reasoning; ``AMBIGUOUS`` needs a human or more evidence."""
        return self in (ResolutionVerdict.RESOLVED, ResolutionVerdict.UNRESOLVED)


class ReasonVerdict(StrEnum):
    """The graded outcome of one compatibility check on one candidate.

    Graded rather than boolean, for the reason :class:`~semantic.contracts.Verdict` exists: a
    check that could not be evaluated must be able to say so instead of collapsing into pass or
    fail (FR-011, SC-9). ``UNEVALUATED`` is what a check with nothing to compare against returns,
    and it never removes a candidate - unknown is not contrary.
    """

    SUPPORTED = "supported"
    WEAKENED = "weakened"
    CONFLICT = "conflict"
    REFUSED = "refused"
    UNEVALUATED = "unevaluated"


class CompatibilityLayer(StrEnum):
    """The four filters, in the order the architect named them."""

    CONTEXT = "context"
    TEMPORAL = "temporal"
    SOURCE = "source"
    TYPE = "type"

    def rank(self) -> int:
        """Position in the order the layers run and are reported in."""
        return _LAYER_RANK[self]


_LAYER_RANK: dict[CompatibilityLayer, int] = {
    layer: index for index, layer in enumerate(CompatibilityLayer)
}


@dataclass(frozen=True)
class ResolutionMention:
    """One unresolved mention, as resolution sees it: a surface plus its whole frame.

    Not a copy of anyone else's ``Mention`` type - this is a *position* in a resolution, and it
    carries the context, temporal and provenance facts the compatibility layers have to compare.
    ``role`` decides which end of the relation operator's affordances applies, so a person mention
    and an organisation mention in the same sentence are narrowed by different declared kinds
    (US7). Every timestamp is the caller's; nothing here reads a clock.

    ``type_assertions`` are the typing claims this mention already carries, in whatever layers
    exist, and they are consulted **as hints only**. ``declared_type_refs`` is the weaker fallback
    for a caller that has not built assertions yet. Neither ever reaches a candidate: a type
    hypothesis narrows a comparison and is discarded with it (FR-016).
    """

    mention_id: str
    surface: str
    kind: str = ""
    role: RelationRole = RelationRole.OBJECT
    tenant_id: str = "default-tenant"
    investigation_id: str = ""
    source_id: str = ""
    source_family: str = ""
    independence_group: str = ""
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    observed_at: datetime | None = None
    profile_id: str = ""
    profile_version: str = ""
    ontology_version: str = ""
    normalization_version: str = ""
    regime_id: str = ""
    declared_type_refs: tuple[str, ...] = ()
    type_assertions: tuple[TypeAssertion, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "mention_id", str(self.mention_id).strip())
        object.__setattr__(self, "surface", str(self.surface))
        object.__setattr__(self, "role", RelationRole(self.role))
        object.__setattr__(self, "declared_type_refs", tuple(self.declared_type_refs))
        object.__setattr__(self, "type_assertions", tuple(self.type_assertions))

    def type_refs(self) -> tuple[tuple[str, SemanticRef], ...]:
        """Every type this mention carries, with the vocabulary it was framed in.

        The recorded ``TypeAssertion`` layers come first because they carry a scheme and an
        evidence chain; the bare declared refs follow as a scheme-less fallback. Ordered by
        ``(type_ref, scheme)`` so a mention's hypothesis set is a pure function of its content.
        """
        seen: set[tuple[str, str]] = set()
        pairs: list[tuple[str, SemanticRef]] = []
        for assertion in self.type_assertions:
            key = (str(assertion.type_ref).strip(), str(assertion.type_scheme))
            if not key[0] or key in seen:
                continue
            seen.add(key)
            pairs.append((key[0], assertion.type_scheme))
        for ref in self.declared_type_refs:
            key = (str(ref).strip(), str(SemanticRef.INTERNAL))
            if not key[0] or key in seen:
                continue
            seen.add(key)
            pairs.append((key[0], SemanticRef.INTERNAL))
        return tuple(sorted(pairs, key=lambda pair: (pair[0], str(pair[1]))))

    def type_hint_source(self) -> str:
        """Which of the two type inputs actually said something, for the recorded reason.

        ``"assertion"``, ``"declared"`` or ``"absent"``. Absent is an answer, not a defect: a
        mention nobody has typed is compared on the other layers alone rather than refused.
        """
        if any(str(a.type_ref).strip() for a in self.type_assertions):
            return "assertion"
        if any(str(ref).strip() for ref in self.declared_type_refs):
            return "declared"
        return "absent"

    def independence_key(self) -> str:
        """The group corroboration must *differ* from to count as independent.

        Prefers the declared independence group, falls back to the source family, and finally to
        the source itself. An undeclared group therefore degrades to "same family", which is the
        conservative direction: it is harder to earn corroboration, never easier.
        """
        return (
            self.independence_group.strip()
            or self.source_family.strip()
            or self.source_id.strip()
        )


@dataclass(frozen=True)
class ResolutionCandidate:
    """One record in the candidate universe, with everything the layers compare.

    Frozen because it is an *input to a comparison*, not a place to record a conclusion. If
    resolution could write to its candidates, "pruning asserts nothing" would be a promise rather
    than a fact - so this module never calls ``replace`` on one, never constructs a
    :class:`~semantic.contracts.TypeAssertion`, and :attr:`BlockingOutcome.universe_fingerprint`
    lets a caller verify the whole universe came through byte for byte.

    ``entity_ref`` is the entity's **established** identity when it has one, and empty when it does
    not. That distinction is the whole of the anchoring story: an established ref is adopted and
    never renamed, and an absent one is the case where :func:`logical_entity_ref_for` mints a ref
    from the anchor mention. ``support_mention_ids`` / ``supporting_groups`` are what make "a
    second mention joined this entity" a fact on the candidate rather than a claim in prose.
    """

    entity_ref: str = ""
    name: str = ""
    kind: str = ""
    type_refs: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    tenant_id: str = "default-tenant"
    investigation_id: str = ""
    profile_id: str = ""
    profile_version: str = ""
    ontology_version: str = ""
    normalization_version: str = ""
    regime_id: str = ""
    source_family: str = ""
    independence_group: str = ""
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    observed_at: datetime | None = None
    support_mention_ids: tuple[str, ...] = ()
    supporting_groups: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "entity_ref", str(self.entity_ref).strip())
        object.__setattr__(self, "name", str(self.name))
        object.__setattr__(self, "kind", str(self.kind))
        object.__setattr__(self, "aliases", tuple(self.aliases))
        object.__setattr__(self, "type_refs", tuple(self.type_refs))
        object.__setattr__(
            self, "support_mention_ids", tuple(sorted(set(self.support_mention_ids)))
        )
        object.__setattr__(
            self, "supporting_groups", tuple(sorted(set(self.supporting_groups)))
        )

    @property
    def has_established_ref(self) -> bool:
        """Whether this record already has an identity, and therefore keeps it."""
        return bool(self.entity_ref)

    def identity_ref(self) -> str:
        """A stable sort key for the universe, honest about whether identity exists.

        An established entity is named by its own ref. A record with no ref is named by a ``NEW-``
        key over its own content, which is emphatically **not** an entity identity: it says "a
        record in the universe, not yet identified", and it never reaches a decision.
        """
        if self.entity_ref:
            return self.entity_ref
        return UNIDENTIFIED_PREFIX + content_key(
            {"name": self.name, "kind": self.kind, "tenant": self.tenant_id}
        )[:16]

    def name_keys(self) -> tuple[str, ...]:
        """Every normalised name this record answers to: its own plus recorded aliases."""
        keys = {normalize_surface_form(self.name)}
        keys.update(normalize_surface_form(alias) for alias in self.aliases)
        return tuple(sorted(key for key in keys if key))

    def to_blocking_candidate(self) -> BlockingCandidate:
        """Project onto the shape :mod:`semantic.blocking` compares, and nothing more.

        A projection, not a conversion: the blocking call sees the name, the kind and the recorded
        type references and has no access to anything else about this record - so it structurally
        cannot annotate it, and the original frozen object comes back out untouched.
        """
        return BlockingCandidate(
            entity_ref=self.identity_ref(),
            name=self.name,
            kind=self.kind,
            type_refs=self.type_refs,
        )

    def to_blocking_candidates(self) -> tuple[BlockingCandidate, ...]:
        """One projection per surface this record answers to: its name and each alias.

        :meth:`to_blocking_candidate` alone is wrong for comparison, and silently so. The
        default blocking key is ``name|kind`` -- see
        :func:`semantic.blocking.candidate_blocking_key` -- so a record whose aliases are
        dropped here answers only to its primary name. A mention of "Acme" then never meets
        a record named "Acme Holdings" that records `acme` as an alias, and the resolver
        reports ``unresolved`` while the recorded alias sits unread on the record. The
        failure looks like absence of evidence rather than a dropped key, which is the
        worst way for it to look.

        One projection per surface rather than a widened key keeps
        :mod:`semantic.blocking` untouched: it still sees exactly the shape it compares,
        and it still owns the normalisation, so the raw surfaces are passed through rather
        than pre-normalised. Every projection carries the same ``entity_ref``, so the
        survivor set collapses to one entry per record and the reduction ratio stays a
        count of *records* rather than of alias rows.
        """
        surfaces = (self.name, *self.aliases)
        projected = [
            BlockingCandidate(
                entity_ref=self.identity_ref(),
                name=surface,
                kind=self.kind,
                type_refs=self.type_refs,
            )
            for surface in surfaces
            if str(surface).strip()
        ]
        if not projected:
            return (self.to_blocking_candidate(),)
        return tuple(projected)

    def content_key(self) -> str:
        """Order-insensitive identity of this record as supplied to the comparison."""
        return content_key(
            {
                "entity": self.entity_ref,
                "name": self.name,
                "kind": self.kind,
                "types": list(self.type_refs),
                "aliases": list(self.aliases),
                "tenant": self.tenant_id,
                "investigation": self.investigation_id,
                "profile": [self.profile_id, self.profile_version],
                "ontology": self.ontology_version,
                "normalization": self.normalization_version,
                "regime": self.regime_id,
                "source_family": self.source_family,
                "independence_group": self.independence_group,
                "valid_from": str(self.valid_from) if self.valid_from else None,
                "valid_to": str(self.valid_to) if self.valid_to else None,
                "observed_at": str(self.observed_at) if self.observed_at else None,
                "support_mentions": list(self.support_mention_ids),
                "support_groups": list(self.supporting_groups),
            }
        )


@dataclass(frozen=True)
class EntityAnchor:
    """Which mention introduced an entity in a scope, recorded so it never has to be re-derived.

    This is the load-bearing record of the whole module. If the anchor were recomputed from the
    mentions currently in hand, then a third mention that sorts *before* the first would silently
    re-elect it and the entity's identity would move - the precise instability two-level identity
    exists to prevent. So the anchor is written once, keyed by the entity it belongs to, and later
    batches are *attached* to it. :class:`ResolutionScope` is the frozen carrier, and
    :meth:`MentionResolver.resolve` hands back the updated one for the caller to persist.
    """

    logical_entity_ref: str
    anchor_mention_id: str
    anchor_key: str = ""
    candidate_ref: str = ""
    established_by_decision: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "logical_entity_ref", str(self.logical_entity_ref).strip())
        object.__setattr__(self, "anchor_mention_id", str(self.anchor_mention_id).strip())
        object.__setattr__(self, "anchor_key", str(self.anchor_key))
        object.__setattr__(self, "candidate_ref", str(self.candidate_ref).strip())

    def content_key(self) -> str:
        """Identity of the anchor, so a scope rebuild is comparable across processes."""
        return content_key(
            {
                "entity": self.logical_entity_ref,
                "anchor_mention": self.anchor_mention_id,
                "anchor_key": self.anchor_key,
                "candidate": self.candidate_ref,
                "established_by": self.established_by_decision,
            }
        )


@dataclass(frozen=True)
class ResolutionScope:
    """The tenant and investigation a resolution is local to, plus its recorded anchors.

    One scope per ``(tenant, investigation)``, which is the boundary a fail-closed resolver needs:
    a mention outside the scope's tenant is not compared against anything at all (constitution IV).
    Frozen, and :meth:`with_anchor` returns a new scope rather than mutating this one, so a scope
    handed to two resolvers cannot change under either.
    """

    scope_id: str = ""
    tenant_id: str = "default-tenant"
    investigation_id: str = ""
    anchors: tuple[EntityAnchor, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "anchors", tuple(self.anchors))

    def anchor_for(self, ref: str) -> EntityAnchor | None:
        """The recorded anchor for an entity, found by its entity ref or by its candidate's ref.

        Two lookups rather than one because both halves matter: a batch resolving against a
        universe that already carries the entity should find the anchor the *first* time it
        introduces it, and a batch resolving against a universe that has since learned the minted
        ref should find the same anchor through the other key.
        """
        wanted = str(ref).strip()
        for anchor in self.anchors:
            if anchor.logical_entity_ref == wanted or anchor.candidate_ref == wanted:
                return anchor
        return None

    def with_anchors(self, anchors: Iterable[EntityAnchor]) -> ResolutionScope:
        """A new scope carrying these anchors too. Existing anchors are never rewritten.

        The first anchor recorded for an entity wins, and later ones are dropped, which is what
        makes identity monotone: once an entity has an anchor, no amount of later evidence can
        replace it.
        """
        by_entity: dict[str, EntityAnchor] = {}
        for anchor in (*self.anchors, *anchors):
            if not anchor.logical_entity_ref:
                continue
            by_entity.setdefault(anchor.logical_entity_ref, anchor)
        return ResolutionScope(
            scope_id=self.scope_id,
            tenant_id=self.tenant_id,
            investigation_id=self.investigation_id,
            anchors=tuple(by_entity[ref] for ref in sorted(by_entity)),
        )

    def content_key(self) -> str:
        """Identity of the scope and every anchor in it, canonically ordered."""
        return content_key(
            {
                "scope": self.scope_id,
                "tenant": self.tenant_id,
                "investigation": self.investigation_id,
                "anchors": [anchor.content_key() for anchor in self.anchors],
            }
        )


def resolution_scope_for(tenant_id: str, investigation_id: str = "") -> ResolutionScope:
    """The scope every resolution in one ``(tenant, investigation)`` shares, addressed by content.

    Derived from its own coordinates so two callers naming the same boundary get the same scope id
    and therefore the same ``ENT-`` addresses, with no registry and no clock.
    """
    tenant = str(tenant_id).strip() or "default-tenant"
    investigation = str(investigation_id).strip()
    return ResolutionScope(
        scope_id=SCOPE_ID_PREFIX
        + content_key({"tenant": tenant, "investigation": investigation}),
        tenant_id=tenant,
        investigation_id=investigation,
    )


def logical_entity_ref_for(tenant_id: str, scope_id: str, anchor_mention_id: str) -> str:
    """``ENT-`` + digest of ``(tenant, scope, anchor mention)`` - the entity's stable identity.

    Deliberately a function of the **anchor mention id** and of nothing else. Not of the surface
    form, so ``"Acme"`` and ``"Acme Corporation"`` can be the same entity; not of the name at all,
    so a rename is not a re-identification; not of the evidence set, so the third mention does not
    move it. What makes it *hold* rather than merely *look* stable is that the anchor it names is
    recorded in a :class:`ResolutionScope` once and reused, so the value is not recomputed from a
    growing mention set.
    """
    return ENTITY_ID_PREFIX + content_key(
        {
            "tenant": str(tenant_id).strip() or "default-tenant",
            "scope": str(scope_id).strip(),
            "anchor_mention": str(anchor_mention_id).strip(),
        }
    )


@dataclass(frozen=True)
class NormalizedSurface:
    """A mention's comparison keys: the surface, its kind, and what the vocabulary widened it to.

    :attr:`comparison_keys` is a *query-time widening* of the surface, not a rewriting of it: the
    raw form is retained on the mention and on the decision, so FR-004's ladder from raw text to
    resolved entity stays reconstructable. :attr:`type_hints` carries the broader concepts the
    surface reached, which the type layer consults as a hint about kind and which must never
    become a type on a candidate.
    """

    mention_id: str
    raw_surface: str
    surface_key: str
    kind_key: str
    comparison_keys: tuple[str, ...] = ()
    concept_refs: tuple[str, ...] = ()
    type_hints: tuple[str, ...] = ()
    expanded: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "comparison_keys", tuple(self.comparison_keys))
        object.__setattr__(self, "concept_refs", tuple(self.concept_refs))
        object.__setattr__(self, "type_hints", tuple(self.type_hints))

    def content_key(self) -> str:
        """Identity of the normalisation: a wider query is a different query, so this differs."""
        return content_key(
            {
                "mention": self.mention_id,
                "raw": self.raw_surface,
                "surface_key": self.surface_key,
                "kind_key": self.kind_key,
                "keys": list(self.comparison_keys),
                "concepts": list(self.concept_refs),
                "type_hints": list(self.type_hints),
                "expanded": self.expanded,
            }
        )


def vocabulary_name_keys(
    registry: SemanticRegistry | None,
    surface: str,
    tenant_id: str = "default-tenant",
) -> tuple[tuple[str, tuple[str, ...], tuple[str, ...]], str, tuple[str, ...]]:
    """Ask the vocabulary what else this surface may be called, and what it may be.

    Returns ``(name keys, concept refs, broader type hints)``. Three uses of one facade, kept
    separate on purpose:

    * ``resolve_term`` first, because ``get_aliases`` looks a concept up **by id** and a surface
      form is not a concept id.
    * ``get_aliases(concept)`` widens the *name* comparison set. This is how ``"Acme"`` meets
      ``"Acme Corporation"`` and it is the retrieval instrument FR-015 and US8 are about.
    * ``parents(concept)`` widens the *type* hint set only. A broader concept is a statement about
      kind, never about name, so ``"Public Company"`` must not make the name ``"Organization"``
      comparable - that would merge records on a hierarchy link and assert an equivalence SKOS
      does not record (FR-008).

    No registry, or a term the registry does not contain, yields exactly the surface's own
    normalised key. Absence is a normal answer here and raises nothing (FR-001).
    """
    own = normalize_surface_form(surface)
    if registry is None or not own:
        return ((own,) if own else ()), (), ()
    resolved = registry.resolve_term(surface, tenant_id=tenant_id)
    names: set[str] = {own}
    concepts: list[str] = []
    type_hints: set[str] = set()
    for concept in resolved.concepts:
        concepts.append(concept.concept_id)
        for label in registry.get_aliases(concept.concept_id, tenant_id=tenant_id):
            key = normalize_surface_form(label)
            if key:
                names.add(key)
        for parent in registry.parents(concept.concept_id, tenant_id=tenant_id):
            parent_key = normalize_surface_form(parent)
            if parent_key:
                type_hints.add(parent_key)
    return (
        tuple(sorted(names)),
        tuple(sorted(set(concepts))),
        tuple(sorted(type_hints)),
    )


def normalize_mention(
    mention: ResolutionMention,
    registry: SemanticRegistry | None = None,
) -> NormalizedSurface:
    """Turn one mention's surface form into the keys the rest of the machine compares on.

    Two normalisations, both reused rather than reimplemented: the surface through
    :func:`semantic.vocabularies.normalize_surface_form` and the kind through
    :func:`semantic.blocking.normalize_kind`, so this module and the blocking it delegates to
    cannot drift on what "the same name" means. Alias expansion is the third step and comes from
    the vocabulary facade.
    """
    surface_key = normalize_surface_form(mention.surface)
    kind_key = normalize_kind(mention.kind or mention.role)
    keys, concepts, type_hints = vocabulary_name_keys(registry, mention.surface, mention.tenant_id)
    if not keys and surface_key:
        keys = (surface_key,)
    return NormalizedSurface(
        mention_id=mention.mention_id,
        raw_surface=mention.surface,
        surface_key=surface_key,
        kind_key=kind_key,
        comparison_keys=keys,
        concept_refs=concepts,
        type_hints=type_hints,
        expanded=len(keys) > 1,
    )


def type_hypotheses_for(
    mention: ResolutionMention,
    normalized: NormalizedSurface,
) -> tuple[TypeHypothesis, ...]:
    """The mention's typing as :class:`semantic.blocking.TypeHypothesis`, narrowed to the kind.

    Built from what the mention already carries and discarded with the comparison. A hypothesis has
    no evidence, no scope and no status ladder, and there is no field on it that could survive into
    a record - which is the structural reason a pruned candidate cannot have gained a type.
    """
    pairs = mention.type_refs()
    if not pairs and normalized.kind_key:
        pairs = ((normalized.kind_key, SemanticRef.INTERNAL),)
    return tuple(
        TypeHypothesis(type_ref=ref, scheme=scheme) for ref, scheme in pairs
    )


@dataclass(frozen=True)
class BlockingOutcome:
    """What blocking cost, what it bought, and which comparison keys did the work.

    One :func:`semantic.blocking.block_candidates` run per comparison key, because alias expansion
    widened the query, and this is the union of the survivor sets. The aggregate
    :attr:`before_count` / :attr:`after_count` / :attr:`reduction_ratio` are the *reported* outcome
    (SC-10, FR-016); :attr:`results` holds every individual
    :class:`~semantic.blocking.BlockingResult` so a reduction of ``0.8`` can be attributed to a
    key rather than merely asserted.

    :attr:`universe_fingerprint` is the content key of every input record, in canonical order. It is
    the check behind "pruning asserts nothing": a caller can recompute it after the resolution and
    see that no candidate was re-typed, re-named or otherwise annotated on the way through.
    """

    role: RelationRole = RelationRole.OBJECT
    before_count: int = 0
    after_count: int = 0
    results: tuple[BlockingResult, ...] = ()
    survivor_refs: tuple[str, ...] = ()
    pruned_refs: tuple[str, ...] = ()
    hypotheses: tuple[TypeHypothesis, ...] = ()
    allowed_kinds: tuple[str, ...] = ()
    query_keys: tuple[str, ...] = ()
    type_hypotheses_offered: tuple[TypeHypothesis, ...] = ()
    unknown_kind_retained: int = 0
    universe_fingerprint: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "role", RelationRole(self.role))
        object.__setattr__(self, "results", tuple(self.results))
        object.__setattr__(self, "survivor_refs", tuple(self.survivor_refs))
        object.__setattr__(self, "pruned_refs", tuple(self.pruned_refs))
        object.__setattr__(self, "hypotheses", tuple(self.hypotheses))
        object.__setattr__(self, "allowed_kinds", tuple(self.allowed_kinds))
        object.__setattr__(self, "query_keys", tuple(self.query_keys))
        object.__setattr__(self, "type_hypotheses_offered", tuple(self.type_hypotheses_offered))
        object.__setattr__(self, "universe_fingerprint", tuple(self.universe_fingerprint))
        object.__setattr__(self, "notes", tuple(self.notes))

    @property
    def pruned_count(self) -> int:
        """How many records this comparison did not propose. Never a deletion count."""
        return max(self.before_count - self.after_count, 0)

    @property
    def reduction_ratio(self) -> float:
        """Fraction of the universe this mention's comparison did not propose, in ``0.0..1.0``.

        Computed over the *union* of the per-key survivor sets, because that union is the set the
        rest of the machine actually considered. ``0.0`` for an empty universe as well as for no
        pruning: reporting ``0/0`` as a saving would invent one.
        """
        if self.before_count <= 0:
            return 0.0
        return self.pruned_count / self.before_count

    @property
    def reduction_factor(self) -> float | None:
        """How many times smaller the comparison set became; ``None`` when nothing was left."""
        if self.after_count <= 0:
            return None
        return self.before_count / self.after_count

    def content_key(self) -> str:
        """Identity of the whole blocking operation, reduction and per-key results included."""
        return content_key(
            {
                "role": str(self.role),
                "before": self.before_count,
                "after": self.after_count,
                "survivors": list(self.survivor_refs),
                "pruned": list(self.pruned_refs),
                "keys": list(self.query_keys),
                "allowed_kinds": list(self.allowed_kinds),
                "offered_hypotheses": [
                    [item.type_ref, str(item.scheme)] for item in self.type_hypotheses_offered
                ],
                "results": [result.content_key() for result in self.results],
                "universe": list(self.universe_fingerprint),
                "notes": list(self.notes),
            }
        )


def block_mention(
    mention: ResolutionMention,
    normalized: NormalizedSurface,
    universe: tuple[ResolutionCandidate, ...],
    operator: object | None,
    *,
    unknown_policy: UnknownKindPolicy = UnknownKindPolicy.RETAIN,
) -> BlockingOutcome:
    """Delegate the narrowing, once per comparison key, and report the reduction.

    The delegate is :func:`semantic.blocking.block_for_relation` when an operator is supplied, so
    the *operator* decides which kinds may stand in this mention's role via
    :func:`semantic.blocking.affordance_kinds`, and a caller cannot re-derive that wrongly. With no
    operator the call is the bare :func:`semantic.blocking.block_candidates`, which is the correct
    behaviour rather than a fallback: a relation with no domain/range hints is still a perfectly
    good relation (FR-013), and blocking must not read the absence of a hint as a restriction.

    **The one narrowing this function declines to delegate.** The mention's type hypotheses are
    offered to blocking *only if some record in the universe actually carries one of them*.
    Otherwise the ``TYPE`` stage would prune every typed record for the sole reason that the
    mention's type is one nobody has recorded - which is pruning on an absent fact, and an
    assertion by omission (FR-001, and exactly the ``UnknownKindPolicy.RETAIN`` reasoning applied
    to types). A hypothesis that discriminates nothing is not a filter, so it is withheld, and
    :attr:`BlockingOutcome.notes` says so; the hypotheses that *were* offered are still on
    :attr:`BlockingOutcome.type_hypotheses_offered`, so nothing is hidden.
    """
    offered = type_hypotheses_for(mention, normalized)
    offered_refs = frozenset(hypothesis.reference() for hypothesis in offered)
    informative = bool(offered_refs) and any(
        offered_refs & frozenset(candidate.type_refs) for candidate in universe
    )
    hypotheses = offered if informative else ()
    notes: tuple[str, ...] = ()
    if offered and not informative:
        notes = (
            f"the mention's type hypotheses {[h.type_ref for h in offered]} share no reference "
            f"with any of the {len(universe)} records in the universe, so the type stage would "
            "discriminate nothing and was withheld; pruning on an absent fact is an assertion "
            "by omission, not a narrowing (FR-001)",
        )
    kinds = affordance_kinds(operator, mention.role) if operator is not None else ()
    projected: list[BlockingCandidate] = []
    for candidate in universe:
        projected.extend(candidate.to_blocking_candidates())
    keys = normalized.comparison_keys
    if not keys:
        keys = (normalized.surface_key,) if normalized.surface_key else ()
    results: list[BlockingResult] = []
    survivor_refs: list[str] = []
    for key in keys:
        if operator is None:
            result = block_candidates(
                projected,
                hypotheses,
                kinds,
                query_name=key,
                unknown_policy=unknown_policy,
            )
        else:
            result = block_for_relation(
                projected,
                hypotheses,
                operator,
                mention.role,
                query_name=key,
                unknown_policy=unknown_policy,
            )
        results.append(result)
        survivor_refs.extend(candidate.entity_ref for candidate in result.candidates)
    ordered_survivors = tuple(sorted(set(survivor_refs)))
    retained = max((result.unknown_kind_retained for result in results), default=0)
    return BlockingOutcome(
        role=RelationRole(mention.role),
        before_count=len(universe),
        after_count=len(ordered_survivors),
        results=tuple(results),
        survivor_refs=ordered_survivors,
        pruned_refs=tuple(
            ref
            for ref in sorted(
                {candidate.identity_ref() for candidate in universe} - set(ordered_survivors)
            )
        ),
        hypotheses=hypotheses,
        allowed_kinds=tuple(kinds),
        query_keys=tuple(keys),
        type_hypotheses_offered=offered,
        unknown_kind_retained=retained,
        universe_fingerprint=tuple(candidate.content_key() for candidate in universe),
        notes=notes,
    )


@dataclass(frozen=True)
class CompatibilityReason:
    """One recorded judgement by one layer about one candidate.

    Frozen, addressed by content, and carrying its own graded verdict: a filter that removed a
    candidate must be able to say *which* filter and *why*, and a filter that could not be
    evaluated must be able to say that too. ``detail`` holds the specifics - the two windows that
    failed to overlap, the two tenants, the counts - so the record is auditable rather than
    merely present.
    """

    candidate_ref: str
    layer: CompatibilityLayer
    code: str
    verdict: ReasonVerdict
    detail: str = ""
    delta: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_ref", str(self.candidate_ref).strip())
        object.__setattr__(self, "layer", CompatibilityLayer(self.layer))
        object.__setattr__(self, "verdict", ReasonVerdict(self.verdict))
        object.__setattr__(self, "detail", str(self.detail))
        object.__setattr__(self, "delta", float(self.delta))

    def content_key(self) -> str:
        """Identity of one recorded judgement, detail and score delta included."""
        return content_key(
            {
                "candidate": self.candidate_ref,
                "layer": str(self.layer),
                "code": self.code,
                "verdict": str(self.verdict),
                "detail": self.detail,
                "delta": round(self.delta, 6),
            }
        )


@dataclass(frozen=True)
class CompatibilityEvidence:
    """Everything the four layers concluded about one surviving candidate, and its score.

    The score is a transparent sum of the recorded ``delta`` values, never a black box: every
    contribution is a :class:`CompatibilityReason` in :attr:`reasons`, so "why did this candidate
    win" is answerable by reading them. :attr:`refused`` means a layer removed the candidate rather
    than weakening it, and only context may set it (constitution IV).
    """

    candidate_ref: str
    reasons: tuple[CompatibilityReason, ...] = ()
    score: float = 0.0
    refused: bool = False
    independent_corroboration: int = 0
    same_source_only: bool = False
    block_key: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(self.reasons))
        object.__setattr__(self, "score", round(float(self.score), 6))

    @property
    def excluded(self) -> bool:
        """Whether this candidate is out of the comparison entirely, and why that is different.

        Two verdicts remove a candidate rather than weaken it, and the distinction matters:

        * ``REFUSED`` - a **constitution IV** boundary. The context layer will not even measure a
          cross-tenant record against this mention, so there is nothing to score.
        * ``CONFLICT`` - a **contradiction**. Two validity windows that do not overlap are a
          positive claim that they cannot both be true, which is a different kind of statement
          from "nobody has said". Contradiction may exclude; absence may not (FR-011, SC-9).

        Neither deletes anything: the candidate stays in the universe, stays frozen, and can be
        proposed again by a query whose window does overlap. The reasons are on the decision, so
        "why was this dropped" is always answerable.
        """
        return self.refused or any(
            reason.verdict is ReasonVerdict.CONFLICT for reason in self.reasons
        )

    def codes(self, layer: CompatibilityLayer | None = None) -> tuple[str, ...]:
        """The recorded reason codes, canonically ordered, optionally for one layer."""
        wanted = CompatibilityLayer(layer) if layer is not None else None
        return tuple(
            reason.code
            for reason in self.reasons
            if wanted is None or reason.layer is wanted
        )

    def content_key(self) -> str:
        """Identity of the whole compatibility record, so a decision can cite its evidence."""
        return content_key(
            {
                "candidate": self.candidate_ref,
                "score": round(self.score, 6),
                "refused": self.refused,
                "corroboration": self.independent_corroboration,
                "same_source_only": self.same_source_only,
                "reasons": [reason.content_key() for reason in self.reasons],
            }
        )


def _window(value: datetime | None) -> str:
    return value.isoformat() if value is not None else "open"


def _windows_overlap(
    left_from: datetime | None,
    left_to: datetime | None,
    right_from: datetime | None,
    right_to: datetime | None,
) -> bool:
    """Whether two validity windows share at least one instant. An absent bound is open.

    Half-open at the end, because a window that *ends* at an instant does not cover that instant
    and a window that *starts* there does; the two would then be disjoint at exactly one point
    rather than falsely overlapping.
    """
    if left_from is not None and right_to is not None and left_from >= right_to:
        return False
    if right_from is not None and left_to is not None and right_from >= left_to:
        return False
    return True


def mutually_exclusive(
    left: ResolutionMention,
    right: ResolutionMention,
) -> tuple[bool, str]:
    """Whether two mentions cannot be about the same thing, with the code that says why.

    Used by the collective pass to decide what counts as a *contested* claim, so it must be
    conservative: it returns ``(False, "")`` for anything it cannot demonstrate, because declaring
    two mentions exclusive on thin evidence manufactures a contradiction nobody recorded.
    Demonstrable exclusivity is a different tenant, a different investigation, or two validity
    windows that do not overlap.
    """
    if left.mention_id == right.mention_id:
        return (False, "")
    if left.tenant_id and right.tenant_id and left.tenant_id != right.tenant_id:
        return (True, "distinct_tenant")
    if (
        left.investigation_id
        and right.investigation_id
        and left.investigation_id != right.investigation_id
    ):
        return (True, "distinct_investigation")
    if not _windows_overlap(
        left.valid_from, left.valid_to, right.valid_from, right.valid_to
    ):
        return (True, "disjoint_validity_windows")
    return (False, "")


def analyse_candidate(
    mention: ResolutionMention,
    normalized: NormalizedSurface,
    candidate: ResolutionCandidate,
    allowed_kinds: tuple[str, ...] = (),
) -> CompatibilityEvidence:
    """Run the four compatibility layers over one candidate and record every judgement.

    Each layer returns at least one reason, so a candidate's evidence is never an unexplained
    score. The layers are strictly ordered - context, temporal, source, type - and the first
    two may **exclude** rather than weaken, for the two different reasons
    :attr:`CompatibilityEvidence.excluded` names: a cross-tenant candidate is *refused* outright,
    because scoring it down would leave a record in the comparison that only authority stops
    (constitution IV), and two validity windows that do not overlap are a *contradiction*, which
    is a positive claim rather than an absence of knowledge (FR-011). Everything else is a
    recorded weakening, and a check with nothing to compare against records ``UNEVALUATED`` rather
    than failing (SC-9).
    """
    ref = candidate.identity_ref()
    reasons: list[CompatibilityReason] = []

    if mention.tenant_id and candidate.tenant_id and mention.tenant_id != candidate.tenant_id:
        reasons.append(
            CompatibilityReason(
                ref,
                CompatibilityLayer.CONTEXT,
                "cross_tenant",
                ReasonVerdict.REFUSED,
                detail=(
                    f"mention tenant {mention.tenant_id!r} cannot read candidate tenant "
                    f"{candidate.tenant_id!r}; refused, not scored"
                ),
            )
        )
        return CompatibilityEvidence(
            candidate_ref=ref, reasons=tuple(reasons), refused=True, block_key=ref
        )

    reasons.append(
        CompatibilityReason(
            ref,
            CompatibilityLayer.CONTEXT,
            "tenant_compatible",
            ReasonVerdict.SUPPORTED,
            detail=f"tenant {candidate.tenant_id!r} matches the scope",
        )
    )
    if (
        mention.investigation_id
        and candidate.investigation_id
        and mention.investigation_id != candidate.investigation_id
    ):
        reasons.append(
            CompatibilityReason(
                ref,
                CompatibilityLayer.CONTEXT,
                "investigation_mismatch",
                ReasonVerdict.WEAKENED,
                detail=(
                    f"candidate belongs to investigation {candidate.investigation_id!r}, "
                    f"mention to {mention.investigation_id!r}"
                ),
                delta=-0.1,
            )
        )
    else:
        reasons.append(
            CompatibilityReason(
                ref,
                CompatibilityLayer.CONTEXT,
                "investigation_compatible",
                ReasonVerdict.SUPPORTED,
                detail=f"investigation {candidate.investigation_id or '(none)'}",
            )
        )
    if (
        mention.profile_id
        and candidate.profile_id
        and (mention.profile_id, mention.profile_version)
        != (candidate.profile_id, candidate.profile_version)
    ):
        reasons.append(
            CompatibilityReason(
                ref,
                CompatibilityLayer.CONTEXT,
                "profile_mismatch",
                ReasonVerdict.WEAKENED,
                detail=(
                    f"interpreted under {mention.profile_id}@{mention.profile_version}, "
                    f"candidate declared under {candidate.profile_id}@{candidate.profile_version}"
                ),
                delta=-0.05,
            )
        )
    if mention.ontology_version and candidate.ontology_version:
        if mention.ontology_version == candidate.ontology_version:
            reasons.append(
                CompatibilityReason(
                    ref,
                    CompatibilityLayer.CONTEXT,
                    "ontology_version_compatible",
                    ReasonVerdict.SUPPORTED,
                    detail=f"ontology version {mention.ontology_version!r}",
                )
            )
        else:
            reasons.append(
                CompatibilityReason(
                    ref,
                    CompatibilityLayer.CONTEXT,
                    "ontology_version_mismatch",
                    ReasonVerdict.WEAKENED,
                    detail=(
                        f"mention read under ontology {mention.ontology_version!r}, candidate "
                        f"under {candidate.ontology_version!r}"
                    ),
                    delta=-0.05,
                )
            )
    else:
        reasons.append(
            CompatibilityReason(
                ref,
                CompatibilityLayer.CONTEXT,
                "ontology_version_unevaluated",
                ReasonVerdict.UNEVALUATED,
                detail="one side records no ontology version; nothing to compare",
            )
        )
    if mention.regime_id and candidate.regime_id:
        reasons.append(
            CompatibilityReason(
                ref,
                CompatibilityLayer.CONTEXT,
                "regime_compatible"
                if mention.regime_id == candidate.regime_id
                else "regime_mismatch",
                ReasonVerdict.SUPPORTED
                if mention.regime_id == candidate.regime_id
                else ReasonVerdict.WEAKENED,
                detail=(
                    f"mention regime {mention.regime_id}, candidate regime {candidate.regime_id}"
                ),
                delta=0.0 if mention.regime_id == candidate.regime_id else -0.05,
            )
        )
    else:
        reasons.append(
            CompatibilityReason(
                ref,
                CompatibilityLayer.CONTEXT,
                "regime_unevaluated",
                ReasonVerdict.UNEVALUATED,
                detail="one side records no semantic regime id; nothing to compare",
            )
        )

    if mention.valid_from is not None or mention.valid_to is not None or (
        candidate.valid_from is not None or candidate.valid_to is not None
    ):
        if _windows_overlap(
            mention.valid_from, mention.valid_to, candidate.valid_from, candidate.valid_to
        ):
            open_ended = mention.valid_to is None and candidate.valid_to is None
            reasons.append(
                CompatibilityReason(
                    ref,
                    CompatibilityLayer.TEMPORAL,
                    "temporal_windows_overlap" if not open_ended else "temporal_window_open_ended",
                    ReasonVerdict.SUPPORTED,
                    detail=(
                        f"mention [{_window(mention.valid_from)}, "
                        f"{_window(mention.valid_to)}) vs candidate "
                        f"[{_window(candidate.valid_from)}, {_window(candidate.valid_to)})"
                    ),
                )
            )
        else:
            reasons.append(
                CompatibilityReason(
                    ref,
                    CompatibilityLayer.TEMPORAL,
                    "temporal_windows_disjoint",
                    ReasonVerdict.CONFLICT,
                    detail=(
                        f"non-overlapping validity windows: mention "
                        f"[{_window(mention.valid_from)}, {_window(mention.valid_to)}) vs "
                        f"candidate [{_window(candidate.valid_from)}, "
                        f"{_window(candidate.valid_to)}); the entity did not exist across the "
                        "whole of the mention's window"
                    ),
                )
            )
    else:
        reasons.append(
            CompatibilityReason(
                ref,
                CompatibilityLayer.TEMPORAL,
                "temporal_window_unrecorded",
                ReasonVerdict.UNEVALUATED,
                detail="neither side records a validity window; no temporal claim to check",
            )
        )
    if mention.observed_at is not None and candidate.observed_at is not None:
        if candidate.observed_at <= mention.observed_at:
            reasons.append(
                CompatibilityReason(
                    ref,
                    CompatibilityLayer.TEMPORAL,
                    "observed_before_mention",
                    ReasonVerdict.SUPPORTED,
                    detail=(
                        f"candidate observed {candidate.observed_at.isoformat()}, mention "
                        f"{mention.observed_at.isoformat()}: the record predates the reading"
                    ),
                )
            )
        else:
            reasons.append(
                CompatibilityReason(
                    ref,
                    CompatibilityLayer.TEMPORAL,
                    "observed_after_mention",
                    ReasonVerdict.WEAKENED,
                    detail=(
                        f"candidate observed {candidate.observed_at.isoformat()}, mention "
                        f"{mention.observed_at.isoformat()}: learned later, so it cannot confirm "
                        "what was known at the time"
                    ),
                    delta=-0.05,
                )
            )
    else:
        reasons.append(
            CompatibilityReason(
                ref,
                CompatibilityLayer.TEMPORAL,
                "observed_at_unevaluated",
                ReasonVerdict.UNEVALUATED,
                detail="one side records no observed_at; no ordering to check",
            )
        )

    own_group = mention.independence_key()
    independent = sorted(
        group
        for group in candidate.supporting_groups
        if group and group != own_group and group != mention.source_family
    )
    same_source_only = bool(candidate.supporting_groups) and not independent
    if not candidate.supporting_groups:
        reasons.append(
            CompatibilityReason(
                ref,
                CompatibilityLayer.SOURCE,
                "no_prior_support",
                ReasonVerdict.UNEVALUATED,
                detail=(
                    "candidate records no supporting groups; this mention would be the first "
                    "evidence for it, which is a fact and not a weakness"
                ),
            )
        )
    elif same_source_only:
        reasons.append(
            CompatibilityReason(
                ref,
                CompatibilityLayer.SOURCE,
                "same_source_only",
                ReasonVerdict.WEAKENED,
                detail=(
                    f"all {len(candidate.supporting_groups)} recorded support group(s) "
                    f"{list(candidate.supporting_groups)} belong to the mention's own source "
                    f"family {own_group!r}; zero independent corroboration"
                ),
                delta=-0.1,
            )
        )
    else:
        reasons.append(
            CompatibilityReason(
                ref,
                CompatibilityLayer.SOURCE,
                "independent_corroboration",
                ReasonVerdict.SUPPORTED,
                detail=(
                    f"{len(independent)} independent group(s) {independent} differ from the "
                    f"mention's own {own_group!r}"
                ),
                delta=_CONF_CORROBORATION_STEP * len(independent),
            )
        )
    if mention.source_family and candidate.source_family:
        reasons.append(
            CompatibilityReason(
                ref,
                CompatibilityLayer.SOURCE,
                "source_family_match"
                if mention.source_family == candidate.source_family
                else "source_family_differs",
                ReasonVerdict.SUPPORTED
                if mention.source_family == candidate.source_family
                else ReasonVerdict.UNEVALUATED,
                detail=(
                    f"mention source family {mention.source_family!r} vs candidate "
                    f"{candidate.source_family!r}"
                ),
            )
        )

    reasons.append(_type_hint_reason(ref, mention, normalized, candidate, allowed_kinds))
    return CompatibilityEvidence(
        candidate_ref=ref,
        reasons=tuple(reasons),
        score=sum(reason.delta for reason in reasons),
        independent_corroboration=len(independent),
        same_source_only=same_source_only,
        block_key=ref,
    )


def _type_hint_reason(
    ref: str,
    mention: ResolutionMention,
    normalized: NormalizedSurface,
    candidate: ResolutionCandidate,
    allowed_kinds: tuple[str, ...] = (),
) -> CompatibilityReason:
    """The type layer's opinion, which is a *hint* and can never become an assertion.

    Consults the mention's own ``TypeAssertion`` layers - read, never written - plus the broader
    concepts its surface reached, and asks the operator's declared affordance kinds
    (``subject_kinds``/``object_kinds``, already computed by
    :func:`semantic.blocking.affordance_kinds`) whether such a type may stand in this role at all.
    A candidate that declares types and shares none of them is *weakened*, not removed and not
    re-typed: pruning is a query-time narrowing (FR-016), and nothing in this module constructs a
    ``TypeAssertion``, so a candidate cannot acquire a type by being compared.
    """
    pairs = mention.type_refs()
    if not pairs:
        return CompatibilityReason(
            ref,
            CompatibilityLayer.TYPE,
            "type_hint_absent",
            ReasonVerdict.UNEVALUATED,
            detail="the mention carries no typing claim; type compatibility is unevaluable",
        )
    mention_refs = {ref_str for ref_str, _ in pairs}
    if allowed_kinds:
        mentioned_kinds = {normalize_kind(value) for value in mention_refs}
        if mentioned_kinds & set(allowed_kinds):
            return CompatibilityReason(
                ref,
                CompatibilityLayer.TYPE,
                "type_hint_afforded_in_role",
                ReasonVerdict.SUPPORTED,
                detail=(
                    f"the operator affords {sorted(allowed_kinds)} in the {mention.role!s} role "
                    f"and the mention carries {sorted(mention_refs)}; the operator's own view "
                    "permits it, which is a hint and not a type"
                ),
                delta=0.05,
            )
        return CompatibilityReason(
            ref,
            CompatibilityLayer.TYPE,
            "type_hint_unafforded_in_role",
            ReasonVerdict.WEAKENED,
            detail=(
                f"the operator affords {sorted(allowed_kinds)} in the {mention.role!s} role and "
                f"the mention carries {sorted(mention_refs)}, which is outside that hint; advisory "
                "only, and no type is asserted on the candidate"
            ),
            delta=-0.05,
        )
    candidate_refs = {str(value).strip() for value in candidate.type_refs}
    shared = mention_refs & candidate_refs
    if shared:
        return CompatibilityReason(
            ref,
            CompatibilityLayer.TYPE,
            "type_hint_shared",
            ReasonVerdict.SUPPORTED,
            detail=(
                f"mention types {sorted(mention_refs)} and candidate types "
                f"{sorted(candidate_refs)} share {sorted(shared)} (source: "
                f"{mention.type_hint_source()}); a shared type is a comparison, not identity"
            ),
            delta=0.05,
        )
    if normalized.type_hints and set(normalized.type_hints) & candidate_refs:
        return CompatibilityReason(
            ref,
            CompatibilityLayer.TYPE,
            "type_hint_broader_match",
            ReasonVerdict.SUPPORTED,
            detail=(
                f"vocabulary broader concepts {list(normalized.type_hints)} reach candidate types "
                f"{sorted(candidate_refs)}; hint only, no type is asserted"
            ),
            delta=0.02,
        )
    if candidate_refs:
        return CompatibilityReason(
            ref,
            CompatibilityLayer.TYPE,
            "type_hint_unshared",
            ReasonVerdict.WEAKENED,
            detail=(
                f"mention types {sorted(mention_refs)} share nothing with candidate types "
                f"{sorted(candidate_refs)}; narrowed, not excluded, and no type is asserted"
            ),
            delta=-0.05,
        )
    return CompatibilityReason(
        ref,
        CompatibilityLayer.TYPE,
        "type_hint_candidate_untyped",
        ReasonVerdict.UNEVALUATED,
        detail=(
            f"the candidate declares no types, so nothing conflicts with the mention's "
            f"{sorted(mention_refs)}; unrecorded is not contrary"
        ),
    )


@dataclass(frozen=True)
class CollectiveRemoval:
    """One edge the collective pass removed from the mention<->candidate graph, and why."""

    mention_id: str
    candidate_ref: str
    code: str
    detail: str = ""

    def content_key(self) -> str:
        """Identity of one edge the collective pass removed, and the rule that removed it."""
        return content_key(
            {
                "mention": self.mention_id,
                "candidate": self.candidate_ref,
                "code": self.code,
                "detail": self.detail,
            }
        )


@dataclass(frozen=True)
class CollectiveOutcome:
    """The result of the collective pass: what it committed, what it contested, what it removed.

    :attr:`applied` is ``False`` when the pass was skipped or did not converge, and in that case
    :attr:`feasible` reproduces the pre-collective sets exactly - the caller gets the answer it
    would have had without this step rather than a partial one presented as a whole.
    :attr:`contested` is reported, never acted on: a candidate two mutually exclusive mentions both
    claim is a contradiction for a human to weigh, and averaging it away is the one thing a
    resolver must not do.
    """

    applied: bool = False
    converged: bool = False
    iterations: int = 0
    edges_before: int = 0
    edges_after: int = 0
    feasible: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    committed: Mapping[str, str] = field(default_factory=dict)
    support: Mapping[str, int] = field(default_factory=dict)
    contested: tuple[str, ...] = ()
    removals: tuple[CollectiveRemoval, ...] = ()
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "feasible", MappingProxyType(dict(self.feasible)))
        object.__setattr__(self, "committed", MappingProxyType(dict(self.committed)))
        object.__setattr__(self, "support", MappingProxyType(dict(self.support)))
        object.__setattr__(self, "contested", tuple(self.contested))
        object.__setattr__(self, "removals", tuple(self.removals))
        object.__setattr__(self, "notes", tuple(self.notes))

    @property
    def edges_removed(self) -> int:
        """How many mention<->candidate edges the pass closed, which is how much it decided."""
        return max(self.edges_before - self.edges_after, 0)

    def feasible_for(self, mention_id: str) -> tuple[str, ...]:
        """The candidates still feasible for one mention, canonically ordered."""
        return tuple(self.feasible.get(mention_id, ()))

    def content_key(self) -> str:
        """Identity of the collective pass, so a decision can cite exactly what it propagated."""
        return content_key(
            {
                "applied": self.applied,
                "converged": self.converged,
                "iterations": self.iterations,
                "edges_before": self.edges_before,
                "edges_after": self.edges_after,
                "feasible": {key: list(value) for key, value in sorted(self.feasible.items())},
                "committed": dict(sorted(self.committed.items())),
                "support": dict(sorted(self.support.items())),
                "contested": list(self.contested),
                "removals": [removal.content_key() for removal in self.removals],
            }
        )


def collective_resolution(
    mentions: Mapping[str, ResolutionMention],
    feasible: Mapping[str, frozenset[str]],
    max_iterations: int = DEFAULT_COLLECTIVE_MAX_ITERATIONS,
) -> CollectiveOutcome:
    """Close the mention<->candidate graph under mutual consistency, deterministically.

    Four rules, and every one of them only ever **removes** an edge or **commits** a mention:

    1. a mention with exactly one feasible candidate is *committed* to it, and a committed mention
       never moves again;
    2. a candidate that a committed mention holds gains *support* from it - support is monotone
       non-decreasing, so it can only strengthen, never re-open a decision;
    3. a mention that is not committed, whose only candidate is held by a committed mention
       **that cannot be the same thing**, loses it. The mutual-exclusivity requirement is
       load-bearing rather than a refinement: two mentions of one entity is the ordinary case
       this whole module exists to detect, so a rule that made exclusivity out of mere
       co-residence would forbid exactly the thing it is looking for;
    4. a mention that is not committed and whose leader holds strictly more support than the
       runner-up drops the runner-up;
    5. a candidate still feasible for two *mutually exclusive* mentions is reported contested, and
       never acted on.

    **Why it terminates.** Take the potential ``Phi = |E| + |M|``, where ``|E|`` is the number of
    mention<->candidate edges and ``|M|`` the number of mentions not yet committed. Rule 1 removes
    one mention from ``|M|``; rules 3 and 4 each remove at least one edge from ``|E|``; rules 2 and
    5 change neither. So every firing strictly decreases a non-negative integer bounded above by
    ``|E| + |M|``, hence at most that many firings can happen: the loop cannot run forever, cannot
    oscillate, and does not have to be watched. ``max_iterations`` is still honoured as a hard
    bound, and if it trips the caller gets the **pre-collective** sets back with ``applied=False``
    and a note saying so - a partial propagation presented as a whole would be worse than none.

    **Why it is deterministic.** Mentions are visited in ``mention_id`` order and their candidates
    in sorted ``entity_ref`` order on every round, so the same input produces the same rounds in
    the same order in any process (constitution VI).
    """
    original = {key: frozenset(value) for key, value in feasible.items()}
    initial = {key: set(value) for key, value in feasible.items()}
    edges_before = sum(len(value) for value in initial.values())
    order = tuple(sorted(initial))
    if not order:
        return CollectiveOutcome(
            applied=True,
            converged=True,
            iterations=0,
            edges_before=0,
            edges_after=0,
            feasible=MappingProxyType({}),
            notes=("no mention survived candidate generation; nothing to propagate",),
        )
    cap = max(int(max_iterations), 1)
    notes: list[str] = []
    bound = edges_before + len(initial)
    if cap < bound:
        notes.append(
            f"collective iteration cap {cap} is below the {bound}-step bound implied by this "
            f"graph ({edges_before} edges + {len(initial)} mentions); the cap is a hard bound, "
            "not an expected outcome"
        )
    committed: dict[str, str] = {}
    support: dict[str, int] = {}
    removals: list[CollectiveRemoval] = []
    iterations = 0
    converged = False
    while iterations < cap:
        iterations += 1
        fired = False
        for mention_id in order:
            options = sorted(initial[mention_id])
            if mention_id in committed or not options:
                continue
            if len(options) == 1:
                committed[mention_id] = options[0]
                support[options[0]] = support.get(options[0], 0) + 1
                removals.append(
                    CollectiveRemoval(
                        mention_id,
                        options[0],
                        "unique_feasible_candidate",
                        "exactly one candidate left for this mention, so it is provisionally "
                        "resolved to it",
                    )
                )
                fired = True
                continue
            best = max(support.get(option, 0) for option in options)
            leaders = [option for option in options if support.get(option, 0) == best]
            if best > 0 and len(leaders) == 1:
                kept = leaders[0]
                for option in options:
                    if option == kept:
                        continue
                    initial[mention_id].discard(option)
                    removals.append(
                        CollectiveRemoval(
                            mention_id,
                            option,
                            "decisively_less_supported",
                            f"{option!r} holds {support.get(option, 0)} committed mention(s) "
                            f"against {best} for {kept!r}; the gap is decisive",
                        )
                    )
                fired = True
        for mention_id in order:
            held = committed.get(mention_id)
            holder = mentions.get(mention_id)
            if held is None or holder is None:
                continue
            for other in order:
                if other == mention_id or other in committed:
                    continue
                peer = mentions.get(other)
                if peer is None:
                    continue
                exclusive, why = mutually_exclusive(holder, peer)
                if not exclusive:
                    continue
                options = initial[other]
                if held in options and len(options) == 1:
                    options.discard(held)
                    removals.append(
                        CollectiveRemoval(
                            other,
                            held,
                            "exclusively_claimed",
                            f"{held!r} is the only candidate for {other!r} and is already "
                            f"committed to {mention_id!r}, which cannot be the same thing "
                            f"({why})",
                        )
                    )
                    fired = True
        if not fired:
            converged = True
            break
    if not converged:
        notes.append(
            f"collective pass did not converge within {cap} iteration(s) and stopped with "
            f"{len(removals)} edge removal(s) applied; the pre-collective candidate sets are "
            "returned unpropagated and collective_applied is False"
        )
        return CollectiveOutcome(
            applied=False,
            converged=False,
            iterations=iterations,
            edges_before=edges_before,
            edges_after=edges_before,
            feasible=MappingProxyType(
                {key: tuple(sorted(value)) for key, value in original.items()}
            ),
            removals=tuple(removals),
            notes=tuple(notes),
        )
    edges_after = sum(len(value) for value in initial.values())
    contested = sorted(
        candidate
        for candidate in {ref for value in initial.values() for ref in value}
        if _is_contested(candidate, mentions, initial)
    )
    if contested:
        notes.append(
            f"contested candidate(s) {contested} remain feasible for mutually exclusive mentions; "
            "reported, never resolved by this pass"
        )
    return CollectiveOutcome(
        applied=True,
        converged=True,
        iterations=iterations,
        edges_before=edges_before,
        edges_after=edges_after,
        feasible=MappingProxyType({key: tuple(sorted(value)) for key, value in initial.items()}),
        committed=MappingProxyType(dict(sorted(committed.items()))),
        support=MappingProxyType(dict(sorted(support.items()))),
        contested=tuple(contested),
        removals=tuple(removals),
        notes=tuple(notes),
    )


def _is_contested(
    candidate_ref: str,
    mentions: Mapping[str, ResolutionMention],
    feasible: Mapping[str, frozenset[str]],
) -> bool:
    """Whether two mentions that cannot be the same thing both still hold this candidate."""
    holders = tuple(
        sorted(mention_id for mention_id, options in feasible.items() if candidate_ref in options)
    )
    for index, left_id in enumerate(holders):
        for right_id in holders[index + 1 :]:
            left, right = mentions.get(left_id), mentions.get(right_id)
            if left is None or right is None:
                continue
            exclusive, _ = mutually_exclusive(left, right)
            if exclusive:
                return True
    return False


@dataclass(frozen=True)
class EntityHypothesis:
    """The entity a mention is proposed to be, and everything that supports the proposal.

    Carries the **anchor** explicitly, because the anchor is the claim about identity while the
    decision's id is the claim about this resolution: the same entity re-hypothesised with one more
    mention has a new decision id and the same :attr:`logical_entity_ref`. ``new_entity`` records
    whether the identity was minted by this pass or adopted from a record that already had one, and
    ``corroboration`` is the count of independent groups behind the record, not the count of
    mentions - one source saying it three times is one source.
    """

    logical_entity_ref: str
    candidate_ref: str
    name: str
    anchor_mention_id: str
    merged_mentions: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    corroboration: int = 0
    new_entity: bool = False
    established: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "merged_mentions", tuple(self.merged_mentions))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))

    def content_key(self) -> str:
        """Identity of the hypothesis: the anchor and the corroboration, and nothing else."""
        return content_key(
            {
                "entity": self.logical_entity_ref,
                "candidate": self.candidate_ref,
                "name": self.name,
                "anchor_mention": self.anchor_mention_id,
                "merged": list(self.merged_mentions),
                "evidence": list(self.evidence_refs),
                "corroboration": self.corroboration,
                "new_entity": self.new_entity,
            }
        )


@dataclass(frozen=True)
class ResolutionDecision:
    """What one mention resolved to, and the complete, inspectable record of how.

    Frozen and content-addressed in two levels, like every other identity in the platform. The
    ``resolution_decision_id`` is derived in :meth:`__post_init__` over
    :meth:`decision_material` and **verified** when supplied, so a decision carrying an id its own
    content does not address to cannot be constructed - the same discipline
    :class:`~semantic.contracts.TypeAssertion` follows. The derived fields are: :attr:`confidence`
    from :attr:`confidence_parts`, and the id from everything else.

    Every element the architect asked for is a field: the surviving candidates
    (:attr:`surviving`), the per-candidate compatibility reasons (:attr:`reasons`),
    :attr:`corroboration`, :attr:`collective`, :attr:`blocking`, :attr:`logical_entity_ref`, the
    decision's own :attr:`resolution_decision_id` and :attr:`confidence`. :attr:`verdict` is a
    result, and :attr:`logical_entity_ref` is empty whenever the verdict did not resolve - so a
    caller cannot read an entity out of an unresolved decision by accident.
    """

    mention_id: str = ""
    surface: str = ""
    verdict: ResolutionVerdict = ResolutionVerdict.UNRESOLVED
    resolution_decision_id: str = ""
    logical_entity_ref: str = ""
    anchor_mention_id: str = ""
    anchor_key: str = ""
    merged_mentions: tuple[str, ...] = ()
    considered: tuple[str, ...] = ()
    surviving: tuple[str, ...] = ()
    scored: tuple[tuple[str, float], ...] = ()
    evidence: tuple[CompatibilityEvidence, ...] = ()
    reasons: tuple[CompatibilityReason, ...] = ()
    blocked_out: tuple[CompatibilityReason, ...] = ()
    normalization: tuple[str, ...] = ()
    blocking: BlockingOutcome | None = None
    collective: CollectiveOutcome | None = None
    hypothesis: EntityHypothesis | None = None
    corroboration: int = 0
    confidence_parts: tuple[tuple[str, float], ...] = ()
    confidence: float = 0.0
    resolution_scope_id: str = ""
    tenant_id: str = "default-tenant"
    operator_ref: str = ""
    normalization_version: str = ""
    ontology_version: str = ""
    regime_id: str = ""
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "verdict", ResolutionVerdict(self.verdict))
        for name in (
            "merged_mentions",
            "considered",
            "surviving",
            "normalization",
            "notes",
        ):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "reasons", tuple(self.reasons))
        object.__setattr__(self, "blocked_out", tuple(self.blocked_out))
        object.__setattr__(self, "confidence_parts", tuple(self.confidence_parts))
        object.__setattr__(self, "confidence", _confidence_from(self.confidence_parts))
        addressed = RESOLUTION_ID_PREFIX + content_key(self.decision_material())
        if not self.resolution_decision_id:
            object.__setattr__(self, "resolution_decision_id", addressed)
        elif self.resolution_decision_id != addressed:
            raise ValueError(
                f"decision carries {self.resolution_decision_id!r} but its own content addresses "
                f"to {addressed!r}; a content address is verified, never trusted"
            )

    def decision_material(self) -> dict[str, Any]:
        """Exactly what :attr:`resolution_decision_id` digests - this decision's audit surface.

        Every input the verdict was reached from, including the merged mention set, the candidates
        considered and the compatibility evidence, because a resolution id that did not cover its
        evidence would be an id that could be reused for a different answer.
        """
        return {
            "mention": self.mention_id,
            "surface": self.surface,
            "verdict": str(self.verdict),
            "entity": self.logical_entity_ref,
            "anchor_mention": self.anchor_mention_id,
            "anchor_key": self.anchor_key,
            "merged_mentions": list(self.merged_mentions),
            "considered": list(self.considered),
            "surviving": list(self.surviving),
            "scored": [[ref, round(score, 6)] for ref, score in self.scored],
            "reasons": [reason.content_key() for reason in self.reasons],
            "blocked_out": [reason.content_key() for reason in self.blocked_out],
            "normalization": list(self.normalization),
            "blocking": self.blocking.content_key() if self.blocking is not None else "",
            "collective": self.collective.content_key() if self.collective is not None else "",
            "hypothesis": self.hypothesis.content_key() if self.hypothesis is not None else "",
            "corroboration": self.corroboration,
            "confidence": round(self.confidence, 6),
            "confidence_parts": [[code, round(delta, 6)] for code, delta in self.confidence_parts],
            "scope": self.resolution_scope_id,
            "tenant": self.tenant_id,
            "operator": self.operator_ref,
            "normalization_version": self.normalization_version,
            "ontology_version": self.ontology_version,
            "regime": self.regime_id,
            "notes": list(self.notes),
        }

    @property
    def is_resolved(self) -> bool:
        """Whether this decision named exactly one entity, and so may be used as a participant."""
        return self.verdict.is_resolved

    @property
    def is_ambiguous(self) -> bool:
        """Whether the resolver declined to choose between two equally supported candidates."""
        return self.verdict is ResolutionVerdict.AMBIGUOUS

    def reasons_for(self, layer: CompatibilityLayer | str) -> tuple[CompatibilityReason, ...]:
        """The recorded reasons from one layer, in the order that layer produced them."""
        wanted = CompatibilityLayer(layer)
        return tuple(reason for reason in self.reasons if reason.layer is wanted)

    def reason_codes(self) -> tuple[str, ...]:
        """Every recorded reason code, canonically ordered, for a log line or a diff."""
        return tuple(sorted(reason.code for reason in self.reasons))

    def ambiguous_candidates(self) -> tuple[str, ...]:
        """Both candidates of an ambiguous decision, in score order. Never a single pick."""
        if self.verdict is not ResolutionVerdict.AMBIGUOUS:
            return ()
        return tuple(ref for ref, _ in self.scored)

    def content_key(self) -> str:
        """The bare digest behind :attr:`resolution_decision_id`, for a caller storing the pair."""
        return self.resolution_decision_id.removeprefix(RESOLUTION_ID_PREFIX)


def _confidence_from(parts: tuple[tuple[str, float], ...]) -> float:
    """The decision's confidence, from its own recorded parts. Deterministic, and never a surprise.

    A transparent sum rather than a model, so that the number on a decision is explainable by
    reading the same decision: every contribution is a named part, clamped into ``0.0..1.0`` and
    rounded to six places so the digest of it is stable across platforms.
    """
    total = sum(delta for _, delta in parts)
    return round(min(max(_CONF_BASE + total, 0.0), 1.0), 6)


@dataclass(frozen=True)
class ResolutionBatch:
    """Every decision from one batch, the updated scope, and the universe they ran against.

    Keyed by mention because that is how a caller asks the question ("what became of *this*
    mention"), while the tuple is canonically ordered by ``mention_id`` for byte-comparison. The
    returned :attr:`scope` carries the anchors this batch established; a caller that does not
    persist it loses the guarantee that a later mention joins the entity rather than minting a new
    one, which is stated here rather than left to be discovered.
    """

    decisions: tuple[ResolutionDecision, ...] = ()
    scope: ResolutionScope = field(default_factory=ResolutionScope)
    universe: tuple[ResolutionCandidate, ...] = ()
    collective: CollectiveOutcome | None = None
    _by_mention: Mapping[str, ResolutionDecision] = field(
        default_factory=dict, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "decisions", tuple(self.decisions))
        object.__setattr__(self, "universe", tuple(self.universe))
        object.__setattr__(
            self,
            "_by_mention",
            MappingProxyType({decision.mention_id: decision for decision in self.decisions}),
        )

    def decision_for(self, mention_id: str) -> ResolutionDecision | None:
        """The decision for one mention, or ``None`` when this batch did not carry it."""
        return self._by_mention.get(str(mention_id))

    def entity_for(self, mention_id: str) -> str:
        """The resolved entity ref for one mention, or the empty string when it did not resolve.

        The empty string is the honest answer for ``AMBIGUOUS`` and ``UNRESOLVED``: there is no
        entity to name, and returning the first candidate's ref here would be exactly the silent
        coin-flip the architecture forbids.
        """
        decision = self.decision_for(mention_id)
        return decision.logical_entity_ref if decision is not None else ""

    def verdict_for(self, mention_id: str) -> ResolutionVerdict | None:
        """One mention's verdict, or ``None`` when this batch did not carry it."""
        decision = self.decision_for(mention_id)
        return decision.verdict if decision is not None else None

    def supporting_groups_for(self, entity_ref: str) -> tuple[str, ...]:
        """The independence groups that stand behind one resolved entity in this batch.

        A query on the batch rather than a field on the decision, deliberately. The groups are
        a property of the *candidate* that was selected, several mentions may select the same
        one, and putting them in the decision would fold a fact about the universe into the
        material every ``RES-`` id is derived from -- so learning a corroborating source later
        would change the address of a decision that never mentioned it.

        Empty for an entity this batch did not resolve, which is the honest answer: no groups
        were established here. It is also the value that keeps ``independent_source_count`` at
        zero when nothing independent actually backed the resolution, rather than inventing a
        group so a corroboration check would have something to pass on.
        """
        if not entity_ref:
            return ()
        for candidate in self.universe:
            if candidate.identity_ref() == entity_ref:
                return candidate.supporting_groups
        return ()

    def verdicts(self) -> Mapping[str, ResolutionVerdict]:
        """Every mention's verdict, so an ambiguity cannot be missed by reading one end only."""
        return MappingProxyType(
            {decision.mention_id: decision.verdict for decision in self.decisions}
        )

    def identities(self) -> tuple[tuple[str, str], ...]:
        """``(logical_entity_ref, resolution_decision_id)`` per decision, for a byte-comparison."""
        return tuple(
            (decision.logical_entity_ref, decision.resolution_decision_id)
            for decision in self.decisions
        )

    def blocking_reductions(self) -> Mapping[str, float]:
        """The reported reduction per mention, which is the outcome SC-10 asks to be measurable."""
        return MappingProxyType(
            {
                decision.mention_id: decision.blocking.reduction_ratio
                for decision in self.decisions
                if decision.blocking is not None
            }
        )


class MentionResolver:
    """The machine, in one place: a batch of mentions against a universe, to a set of decisions.

    Constructed with the instruments and the policy, then called with the data:

    * ``registry`` - a :class:`semantic.registry.SemanticRegistry` whose aliases let ``"Acme"`` and
      ``"Acme Corporation"`` meet. Optional: without one, resolution compares normalised forms and
      nothing else, which is a correct and much weaker resolver rather than a broken one.
    * ``operator`` - a :class:`semantic.operators.RelationOperator`, whose ``subject_kinds`` and
      ``object_kinds`` prune what may stand in each mention's role through
      :func:`semantic.blocking.affordance_kinds`. Also optional, for the same reason.
    * ``ambiguity_margin`` - the score gap one candidate must beat the runner-up by to be
      ``RESOLVED``. ``0.0`` means an exact tie is ``AMBIGUOUS``, which is the only setting that
      cannot be accused of preferring a candidate.
    * ``collective_max_iterations`` - the hard bound on the collective pass. The pass is provably
      terminating, so tripping this means the bound was set tighter than the work needed; the
      result is then the pre-collective one, marked ``collective_applied=False``.

    The class holds no state beyond its construction: :meth:`resolve` is a pure function of its
    arguments, and the anchors it establishes are returned in the :class:`ResolutionBatch` rather
    than kept privately, so the caller can see and persist exactly what identity rests on.
    """

    def __init__(
        self,
        *,
        registry: SemanticRegistry | None = None,
        operator: object | None = None,
        ambiguity_margin: float = 0.0,
        collective_max_iterations: int = DEFAULT_COLLECTIVE_MAX_ITERATIONS,
        unknown_kind_policy: UnknownKindPolicy = UnknownKindPolicy.RETAIN,
    ) -> None:
        self._registry = registry
        self._operator = operator
        self._margin = max(float(ambiguity_margin), 0.0)
        self._max_iterations = max(int(collective_max_iterations), 1)
        self._unknown_policy = UnknownKindPolicy(unknown_kind_policy)

    def __repr__(self) -> str:
        operator = getattr(self._operator, "relation_type", "") or "-"
        return (
            f"MentionResolver(operator={operator!r}, registry={self._registry is not None}, "
            f"ambiguity_margin={self._margin}, "
            f"collective_max_iterations={self._max_iterations})"
        )

    def resolve(
        self,
        mentions: Iterable[ResolutionMention],
        candidates: Iterable[ResolutionCandidate] = (),
        scope: ResolutionScope | None = None,
    ) -> ResolutionBatch:
        """Resolve a batch, returning one decision per mention and the updated scope.

        Four passes, in this order, and the order is the reason the anchor is correct:

        1. **per mention** - normalize, block, and run the four compatibility layers;
        2. **batch** - the collective pass over the surviving mention<->candidate graph;
        3. **batch** - group the mentions by the entity they landed on and elect one anchor per
           entity, canonically first, minting ``ENT-`` refs only where no ref already exists;
        4. **per mention** - verdict, hypothesis and the content-addressed decision.

        Pass 3 must come after pass 1 and before pass 4 because the anchor is a property of the
        *entity*, not of one mention: two mentions arriving in the same batch that both land on a
        new entity must agree on which of them introduced it, and only a batch-wide pass can say.
        """
        ordered = tuple(sorted(mentions, key=lambda mention: mention.mention_id))
        universe = self._universe(candidates)
        active = tuple(
            mention
            for mention in ordered
            if not scope or not mention.tenant_id or mention.tenant_id == scope.tenant_id
        )
        out_of_scope = tuple(
            mention for mention in ordered if mention not in active
        )
        working = ResolutionScope(
            scope_id=scope.scope_id if scope is not None else resolution_scope_for(
                active[0].tenant_id if active else "default-tenant",
                active[0].investigation_id if active else "",
            ).scope_id,
            tenant_id=scope.tenant_id if scope is not None else (
                active[0].tenant_id if active else "default-tenant"
            ),
            investigation_id=scope.investigation_id if scope is not None else (
                active[0].investigation_id if active else ""
            ),
            anchors=scope.anchors if scope is not None else (),
        )
        prepared = {
            mention.mention_id: self._prepare(mention, universe, working)
            for mention in active
        }
        collective = self._collective(active, prepared)
        grouped = self._anchor(active, prepared, working)
        updated = working.with_anchors(
            anchor for anchor in grouped.values() if anchor.logical_entity_ref
        )
        decisions = tuple(
            self._decide(
                mention,
                prepared[mention.mention_id],
                collective,
                grouped[mention.mention_id],
                updated,
            )
            for mention in active
        )
        decisions = decisions + tuple(
            self._refuse_out_of_scope(mention, working) for mention in out_of_scope
        )
        return ResolutionBatch(
            decisions=tuple(sorted(decisions, key=lambda item: item.mention_id)),
            scope=updated,
            universe=universe,
            collective=collective,
        )

    def _universe(
        self, candidates: Iterable[ResolutionCandidate]
    ) -> tuple[ResolutionCandidate, ...]:
        """The candidate universe, de-duplicated and canonically ordered.

        De-duplication keeps the first record for an identity, which with a canonically sorted
        input is itself deterministic - two universe rows naming one entity is a data defect, and
        resolving it by input order would make the answer depend on how the caller listed them.
        """
        by_identity: dict[str, ResolutionCandidate] = {}
        for candidate in candidates:
            by_identity.setdefault(candidate.identity_ref(), candidate)
        return tuple(
            by_identity[ref]
            for ref in sorted(
                by_identity,
                key=lambda ref: (
                    normalize_surface_form(by_identity[ref].name),
                    normalize_kind(by_identity[ref].kind),
                    ref,
                ),
            )
        )

    def _prepare(
        self,
        mention: ResolutionMention,
        universe: tuple[ResolutionCandidate, ...],
        scope: ResolutionScope,
    ) -> _Prepared:
        """Pass 1: normalize, delegate blocking, and run the compatibility layers."""
        normalized, refusal = self._normalize(mention)
        notes: list[str] = []
        if refusal is not None:
            notes.append(refusal)
        blocking = block_mention(
            mention,
            normalized,
            universe,
            self._operator,
            unknown_policy=self._unknown_policy,
        )
        notes.extend(blocking.notes)
        by_ref = {candidate.identity_ref(): candidate for candidate in universe}
        kinds = affordance_kinds(self._operator, mention.role) if self._operator is not None else ()
        evidence: list[CompatibilityEvidence] = []
        blocked: list[CompatibilityReason] = []
        for ref in blocking.survivor_refs:
            candidate = by_ref.get(ref)
            if candidate is None:
                continue
            assessed = analyse_candidate(mention, normalized, candidate, kinds)
            if assessed.excluded:
                blocked.extend(assessed.reasons)
            else:
                evidence.append(assessed)
        return _Prepared(
            mention=mention,
            normalized=normalized,
            blocking=blocking,
            evidence=tuple(evidence),
            candidates=MappingProxyType(by_ref),
            refused=tuple(blocked),
            notes=tuple(notes)
            + (() if universe else ("the candidate universe was empty; nothing to compare",)),
        )

    def _normalize(
        self, mention: ResolutionMention
    ) -> tuple[NormalizedSurface, str | None]:
        """Normalize through the vocabulary facade, recording a refusal rather than raising it.

        :class:`semantic.registry.SemanticRegistry` is fail-closed by tenant (constitution IV), so
        a registry that does not serve this mention's tenant raises rather than answering. Letting
        that escape would make a *wiring* refusal look like a *content* failure and would take the
        whole batch down for one mention, so it is caught - and **recorded**, on the decision's
        notes, where it changes the decision's content address. The mention is then compared on its
        own normalised form, which is a weaker resolver and says so, rather than silently pretending
        the vocabulary had nothing to contribute.
        """
        if self._registry is None:
            return (normalize_mention(mention, None), None)
        try:
            return (normalize_mention(mention, self._registry), None)
        except SemanticRegistryError as refusal:
            return (
                normalize_mention(mention, None),
                (
                    f"vocabulary facade refused the lookup for tenant {mention.tenant_id!r} "
                    f"({type(refusal).__name__}); alias expansion is UNEVALUATED for this mention "
                    "and its comparison keys are the surface's own normalised form"
                ),
            )

    def _collective(
        self,
        mentions: tuple[ResolutionMention, ...],
        prepared: Mapping[str, _Prepared],
    ) -> CollectiveOutcome:
        """Pass 2: the collective pass over the whole batch's surviving graph."""
        by_id = {mention.mention_id: mention for mention in mentions}
        feasible = {
            mention_id: frozenset(item.evidence_by_ref()) for mention_id, item in prepared.items()
        }
        return collective_resolution(by_id, feasible, self._max_iterations)

    def _anchor(
        self,
        mentions: tuple[ResolutionMention, ...],
        prepared: Mapping[str, _Prepared],
        scope: ResolutionScope,
    ) -> dict[str, _AnchorAssignment]:
        """Pass 3: one anchor per entity, canonically first, and the ``ENT-`` ref it names.

        Three cases, in the order they are checked, and the order is what makes identity stable:

        1. the scope already records an anchor for this entity or for this candidate - reuse it
           verbatim, because an anchor is *recorded* and a recomputed one is the defect;
        2. the candidate already carries an established ``entity_ref`` - adopt it, and record the
           canonically-first mention as its anchor so the next batch has something to find;
        3. nothing exists yet - mint ``ENT-`` from the canonically-first mention that reached it.

        Case 3 is the only one that creates identity, and it creates it once: the second mention in
        the same batch finds the assignment the first one made and joins it, which is why a third
        mention later cannot move the entity.

        The anchor is elected from the mention's **top-scoring surviving candidate**, not from its
        verdict's winner. The entity a mention landed on exists whether or not the verdict could
        pick between two of them, and anchoring on the verdict would leave an ambiguous mention
        with no anchor for the next one to join.
        """
        by_mention: dict[str, _AnchorAssignment] = {}
        by_target: dict[str, _AnchorAssignment] = {}
        for mention in mentions:
            item = prepared[mention.mention_id]
            target = item.leading_candidate_ref()
            if target is None:
                by_mention[mention.mention_id] = _AnchorAssignment(
                    logical_entity_ref="",
                    anchor_mention_id=mention.mention_id,
                    anchor_key=item.normalized.surface_key,
                    candidate_ref="",
                    established=False,
                )
                continue
            held = by_target.get(target)
            if held is not None:
                by_mention[mention.mention_id] = held
                continue
            candidate = item.candidate_for(target)
            recorded = scope.anchor_for(target)
            if recorded is None and candidate is not None:
                recorded = scope.anchor_for(candidate.entity_ref)
            if recorded is not None:
                assignment = _AnchorAssignment(
                    logical_entity_ref=recorded.logical_entity_ref,
                    anchor_mention_id=recorded.anchor_mention_id,
                    anchor_key=recorded.anchor_key or item.normalized.surface_key,
                    candidate_ref=target,
                    established=True,
                )
            elif candidate is not None and candidate.has_established_ref:
                assignment = _AnchorAssignment(
                    logical_entity_ref=candidate.entity_ref,
                    anchor_mention_id=mention.mention_id,
                    anchor_key=item.normalized.surface_key,
                    candidate_ref=target,
                    established=True,
                )
            else:
                assignment = _AnchorAssignment(
                    logical_entity_ref=logical_entity_ref_for(
                        mention.tenant_id, scope.scope_id, mention.mention_id
                    ),
                    anchor_mention_id=mention.mention_id,
                    anchor_key=item.normalized.surface_key,
                    candidate_ref=target,
                    established=False,
                )
            by_target[target] = assignment
            by_mention[mention.mention_id] = assignment
        return by_mention

    def _decide(
        self,
        mention: ResolutionMention,
        item: _Prepared,
        collective: CollectiveOutcome,
        assignment: _AnchorAssignment,
        scope: ResolutionScope,
    ) -> ResolutionDecision:
        """Pass 4: the verdict, the hypothesis, and the content-addressed decision."""
        survivors = item.survivors_after(collective)
        scored = item.scored(survivors)
        verdict, notes = self._verdict(survivors, scored, collective, item)
        resolved_ref = assignment.logical_entity_ref if verdict.is_resolved else ""
        kept = {entry.candidate_ref for entry in survivors}
        hypothesis = self._hypothesis(mention, item, survivors, assignment, verdict)
        corroboration = survivors[0].corroboration if verdict.is_resolved else 0
        operator_ref = ""
        if self._operator is not None:
            operator_ref = "{}@{}".format(
                getattr(self._operator, "relation_type", ""),
                getattr(self._operator, "schema_version", ""),
            )
        return ResolutionDecision(
            mention_id=mention.mention_id,
            surface=mention.surface,
            verdict=verdict,
            logical_entity_ref=resolved_ref,
            anchor_mention_id=assignment.anchor_mention_id if resolved_ref else "",
            anchor_key=assignment.anchor_key if resolved_ref else "",
            merged_mentions=item.merged_mentions(assignment) if resolved_ref else (),
            considered=item.blocking.survivor_refs,
            surviving=tuple(entry.candidate_ref for entry in survivors),
            scored=scored,
            evidence=tuple(entry.evidence for entry in survivors),
            reasons=tuple(
                reason for entry in survivors for reason in entry.evidence.reasons
            ),
            blocked_out=item.refused
            + tuple(
                reason
                for entry in item.evidence
                if entry.candidate_ref not in kept
                for reason in entry.reasons
            ),
            normalization=item.normalized.comparison_keys,
            blocking=item.blocking,
            collective=collective,
            hypothesis=hypothesis,
            corroboration=corroboration,
            confidence_parts=self._confidence_parts(verdict, survivors, collective),
            resolution_scope_id=scope.scope_id,
            tenant_id=mention.tenant_id,
            operator_ref=operator_ref,
            normalization_version=mention.normalization_version,
            ontology_version=mention.ontology_version,
            regime_id=mention.regime_id,
            notes=tuple(notes) + item.notes,
        )

    def _refuse_out_of_scope(
        self, mention: ResolutionMention, scope: ResolutionScope
    ) -> ResolutionDecision:
        """A mention from outside the scope's tenant gets no comparison at all.

        Fail-closed in the strictest available form: not a lower score, not a pruned candidate -
        no candidate was ever proposed, so nothing about the scope's universe was even measured
        against this mention (constitution IV).
        """
        return ResolutionDecision(
            mention_id=mention.mention_id,
            surface=mention.surface,
            verdict=ResolutionVerdict.UNRESOLVED,
            blocked_out=(
                CompatibilityReason(
                    "",
                    CompatibilityLayer.CONTEXT,
                    "mention_outside_scope_tenant",
                    ReasonVerdict.REFUSED,
                    detail=(
                        f"mention tenant {mention.tenant_id!r} is not the scope tenant "
                        f"{scope.tenant_id!r}; refused without comparison"
                    ),
                ),
            ),
            notes=("cross-tenant mention refused before any candidate was proposed",),
            resolution_scope_id=scope.scope_id,
            tenant_id=mention.tenant_id,
        )

    def _verdict(
        self,
        survivors: tuple[_Survivor, ...],
        scored: tuple[tuple[str, float], ...],
        collective: CollectiveOutcome,
        item: _Prepared,
    ) -> tuple[ResolutionVerdict, tuple[str, ...]]:
        """The verdict, and the notes that explain it. Never a coin-flip, never a silent default."""
        notes: list[str] = []
        mention_id = item.mention.mention_id
        if not survivors:
            mine = [
                removal
                for removal in collective.removals
                if removal.mention_id == mention_id
            ]
            if item.blocking.after_count == 0:
                notes.append(
                    "no candidate survived blocking for any comparison key "
                    f"{list(item.blocking.query_keys)}"
                )
            elif mine:
                notes.append(
                    f"{item.blocking.after_count} candidate(s) survived blocking and the "
                    "collective pass then closed every one of them: "
                    + ", ".join(
                        f"{removal.candidate_ref} ({removal.code})" for removal in mine
                    )
                )
            else:
                notes.append(
                    f"{item.blocking.after_count} candidate(s) survived blocking and every one was "
                    "removed by a compatibility filter; the reasons are recorded under BLOCKED"
                )
            return (ResolutionVerdict.UNRESOLVED, tuple(notes))
        top_ref, top_score = scored[0]
        if not collective.applied:
            notes.append(
                "collective resolution did not converge within its iteration cap; the "
                "pre-collective candidate sets are used and collective_applied is False"
            )
        if top_ref in collective.contested:
            notes.append(
                f"the best-supported candidate {top_ref} is contested by two mutually exclusive "
                "mentions; a contradiction is reported, never averaged"
            )
            return (ResolutionVerdict.CONFLICTED, tuple(notes))
        if len(scored) == 1:
            return (ResolutionVerdict.RESOLVED, tuple(notes))
        runner_up = scored[1][1]
        if top_score - runner_up > self._margin:
            return (ResolutionVerdict.RESOLVED, tuple(notes))
        notes.append(
            f"candidates {top_ref} and {scored[1][0]} are equally supported at {top_score}; "
            "ambiguity is reported with both listed and neither is preferred"
        )
        return (ResolutionVerdict.AMBIGUOUS, tuple(notes))

    def _hypothesis(
        self,
        mention: ResolutionMention,
        item: _Prepared,
        survivors: tuple[_Survivor, ...],
        assignment: _AnchorAssignment,
        verdict: ResolutionVerdict,
    ) -> EntityHypothesis | None:
        """The entity hypothesis, or ``None`` when the verdict named no entity.

        Built from the same evidence as the verdict, so it cannot disagree with it: an ambiguous or
        unresolved decision has no hypothesis at all rather than a hypothesis pointing at the first
        candidate.
        """
        if not verdict.is_resolved or not assignment.logical_entity_ref:
            return None
        entry = survivors[0]
        candidate = entry.candidate
        return EntityHypothesis(
            logical_entity_ref=assignment.logical_entity_ref,
            candidate_ref=entry.candidate_ref,
            name=candidate.name if candidate is not None else mention.surface,
            anchor_mention_id=assignment.anchor_mention_id,
            merged_mentions=item.merged_mentions(assignment),
            evidence_refs=entry.evidence.reasons[:0],
            corroboration=entry.corroboration,
            new_entity=not assignment.established,
            established=assignment.established,
        )

    def _confidence_parts(
        self,
        verdict: ResolutionVerdict,
        survivors: tuple[_Survivor, ...],
        collective: CollectiveOutcome,
    ) -> tuple[tuple[str, float], ...]:
        """The named contributions to the decision's confidence, in a fixed order."""
        parts: list[tuple[str, float]] = [("base", 0.0)]
        if verdict is ResolutionVerdict.RESOLVED:
            parts.append(("decisive_survivor", _CONF_DECISIVE))
        elif verdict is ResolutionVerdict.AMBIGUOUS:
            parts.append(("ambiguous_survivors", _CONF_AMBIGUOUS))
        elif verdict is ResolutionVerdict.CONFLICTED:
            parts.append(("contested_candidate", _CONF_CONTESTED))
        else:
            parts.append(("no_survivor", _CONF_NO_SURVIVOR))
        if verdict.is_resolved and survivors:
            corroboration = survivors[0].corroboration
            parts.append(
                (
                    "independent_corroboration",
                    min(_CONF_CORROBORATION_STEP * corroboration, _CONF_CORROBORATION_CAP),
                )
            )
            if corroboration == 0 and survivors[0].same_source_only:
                parts.append(("same_source_only", _CONF_SAME_SOURCE_ONLY))
        if collective.applied and collective.converged:
            parts.append(("collective_converged", _CONF_COLLECTIVE))
        weakened = sum(
            1
            for entry in survivors
            for reason in entry.evidence.reasons
            if reason.verdict is ReasonVerdict.WEAKENED
        )
        if weakened:
            parts.append(
                (
                    "weakened_reasons",
                    _CONF_WEAKENED_STEP * min(weakened, _CONF_WEAKENED_CAP),
                )
            )
        return tuple(parts)


@dataclass(frozen=True)
class _AnchorAssignment:
    """The entity a mention landed on, and which mention introduced it."""

    logical_entity_ref: str
    anchor_mention_id: str
    anchor_key: str
    candidate_ref: str
    established: bool


@dataclass(frozen=True)
class _Survivor:
    """One surviving candidate with its evidence, its score and its corroboration count."""

    candidate_ref: str
    evidence: CompatibilityEvidence
    candidate: ResolutionCandidate | None

    @property
    def score(self) -> float:
        return self.evidence.score

    @property
    def corroboration(self) -> int:
        return self.evidence.independent_corroboration

    @property
    def same_source_only(self) -> bool:
        return self.evidence.same_source_only


@dataclass(frozen=True)
class _Prepared:
    """What pass 1 produced for one mention, kept so the later passes need not redo it."""

    mention: ResolutionMention
    normalized: NormalizedSurface
    blocking: BlockingOutcome
    evidence: tuple[CompatibilityEvidence, ...]
    candidates: Mapping[str, ResolutionCandidate]
    refused: tuple[CompatibilityReason, ...]
    notes: tuple[str, ...] = ()

    def evidence_by_ref(self) -> frozenset[str]:
        return frozenset(entry.candidate_ref for entry in self.evidence)

    def candidate_for(self, ref: str) -> ResolutionCandidate | None:
        return self.candidates.get(ref)

    def leading_candidate_ref(self) -> str | None:
        """The candidate this mention's verdict is *about*: the top-scoring one it still holds.

        The anchor is a property of the entity, so it has to be elected before the verdict is known
        - and electing it from the top-scoring candidate is the only choice that a later verdict
        cannot contradict. It is deliberately **not** the verdict's winner: an ambiguous mention
        still needs the entity it landed on anchored, or the next mention would have nothing to
        join.
        """
        if not self.evidence:
            return None
        return min(
            self.evidence,
            key=lambda entry: (-entry.score, entry.candidate_ref),
        ).candidate_ref

    def survivors_after(self, collective: CollectiveOutcome) -> tuple[_Survivor, ...]:
        """The survivors the collective pass left, canonically ordered by descending score.

        When the pass was not applied this is exactly the pre-collective set, so a caller can tell
        "the graph resolved this" from "the graph was skipped" by reading
        :attr:`CollectiveOutcome.applied` and get the same answer either way.
        """
        if not collective.applied:
            allowed = self.evidence_by_ref()
        else:
            allowed = frozenset(collective.feasible_for(self.mention.mention_id))
        return tuple(
            sorted(
                (
                    _Survivor(entry.candidate_ref, entry, self.candidate_for(entry.candidate_ref))
                    for entry in self.evidence
                    if entry.candidate_ref in allowed
                ),
                key=lambda entry: (-entry.score, entry.candidate_ref),
            )
        )

    def scored(self, survivors: tuple[_Survivor, ...]) -> tuple[tuple[str, float], ...]:
        return tuple((entry.candidate_ref, entry.score) for entry in survivors)

    def merged_mentions(self, assignment: _AnchorAssignment) -> tuple[str, ...]:
        """Every mention known to be part of the entity this one landed on.

        The anchor, this mention, and whatever the record itself already carried - so "the third
        mention joined" is visible in the decision's own material, which is what makes the
        ``resolution_decision_id`` move while the ``logical_entity_ref`` holds.
        """
        candidate = self.candidate_for(assignment.candidate_ref)
        carried = candidate.support_mention_ids if candidate is not None else ()
        return tuple(
            sorted(
                {
                    assignment.anchor_mention_id,
                    self.mention.mention_id,
                    *carried,
                }
            )
        )
