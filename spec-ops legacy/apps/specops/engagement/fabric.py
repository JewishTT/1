"""The engagement fabric: an append-only, anonymisable event log (Feature 032).

Design constraints, and where each comes from
---------------------------------------------

**Append-only, immutable.** Constitution §I: an observation is immutable once recorded.
There is no update and no delete. "Correcting" an event is recording another one, which
is the only thing that keeps an assessment record defensible years later.

**Derived, never counted.** Constitution §III: every projection rebuilds from durable
events. So the funnel in :mod:`specops.engagement.funnel` is a pure fold over this log,
and a number on the board can always be re-derived to prove where it came from. The
department's earlier channels incremented counters in place, which means their totals
cannot be explained after the fact.

**Anonymous by construction.** The donor's best idea, and the reason its model scales
to a compliance regime: an event can be recorded with its subject link stripped and a
stable pseudonym left in its place. The event stays countable and groupable — "this
person engaged in three campaigns" survives — while ceasing to identify them. That is
what makes it possible to run an awareness programme and still honour a retention
window. :meth:`EngagementEvent.anonymize` implements it.

**Payloads are refused, not redacted.** ``SUBMITTED_DATA`` and ``STAGE_MATCHED`` are the
two credential-bearing events. They are recorded as *the fact that they happened* with
their stage, and the payload is dropped at the boundary with a stated kind — the same
shape as :mod:`specops.ghostline.redaction`, applied one level up. Refusing at the
boundary means no caller can bypass it by writing the file directly.

**Channels share one ladder.** An email click and a voice answer both land on
``Stage.ENGAGED``. That is the entire point of the module: the department's two channels
now produce one comparable number instead of two unrelated ones.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from specops.engagement.config import events_path
from specops.engagement.taxonomy import (
    DEFINITIONS,
    EventKind,
    EventTrack,
    Stage,
    position_in_funnel,
)

__all__ = (
    "EngagementEvent",
    "EngagementFabric",
    "fabric",
    "PayloadRefused",
)

_LOGGER = logging.getLogger(__name__)


class PayloadRefused(Exception):
    """A credential-bearing payload was offered. It is refused, not truncated.

    Truncation is the failure this avoids: a "redacted" payload that still carries the
    first four characters is still a credential, and the caller believes they were
    protected. Refusing means the caller gets an error and a decision to make.
    """

    def __init__(self, kind: EventKind) -> None:
        super().__init__(f"{kind.value} carries a payload this platform does not store")
        self.kind = kind


def _now() -> str:
    return datetime.now(UTC).isoformat()


#: The pseudonym key, resolved ONCE per process.
#:
#: This has to be stable for the whole process and not per call, or the pseudonym
#: stops being a pseudonym and becomes a fresh random id on every event — at which
#: point every subject looks like a different subject, the funnel's subject counts
#: inflate to the event count, and anonymisation silently destroys the numbers it was
#: supposed to preserve. That failure is quiet: the board still renders, it is just
#: wrong, and only a cross-campaign check catches it.
#:
#: Behaviour with no key configured: one random key per process. So a subject keeps one
#: pseudonym for the life of the process, and linkage is LOST across a restart. That is
#: the correct direction to fail — losing linkage never re-identifies anybody, whereas a
#: deterministic key derived from something guessable would. Set
#: ``GHOSTLINE_PSEUDONYM_KEY`` to keep linkage across restarts.
_PSEUDONYM_KEY: bytes = os.environ.get("GHOSTLINE_PSEUDONYM_KEY", "").encode("utf-8") or os.urandom(
    32
)


def _psuedonym_for(subject_ref: str) -> str:
    """A stable, non-reversible pseudonym for a subject reference.

    Not a hash: an unsalted digest of an email address is trivially reversed by anyone
    with a list of addresses, so a "pseudonymised" dataset built from one is still
    personal data. This is a keyed HMAC — the key never leaves the process, so the same
    subject always yields the same pseudonym and nobody outside can reverse it.

    The donor uses a random UUID stored alongside; this uses a keyed derivation because
    that survives the subject row being pruned, which is the case a retention window
    actually produces.
    """
    import hashlib
    import hmac

    digest = hmac.new(_PSEUDONYM_KEY, subject_ref.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"anon-{digest[:16]}"


@dataclass(frozen=True, slots=True)
class EngagementEvent:
    """One immutable observation about one subject's engagement."""

    event_id: str
    campaign_id: str
    #: ``"email"`` | ``"voice"`` | whatever a future channel calls itself.
    channel: str
    kind: EventKind
    occurred_at: str
    #: The subject this event is about. ``None`` once anonymised.
    subject_ref: str | None = None
    #: Stable pseudonym. Present from the start for an anonymised campaign, and left in
    #: place afterwards even when the link is stripped, so history survives.
    pseudonym: str | None = None
    #: The rung this event establishes. Denormalised from the taxonomy so a reader never
    #: has to join to know how deep the engagement went.
    stage: Stage = Stage.NONE
    track: EventTrack = EventTrack.PHISHING
    #: Declared payload. Refused outright for a credential-bearing event.
    payload: dict[str, Any] = field(default_factory=dict)
    #: Free-form context that is NOT subject-supplied content: stage names, call ids,
    #: playbook ids. Safe to keep, and the only kind of detail a caller may pass.
    metadata: dict[str, Any] = field(default_factory=dict)
    ip: str | None = None
    user_agent: str | None = None

    @property
    def anonymized(self) -> bool:
        """True when the event carries no subject link."""
        return self.subject_ref is None

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "campaign_id": self.campaign_id,
            "channel": self.channel,
            "kind": self.kind.value,
            "display": DEFINITIONS[self.kind].display,
            "occurred_at": self.occurred_at,
            "subject_ref": self.subject_ref,
            "pseudonym": self.pseudonym,
            "stage": int(self.stage),
            "track": self.track.value,
            "payload": self.payload,
            "metadata": self.metadata,
            "ip": self.ip,
            "user_agent": self.user_agent,
            "anonymized": self.anonymized,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> EngagementEvent:
        return cls(
            event_id=str(raw.get("event_id", "")),
            campaign_id=str(raw.get("campaign_id", "")),
            channel=str(raw.get("channel", "")),
            kind=EventKind(str(raw.get("kind", ""))),
            occurred_at=str(raw.get("occurred_at", "")),
            subject_ref=raw.get("subject_ref"),
            pseudonym=raw.get("pseudonym"),
            stage=Stage(int(raw.get("stage", 0))),
            track=EventTrack(str(raw.get("track", "phishing"))),
            payload=dict(raw.get("payload") or {}),
            metadata=dict(raw.get("metadata") or {}),
            ip=raw.get("ip"),
            user_agent=raw.get("user_agent"),
        )


