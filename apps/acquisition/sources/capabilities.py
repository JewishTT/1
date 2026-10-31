"""Capability offers derived from the live source catalogue (spec 026 FR-097, FR-098).

The enrichment planner can only fetch what some source says it can fetch. Until now that
sentence had no producer: :mod:`sources.catalogue` validated 151 definitions and stopped at
the boundary, so "who can produce ``certificate`` for a ``domain``" was answered by whatever
a consumer happened to hardcode. FR-097 requires capabilities to be *data discoverable at
runtime*, and FR-098 requires the planner to invent nothing. Both are satisfied by deriving
the offers from the same YAML the executor runs, with no second vocabulary to drift.

**The attribute name is the declared kind.** A definition says what its fields *are*
(``kind: timestamp``, ``kind: leak``, ``kind: subdomain``) and this module offers exactly
those strings. It does not map them onto a closed vocabulary, because a closed vocabulary
is precisely the invention FR-098 forbids: a source offering ``bcell`` for a person would
have to be forced into ``organization``, and the planner would then schedule a fetch under
a name the source never used. An attribute nobody has heard of must still be plannable, so
the set stays open and whatever the catalogue declares is what the planner sees.

**A source that declares nothing offers nothing.** :func:`offers_for` returns an empty tuple
rather than a placeholder offer with no attributes. An offer with zero attributes is a claim
that cannot be acted on, and emitting one would inflate the source count that
:func:`catalogue_offers` reports while planning no work at all.

**Layers.** ``CapabilityOffer`` lives in ``apps/science/context/enrichment.py``; this module
lives in ``apps/acquisition``, which sits below it. Importing it would be an upward
dependency and would add a layer-boundary violation, so the offers are returned as plain
dicts carrying exactly :data:`OFFER_FIELDS` -- the same field names, in the same order, with
the same defaults. A higher layer rebuilds a ``CapabilityOffer`` from a dict by field name
(``CapabilityOffer(**offer)``), which is structural compatibility by construction rather than
by shared import.

**What is passed through verbatim, and what that costs.** ``contact`` is the catalogue's
vocabulary (``none`` / ``public_api`` / ``search_engine`` / ``archive`` / ``passive_dns`` /
``active``); ``CapabilityOffer`` documents ``passive`` / ``polite`` / ``intrusive``. No
translation is applied, because any table between the two would be invented -- and inventing
one silently downgrades an ``active`` source to ``intrusive`` and claims the mapping was
always true. The two vocabularies differ; a consumer that needs them unified should say so
in one place, on purpose, rather than inherit a guess from here.

The same applies to ``applies_to: [any]``, which nine definitions use to mean "any entity
kind". It is *not* rewritten to the empty tuple that ``CapabilityOffer.applies_to`` treats as a
wildcard: rewriting a declared kind into a wildcard changes what the offer claims, and the
planner would then schedule ``feodo_tracker`` -- a botnet command-and-control IP feed -- against
a ``domain`` on our say-so. :func:`offers_for_entity` therefore matches declared kinds only, so
those nine are not returned by a request for any concrete kind. They stay visible as the literal
kind ``any`` in ``entity_kinds``, which is where a consumer that *does* want the wildcard
semantics can see them and decide that in one place, on purpose.

Ordering is derived from offer content, never from filesystem or dictionary order, so two
runs over the same catalogue produce byte-identical plans and a diff means something.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

from sources.catalogue import SourceDefinition, load_catalogue

__all__ = [
    "ANY_KIND",
    "OFFER_FIELDS",
    "catalogue_offers",
    "offer_sort_key",
    "offers_for",
    "offers_for_entity",
]

#: The offer's fields, in ``CapabilityOffer`` declaration order. Consumers rebuild a
#: ``CapabilityOffer`` from a dict by these names, so renaming one here silently breaks
#: every higher layer that maps by key.
OFFER_FIELDS: tuple[str, ...] = (
    "source_id",
    "entity_kinds",
    "attributes",
    "cost_class",
    "contact",
    "key_env",
    "binary",
    "os_requirement",
)

#: The literal ``applies_to`` entry nine definitions use to mean "any kind". Preserved
#: verbatim in ``entity_kinds`` and not honoured as a wildcard -- see the module docstring.
ANY_KIND = "any"

_WHITESPACE_RE = re.compile(r"\s+")


def _normalise_kind(raw: Any) -> str:
    """One declared kind as a comparable token, or "" when it is not usable as one.

    Definitions are hand-written YAML and are edited by hand, so a kind can arrive as
    ``Timestamp`` or ``"timestamp "``. That has not happened yet -- across all 145
    definitions every declared kind is already lowercase and trimmed, so this normalisation
    currently rewrites nothing -- but the cost of it being wrong later is silent: one
    attribute split into two spellings halves every gap count derived from it, with no
    error anywhere to notice. Collapsing whitespace and case cannot invent a name; it can
    only merge two spellings of the same one. Anything that is not a string yields ""
    rather than a ``str()`` of a list or ``None``: a malformed declaration is dropped, not
    guessed at.
    """
    if not isinstance(raw, str):
        return ""
    return _WHITESPACE_RE.sub(" ", raw).strip().lower()


def _field_kinds(parse: Any) -> Iterator[str]:
    """Normalised ``kind`` of every field in a definition's ``parse`` block.

    ``fields`` is a mapping of field name to spec in all 126 definitions that carry a parse
    block; the list form is handled because it is a one-line accommodation and a catalogue
    that grows one file of it would otherwise silently contribute zero kinds.
    """
    if not isinstance(parse, Mapping):
        return
    fields = parse.get("fields")
    if isinstance(fields, Mapping):
        specs: Iterable[Any] = fields.values()
    elif isinstance(fields, (list, tuple)):
        specs = fields
    else:
        return
    for spec in specs:
        if isinstance(spec, Mapping):
            yield _normalise_kind(spec.get("kind"))


def _declared_attributes(definition: SourceDefinition) -> tuple[str, ...]:
    """Every attribute this source declares it can produce, sorted and deduplicated.

    Two declarations feed one attribute set: ``entity_hints`` (what the source says it
    looks for) and ``parse.fields[].kind`` (what it says the fields are). Both are the
    source's own words. Hints are broader and catch a definition with no parse block; kinds
    are what the payload will actually carry, and 27 of them are ``unknown`` -- kept, because
    the source declared that and silently dropping it would understate what it returns.
    """
    found = {_normalise_kind(hint) for hint in definition.entity_hints}
    found.update(_field_kinds(definition.definition.get("parse")))
    found.discard("")
    return tuple(sorted(found))


def _declared_kinds(definition: SourceDefinition) -> tuple[str, ...]:
    """``applies_to`` deduplicated and sorted, for deterministic offer content.

    Trimmed but otherwise left alone: an entity kind is the source's own label for what it
    consumes, so it belongs to the catalogue's vocabulary and not to a normalised one.
    :func:`offers_for_entity` compares case-insensitively for that reason rather than
    requiring every definition to be re-spelled here. ``SourceDefinition`` has already coerced
    the sequence to ``tuple[str, ...]``, so nothing needs a ``str()`` to be compared.
    """
    trimmed = {kind.strip() for kind in definition.applies_to}
    trimmed.discard("")
    return tuple(sorted(trimmed))


def _binary_of(definition: SourceDefinition) -> str:
    """The local binary this source needs, or "" when it is an HTTP source.

    19 definitions are local tools. That is not a detail the planner can be left to guess:
    ``CapabilityOffer.runnable`` is False whenever ``binary`` is set, so a missing value here
    would schedule a fetch that cannot execute.
    """
    tool = definition.tool
    if not isinstance(tool, Mapping):
        return ""
    return str(tool.get("binary") or "")


def offers_for(definition: SourceDefinition) -> tuple[dict, ...]:
    """The offers this one definition makes, as at most one entry.

    One entry per source, because an offer carries a tuple of attributes: a source offering
    ``timestamp`` and ``domain`` is one capability that yields two, not two capabilities.
    Splitting per attribute would multiply the source count without adding any scheduling
    choice, since the planner indexes offers by attribute anyway.

    Returns ``()`` for a definition that declares no attribute at all. That is the honest
    answer and it is also the useful one: an offer with no attributes names no work, so
    emitting one would inflate the catalogue's apparent coverage with nothing behind it.
    """
    attributes = _declared_attributes(definition)
    if not attributes:
        return ()
    offer = {
        "source_id": definition.source_id,
        "entity_kinds": _declared_kinds(definition),
        "attributes": attributes,
        "cost_class": definition.cost_class,
        "contact": definition.contact,
        "key_env": definition.key_env,
        "binary": _binary_of(definition),
        "os_requirement": definition.os_requirement,
    }
    return (offer,)


def offer_sort_key(offer: Mapping[str, Any]) -> tuple[Any, ...]:
    """Total order over offers, from their content alone.

    Each value is coerced to the shape of its field rather than to one type for all of them:
    a sequence becomes a tuple of strings, anything else a string. That is what makes the key
    total. ``OFFER_FIELDS`` mixes scalars with tuples, so a missing key defaulted to ``()`` would
    put a tuple next to a string and raise :class:`TypeError` mid-sort on any offer a caller
    passes in by hand -- and a planner should not be one bad dict away from a crash. Coercing
    by shape also keeps the key in step with ``OFFER_FIELDS`` automatically: adding a field
    needs no second list here to be updated.

    ``source_id`` is already content-addressed, but it leads anyway: it is the field a reader
    scans, and a stable prefix means the ordering survives a change to any other field.
    """
    return tuple(
        tuple(str(item) for item in value) if isinstance(value, (list, tuple)) else str(value)
        for value in (offer.get(name, "") for name in OFFER_FIELDS)
    )


def catalogue_offers(root: Path | None = None) -> tuple[dict, ...]:
    """Every offer the whole catalogue makes, deterministically.

    Built from the live YAML via :func:`sources.catalogue.load_catalogue`, so the offers
    cannot disagree with the definitions the executor runs: a source added to the catalogue
    is offerable the moment it loads, with no registration step and no second list to update.
    Rejected definitions contribute nothing, exactly as they contribute no executable source.
    Today all 151 definitions load and all 151 declare at least one attribute, so every one
    of them yields exactly one offer and 206 distinct attribute names exist across them.
    """
    definitions, _rejected = load_catalogue(root)
    offers = [offer for definition in definitions for offer in offers_for(definition)]
    offers.sort(key=offer_sort_key)
    return tuple(offers)


def offers_for_entity(kind: str, root: Path | None = None) -> tuple[dict, ...]:
    """The offers whose declared kinds cover ``kind``, in :func:`catalogue_offers` order.

    An offer naming no kinds applies to everything, matching ``CapabilityOffer.applies_to``:
    a source that declares no kinds is claiming to be general, and making it re-declare per
    kind would make a new entity type silently under-enriched. No source in the catalogue does
    that today -- all 145 declare at least one -- so that branch is a rule for a definition
    added later, not a path anything runs through now. A kind that normalises to nothing
    selects nothing, because "the empty kind" is not an entity and matching it against the
    general offer would return every general source in the catalogue.

    ``applies_to: [any]`` is not honoured here; see the module docstring for why, and note
    what it costs: ``person`` and ``ip`` are not the catalogue's vocabulary, so asking for
    them returns nothing rather than the ``username`` and ``ipv4`` sources that look like the
    answer. Mapping them would be exactly the invention FR-098 forbids, so the caller asks
    for the kind the definitions actually declare.

    The comparison is case-insensitive because entity kinds reach this function from entity
    detection, which is free to capitalise, while the offers hold whatever the definition
    wrote. Filtering a sorted sequence keeps it sorted, so no re-sort is needed.
    """
    wanted = _normalise_kind(kind)
    if not wanted:
        return ()
    return tuple(
        offer
        for offer in catalogue_offers(root)
        if not offer["entity_kinds"]
        or any(_normalise_kind(k) == wanted for k in offer["entity_kinds"])
    )


def offers_for_query_kinds(kinds: Iterable[str]) -> tuple[dict, ...]:
    """The union of offers any of ``kinds`` would select, one entry per source.

    The catalogue declares what a source can be *asked with* -- ``domain``, ``username``,
    ``keyword``, ``ipv4`` -- and never what kind of thing the answer is. Those are different
    questions and conflating them is how a request for a person silently scheduled nothing:
    no definition declares ``applies_to: person``, because a name is not an address, and the
    sources that can speak about a person are the ones that take a name or a username.

    So the caller states what it actually holds, and this unions the offers it makes runnable.
    A kind nothing declares contributes nothing and is not an error -- a caller offering four
    shapes for one subject should get the sources that match any of them, not a complaint
    about the fifth.

    Deduplicated by ``source_id`` and left in catalogue order, so the union is a set of
    capabilities rather than a multiset: one source that matches two query shapes is still one
    thing to run.
    """
    wanted = tuple(dict.fromkeys(_normalise_kind(k) for k in kinds if _normalise_kind(k)))
    if not wanted:
        return ()
    seen: set[str] = set()
    selected: list[dict] = []
    for offer in catalogue_offers():
        if seen.__contains__(offer["source_id"]):
            continue
        declared = {_normalise_kind(k) for k in offer["entity_kinds"]}
        if not declared or declared & set(wanted):
            seen.add(offer["source_id"])
            selected.append(offer)
    return tuple(selected)
