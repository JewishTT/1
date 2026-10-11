"""The vertical slice the platform was missing: subject -> sources -> invariant -> dossier.

Every part this module joins existed as a verified component and none of them were joined:
``offers_for_entity`` knew 54 sources could answer for a domain, ``plan_enrichment`` could
enumerate the 77 gaps, ``interpret_parse`` could turn bytes into typed referents, and
``from_entity_stream`` could fold a life-stream into a ``GraphInvariant``. Running the real
catalogue showed the seam was missing in the middle, so nothing produced a dossier with a
single traced fact in it.

What this service is responsible for, and what it is deliberately not:

* **It decides what to ask.** The gap list comes from the planner against the live
  catalogue, not from a hand-written source list, so a source added to the catalogue
  tomorrow is scheduled tomorrow without touching this file.
* **It keeps the three refusals visible.** Echoes, shape mismatches and attribution splits
  are collected on the report instead of being dropped, because "we asked 54 sources and
  this is what came back" is a claim the dossier has to be able to make.
* **It does not invent an identity.** The subject referent is minted from the subject's own
  kind and canonical value; a discovered entity gets its own referent and, when
  ``depth`` allows, its own invariant and its own enrichment pass.
* **It separates event time from record time.** A source that declares ``event_date`` or
  ``not_before`` dates the event; otherwise the event happened when we observed it. Both are
  carried, because conflating them is how a domain registered in 1995 appears to have been
  registered this afternoon.

Determinism: no network, no clock and no store is reached except through the constructor, so
a test can inject all three and replay the same sweep byte-for-byte. Ordering of the sweep is
by gap name, not by whatever the catalogue happens to list first.
"""

from __future__ import annotations

import hashlib
import inspect
import os
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from context.dossier import Dossier, build_dossier
from context.enrichment import (
    AttributeState,
    CapabilityOffer,
    Coverage,
    EnrichmentPlan,
    EntityProfile,
    merge_offer,
    plan_enrichment,
)
from domain.graph_invariant import GraphInvariant, from_entity_stream
from sources.capabilities import offers_for
from sources.catalogue import SourceDefinition, load_catalogue
from sources.connector import SourceConnector

#: Fields a source can use to date an event it reports about the subject. Checked in order;
#: the first one present wins. These are *event* times: when the thing happened.
_EVENT_TIME_FIELDS: tuple[str, ...] = (
    "event_date",
    "not_before",
    "registered_at",
    "created_at",
    "date",
    "published_at",
    "first_seen",
    "timestamp",
)


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _truthy(name: str) -> bool:
    return bool(os.environ.get(name, "").strip())


@dataclass(frozen=True)
class Refusal:
    """One thing a source said that the platform declined to record as a fact."""

    source: str
    attribute: str
    reason: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {
            "source": self.source,
            "attribute": self.attribute,
            "reason": self.reason,
            "detail": self.detail,
        }


@dataclass
class Discovered:
    """An entity found while enriching the subject.

    ``ref`` is its own identity, not the subject's, because the whole point of finding it is
    that it can be enriched on its own terms later.
    """

    ref: str
    type_label: str
    canonical: str
    found_by: tuple[str, ...] = ()
    observation_ref: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "entity_ref": self.ref,
            "type_label": self.type_label,
            "canonical": self.canonical,
            "found_by": ",".join(self.found_by),
            "observation_ref": self.observation_ref,
        }


@dataclass
class SourceReport:
    """What one source did, whether or not it helped."""

    source: str
    attribute: str
    outcome: str
    status: int = 0
    records: int = 0
    bytes_: int = 0
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "attribute": self.attribute,
            "outcome": self.outcome,
            "status": self.status,
            "records": self.records,
            "bytes": self.bytes_,
            "detail": self.detail,
        }