class EngagementFabric:
    """The append-only log, with an in-memory index that rebuilds from the file.

    Same durability argument as the GhostLine ledger: the JSONL file is the record and
    the index is a projection of it, rebuilt and keyed on the resolved path so an index
    can never disagree with the file it came from.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[EngagementEvent] = []
        self._loaded = False
        self._loaded_path: Path | None = None

    @property
    def path(self) -> Path:
        return events_path()

    # ── lifecycle ──────────────────────────────────────────────────────

    def load(self) -> None:
        path = self.path
        if self._loaded and self._loaded_path == path:
            return
        if self._loaded and self._loaded_path != path:
            self._events = []
        self._loaded_path = path
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    self._events.append(EngagementEvent.from_dict(json.loads(line)))
                except (json.JSONDecodeError, KeyError, ValueError):
                    # A truncated tail from a crash mid-append. One bad line must not
                    # cost the operator the whole engagement history.
                    _LOGGER.warning("engagement: skipping unparseable event line in %s", path)
        self._loaded = True
        _LOGGER.info("engagement: loaded %d event(s) from %s", len(self._events), path)

    # ── writes ─────────────────────────────────────────────────────────

    def record(
        self,
        *,
        campaign_id: str,
        channel: str,
        kind: EventKind,
        subject_ref: str | None = None,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
        anonymized: bool = False,
    ) -> EngagementEvent:
        """Append one event.

        Order is load-bearing. The credential-bearing check happens BEFORE anything is
        constructed, so a refused payload never exists as an object a caller could
        hold — and before the file is touched, so a refusal leaves no trace at all.
        """
        definition = DEFINITIONS[kind]
        if definition.credential_bearing and payload:
            raise PayloadRefused(kind)

        self.load()
        event = EngagementEvent(
            event_id=str(uuid.uuid4()),
            campaign_id=campaign_id,
            channel=channel,
            kind=kind,
            occurred_at=_now(),
            subject_ref=None if anonymized else subject_ref,
            pseudonym=_psuedonym_for(subject_ref) if subject_ref else None,
            stage=position_in_funnel(kind),
            track=definition.track,
            payload=dict(payload or {}),
            metadata=dict(metadata or {}),
            ip=None if anonymized else ip,
            user_agent=None if anonymized else user_agent,
        )
        with self._lock:
            self._events.append(event)
            self._append(event)
        return event

    def anonymize_campaign(self, campaign_id: str) -> int:
        """Strip identity from every event of a campaign. Returns how many changed.

        Rewrites the file, which is the one place this fabric is not append-only — and
        deliberately so: the alternative is retaining personal data past its window,
        which is the failure this whole operation exists to avoid. The previous rows
        are not discarded, they are *replaced by their anonymised form*, and the count
        is returned so the caller can record that it happened.
        """
        self.load()
        changed: list[EngagementEvent] = []
        with self._lock:
            for index, event in enumerate(self._events):
                if event.campaign_id != campaign_id or event.anonymized:
                    continue
                self._events[index] = event.__class__(
                    event_id=event.event_id,
                    campaign_id=event.campaign_id,
                    channel=event.channel,
                    kind=event.kind,
                    occurred_at=event.occurred_at,
                    subject_ref=None,
                    pseudonym=event.pseudonym or _psuedonym_for(event.subject_ref or ""),
                    stage=event.stage,
                    track=event.track,
                    payload={},
                    metadata=event.metadata,
                    ip=None,
                    user_agent=None,
                )
                changed.append(self._events[index])
            if changed:
                self._rewrite()
        return len(changed)

    def _append(self, event: EngagementEvent) -> None:
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.as_dict(), ensure_ascii=False) + "\n")

    def _rewrite(self) -> None:
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".jsonl.tmp")
        tmp.write_text(
            "\n".join(json.dumps(e.as_dict(), ensure_ascii=False) for e in self._events)
            + ("\n" if self._events else ""),
            encoding="utf-8",
        )
        os.replace(tmp, path)

    # ── reads ──────────────────────────────────────────────────────────

    def all_events(self) -> tuple[EngagementEvent, ...]:
        self.load()
        with self._lock:
            return tuple(self._events)

    def for_campaign(self, campaign_id: str) -> tuple[EngagementEvent, ...]:
        return tuple(e for e in self.all_events() if e.campaign_id == campaign_id)

    def for_subject(self, subject_ref: str) -> tuple[EngagementEvent, ...]:
        """Every event about one subject, across every campaign.

        The cross-campaign view is the reason this fabric exists: it is what makes
        "repeat clicker" and "completed training twice" answerable without a report.
        """
        pseudonym = _psuedonym_for(subject_ref)
        return tuple(
            e for e in self.all_events() if e.subject_ref == subject_ref or e.pseudonym == pseudonym
        )

    def timeline(self, *, limit: int = 200) -> tuple[EngagementEvent, ...]:
        """Most recent first."""
        events = sorted(self.all_events(), key=lambda e: e.occurred_at, reverse=True)
        return tuple(events[: max(limit, 0)])

    def campaigns(self) -> tuple[str, ...]:
        return tuple(sorted({e.campaign_id for e in self.all_events()}))

    def channels(self) -> tuple[str, ...]:
        return tuple(sorted({e.channel for e in self.all_events()}))


_FABRIC = EngagementFabric()


def fabric() -> EngagementFabric:
    """The process-wide engagement fabric."""
    return _FABRIC


def _unused(_: Iterable[object]) -> None:  # pragma: no cover
    """Placeholder kept out of the public surface; see :mod:`specops.engagement.taxonomy`."""
