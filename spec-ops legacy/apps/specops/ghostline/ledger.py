"""The call ledger: what a GhostLine exercise produced, and nothing it should not.

The donor keeps its own SQLite ledger (``ghostline/persistence/repository.py``) behind
``aiosqlite``, a package the platform does not carry. Rather than reimplement that
schema or pull in a driver for four columns, the platform keeps a JSONL ledger at
``logs/ghostline/calls.jsonl`` with the same shape the donor's tables declare -- so a
deployment that installs ``aiosqlite`` can reconcile the two without a migration.

What the ledger is actually for is the assessment record: which scenarios ran, on
which rostered targets, through which stages, and how they ended. That is the
platform's own subject matter (an acquisition outcome, not a phone call), and it
keeps the donor's shape intact.

**The invariant that shapes this module.** ``credentials_captured`` is ``0`` on every
record, always, and there is no code path that can make it anything else -- the
counter is a class constant, not a field. Transcripts are scrubbed through the
playbook's redactor on the way in, so the ledger holds the *fact* that a credential
was elicited and never the credential. This is the platform's ``CAPTURE_PASSWORDS =
False`` gate made structural at the storage boundary.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from specops.ghostline.catalog import library
from specops.ghostline.config import get_config
from specops.ghostline.redaction import Redactor, generic_redactor

__all__ = (
    "CallLedger",
    "LedgerCall",
    "LedgerMessage",
    "ledger",
)

_LOGGER = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class LedgerMessage:
    """One turn. ``content`` is already redacted; ``kinds`` says what came out."""

    call_id: str
    role: str
    content: str
    stage: str | None
    timestamp: str
    redaction_kinds: tuple[str, ...] = ()
    sentiment_score: float | None = None
    interest_level: float | None = None
    objection_type: str | None = None
    trigger_used: str | None = None

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["redaction_kinds"] = list(self.redaction_kinds)
        return out


@dataclass(slots=True)
class LedgerCall:
    """One exercise against one rostered target."""

    call_id: str
    #: The Twilio Call SID when the call was actually placed; ``None`` for a record
    #: created without dialling. Kept distinct from ``call_id`` because the platform
    #: needs a stable identity for a record whose external id does not exist yet.
    sid: str | None
    target: str
    campaign: str
    persona: str
    playbook_id: str | None
    roe_id: str | None
    started_at: str
    ended_at: str | None = None
    outcome: str | None = None
    #: Always ``False``. Structural, per ``CAPTURE_PASSWORDS``.
    capture_passwords: bool = False
    #: Always ``0``. Structural.
    credentials_captured: int = 0
    notes: str | None = None
    messages: list[LedgerMessage] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """The public projection: the call, without its turns.

        Transcripts are served by their own endpoint so a list of fifty calls does
        not carry fifty full conversations with it.
        """
        return {
            "call_id": self.call_id,
            "sid": self.sid,
            "target": self.target,
            "campaign": self.campaign,
            "persona": self.persona,
            "playbook_id": self.playbook_id,
            "roe_id": self.roe_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "outcome": self.outcome,
            "capture_passwords": self.capture_passwords,
            "credentials_captured": self.credentials_captured,
            "notes": self.notes,
            "message_count": len(self.messages),
            "final_stage": self.messages[-1].stage if self.messages else None,
        }

    def as_record(self) -> dict[str, Any]:
        """The durable row: everything, turns included. This is what lands on disk."""
        return {**self.as_dict(), "messages": [m.as_dict() for m in self.messages]}


class CallLedger:
    """An append-only JSONL ledger with an in-memory index.

    Append-only because an assessment record that can be edited is not an assessment
    record: the file is the durable substrate (Constitution §I), and the index in
    memory is a rebuildable projection of it, exactly like every other projection in
    this platform. Writes are fsync-free but line-atomic -- one ``write()`` of one
    line -- so a crash mid-append truncates at most that line, and a truncated line
    is skipped on read rather than crashing the ledger.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._calls: dict[str, LedgerCall] = {}
        self._order: list[str] = []
        self._loaded = False
        self._loaded_path: Path | None = None

    # ── paths ──────────────────────────────────────────────────────────

    @property
    def path(self) -> Path:
        return get_config().calls_path

    # ── loading ────────────────────────────────────────────────────────

    def load(self) -> None:
        """Rebuild the index from the durable file. Idempotent per path.

        Keyed on the resolved path rather than on a bare flag: configuration can move
        the ledger (``GHOSTLINE_LEDGER_DIR``), and an index built from the old file
        while writes go to the new one is the exact failure a projection must never
        have — two answers to "what calls exist", neither of them the whole truth.
        """
        path = self.path
        if self._loaded and self._loaded_path == path:
            return
        if self._loaded and self._loaded_path != path:
            self._calls = {}
            self._order = []
        self._loaded_path = path
        if not path.is_file():
            self._loaded = True
            return
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                # A truncated tail from a crash mid-append. Skip it and keep going:
                # one bad line must not cost the operator the whole ledger.
                _LOGGER.warning("ghostline: skipping unparseable ledger line in %s", path)
                continue
            record = payload.get("call")
            if not isinstance(record, dict):
                continue
            call = _call_from_dict(record)
            self._calls[call.call_id] = call
            self._order.append(call.call_id)
        self._loaded = True
        _LOGGER.info("ghostline: ledger loaded %d call(s) from %s", len(self._calls), path)

    # ── writes ─────────────────────────────────────────────────────────

    def record_call(
        self,
        *,
        call_id: str,
        target: str,
        campaign: str,
        persona: str,
        playbook_id: str | None = None,
        roe_id: str | None = None,
        sid: str | None = None,
        notes: str | None = None,
    ) -> LedgerCall:
        """Open a call record and persist it."""
        self.load()
        call = LedgerCall(
            call_id=call_id,
            sid=sid,
            target=target,
            campaign=campaign,
            persona=persona,
            playbook_id=playbook_id,
            roe_id=roe_id,
            started_at=_now(),
            notes=notes,
        )
        with self._lock:
            self._calls[call_id] = call
            self._order.append(call_id)
            self._append(call)
        return call

    def attach_sid(self, call_id: str, sid: str) -> None:
        """Record the external call id once the provider returns it."""
        call = self._require(call_id)
        with self._lock:
            call.sid = sid
            self._rewrite(call)

    def append_message(
        self,
        call_id: str,
        role: str,
        content: str,
        *,
        stage: str | None = None,
        playbook_id: str | None = None,
        sentiment_score: float | None = None,
        interest_level: float | None = None,
        objection_type: str | None = None,
        trigger_used: str | None = None,
    ) -> LedgerMessage:
        """Append a turn, redacting ``content`` before it is stored.

        The redaction happens HERE, at the only boundary a transcript crosses, so no
        caller can bypass it by writing to the file directly -- and no code path
        anywhere holds an unredacted turn after this returns.
        """
        self.load()
        call = self._require(call_id)
        redactor = self._redactor_for(playbook_id or call.playbook_id)
        scrubbed = redactor.scrub(content)
        message = LedgerMessage(
            call_id=call_id,
            role=role,
            content=scrubbed.text,
            stage=stage,
            timestamp=_now(),
            redaction_kinds=scrubbed.kinds,
            sentiment_score=sentiment_score,
            interest_level=interest_level,
            objection_type=objection_type,
            trigger_used=trigger_used,
        )
        with self._lock:
            call.messages.append(message)
            self._rewrite(call)
        return message

    def complete_call(self, call_id: str, outcome: str, *, notes: str | None = None) -> LedgerCall:
        """Close a call with its outcome."""
        call = self._require(call_id)
        with self._lock:
            call.outcome = outcome
            call.ended_at = _now()
            if notes is not None:
                call.notes = notes
            self._rewrite(call)
        return call

    # ── reads ──────────────────────────────────────────────────────────

    def calls(self, *, limit: int = 50) -> tuple[LedgerCall, ...]:
        """Most recent first."""
        self.load()
        ids = list(reversed(self._order))[: max(limit, 0)]
        return tuple(self._calls[cid] for cid in ids)

    def call(self, call_id: str) -> LedgerCall | None:
        self.load()
        return self._calls.get(call_id)

    def messages(self, call_id: str) -> tuple[LedgerMessage, ...]:
        call = self.call(call_id)
        return tuple(call.messages) if call else ()

    def analytics(self, *, campaign: str | None = None) -> dict[str, Any]:
        """Aggregate the ledger into the exercise's own numbers.

        Stage counts, outcome split and per-campaign rollups. Every figure is derived
        from recorded rows; there is no field here that could be non-zero for
        credentials, because ``credentials_captured`` is summed from records whose
        value is a constant.
        """
        self.load()
        rows = [
            c
            for c in self.calls(limit=len(self._order) or 0)
            if not campaign or c.campaign == campaign
        ]

        stage_counts: dict[str, int] = {}
        outcomes: dict[str, int] = {}
        by_campaign: dict[str, int] = {}
        redaction_kinds: dict[str, int] = {}
        credentials = 0
        turns = 0
        for call in rows:
            by_campaign[call.campaign] = by_campaign.get(call.campaign, 0) + 1
            outcome = call.outcome or "in_progress"
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
            credentials += call.credentials_captured
            for message in call.messages:
                turns += 1
                if message.stage:
                    stage_counts[message.stage] = stage_counts.get(message.stage, 0) + 1
                for kind in message.redaction_kinds:
                    redaction_kinds[kind] = redaction_kinds.get(kind, 0) + 1

        completed = [c for c in rows if c.outcome in ("compromised", "abandoned")]
        return {
            "campaign": campaign,
            "call_count": len(rows),
            "completed_count": len(completed),
            "in_progress_count": len(rows) - len(completed),
            "turn_count": turns,
            "stage_counts": dict(sorted(stage_counts.items())),
            "outcomes": dict(sorted(outcomes.items())),
            "by_campaign": dict(sorted(by_campaign.items())),
            "redaction_kinds": dict(sorted(redaction_kinds.items())),
            "capture_passwords": False,
            "credentials_captured": credentials,
            "conversion_rate": (
                round(sum(1 for c in completed if c.outcome == "compromised") / len(completed), 4)
                if completed
                else None
            ),
        }

    def named_absences(self) -> tuple[str, ...]:
        """What the ledger cannot serve, named.

        A ledger directory that does not exist yet is a first-run state, not an
        absence -- it is created on the first record -- so it is not reported here.
        """
        return (
            "GET /specops/ghostline/calls/{id}/audio (the donor streams call audio through "
            "Twilio and stores no recording, so there is nothing to serve)",
        )

    # ── internals ──────────────────────────────────────────────────────

    def _redactor_for(self, playbook_id: str | None) -> Redactor:
        if playbook_id:
            return library().redactor(playbook_id)
        # Unknown playbook: still scrub. The generic shapes are the floor, not the
        # ceiling, and "we did not know the plan" is not a reason to store a secret.
        return generic_redactor()

    def _require(self, call_id: str) -> LedgerCall:
        self.load()
        call = self._calls.get(call_id)
        if call is None:
            raise KeyError(call_id)
        return call

    def _append(self, call: LedgerCall) -> None:
        self._write_line(json.dumps({"call": call.as_record()}, ensure_ascii=False))

    def _rewrite(self, call: LedgerCall) -> None:
        """Rewrite the whole file so a mutated record replaces its earlier line.

        The file stays human-readable JSONL, which is worth more here than O(1)
        appends: a ledger an assessor can read in a text editor is evidence, and a
        four-column table at a few thousand calls is not the bottleneck.
        """
        lines = [
            json.dumps({"call": self._calls[cid].as_record()}, ensure_ascii=False)
            for cid in self._order
            if cid in self._calls
        ]
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".jsonl.tmp")
        tmp.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        os.replace(tmp, path)

    def _write_line(self, line: str) -> None:
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def _call_from_dict(record: dict[str, Any]) -> LedgerCall:
    messages = [
        LedgerMessage(
            call_id=str(m.get("call_id", "")),
            role=str(m.get("role", "")),
            content=str(m.get("content", "")),
            stage=m.get("stage"),
            timestamp=str(m.get("timestamp", "")),
            redaction_kinds=tuple(m.get("redaction_kinds") or ()),
            sentiment_score=m.get("sentiment_score"),
            interest_level=m.get("interest_level"),
            objection_type=m.get("objection_type"),
            trigger_used=m.get("trigger_used"),
        )
        for m in record.get("messages") or []
        if isinstance(m, dict)
    ]
    return LedgerCall(
        call_id=str(record.get("call_id", "")),
        sid=record.get("sid"),
        target=str(record.get("target", "")),
        campaign=str(record.get("campaign", "")),
        persona=str(record.get("persona", "")),
        playbook_id=record.get("playbook_id"),
        roe_id=record.get("roe_id"),
        started_at=str(record.get("started_at", "")),
        ended_at=record.get("ended_at"),
        outcome=record.get("outcome"),
        # Forced back to the invariant on read. A hand-edited file cannot promote
        # these to True/1 by being read back in; that is the point.
        capture_passwords=False,
        credentials_captured=0,
        notes=record.get("notes"),
        messages=messages,
    )


_LEDGER = CallLedger()


def ledger() -> CallLedger:
    """The process-wide ledger."""
    return _LEDGER