@dataclass
class EnrichmentReport:
    """Everything one enrichment pass produced, refusals included."""

    subject: EntityProfile
    plan: EnrichmentPlan
    invariant: GraphInvariant | None = None
    dossier: Dossier | None = None
    reports: tuple[SourceReport, ...] = ()
    refusals: tuple[Refusal, ...] = ()
    discovered: tuple[Discovered, ...] = ()
    stream: tuple[dict[str, Any], ...] = ()
    children: tuple[EnrichmentReport, ...] = ()
    coverage_before: Coverage | None = None
    #: What was actually asked for, verbatim. The referent is derived from it and is not
    #: reversible -- ``REF-a1b2`` says nothing about whether it was a domain or a name -- so
    #: the query travels with the report for anyone reading it back later.
    query: str = ""
    #: Why no invariant could be derived, when that happened. Never swallowed: a life-stream
    #: that silently fails to build looks exactly like a subject that never changed.
    invariant_error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "subject": {
                "entity_ref": self.subject.entity_ref,
                "type_label": self.subject.type_label,
                "known": list(self.subject.known()),
            },
            "saturation": self.plan.saturation.as_dict(),
            "gaps": [g.attribute for g in self.plan.gaps],
            "invariant": self.invariant.identity.as_dict() if self.invariant else None,
            "reports": [r.as_dict() for r in self.reports],
            "refusals": [r.as_dict() for r in self.refusals],
            "discovered": [d.as_dict() for d in self.discovered],
            "stream_events": len(self.stream),
            "invariant_error": self.invariant_error,
            "children": [c.subject.entity_ref for c in self.children],
        }


#: How many candidate sources one gap may try before it is left for the next pass. Three is
#: enough to walk past a dead host and a rate-limited one without spending a sweep on hosts
#: that are plainly not answering.
_ATTEMPTS_PER_GAP = 3

Sink = Callable[[EnrichmentReport], None]


