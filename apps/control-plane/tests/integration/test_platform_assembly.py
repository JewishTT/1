"""Contract: the assembled platform -- ``composition.py`` and the cycle it drives.

These pin the four properties that make the platform an engine rather than a pile of
correct components:

**Assembly is total and never fatal.** Every component is attempted independently. A
deployment without PostgreSQL, or without Temporal, or without the acquisition wheel boots
with what it has and names what it does not. A composition root that raises turns one
missing subsystem into a total outage, at startup, where the failure names a startup error
rather than the component that was absent.

**The durable authority is not optional.** ``ready`` is false without it. A platform holding
its context in memory while reporting itself healthy is the exact failure the persistence
layer exists to prevent.

**A tick moves the context in at least one direction.** ``moved`` distinguishes a pass that
learned something from a pass that merely completed. Without it a no-op tick and a
productive one are indistinguishable in a log, which is how an investigation appears to be
running while making no progress.

**The cycle classifies its obligations.** An undetermined scope is answered by resolving a
subject locally; a saturation shortfall is answered by searching. Sending both through
acquisition would spend source budget to learn what the entity stream already holds.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.integration


class _StubObligation:
    """The fields ``compile_obligations`` reads, and nothing else."""

    def __init__(self, question: str, rationale: str = "", rule: str = "", criteria=()):
        self.question = question
        self.rationale = rationale
        self.created_by = f"context-engine/rules/v1#{rule}" if rule else ""
        self.satisfaction_criteria = tuple(criteria)
        self.target_knowledge_type = "entity"
        self.obligation_id = "OBL-1"
        self.status = type("S", (), {"value": "open"})()


class _StubContext:
    context_id = "CXI-stub"
    investigation_id = "INV-stub"
    tenant_id = "stub-tenant"
    question = "who controls CLUSTER-1?"
    scope_refs = ("CLUSTER-1",)


def _service() -> object:
    from services.cycle_service import CycleService

    return CycleService(
        store=None, fabric_store=None, loop=None, cycle=None, ledger=None
    )


class TestObligationClassification:
    def test_an_undetermined_scope_is_a_local_subject_not_a_search(self) -> None:
        asts, refs, unresolved = _service().compile_obligations(
            [
                _StubObligation(
                    "place observation OBS-7: no defensible scope",
                    "no determination was made for this observation's scope",
                    rule="coverage_gap",
                )
            ]
        )
        assert asts == ()
        assert refs == ("OBS-7",)
        assert unresolved == ()

    def test_a_saturation_shortfall_is_a_source_expansion_query(self) -> None:
        asts, refs, _ = _service().compile_obligations(
            [
                _StubObligation(
                    "close saturation gap: insufficient_independence",
                    "saturation is unsaturated; n_eff=0.0",
                    rule="saturation_shortfall",
                )
            ]
        )
        assert len(asts) == 1
        assert asts[0].concept == "source_expansion"
        assert refs == ()

    def test_an_expansion_query_carries_no_invented_filter(self) -> None:
        asts, _, _ = _service().compile_obligations(
            [_StubObligation("widen", rule="saturation_shortfall")]
        )
        # No field was named by the obligation. A filter here would be a constraint nobody
        # asked for, and it would silently narrow the search.
        assert asts[0].filters == ()

    def test_an_unrecognised_obligation_is_reported_not_guessed(self) -> None:
        asts, refs, unresolved = _service().compile_obligations(
            [_StubObligation("something nobody can classify", rule="mystery_rule")]
        )
        assert asts == ()
        assert refs == ()
        assert unresolved == ("something nobody can classify",)

    def test_words_that_look_like_refs_are_not_treated_as_refs(self) -> None:
        asts, refs, _ = _service().compile_obligations(
            [
                _StubObligation(
                    "check", rationale="rule=saturation.reason@1.0 RULE Saturation",
                    rule="saturation_shortfall",
                )
            ]
        )
        assert refs == ()
        assert len(asts) == 1

    def test_duplicate_expansion_obligations_compile_to_one_query(self) -> None:
        asts, _, _ = _service().compile_obligations(
            [
                _StubObligation("widen", rule="saturation_shortfall"),
                _StubObligation("widen more", rule="saturation_shortfall"),
            ]
        )
        assert len({ast.ast_id for ast in asts}) == 1


class TestSubjectRefs:
    def test_platform_ref_prefixes_are_found(self) -> None:
        from services.cycle_service import _subject_refs

        found = _subject_refs("place observation OBS-2 and entity ENT-7", ())
        assert "OBS-2" in found
        assert "ENT-7" in found

    def test_a_ref_is_taken_from_satisfaction_criteria(self) -> None:
        from services.cycle_service import _subject_refs

        assert _subject_refs("resolve it", ("OBS-9",)) == ("OBS-9",)

    def test_an_unknown_prefix_is_not_a_ref(self) -> None:
        from services.cycle_service import _subject_refs

        assert _subject_refs("nothing here Xyz-1", ()) == ()


class TestRuleExtraction:
    def test_the_rule_is_read_from_created_by(self) -> None:
        from services.cycle_service import _rule_of

        assert _rule_of("context-engine/rules/v1#coverage_gap") == "coverage_gap"

    def test_a_bare_rule_name_still_works(self) -> None:
        from services.cycle_service import _rule_of

        assert _rule_of("coverage_gap") == "coverage_gap"

    def test_an_absent_rule_is_empty(self) -> None:
        from services.cycle_service import _rule_of

        assert _rule_of("") == ""


class TestHealth:
    def test_a_platform_without_the_authority_is_not_ready(self) -> None:
        from composition import Health

        health = Health(durable="absent")
        assert health.ready is False
        assert health.cycles is False

    def test_the_authority_alone_is_not_a_cycle(self) -> None:
        from composition import Health

        health = Health(durable="ready", fabric="absent")
        assert health.ready is True
        assert health.cycles is False

    def test_a_full_platform_can_cycle(self) -> None:
        from composition import Health

        health = Health(durable="ready", fabric="ready", catalogue="ready")
        assert health.cycles is True

    def test_health_is_reportable(self) -> None:
        from composition import Health

        payload = Health(durable="ready", notes=["temporal unavailable"]).as_dict()
        assert payload["ready"] is True
        assert payload["notes"] == ["temporal unavailable"]


class TestReportShape:
    def test_a_report_says_which_phases_ran(self) -> None:
        from services.cycle_service import PhaseResult, TickReport

        report = TickReport(
            context_id="CXI-1",
            phases=[
                PhaseResult("read_obligations", True, "2 open", 2),
                PhaseResult("tick_context", False, "boom"),
            ],
        )
        assert report.ok is False
        payload = report.as_dict()
        assert [p["name"] for p in payload["phases"]] == ["read_obligations", "tick_context"]
        assert payload["phases"][1]["ok"] is False

    def test_a_report_that_moved_nothing_says_so(self) -> None:
        from services.cycle_service import TickReport

        assert TickReport(context_id="CXI-1").moved is False
        assert TickReport(context_id="CXI-1", cell_ids=("CXC-1",)).moved is True
        assert TickReport(context_id="CXI-1", requests=("x",)).moved is True


class TestDeduplication:
    def test_query_ast_is_not_hashable_so_plans_dedupe_by_identity(self) -> None:
        """``QueryAST`` carries a mapping, so hashing it raises. The tick must not."""
        from context.query_ast import QueryAST, QueryVerb

        ast = QueryAST(verb=QueryVerb.FIND, concept="x")
        with pytest.raises(TypeError):
            hash(ast)
        # The identity used for dedup is the digest, which is stable.
        assert ast.ast_id == QueryAST(verb=QueryVerb.FIND, concept="x").ast_id


class TestFrontierDraining:
    def test_no_frontier_is_not_a_failure(self) -> None:
        service = _service()
        assert service.drain_frontier(tenant_id="t", investigation_id="INV") == []

    def test_a_factory_that_raises_yields_nothing(self) -> None:
        def _boom():
            raise RuntimeError("no frontier")

        service = _service()
        service._frontier_factory = _boom
        assert service.drain_frontier(tenant_id="t", investigation_id="INV") == []

    def test_an_empty_frontier_yields_nothing(self) -> None:
        class _Empty:
            def pop_next(self, *, tenant_id, now=None):
                return None

        service = _service()
        service._frontier_factory = lambda: _Empty()
        assert service.drain_frontier(tenant_id="t", investigation_id="INV") == []


class TestUnreadableObligations:
    @pytest.mark.asyncio
    async def test_a_store_that_cannot_answer_yields_no_obligations(self) -> None:
        class _Broken:
            async def obligations(self, context_id):
                raise RuntimeError("database is down")

        service = _service()
        service._store = _Broken()
        assert await service._open_obligations(_StubContext()) == ()


class TestScopeLatticePhase:
    """The tick ends by closing the lattice over what was actually read.

    Without this the only view of context is a list of cells, and the growth question has no
    answer: nothing says which entities are jointly in scope, or which single entity would
    add an observation nobody has.
    """

    class _Stream:
        def __init__(self, rows: list[dict] | None = None, *, raises: bool = False) -> None:
            self._rows = rows or []
            self._raises = raises

        async def observation_entity_rows(self, tenant_id: str, **_kw):
            self.asked_for = tenant_id
            if self._raises:
                raise RuntimeError("entity stream unavailable")
            return self._rows

    def _rows(self) -> list[dict]:
        return [
            {"observation_ref": "OBS-1", "entity_ref": "REF-a", "entity_type": "domain"},
            {"observation_ref": "OBS-1", "entity_ref": "REF-b", "entity_type": "person"},
            {"observation_ref": "OBS-2", "entity_ref": "REF-b", "entity_type": "person"},
            {"observation_ref": "OBS-2", "entity_ref": "REF-c", "entity_type": "organization"},
        ]

    @pytest.mark.asyncio
    async def test_a_tick_reports_the_closed_scope(self) -> None:
        from services.cycle_service import TickReport

        service = _service()
        service._store = self._Stream(self._rows())
        report = TickReport(context_id="CXI-stub")
        await service._read_lattice(_StubContext(), report, tenant_id="stub-tenant")
        assert report.lattice["entities"] == 3
        assert report.lattice["observations"] == 2
        assert report.lattice["types"] == ["domain", "organization", "person"]

    @pytest.mark.asyncio
    async def test_the_phase_appears_by_name_in_the_report(self) -> None:
        from services.cycle_service import TickReport

        service = _service()
        service._store = self._Stream(self._rows())
        report = TickReport(context_id="CXI-stub")
        await service._read_lattice(_StubContext(), report, tenant_id="stub-tenant")
        assert "scope_lattice" in {phase.name for phase in report.phases}

    @pytest.mark.asyncio
    async def test_the_stream_is_read_for_the_context_tenant(self) -> None:
        # The stream is tenant-wide. Reading another tenant's entities would answer a
        # question this context never asked.
        from services.cycle_service import TickReport

        stream = self._Stream(self._rows())
        service = _service()
        service._store = stream
        report = TickReport(context_id="CXI-stub")
        await service._read_lattice(_StubContext(), report, tenant_id="stub-tenant")
        assert stream.asked_for == "stub-tenant"

    @pytest.mark.asyncio
    async def test_unreadable_observations_stay_visible(self) -> None:
        from services.cycle_service import TickReport

        service = _service()
        service._store = self._Stream(
            [{"observation_ref": "OBS-9", "entity_ref": "REF-z", "entity_type": "domain"}]
        )
        report = TickReport(context_id="CXI-stub")
        await service._read_lattice(_StubContext(), report, tenant_id="stub-tenant")
        assert report.gradient["unplaced_observations"] == 0

    @pytest.mark.asyncio
    async def test_an_unreadable_stream_is_a_failed_phase_not_a_crash(self) -> None:
        from services.cycle_service import TickReport

        service = _service()
        service._store = self._Stream(raises=True)
        report = TickReport(context_id="CXI-stub")
        await service._read_lattice(_StubContext(), report, tenant_id="stub-tenant")
        assert any(p.name == "scope_lattice" and not p.ok for p in report.phases)
        # Distinct from an empty lattice: nothing was read, which is not "nothing in scope".
        assert report.lattice is None

    @pytest.mark.asyncio
    async def test_an_empty_stream_is_not_a_failure(self) -> None:
        from services.cycle_service import TickReport

        service = _service()
        service._store = self._Stream([])
        report = TickReport(context_id="CXI-stub")
        await service._read_lattice(_StubContext(), report, tenant_id="stub-tenant")
        assert report.lattice["entities"] == 0
        assert report.lattice["unplaced"] == 0
        assert all(p.ok for p in report.phases if p.name == "scope_lattice")

    @pytest.mark.asyncio
    async def test_a_conflicting_type_is_reported_in_the_lattice(self) -> None:
        from services.cycle_service import TickReport

        service = _service()
        service._store = self._Stream([
            {"observation_ref": "OBS-1", "entity_ref": "REF-x", "entity_type": "person"},
            {"observation_ref": "OBS-2", "entity_ref": "REF-x", "entity_type": "organization"},
        ])
        report = TickReport(context_id="CXI-stub")
        await service._read_lattice(_StubContext(), report, tenant_id="stub-tenant")
        assert "unknown" in report.lattice["types"]
        assert set(report.lattice["conflicts"]["REF-x"]) == {"organization", "person"}

    @pytest.mark.asyncio
    async def test_the_report_serializes_the_lattice_and_gradient(self) -> None:
        from services.cycle_service import TickReport

        service = _service()
        service._store = self._Stream(self._rows())
        report = TickReport(context_id="CXI-stub")
        await service._read_lattice(_StubContext(), report, tenant_id="stub-tenant")
        payload = report.as_dict()
        assert payload["lattice"]["entities"] == 3
        assert payload["gradient"]["saturated"] is False
