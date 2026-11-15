"""The engagement event taxonomy — one lifecycle, every channel (Feature 032).

Harvested from `donors/phishingclub` (AGPL-3.0) and re-expressed against this
platform's vocabulary. The donor is credited in ``DONT_HERITATE`` below and the
attribution lives in ``donors/phishingclub/ATTRIBUTION.md``; what was taken is the
*taxonomy*, which is a set of facts about an engagement rather than an implementation.

Why this exists at all
----------------------

Before this, the department had two live channels and no shared record:

    email   apps/specops/phishing.py  -> sent / opened / clicked / submitted
    voice   apps/specops/ghostline/   -> call placed / outcome

Neither could answer "who engages, how deep do they go, and in what order", because
they counted in different currencies and stored in different places. An assessor
comparing a phishing campaign to a voice drill got two unrelated numbers and had to
guess. This module is the third currency.

What was taken from the donor
-----------------------------

Its fourteen-event lifecycle, which is the most complete engagement model the donor
library has::

    campaign_closed
    campaign_recipient_message_sent        campaign_recipient_message_failed
    campaign_recipient_message_read
    campaign_recipient_submitted_data      campaign_recipient_reported
    campaign_recipient_evasion_page_visited
    campaign_recipient_before_page_visited campaign_recipient_page_visited
    campaign_recipient_after_page_visited  campaign_recipient_deny_page_visited
    campaign_recipient_training_started    campaign_recipient_training_completed

Three things in that model are genuinely better than what the department had, and are
reproduced here rather than reinvented:

1. **Multi-stage depth is a position, not a boolean.** ``before_/page_/after_/deny_
   page_visited`` distinguish *where in a multi-stage flow* the subject stopped. The
   platform's phishing router could previously only say "clicked". Knowing that a
   subject reached ``deny_page`` (the stage that refuses them) is a different fact
   from knowing they reached ``after_page``, and it changes what you do next.

2. **Training is counted on its own track.** The donor computes ``TrainingsAssigned``
   and ``TrainingsCompleted`` "from training campaigns only" and never sums them into
   the phishing funnel. That separation is the single most important thing in the
   model: an employee who finishes training and an employee who clicks a link are
   different observations about different things, and a dashboard that adds them
   produces a number that means nothing. :mod:`specops.engagement.funnel` enforces it.

3. **Anonymisation preserves linkage.** The donor's ``CampaignEvent.Anonymize`` strips
   the recipient link, the IP, the user agent and the submitted payload, and stamps a
   stable pseudonym in its place — so events stay countable and groupable while
   ceasing to identify anyone. :mod:`specops.engagement.fabric` reproduces that shape.

What was NOT taken, and why
---------------------------

* **Their palette.** ``pc-pink: #ff00ff`` / ``pc-purple: #9622fc`` and ~30 near-identical
  categorical colours are the exact list ``styles/tokens/color.css`` forbids. Rejected on
  the platform's own rules, not on taste.
* **Their campaign-counting shape.** Their stats count raw events. This platform keeps
  observations and derives (Constitution §III: every projection rebuildable from durable
  events), so the funnel here is a projection over an append-only log rather than a
  counter incremented in place.
* **Their Go backend.** Out of scope for this module; where a feature is genuinely
  needed (SCIM, reverse-proxy domains) it becomes an adapter question, not a port.

The invariant that survives the port
------------------------------------

``SUBMITTED_DATA`` records that a subject reached the stage and how far, and NEVER the
payload. This is the platform's ``CAPTURE_PASSWORDS = False`` invariant extended from
credentials to engagement data: see :mod:`specops.engagement.fabric` for the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, StrEnum
from typing import Final

__all__ = (
    "DONT_HERITATE",
    "EventKind",
    "EventTrack",
    "FUNNEL_STAGES",
    "Stage",
    "event_display_name",
    "is_credential_bearing",
    "position_in_funnel",
)

#: What was harvested, and what was refused. Kept next to the taxonomy on purpose: a
#: reader deciding whether this is a legitimate donor integration should not have to go
#: and reconstruct the judgement from the code.
DONT_HERITATE: Final[tuple[str, ...]] = (
    "their frontend (SvelteKit, 166 .svelte files) — a different framework, and the "
    "visual language is re-implemented in React on this platform's tokens instead",
    "their palette (pc-pink #ff00ff, pc-purple #9622fc, ~30 categorical colours) — the "
    "exact set styles/tokens/color.css forbids",
    "their Go backend — not ported; SCIM / reverse-proxy domains / SMTP are adapter "
    "questions when they are actually needed, not ports",
    "their submitted-data storage — their model persists what a subject typed on a "
    "landing page. This platform records that it happened and never the payload.",
)


class EventTrack(StrEnum):
    """Which question an event answers.

    The split is load-bearing and comes from the donor. ``phishing`` events say how
    deep a subject went on an adversarial path. ``training`` events say whether someone
    completed an exercise. Merging them produces a single number that describes neither.
    """

    PHISHING = "phishing"
    TRAINING = "training"
    LIFECYCLE = "lifecycle"


class EventKind(StrEnum):
    """The closed event vocabulary.

    Every name here is either one of the donor's fourteen or a voice-channel event
    this platform needed to add. Nothing outside this enum can be recorded: an
    unrecognised event is rejected at the boundary rather than stored and rendered as
    a string, because an open-ended event log is how an evidence substrate stops being
    queryable.
    """

    # ── donor events, renamed to this platform's casing ──────────────────────
    CAMPAIGN_CLOSED = "campaign_closed"

    MESSAGE_SENT = "campaign_recipient_message_sent"
    MESSAGE_FAILED = "campaign_recipient_message_failed"
    MESSAGE_READ = "campaign_recipient_message_read"

    EVASION_PAGE_VISITED = "campaign_recipient_evasion_page_visited"
    BEFORE_PAGE_VISITED = "campaign_recipient_before_page_visited"
    PAGE_VISITED = "campaign_recipient_page_visited"
    AFTER_PAGE_VISITED = "campaign_recipient_after_page_visited"
    DENY_PAGE_VISITED = "campaign_recipient_deny_page_visited"

    SUBMITTED_DATA = "campaign_recipient_submitted_data"
    REPORTED = "campaign_recipient_reported"

    TRAINING_STARTED = "campaign_recipient_training_started"
    TRAINING_COMPLETED = "campaign_recipient_training_completed"

    # ── voice channel, added by this platform ────────────────────────────────
    #: An outbound call reached the PSTN. The voice analogue of ``MESSAGE_SENT``.
    CALL_PLACED = "call_placed"
    #: The call was answered — a party picked up. Distinct from dialled.
    CALL_ANSWERED = "call_answered"
    #: The stage machine reached a new rung. Which rung is in ``metadata``.
    STAGE_REACHED = "stage_reached"
    #: The target said something that matched the playbook's declared pattern.
    STAGE_MATCHED = "stage_matched"
    #: The call ended. ``metadata`` carries the donor's own outcome vocabulary.
    CALL_COMPLETED = "call_completed"


#: Track per event. The donor's separation, expressed once so nothing has to infer it.
_TRACK: Final[dict[EventKind, EventTrack]] = {
    EventKind.CAMPAIGN_CLOSED: EventTrack.LIFECYCLE,
    EventKind.MESSAGE_SENT: EventTrack.PHISHING,
    EventKind.MESSAGE_FAILED: EventTrack.PHISHING,
    EventKind.MESSAGE_READ: EventTrack.PHISHING,
    EventKind.EVASION_PAGE_VISITED: EventTrack.PHISHING,
    EventKind.BEFORE_PAGE_VISITED: EventTrack.PHISHING,
    EventKind.PAGE_VISITED: EventTrack.PHISHING,
    EventKind.AFTER_PAGE_VISITED: EventTrack.PHISHING,
    EventKind.DENY_PAGE_VISITED: EventTrack.PHISHING,
    EventKind.SUBMITTED_DATA: EventTrack.PHISHING,
    EventKind.REPORTED: EventTrack.PHISHING,
    EventKind.TRAINING_STARTED: EventTrack.TRAINING,
    EventKind.TRAINING_COMPLETED: EventTrack.TRAINING,
    EventKind.CALL_PLACED: EventTrack.PHISHING,
    EventKind.CALL_ANSWERED: EventTrack.PHISHING,
    EventKind.STAGE_REACHED: EventTrack.PHISHING,
    EventKind.STAGE_MATCHED: EventTrack.PHISHING,
    EventKind.CALL_COMPLETED: EventTrack.PHISHING,
}

#: Human labels. The donor keeps the same map; it exists so the campaign wizard and the
#: board label an event the same way instead of showing the internal name.
_DISPLAY: Final[dict[EventKind, str]] = {
    EventKind.CAMPAIGN_CLOSED: "Campaign closed",
    EventKind.MESSAGE_SENT: "Message sent",
    EventKind.MESSAGE_FAILED: "Message failed",
    EventKind.MESSAGE_READ: "Message read",
    EventKind.EVASION_PAGE_VISITED: "Evasion page visited",
    EventKind.BEFORE_PAGE_VISITED: "Before page visited",
    EventKind.PAGE_VISITED: "Landing page visited",
    EventKind.AFTER_PAGE_VISITED: "After page visited",
    EventKind.DENY_PAGE_VISITED: "Deny page visited",
    EventKind.SUBMITTED_DATA: "Reached the ask",
    EventKind.REPORTED: "Reported",
    EventKind.TRAINING_STARTED: "Training started",
    EventKind.TRAINING_COMPLETED: "Training completed",
    EventKind.CALL_PLACED: "Call placed",
    EventKind.CALL_ANSWERED: "Call answered",
    EventKind.STAGE_REACHED: "Stage reached",
    EventKind.STAGE_MATCHED: "Stage matched",
    EventKind.CALL_COMPLETED: "Call completed",
}


class Stage(int, Enum):
    """Funnel position, comparable across channels.

    This is the thing the platform did not have. The email channel and the voice
    channel both produce a position on ONE ladder, so "who engaged further" is a
    comparable question for the first time.

    The ladder is monotone: an event at a higher stage implies every lower stage
    happened, which is what makes a single number per subject meaningful. Events that
    do not imply a lower stage (``EVASION_PAGE_VISITED``, ``REPORTED``) sit at zero
    and are read as flags rather than as depth — a subject who reported the message
    did not go deeper than a subject who did nothing.
    """

    NONE = 0
    DISPATCHED = 1
    """A message went out, or a call was placed."""
    ENGAGED = 2
    """Opened (read), or answered."""
    LANDED = 3
    """Clicked through, or reached a landing page."""
    STAGE_ADVANCED = 4
    """Reached a deeper page in a multi-stage flow, or a later stage of the call."""
    ASK_REACHED = 5
    """Reached the ask. The payload is never recorded."""
    CONCEDED = 6
    """Conceded: submitted, or matched the playbook's declared pattern."""
    RESISTED = 7
    """Stopped: reported, refused at the deny page, or abandoned the call."""


