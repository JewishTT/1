"""Contract: the dossier is the honest end of the pipeline (spec 026).

Upstream layers emit fragments. This test file pins the properties of the one artefact
that has to carry all of them to an analyst without lying in the joining.

**Gaps are visible.** ``build_dossier`` copies the ``EnrichmentPlan``'s gaps instead of
recomputing them, so the screen can never disagree with the work queue about what is
missing, and a dossier assembled without a plan reports ``plan_known=False`` instead of a
comfortable zero.

**Conflicts are not resolved silently.** A contradiction enters as a ``Conflict`` carrying
both sides and the union of disagreeing sources. Choosing a winner here would make the
answer depend on ingestion order, which is the whole failure mode the five-state coverage
vocabulary exists to prevent.

**Every fact has a source.** Lifecycle windows, edges and contacts cite refs; anything
unsourced is dropped *and counted* in ``coverage.untraced``. The count is the point: an
item silently removed is indistinguishable from an item never seen.

**Emptiness is a claim, not a blank.** A dossier with nothing in it is empty, untraceable
only in the honest sense, and explicitly incomplete.

**Order carries no information.** Timeline, edges, contacts, gaps and conflicts all sort
from content, so shuffled input yields a byte-identical ``as_dict`` and digest.

**The timeline is the invariant's own windows.** ``window_start``/``window_end``/``state``/
``event_count`` come from real ``TemporalSlice`` fields, dormancy included and labelled.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from domain.graph_invariant import (
    EvidenceBlock,
    GraphInvariant,
    InvariantIdentity,
    LifecycleState,
    ProvenanceBlock,
    TemporalLifecycle,
    TemporalSlice,
    TopologicalState,
    WindowTopology,
    from_entity_stream,
)

from context.dossier import (
    ADJACENT_RELATION,
    CO_MENTION_RELATION,
    CONTACT_PREFIX,
    Conflict,
    ConflictSide,
    Contact,
    ContactSet,
    CoverageView,
    Dossier,
    DossierIdentity,
    Gap,
    Link,
    LinkMap,
    LinkOrigin,
    TimelineEntry,
    build_dossier,
)
from context.enrichment import (
    AttributeState,
    CapabilityOffer,
    Coverage,
    EntityProfile,
    merge_offer,
    plan_enrichment,
)

pytestmark = pytest.mark.contract

T0 = datetime(2026, 3, 1, tzinfo=UTC)
DAY = timedelta(days=1)


def profile(**attributes: AttributeState) -> EntityProfile:
    return EntityProfile(entity_ref="ent-1", type_label="record", attributes=dict(attributes))


def window(start: datetime, state: str, count: int) -> TemporalSlice:
    return TemporalSlice(
        window_start=start,
        window_end=start + DAY,
        state=LifecycleState(state),
        event_count=count,
        events_per_period=count,
        burstiness=None,
        first_seen=start if count else None,
        last_seen=start if count else None,
    )


def invariant(
    slices: tuple[TemporalSlice, ...],
    *,
    topology: tuple[WindowTopology, ...] = (),
    traced: bool = True,
    entity_id: str = "ent-1",
) -> GraphInvariant:
    """A minimal but *real* invariant: real identity, lifecycle, topology, evidence.

    ``traced=False`` models a projection whose *provenance block* was never written (no chain
    tip, no observation anchors). The stream anchor survives because ``InvariantIdentity``
    refuses to exist without one — which is exactly why lifecycle facts can never be
    untraceable in practice, and why the drop rule below is a backstop rather than a
    routine path.
    """
    return GraphInvariant(
        identity=InvariantIdentity(
            entity_id=entity_id, stream_anchor="evt-genesis0001", type_label="record"
        ),
        lifecycle=TemporalLifecycle(slices=slices),
        topology=TopologicalState(
            degree=len({nid for row in topology for nid, _ in row.neighbor_weights}),
            community="",
            neighbor_signature=tuple(
                sorted({nid for row in topology for nid, _ in row.neighbor_weights})
            ),
            window_topology=topology,
        ),
        evidence=EvidenceBlock(
            observation_count=1 if traced else 0,
            observation_anchors=("obs-1",) if traced else (),
        ),
        provenance=ProvenanceBlock(
            tenant_id="t-1",
            event_id="evt-chain-tip-0001" if traced else "",
            stream_head="chain-tip-0001" if traced else "",
        ),
    )


def conflicting(state: AttributeState, *pairs: tuple[str, str]) -> AttributeState:
    """Fold source/value pairs through the real merger to obtain a CONFLICT state."""
    folded = state
    for source, value in pairs:
        folded = merge_offer(folded, source_id=source, values=[value])
    return folded


PLANNABLE = (
    CapabilityOffer(source_id="feed_a", entity_kinds=(), attributes=("alias",)),
    CapabilityOffer(
        source_id="feed_b", entity_kinds=(), attributes=("alias",), key_env="FEED_B_KEY"
    ),
)


def plan_for(subject: EntityProfile, **available: bool):
    return plan_enrichment(subject, PLANNABLE, available=available)


def offering(*attributes: str, key_env: str = "", source_id: str = "feed_a"):
    return CapabilityOffer(
        source_id=source_id, entity_kinds=(), attributes=attributes, key_env=key_env
    )


# --------------------------------------------------------------------------
# 1. A complete dossier, every section populated
# --------------------------------------------------------------------------


def test_complete_dossier_has_every_section() -> None:
    subject = profile(
        **{
            "alias": AttributeState(
                name="alias", values=("operation-north",), coverage=Coverage.ACQUIRED,
                sources=("feed_a",),
            ),
            f"{CONTACT_PREFIX}handle": AttributeState(
                name=f"{CONTACT_PREFIX}handle", values=("@north",),
                coverage=Coverage.ACQUIRED, sources=("feed_a",),
            ),
        }
    )
    inv = invariant(
        (window(T0, "nascent", 3), window(T0 + DAY, "stable", 3)),
        topology=(WindowTopology(T0, T0 + DAY, neighbor_weights=(("ent-2", 2.0),)),),
    )
    dossier = build_dossier(
        subject,
        invariant=inv,
        relations=({"target": "ent-3", "relation": "linked_to", "source_ref": "obs-1"},),
        plan=plan_enrichment(subject, (offering("alias"),)),
    )

    assert dossier.identity.entity_ref == "ent-1"
    assert dossier.identity.stream_anchor == "evt-genesis0001"
    assert [e.state for e in dossier.timeline] == ["nascent", "stable"]
    assert {e.origin.value for e in dossier.links.edges} == {"derived", "observed"}
    assert dossier.contacts.kinds == ("handle",)
    assert dossier.gaps == (), "nothing outstanding: the planner found no work"
    assert dossier.conflicts == ()
    assert not dossier.is_empty
    assert dossier.is_complete


def test_dossier_is_json_shaped_and_content_addressed() -> None:
    subject = profile(alias=AttributeState("alias", ("x",), Coverage.ACQUIRED, ("s",)))
    dossier = build_dossier(subject, plan=plan_enrichment(subject, (offering("alias"),)))
    payload = dossier.as_dict()

    assert set(payload) == {
        "dossier_id", "identity", "is_empty", "is_complete", "timeline", "links",
        "contacts", "coverage", "gaps", "conflicts",
    }
    assert payload["dossier_id"] == dossier.dossier_id == f"DS-{dossier.integrity_digest[:32]}"
    assert len(dossier.integrity_digest) == 64


# --------------------------------------------------------------------------
# 2. Gaps are visible, and their absence is declared
# --------------------------------------------------------------------------


def test_gaps_come_from_the_plan_verbatim() -> None:
    subject = profile(alias=AttributeState("alias", ("x",), Coverage.ACQUIRED, ("feed_a",)))
    plan = plan_enrichment(
        profile(),
        (offering("alias", "handle"), offering("alias", key_env="FEED_C_KEY",
                                              source_id="feed_c")),
        available={"feed_a": True, "feed_c": False},
    )
    dossier = build_dossier(subject, plan=plan)

    assert [g.attribute for g in dossier.gaps] == ["alias", "handle"]
    assert dossier.gaps[0].candidate_sources == ("feed_a",)
    assert dossier.gaps[0].blocked_sources == ("feed_c",)
    assert dossier.has_work
    assert not dossier.is_complete


def test_missing_plan_is_declared_not_treated_as_zero_work() -> None:
    subject = profile(alias=AttributeState("alias", ("x",), Coverage.ACQUIRED, ("feed_a",)))
    with_plan = build_dossier(subject, plan=plan_for(subject, feed_a=True))
    without = build_dossier(subject)

    assert with_plan.coverage.plan_known is True
    assert without.coverage.plan_known is False
    assert without.coverage.attributes is None
    assert without.gaps == ()
    assert not without.is_complete, "no planner has looked: the dossier is not complete"


def test_a_plan_that_ran_and_found_nothing_differs_from_no_plan() -> None:
    subject = profile(alias=AttributeState("alias", ("x",), Coverage.ACQUIRED, ("feed_a",)))
    saturated = plan_enrichment(subject, (offering("alias"),))
    assert saturated.gaps == ()
    dossier = build_dossier(subject, plan=saturated)

    assert dossier.coverage.plan_known is True
    assert dossier.coverage.attributes is not None
    assert not dossier.has_work


# --------------------------------------------------------------------------
# 3. Conflicts are shown with both sides
# --------------------------------------------------------------------------


def test_conflict_keeps_both_sides_and_their_sources() -> None:
    state = conflicting(
        AttributeState(name="role"),
        ("feed_a", "operator"),
        ("feed_b", "broker"),
    )
    assert state.coverage is Coverage.CONFLICT
    dossier = build_dossier(profile(role=state))

    conflict = dossier.conflicts[0]
    assert conflict.subject == "role"
    assert [side.value for side in conflict.sides] == ["broker", "operator"]
    assert conflict.sources == ("feed_a", "feed_b")
    assert conflict.sides_known
    assert dossier.as_dict()["conflicts"][0]["sides_known"] is True


def test_conflict_is_not_resolved_by_arrival_order() -> None:
    forwards = conflicting(AttributeState("role"), ("feed_a", "operator"), ("feed_b", "broker"))
    backwards = conflicting(AttributeState("role"), ("feed_b", "broker"), ("feed_a", "operator"))

    one = build_dossier(profile(role=forwards)).as_dict()["conflicts"]
    two = build_dossier(profile(role=backwards)).as_dict()["conflicts"]
    assert one == two, "ingestion order must not decide the dossier"


def test_conflicting_contact_is_not_attributed_to_either_source() -> None:
    """A conflict cannot be decomposed per source, so no contact row is invented."""
    state = conflicting(
        AttributeState(name=f"{CONTACT_PREFIX}mail"), ("feed_a", "a@x"), ("feed_b", "b@x")
    )
    dossier = build_dossier(profile(**{f"{CONTACT_PREFIX}mail": state}))

    assert dossier.contacts.contacts == (), "cross-producting would fake 4 attributions"
    assert dossier.coverage.untraced_contacts == 2
    conflict = dossier.conflicts[0]
    assert [side.value for side in conflict.sides] == ["a@x", "b@x"], "values stay visible"
    assert conflict.sources == ("feed_a", "feed_b")


def test_agreed_contact_value_is_repeated_per_contributing_source() -> None:
    state = AttributeState(
        name=f"{CONTACT_PREFIX}mail", values=("a@x",), coverage=Coverage.ACQUIRED,
        sources=("feed_b", "feed_a"),
    )
    dossier = build_dossier(profile(**{f"{CONTACT_PREFIX}mail": state}))

    assert [(c.value, c.source) for c in dossier.contacts.contacts] == [
        ("a@x", "feed_a"), ("a@x", "feed_b"),
    ]
    assert dossier.coverage.untraced == 0


def test_plan_reported_conflict_without_values_is_still_shown() -> None:
    subject = profile(alias=AttributeState("alias", ("x",), Coverage.ACQUIRED, ("feed_a",)))
    plan = replace(plan_enrichment(subject, ()), conflicts=("role",))
    dossier = build_dossier(subject, plan=plan)

    conflict = dossier.conflicts[0]
    assert conflict.subject == "role"
    assert conflict.sides == ()
    assert conflict.sides_known is False
    assert not dossier.is_complete


def test_conflict_without_sources_is_dropped_and_counted() -> None:
    state = AttributeState(
        name="role", values=("operator", "broker"), coverage=Coverage.CONFLICT, sources=()
    )
    dossier = build_dossier(profile(role=state))

    assert dossier.conflicts == ()
    assert dossier.coverage.untraced_conflicts == 1
    assert not dossier.coverage.is_traceable


# --------------------------------------------------------------------------
# 4. Traceability — nothing reaches the dossier without a source
# --------------------------------------------------------------------------


def test_every_timeline_entry_cites_the_invariant_provenance() -> None:
    inv = invariant((window(T0, "nascent", 2), window(T0 + DAY, "dormant", 0)))
    dossier = build_dossier(profile(), invariant=inv)

    for entry in dossier.timeline:
        assert entry.source_refs == ("evt-chain-tip-0001", "evt-genesis0001", "obs-1")


def test_every_edge_and_contact_cites_a_source() -> None:
    subject = profile(
        **{
            f"{CONTACT_PREFIX}mail": AttributeState(
                f"{CONTACT_PREFIX}mail", ("a@x",), Coverage.ACQUIRED, ("feed_a",)
            )
        }
    )
    inv = invariant(
        (window(T0, "nascent", 1),),
        topology=(WindowTopology(T0, T0 + DAY, neighbor_weights=(("ent-2", 1.0),)),),
    )
    dossier = build_dossier(subject, invariant=inv, mentions=[
        {"entity_id": "ent-9", "page_url": "https://page/1", "mention_count": 2}
    ])

    assert all(edge.source_refs for edge in dossier.links.edges)
    assert all(contact.source for contact in dossier.contacts.contacts)


def test_lifecycle_fact_is_traced_even_to_an_unwritten_provenance_block() -> None:
    """The genesis anchor is always a usable source: identity cannot exist without one."""
    inv = invariant((window(T0, "nascent", 4), window(T0 + DAY, "stable", 4)), traced=False)
    dossier = build_dossier(profile(), invariant=inv)

    assert len(dossier.timeline) == 2
    assert {e.source_refs for e in dossier.timeline} == {("evt-genesis0001",)}
    assert dossier.coverage.traced_facts == dossier.coverage.total_facts == 2
    assert dossier.coverage.untraced_facts == 0


def test_unsourced_timeline_entry_cannot_be_constructed() -> None:
    """The drop rule is enforced by the value type, not only by the builder."""
    with pytest.raises(ValueError, match="source refs"):
        TimelineEntry(T0, T0 + DAY, "nascent", 3, source_refs=())


def test_unsourced_relation_is_dropped_and_counted() -> None:
    dossier = build_dossier(
        profile(),
        relations=({"target": "ent-5", "relation": "linked_to"},),
    )
    assert dossier.links.edges == ()
    assert dossier.coverage.untraced_edges == 1


def test_unsourced_contact_is_dropped_and_counted() -> None:
    subject = profile(
        **{
            f"{CONTACT_PREFIX}mail": AttributeState(
                f"{CONTACT_PREFIX}mail", ("a@x",), Coverage.ACQUIRED, sources=()
            )
        }
    )
    dossier = build_dossier(subject)

    assert dossier.contacts.contacts == ()
    assert dossier.coverage.untraced_contacts == 1
    assert dossier.coverage.total_contacts == 1


def test_fan_without_a_page_is_unsourced_and_does_not_become_a_neighbour() -> None:
    dossier = build_dossier(profile(), fan={("ent-1", "ent-7"): 3})

    assert dossier.links.edges == ()
    assert dossier.coverage.untraced_edges == 1
    assert dossier.coverage.traced_edges == 0


def test_relation_without_target_or_relation_is_unsourced_work() -> None:
    dossier = build_dossier(profile(), relations=({"relation": "linked_to"}, {"target": "x"}))
    assert dossier.links.edges == ()
    assert dossier.coverage.untraced_edges == 2


def test_traced_ratio_accounts_for_drops() -> None:
    subject = profile(
        **{
            f"{CONTACT_PREFIX}mail": AttributeState(
                f"{CONTACT_PREFIX}mail", ("a@x",), Coverage.ACQUIRED, sources=()
            )
        }
    )
    dossier = build_dossier(subject)
    assert dossier.coverage.traced_ratio == 0.0


# --------------------------------------------------------------------------
# 5. The empty dossier is honest
# --------------------------------------------------------------------------


def test_empty_dossier_is_empty_and_incomplete() -> None:
    dossier = build_dossier(profile())

    assert dossier.is_empty
    assert dossier.timeline == ()
    assert dossier.links.edges == ()
    assert dossier.contacts.contacts == ()
    assert dossier.gaps == ()
    assert dossier.conflicts == ()
    assert dossier.coverage.total_facts == 0
    assert dossier.coverage.traced_ratio == 1.0, "nothing to drop: nothing claimed"
    assert not dossier.is_complete


def test_empty_dossier_still_names_its_subject() -> None:
    dossier = build_dossier(profile())
    assert dossier.identity == DossierIdentity(
        entity_ref="ent-1", type_label="record", stream_anchor="", revision=0
    )
    assert dossier.links.nodes == ("ent-1",), "the subject is a node even with no edges"
    assert dossier.links.degree == 0


def test_empty_plan_only_dossier_reports_explicit_gaps() -> None:
    subject = profile()
    plan = plan_enrichment(
        subject,
        (offering("alias", "handle"), offering("alias", source_id="feed_b")),
        available={},
    )
    dossier = build_dossier(subject, plan=plan)

    assert dossier.is_empty
    assert [g.attribute for g in dossier.gaps] == ["alias", "handle"]
    assert not dossier.is_complete
    assert dossier.coverage.attributes.unknown == 2


def test_dossier_refuses_a_subject_it_cannot_name() -> None:
    with pytest.raises(ValueError, match="entity_ref"):
        build_dossier(EntityProfile(entity_ref=""))


def test_dossier_without_invariant_claims_no_stream_position() -> None:
    dossier = build_dossier(profile())
    assert dossier.identity.stream_anchor == ""
    assert dossier.identity.revision == 0


# --------------------------------------------------------------------------
# 6. Determinism — order comes from content, not from arrival
# --------------------------------------------------------------------------


def test_shuffled_inputs_render_identical_dossiers() -> None:
    slices = (
        window(T0 + 2 * DAY, "stable", 2),
        window(T0, "nascent", 5),
        window(T0 + DAY, "decaying", 1),
    )
    inv = invariant(
        slices,
        topology=(
            WindowTopology(T0, T0 + DAY, neighbor_weights=(("ent-3", 1.0),)),
            WindowTopology(T0 + DAY, T0 + 2 * DAY, neighbor_weights=(("ent-2", 4.0),)),
        ),
    )
    subject = profile(
        **{
            f"{CONTACT_PREFIX}mail": AttributeState(
                f"{CONTACT_PREFIX}mail", ("b@x", "a@x"), Coverage.ACQUIRED,
                sources=("feed_b", "feed_a"),
            ),
            "role": conflicting(AttributeState("role"), ("s1", "x"), ("s2", "y")),
        }
    )
    relations = [
        {"target": "ent-5", "relation": "linked_to", "source_ref": "r1"},
        {"target": "ent-4", "relation": "linked_to", "source_ref": "r2", "weight": 2.0},
    ]
    mentions = [
        {"entity_id": "ent-8", "page_url": "https://b", "mention_count": 1},
        {"entity_id": "ent-7", "page_url": "https://a", "mention_count": 4},
    ]
    fan = {("ent-1", "ent-6"): 9}

    forwards = build_dossier(
        subject, invariant=inv, mentions=mentions, relations=relations, fan=fan
    )
    backwards = build_dossier(
        subject,
        invariant=inv,
        mentions=list(reversed(mentions)),
        relations=list(reversed(relations)),
        fan=dict(reversed(list(fan.items()))),
    )

    assert forwards.as_dict() == backwards.as_dict()
    assert forwards.integrity_digest == backwards.integrity_digest


def test_deterministic_ordering_of_every_section() -> None:
    inv = invariant((window(T0 + DAY, "stable", 2), window(T0, "nascent", 5)))
    subject = profile(
        **{
            f"{CONTACT_PREFIX}phone": AttributeState(
                f"{CONTACT_PREFIX}phone", ("+9",), Coverage.ACQUIRED, ("feed_b",)
            ),
            f"{CONTACT_PREFIX}mail": AttributeState(
                f"{CONTACT_PREFIX}mail", ("a@x",), Coverage.ACQUIRED, ("feed_a",)
            ),
        }
    )
    dossier = build_dossier(
        subject,
        invariant=inv,
        relations=(
            {"target": "ent-3", "relation": "r", "source_ref": "b"},
            {"target": "ent-2", "relation": "r", "source_ref": "a"},
        ),
        plan=plan_enrichment(profile(), (offering("alias"),)),
    )

    assert [e.window_start for e in dossier.timeline] == [T0, T0 + DAY]
    assert [e.target for e in dossier.links.edges] == ["ent-2", "ent-3"]
    assert dossier.contacts.kinds == ("mail", "phone")
    assert [g.attribute for g in dossier.gaps] == ["alias"]
    assert dossier.links.nodes == ("ent-1", "ent-2", "ent-3")


# --------------------------------------------------------------------------
# 7. The timeline is built from the invariant's real lifecycle windows
# --------------------------------------------------------------------------


def test_timeline_mirrors_lifecycle_slice_fields_exactly() -> None:
    slices = (
        TemporalSlice(
            window_start=T0,
            window_end=T0 + DAY,
            state=LifecycleState.NASCENT,
            event_count=7,
            events_per_period=7.0,
            burstiness=0.25,
            first_seen=T0,
            last_seen=T0 + timedelta(hours=6),
        ),
        TemporalSlice(
            window_start=T0 + DAY,
            window_end=T0 + 2 * DAY,
            state=LifecycleState.DORMANT,
            event_count=0,
            events_per_period=0.0,
            burstiness=None,
            first_seen=None,
            last_seen=None,
        ),
    )
    dossier = build_dossier(profile(), invariant=invariant(slices))

    active = tuple(s for s in slices if s.event_count > 0)
    assert len(dossier.timeline) == len(active)
    for entry, source_slice in zip(dossier.timeline, active, strict=True):
        assert entry.window_start == source_slice.window_start
        assert entry.window_end == source_slice.window_end
        assert entry.state == source_slice.state.value
        assert entry.event_count == source_slice.event_count
    assert dossier.coverage.dormant_windows == len(slices) - len(active)


def test_timeline_does_not_claim_coverage_it_never_had() -> None:
    """A window nobody swept is an unknown, not evidence of absence.

    The lifecycle grid is derived from the span between observed events, so it fills the gaps
    between them with windows that hold nothing. A real sweep of ``example.com`` whose RDAP
    record carries a 1995 registration date produced 1627 weekly windows, 1626 of them empty;
    rendering those as ``EMPTY`` would tell an analyst the platform watched every week of the
    last thirty-one years. It watched once. They are counted, not rendered.
    """
    slices = (
        window(T0, "nascent", 3),
        window(T0 + DAY, "dormant", 0),
        window(T0 + 2 * DAY, "growing", 9),
    )
    dossier = build_dossier(profile(), invariant=invariant(slices))

    assert [e.coverage for e in dossier.timeline] == [Coverage.ACQUIRED, Coverage.ACQUIRED]
    assert [e.event_count for e in dossier.timeline] == [3, 9]
    assert dossier.coverage.dormant_windows == 1, "the omission is stated, not performed"
    assert dossier.coverage.traced_facts == 2
    assert dossier.coverage.total_facts == 2


def test_timeline_from_a_stream_projected_invariant() -> None:
    """End to end over the real builder: dossier windows are that stream's windows."""
    entries = [
        {
            "ts": T0 + timedelta(hours=1),
            "kind": "observed",
            "sequence": 1,
            "entity_id": "ent-1",
            "record_hash": "h1",
            "observation_id": "obs-1",
            "payload": {"neighbors": {"ent-2": 2.0}, "community": "c1"},
        },
        {
            "ts": T0 + timedelta(days=3),
            "kind": "observed",
            "sequence": 2,
            "entity_id": "ent-1",
            "record_hash": "h2",
            "observation_id": "obs-2",
            "payload": {"neighbors": {"ent-2": 1.0}},
        },
    ]
    inv = from_entity_stream(entries, window=timedelta(days=1))
    dossier = build_dossier(profile(), invariant=inv)

    assert len(inv.lifecycle.slices) == 4, "the invariant keeps its whole grid"
    assert len(dossier.timeline) == 2, "the dossier shows the windows that hold evidence"
    assert [e.state for e in dossier.timeline] == ["nascent", "growing"]
    assert [e.event_count for e in dossier.timeline] == [
        s.event_count for s in inv.lifecycle.slices if s.event_count > 0
    ]
    assert dossier.coverage.dormant_windows == 2


