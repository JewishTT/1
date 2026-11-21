"""Voice registry: the donor's ``clone`` verb, as a served control.

GhostLine's CLI has exactly one command for voices -- ``ghostline clone sample.wav
--name helpdesk`` -- which uploads a sample to ElevenLabs and prints a ``voice_id``
that is then pasted into ``serve --voice-id``. In a terminal that is a two-step
copy-paste with an ID nobody can read. As a surface it is a registry: a voice has an
id, a name, an origin and a provenance, it can be listed, it can be created from an
upload, and the runtime points at one by id.

Two repairs on transfer, both of them things the CLI cannot express:

* **Premade voices are first-class.** The donor's README tells operators on
  ElevenLabs' free tier that cloning is unavailable and that they should pick a
  premade ``voice_id`` from the console instead. That ID is a perfectly good voice
  and the CLI has no way to record one. ``origin`` carries the distinction so the
  operator knows which voices are clones of a real person and which are stock.
* **Uploads are bounded and contained.** A sample arrives as a name plus bytes. The
  name is resolved inside a configured samples root (so nothing can address
  ``C:/Windows`` by climbing out of it), the suffix must be one the donor's reader
  actually handles, and the size is capped (Constitution §VII: every external input
  is untrusted, with size limits).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from specops.ghostline.config import GhostlineConfig, get_config
from specops.ghostline.loader import donor

__all__ = (
    "Voice",
    "VoiceRegistry",
    "VoiceUnavailable",
    "voices",
)

_LOGGER = logging.getLogger(__name__)


class VoiceUnavailable(Exception):
    """Cloning could not run. ``reason`` names what is missing, never a stack trace."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class Voice:
    """One registered voice."""

    voice_id: str
    name: str
    #: ``cloned`` from an uploaded sample, or ``premade`` from the provider's library.
    origin: str
    created_at: str
    #: The sample's name relative to the samples root. ``None`` for a premade voice.
    sample_ref: str | None = None
    #: Bytes of the sample, when known. Useful for spotting a too-short clone.
    sample_bytes: int | None = None
    notes: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class VoiceRegistry:
    """Registered voices, persisted as JSONL beside the call ledger.

    Same durability argument as the ledger: the file is the record, the in-memory
    list is a projection of it. Voice ids are the thing a runtime is pinned to, so a
    registry that forgets on restart would strand a running exercise.
    """

    def __init__(self) -> None:
        self._voices: dict[str, Voice] = {}
        self._loaded = False
        self._loaded_path: Path | None = None

    @property
    def path(self) -> Path:
        return get_config().voices_path

    def load(self) -> None:
        """Rebuild from the registry file. Idempotent per path.

        Path-keyed for the same reason the ledger is: an index built from one file
        while writes go to another is two registries, and a runtime pinned to a voice
        id that only exists in one of them is a runtime that breaks on restart.
        """
        path = self.path
        if self._loaded and self._loaded_path == path:
            return
        if self._loaded and self._loaded_path != path:
            self._voices = {}
        self._loaded_path = path
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    _LOGGER.warning("ghostline: skipping unparseable voice line in %s", path)
                    continue
                voice = Voice(
                    voice_id=str(payload.get("voice_id", "")),
                    name=str(payload.get("name", "")),
                    origin=str(payload.get("origin", "premade")),
                    created_at=str(payload.get("created_at", "")),
                    sample_ref=payload.get("sample_ref"),
                    sample_bytes=payload.get("sample_bytes"),
                    notes=payload.get("notes"),
                )
                if voice.voice_id:
                    self._voices[voice.voice_id] = voice
        self._loaded = True

    # ── reads ──────────────────────────────────────────────────────────

    def list(self) -> tuple[Voice, ...]:
        self.load()
        return tuple(sorted(self._voices.values(), key=lambda v: (v.created_at, v.voice_id)))

    def get(self, voice_id: str) -> Voice | None:
        self.load()
        return self._voices.get(voice_id)

    # ── writes ─────────────────────────────────────────────────────────

    def register(
        self,
        *,
        voice_id: str,
        name: str,
        origin: str,
        sample_ref: str | None = None,
        sample_bytes: int | None = None,
        notes: str | None = None,
    ) -> Voice:
        """Record a voice. Idempotent on ``voice_id``: re-registering updates it."""
        voice = Voice(
            voice_id=voice_id,
            name=name,
            origin=origin,
            created_at=datetime.now(UTC).isoformat(),
            sample_ref=sample_ref,
            sample_bytes=sample_bytes,
            notes=notes,
        )
        self.load()
        self._voices[voice_id] = voice
        self._persist(voice)
        return voice

    def remove(self, voice_id: str) -> bool:
        """Forget a voice. Returns False when it was not registered.

        Refuses to remove the voice a running exercise is pinned to -- the registry
        has no idea what that is, so the caller checks and the runtime does not.
        """
        self.load()
        if voice_id not in self._voices:
            return False
        del self._voices[voice_id]
        self._rewrite()
        return True

    def clone(
        self,
        *,
        name: str,
        sample_ref: str | None = None,
        sample_bytes: bytes | None = None,
        sample_filename: str | None = None,
    ) -> Voice:
        """Clone a voice from a sample. Raises :class:`VoiceUnavailable` when it cannot.

        Two input shapes, matching the two ways an operator has a sample: a name
        already in the samples root (the donor CLI's shape), or bytes uploaded from
        the UI. Both go through the same validation.
        """
        config = get_config()
        if not config.elevenlabs_api_key:
            raise VoiceUnavailable(
                "ElevenLabs is not configured — set GHOSTLINE_ELEVENLABS_API_KEY to clone a voice. "
                "A premade voice id from the provider's library can be registered instead."
            )
        # The sample is validated before the donor's service class is resolved, and the
        # order is deliberate. Each step answers the question an operator would ask
        # next, cheapest-and-most-fundamental first: is there a provider at all, is the
        # file I asked for actually a cloneable sample, and only then — can this
        # environment run the code that does the cloning. Validating last would make
        # a typo'd filename report "pydub is not installed", which is not the thing
        # the operator did wrong.
        sample_path = self._stage_sample(
            config,
            sample_ref=sample_ref,
            sample_bytes=sample_bytes,
            sample_filename=sample_filename,
        )
        service_cls = self._service_class()

        service = service_cls(
            api_key=config.elevenlabs_api_key,
            model_id=config.elevenlabs_model,
        )

        # The donor's clone is async and this module is sync (it is called from the
        # router's threadpool). Rather than nest an event loop per request, the whole
        # clone runs to completion on a fresh loop owned by this call.
        voice_id = _run_async(service.clone(str(sample_path), name=name))
        if not voice_id:
            raise VoiceUnavailable(
                "ElevenLabs rejected the clone. The common cause is plan tier: instant voice "
                "cloning requires a Starter subscription, and the free tier serves premade "
                "voices only."
            )
        size = sample_path.stat().st_size if sample_path.is_file() else None
        return self.register(
            voice_id=voice_id,
            name=name,
            origin="cloned",
            sample_ref=sample_ref or (sample_filename or sample_path.name),
            sample_bytes=size,
        )

    # ── internals ──────────────────────────────────────────────────────

    @staticmethod
    def _service_class() -> Any:
        module = donor().get("ghostline.tts.elevenlabs")
        service_cls = getattr(module, "VoiceService", None)
        if service_cls is None:
            raise VoiceUnavailable(
                "the donor's ElevenLabs voice service is not importable — its `pydub` "
                "dependency is not installed in the platform environment"
            )
        return service_cls

    def _stage_sample(
        self,
        config: GhostlineConfig,
        *,
        sample_ref: str | None,
        sample_bytes: bytes | None,
        sample_filename: str | None,
    ) -> Path:
        """Resolve or persist the sample and return a path the donor can read."""
        if sample_bytes is not None:
            if sample_ref is None and sample_filename is None:
                raise VoiceUnavailable("an uploaded sample needs a filename to keep its suffix")
            return _write_upload(
                config, sample_filename or sample_ref or "sample.wav", sample_bytes
            )
        if not sample_ref:
            raise VoiceUnavailable("no sample supplied: give a sample name or upload a file")
        resolved = config.sample_path(sample_ref)
        if resolved is None:
            raise VoiceUnavailable(
                f"sample {sample_ref!r} resolves outside the samples root "
                f"({config.samples_root}); send a name, not a path"
            )
        suffix = resolved.suffix.lower()
        if suffix not in config.allowed_sample_suffixes:
            allowed = ", ".join(config.allowed_sample_suffixes)
            raise VoiceUnavailable(
                f"sample format {suffix or '(none)'} is not readable by the donor's cloner; "
                f"expected one of {allowed} (M4A is transcoded through ffmpeg)"
            )
        if not resolved.is_file():
            raise VoiceUnavailable(
                f"sample {sample_ref!r} was not found under {config.samples_root}. "
                "Upload it, or point GHOSTLINE_SAMPLES_ROOT at the directory holding it."
            )
        size = resolved.stat().st_size
        if size > config.max_sample_bytes:
            raise VoiceUnavailable(f"sample is {size} bytes; the cap is {config.max_sample_bytes}")
        return resolved

    def _persist(self, voice: Voice) -> None:
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(voice.as_dict(), ensure_ascii=False) + "\n")

    def _rewrite(self) -> None:
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".jsonl.tmp")
        tmp.write_text(
            "\n".join(json.dumps(v.as_dict(), ensure_ascii=False) for v in self.list()) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, path)

    def named_absences(self) -> tuple[str, ...]:
        out: list[str] = []
        if donor().get("ghostline.tts.elevenlabs") is None:
            out.append(
                "POST /specops/ghostline/voices/clone (the donor's ElevenLabs voice service "
                "needs pydub + ffmpeg, not installed in the platform environment)"
            )
        if not get_config().elevenlabs_api_key:
            out.append(
                "POST /specops/ghostline/voices/clone (GHOSTLINE_ELEVENLABS_API_KEY is unset)"
            )
        return tuple(out)