#: stage -> the events that establish it
_STAGE_EVENTS: Final[dict[EventKind, Stage]] = {
    EventKind.MESSAGE_SENT: Stage.DISPATCHED,
    EventKind.CALL_PLACED: Stage.DISPATCHED,
    EventKind.MESSAGE_FAILED: Stage.DISPATCHED,
    EventKind.MESSAGE_READ: Stage.ENGAGED,
    EventKind.CALL_ANSWERED: Stage.ENGAGED,
    EventKind.EVASION_PAGE_VISITED: Stage.ENGAGED,
    EventKind.PAGE_VISITED: Stage.LANDED,
    EventKind.BEFORE_PAGE_VISITED: Stage.LANDED,
    EventKind.AFTER_PAGE_VISITED: Stage.STAGE_ADVANCED,
    EventKind.DENY_PAGE_VISITED: Stage.RESISTED,
    EventKind.STAGE_REACHED: Stage.STAGE_ADVANCED,
    EventKind.STAGE_MATCHED: Stage.CONCEDED,
    EventKind.SUBMITTED_DATA: Stage.CONCEDED,
    EventKind.REPORTED: Stage.RESISTED,
    EventKind.CALL_COMPLETED: Stage.ENGAGED,
}

#: The funnel as a projection renders it. Names, not counts — the counts are derived.
FUNNEL_STAGES: Final[tuple[tuple[str, Stage, str], ...]] = (
    ("dispatched", Stage.DISPATCHED, "a message went out, or a call was placed"),
    ("engaged", Stage.ENGAGED, "opened, answered, or hit the evasion page"),
    ("landed", Stage.LANDED, "clicked through or reached the landing page"),
    ("advanced", Stage.STAGE_ADVANCED, "went deeper in a multi-stage flow or call"),
    ("ask", Stage.ASK_REACHED, "reached the ask — recorded, never the payload"),
    ("conceded", Stage.CONCEDED, "gave something up"),
    ("resisted", Stage.RESISTED, "stopped: reported, refused, or abandoned"),
)