# --------------------------------------------------------------------------
# 8. Links carry their origin, and origins are not merged
# --------------------------------------------------------------------------


def test_link_origins_are_distinguishable() -> None:
    inv = invariant(
        (window(T0, "nascent", 1),),
        topology=(WindowTopology(T0, T0 + DAY, neighbor_weights=(("ent-2", 1.0),)),),
    )
    dossier = build_dossier(
        profile(),
        invariant=inv,
        relations=({"target": "ent-2", "relation": "adjacent", "source_ref": "obs-1"},),
        mentions=[{"entity_id": "ent-2", "page_url": "https://p/1"}],
    )

    derived = dossier.links.of_origin(LinkOrigin.DERIVED)
    observed = dossier.links.of_origin(LinkOrigin.OBSERVED)
    co = dossier.links.of_origin(LinkOrigin.CO_MENTION)

    assert [e.weight for e in derived] == [1.0]
    assert [e.relation for e in observed] == [ADJACENT_RELATION]
    assert [e.relation for e in co] == [CO_MENTION_RELATION]
    assert len(dossier.links.edges) == 3, "the same pair under two origins stays two edges"
    assert dossier.links.degree == 1


def test_derived_weights_sum_across_windows() -> None:
    inv = invariant(
        (window(T0, "nascent", 1), window(T0 + DAY, "stable", 2)),
        topology=(
            WindowTopology(T0, T0 + DAY, neighbor_weights=(("ent-2", 1.0), ("ent-3", 5.0))),
            WindowTopology(T0 + DAY, T0 + 2 * DAY, neighbor_weights=(("ent-2", 2.0),)),
        ),
    )
    dossier = build_dossier(profile(), invariant=inv)
    weights = {e.target: e.weight for e in dossier.links.edges}

    assert weights == {"ent-2": 3.0, "ent-3": 5.0}
    assert all(e.origin is LinkOrigin.DERIVED for e in dossier.links.edges)


