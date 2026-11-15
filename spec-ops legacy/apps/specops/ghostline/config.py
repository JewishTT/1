"""GhostLine configuration, read from the platform's environment.

The donor loads ``.env`` from the process working directory through
``pydantic-settings`` (``ghostline/settings.py``). Adopting that here would mean the
control plane silently inherited a donor-local secrets file from whatever directory
it was launched in, which is exactly the secret-isolation failure Constitution §VII
forbids. So the platform reads its own ``GHOSTLINE_*`` variables and constructs the
donor's settings object explicitly when one is genuinely needed.

Two rules shape everything below:

1. **A secret is never echoed.** Every provider reports ``configured: true/false``
   and the env var that would configure it. There is no accessor that returns a
   secret, so no router can leak one into a response, a log line or a UI.
2. **Absent is named.** A provider without a credential is ``configured: false``
   with the variable to set -- never a fabricated "ready", because the UI's job
   here is to tell the operator exactly what is left to do.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from specops.ghostline.loader import DONOR_ASSETS, DONOR_PLAYBOOKS, REPO_ROOT

__all__ = (
    "GhostlineConfig",
    "ProviderReadiness",
    "clear_config_cache",
    "get_config",
)

#: Default ledger location. The donor defaults to ``sales_tracking.db`` in the CWD,
#: which for a long-running API is whichever directory uvicorn was started in. The
#: platform pins it under the workspace's ``logs/`` instead.
_DEFAULT_LEDGER = REPO_ROOT / "logs" / "ghostline"

#: Upper bound on an uploaded voice sample. The donor's own clone path takes a local
#: file with no size check; a browser upload needs one (Constitution §VII: limits on
#: size, count and depth for anything arriving from outside).
_MAX_SAMPLE_BYTES = 25 * 1024 * 1024

#: Sample formats the donor's reader actually handles: WAV natively, M4A via
#: pydub/ffmpeg. Anything else is refused by name rather than half-decoded.
_ALLOWED_SAMPLE_SUFFIXES = (".wav", ".m4a")


@dataclass(frozen=True, slots=True)
class ProviderReadiness:
    """Whether one external provider is usable, and what would make it so."""

    name: str
    configured: bool
    env_var: str
    detail: str

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "configured": self.configured,
            "env_var": self.env_var,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class GhostlineConfig:
    """The platform's view of a GhostLine deployment.

    ``phone_number`` is the single most sensitive field in the donor -- it is the
    operator's own PSTN identity, and the donor README says so. It is held here so
    readiness can report it, and it is the one field the adapter refuses to render
    into a view model.
    """

    # Twilio (PSTN + Media Streams)
    twilio_account_sid: str | None
    twilio_auth_token: str | None
    twilio_from_number: str | None
    # Deepgram (STT)
    deepgram_api_key: str | None
    deepgram_model: str
    deepgram_language: str
    # ElevenLabs (TTS + cloning)
    elevenlabs_api_key: str | None
    elevenlabs_model: str
    # LiteLLM (the persuasion model, provider-agnostic)
    litellm_model: str
    litellm_api_base: str | None
    openai_api_key: str | None
    anthropic_api_key: str | None
    gemini_api_key: str | None
    # Tunnel. ``public_base_url`` is the platform's escape hatch: the donor hard-wires
    # ngrok, but its own design notes say the tunnel provider is swappable, so a
    # self-hosted Cloudflare/FRP front door needs no pyngrok at all.
    ngrok_authtoken: str | None
    public_base_url: str | None
    # Runtime knobs
    ledger_dir: Path
    samples_root: Path
    playbooks_root: Path
    host: str
    port: int
    log_level: str
    max_sample_bytes: int = _MAX_SAMPLE_BYTES
    allowed_sample_suffixes: tuple[str, ...] = _ALLOWED_SAMPLE_SUFFIXES
    _extra: dict[str, str] = field(default_factory=dict, repr=False)

    # ── construction ────────────────────────────────────────────────────

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> GhostlineConfig:
        """Build from ``GHOSTLINE_*`` variables, falling back to the donor's own
        variable names.

        The fallbacks exist because an operator who followed the donor's setup
        walkthrough already has ``TWILIO_ACCOUNT_SID`` and friends exported; making
        them re-type every secret under a new prefix would be the kind of friction
        that gets a system switched off. The prefix always wins.
        """
        source = dict(os.environ if env is None else env)

        def pick(*names: str, default: str | None = None) -> str | None:
            for name in names:
                value = (source.get(name) or "").strip()
                if value:
                    return value
            return default

        ledger_dir = pick("GHOSTLINE_LEDGER_DIR", default=str(_DEFAULT_LEDGER))
        samples_root = pick("GHOSTLINE_SAMPLES_ROOT", default=str(DONOR_ASSETS))
        port_raw = pick("GHOSTLINE_PORT", default="0")
        try:
            port = int(port_raw or 0)
        except ValueError:
            port = 0

        return cls(
            twilio_account_sid=pick("GHOSTLINE_TWILIO_ACCOUNT_SID", "TWILIO_ACCOUNT_SID"),
            twilio_auth_token=pick("GHOSTLINE_TWILIO_AUTH_TOKEN", "TWILIO_AUTH_TOKEN"),
            twilio_from_number=pick("GHOSTLINE_TWILIO_FROM_NUMBER", "TWILIO_FROM_NUMBER"),
            deepgram_api_key=pick("GHOSTLINE_DEEPGRAM_API_KEY", "DEEPGRAM_API_KEY"),
            deepgram_model=pick("GHOSTLINE_DEEPGRAM_MODEL", default="nova-2") or "nova-2",
            deepgram_language=pick("GHOSTLINE_DEEPGRAM_LANGUAGE", default="en-US") or "en-US",
            elevenlabs_api_key=pick("GHOSTLINE_ELEVENLABS_API_KEY", "ELEVENLABS_API_KEY"),
            elevenlabs_model=pick("GHOSTLINE_ELEVENLABS_MODEL", default="eleven_multilingual_v2")
            or "eleven_multilingual_v2",
            litellm_model=pick("GHOSTLINE_LITELLM_MODEL", default="openai/gpt-4o-mini")
            or "openai/gpt-4o-mini",
            litellm_api_base=pick("GHOSTLINE_LITELLM_API_BASE", "LITELLM_API_BASE"),
            openai_api_key=pick("GHOSTLINE_OPENAI_API_KEY", "OPENAI_API_KEY"),
            anthropic_api_key=pick("GHOSTLINE_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY"),
            gemini_api_key=pick("GHOSTLINE_GEMINI_API_KEY", "GEMINI_API_KEY"),
            ngrok_authtoken=pick("GHOSTLINE_NGROK_AUTHTOKEN", "NGROK_AUTHTOKEN"),
            public_base_url=pick("GHOSTLINE_PUBLIC_BASE_URL"),
            ledger_dir=Path(ledger_dir) if ledger_dir else _DEFAULT_LEDGER,
            samples_root=Path(samples_root) if samples_root else DONOR_ASSETS,
            playbooks_root=DONOR_PLAYBOOKS,
            host=pick("GHOSTLINE_HOST", default="127.0.0.1") or "127.0.0.1",
            port=port,
            log_level=pick("GHOSTLINE_LOG_LEVEL", default="INFO") or "INFO",
        )

    # ── derived ─────────────────────────────────────────────────────────

    @property
    def llm_api_key(self) -> str | None:
        """The key for the active LiteLLM provider, resolved by model prefix.

        Same rule the donor's composition root uses, kept here so readiness can
        answer "is the model credentialed?" without instantiating the donor.
        """
        model = self.litellm_model.lower()
        if model.startswith("openai/"):
            return self.openai_api_key
        if model.startswith("anthropic/"):
            return self.anthropic_api_key
        if model.startswith("gemini/"):
            return self.gemini_api_key
        # Ollama and other local endpoints need no key.
        return None

    @property
    def calls_path(self) -> Path:
        """The JSONL call ledger."""
        return self.ledger_dir / "calls.jsonl"

    @property
    def voices_path(self) -> Path:
        """The JSONL voice registry."""
        return self.ledger_dir / "voices.jsonl"

    def sample_path(self, relative: str) -> Path | None:
        """Resolve a caller-supplied sample reference inside ``samples_root``.

        Returns ``None`` when the reference escapes the root, which is the
        path-traversal guard: the UI sends a name, never a path, and a name that
        climbs out of the root resolves to nothing rather than to ``C:/Windows``.
        """
        if not relative:
            return None
        candidate = Path(relative)
        if candidate.is_absolute():
            return None
        root = self.samples_root.resolve()
        try:
            resolved = (root / candidate).resolve()
        except OSError:
            return None
        if resolved != root and root not in resolved.parents:
            return None
        return resolved

    # ── readiness ───────────────────────────────────────────────────────

    def readiness(self) -> tuple[ProviderReadiness, ...]:
        """Per-provider readiness, in the order an operator sets them up.

        ``configured`` answers only "is this usable", never "is it correct" --
        validity of a key is a live call to the provider, and a false negative here
        would be a lie in the other direction.
        """
        model = self.litellm_model
        llm_ok = bool(self.llm_api_key) or _is_local_model(model)
        return (
            ProviderReadiness(
                name="twilio",
                configured=bool(self.twilio_account_sid and self.twilio_auth_token),
                env_var="GHOSTLINE_TWILIO_ACCOUNT_SID + GHOSTLINE_TWILIO_AUTH_TOKEN",
                detail="Outbound PSTN placement and Media Stream dial-back.",
            ),
            ProviderReadiness(
                name="twilio_from_number",
                configured=bool(self.twilio_from_number),
                env_var="GHOSTLINE_TWILIO_FROM_NUMBER",
                detail="The caller ID placed on every call. Absent means calls cannot be dialled.",
            ),
            ProviderReadiness(
                name="deepgram",
                configured=bool(self.deepgram_api_key),
                env_var="GHOSTLINE_DEEPGRAM_API_KEY",
                detail=f"Streaming STT ({self.deepgram_model}, {self.deepgram_language})."
                " Unnecessary when the model consumes audio natively.",
            ),
            ProviderReadiness(
                name="elevenlabs",
                configured=bool(self.elevenlabs_api_key),
                env_var="GHOSTLINE_ELEVENLABS_API_KEY",
                detail=f"TTS ({self.elevenlabs_model}) and voice cloning. "
                "Unnecessary when the model produces audio natively.",
            ),
            ProviderReadiness(
                name="llm",
                configured=llm_ok,
                env_var="GHOSTLINE_LITELLM_MODEL + the matching provider key",
                detail=f"Persuasion model: {model}."
                + ("" if llm_ok else " No provider credential resolved for this prefix."),
            ),
            ProviderReadiness(
                name="tunnel",
                configured=bool(self.public_base_url) or bool(self.ngrok_authtoken),
                env_var="GHOSTLINE_PUBLIC_BASE_URL (or GHOSTLINE_NGROK_AUTHTOKEN)",
                detail="A public WSS front door Twilio can dial back into.",
            ),
        )

    def blocking(self) -> tuple[str, ...]:
        """Named absences that stop a call from being placed, in setup order.

        This is what the runtime panel renders as a checklist: everything listed
        here is something the operator can fix, with the variable named.
        """
        out: list[str] = []
        for entry in self.readiness():
            if not entry.configured:
                out.append(f"{entry.name}: set {entry.env_var} -- {entry.detail}")
        return tuple(out)


def _is_local_model(model: str) -> bool:
    """True for model prefixes that are expected to run without an API key."""
    return model.lower().startswith(("ollama/", "openrouter/", "litellm/", "hosted_vllm/"))


@lru_cache(maxsize=1)
def get_config() -> GhostlineConfig:
    """Cached process-wide configuration.

    Cached because a readiness sweep runs on every status poll and re-reading a
    dozen environment variables per request is waste; invalidated only by an
    explicit :func:`clear_config_cache`, which is what the settings route calls
    after an operator writes a value.
    """
    return GhostlineConfig.from_env()


def clear_config_cache() -> None:
    """Drop the cached config so the next read sees the current environment."""
    get_config.cache_clear()