class EnrichmentService:
    """Runs one subject through every source that can speak about it.

    Parameters
    ----------
    definitions:
        Catalogue entries. Loaded once and passed in, so 145 YAML files are not re-read per
        entity and so a test can offer a catalogue of two.
    collect:
        Async iterator yielding ``(capability, event)`` for a source definition. Defaults to
        the real connector; swapped in tests to return fixed bytes.
    parse:
        ``parse_source(definition, body, status_code=...) -> ParseOutcome``.
    interpret:
        ``interpret_parse(outcome, source_name=..., tenant_id=..., query=...)``.
    clock:
        Record-time source. Injected because "when we looked" is part of the answer and must
        be reproducible in a test.
    sink:
        Called once per completed report with the report and, if given, the invariant.
        Persistence hooks in here; the sweep itself never writes anywhere.
    """

    def __init__(
        self,
        *,
        tenant_id: str = "default-tenant",
        definitions: Sequence[SourceDefinition] | None = None,
        collect: Callable[..., Any] | None = None,
        parse: Callable[..., Any] | None = None,
        interpret: Callable[..., Any] | None = None,
        clock: Callable[[], datetime] | None = None,
        sink: Sink | None = None,
        window: timedelta = timedelta(days=7),
    ) -> None:
        self.tenant_id = tenant_id
        if definitions is None:
            definitions, _ = load_catalogue()
        self._by_id: dict[str, SourceDefinition] = {d.source_id: d for d in definitions}
        self._by_name: dict[str, SourceDefinition] = {d.name: d for d in definitions}
        self._collect = collect
        self._parse = parse
        self._interpret = interpret
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sink = sink
        self._window = window

    # ------------------------------------------------------------------ sweep

    async def enrich(
        self,
        query: str,
        *,
        kind: str = "domain",
        depth: int = 0,
        max_sources: int | None = None,
        entity_ref: str = "",
        type_label: str = "",
    ) -> EnrichmentReport:
        """Enrich one subject and return everything the pass produced.

        ``depth`` is how many generations of newly discovered entities to enrich as well. It
        defaults to 0 because an unbounded sweep over 145 sources finds new subjects forever;
        the recursion exists and is capped so a caller who wants it must say so.
        """
        subject = EntityProfile(
            entity_ref=entity_ref or _referent(kind, query),
            type_label=type_label or kind,
        )
        offers = self._offers(query, kind)
        available = {o.source_id: self._available(o) for o in offers}
        plan = plan_enrichment(subject, offers, available=available)
        coverage_before = plan.saturation

        reports: list[SourceReport] = []
        refusals: list[Refusal] = []
        discovered: dict[str, Discovered] = {}
        stream: list[dict[str, Any]] = []
        used: set[str] = set()
        wanted = max_sources if max_sources is not None else len(plan.gaps)

        # Gap name order, so two runs of the same catalogue schedule the same work.
        for gap in sorted(plan.gaps, key=lambda g: g.attribute):
            if len(used) >= wanted:
                break
            attempts = 0
            for source_id in gap.candidate_sources:
                if source_id in used or not available.get(source_id):
                    continue
                if attempts >= _ATTEMPTS_PER_GAP:
                    break
                definition = self._by_id.get(source_id)
                if definition is None or not definition.enabled:
                    continue
                used.add(source_id)
                attempts += 1
                outcome = await self._visit(
                    definition=definition,
                    gap=gap.attribute,
                    query=query,
                    subject=subject,
                    reports=reports,
                    refusals=refusals,
                    discovered=discovered,
                    stream=stream,
                )
                if outcome != "error":
                    break

        plan = plan_enrichment(subject, offers, available=available)
        invariant, invariant_error = self._invariant(stream, type_label or kind)
        dossier = (
            build_dossier(subject, invariant=invariant, plan=plan)
            if invariant is not None or plan.gaps
            else None
        )
        report = EnrichmentReport(
            query=query,
            subject=subject,
            plan=plan,
            invariant=invariant,
            dossier=dossier,
            reports=tuple(reports),
            refusals=tuple(refusals),
            discovered=tuple(sorted(discovered.values(), key=lambda d: d.ref)),
            stream=tuple(stream),
            coverage_before=coverage_before,
            invariant_error=invariant_error,
        )
        if self._sink is not None:
            # A sink that reaches storage has to be awaited; one that only collects in memory
            # need not be. Supporting both means a test can assert on the reports it was given
            # without standing up a database to prove the sweep still works.
            written = self._sink(report)
            if inspect.isawaitable(written):
                await written

        report.children = await self._recurse(report, query, depth=depth, max_sources=max_sources)
        return report

    async def _recurse(
        self,
        report: EnrichmentReport,
        query: str,
        *,
        depth: int,
        max_sources: int | None,
    ) -> tuple[EnrichmentReport, ...]:
        if depth <= 0 or not report.discovered:
            return ()
        children = []
        for found in report.discovered:
            children.append(
                await self.enrich(
                    found.canonical,
                    kind=found.type_label or "domain",
                    depth=depth - 1,
                    max_sources=max_sources,
                    entity_ref=found.ref,
                    type_label=found.type_label,
                )
            )
        return tuple(children)

    # --------------------------------------------------------------- per source

    async def _visit(
        self,
        *,
        definition: SourceDefinition,
        gap: str,
        query: str,
        subject: EntityProfile,
        reports: list[SourceReport],
        refusals: list[Refusal],
        discovered: dict[str, Discovered],
        stream: list[dict[str, Any]],
    ) -> str:
        """Run one source, absorb what it says, and report what it was.

        Returns the outcome so the caller can move on. A gap with two candidate sources must
        not be decided by whichever one happens to be listed first: a refused host, a rate
        limit or a retired endpoint is routine, and letting the first failure end the gap
        would silently discard the attribute the second source could have supplied.
        

        A source that cannot be reached is recorded, not raised. Of 145 definitions a sweep
        meets refused hosts, 429s, retired endpoints and DNS failures, and one of those must
        not cost the other fifty the run -- the dossier's claim is "we asked and this is what
        came back", and a source that never answered belongs in that sentence too.
        """
        parse, interpret = self._parsers()
        try:
            async for capability, _event in _drive(
                self._collect, definition, query, self.tenant_id
            ):
                self._absorb(
                    definition=definition,
                    gap=gap,
                    query=query,
                    subject=subject,
                    capability=capability,
                    parse=parse,
                    interpret=interpret,
                    reports=reports,
                    refusals=refusals,
                    discovered=discovered,
                    stream=stream,
                )
                break
        except Exception as exc:  # noqa: BLE001 - one dead source must not end the sweep
            reports.append(
                SourceReport(
                    source=definition.name,
                    attribute=gap,
                    outcome="error",
                    detail=f"{type(exc).__name__}: {exc}"[:200],
                )
            )
            return "error"

        return reports[-1].outcome if reports else "no_answer"

    def _parsers(self) -> tuple[Callable[..., Any], Callable[..., Any]]:
        if self._parse is not None and self._interpret is not None:
            return self._parse, self._interpret
        from parsers.families import parse_source
        from parsers.to_entities import interpret_parse

        return parse_source, interpret_parse

    def _absorb(
        self,
        *,
        definition: SourceDefinition,
        gap: str,
        query: str,
        subject: EntityProfile,
        capability: Any,
        parse: Callable[..., Any],
        interpret: Callable[..., Any],
        reports: list[SourceReport],
        refusals: list[Refusal],
        discovered: dict[str, Discovered],
        stream: list[dict[str, Any]],
    ) -> None:
        body = capability.body or b""
        outcome = parse(definition, body, status_code=capability.status)
        result = interpret(
            outcome, source_name=definition.name, tenant_id=self.tenant_id, query=query
        )
        reports.append(
            SourceReport(
                source=definition.name,
                attribute=gap,
                outcome=outcome.status,
                status=int(capability.status),
                records=int(outcome.record_count),
                bytes_=len(body),
            )
        )

        refusals.extend(
            Refusal(definition.name, gap, "echo", line) for line in result.rejected_echoes
        )
        refusals.extend(
            Refusal(definition.name, gap, "shape", line) for line in result.rejected_shapes
        )

        observation_id = "OBS-" + _digest(
            self.tenant_id, definition.source_id, query, str(capability.status)
        )[:24]

        for entity in result.entities:
            name = entity.entity_type.value
            subject.attributes[name] = merge_offer(
                subject.attributes.get(name, AttributeState(name)),
                source_id=definition.name,
                values=[entity.canonical],
            )

        for entity in result.about_result:
            discovered.setdefault(
                entity.referent_id,
                Discovered(
                    ref=entity.referent_id,
                    type_label=entity.entity_type.value,
                    canonical=entity.canonical,
                    found_by=(definition.name,),
                    observation_ref=observation_id,
                ),
            )

        for name, value in (result.values or {}).items():
            state_name = f"claim.{name}"
            subject.attributes[state_name] = merge_offer(
                subject.attributes.get(state_name, AttributeState(state_name)),
                source_id=definition.name,
                values=[value],
            )

        now = self._clock()
        event_time = _event_time(result.values or {}, fallback=now)
        stream.append(
            {
                "ts": event_time,
                "entity_id": subject.entity_ref,
                "kind": f"observation:{definition.name}",
                "sequence": len(stream) + 1,
                # The record hash identifies this *event*, not this question. Hashed from
                # source+query alone, every re-sweep of the same subject produced one value
                # forever: the second sweep collided with the first on the unique index and
                # took the transaction down with it, which is how a live database turns a
                # stale hash into a lost sweep. The event time belongs in it -- a genuine
                # replay still hashes equal, and the invariant collapses it on read.
                "record_hash": _digest(
                    self.tenant_id,
                    definition.source_id,
                    query,
                    outcome.status,
                    event_time.isoformat(),
                ),
                "observation_id": observation_id,
                "payload": {
                    "attribute": gap,
                    "source": definition.name,
                    "records": int(outcome.record_count),
                    "recorded_at": now.isoformat(),
                    "event_time": event_time.isoformat(),
                    "neighbors": {ref: 1.0 for ref in discovered},
                },
            }
        )

    # ------------------------------------------------------------------ outputs

    def _invariant(
        self, stream: Sequence[dict[str, Any]], type_label: str
    ) -> tuple[GraphInvariant | None, str]:
        """Fold the observed stream into an invariant, or say why it could not be folded.

        The reason travels with the report instead of being discarded. A sweep that quietly
        produced no life-stream is indistinguishable from a subject that never existed, and
        that ambiguity is the one thing a dossier must not carry.
        """
        if not stream:
            return None, ""
        try:
            return (
                from_entity_stream(
                    list(stream),
                    window=self._window,
                    tenant_id=self.tenant_id,
                    type_label=type_label,
                ),
                "",
            )
        except ValueError as exc:
            return None, f"{type(exc).__name__}: {exc}"

    def _offers(self, query: str, kind: str) -> tuple[CapabilityOffer, ...]:
        """Offers drawn from the catalogue this service was given, for what it can ask with.

        Two questions were being conflated here. A source declares the *shape of input* it
        takes; the subject declares the *kind of thing* it is. A person is not an input shape
        -- no definition has ``applies_to: person``, because a name is not an address -- so
        asking by referent kind returned nothing and a person was silently never enriched.
        Mapping ``person`` onto ``username`` would be inventing a correspondence the catalogue
        never declared.

        So the service asks with the shapes the query itself has. ``example.com`` is a domain
        and gets the 54 domain sources; ``John Smith`` is a name, gets the 32 keyword sources
        and the 23 username sources, and whatever those return is typed by the parsers into
        person-shaped referents. The referent kind stays the caller's assertion and is not
        used to decide who to call.

        Built from ``self._by_id`` rather than the module-level loader: a service that takes a
        catalogue and then schedules from a different one cannot be tested, and the tests would
        be silently exercising the 145 live sources.
        """
        wanted = {shape.lower() for shape in _query_shapes(query, kind)}
        selected: dict[str, CapabilityOffer] = {}
        for definition in self._by_id.values():
            if not definition.enabled:
                continue
            for raw in offers_for(definition):
                offer = CapabilityOffer(**raw)
                if offer.source_id in selected:
                    continue
                declared = {k.lower() for k in offer.entity_kinds}
                # A source declaring no kinds claims to be general; matching it everywhere is
                # what the catalogue module already decided, and inventing an exclusion here
                # would silently drop it instead.
                if not declared or declared & wanted:
                    selected[offer.source_id] = offer
        return tuple(selected.values())

    @staticmethod
    def _available(offer: CapabilityOffer) -> bool:
        """Whether this offer can actually be executed here.

        An offer with a key we were not given and an offer needing a binary that is not
        installed are both ``REFUSED``, never ``EMPTY``: we did not look, so the dossier must
        not claim absence.
        """
        if offer.key_env:
            return _truthy(offer.key_env)
        if offer.binary:
            return offer.binary in os.environ.get("PATH", "").split(os.pathsep)
        if offer.os_requirement and offer.os_requirement.lower().startswith("linux"):
            return os.name == "posix"
        return True