def event_display_name(kind: EventKind) -> str:
    """The operator-facing label. Unknown kinds render as their raw name, never blank."""
    return _DISPLAY.get(kind, kind.value)


def track_of(kind: EventKind) -> EventTrack:
    """Which question an event answers: phishing risk, training compliance, or lifecycle."""
    return _TRACK[kind]


def position_in_funnel(kind: EventKind) -> Stage:
    """The rung an event establishes. An event outside the ladder is ``NONE``."""
    return _STAGE_EVENTS.get(kind, Stage.NONE)


def is_credential_bearing(kind: EventKind) -> bool:
    """Whether this event's *payload* would be a credential or personal data.

    ``SUBMITTED_DATA`` and the GhostLine utterance-equivalents are the two. The fabric
    refuses to store a payload for either, which is the same boundary the RoE gate
    draws for credentials — extended from credentials to engagement data.

    ``STAGE_MATCHED`` is here too: the donor's CLOSE-stage regex fires precisely when a
    subject says the secret out loud, so its payload is the secret.
    """
    return kind in {
        EventKind.SUBMITTED_DATA,
        EventKind.STAGE_MATCHED,
    }


@dataclass(frozen=True, slots=True)
class EventDefinition:
    """Static metadata for one event, resolved once so callers never re-derive it."""

    kind: EventKind
    track: EventTrack
    stage: Stage
    display: str
    credential_bearing: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "track": self.track.value,
            "stage": int(self.stage),
            "display": self.display,
            "credential_bearing": self.credential_bearing,
        }


DEFINITIONS: Final[dict[EventKind, EventDefinition]] = {
    kind: EventDefinition(
        kind=kind,
        track=_TRACK[kind],
        stage=_STAGE_EVENTS.get(kind, Stage.NONE),
        display=_DISPLAY[kind],
        credential_bearing=is_credential_bearing(kind),
    )
    for kind in EventKind
}
