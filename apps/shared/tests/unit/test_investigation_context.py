"""Feature 024 Phase 4 -- InvestigationContext identity, revision, scope.

Hermetic. No store, no clock, no network: every assertion here is about the object
contract, and the object contract is what makes the rest of the Context Engine
trustworthy.

Naming follows the repository convention: a test name states the invariant, not the
method call.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from domain.investigation_context import (
    CONTEXT_ID_PREFIX,
    REVISION_PREFIX,
    ContextEngineError,
    ContextRevision,
    InvestigationContext,
    InvestigationState,
    ScopeLinkage,
    verify_context_partition,
)

pytestmark = pytest.mark.unit


def ctx(**over) -> InvestigationContext:
    base = {
        "tenant_id": "t1",
        "investigation_id": "INV-1",
        "title": "Acme acquisition",
        "scope_refs": ("acme.example",),
    }
    base.update(over)
    return InvestigationContext(**base)


# -- identity (FR-024) --------------------------------------------------------

def test_context_id_is_cxi_prefixed_128_bit_digest():
    c = ctx()
    assert c.context_id.startswith(CONTEXT_ID_PREFIX)
    assert len(c.context_id) == len(CONTEXT_ID_PREFIX) + 32


def test_identity_is_stable_across_content_changes():
    """The address names the investigation, not its progress. If revision state moved
    the address, every stored reference to this context would break on the first
    revision."""
    before = ctx()
    after = replace_state(before, InvestigationState.CLOSED, question="something else")
    assert after.context_id == before.context_id
    assert before.address() == after.address()


def replace_state(
    c: InvestigationContext, state: InvestigationState, *, question: str = ""
) -> InvestigationContext:
    from dataclasses import replace

    return replace(c, state=state, question=question or c.question, context_id=c.address())


def test_two_contexts_with_same_identity_are_the_same_context():
    assert ctx().address() == ctx().address()


def test_different_investigation_is_a_different_context():
    assert ctx().address() != ctx(investigation_id="INV-2").address()


def test_different_scope_is_a_different_context():
    assert ctx().address() != ctx(scope_refs=("other.example",)).address()


def test_scope_ref_order_does_not_change_identity():
    assert ctx(scope_refs=("a", "b")).address() == ctx(scope_refs=("b", "a")).address()


def test_scope_refs_are_deduplicated():
    assert ctx(scope_refs=("a", "a", "b")).scope_refs == ("a", "b")


def test_declared_id_must_match_its_own_material():
    with pytest.raises(ContextEngineError) as e:
        ctx(context_id=CONTEXT_ID_PREFIX + "0" * 32)
    assert e.value.code == "context_id_mismatch"


def test_forged_id_is_refused_rather_than_silently_replaced():
    """Same stance as EvidenceContext: a mismatch is a contract violation, not an
    invitation to recompute."""
    c = ctx()
    from dataclasses import replace

    with pytest.raises(ContextEngineError) as e:
        replace(c, title="tampered", context_id=c.context_id)
    assert e.value.code == "context_id_mismatch"


def test_context_is_frozen():
    with pytest.raises(FrozenInstanceError):
        ctx().title = "changed"  # type: ignore[misc]


# -- refusals -----------------------------------------------------------------

def test_tenant_is_required():
    with pytest.raises(ContextEngineError) as e:
        ctx(tenant_id="")
    assert e.value.code == "tenant_id_missing"


def test_investigation_is_required():
    with pytest.raises(ContextEngineError) as e:
        ctx(investigation_id="")
    assert e.value.code == "investigation_id_missing"


def test_an_empty_scope_is_refused():
    """A context with no scope is indistinguishable from no context at all. The
    platform's discipline elsewhere is that None means 'honestly unknown', not
    'empty'; a scopeless context would read as empty when it is unknown."""
    with pytest.raises(ContextEngineError) as e:
        ctx(scope_refs=())
    assert e.value.code == "scope_empty"


def test_unknown_identity_schema_is_refused():
    with pytest.raises(ContextEngineError) as e:
        ctx(identity_schema="investigation-context/v99")
    assert e.value.code == "identity_schema_unknown"


# -- unknown is not empty (FR-030) --------------------------------------------

def test_uninvestigated_and_closed_are_distinguishable():
    assert InvestigationState.UNINVESTIGATED != InvestigationState.CLOSED
    assert InvestigationState.EXHAUSTED != InvestigationState.SATURATED


def test_state_survives_round_trip():
    for state in InvestigationState:
        assert InvestigationContext.from_dict(ctx(state=state).to_dict()).state is state


def test_state_is_canonicalised_from_text():
    assert ctx(state="active").state is InvestigationState.ACTIVE


def test_unknown_state_text_is_refused():
    with pytest.raises(ValueError):
        ctx(state="vibing")


# -- revision (FR-025, FR-026, FR-029) ----------------------------------------

def rev(c: InvestigationContext, revision: int = 1, **over) -> ContextRevision:
    base = {
        "context_id": c.context_id,
        "revision": revision,
        "parent_revision": revision - 1,
        "state": InvestigationState.ACTIVE,
        "snapshot": c.to_dict(),
        "caused_by_event_ids": ("evt-1",),
    }
    base.update(over)
    return ContextRevision(**base)


def test_revision_id_is_prefixed_and_digest_addressed():
    r = rev(ctx())
    assert r.revision_id.startswith(REVISION_PREFIX)


def test_revision_chain_must_be_contiguous():
    with pytest.raises(ContextEngineError) as e:
        rev(ctx(), revision=3, parent_revision=1)
    assert e.value.code == "revision_chain_broken"


def test_revision_must_be_positive():
    with pytest.raises(ContextEngineError) as e:
        rev(ctx(), revision=0, parent_revision=-1)
    assert e.value.code == "revision_invalid"


def test_revision_refuses_a_foreign_context_id():
    with pytest.raises(ContextEngineError) as e:
        rev(ctx(), context_id="CX-" + "0" * 32)
    assert e.value.code == "context_id_foreign"


def test_revision_round_trip_is_lossless():
    r = rev(ctx())
    assert ContextRevision.from_dict(r.to_dict()) == r


def test_distinct_revisions_get_distinct_ids():
    c = ctx()
    assert rev(c, revision=1).revision_id != rev(c, revision=2).revision_id


def test_revision_without_a_cause_is_not_auditable():
    r = rev(ctx(), caused_by_event_ids=(), decision_ids=(), operator_actions=())
    assert r.is_auditable is False


def test_revision_with_any_cause_is_auditable():
    assert rev(ctx(), caused_by_event_ids=("evt-1",)).is_auditable is True
    assert rev(ctx(), caused_by_event_ids=(), decision_ids=("DEC-1",)).is_auditable is True
    assert rev(ctx(), caused_by_event_ids=(), operator_actions=("pause",)).is_auditable is True


def test_next_revision_records_its_provenance():
    r = ctx().next_revision(
        revision=1,
        state=InvestigationState.ACTIVE,
        caused_by_event_ids=("evt-a", "evt-b"),
        decision_ids=("DEC-1",),
        operator_actions=("approve",),
        rules_version="rules/v1",
    )
    assert r.caused_by_event_ids == ("evt-a", "evt-b")
    assert r.decision_ids == ("DEC-1",)
    assert r.operator_actions == ("approve",)
    assert r.rules_version == "rules/v1"


def test_next_revision_does_not_mutate_its_parent():
    before = ctx()
    before.next_revision(revision=1, state=InvestigationState.CLOSED, caused_by_event_ids=("e",))
    assert before.state is InvestigationState.UNINVESTIGATED


def test_a_rewrite_of_the_snapshot_changes_the_revision_id():
    c = ctx()
    a = c.next_revision(revision=1, state=InvestigationState.ACTIVE, caused_by_event_ids=("e",))
    b = c.next_revision(revision=1, state=InvestigationState.CLOSED, caused_by_event_ids=("e",))
    assert a.revision_id != b.revision_id


# -- mode is recorded (FR-046) ------------------------------------------------

def test_mode_must_be_declared_and_known():
    assert rev(ctx(), mode="deterministic").mode == "deterministic"
    assert rev(ctx(), mode="adaptive").mode == "adaptive"
    with pytest.raises(ContextEngineError) as e:
        rev(ctx(), mode="vibes")
    assert e.value.code == "mode_unknown"


def test_same_state_under_a_different_mode_is_a_different_revision():
    """The mode is part of what produced the revision, so it is part of its address.
    Otherwise a deterministic rebuild could not prove it rebuilt the same thing."""
    c = ctx()
    det = c.next_revision(
        revision=1,
        state=InvestigationState.ACTIVE,
        caused_by_event_ids=("e",),
        mode="deterministic",
    )
    ada = c.next_revision(
        revision=1,
        state=InvestigationState.ACTIVE,
        caused_by_event_ids=("e",),
        mode="adaptive",
    )
    assert det.revision_id != ada.revision_id


# -- scope linkage (FR-031) ---------------------------------------------------

def test_scope_link_requires_a_reason():
    link = ScopeLinkage(
        other_context_id="CXI-" + "1" * 32, relation="reuses", reason="same entity"
    )
    assert link.reason


def test_scope_link_round_trips():
    link = ScopeLinkage(
        other_context_id="CXI-" + "1" * 32,
        relation="derived_from",
        reason="fork of an earlier scope",
        declared_at="2026-01-01T00:00:00Z",
        declared_by="operator:tim",
    )
    assert ScopeLinkage.from_dict(link.to_dict()) == link


def test_links_survive_a_context_round_trip():
    link = ScopeLinkage(
        other_context_id="CXI-" + "2" * 32, relation="sibling", reason="r"
    )
    c = ctx(scope_links=(link,))
    assert InvestigationContext.from_dict(c.to_dict()).scope_links == c.scope_links


def test_link_does_not_change_the_context_address():
    """Linkage is revision state, not identity: two contexts describing the same
    scope are the same scope whether or not one has declared a link yet."""
    plain = ctx()
    link = ScopeLinkage(
        other_context_id="CXI-" + "2" * 32, relation="sibling", reason="r"
    )
    linked = ctx(scope_links=(link,))
    assert linked.address() == plain.address()


# -- partition ----------------------------------------------------------------

def test_every_field_is_classified_as_identity_or_revision_state():
    verify_context_partition()


def test_round_trip_is_lossless():
    c = ctx(
        question="who acquired acme",
        state=InvestigationState.ACTIVE,
        policy_snapshot_ref="policy/3",
        created_at="2026-01-01T00:00:00Z",
    )
    assert InvestigationContext.from_dict(c.to_dict()) == c