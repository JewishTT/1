"""The search projection's manifest is real, not decorative (FR-006, FR-071).

The WP0 capability matrix found `ProjectionManifest` with 24 tests and **no production
consumer**: the type was correct and unused, so "every projection carries a manifest"
was true of nothing. This suite pins the first real attachment.

What is asserted here is not "a manifest object exists" but the properties that make
the manifest worth having:

* the **output digest** changes when the projection's content changes;
* the **fingerprint** is stable across two rebuilds of the same batch, so a rebuild is
  reproducible rather than merely repeatable;
* `rebuildable` is **false** for an in-memory batch, because its source is the process;
* a batch spanning two tenants is refused rather than labelled with one of them.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_APPS = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_APPS / "shared"))
sys.path.insert(0, str(_APPS / "projection"))

from contracts.projection_manifest import ProjectionDeclarationError, ProjectionKind
from search.index import InMemorySearchIndex
from search.projector import SearchEvent, SearchProjector

pytestmark = pytest.mark.contract

TENANT = "tenant-a"


def _events() -> list[SearchEvent]:
    return [
        SearchEvent(
            kind="observation",
            doc_id="OB-2",
            body={"tenant_id": TENANT, "text": "second document"},
            event_id="evt-2",
        ),
        SearchEvent(
            kind="observation",
            doc_id="OB-1",
            body={"tenant_id": TENANT, "text": "first document"},
            event_id="evt-1",
        ),
        SearchEvent(
            kind="document",
            doc_id="DOC-1",
            body={"tenant_id": TENANT, "title": "a document"},
            event_id="evt-3",
        ),
    ]


def _projector(events: list[SearchEvent] | None = None) -> SearchProjector:
    projector = SearchProjector(InMemorySearchIndex())
    for event in events if events is not None else _events():
        projector.project(event)
    return projector


def test_rebuild_returns_a_manifest_for_the_batch() -> None:
    manifest = _projector().rebuild(tenant_id=TENANT)

    assert manifest.projection_kind is ProjectionKind.SEARCH
    assert manifest.tenant_id == TENANT
    assert manifest.source_event_offset["event_count"] == 3
    assert manifest.output_derivation["documents"] == 3
    assert manifest.output_digest.startswith("sha256:")
    assert manifest.input_snapshot_digest.startswith("sha256:")


def test_the_fingerprint_is_stable_across_identical_rebuilds() -> None:
    first = _projector().rebuild(tenant_id=TENANT)
    second = _projector().rebuild(tenant_id=TENANT)

    assert first.fingerprint() == second.fingerprint()
    assert first.output_digest == second.output_digest
    assert first.parameters_fingerprint == second.parameters_fingerprint


def test_changed_content_changes_the_output_digest() -> None:
    baseline = _projector().rebuild(tenant_id=TENANT)

    changed_events = _events()
    changed_events[0].body = {"tenant_id": TENANT, "text": "second document, revised"}
    changed = _projector(changed_events).rebuild(tenant_id=TENANT)

    assert changed.output_digest != baseline.output_digest, (
        "a changed projection body must move the output digest; otherwise a rebuild that "
        "silently altered the projection would look identical to a faithful one"
    )
    # The source cut did not move: the same events, one different body.
    assert changed.input_snapshot_digest == baseline.input_snapshot_digest


def test_an_in_memory_batch_is_not_declared_rebuildable() -> None:
    manifest = _projector().rebuild(tenant_id=TENANT)

    assert manifest.rebuildable is False, (
        "the in-memory batch is the process, not a durable cut; declaring it rebuildable "
        "would be the claim FR-071 exists to refuse"
    )
    assert manifest.output_derivation["source_is_durable"] is False


def test_a_durable_source_may_declare_rebuildable() -> None:
    manifest = _projector().rebuild(tenant_id=TENANT, source_is_durable=True)

    assert manifest.rebuildable is True
    assert manifest.can_rebuild()


def test_a_batch_without_a_tenant_yields_no_manifest() -> None:
    """Not a refusal and not a guess: there is no honest tenant to write.

    The contract refuses a manifest without a tenant (FR-090), so the projector
    returns ``None`` rather than inventing one. A caller that needs FR-006
    compliance passes ``tenant_id`` explicitly.
    """
    events = [SearchEvent(kind="observation", doc_id="OB-9", body={"text": "tenantless"})]
    assert _projector(events).rebuild() is None


def test_a_single_tenant_batch_derives_its_tenant() -> None:
    manifest = _projector().rebuild()

    assert manifest is not None
    assert manifest.tenant_id == TENANT, (
        "every document in the batch names the same tenant, so the manifest can state it "
        "without guessing"
    )


def test_a_mixed_tenant_batch_yields_no_manifest() -> None:
    events = _events() + [
        SearchEvent(
            kind="observation",
            doc_id="OB-7",
            body={"tenant_id": "tenant-b", "text": "another tenant"},
            event_id="evt-7",
        )
    ]
    assert _projector(events).rebuild() is None, (
        "two tenants in one batch have no single answer; labelling the batch with either one "
        "would make the projection readable across tenants"
    )


def test_rebuild_leaves_the_index_queryable() -> None:
    projector = _projector()
    projector.rebuild(tenant_id=TENANT)

    assert projector.search("observation", "first") == ["OB-1"]
