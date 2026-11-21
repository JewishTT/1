"""The GhostLine facade the router talks to, and the CLI-to-service translation.

Everything the donor's four CLI verbs could do is here, as served operations:

===================  =========================================================
``clone``            :meth:`Service.clone_voice` -- plus registering a premade id
``serve``            :meth:`Service.start_runtime` / :meth:`Service.stop_runtime`
``call``             :meth:`Service.dial` -- plus the RoE gate the CLI lacks
``analytics``        :meth:`Service.analytics` -- served, not written to a file
===================  =========================================================

Two verbs gain something the CLI could not express. ``clone`` gains a premade-voice
registration, because the donor tells free-tier operators to use a stock voice and
gives them no way to record the id they chose. ``analytics`` gains a served view,
because a CSV on disk is only readable by the operator who wrote it.

This module is the only place that composes the donor's pieces. The router calls
methods here and never touches the donor directly, which is what keeps the safety
ordering in one file: :meth:`Service.dial` checks the rules-of-engagement gate
*before* it can reach :mod:`specops.ghostline.telephony`, so no route can be
arranged to dial first and authorise afterwards.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from specops.ghostline.catalog import library
from specops.ghostline.config import get_config
from specops.ghostline.engine import simulate
from specops.ghostline.ledger import ledger
from specops.ghostline.loader import donor
from specops.ghostline.runtime import RuntimeController, runtime
from specops.ghostline.telephony import CallPlaced, DialBlocked, place_call
from specops.ghostline.voices import Voice, VoiceRegistry, VoiceUnavailable, voices

__all__ = ("Service",)

_LOGGER = logging.getLogger(__name__)


class GateRefused(Exception):
    """The rules-of-engagement gate refused. Carries the gate's own verdict.

    Distinct from :class:`DialBlocked` because the two mean different things to an
    operator and must read differently in the UI: a gate refusal is an authorisation
    fact, an operational block is a setup fact.
    """

    def __init__(self, code: str, reason: str, rejected: list[str] | None = None) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.rejected = rejected or []


class Service:
    """The GhostLine control surface, as operations.

    Deliberately a class rather than module functions: it holds the four registries,
    and a deployment that wants a scoped instance (a tenant with its own ledger, say)
    can construct one instead of reaching for a module global.
    """

    def __init__(
        self,
        *,
        library_ref: Any = None,
        voice_registry: VoiceRegistry | None = None,
        runtime_controller: RuntimeController | None = None,
        ledger_ref: Any = None,
    ) -> None:
        self.library = library_ref if library_ref is not None else library()
        self.voices = voice_registry if voice_registry is not None else voices()
        self.runtime = runtime_controller if runtime_controller is not None else runtime()
        self.ledger = ledger_ref if ledger_ref is not None else ledger()

    # ── status ─────────────────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        """Everything the runtime panel needs for one render.

        Assembled in one pass because the panel polls it: the donor report, the
        provider readiness checklist, the runtime descriptor and the catalogue
        validation errors are all part of the same question ("can I run an exercise
        right now, and if not, what is missing").
        """
        config = get_config()
        playbooks = self.library.summaries()
        voices = self.voices.list()
        return {
            "donor": donor().report(),
            "config": {
                "model": config.litellm_model,
                "litellm_api_base": config.litellm_api_base,
                "tts_model": config.elevenlabs_model,
                "stt_model": config.deepgram_model,
                "stt_language": config.deepgram_language,
                "samples_root": str(config.samples_root),
                "playbooks_root": str(config.playbooks_root),
                "ledger_path": str(config.calls_path),
                "log_level": config.log_level,
            },
            "providers": [p.as_dict() for p in config.readiness()],
            "blockers": list(config.blocking()),
            "runtime": self.runtime.state().as_dict(),
            "counts": {
                "playbooks": len(playbooks),
                "playbooks_valid": sum(1 for p in playbooks if p.valid),
                "voices": len(voices),
                "calls": len(self.ledger.calls(limit=10_000)),
            },
            "playbook_validation_errors": self.library.validation_errors(),
            "missing": list(self.missing()),
        }

    def missing(self) -> tuple[str, ...]:
        """Every named absence this deployment has, across every sub-surface."""
        out: list[str] = list(self.library.named_absences())
        out.extend(self.voices.named_absences())
        out.extend(self.ledger.named_absences())
        out.extend(self.runtime.state().missing)
        out.extend(self._dial_absences())
        return tuple(dict.fromkeys(out))

    def _dial_absences(self) -> tuple[str, ...]:
        out: list[str] = []
        if donor().get("ghostline.telephony.twilio") is None:
            out.append(
                "POST /specops/ghostline/calls (the donor's Twilio service needs the `twilio` "
                "package, not installed in the platform environment)"
            )
        return tuple(out)

    # ── playbooks (donor CLI: `--playbook` on `serve`) ─────────────────

    def playbooks(self) -> list[dict[str, Any]]:
        return [s.as_dict() for s in self.library.summaries()]

    def playbook(self, playbook_id: str) -> dict[str, Any] | None:
        entry = self.library.entry(playbook_id)
        if entry is None:
            return None
        return {
            "playbook": entry.summary.as_dict(),
            "stages": [s.as_dict() for s in entry.stages],
            "persona": _persona_view(entry.playbook),
            "defaults": _defaults_view(entry.playbook),
        }

    def reload_playbooks(self) -> int:
        return self.library.reload()

    def simulate(self, playbook_id: str, utterances: list[str]) -> dict[str, Any]:
        """Dry-run the donor's stage machine. Never dialled, never persisted."""
        return simulate(playbook_id, utterances).as_dict()

    # ── voices (donor CLI: `clone`) ────────────────────────────────────

    def list_voices(self) -> list[dict[str, Any]]:
        return [v.as_dict() for v in self.voices.list()]

    def register_voice(
        self,
        *,
        voice_id: str,
        name: str,
        origin: str = "premade",
        notes: str | None = None,
    ) -> Voice:
        """Record a voice id the operator already holds.

        This is the free-tier path the donor documents in prose: pick a stock voice
        from the provider's console, paste the id here, and the runtime can speak it.
        """
        cleaned = (voice_id or "").strip()
        if not cleaned:
            raise VoiceUnavailable("a voice_id is required")
        if origin not in ("premade", "cloned"):
            raise VoiceUnavailable(f"origin must be 'premade' or 'cloned'; got {origin!r}")
        return self.voices.register(
            voice_id=cleaned,
            name=(name or cleaned).strip(),
            origin=origin,
            notes=notes,
        )

    def clone_voice(
        self,
        *,
        name: str,
        sample_ref: str | None = None,
        sample_bytes: bytes | None = None,
        sample_filename: str | None = None,
    ) -> Voice:
        return self.voices.clone(
            name=name,
            sample_ref=sample_ref,
            sample_bytes=sample_bytes,
            sample_filename=sample_filename,
        )

    def forget_voice(self, voice_id: str, *, in_use_by: str | None = None) -> bool:
        if in_use_by:
            raise VoiceUnavailable(
                f"voice {voice_id} is pinned to the running runtime; stop the runtime first"
            )
        return self.voices.remove(voice_id)

    # ── runtime (donor CLI: `serve`) ───────────────────────────────────

    def start_runtime(
        self, *, voice_id: str, playbook_id: str, port: int | None = None
    ) -> dict[str, Any]:
        state = self.runtime.start(voice_id=voice_id, playbook_id=playbook_id, port=port)
        return state.as_dict()

    def stop_runtime(self) -> dict[str, Any]:
        return self.runtime.stop().as_dict()

    # ── dialling (donor CLI: `call`) ───────────────────────────────────

    def dial(
        self,
        *,
        target: str,
        campaign: str,
        persona: str,
        roe_id: str,
        approved_roster: list[str],
        playbook_id: str | None = None,
    ) -> dict[str, Any]:
        """Authorise, then place, then record. In that order.

        The gate is first because it is the only step that can refuse on
        authorisation grounds, and doing it first means an unrostered number never
        reaches a provider, a ledger or a runtime. ``capture_passwords`` is written
        as ``False`` on the record structurally -- there is no argument to pass that
        would change it.
        """
        from specops.roe.gate import REGISTRY as ROE
        from specops.roe.gate import capture_passwords_enabled
        from specops.roe.gate import launch_campaign as gate_launch

        number = target.strip()
        roe = ROE.get(roe_id)
        try:
            authorisation = gate_launch(
                roe=roe, targets=[number], approved_roster=list(approved_roster)
            )
        except Exception as exc:
            code = getattr(exc, "code", "RoEError")
            reason = getattr(exc, "reason", str(exc))
            rejected = list(getattr(exc, "rejected", []) or [])
            raise GateRefused(code, reason, rejected) from exc

        state = self.runtime.state()
        if state.state != "running" or not state.ws_url:
            raise DialBlocked(
                "the GhostLine runtime is not running, so there is no media stream for Twilio "
                "to dial back into. Start the runtime (voice + playbook) and try again."
            )

        call_id = f"gl-{uuid.uuid4().hex[:12]}"
        record = self.ledger.record_call(
            call_id=call_id,
            target=number,
            campaign=campaign,
            persona=persona,
            playbook_id=playbook_id or state.playbook_id,
            roe_id=roe_id,
            notes=f"authorised by {authorisation['roe_id']}",
        )

        placed: CallPlaced = place_call(target=number, stream_ws_url=state.ws_url)
        self.ledger.attach_sid(call_id, placed.sid)
        self.ledger.append_message(
            call_id,
            "operator",
            f"Call placed to {placed.to_number} from {placed.from_number}",
            playbook_id=record.playbook_id,
        )
        _LOGGER.info(
            "ghostline: placed %s -> %s (campaign=%s, rostered)",
            placed.sid,
            placed.to_number,
            campaign,
        )
        return {
            "call": record.as_dict(),
            "placed": {
                "sid": placed.sid,
                "to_number": placed.to_number,
                "from_number": placed.from_number,
                "ws_url": placed.ws_url,
            },
            "authorisation": authorisation,
            "capture_passwords": capture_passwords_enabled(),
            "credentials_captured": 0,
        }

    def complete_call(
        self, call_id: str, outcome: str, *, notes: str | None = None
    ) -> dict[str, Any]:
        if outcome not in ("compromised", "abandoned", "in_progress", "no_answer"):
            raise DialBlocked(
                "outcome must be one of compromised, abandoned, in_progress, no_answer; "
                f"got {outcome!r}"
            )
        call = self.ledger.complete_call(call_id, outcome, notes=notes)
        return call.as_dict()

    def log_turn(
        self,
        call_id: str,
        *,
        role: str,
        content: str,
        stage: str | None = None,
        playbook_id: str | None = None,
        sentiment_score: float | None = None,
        interest_level: float | None = None,
        objection_type: str | None = None,
        trigger_used: str | None = None,
    ) -> dict[str, Any]:
        """Append a turn to a call. Content is redacted on the way in."""
        message = self.ledger.append_message(
            call_id,
            role,
            content,
            stage=stage,
            playbook_id=playbook_id,
            sentiment_score=sentiment_score,
            interest_level=interest_level,
            objection_type=objection_type,
            trigger_used=trigger_used,
        )
        return message.as_dict()

    # ── analytics (donor CLI: `analytics`) ─────────────────────────────

    def analytics(self, *, campaign: str | None = None) -> dict[str, Any]:
        return self.ledger.analytics(campaign=campaign)

    def calls(self, *, limit: int = 50) -> list[dict[str, Any]]:
        return [c.as_dict() for c in self.ledger.calls(limit=limit)]

    def call(self, call_id: str) -> dict[str, Any] | None:
        record = self.ledger.call(call_id)
        if record is None:
            return None
        return {**record.as_dict(), "messages": [m.as_dict() for m in record.messages]}

    def analytics_export(self, *, campaign: str | None = None, fmt: str = "csv") -> dict[str, Any]:
        """The donor's ``analytics`` export, served rather than written.

        The donor writes a file and prints a path. Here the rows are returned so the
        UI can offer a download, and the CSV is generated from the same aggregate the
        dashboard renders -- so what an operator exports is what they saw.
        """
        summary = self.ledger.analytics(campaign=campaign)
        if fmt not in ("csv", "json"):
            raise DialBlocked(f"format must be 'csv' or 'json'; got {fmt!r}")
        rows: list[tuple[str, object]] = [("metric", "value")]
        for key in (
            "call_count",
            "completed_count",
            "in_progress_count",
            "turn_count",
            "conversion_rate",
        ):
            rows.append((key, summary.get(key)))
        for stage, count in (summary.get("stage_counts") or {}).items():
            rows.append((f"stage_{stage}", count))
        for outcome, count in (summary.get("outcomes") or {}).items():
            rows.append((f"outcome_{outcome}", count))
        rows.append(("capture_passwords", "false"))
        rows.append(("credentials_captured", summary.get("credentials_captured", 0)))

        if fmt == "json":
            return {"format": "json", "filename": "ghostline-analytics.json", "payload": summary}
        import csv
        import io

        buffer = io.StringIO()
        csv.writer(buffer).writerows(rows)
        return {
            "format": "csv",
            "filename": "ghostline-analytics.csv",
            "payload": buffer.getvalue(),
        }


# ── playbook projections ──────────────────────────────────────────────


def _persona_view(playbook: Any) -> dict[str, Any] | None:
    if playbook is None or getattr(playbook, "persona", None) is None:
        return None
    persona = playbook.persona
    return {
        "name": persona.name,
        "background": persona.background,
        "voice": persona.voice,
        "persuasion_principles": list(persona.persuasion_principles),
        "do": list(persona.do),
        "dont": list(persona.dont),
    }


def _defaults_view(playbook: Any) -> dict[str, Any] | None:
    if playbook is None or getattr(playbook, "defaults", None) is None:
        return None
    defaults = playbook.defaults.model_dump()
    return {str(k): v for k, v in defaults.items()}


_SERVICE = Service()