async def _drive(
    collect: Callable[..., Any] | None,
    definition: SourceDefinition,
    query: str,
    tenant_id: str,
) -> AsyncIterator[Any]:
    """Iterate one source's capabilities for a query.

    The connector is reached through two callables -- ``tasks_for`` builds the task, ``collect``
    executes it -- and both are constructor-injectable, because a test that cannot hand over
    fixed bytes is a test that hits the network.
    """
    from sources.connector import tasks_for

    collect = collect or SourceConnector().collect
    stream = collect(tasks_for(definition, query, tenant_id=tenant_id))
    if hasattr(stream, "__aiter__"):
        async for item in stream:
            yield item
        return
    for item in await stream:
        yield item


_EMAIL_AT = "@"


def _query_shapes(value: str, kind: str) -> tuple[str, ...]:
    """The catalogue input shapes this value can honestly be sent as.

    Read off the value itself, because the value is the only thing here that is a fact: a
    string that resolves as an address is one, and a string with spaces is a name whether or
    not the caller told us it was a person's.

    ``keyword`` is the fallback and is deliberately generous -- it is what a free-text search
    endpoint accepts -- so an unrecognised subject still reaches 32 sources instead of none.
    The referent ``kind`` contributes only when the value gave no shape of its own, which
    happens for a synthetic id: a caller passing ``entity_ref`` for something that looks like
    nothing gets asked with that name rather than with silence.
    """
    text = value.strip()
    shapes: list[str] = []
    if _EMAIL_AT in text and "." in text.rsplit(_EMAIL_AT, 1)[-1]:
        shapes.append("email")
    # An address is four dotted numbers, and it is not a domain even though it splits on
    # dots. Sending ``8.8.8.8`` to the 54 domain sources means WHOIS and RDAP calls that can
    # only answer with a refusal, spent from the budget a real domain lookup needed.
    is_ip = False
    if _looks_like_ipv4(text):
        shapes.append("ipv4")
        is_ip = True
    elif _looks_like_ipv6(text):
        shapes.append("ipv6")
        is_ip = True
    if _looks_like_domain(text) and not is_ip:
        shapes.append("domain")
    if " " in text:
        shapes.append("keyword")
    if not shapes:
        shapes.append("keyword")
        if " " not in text and _EMAIL_AT not in text:
            shapes.append("username")
    shapes.append("any")
    if not shapes or set(shapes) == {"any"}:
        shapes.append(kind)
    return tuple(dict.fromkeys(shapes))


