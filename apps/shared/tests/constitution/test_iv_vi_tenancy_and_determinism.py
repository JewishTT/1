"""Constitution IV and VI: tenants are fail-closed, and two processes must agree.

**IV — every durable fact is tenant-scoped, and an empty tenant is not a tenant.**
NOT NULL is not enough, because ``''`` is a string and a database will store it happily.
The tests below check both halves on the four types 019 made durable plus the cross-tenant
refusals on the paths that consume them.

The reason this is worth a constitutional test rather than a per-feature one: the failure
mode is *silent and shared*. A row that escaped its tenant is not wrong in one place; it is
wrong in every query that reads it, and it looks right to each of them. And a cross-tenant
admission that succeeds is worse than one that fails loudly, because it produces a claim that
cites a candidate from an investigation the reader is not allowed to see.

**VI — determinism: the same inputs give the same addresses, in any process, in any order.**
The check is not "the hash is stable" — it is that *assembly* is order-independent, because
assembly iterates collections and the collections come from producers that finish in
whatever order they finish. A platform where two processes reading the same document derive
different ids cannot be replayed, cannot be compared across a migration, and cannot be
diffed — and the failure appears as a growing pile of "identical" records that are not
identical.

The cross-process half is checked the only way available without two interpreters: by
deriving in one process, and by asserting the inputs are fully content-addressed so a second
process has nothing left to disagree about.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

import pytest
from extractors.signals import (
    Neighbourhood,
    RelationSignal,
    SignalContractError,
    SignalKind,
)

from domain.capture import Capture, CaptureTimeBasis
from domain.relation_candidate import RelationCandidate, TemporalHypothesis
from domain.relation_claim_material import (
    EvidenceGrade,
    build,
)
from domain.relation_participant import binary_participants
from domain.temporal_observation import (
    SourceTemporalObservation,
    TemporalAxis,
    TemporalPrecision,
)
from semantic.contracts import RelationRef

UTC = UTC


def _candidate(**over) -> RelationCandidate:
    base = {
        "subject_mention_ref": "MN-A",
        "object_mention_ref": "MN-B",
        "relation_ref": RelationRef("works_for"),
        "relation_surface": "CEO of",
        "context_ref": "CX-1",
        "semantic_regime_ref": "RG-1",
        "tenant_id": "T1",
        "temporal_hypothesis": TemporalHypothesis.absent(),
    }
    return RelationCandidate(**{**base, **over}).with_id()


def _signal(**over) -> RelationSignal:
    base = {
        # The native participant tuple, as of Phase 4B. Two ends here because this suite's
        # subject is tenancy and determinism, not arity; the tuple is the only construction
        # path a `RelationSignal` has.
        "participants": binary_participants("MN-A", "MN-B"),
        "kind": SignalKind.LEXICAL,
        "relation_surface": "CEO of",
        "neighbourhood": Neighbourhood(
            characters_scanned=40, pairs_considered=0, scope_read="one sentence"
        ),
        "context_ref": "CX-1",
        "semantic_regime_ref": "RG-1",
        "tenant_id": "T1",
    }
    return RelationSignal(**{**base, **over})


class TestTenantsAreFailClosed:
    @pytest.mark.parametrize(
        "factory",
        [
            pytest.param(partial(_candidate, tenant_id=""), id="candidate"),
            pytest.param(partial(_signal, tenant_id=""), id="signal"),
            pytest.param(
                lambda: SourceTemporalObservation(
                    temporal_axis=TemporalAxis.PUBLISHED_AT,
                    capture_ref="CAP-1",
                    stated_value=datetime(2024, 3, 15, tzinfo=UTC),
                    precision=TemporalPrecision.DAY,
                    basis=CaptureTimeBasis.PUBLICATION,
                    evidence_location="date filed",
                    tenant_id="",
                ),
                id="temporal-observation",
            ),
            pytest.param(
                lambda: Capture(
                    tenant_id="", source_id="src-1", target_uri="https://example.com/a",
                    content_digest="d" * 64, fetched_at=datetime(2024, 1, 1, tzinfo=UTC),
                    time_basis=CaptureTimeBasis.FETCH,
                ),
                id="capture",
            ),
        ],
    )
    def test_an_empty_tenant_is_refused(self, factory) -> None:
        """``''`` is a string and a database will store it. This is where it stops."""
        with pytest.raises(Exception) as excinfo:
            factory()
        assert "tenant" in str(excinfo.value).lower(), (
            f"refused, but not for a tenancy reason: {excinfo.value}"
        )

    def test_a_candidate_built_for_another_tenant_cannot_become_material(self) -> None:
        """The cross-tenant refusal, on the path that actually commits something.

        The refusal arrives as :class:`domain.relation_candidate.CandidateContractError`
        rather than :class:`domain.relation_claim_material.MaterialContractError`, and that
        is the better of the two: the *candidate* knows it belongs to another tenant, so the
        check belongs to the layer that read the field. The material module is not obliged to
        re-check what its own input already refused, and this test asserts the refusal rather
        than a particular type carrying it.
        """
        foreign = _candidate(tenant_id="T2")
        with pytest.raises(Exception) as excinfo:
            build(
                foreign,
                subject_ref="EN-A",
                object_ref="EN-B",
                revision_number=1,
                evidence_grade=EvidenceGrade.WEAK,
                tenant_id="T1",
            )
        assert "tenant" in str(excinfo.value).lower()
        assert "T2" in str(excinfo.value) and "T1" in str(excinfo.value)

    def test_the_tenant_is_part_of_the_address(self) -> None:
        """So a record cannot be moved between tenants by rewriting one column.

        Without the tenant in the material, ``tenant_id`` would be mutable projection data
        and re-homing a record would be a single UPDATE — which is exactly the move a
        cross-tenant read would then be unable to detect.
        """
        assert _candidate(tenant_id="T1").candidate_id != _candidate(tenant_id="T2").candidate_id
        assert _signal(tenant_id="T1").signal_id != _signal(tenant_id="T2").signal_id

    def test_a_signal_with_the_wrong_tenant_is_refused_not_silently_stamped(self) -> None:
        """``run_producer`` overwrites the registry's fields, including the tenant.

        Overwriting a *mismatch* would be a silent repair, so the registry refuses first.
        The distinction matters: overwriting is right for ``producer_ref`` (the registry is
        the authority on who spoke) and wrong for the tenant (a cross-tenant signal means a
        producer was run for the wrong tenant, which is a bug to surface).
        """
        from extractors.signals.protocol import ProducerDeclaration, run_producer

        class _P:
            def declares(self):
                return ProducerDeclaration(
                    producer_ref="p/1", producer_version="1", kinds=(SignalKind.LEXICAL,),
                    reads="a sentence", cannot_read="anything ambiguous", max_pairs_considered=8,
                )

            def extract(self, record, *, scope):
                return (_signal(tenant_id="T2"),)

        from extractors.signals.protocol import ExtractionScope

        with pytest.raises(SignalContractError) as excinfo:
            run_producer(
                _P(), [{"x": 1}],
                scope=ExtractionScope(
                    tenant_id="T1", context_ref="CX-1", semantic_regime_ref="RG-1"
                ),
            )
        assert excinfo.value.code == "signal_tenant_mismatch"


class TestDeterminism:
    def test_the_same_input_gives_the_same_address_in_this_process(self) -> None:
        assert _candidate().candidate_id == _candidate().candidate_id
        assert _signal().signal_id == _signal().signal_id

    def test_a_second_interpreter_derives_the_same_addresses(self) -> None:
        """The cross-process half, checked the only way available here.

        A separate interpreter is the closest thing to a second process this suite can
        reach, and it is a real check rather than a mock: a different interpreter has a
        different hash seed, a different dict ordering behaviour and no shared state, so an
        address that survives it was derived from the contents.
        """
        script = (
            "from domain.relation_candidate import RelationCandidate, TemporalHypothesis\n"
            "from semantic.contracts import RelationRef\n"
            "c = RelationCandidate(\n"
            "    subject_mention_ref='MN-A', object_mention_ref='MN-B',\n"
            "    relation_ref=RelationRef('works_for'), relation_surface='CEO of',\n"
            "    context_ref='CX-1', semantic_regime_ref='RG-1', tenant_id='T1',\n"
            "    temporal_hypothesis=TemporalHypothesis.absent()).with_id()\n"
            "print(c.candidate_id)\n"
        )
        shared = Path(__file__).resolve().parents[3]
        completed = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            cwd=str(shared),
            env={"PYTHONPATH": str(shared), "PATH": "/usr/bin:/bin"},
        )
        assert completed.returncode == 0, completed.stderr
        assert completed.stdout.strip() == _candidate().candidate_id, (
            "a second interpreter derived a different address: "
            f"{completed.stdout.strip()} vs {_candidate().candidate_id}"
        )

    def test_addresses_carry_no_clock_and_no_randomness(self) -> None:
        """Two candidates differing only in a timestamp get different addresses.

        This is the flip side of determinism and the reason it is not free: an address that
        ignored ``observed_at`` would be *stable* and *wrong* - two readings taken at
        different moments would collapse into one, and the record of when something was seen
        would be lost. Determinism means no hidden input, not no input.
        """
        first = _candidate().with_id()
        assert first.candidate_id == _candidate().candidate_id
        with_evidence = RelationCandidate(
            **{
                field_name: getattr(first, field_name)
                for field_name in (
                    "subject_mention_ref", "object_mention_ref", "relation_ref",
                    "relation_surface", "context_ref", "semantic_regime_ref", "tenant_id",
                    "temporal_hypothesis",
                )
            },
            observed_at=datetime(2024, 1, 1, tzinfo=UTC),
        ).with_id()
        assert with_evidence.candidate_id != first.candidate_id

    def test_two_producers_reading_the_same_thing_are_two_signals(self) -> None:
        """``producer_ref`` is *in* the address, and ``producer_confidence`` is not.

        The pair is the whole of FR-034 at this layer, and getting either half wrong is
        fatal in opposite directions. Leave the producer out of the address and two readers
        of one page collapse into one observation, so the platform reports corroboration it
        does not have. Put the *confidence* in and one producer's growing certainty mints
        fresh addresses, so its own uncertainty manufactures corroboration of itself.

        This test exists because the mutation harness found it unguarded: removing
        ``producer_ref`` from the address left the whole constitutional suite green, which
        meant the property was real, load-bearing, and untested.
        """
        base = {
            # The canonical participant tuple, as of Phase 4B. The local literal rather than
            # the module's `_signal` default, so the test keeps asserting about exactly the
            # two ends it names.
            "participants": binary_participants("MN-A", "MN-B"),
            "kind": SignalKind.LEXICAL,
            "relation_surface": "CEO of",
            "neighbourhood": Neighbourhood(
                characters_scanned=40, pairs_considered=0, scope_read="one sentence"
            ),
            "context_ref": "CX-1",
            "semantic_regime_ref": "RG-1",
            "tenant_id": "T1",
        }
        first = _signal(producer_ref="lexical/1", **base)
        second = _signal(producer_ref="structural/table", **base)
        assert first.signal_id != second.signal_id, (
            "two producers reading the same structure must be two observations, or FR-034's "
            "independence count is counting readers rather than sources"
        )
        # And confidence, symmetrically, must NOT mint a new address.
        surer = _signal(producer_ref="lexical/1", producer_confidence=0.99, **base)
        assert surer.signal_id == first.signal_id, (
            "a producer being more sure of the same reading is not a second observation"
        )

    def test_assembly_is_order_independent(self) -> None:
        """Producers finish in whatever order they finish; the address must not notice."""
        from semantic_path.assembly import assemble

        kw = dict(tenant_id="T1", context_ref="CX-1", semantic_regime_ref="RG-1")
        forwards = [
            _signal(relation_surface="CEO of", relation_ref=RelationRef("works_for")),
            _signal(
                relation_surface="founded", relation_ref=RelationRef("founded"),
                producer_ref="p/2", kind=SignalKind.TABLE,
            ),
        ]
        a = assemble(forwards, **kw)
        b = assemble(list(reversed(forwards)), **kw)
        assert [c.candidate_id for c in a.candidates] == [c.candidate_id for c in b.candidates]
        assert [c.logical_candidate_id for c in a.candidates] == [
            c.logical_candidate_id for c in b.candidates
        ]
