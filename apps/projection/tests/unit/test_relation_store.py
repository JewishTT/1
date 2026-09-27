"""T017/T018: RelationStore write path, directional reads, projection bridge."""

from __future__ import annotations

import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from domain import ProjectionRebuildableError
from domain.relation_claim import (
    EvidenceGrade,
    RelationClaim,
    RelationContractError,
    RelationRoleBinding,
    RelationStatus,
)
from domain.relation_identity import RelationArityMode

import path_shim  # noqa: F401 - ensure apps/shared precedes conflicting dirs
from graph.relation_store import (
    GraphProjectionBridge,
    InMemoryRelationStore,
    RelationClaimService,
    RelationStore,
)

pytestmark = pytest.mark.unit

PROV = {"event_id": "e1", "observation_id": "obs-1"}
CTX = "CX-" + "a" * 32


def _service() -> RelationClaimService:
    return RelationClaimService(tenant_id="t1")


def _directed(
    *,
    relation_type: str = "works_for",
    subject: str = "P1",
    obj: str = "O1",
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    revision_number: int = 1,
    status: RelationStatus = RelationStatus.ACTIVE,
    supersedes: str = "",
) -> RelationClaim:
    return _service().build(
        relation_type=relation_type,
        arity_mode=RelationArityMode.DIRECTED,
        subject_ref=subject,
        object_ref=obj,
        context_ref=CTX,
        valid_from=valid_from,
        valid_to=valid_to,
        revision_number=revision_number,
        status=status,
        supersedes=supersedes,
    )


def _undirected(*, subject: str = "D1", obj: str = "D2") -> RelationClaim:
    return _service().build(
        relation_type="co_occurs_with",
        arity_mode=RelationArityMode.UNDIRECTED,
        subject_ref=subject,
        object_ref=obj,
        context_ref=CTX,
    )


def _nary(*, subject: str = "P1", obj: str = "O1") -> RelationClaim:
    return _service().build(
        relation_type="employment",
        arity_mode=RelationArityMode.NARY,
        subject_ref=subject,
        object_ref=obj,
        context_ref=CTX,
        role_bindings=(
            RelationRoleBinding(role="person", member_ref=subject),
            RelationRoleBinding(role="organization", member_ref=obj),
            RelationRoleBinding(role="location", member_ref="HQ1"),
        ),
    )


# --- T017: write is idempotent, provenance-enforced, never mints an id ------


def test_write_is_idempotent_on_identical_content() -> None:
    store = InMemoryRelationStore()
    claim = _directed()
    first = store.write(claim, provenance=PROV)
    checksum = store.checksum()
    second = store.write(claim, provenance=PROV)
    assert first == second == claim.relation_id
    assert len(store) == 1
    assert store.checksum() == checksum


def test_write_without_provenance_is_refused_and_store_unchanged() -> None:
    store = InMemoryRelationStore()
    claim = _directed()
    for bad in ({}, {"event_id": "e1"}, None):
        with pytest.raises(ProjectionRebuildableError):
            store.write(claim, provenance=bad)
        assert len(store) == 0
        assert store.get(claim.relation_id) is None


def test_store_never_invents_a_relation_id() -> None:
    store = InMemoryRelationStore()
    claims = [_directed(subject="P1", obj="O1"), _undirected(), _nary()]
    for claim in claims:
        assert store.write(claim, provenance=PROV) == claim.relation_id
    for claim in claims:
        stored = store.get(claim.relation_id)
        assert stored is not None
        assert stored.relation_id == claim.relation_id
        assert stored.logical_relation_id == claim.logical_relation_id
    assert len(store) == 3
    assert store.get("RC-" + "0" * 32) is None


def test_write_refuses_a_colliding_relation_id_and_preserves_the_row() -> None:
    store = InMemoryRelationStore()
    claim = _directed()
    store.write(claim, provenance=PROV)
    collision = replace(claim, subject_ref="P9", object_ref="O9")
    assert collision.relation_id == claim.relation_id
    assert collision.content_hash != claim.content_hash
    with pytest.raises(RelationContractError):
        store.write(collision, provenance=PROV)
    assert len(store) == 1
    assert store.get(claim.relation_id) == claim
    assert store.detect_collisions() == ()


