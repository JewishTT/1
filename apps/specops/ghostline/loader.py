"""Loader for the vendored GhostLine donor (mbhatt1/GhostLine, MIT).

GhostLine arrives the way every donor arrives: as source under ``donors/``, not as a
wheel. The constitution makes donor reuse the default (rev. 1.1.0), so this module
imports the donor's *own* modules rather than reimplementing them, and the split
below is what keeps that honest.

GhostLine is two different things and they have very different portability:

**The stage engine** -- ``taxonomy`` (the 12-stage vocabulary + psych triggers),
``playbook`` (the YAML schema), ``playbook_runner`` (success_regex / goto_* /
max_cycles), ``audio.codec`` (pure-numpy G.711), ``telephony.media_stream``
(the Twilio frame protocol). Zero third-party requirements beyond ``pyyaml``,
``pydantic`` and ``numpy``, all of which the platform already carries. **This runs
unmodified inside the control plane**, so the playbook browser and the dry-run stage
simulator exercise the donor's real logic, not a paraphrase of it.

**The live edges** -- Twilio (PSTN), Deepgram (STT), ElevenLabs (TTS), ngrok
(tunnel), LiteLLM + the Agents SDK (the persuasion model), aiosqlite (the donor's own
ledger). Each needs a third-party package the platform deliberately does not
depend on, and each needs an operator credential. Those are probed, never forced.

The consequence for the UI is the platform's ordinary discipline: what cannot run is
*named* in a ``missing[]`` list rather than rendered as a zero or a blank pane
(FR-012, §90, §99). Every one of GhostLine's CLI verbs maps onto a served control
whether or not its provider is configured, because the operator still has to be able
to see and set up the thing that is missing.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

__all__ = (
    "DONOR_ID",
    "DONOR_LICENSE",
    "DONOR_REPO",
    "DONOR_ROOT",
    "DONOR_SRC",
    "LIVE_EDGES",
    "STAGE_ENGINE",
    "DonorHandle",
    "REPO_ROOT",
    "donor",
    "donor_readiness",
)

_LOGGER = logging.getLogger(__name__)

#: ``apps/specops/ghostline/loader.py`` -> ghostline -> specops -> apps -> repo root.
REPO_ROOT = Path(__file__).resolve().parents[3]

DONOR_ID = "ghostline"
DONOR_REPO = "https://github.com/mbhatt1/GhostLine"
DONOR_LICENSE = "MIT"
DONOR_ROOT = REPO_ROOT / "donors" / DONOR_ID
DONOR_SRC = DONOR_ROOT / "src"
DONOR_PLAYBOOKS = DONOR_ROOT / "playbooks"
DONOR_ASSETS = DONOR_ROOT / "assets"


@dataclass(frozen=True, slots=True)
class _ModuleSpec:
    """One donor module, and what it needs before it can even be imported."""

    #: Dotted name inside the donor's own package.
    dotted: str
    #: Third-party distributions required at import time. Probed, never installed.
    requires: tuple[str, ...] = ()
    #: Short operator-facing reason when the module is unavailable.
    role: str = ""


#: The stage engine: runs inside the platform today, unmodified.
STAGE_ENGINE: tuple[_ModuleSpec, ...] = (
    _ModuleSpec("ghostline.taxonomy", role="12-stage conversation taxonomy + trigger tables"),
    _ModuleSpec("ghostline.playbook", ("yaml", "pydantic"), "playbook YAML schema + validation"),
    _ModuleSpec(
        "ghostline.playbook_runner",
        role="stage transitions: success_regex / goto_on_* / max_cycles",
    ),
    _ModuleSpec("ghostline.audio.codec", ("numpy",), "pure-numpy G.711 mu-law codec"),
    _ModuleSpec("ghostline.telephony.media_stream", role="Twilio Media Stream frame protocol"),
)

#: The live edges: each needs a package the platform does not carry, or a credential.
LIVE_EDGES: tuple[_ModuleSpec, ...] = (
    _ModuleSpec("ghostline.telephony.twilio", ("twilio",), "outbound PSTN call placement + TwiML"),
    _ModuleSpec("ghostline.telephony.tunnel", ("pyngrok",), "ngrok tunnel"),
    _ModuleSpec("ghostline.stt.deepgram", ("aiohttp",), "streaming speech-to-text"),
    _ModuleSpec("ghostline.tts.elevenlabs", ("httpx", "pydub"), "text-to-speech + voice cloning"),
    _ModuleSpec("ghostline.agent.reply_generator", ("agents", "litellm"), "persuasion model"),
    _ModuleSpec(
        "ghostline.persistence.repository",
        ("aiosqlite",),
        "the donor's own SQLite call ledger",
    ),
    _ModuleSpec(
        "ghostline.server.fastapi", ("fastapi", "agents"), "the donor's Twilio media server"
    ),
)

_ALL: tuple[_ModuleSpec, ...] = STAGE_ENGINE + LIVE_EDGES


@dataclass(slots=True)
class DonorHandle:
    """Resolves donor modules on demand and remembers why any of them is absent.

    Resolution is lazy and cached per module. Nothing here imports eagerly, so
    importing ``specops.ghostline`` costs nothing even when the donor tree is
    missing -- the department then simply reports its donor as not served.
    """

    root: Path
    src: Path
    _loaded: dict[str, object | None] = None  # type: ignore[assignment]
    _absent: dict[str, str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self._loaded = {}
        self._absent = {}

    # ── resolution ──────────────────────────────────────────────────────

    def available(self) -> bool:
        """True when the vendored source tree is present at all."""
        return self.src.is_dir() and (self.src / "ghostline" / "__init__.py").is_file()

    def get(self, dotted: str) -> object | None:
        """Return the donor module, or ``None`` with the reason recorded.

        Never raises: an unimportable donor module is a named absence, not a
        crash of whatever surface happened to ask for it.
        """
        if dotted in self._loaded:
            return self._loaded[dotted]
        module = self._resolve(dotted)
        self._loaded[dotted] = module
        if module is None:
            self._absent[dotted] = self._absent.get(dotted, "not importable")
        return module

    def _resolve(self, dotted: str) -> object | None:
        if not self.available():
            return None
        spec = next((s for s in _ALL if s.dotted == dotted), None)
        if spec is not None:
            unmet = [dep for dep in spec.requires if not _has_distribution(dep)]
            if unmet:
                self._absent[dotted] = (
                    f"donor module {dotted} needs {', '.join(unmet)} "
                    "(not installed in the platform environment)"
                )
                return None
        self._ensure_src_on_path()
        try:
            return importlib.import_module(dotted)
        except Exception as exc:
            self._absent[dotted] = f"donor module {dotted} failed to import: {exc}"
            _LOGGER.warning("ghostline: %s", self._absent[dotted])
            return None

    def _ensure_src_on_path(self) -> None:
        """Put ``donors/ghostline/src`` on ``sys.path`` exactly once.

        The donor is imported under its own name (``ghostline.*``) rather than
        re-homed, because its modules use absolute intra-package imports
        (``from ghostline.taxonomy import SalesStage``) and a renamed copy would
        break every one of them. The entry is appended, not prepended: the
        platform's own packages must win any name collision.
        """
        entry = str(self.src)
        if entry not in sys.path:
            sys.path.append(entry)

    # ── reporting ───────────────────────────────────────────────────────

    def absence(self) -> dict[str, str]:
        """dotted module -> why it is unavailable (only modules actually probed)."""
        return dict(self._absent)

    def report(self) -> dict[str, object]:
        """A machine-readable description of the donor, for ``GET /status``.

        ``present`` is the vendored tree; per-module ``ready`` is what the platform
        can actually execute; ``absent`` names each blocker with the package or
        tree that would close it.
        """
        engine_ready: list[str] = []
        engine_absent: list[str] = []
        for spec in STAGE_ENGINE:
            (engine_ready if self.get(spec.dotted) is not None else engine_absent).append(
                spec.dotted
            )
        edge_ready: list[str] = []
        edge_absent: list[str] = []
        for spec in LIVE_EDGES:
            if self.get(spec.dotted) is not None:
                edge_ready.append(spec.dotted)
            else:
                edge_absent.append(self._absent.get(spec.dotted, "not imported"))

        roles = {spec.dotted: spec.role for spec in _ALL}
        return {
            "donor_id": DONOR_ID,
            "repo": DONOR_REPO,
            "license": DONOR_LICENSE,
            "root": str(self.root),
            "present": self.available(),
            "playbooks_root": str(DONOR_PLAYBOOKS),
            "stage_engine": {"ready": engine_ready, "absent": engine_absent},
            "live_edges": {"ready": edge_ready, "absent": edge_absent},
            "roles": roles,
        }


def _has_distribution(name: str) -> bool:
    """True when ``name`` is importable in the current interpreter."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):  # pragma: no cover - defensive
        return False


#: One handle per process. The vendor tree does not move under us at runtime, and
#: re-probing on every request would make the status endpoint a filesystem sweep.
_HANDLE = DonorHandle(root=DONOR_ROOT, src=DONOR_SRC)


def donor() -> DonorHandle:
    """The process-wide donor handle."""
    return _HANDLE


def donor_readiness() -> dict[str, object]:
    """Convenience: ``donor().report()``."""
    return _HANDLE.report()