def test_co_mention_weight_comes_from_the_page_mentions() -> None:
    dossier = build_dossier(profile(), mentions=[
        {"entity_id": "ent-2", "page_url": "https://p/1", "mention_count": 3},
        {"entity_id": "ent-2", "page_url": "https://p/2", "mention_count": 4},
    ])
    edge = dossier.links.edges[0]

    assert edge.weight == 7.0
    assert edge.source_refs == ("https://p/1", "https://p/2")


def test_preaggregated_fan_sets_the_weight_when_present() -> None:
    dossier = build_dossier(
        profile(),
        mentions=[{"entity_id": "ent-2", "page_url": "https://p/1", "mention_count": 9}],
        fan={("ent-1", "ent-2"): 2},
    )
    assert dossier.links.edges[0].weight == 2.0
    assert dossier.links.edges[0].source_refs == ("https://p/1",)


def test_self_mention_is_not_a_link() -> None:
    dossier = build_dossier(profile(), mentions=[{"entity_id": "ent-1", "page_url": "https://p"}])
    assert dossier.links.edges == ()


def test_typed_link_shaped_relations_are_read_without_rewriting() -> None:
    inv = invariant((window(T0, "nascent", 1),))
    dossier = build_dossier(
        profile(),
        invariant=inv,
        relations=({"target_id": "ent-2", "relation": "linked_to", "weight": 0.5},),
    )
    edge = dossier.links.edges[0]

    assert (edge.target, edge.relation, edge.weight) == ("ent-2", "linked_to", 0.5)
    assert edge.origin is LinkOrigin.OBSERVED
    assert edge.source_refs == ("evt-chain-tip-0001", "evt-genesis0001", "obs-1"), (
        "an asserted edge inside a known stream is traced to that stream"
    )


