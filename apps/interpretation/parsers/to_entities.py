"""Turn a source's parsed fields into typed entities (spec 025 §33).

The parser produces values and the kind each value is. This module decides which of those
are *things that can be the subject of a claim*, mints a referent for each, and hands them
to the resolution layer. It is the seam that was missing: a live sweep showed 37 field kinds
outside the ontology reaching the pipeline and being dropped at a classification step, while
106 declared kinds mapped onto entities that the ontology had no name for.

**The three-way split is the design.** :func:`domain.ontology.axis_for` returns ``entity``,
``value`` or ``unknown``, and this module acts differently on each. An entity becomes a
referent. A value becomes an attribute carried on whatever claim the record supports -- a
timestamp is not a thing, and minting one would let a scope lattice claim a moment inherits
``Thing``. An unknown kind becomes a referent with no declared type, because the source told
us something real that we cannot yet name, and losing it would lose the observation.

**Deterministic ids, no names as identity.** A referent is addressed by
``(kind, canonical)``, never by the string alone. Two sources reporting ``Cloudflare`` as an
organization and as an ISP produce two referents, and that disagreement is exactly what a
resolution layer is supposed to see -- collapsing them here would destroy it before anyone
looked.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from domain.derivation import (
    Derivation,
    DerivationGraph,
    MethodFingerprint,
    NumericEnvironment,
)
from domain.ontology import (
    KIND_ALIASES,
    EntityType,
    ValueKind,
    axis_for,
    classify_kind,
    value_kind_for,
)

__all__ = [
    "PARSER_METHOD",
    "ParsedEntity",
    "SourceInterpretation",
    "canon_of",
    "interpret_parse",
]

#: The method that reads a source's declared fields. Recorded on every derivation so a later
#: question -- "why does this referent have this type" -- names the thing that answered it
#: rather than the layer that happened to be running.
PARSER_METHOD = MethodFingerprint("parser.fields", "v1")

#: Entity types whose canonical form is case-insensitive and therefore lowercased. The rest
#: keep their case, because lowercasing ``Example Corp`` and ``example corp`` into one
#: referent merges two legally distinct names.
_LOWERCASE_TYPES: frozenset[EntityType] = frozenset(
    {
        EntityType.DOMAIN,
        EntityType.SUBDOMAIN,
        EntityType.EMAIL,
        EntityType.IP,
        EntityType.CRYPTO,
        EntityType.HANDLE,
        EntityType.ASN,
        EntityType.CVE,
        EntityType.HASH,
        EntityType.MAC_ADDRESS,
        EntityType.BSSID,
        EntityType.PREFIX,
        EntityType.NAMESERVER,
        EntityType.DOI,
        EntityType.ORCID,
        EntityType.CPE,
    }
)


def canon_of(entity_type: EntityType, value: str) -> str:
    """The canonical spelling of a value for one entity type.

    Type-dependent on purpose. A domain is case-insensitive by DNS, a person's name is not,
    and normalising both the same way would merge ``EXAMPLE.COM`` with a distinct company
    named ``Example Com``.
    """
    text = str(value or "").strip()
    if entity_type in _LOWERCASE_TYPES:
        return text.lower()
    return text


@dataclass(frozen=True, slots=True)
class ParsedEntity:
    """One thing the source said about, ready for resolution."""

    referent_id: str
    kind: str
    value: str
    canonical: str
    entity_type: EntityType
    #: The declared kind as written in the source, before alias resolution. Kept so a reader
    #: can see that ``btc_address`` became ``crypto`` rather than discovering the rewrite.
    declared_kind: str = ""
    #: ``entity`` / ``value`` / ``unknown`` from :func:`axis_for`.
    axis: str = "entity"
    #: The record's other fields, carried as attributes. Not entities of their own.
    attributes: Mapping[str, str] = None  # type: ignore[assignment]

    def attribute_map(self) -> Mapping[str, str]:
        return dict(self.attributes or {})

    def as_dict(self) -> dict[str, Any]:
        return {
            "referent_id": self.referent_id,
            "kind": self.kind,
            "value": self.value,
            "canonical": self.canonical,
            "entity_type": self.entity_type.value,
            "declared_kind": self.declared_kind,
            "axis": self.axis,
        }


@dataclass(frozen=True, slots=True)
class SourceInterpretation:
    """Everything one source response contributed."""

    source_name: str
    entities: tuple[ParsedEntity, ...] = ()
    #: Field values that are attributes rather than things, keyed by field name.
    values: Mapping[str, str] = None  # type: ignore[assignment]
    #: Kinds the ontology has no name for. Carried, never dropped -- see the module docstring.
    unclassified: tuple[str, ...] = ()
    derivations: DerivationGraph = None  # type: ignore[assignment]
    record_count: int = 0

    @property
    def typed(self) -> tuple[ParsedEntity, ...]:
        return tuple(e for e in self.entities if e.axis == "entity")

    @property
    def untyped(self) -> tuple[ParsedEntity, ...]:
        """Referents admitted with no declared type.

        Not a failure: these are the observations the world contains and the ontology cannot
        yet name. A pipeline that discarded them would be quietly narrowing its own coverage.
        """
        return tuple(e for e in self.entities if e.entity_type is EntityType.UNKNOWN)

    def kinds_seen(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for entity in self.entities:
            key = entity.entity_type.value
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items()))

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "entities": len(self.entities),
            "typed": len(self.typed),
            "untyped": len(self.untyped),
            "values": len(self.values or {}),
            "unclassified": list(self.unclassified),
            "kinds": self.kinds_seen(),
            "record_count": self.record_count,
        }


def _referent_id(kind: str, canonical: str, *, tenant_id: str) -> str:
    from domain.relation_identity import digest128

    return f"REF-{digest128(f'{tenant_id}|{kind}|{canonical}')}"


def interpret_parse(
    outcome: Any,
    *,
    source_name: str,
    tenant_id: str = "default-tenant",
    method: MethodFingerprint | None = None,
) -> SourceInterpretation:
    """Read one :class:`~parsers.families.ParseOutcome` into typed referents.

    ``outcome`` is duck-typed on ``status``/``records`` so this module does not import the
    parser package: the acquisition side and the interpretation side stay independent, and a
    test can pass a hand-built outcome.
    """
    fingerprint = method or PARSER_METHOD
    graph = DerivationGraph()
    entities: dict[str, ParsedEntity] = {}
    values: dict[str, str] = {}
    unclassified: list[str] = []
    record_count = 0

    for record in getattr(outcome, "records", ()) or ():
        record_count += 1
        record_values: dict[str, str] = {}
        for name, declared in sorted(record.kinds.items()):
            raw_name = KIND_ALIASES.get(declared, declared)
            axis = axis_for(raw_name)
            for value in record.all_of(name):
                if not value or not value.strip():
                    continue
                if axis != "entity":
                    # A value on a claim. Recorded once, by field name, because two records
                    # reporting the same timestamp are the same claim and not two.
                    values.setdefault(name, value.strip())
                    continue
                parsed = _entity_for(
                    raw_name,
                    declared,
                    value.strip(),
                    record_values=record_values,
                    tenant_id=tenant_id,
                    observation_ref="",
                )
                if parsed is None:
                    continue
                if axis == "unknown":
                    unclassified.append(declared)
                entities.setdefault(parsed.referent_id, parsed)

    for entity in entities.values():
        graph.add(
            Derivation(
                method=fingerprint,
                inputs=(entity.declared_kind or entity.kind,),
                output=f"{entity.referent_id}@{entity.entity_type.value}",
                # The referent id is in the statement on purpose. ``output`` is
                # ``REF-…@type`` and the join works on it, but a reader opening the ledger
                # sees statements; one reading "13335 read as asn from ipwho_is" cannot tell
                # *which* referent that was, so the answer to "why is this one an ASN" stays
                # unreadable even though the row is there.
                statement=(
                    f"{entity.referent_id} is {entity.canonical} read as"
                    f" {entity.entity_type.value} from {source_name}"
                ),
                environment=NumericEnvironment(),
                confidence=None if entity.entity_type is EntityType.UNKNOWN else 1.0,
            )
        )

    return SourceInterpretation(
        source_name=source_name,
        entities=tuple(sorted(entities.values(), key=lambda e: e.referent_id)),
        values=values,
        unclassified=tuple(sorted(set(unclassified))),
        derivations=graph,
        record_count=record_count,
    )


def _entity_for(
    resolved_kind: str,
    declared_kind: str,
    value: str,
    *,
    record_values: Mapping[str, str],
    tenant_id: str,
    observation_ref: str,
) -> ParsedEntity | None:
    entity_type = classify_kind(resolved_kind)
    axis = axis_for(resolved_kind)
    if entity_type is None:
        # An axis we know is ``entity`` but whose name is not a type. Admitted untyped: the
        # evidence is real and the ontology is behind, which is the wrong way round to fail.
        entity_type = EntityType.UNKNOWN
        axis = "unknown"
    canonical = canon_of(entity_type, value)
    return ParsedEntity(
        referent_id=_referent_id(resolved_kind, canonical, tenant_id=tenant_id),
        kind=resolved_kind,
        value=value,
        canonical=canonical,
        entity_type=entity_type,
        declared_kind=declared_kind,
        axis=axis,
        attributes=dict(record_values),
    )


def values_to_attributes(
    values: Mapping[str, Any]
) -> dict[str, str]:
    """Coerce a parse's value fields into attribute strings.

    Each is tagged with its :class:`ValueKind` so a reader knows ``port=443`` came from a
    value declaration rather than an entity mention -- the distinction is what keeps a port
    out of the entity graph.
    """
    out: dict[str, str] = {}
    for name, value in values.items():
        kind = value_kind_for(name)
        prefix = "" if kind is ValueKind.UNKNOWN else f"{kind.value}:"
        text = ", ".join(value) if isinstance(value, (list, tuple)) else str(value)
        if text.strip():
            out[str(name)] = f"{prefix}{text.strip()}" if prefix else text.strip()
    return out


def iter_typed(
    entities: Iterable[ParsedEntity],
) -> Sequence[ParsedEntity]:
    """Only the entities carrying a declared type. A view, not a filter with side effects."""
    return [e for e in entities if e.entity_type is not EntityType.UNKNOWN]