def _looks_like_ipv4(value: str) -> bool:
    parts = value.split(".")
    return len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)


def _looks_like_ipv6(value: str) -> bool:
    return value.count(":") >= 2 and all(
        all(c in "0123456789abcdefABCDEF" for c in chunk) for chunk in value.split(":")
    )


def _looks_like_domain(value: str) -> bool:
    if " " in value or _EMAIL_AT in value:
        return False
    labels = value.rstrip(".").split(".")
    return len(labels) >= 2 and all(
        label and not label.startswith("-") and not label.endswith("-") for label in labels
    )


def _referent(kind: str, value: str) -> str:
    return f"REF-{_digest(kind, value.strip().lower())[:16]}"


def _event_time(values: dict[str, str], *, fallback: datetime) -> datetime:
    """Prefer the time the source declared over the time we happened to ask."""
    for field_name in _EVENT_TIME_FIELDS:
        raw = values.get(field_name)
        if not raw:
            continue
        parsed = _parse_ts(str(raw))
        if parsed is not None:
            return parsed
    return fallback


def _parse_ts(raw: str) -> datetime | None:
    text = raw.strip().strip("[]'\"")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y", "%Y%m%d"):
            try:
                parsed = datetime.strptime(text[: len(fmt) + 2], fmt).replace(tzinfo=UTC)
                break
            except ValueError:
                continue
        else:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