def test_typed_link_shaped_relation_without_a_stream_is_unsourced() -> None:
    dossier = build_dossier(
        profile(), relations=({"target_id": "ent-2", "relation": "linked_to"},)
    )
    assert dossier.links.edges == ()
    assert dossier.coverage.untraced_edges == 1


# --------------------------------------------------------------------------
# 9. Contacts: per-source rows, and their absence
# --------------------------------------------------------------------------


def test_one_contact_from_two_sources_is_two_rows_with_two_sources() -> None:
    subject = profile(
        **{
            f"{CONTACT_PREFIX}mail": AttributeState(
                f"{CONTACT_PREFIX}mail", ("a@x",), Coverage.ACQUIRED,
                sources=("feed_b", "feed_a"),
            )
        }
    )
    dossier = build_dossier(subject)
    contacts = dossier.contacts.by_kind("mail")

    assert [c.source for c in contacts] == ["feed_a", "feed_b"]
    assert dossier.contacts.sources_for("mail", "a@x") == ("feed_a", "feed_b")
    assert dossier.coverage.untraced == 0


def test_contacts_group_by_open_channel_kinds() -> None:
    subject = profile(
        **{
            f"{CONTACT_PREFIX}mail": AttributeState(
                f"{CONTACT_PREFIX}mail", ("a@x",), Coverage.ACQUIRED, ("feed_a",)
            ),
            f"{CONTACT_PREFIX}signal": AttributeState(
                f"{CONTACT_PREFIX}signal", ("@s",), Coverage.ACQUIRED, ("feed_b",)
            ),
        }
    )
    grouped = build_dossier(subject).contacts.by_type

    assert list(grouped) == ["mail", "signal"]
    assert grouped["signal"][0].value == "@s"