def _write_upload(config: GhostlineConfig, filename: str, data: bytes) -> Path:
    """Persist an uploaded sample under the samples root and return its path."""
    if len(data) > config.max_sample_bytes:
        raise VoiceUnavailable(f"upload is {len(data)} bytes; the cap is {config.max_sample_bytes}")
    suffix = Path(filename).suffix.lower()
    if suffix not in config.allowed_sample_suffixes:
        allowed = ", ".join(config.allowed_sample_suffixes)
        raise VoiceUnavailable(
            f"upload format {suffix or '(none)'} is not readable by the donor's cloner; "
            f"expected one of {allowed}"
        )
    if not data:
        raise VoiceUnavailable("the uploaded sample is empty")
    root = config.samples_root
    root.mkdir(parents=True, exist_ok=True)
    # The stored name is derived, never taken from the client: a browser-supplied
    # filename is attacker-controlled and would otherwise decide where a write lands.
    safe_stem = "".join(ch for ch in Path(filename).stem if ch.isalnum() or ch in "-_")[:48]
    target = root / f"{safe_stem or 'sample'}{suffix}"
    counter = 1
    while target.exists():
        target = root / f"{safe_stem or 'sample'}-{counter}{suffix}"
        counter += 1
    target.write_bytes(data)
    return target


def _run_async(coro: Any) -> Any:
    """Run a coroutine to completion from a synchronous caller.

    The router runs its handlers in a threadpool precisely so that blocking work does
    not stall the event loop, which means there is no loop running here to await on.
    """
    import asyncio

    return asyncio.run(coro)


_VOICES = VoiceRegistry()


def voices() -> VoiceRegistry:
    """The process-wide voice registry."""
    return _VOICES
