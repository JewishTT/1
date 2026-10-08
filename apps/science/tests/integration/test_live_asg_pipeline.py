"""Acceptance: real bytes from several domains reach the ASG and the derivation ledger.

This is the end-to-end proof the phase plan called for. Everything else can pass while the
slice is broken -- the registry can be right while nothing uses it, the parser families can
be right while nothing persists, the lattice can be right while the ASG is empty.

The path, with no stubbing at any point:

    live HTTP  ->  SourceConnector  ->  parse_source  ->  interpret_parse
              ->  observations / entities / entity_stream
              ->  semantic_nodes  +  derivations

Domains deliberately mixed: an IP-infrastructure feed, certificate transparency, geo, DNS,
and two vulnerability feeds. A pipeline that only works on one domain has not been shown to
be general, which is the entire claim being tested.

Skipped when a source needs a credential or its upstream refuses -- and the skip names the
source. A run that quietly collected nothing would report success.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "acquisition"))

from db.session import make_engine
from domain.ontology import axis_for
from parsers.families import parse_source
from parsers.to_entities import interpret_parse
from sources.catalogue import load_catalogue
from sources.connector import SourceConnector, tasks_for
from sqlalchemy import text

from context.lattice import ScopeLattice

pytestmark = [pytest.mark.integration, pytest.mark.live]

TENANT = "t-asg"
DSN = "postgresql+asyncpg://postgres@127.0.0.1:5432/cognitive"

#: name -> (query, the domain it represents). Three domains, not three feeds of one kind.
SOURCES: dict[str, tuple[str, str]] = {
    "shodan_internetdb": ("1.1.1.1", "ip_infrastructure"),
    "crt_sh_certificates": ("example.com", "certificate_transparency"),
    "ipwho_is": ("1.1.1.1", "geo"),
    "dns_google": ("example.com", "dns"),
    "cisa_kev_recent": ("test", "vulnerability"),
    "nvd_cve": ("test", "vulnerability"),
}

CONNECTOR = SourceConnector()


def _definitions():
    definitions, _ = load_catalogue()
    return {d.name: d for d in definitions}


async def _interpret(name: str, query: str):
    """Fetch, parse and interpret one source. ``None`` when it cannot run."""
    definition = _definitions().get(name)
    if definition is None or definition.requires_key:
        return None, f"{name}: требует ключ или не определён"
    try:
        async for capture, _event in CONNECTOR.collect(tasks_for(definition, query)):
            outcome = parse_source(definition, capture.body or b"", status_code=capture.status)
            if outcome.status != "ok" or not outcome.record_count:
                return None, f"{name}: {outcome.status}"
            return interpret_parse(
                outcome, source_name=name, tenant_id=TENANT
            ), ""
    except Exception as exc:  # noqa: BLE001
        return None, f"{name}: {type(exc).__name__}"
    return None, f"{name}: ни одной страницы"


def _one_loop(coroutine_factory):
    """Run every async step on one loop.

    ``asyncio.run`` per test looked equivalent and was not: SQLAlchemy's async engine
    binds its connection pool to the loop that first used it, so the second ``asyncio.run``
    found a pool bound to a closed loop and raised ``Event loop is closed`` from a
    greenlet spawn. One loop for the module, and the counts are computed there.
    """
    return asyncio.run(coroutine_factory())


def _ingest_and_measure() -> dict:
    """The whole path in one pass: fetch, parse, persist, then read the evidence back."""

    async def main() -> dict:
        try:
            engine = make_engine(DSN)
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"PostgreSQL недоступен: {type(exc).__name__}")

        async with engine.begin() as conn:
            for table in (
                "semantic_edges", "semantic_nodes", "derivation_edges",
                "derivations", "entity_stream", "entities", "observations",
            ):
                await conn.execute(
                    text(f"DELETE FROM {table} WHERE tenant_id = :t"), {"t": TENANT}
                )

        now = datetime.now(UTC)
        collected: dict[str, object] = {}
        for name, (query, domain) in SOURCES.items():
            result, reason = await _interpret(name, query)
            if result is None:
                collected[name] = {"skipped": reason, "domain": domain}
                continue
            if not result.entities:
                # The source answered and the parse found only *values* -- a timestamp, a
                # description. There is nothing to attach an observation to, and writing the
                # row anyway would put an observation in storage that no referent claims,
                # which every coverage count would then read as a placement.
                collected[name] = {
                    "skipped": "no entities", "domain": domain,
                    "values": len(result.values),
                }
                continue
            observation_ref = f"OBS-{name}"
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO observations (observation_id, tenant_id, uri,"
                        " content_hash, content_type, status, duplicate)"
                        " VALUES (:o, :t, :u, :h, 'structured', 'acquired', false)"
                    ),
                    {"o": observation_ref, "t": TENANT, "u": name, "h": "sha-" + name},
                )
                for entity in result.entities:
                    await conn.execute(
                        text(
                            "INSERT INTO entities (entity_id, tenant_id, entity_type,"
                            " canonical_name, current_version)"
                            " VALUES (:e, :t, :ty, :c, 1) ON CONFLICT (entity_id) DO NOTHING"
                        ),
                        {"e": entity.referent_id, "t": TENANT,
                         "ty": entity.entity_type.value, "c": entity.canonical},
                    )
                    await conn.execute(
                        text(
                            "INSERT INTO entity_stream (tenant_id, entity_id, sequence,"
                            " record_hash, kind, ts, payload, observation_id, dataset_id,"
                            " extraction_version)"
                            " VALUES (:t, :e, 1, :h, 'entity', :ts, :p, :o, :d, :v)"
                        ),
                        {"t": TENANT, "e": entity.referent_id,
                         # ``record_hash`` is globally UNIQUE in this table, so it carries
                         # the source as well as the referent. Two sources reporting the same
                         # referent are the same fact about two things, and hashing one of
                         # them away would make the second look like a replay.
                         "h": (name + ":" + entity.referent_id)[:32],
                         "ts": now, "p": json.dumps(entity.as_dict()),
                         "o": observation_ref, "d": name, "v": "parser.fields@v1"},
                    )
                    await conn.execute(
                        text(
                            "INSERT INTO semantic_nodes (node_id, tenant_id, node_kind,"
                            " label, entity_type) VALUES (:e, :t, 'entity', :c, :ty)"
                            " ON CONFLICT (node_id) DO NOTHING"
                        ),
                        {"e": entity.referent_id, "t": TENANT,
                         "c": entity.canonical, "ty": entity.entity_type.value},
                    )
                for derivation in result.derivations._nodes.values():
                    await conn.execute(
                        text(
                            "INSERT INTO derivations (derivation_id, tenant_id, method_id,"
                            " method_version, inputs, output, statement, confidence)"
                            " VALUES (:d, :t, :mi, :mv, :i, :o, :s, :c)"
                            " ON CONFLICT (derivation_id) DO NOTHING"
                        ),
                        {"d": derivation.derivation_id, "t": TENANT,
                         "mi": derivation.method.id, "mv": derivation.method.version,
                         "i": json.dumps(list(derivation.inputs)), "o": derivation.output,
                         "s": derivation.statement, "c": derivation.confidence},
                    )
            collected[name] = {
                "domain": domain,
                "entities": len(result.entities),
                "derivations": len(result.derivations._nodes),
                "unclassified": list(result.unclassified),
            }

        # -- read the evidence back, on this same loop ----------------------
        async with engine.connect() as conn:
            async def scalar(sql: str, **params) -> object:
                return await conn.scalar(text(sql), {"t": TENANT, **params})
            counts = {
                table: await scalar(f"SELECT count(*) FROM {table} WHERE tenant_id = :t")
                for table in ("observations", "entities", "entity_stream",
                              "derivations", "semantic_nodes")
            }
            streamed = await scalar(
                "SELECT count(DISTINCT entity_id) FROM entity_stream"
                " WHERE tenant_id = :t AND observation_id IS NOT NULL"
            )
            empty_observations = await scalar(
                "SELECT count(*) FROM observations o WHERE o.tenant_id = :t"
                " AND NOT EXISTS (SELECT 1 FROM entity_stream es"
                " WHERE es.observation_id = o.observation_id)"
            )
            methods = list(await conn.execute(
                text(
                    "SELECT method_id || '@' || method_version AS m, count(*) AS n"
                    " FROM derivations WHERE tenant_id = :t GROUP BY 1 ORDER BY 1"
                ),
                {"t": TENANT},
            ))
            attributed = (
                await conn.execute(
                    text(
                        "SELECT e.entity_id, d.statement FROM entities e"
                        " JOIN derivations d ON d.output = e.entity_id || '@' || e.entity_type"
                        " WHERE e.tenant_id = :t LIMIT 1"
                    ),
                    {"t": TENANT},
                )
            ).first()
            bad_ids = await scalar(
                "SELECT count(*) FROM derivations"
                " WHERE tenant_id = :t AND length(derivation_id) <> 64"
            )
            types = list(await conn.execute(
                text(
                    "SELECT entity_type, count(*) FROM entities WHERE tenant_id = :t"
                    " GROUP BY 1 ORDER BY 1"
                ),
                {"t": TENANT},
            ))
            stream_rows = [
                dict(r._mapping)
                for r in await conn.execute(
                    text(
                        "SELECT es.observation_id AS observation_ref,"
                        " es.entity_id AS entity_ref, e.entity_type AS entity_type"
                        " FROM entity_stream es JOIN entities e"
                        "  ON e.entity_id = es.entity_id AND e.tenant_id = es.tenant_id"
                        " WHERE es.tenant_id = :t ORDER BY es.observation_id"
                    ),
                    {"t": TENANT},
                )
            ]

        # Replay: the second insert must collide rather than duplicate.
        async with engine.begin() as conn:
            before = await conn.scalar(
                text("SELECT count(*) FROM derivations WHERE tenant_id = :t"), {"t": TENANT}
            )
            await conn.execute(
                text(
                    "INSERT INTO derivations (derivation_id, tenant_id, method_id,"
                    " method_version, inputs, output, statement)"
                    " SELECT derivation_id, tenant_id, method_id, method_version, inputs,"
                    " output, statement FROM derivations WHERE tenant_id = :t"
                    " ON CONFLICT (derivation_id) DO NOTHING"
                ),
                {"t": TENANT},
            )
            after = await conn.scalar(
                text("SELECT count(*) FROM derivations WHERE tenant_id = :t"), {"t": TENANT}
            )

        # The CHECK constraints have to bite, not merely exist.
        async def rejected(sql: str, **params) -> bool:
            try:
                async with engine.begin() as conn:
                    await conn.execute(text(sql), {"t": TENANT, **params})
            except Exception:  # noqa: BLE001
                return True
            return False

        node = None
        async with engine.connect() as conn:
            node = await conn.scalar(
                text("SELECT node_id FROM semantic_nodes WHERE tenant_id = :t LIMIT 1"),
                {"t": TENANT},
            )
        guard = {
            "unknown_type": await rejected(
                "INSERT INTO entities (entity_id, tenant_id, entity_type, current_version)"
                " VALUES ('REF-nonsense', :t, 'nonsense', 1)"
            ),
            "observed_edge_with_derivation": await rejected(
                "INSERT INTO semantic_edges (edge_id, tenant_id, source_node_id,"
                " target_node_id, edge_kind, derivation_id)"
                " VALUES ('EDGE-bad', :t, :n, :n, 'observed_in', 'deadbeef')",
                n=node,
            ),
            "quantified_without_quantifier": await rejected(
                "INSERT INTO semantic_nodes (node_id, tenant_id, node_kind)"
                " VALUES ('Q-bad', :t, 'quantified')"
            ),
            "relation_without_endpoints": await rejected(
                "INSERT INTO semantic_nodes (node_id, tenant_id, node_kind, predicate)"
                " VALUES ('REL-bad', :t, 'relation', 'resolves_to')"
            ),
        }

        by_observation: dict[str, list[dict]] = {}
        for row in stream_rows:
            by_observation.setdefault(row["observation_ref"], []).append(row)
        # A dict comprehension cannot express "group into lists by key", so this stays a
        # loop; the lint rule wants a comprehension and the comprehension would be slower.
        lattice = ScopeLattice.from_observations(
            {"observation_ref": k, "entities": v} for k, v in by_observation.items()
        )
        await engine.dispose()
        return {
            "collected": collected,
            "counts": counts,
            "streamed": streamed,
            "empty_observations": empty_observations,
            "methods": [(r[0], r[1]) for r in methods],
            "attributed": (attributed[0], attributed[1]) if attributed else ("", ""),
            "bad_ids": bad_ids,
            "replay": (before, after),
            "types": {r[0]: r[1] for r in types},
            "lattice": lattice.snapshot(),
            "gradient": lattice.gradient(lattice.top()).as_dict(),
            "guard": guard,
        }

    return _one_loop(main)


@pytest.fixture(scope="module")
def evidence() -> dict:
    return _ingest_and_measure()


class TestRealBytesReachTheStore:
    def test_at_least_three_sources_produced_something(self, evidence: dict) -> None:
        produced = {n: v for n, v in evidence["collected"].items() if "entities" in v}
        summary = {n: v.get("entities", v) for n, v in evidence["collected"].items()}
        print(f"\n  прогнано: {summary}")
        assert len(produced) >= 3, f"только {len(produced)} источников дали сущности"

    def test_several_domains_are_represented(self, evidence: dict) -> None:
        domains = {v["domain"] for v in evidence["collected"].values() if "entities" in v}
        assert len(domains) >= 3, f"только домены: {domains}"

    def test_every_persisted_entity_has_a_stream_row(self, evidence: dict) -> None:
        entities = evidence["counts"]["entities"]
        assert entities > 0
        assert entities == evidence["streamed"], (
            f"{entities} сущностей, но только {evidence['streamed']} имеют stream-строку — "
            f"это сущности без членства, и решётка их не увидит"
        )

    def test_every_observation_that_exists_has_entities(self, evidence: dict) -> None:
        assert evidence["empty_observations"] == 0, (
            f"{evidence['empty_observations']} наблюдений записано, но без сущностей"
        )

    def test_a_value_only_source_is_reported_not_written(self, evidence: dict) -> None:
        # A parse that found only values has nothing to attach an observation to. Writing
        # the row anyway would make every coverage count read it as a placement.
        for name, entry in evidence["collected"].items():
            assert "entities" in entry or "skipped" in entry, f"{name} молча исчез"


class TestTheLedgerIsQueryable:
    def test_derivations_are_readable_with_their_method(self, evidence: dict) -> None:
        rows = evidence["methods"]
        print(f"\n  методы в ledger: {rows}")
        assert rows, "деривации не записались"
        assert all("@" in name for name, _ in rows), "метод без версии"

    def test_a_type_is_attributable_after_a_reload(self, evidence: dict) -> None:
        entity_id, statement = evidence["attributed"]
        assert entity_id, "ни одна сущность не имеет деривации своего типа"
        assert entity_id in statement, (
            f"деривация {statement!r} не называет сущность {entity_id} — "
            f"ответ «почему такой тип» не читается"
        )

    def test_a_derivation_id_is_the_content_digest(self, evidence: dict) -> None:
        assert evidence["bad_ids"] == 0, "идентификатор деривации не является digest"

    def test_replaying_a_write_is_a_no_op(self, evidence: dict) -> None:
        before, after = evidence["replay"]
        assert before == after, f"{before} -> {after}: повтор создал новые строки"


class TestTheLatticeSeesIt:
    def test_the_lattice_closes_over_what_was_persisted(self, evidence: dict) -> None:
        print(f"\n  решётка: {evidence['lattice']}")
        print(f"  градиент: {evidence['gradient']}")
        assert evidence["lattice"]["entities"] > 0
        assert evidence["lattice"]["unplaced"] == 0
        assert not evidence["gradient"]["saturated"], (
            "насыщение при нулевом градиенте означает, что сущности не переиспользуются"
        )

    def test_the_types_that_reached_storage_are_named(self, evidence: dict) -> None:
        found = sorted(evidence["types"])
        print(f"\n  типы в хранилище: {found}")
        assert found
        for name in found:
            assert axis_for(name) == "entity", (
                f"{name!r} попал в entity_type, но axis_for говорит иначе"
            )

    def test_the_mix_of_types_is_real(self, evidence: dict) -> None:
        counts = evidence["types"]
        print(f"\n  распределение типов: {counts}")
        assert len(counts) >= 3, (
            f"все сущности одного типа ({counts}) — вёртикальный срез не обобщает"
        )


class TestDatabaseInvariantsHold:
    @pytest.mark.parametrize(
        "invariant",
        [
            "unknown_type",
            "observed_edge_with_derivation",
            "quantified_without_quantifier",
            "relation_without_endpoints",
        ],
    )
    def test_the_constraint_bites(self, evidence: dict, invariant: str) -> None:
        assert evidence["guard"][invariant], f"CHECK не отверг: {invariant}"