def test_non_contact_attributes_never_become_contacts() -> None:
    subject = profile(
        role=AttributeState("role", ("operator",), Coverage.ACQUIRED, ("feed_a",))
    )
    dossier = build_dossier(subject)
    assert dossier.contacts.contacts == ()
    assert dossier.coverage.traced_contacts == 0


# --------------------------------------------------------------------------
# 10. The value types refuse to hold unsourced content
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (
            lambda: TimelineEntry(T0, T0 + DAY, "nascent", 1, ()),
            "source refs",
        ),
        (
            lambda: Link("ent-1", "ent-2", "linked_to", LinkOrigin.OBSERVED, 1.0, ()),
            "source ref",
        ),
        (lambda: Contact(kind="mail", value="a@x", source=""), "source"),
        (lambda: Gap(attribute=""), "attribute"),
    ],
)
def test_unsourced_value_types_refuse_construction(factory, message) -> None:
    with pytest.raises(ValueError, match=message):
        factory()


def test_timeline_entry_rejects_an_inverted_window() -> None:
    with pytest.raises(ValueError, match="window_end"):
        TimelineEntry(T0 + DAY, T0, "nascent", 1, ("obs-1",))


def test_link_map_and_contact_set_normalize_order_on_construction() -> None:
    edges = (
        Link("ent-1", "ent-9", "r", LinkOrigin.OBSERVED, 1.0, ("r1",)),
        Link("ent-1", "ent-2", "r", LinkOrigin.DERIVED, 1.0, ("r2",)),
    )
    contacts = (
        Contact("mail", "b@x", "s2"),
        Contact("mail", "a@x", "s1"),
    )
    links = LinkMap(subject="ent-1", nodes=("ent-9", "ent-1", "ent-2"), edges=edges)

    assert links.nodes == ("ent-1", "ent-2", "ent-9")
    assert [e.target for e in links.edges] == ["ent-2", "ent-9"]
    assert ContactSet(contacts).kinds == ("mail",)
    assert [c.value for c in ContactSet(contacts).contacts] == ["a@x", "b@x"]


