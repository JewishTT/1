"""The funnel projection, and the training separation (Feature 032).

This module is the reason the fabric exists. It is a pure fold over the event log, so
every number on the board can be re-derived and explained (Constitution §III).

The rule it exists to enforce
-----------------------------

**Training compliance is never summed into phishing risk.**

The donor separates them in its stats view — ``TrainingsAssigned`` and
``TrainingsCompleted`` are counted "from training campaigns only" — and that separation
is reproduced here structurally rather than by convention: the two tracks live in
different dictionaries, so there is no expression anywhere that can add them together by
accident.

The reason is worth stating, because the wrong version is easy to build and useless.
A single "engagement score" that adds *clicked a link* to *finished the training* is
measuring two unrelated things and reporting one number. Worse, it is systematically
misleading in the direction that costs money: an employee who did the right thing twice
looks like the department's best-performing asset and gets no follow-up, while one who
clicked once and refused once nets out to "average" and gets none either.

So the funnel reports depth on the phishing track and completion on the training track,
as two numbers, and never as one.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from specops.engagement.fabric import EngagementEvent
from specops.engagement.taxonomy import FUNNEL_STAGES, EventTrack, Stage

__all__ = (
    "CampaignFunnel",
    "FunnelResult",
    "SubjectProfile",
    "campaign_funnel",
    "subject_profiles",
)


@dataclass(frozen=True, slots=True)
class CampaignFunnel:
    """One campaign, projected onto the shared ladder."""

    campaign_id: str
    channels: tuple[str, ...]
    #: stage name -> subject count. A subject appears once per stage at its DEEPEST
    #: position, never once per event, so the numbers are comparable.
    reached: dict[str, int]
    subject_count: int
    event_count: int
    #: Raw event counts per kind, for the drill-down rather than the headline.
    event_counts: dict[str, int]
    training_assigned: int
    training_completed: int
    #: Subject count that resisted (reported, denied, abandoned).
    resisted: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "channels": list(self.channels),
            "reached": self.reached,
            "subject_count": self.subject_count,
            "event_count": self.event_count,
            "event_counts": self.event_counts,
            # Two tracks, two names, never a third combined number.
            "training": {
                "assigned": self.training_assigned,
                "completed": self.training_completed,
            },
            "resisted": self.resisted,
        }


@dataclass(frozen=True, slots=True)
class SubjectProfile:
    """One subject across every campaign. The cross-campaign view is the point."""

    #: ``None`` for an anonymised subject. The pseudonym still works.
    subject_ref: str | None
    pseudonym: str | None
    deepest_stage: Stage
    campaigns: tuple[str, ...]
    channels: tuple[str, ...]
    events: int
    #: Campaigns in which this subject conceded. "Repeat clicker" without a report.
    conceded_campaigns: tuple[str, ...]
    #: Campaigns in which this subject resisted — reported, denied or abandoned.
    resisted_campaigns: tuple[str, ...]
    trainings_completed: int

    @property
    def repeat_engaged(self) -> int:
        """How many campaigns this subject engaged with at all.

        The donor tracks repeat link clicks and repeat submissions as two separate
        counters. This folds both into "how many campaigns did they engage with", which
        answers the question a supervisor actually asks and cannot be inflated by one
        subject generating many events on a single campaign.
        """
        return len(self.campaigns)

    def as_dict(self) -> dict[str, Any]:
        return {
            "subject_ref": self.subject_ref,
            "pseudonym": self.pseudonym,
            "deepest_stage": int(self.deepest_stage),
            "campaigns": list(self.campaigns),
            "channels": list(self.channels),
            "events": self.events,
            "repeat_engaged": self.repeat_engaged,
            "conceded_campaigns": list(self.conceded_campaigns),
            "resisted_campaigns": list(self.resisted_campaigns),
            "trainings_completed": self.trainings_completed,
        }


@dataclass(frozen=True, slots=True)
class FunnelResult:
    """The whole board: per-campaign funnels plus the cross-campaign subject profiles."""

    campaigns: tuple[CampaignFunnel, ...]
    subjects: tuple[SubjectProfile, ...]
    #: How the subjects split at the deepest stage they reached. Never summed with
    #: training.
    outcome_split: dict[str, int] = field(default_factory=dict)
    #: Anything the projection could not compute, named.
    missing: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "campaigns": [c.as_dict() for c in self.campaigns],
            "subjects": [s.as_dict() for s in self.subjects],
            "outcome_split": self.outcome_split,
            "stages": [
                {"key": key, "stage": int(stage), "intent": intent}
                for key, stage, intent in FUNNEL_STAGES
            ],
            "missing": list(self.missing),
        }


def _identity(event: EngagementEvent) -> str:
    """How a subject is keyed for counting.

    An anonymised event has no ``subject_ref``, so it is keyed by its pseudonym. That is
    the whole point of the pseudonym: after anonymisation the funnel is still exact,
    because the same pseudonym is the same person to the projection even when the
    projection can no longer say who they are.
    """
    return event.subject_ref or event.pseudonym or f"event:{event.event_id}"


def campaign_funnel(campaign_id: str, events: Iterable[EngagementEvent]) -> CampaignFunnel:
    """Project one campaign onto the ladder.

    The counting rule: a subject is counted ONCE per stage, at their deepest position.
    Counting per event would make a subject who clicked twice look like two subjects and
    silently inflate every stage below the deepest one they reached.
    """
    rows = list(events)
    deepest: dict[str, Stage] = {}
    subjects: set[str] = set()
    channels: set[str] = set()
    event_counts: dict[str, int] = {}
    training_assigned: set[str] = set()
    training_completed: set[str] = set()
    resisted: set[str] = set()

    for event in rows:
        who = _identity(event)
        subjects.add(who)
        channels.add(event.channel)
        event_counts[event.kind.value] = event_counts.get(event.kind.value, 0) + 1
        if event.stage > deepest.get(who, Stage.NONE):
            deepest[who] = event.stage
        if event.track is EventTrack.TRAINING:
            training_assigned.add(who)
            if event.kind.value.endswith("training_completed"):
                training_completed.add(who)
        elif event.stage is Stage.RESISTED:
            resisted.add(who)

    reached: dict[str, int] = {}
    for name, stage, _intent in FUNNEL_STAGES:
        reached[name] = sum(1 for value in deepest.values() if value >= stage)

    return CampaignFunnel(
        campaign_id=campaign_id,
        channels=tuple(sorted(channels)),
        reached=reached,
        subject_count=len(subjects),
        event_count=len(rows),
        event_counts=dict(sorted(event_counts.items())),
        training_assigned=len(training_assigned),
        training_completed=len(training_completed),
        resisted=len(resisted),
    )


def subject_profiles(events: Iterable[EngagementEvent]) -> tuple[SubjectProfile, ...]:
    """One profile per subject across every campaign."""
    grouped: dict[str, list[EngagementEvent]] = {}
    for event in events:
        grouped.setdefault(_identity(event), []).append(event)

    profiles: list[SubjectProfile] = []
    for rows in grouped.values():
        deepest = max((e.stage for e in rows), default=Stage.NONE)
        campaigns = {e.campaign_id for e in rows}
        conceded = {
            e.campaign_id
            for e in rows
            if e.stage is Stage.CONCEDED and e.track is EventTrack.PHISHING
        }
        resisted = {
            e.campaign_id
            for e in rows
            if e.stage is Stage.RESISTED and e.track is EventTrack.PHISHING
        }
        completed = sum(
            1
            for e in rows
            if e.track is EventTrack.TRAINING and e.kind.value.endswith("training_completed")
        )
        first = rows[0]
        profiles.append(
            SubjectProfile(
                subject_ref=first.subject_ref,
                pseudonym=first.pseudonym,
                deepest_stage=deepest,
                campaigns=tuple(sorted(campaigns)),
                channels=tuple(sorted({e.channel for e in rows})),
                events=len(rows),
                conceded_campaigns=tuple(sorted(conceded)),
                resisted_campaigns=tuple(sorted(resisted)),
                trainings_completed=completed,
            )
        )

    # Deepest engagement first, then alphabetically, so the ordering is stable and the
    # top of the board is the people who went furthest rather than insertion order.
    profiles.sort(key=lambda p: (-int(p.deepest_stage), p.subject_ref or p.pseudonym or ""))
    return tuple(profiles)


def project(events: Iterable[EngagementEvent]) -> FunnelResult:
    """The whole board."""
    rows = list(events)
    by_campaign: dict[str, list[EngagementEvent]] = {}
    for event in rows:
        by_campaign.setdefault(event.campaign_id, []).append(event)

    funnels = tuple(
        campaign_funnel(campaign_id, campaign_events)
        for campaign_id, campaign_events in sorted(by_campaign.items())
    )
    profiles = subject_profiles(rows)

    split: dict[str, int] = {}
    for profile in profiles:
        key = _outcome_key(profile.deepest_stage)
        split[key] = split.get(key, 0) + 1

    missing: list[str] = []
    if not rows:
        missing.append(
            "the engagement board (no events recorded — a channel has to report before there "
            "is anything to project)"
        )

    return FunnelResult(
        campaigns=funnels,
        subjects=profiles,
        outcome_split=dict(sorted(split.items())),
        missing=tuple(missing),
    )


def _outcome_key(stage: Stage) -> str:
    if stage is Stage.RESISTED:
        return "resisted"
    if stage is Stage.CONCEDED:
        return "conceded"
    if stage is Stage.NONE:
        return "no signal"
    return "engaged"