def test_bridge_to_edge_round_trips_properties_and_preserves_direction() -> None:
    claim = _directed(
        valid_from=datetime(2017, 1, 1, tzinfo=UTC),
        valid_to=datetime(2019, 1, 1, tzinfo=UTC),
    )
    edge = GraphProjectionBridge().to_edge(claim)
    assert edge.edge_id == claim.relation_id
    assert edge.edge_type == claim.relation_type
    assert edge.source == claim.subject_ref
    assert edge.target == claim.object_ref
    props = edge.properties
    assert props["relation_id"] == claim.relation_id
    assert props["logical_relation_id"] == claim.logical_relation_id
    assert props["revision_number"] == claim.revision_number
    assert props["arity_mode"] == str(claim.arity_mode)
    assert props["context_ref"] == claim.context_ref
    assert props["valid_from"] == "2017-01-01T00:00:00+00:00"
    assert props["valid_to"] == "2019-01-01T00:00:00+00:00"
    assert props["status"] == str(RelationStatus.ACTIVE)
    assert props["evidence_grade"] == str(EvidenceGrade.UNGRADED)
    assert props["observation_refs"] == list(claim.observation_refs)
    assert props["assertion_refs"] == list(claim.assertion_refs)
    assert props["tenant_id"] == claim.tenant_id


def test_bridge_projects_an_nary_claim_as_one_hyperedge() -> None:
    claim = _nary()
    hyperedge = GraphProjectionBridge().to_hyperedge(claim)
    assert hyperedge.source == ("HQ1", "O1", "P1")
    assert hyperedge.properties["role_map"] == {
        "person": "P1",
        "organization": "O1",
        "location": "HQ1",
    }
    assert hyperedge.properties["relation_id"] == claim.relation_id
    with pytest.raises(ValueError):
        GraphProjectionBridge().to_hyperedge(_directed())


def test_bridge_nodes_cover_every_participant() -> None:
    claim = _nary()
    nodes = GraphProjectionBridge().to_nodes(claim)
    assert {n.node_id for n in nodes} == {"P1", "O1", "HQ1"}
    assert all(n.properties["relation_id"] == claim.relation_id for n in nodes)
    assert {n.node_id: n.node_type for n in nodes} == {
        "P1": "person",
        "O1": "organization",
        "HQ1": "location",
    }
    bare = GraphProjectionBridge().to_node(_undirected())
    assert bare.node_id == "D1"
    assert bare.node_type == "Entity"
    assert bare.properties["tenant_id"] == "t1"


# --- T018: directional reads, revision chains, checksum ----------------------


def test_participants_is_directional_for_a_directed_claim() -> None:
    store = InMemoryRelationStore()
    claim = _directed()
    store.write(claim, provenance=PROV)
    assert store.participants("P1") == [claim]
    assert store.participants("O1") == []


def test_participants_matches_either_endpoint_when_undirected() -> None:
    store = InMemoryRelationStore()
    claim = _undirected()
    store.write(claim, provenance=PROV)
    assert store.participants("D1") == [claim]
    assert store.participants("D2") == [claim]
    assert store.participants("D3") == []


def test_participants_matches_every_role_binding_member_when_nary() -> None:
    store = InMemoryRelationStore()
    claim = _nary()
    store.write(claim, provenance=PROV)
    for ref in ("P1", "O1", "HQ1"):
        assert store.participants(ref) == [claim]
    assert store.participants("X1") == []


def test_participants_is_directional_for_a_temporal_claim() -> None:
    store = InMemoryRelationStore()
    claim = _service().build(
        relation_type="active_during",
        arity_mode=RelationArityMode.TEMPORAL,
        subject_ref="P1",
        object_ref="O1",
        context_ref=CTX,
        valid_from=datetime(2017, 1, 1, tzinfo=UTC),
        valid_to=datetime(2019, 1, 1, tzinfo=UTC),
    )
    store.write(claim, provenance=PROV)
    assert store.participants("P1") == [claim]
    assert store.participants("O1") == []