def test_conflict_side_requires_a_value_and_conflict_requires_a_subject() -> None:
    with pytest.raises(ValueError, match="value"):
        ConflictSide(value="")
    with pytest.raises(ValueError, match="subject"):
        Conflict(subject="")


def test_coverage_view_reports_an_untraced_ledger() -> None:
    view = CoverageView(traced_facts=1, total_facts=3, untraced_edges=1)
    assert view.untraced == 1
    assert view.is_traceable is False
    assert round(view.traced_ratio, 4) == 0.3333


def test_dossier_sorts_what_it_is_given_even_if_constructed_out_of_order() -> None:
    dossier = Dossier(
        identity=DossierIdentity("ent-1"),
        timeline=(
            TimelineEntry(T0 + DAY, T0 + 2 * DAY, "stable", 1, ("r",)),
            TimelineEntry(T0, T0 + DAY, "nascent", 2, ("r",)),
        ),
        gaps=(Gap("zulu"), Gap("alpha")),
        conflicts=(Conflict(subject="zeta"), Conflict(subject="alpha")),
    )
    assert [e.window_start for e in dossier.timeline] == [T0, T0 + DAY]
    assert [g.attribute for g in dossier.gaps] == ["alpha", "zulu"]
    assert [c.subject for c in dossier.conflicts] == ["alpha", "zeta"]
    assert dossier.is_empty is False