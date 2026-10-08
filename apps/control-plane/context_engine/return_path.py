"""The return path: acquired observations back into the context (the reverse direction).

The forward direction compiles context into search requests. This module closes the loop
by turning what acquisition produced into something the context can absorb. Without it the
cycle is a one-way street, and the failure is not obvious -- the loop runs, obligations
are generated, sources are queried, and the context never grows, because every observation
arrives carrying only an id.

The membership an observation needs already exists: the entity stream records
``(tenant, entity, sequence)`` rows carrying the ``observation_id`` that established the
entity. What was missing was the reverse lookup, and
:meth:`~db.entity_stream.SqlEntityStreamRepository.entities_for_observations` provides it.

Three rules this module keeps, each of which is a way the cycle used to lie:

**No membership means no placement, not a guessed one.** An observation with no entity
links yields an outcome with no entities, and the fabric refuses the placement and records
why. Attaching it to the nearest cell would grow the context with fiction.

**An anchor must be a real prior observation.** :func:`anchor_outcomes` links a new
referent to the observation that revealed it, because growth refuses a disjoint scope with
no anchor. The anchor is taken from observation order within the batch, which is the order
the batch was produced -- not from cell order, which would be circular.

**Coverage is measured, never assumed.** ``coverage_delta`` comes from what the sources
reported, so an action that ran and found nothing reads differently from one that found
something.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from context_engine.loop import ObservationOutcome


class EntityMembershipReader(Protocol):
    """The one capability needed from the entity stream.

    A Protocol rather than the concrete repository so this module carries no SQLAlchemy
    import and can be exercised against a plain mapping in a test. What it needs is one
    question answered: which entities did these observations establish.
    """

    async def entities_for_observations(
        self, *, tenant_id: str, observation_ids: Iterable[str]
    ) -> Mapping[str, Sequence[str]]: ...


@dataclass(frozen=True, slots=True)
class AcquisitionResult:
    """What one completed action produced, before membership is resolved."""

    action_id: str
    task_id: str
    observation_ids: tuple[str, ...] = ()
    contradicting: tuple[str, ...] = ()
    coverage_delta: float = 0.0
    marginal_gain: float = 0.0
    #: Free-form provenance, kept so a tick's outcome can be traced back to its source.
    provenance: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AnchorPolicy:
    """How a new referent is anchored to a prior observation.

    ``prior_only`` is the default and the safe setting: an observation may only be anchored
    to one that already has membership. Allowing an anchor to a sibling in the same batch
    would let a batch of mutually-unrelated observations bootstrap each other into a
    structure none of the evidence supports.
    """

    prior_only: bool = True

    def choose_anchor(
        self,
        members: Sequence[str],
        established: Sequence[tuple[str, tuple[str, ...]]],
    ) -> str:
        """Pick the anchor for a new observation from what is already established.

        An anchor that shares a referent is preferred: that is the observation that
        actually revealed this one. Failing that, and only under ``prior_only``, the
        first established observation is used so a genuinely new region still joins the
        context rather than being refused.

        Deterministic by construction -- ``established`` arrives in the order the batch was
        produced, so the same evidence always produces the same anchor and a replay
        reproduces the tree.
        """
        overlapping = [
            anchor
            for anchor, entities in established
            if set(entities) & set(members)
        ]
        if overlapping:
            return overlapping[0]
        for anchor, _ in established:
            return anchor if self.prior_only else ""
        return ""


def _fields(result: AcquisitionResult | ObservationOutcome) -> tuple[Any, ...]:
    """Read the outcome-shaped fields from either type.

    Both describe the same thing at different stages -- one before membership is resolved,
    one after -- so this keeps a caller from having to branch on which it holds.
    """
    if isinstance(result, AcquisitionResult):
        return (
            result.action_id,
            result.task_id,
            result.observation_ids,
            result.contradicting,
            result.coverage_delta,
            result.marginal_gain,
        )
    return (
        result.action_id,
        result.task_id,
        result.produced_observations,
        result.contradicting,
        result.coverage_delta,
        result.marginal_gain,
    )


def anchor_outcomes(
    results: Sequence[AcquisitionResult],
    entities: Mapping[str, Sequence[str]],
    *,
    policy: AnchorPolicy | None = None,
) -> dict[str, str]:
    """Decide which prior observation revealed each new observation's referents.

    Processes the batch in the order given and anchors each observation to one already
    carrying overlapping membership. An observation with no entities gets no anchor: there
    is nothing to anchor, and inventing one would attach unrelated evidence together.
    """
    rules = policy or AnchorPolicy()
    anchors: dict[str, str] = {}
    established: list[tuple[str, tuple[str, ...]]] = []
    for result in results:
        _, _, observation_ids, *_ = _fields(result)
        for observation_id in observation_ids:
            members = tuple(entities.get(observation_id, ()) or ())
            if not members:
                continue
            anchor = rules.choose_anchor(members, established)
            if anchor:
                anchors[observation_id] = anchor
            established.append((observation_id, members))
    return anchors


async def resolve_outcomes(
    results: Sequence[AcquisitionResult],
    reader: EntityMembershipReader,
    *,
    tenant_id: str,
    anchor_policy: AnchorPolicy | None = None,
) -> tuple[ObservationOutcome, ...]:
    """Turn acquisition results into outcomes carrying membership, read from the stream.

    This is the reverse direction's entry point. ``reader`` is asked once for the whole
    batch rather than per observation, because the fabric places an entire tick's evidence
    together and a per-observation query would make the cost of a tick proportional to the
    number of observations in it.
    """
    if not results:
        return ()
    wanted = [
        observation_id
        for result in results
        for observation_id in _fields(result)[2]
    ]
    members = await reader.entities_for_observations(
        tenant_id=tenant_id, observation_ids=wanted
    )
    entities = {key: tuple(value) for key, value in members.items()}
    anchors = anchor_outcomes(results, entities, policy=anchor_policy)

    outcomes: list[ObservationOutcome] = []
    for result in results:
        action_id, task_id, observation_ids, contradicting, coverage, gain = _fields(result)
        outcomes.append(
            ObservationOutcome(
                action_id=str(action_id),
                task_id=str(task_id),
                produced_observations=tuple(observation_ids),
                entities={
                    observation_id: entities[observation_id]
                    for observation_id in observation_ids
                    if observation_id in entities
                },
                revealed_by={
                    observation_id: anchors[observation_id]
                    for observation_id in observation_ids
                    if observation_id in anchors
                },
                contradicting=tuple(contradicting),
                coverage_delta=float(coverage),
                marginal_gain=float(gain),
            )
        )
    return tuple(outcomes)


def unplaced(outcomes: Sequence[ObservationOutcome]) -> tuple[str, ...]:
    """Observations that arrived without membership, and so cannot be placed.

    Reported rather than swallowed. An unplaced observation is a coverage question the
    investigation has to answer, and the caller needs the list to raise it -- a silently
    narrower context is the failure this whole direction exists to prevent.
    """
    missing: list[str] = []
    for outcome in outcomes:
        for observation_id in outcome.produced_observations:
            if not outcome.entities.get(observation_id):
                missing.append(observation_id)
    return tuple(missing)


def newly_grounded(
    before: Sequence[str], outcomes: Sequence[ObservationOutcome]
) -> tuple[str, ...]:
    """Which observations this batch established membership for that was absent before.

    The measure of whether the reverse direction is doing anything: a batch that grounds
    nothing new is a batch the context cannot learn from, whatever it reported as
    produced.
    """
    known = set(before)
    grounded: list[str] = []
    for outcome in outcomes:
        for observation_id in outcome.produced_observations:
            if outcome.entities.get(observation_id) and observation_id not in known:
                grounded.append(observation_id)
    return tuple(grounded)


# Imported late so the dataclass default above can use it without a circular import at
# module load: ``context_engine.loop`` imports nothing from this module.
from dataclasses import field