def test_by_type_filters_on_active_at_and_orders_deterministically() -> None:
    store = InMemoryRelationStore()
    open_window = _directed()
    expired = _directed(
        valid_from=datetime(2010, 1, 1, tzinfo=UTC),
        valid_to=datetime(2015, 1, 1, tzinfo=UTC),
    )
    current = _directed(valid_from=datetime(2020, 1, 1, tzinfo=UTC))
    other = _directed(relation_type="knows", subject="P3", obj="O3")
    for claim in (expired, current, open_window, other):
        store.write(claim, provenance=PROV)
    at_2018 = datetime(2018, 6, 1, tzinfo=UTC)
    at_2021 = datetime(2021, 6, 1, tzinfo=UTC)
    directed = [open_window, expired, current]
    assert {c.relation_id for c in directed} == {c.relation_id for c in store.by_type("works_for")}
    assert len({c.logical_relation_id for c in directed}) == 1  # the window is not identity
    assert store.by_type("works_for", active_at=at_2018) == [open_window]
    assert store.by_type("works_for", active_at=at_2021) == sorted(
        [open_window, current], key=lambda claim: claim.relation_id
    )
    assert store.by_type("nope") == []


def test_revisions_returns_the_ordered_chain_including_non_active() -> None:
    store = InMemoryRelationStore()
    first = _directed()
    second = _directed(revision_number=2)
    retracted = _directed(
        revision_number=3, status=RelationStatus.RETRACTED, supersedes=second.relation_id
    )
    for claim in (second, retracted, first):
        store.write(claim, provenance=PROV)
    chain = store.revisions(first.logical_relation_id)
    assert [c.revision_number for c in chain] == [1, 2, 3]
    assert [c.relation_id for c in chain] == [
        first.relation_id,
        second.relation_id,
        retracted.relation_id,
    ]
    assert chain[-1].status is RelationStatus.RETRACTED
    assert store.get(retracted.relation_id) is retracted  # I-3: never deleted
    assert store.revisions("RL-" + "0" * 32) == ()


def test_checksum_is_stable_under_insertion_order_and_tracks_content() -> None:
    claims = [_directed(subject="P1", obj="O1"), _undirected(), _nary()]
    forward = InMemoryRelationStore()
    backward = InMemoryRelationStore()
    for claim in claims:
        forward.write(claim, provenance=PROV)
    for claim in reversed(claims):
        backward.write(claim, provenance=PROV)
    assert forward.checksum() == backward.checksum()
    assert len(forward.checksum()) == 32
    forward.write(_directed(subject="P4", obj="O4"), provenance=PROV)
    assert forward.checksum() != backward.checksum()


def test_service_refuses_to_mint_a_claim_without_a_context_ref() -> None:
    for bad in ("", "   "):
        with pytest.raises(RelationContractError):
            _service().build(
                relation_type="works_for",
                arity_mode=RelationArityMode.DIRECTED,
                subject_ref="P1",
                object_ref="O1",
                context_ref=bad,
            )


def test_service_mints_both_identity_levels_and_never_accepts_a_forged_id() -> None:
    service = _service()
    claim = _directed()
    assert claim.relation_id.startswith("RC-")
    assert claim.logical_relation_id.startswith("RL-")
    assert claim.revision_number == 1
    assert claim.status is RelationStatus.ACTIVE
    mirrored = _directed(subject="O1", obj="P1")
    assert mirrored.relation_id != claim.relation_id
    assert mirrored.logical_relation_id != claim.logical_relation_id
    assert service.build(
        relation_type="works_for",
        arity_mode=RelationArityMode.DIRECTED,
        subject_ref="P1",
        object_ref="O1",
        context_ref=CTX,
    ) == claim


def test_service_next_revision_advances_the_chain_and_register_stores() -> None:
    service = _service()
    store = InMemoryRelationStore()
    claim = _directed()
    assert service.register(claim, provenance=PROV, store=store) == claim.relation_id
    assert store.get(claim.relation_id) == claim
    assert service.next_revision(claim.logical_relation_id) == 2
    assert service.next_revision(claim.logical_relation_id) == 3
    with pytest.raises(RelationContractError):
        service.register(claim, provenance=PROV)  # minting never persists by itself


def test_store_satisfies_the_relation_store_protocol() -> None:
    store = InMemoryRelationStore()
    for member in (
        "write",
        "get",
        "revisions",
        "by_type",
        "participants",
        "checksum",
    ):
        assert callable(getattr(store, member))
    assert isinstance(store, RelationStore)
