"""The service that turns a subject into a dossier, tested without touching the network.

Every dependency that reaches outward is a constructor parameter -- catalogue, connector,
parser, interpreter, clock, sink -- so these tests state exactly what the platform believes
and lets the assertions be about belief rather than about whatever an API answered today.

The properties worth protecting, in order of how much damage their absence would do:

* the dossier says what was asked. A source that could not be reached appears as an error in
  the report, never as silence;
* refusals stay visible. Echoes and shape mismatches are counted on the report, because a
  refusal that leaves no trace is indistinguishable from a source that was never run;
* an invariant that cannot be folded says why, because "no life-stream" and "the fold is
  broken" look identical from the outside otherwise;
* the whole thing replays. Same bytes, same clock, same dossier -- otherwise a dossier is a
  rumour.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from context_engine.enrichment_service import EnrichmentService
from parsers.families import ParsedRecord, ParseOutcome
from sources.catalogue import SourceDefinition

TENANT = "t-test"
NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


@dataclass
class FakeCapture:
    body: bytes = b"{}"
    status: int = 200


@dataclass
class FakeRefusal:
    """Stands in for a parser that refuses, so refusal plumbing is testable on its own."""

    echoes: tuple[str, ...] = ()
    shapes: tuple[str, ...] = ()


@dataclass
class FakeEntity:
    referent_id: str
    entity_type: Any
    canonical: str


@dataclass
class FakeResult:
    entities: tuple[FakeEntity, ...] = ()
    about_result: tuple[FakeEntity, ...] = ()
    values: dict[str, str] = field(default_factory=dict)
    rejected_echoes: tuple[str, ...] = ()
    rejected_shapes: tuple[str, ...] = ()


class EntityType:
    def __init__(self, value: str) -> None:
        self.value = value


def definition(
    name: str,
    *,
    attributes: tuple[str, ...],
    key_env: str = "",
    binary: str = "",
    enabled: bool = True,
) -> SourceDefinition:
    return SourceDefinition(
        source_id=f"SRC-{name}",
        name=name,
        enabled=enabled,
        category="test",
        description=name,
        parser="raw_text",
        applies_to=("domain",),
        entity_hints=attributes,
        requires_key=bool(key_env),
        key_env=key_env,
        contact=None,
        contact_inferred=False,
        kind="http",
        kind_inferred=False,
        os_requirement="",
        tool="",
        pagination=None,
        parser_is_identity=False,
        source_path=f"catalog/{name}.yml",
    )


def service(
    definitions: list[SourceDefinition],
    bodies: dict[str, tuple[int, bytes]],
    *,
    results: dict[str, FakeResult] | None = None,
    clock: Any = None,
    sink: Any = None,
) -> EnrichmentService:
    """A service wired to fixed bytes: ``bodies`` maps source name to (status, payload)."""

    async def collect(task: Any):
        name = task.source_name
        if name not in bodies:
            raise ConnectionError("host unreachable")
        status, payload = bodies[name]
        yield FakeCapture(body=payload, status=status), {}

    def parse(definition_: Any, body: bytes, *, status_code: int = 200) -> ParseOutcome:
        return ParseOutcome(status="ok", records=(ParsedRecord(values={}, kinds={}),))

    def interpret(_outcome: Any, *, source_name: str, tenant_id: str, query: str) -> FakeResult:
        return (results or {}).get(source_name, FakeResult())

    return EnrichmentService(
        tenant_id=TENANT,
        definitions=definitions,
        collect=collect,
        parse=parse,
        interpret=interpret,
        clock=clock or (lambda: NOW),
        sink=sink,
    )


def enrich(svc: EnrichmentService, query: str = "example.com", **kwargs: Any):
    return asyncio.run(svc.enrich(query, kind="domain", **kwargs))


def test_a_subject_whose_source_answers_gets_a_dossier_with_a_traced_fact() -> None:
    defs = [definition("alpha", attributes=("country",))]
    svc = service(
        defs,
        {"alpha": (200, b"x")},
        results={
            "alpha": FakeResult(
                entities=(FakeEntity("REF-1", EntityType("country"), "US"),),
                values={"timezone": "UTC"},
            )
        },
    )

    report = enrich(svc)

    assert report.invariant is not None, "an answered source must produce a life-stream"
    assert report.dossier is not None
    assert report.dossier.coverage.traced_facts >= 1, "a fact nobody can cite is not a fact"
    assert report.subject.attributes["country"].values == ("US",)
    assert report.subject.attributes["claim.timezone"].values == ("UTC",)


def test_a_source_that_cannot_be_reached_is_reported_not_swallowed() -> None:
    defs = [definition("alpha", attributes=("country",)), definition("beta", attributes=("country",))]
    svc = service(defs, {"beta": (200, b"x")})

    report = enrich(svc)

    outcomes = {r.source: r.outcome for r in report.reports}
    assert "alpha" in reports_names(report), "the unreachable source must still be accounted for"
    assert outcomes["alpha"] == "error"
    assert any("ConnectionError" in r.detail for r in report.reports if r.source == "alpha")
    assert "beta" in reports_names(report), "one dead source must not end the sweep"


def reports_names(report: Any) -> set[str]:
    return {r.source for r in report.reports}


def test_refusals_are_kept_on_the_report() -> None:
    defs = [definition("alpha", attributes=("ip",))]
    svc = service(
        defs,
        {"alpha": (200, b"x")},
        results={"alpha": FakeResult(rejected_echoes=("ip=example.com",), rejected_shapes=("ip=nope",))},
    )

    report = enrich(svc)

    reasons = {r.reason for r in report.refusals}
    assert reasons == {"echo", "shape"}
    assert report.subject.known() == (), "a refused value must not become a known attribute"


def test_a_gated_source_is_refused_never_empty() -> None:
    defs = [definition("keyed", attributes=("abuse_contact",), key_env="SOME_KEY")]

    report = enrich(service(defs, {}))

    assert report.reports == (), "we must not call a source we have no credentials for"
    saturation = report.plan.saturation
    assert saturation.ratio == 0.0
    assert saturation.is_saturated is False, "an unasked question is not a satisfied one"


def test_a_hit_is_discovered_separately_from_the_subject() -> None:
    defs = [definition("alpha", attributes=("organization",))]
    svc = service(
        defs,
        {"alpha": (200, b"x")},
        results={
            "alpha": FakeResult(
                about_result=(FakeEntity("REF-wiki", EntityType("organization"), "Wikipedia"),)
            )
        },
    )

    report = enrich(svc)

    assert report.subject.known() == (), "the hit is not the subject"
    assert [d.canonical for d in report.discovered] == ["Wikipedia"]


def test_a_discovered_entity_is_enriched_on_its_own_terms() -> None:
    defs = [definition("alpha", attributes=("organization",))]
    svc = service(
        defs,
        {"alpha": (200, b"x")},
        results={
            "alpha": FakeResult(
                about_result=(FakeEntity("REF-wiki", EntityType("organization"), "Wikipedia"),)
            )
        },
    )

    report = enrich(svc, depth=1)

    assert [c.subject.entity_ref for c in report.children] == ["REF-wiki"]
    assert report.children[0].subject.entity_ref != report.subject.entity_ref


def test_recursion_is_off_unless_asked_for() -> None:
    defs = [definition("alpha", attributes=("organization",))]
    svc = service(
        defs,
        {"alpha": (200, b"x")},
        results={
            "alpha": FakeResult(
                about_result=(FakeEntity("REF-wiki", EntityType("organization"), "Wikipedia"),)
            )
        },
    )

    report = enrich(svc)

    assert report.children == (), "an unbounded sweep over 145 sources never terminates"


def test_a_broken_fold_says_so_instead_of_returning_nothing() -> None:
    defs = [definition("alpha", attributes=("country",))]
    svc = service(defs, {"alpha": (200, b"x")})

    original = EnrichmentService._invariant

    def broken(self: Any, stream: Any, type_label: str):
        return None, "ValueError: synthetic fold failure"

    EnrichmentService._invariant = broken  # type: ignore[method-assign]
    try:
        report = enrich(svc)
    finally:
        EnrichmentService._invariant = original  # type: ignore[method-assign]

    assert report.invariant is None
    assert "synthetic fold failure" in report.invariant_error


def test_a_declared_event_time_dates_the_event_not_the_observation() -> None:
    defs = [definition("alpha", attributes=("event_date",))]
    registered = datetime(1995, 8, 14, 4, 0, tzinfo=UTC)
    svc = service(defs, {"alpha": (200, b"x")}, results={"alpha": FakeResult(values={"event_date": "1995-08-14T04:00:00Z"})})

    report = enrich(svc)

    event = report.stream[0]
    assert event["ts"] == registered, "a domain registered in 1995 was not registered this afternoon"
    assert event["payload"]["recorded_at"] == NOW.isoformat()


def test_the_same_bytes_and_clock_replay_to_the_same_dossier() -> None:
    defs = [definition("alpha", attributes=("country",))]
    results = {"alpha": FakeResult(entities=(FakeEntity("REF-1", EntityType("country"), "US"),))}

    first = enrich(service(defs, {"alpha": (200, b"x")}, results=results))
    second = enrich(service(defs, {"alpha": (200, b"x")}, results=results))

    assert first.dossier is not None and second.dossier is not None
    assert first.dossier.as_dict() == second.dossier.as_dict()
    assert first.invariant.identity.stream_anchor == second.invariant.identity.stream_anchor


def test_the_sink_sees_every_report() -> None:
    defs = [definition("alpha", attributes=("country",))]
    seen: list[str] = []

    report = enrich(service(defs, {"alpha": (200, b"x")}, sink=lambda r: seen.append(r.subject.entity_ref)))

    assert seen == [report.subject.entity_ref]
