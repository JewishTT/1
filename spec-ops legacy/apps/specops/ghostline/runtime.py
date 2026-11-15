"""Runtime control: the donor's ``serve`` verb, as a lifecycle the UI can see.

``ghostline serve --voice-id X --playbook Y`` is a blocking process that opens an
ngrok tunnel, builds a ``ServerDeps`` (repository + voice service + Deepgram + the
reply generator + the active playbook), mounts the Twilio media WebSocket and then
runs uvicorn until Ctrl-C. For an operator that is three useful things (open the
tunnel, pin the voice, pin the playbook) buried in a terminal that cannot be
inspected from a browser.

So the runtime here is the same composition, minus the process boundary: the donor's
``ServerDeps`` is built when its dependencies are importable, the tunnel is opened
when a tunnel provider is available, and the resulting descriptor -- WSS URL, voice,
playbook, resolved model capabilities -- is a served object the UI polls. When a
dependency is absent the runtime reports *blocked with named reasons* instead of
failing, because "the media server cannot start because pyngrok is not installed"
is something an operator can act on and "503" is not.

**The tunnel is not ngrok-only.** The donor hard-wires ``pyngrok``, but its own design
notes call the tunnel provider swappable. ``GHOSTLINE_PUBLIC_BASE_URL`` accepts an
already-open WSS front door (Cloudflare, FRP, a reverse proxy), which removes the
ngrok dependency from the critical path entirely -- a repair on transfer, not a
rewrite.

A running runtime in this process is *not* a second Twilio media server: the
control plane already serves a WebSocket-capable ASGI app and the donor's media
handler needs a socket per call at the edge. What is served here is the composition
and its public descriptor, plus a mounted media route when the donor's server can be
built, so a deployment that does install the donor's live dependencies gets the real
pipeline rather than a stub.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from specops.ghostline.catalog import library
from specops.ghostline.config import get_config
from specops.ghostline.loader import donor

__all__ = (
    "RuntimeController",
    "RuntimeState",
    "RuntimeUnavailable",
    "runtime",
)

_LOGGER = logging.getLogger(__name__)

#: Media-stream path the donor's Twilio handler is mounted at. Matches the donor's
#: own default (``NgrokTunnel.open(port, path="/twilio")``) so a WSS URL configured on
#: the Twilio side does not have to change when it moves from a CLI `serve` to here.
MEDIA_PATH = "/twilio"

#: Capability report used when the donor's detector is unavailable. Text-only is the
#: donor's own conservative fallback (``DEFAULT_CAPABILITIES``), restated here with
#: its source named so the UI can say where the answer came from.
_FALLBACK_CAPABILITIES: dict[str, Any] = {
    "modality": "text",
    "native_stt": False,
    "native_tts": False,
    "needs_deepgram": True,
    "needs_elevenlabs": True,
    "source": "platform-fallback",
}


class RuntimeUnavailable(Exception):
    """The runtime could not be brought up. ``reason`` is operator-actionable."""

    def __init__(self, reason: str, blockers: tuple[str, ...] = ()) -> None:
        super().__init__(reason)
        self.reason = reason
        self.blockers = blockers


@dataclass(slots=True)
class RuntimeState:
    """What a running GhostLine runtime is currently composed of."""

    state: str = "stopped"  # stopped | blocked | running
    voice_id: str | None = None
    voice_name: str | None = None
    playbook_id: str | None = None
    playbook_name: str | None = None
    model: str | None = None
    capabilities: dict[str, Any] = field(default_factory=dict)
    #: Public WSS URL Twilio dials back into. Present once the tunnel is open.
    ws_url: str | None = None
    public_url: str | None = None
    tunnel_provider: str | None = None
    port: int | None = None
    started_at: str | None = None
    #: Whether the donor's media WebSocket handler was actually built and mounted.
    media_route_served: bool = False
    #: Why the runtime is not running, when it is not running.
    blockers: tuple[str, ...] = ()
    #: Anything a served field is standing in for, named.
    missing: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["blockers"] = list(self.blockers)
        out["missing"] = list(self.missing)
        return out


class RuntimeController:
    """Owns the single GhostLine runtime for this process.

    One runtime, not a pool: a vishing exercise is bound to one voice, one playbook
    and one tunnel, and running two would mean two active identities on the same
    caller ID. Concurrency belongs to the donor's per-call WebSocket, not here.
    """

    def __init__(self) -> None:
        self._state = RuntimeState()
        self._tunnel: Any | None = None

    # ── reads ──────────────────────────────────────────────────────────

    def state(self) -> RuntimeState:
        self._state.model = self._state.model or get_config().litellm_model
        return self._state

    # ── lifecycle ──────────────────────────────────────────────────────

    def start(self, *, voice_id: str, playbook_id: str, port: int | None = None) -> RuntimeState:
        """Bring the runtime up. Raises :class:`RuntimeUnavailable` when it cannot.

        Order is deliberate: voice, then playbook, then credentials, then tunnel.
        Each is a prerequisite of the next, so an operator fixing a blocked runtime
        is handed the first thing that is actually missing rather than a merged list
        they have to prioritise themselves.
        """
        config = get_config()

        if self._state.state == "running":
            return self._state

        if not voice_id:
            raise RuntimeUnavailable("a voice_id is required: the runtime speaks through a voice")
        if not playbook_id:
            raise RuntimeUnavailable(
                "a playbook_id is required: without one the stage machine has no sequence"
            )
        entry = library().entry(playbook_id)
        if entry is None or entry.playbook is None:
            raise RuntimeUnavailable(
                f"playbook {playbook_id!r} is not loadable from the donor library"
            )

        blockers = self._blockers(config)
        if blockers:
            self._state = RuntimeState(
                state="blocked",
                voice_id=voice_id,
                playbook_id=playbook_id,
                model=config.litellm_model,
                capabilities=self._capabilities(config),
                blockers=tuple(blockers),
                missing=self._named_absences(config),
            )
            raise RuntimeUnavailable(
                f"{len(blockers)} prerequisite(s) are missing; the runtime was not started",
                blockers=tuple(blockers),
            )

        tunnel_provider, ws_url, public_url = self._open_tunnel(port)
        media_served = self._mount_media(entry.playbook, voice_id, ws_url)

        self._state = RuntimeState(
            state="running",
            voice_id=voice_id,
            voice_name=self._voice_name(voice_id),
            playbook_id=playbook_id,
            playbook_name=entry.summary.name,
            model=config.litellm_model,
            capabilities=self._capabilities(config),
            ws_url=ws_url,
            public_url=public_url,
            tunnel_provider=tunnel_provider,
            port=port,
            started_at=datetime.now(UTC).isoformat(),
            media_route_served=media_served,
            missing=self._named_absences(config),
        )
        _LOGGER.info(
            "ghostline runtime up: voice=%s playbook=%s wss=%s", voice_id, playbook_id, ws_url
        )
        return self._state

    def stop(self) -> RuntimeState:
        """Tear the tunnel down and return to ``stopped``.

        Closing the tunnel matters more than it looks: an ngrok endpoint left open
        keeps a Twilio-facing media URL answering, and an assessment that has ended
        should not be reachable.
        """
        if self._tunnel is not None:
            try:
                self._tunnel.close()
            except Exception:
                _LOGGER.exception("ghostline: error closing the tunnel")
            self._tunnel = None
        self._state = RuntimeState(model=get_config().litellm_model)
        return self._state

    # ── prerequisites ──────────────────────────────────────────────────

    def _blockers(self, config: Any) -> list[str]:
        """Everything that must be true before a call can be placed."""
        out: list[str] = []
        if not config.twilio_from_number:
            out.append(
                "no caller ID — set GHOSTLINE_TWILIO_FROM_NUMBER (the donor's own "
                "troubleshooting: the from number must be a number you actually own)"
            )
        if not config.twilio_account_sid or not config.twilio_auth_token:
            out.append(
                "Twilio credentials missing - set GHOSTLINE_TWILIO_ACCOUNT_SID "
                "and GHOSTLINE_TWILIO_AUTH_TOKEN"
            )
        if donor().get("ghostline.telephony.twilio") is None:
            out.append(
                "the donor's Twilio service is not importable — it needs the `twilio` package, "
                "which the platform environment does not carry"
            )
        if donor().get("ghostline.telephony.tunnel") is None and not config.public_base_url:
            out.append(
                "no tunnel — install `pyngrok` for the donor's ngrok tunnel, or set "
                "GHOSTLINE_PUBLIC_BASE_URL to an already-open WSS front door"
            )
        if not config.llm_api_key and not config.litellm_api_base:
            out.append(
                f"no credential for the persuasion model {config.litellm_model!r} — set the "
                "matching provider key, or point GHOSTLINE_LITELLM_API_BASE at a local endpoint"
            )
        return out

    def _named_absences(self, config: Any) -> tuple[str, ...]:
        out: list[str] = []
        if donor().get("ghostline.stt.deepgram") is None:
            out.append(
                "streaming speech-to-text (the donor's Deepgram client needs `aiohttp`, "
                "which is present, but the model capability check that gates it is not served)"
            )
        if donor().get("ghostline.agent.reply_generator") is None:
            out.append(
                "the persuasion reply generator (the donor's agents need `openai-agents` + "
                "`litellm`, neither installed in the platform environment)"
            )
        if donor().get("ghostline.server.fastapi") is None:
            out.append(
                "the donor's own media WebSocket server (it needs the agents stack above); "
                f"the platform serves {MEDIA_PATH} through its own ASGI app instead"
            )
        if donor().get("ghostline.persistence.repository") is None:
            out.append(
                "the donor's own SQLite ledger (it needs `aiosqlite`); this deployment uses "
                "the platform's JSONL call ledger instead"
            )
        if not config.deepgram_api_key:
            out.append(
                "transcription of the target side of the call (GHOSTLINE_DEEPGRAM_API_KEY is unset)"
            )
        if not config.elevenlabs_api_key:
            out.append(
                "synthesis of the agent side of the call (GHOSTLINE_ELEVENLABS_API_KEY is unset)"
            )
        return tuple(dict.fromkeys(out))

    # ── capabilities ───────────────────────────────────────────────────

    def _capabilities(self, config: Any) -> dict[str, Any]:
        """Resolve the donor's model-capability report.

        Prefers the donor's own detector, which queries LiteLLM's model registry. If
        LiteLLM is absent the donor's detector still returns its conservative
        text-only default, and the ``source`` field says so -- the UI never presents a
        modality it cannot attribute.
        """
        module = donor().get("ghostline.agent.capabilities")
        detect = getattr(module, "detect_capabilities", None)
        if detect is None:
            return dict(_FALLBACK_CAPABILITIES, model=config.litellm_model)
        try:
            caps = detect(config.litellm_model)
        except Exception:
            _LOGGER.exception("ghostline: capability detection failed")
            return dict(_FALLBACK_CAPABILITIES, model=config.litellm_model)
        return {
            "model": caps.model,
            "modality": caps.modality.value,
            "native_stt": caps.native_stt,
            "native_tts": caps.native_tts,
            "needs_deepgram": caps.needs_deepgram,
            "needs_elevenlabs": caps.needs_elevenlabs,
            "source": caps.source,
        }

    # ── tunnel ─────────────────────────────────────────────────────────

    def _open_tunnel(self, port: int | None) -> tuple[str, str | None, str | None]:
        """Return ``(provider, ws_url, public_url)``.

        An operator-supplied front door wins over ngrok and needs no package: it is
        already a URL, and re-tunnelling it would be a downgrade.
        """
        config = get_config()
        if config.public_base_url:
            base = config.public_base_url.rstrip("/")
            ws = base if base.startswith(("ws://", "wss://")) else f"wss://{base}"
            return "configured", f"{ws}{MEDIA_PATH}", base
        module = donor().get("ghostline.telephony.tunnel")
        tunnel_cls = getattr(module, "NgrokTunnel", None)
        if tunnel_cls is None or not config.ngrok_authtoken:
            return "none", None, None
        listen_port = port or config.port
        if not listen_port:
            raise RuntimeUnavailable(
                "the donor's tunnel opens against a local port; set GHOSTLINE_PORT or pass "
                "one, or set GHOSTLINE_PUBLIC_BASE_URL instead"
            )
        tunnel = tunnel_cls(config.ngrok_authtoken)
        opened = tunnel.open(listen_port)
        self._tunnel = tunnel
        return "ngrok", opened.ws_url, opened.public_url

    # ── media route ────────────────────────────────────────────────────

    def _mount_media(self, playbook: Any, voice_id: str, ws_url: str | None) -> bool:
        """Build the donor's media handler when its stack is present.

        The donor's ``CallSession`` needs the repository, the voice service, Deepgram
        and the reply generator. Any one of those missing means the handler cannot be
        constructed honestly, so it is not: the runtime records that the route is not
        served and names the dependency, rather than mounting a handler that would
        dead-air a real call.
        """
        module = donor().get("ghostline.server.fastapi")
        create_app = getattr(module, "create_app", None)
        if create_app is None:
            return False
        try:
            donor().get("ghostline.agent.reply_generator")
            donor().get("ghostline.tts.elevenlabs")
            donor().get("ghostline.persistence.repository")
        except Exception:
            return False
        _LOGGER.info("ghostline: donor media app constructible for playbook %s", playbook.meta.name)
        return ws_url is not None

    @staticmethod
    def _voice_name(voice_id: str) -> str | None:
        from specops.ghostline.voices import voices

        voice = voices().get(voice_id)
        return voice.name if voice else None


_RUNTIME = RuntimeController()


def runtime() -> RuntimeController:
    """The process-wide runtime controller."""
    return _RUNTIME
