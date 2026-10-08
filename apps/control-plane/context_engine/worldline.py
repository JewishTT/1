"""Control-plane side of the worldline anchor: load revisions, build the view.

``apps/science/context/worldline.py`` owns the algorithm and depends on nothing
below it. This module is the adapter that reads durable context state and feeds
it, which only ``control-plane`` may do (spec 025 plan.md: "control-plane is the
only writer of durable context state").

The split exists because ``LAYER_ORDER`` is
``shared -> interpretation -> admission -> projection -> control-plane -> science``:
a layer imports only downward. ``control-plane`` must not reach up into
``science`` by module path, so the import here is the bare-module form the
science API routes already use, and the direction of *data* is inverted -- the
durable state flows up into a pure view rather than the view reaching down into
a store.
"""

from __future__ import annotations

from typing import Any

from context.worldline import RevisionRecord, WorldlineView

from context_engine.store import ContextStore


async def load_worldline(store: ContextStore, context_id: str) -> WorldlineView:
    """Materialise a context's revision chain into a reader.

    A context with no revisions yields an empty view rather than raising: "no
    snapshot yet" is a legitimate state for a freshly created investigation, and
    the caller's job is to decide whether that is fatal.
    """
    revisions = await store.revisions(context_id)
    return WorldlineView(
        [
            RevisionRecord(
                snapshot_id=revision.revision_id,
                position=int(revision.revision),
                caused_by_event_ids=tuple(revision.caused_by_event_ids),
            )
            for revision in revisions
        ]
    )


async def load_worldline_for(
    store: ContextStore,
    context_id: str,
    *,
    max_revisions: int | None = None,
) -> WorldlineView:
    """Load a bounded prefix, newest-last, for callers that cannot hold it all.

    A long-running investigation accumulates revisions without bound. Anchoring
    only ever reads a prefix, so an explicit ceiling keeps the materialised view
    proportional to the anchor rather than to the investigation's age. The
    anchor's own snapshot is always retained: dropping it would turn a cheap
    read into a spurious ``snapshot_superseded``.
    """
    revisions = await store.revisions(context_id)
    if max_revisions is None or len(revisions) <= max_revisions:
        return await load_worldline(store, context_id)

    kept = list(revisions[-max_revisions:])
    return WorldlineView(
        [
            RevisionRecord(
                snapshot_id=revision.revision_id,
                position=int(revision.revision),
                caused_by_event_ids=tuple(revision.caused_by_event_ids),
            )
            for revision in kept
        ]
    )


def describe(view: WorldlineView) -> dict[str, Any]:
    """Small serialisable summary for API surfaces and operator metadata."""
    return {
        "head": view.current_snapshot_id(),
        "revisions": len(view),
        "positions": list(view.positions),
    }
