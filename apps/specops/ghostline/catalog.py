"""The playbook catalogue: the donor's YAML library, loaded and served whole.

Every ``donors/ghostline/playbooks/*.yaml`` becomes a served plan. The donor's own
``ghostline.playbook.Playbook`` does the parsing and validation, so a playbook that
renders here is one the donor's stage machine will actually accept -- the catalogue
never reports a plan the donor would then reject.

What the platform adds on top of the donor's data, and says so:

* **ATT&CK mapping.** GhostLine carries none. The mapping below is the platform's,
  declared here rather than inferred at render time, and every view that carries a
  technique also carries ``mapping_source: "platform-declared"`` so a technique is
  never mistaken for donor evidence (FR-012, §99).
* **Stage metadata.** The 12-stage vocabulary, psych triggers, silence timings,
  default prompts and check-in lines all come from ``ghostline.taxonomy`` when the
  donor is importable. When it is not, the stage *names* remain servable (they are
  this platform's vocabulary too) and the donor-side detail is named absent.

A playbook is validated on load; an invalid one is recorded as invalid with the
donor's own error, because "this file does not parse" is exactly the thing an
operator authoring a scenario needs to see.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from specops.ghostline.loader import donor
from specops.ghostline.redaction import Redactor

__all__ = (
    "ATTACK_MAPPING_SOURCE",
    "PlaybookLibrary",
    "PlaybookSummary",
    "StageDetail",
    "library",
)

_LOGGER = logging.getLogger(__name__)

#: Every technique this module emits carries this. Stated on the record because
#: GhostLine itself has no ATT&CK vocabulary, and an unattributed technique id on a
#: SpecOps board reads as a measured fact.
ATTACK_MAPPING_SOURCE = "platform-declared"

#: The channel GhostLine operates on, plus the techniques its stages express.
#: Keyed by playbook id where the scenario is specific; the default applies otherwise.
_TECHNIQUES: dict[str, tuple[tuple[str, str], ...]] = {
    "executive_spearphish_multi-lingual": (
        ("T1566.002", "Phishing: Spearphishing Voice — the channel GhostLine dials."),
        ("T1589", "Gather Victim Identity Information — the DISCOVERY/VALIDATION stages."),
        ("T1078", "Valid Accounts — the CLOSE stage reads a one-time code back."),
    ),
    "vendor_payment_change_ceo_whaling": (
        ("T1566.002", "Phishing: Spearphishing Voice — the channel GhostLine dials."),
        ("T1657", "Financial Theft — vendor bank-detail substitution."),
        ("T1589", "Gather Victim Identity Information — confirming the existing record."),
    ),
    "hr_benefits_open_enrollment_phish": (
        ("T1566.002", "Phishing: Spearphishing Voice — the channel GhostLine dials."),
        ("T1657", "Financial Theft — benefits/payroll redirection."),
        ("T1078", "Valid Accounts — an SSO code read back at CLOSE."),
    ),
    "zero_day_it_patch": (
        ("T1566.002", "Phishing: Spearphishing Voice — the channel GhostLine dials."),
        ("T1204.002", "User Execution: Malicious File — the patch one-liner."),
        ("T1059.004", "Command and Scripting Interpreter: Unix Shell — the sudo prompt."),
    ),
    "it-test": (
        ("T1566.002", "Phishing: Spearphishing Voice — the channel GhostLine dials."),
        ("T1204.002", "User Execution: Malicious File — the update portal."),
    ),
}

_DEFAULT_TECHNIQUES: tuple[tuple[str, str], ...] = (
    ("T1566.002", "Phishing: Spearphishing Voice — the channel GhostLine dials."),
)

#: Stage names in canonical progression order. Mirrors ``ghostline.taxonomy.SalesStage``
#: so a plan that omits a stage still renders against a known ladder, and so the UI
#: has a closed vocabulary to colour by.
STAGE_ORDER: tuple[str, ...] = (
    "RAPPORT",
    "CREDIBILITY",
    "DISCOVERY",
    "VALIDATION",
    "ALIGNMENT",
    "PROOF",
    "URGENCY",
    "TRIAL_CLOSE",
    "OBJECTION",
    "CLOSE",
    "FOLLOW_UP",
    "REPORTING",
)


@dataclass(frozen=True, slots=True)
class StageDetail:
    """One stage of a playbook, with everything the donor would act on."""

    stage: str
    position: int
    persona: str | None
    has_custom_prompt: bool
    custom_prompt: str | None
    success_regex: str | None
    goto_on_success: str | None
    goto_on_fail: str | None
    max_cycles: int
    silent_until: int | None
    ambient_ratio: float | None
    language_hint: str | None
    operator_note: str | None
    #: Donor's ``taxonomy`` extras. ``None`` means the donor taxonomy is absent.
    psych_triggers: tuple[str, ...] | None
    default_prompt: str | None
    checkin_line: str | None
    #: True when this stage's ``success_regex`` matches secret-shaped text, so the
    #: redactor treats what the target says here as a credential to scrub.
    captures_credential: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "position": self.position,
            "persona": self.persona,
            "has_custom_prompt": self.has_custom_prompt,
            "custom_prompt": self.custom_prompt,
            "success_regex": self.success_regex,
            "goto_on_success": self.goto_on_success,
            "goto_on_fail": self.goto_on_fail,
            "max_cycles": self.max_cycles,
            "silent_until": self.silent_until,
            "ambient_ratio": self.ambient_ratio,
            "language_hint": self.language_hint,
            "operator_note": self.operator_note,
            "psych_triggers": list(self.psych_triggers) if self.psych_triggers else None,
            "default_prompt": self.default_prompt,
            "checkin_line": self.checkin_line,
            "captures_credential": self.captures_credential,
        }


@dataclass(frozen=True, slots=True)
class PlaybookSummary:
    """A plan as the catalogue lists it."""

    playbook_id: str
    name: str
    author: str | None
    version: float
    culture: str | None
    description: str | None
    stage_count: int
    first_stage: str
    stage_names: tuple[str, ...]
    has_branching: bool
    persona_name: str
    techniques: tuple[tuple[str, str], ...]
    mapping_source: str
    source_path: str
    valid: bool
    invalid_reason: str | None
    #: Everything the donor would have told us that we could not load.
    missing: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "playbook_id": self.playbook_id,
            "name": self.name,
            "author": self.author,
            "version": self.version,
            "culture": self.culture,
            "description": self.description,
            "stage_count": self.stage_count,
            "first_stage": self.first_stage,
            "stage_names": list(self.stage_names),
            "has_branching": self.has_branching,
            "persona_name": self.persona_name,
            "techniques": [{"id": tid, "reason": why} for tid, why in self.techniques],
            "mapping_source": self.mapping_source,
            "source_path": self.source_path,
            "valid": self.valid,
            "invalid_reason": self.invalid_reason,
            "missing": list(self.missing),
        }


@dataclass(slots=True)
class _Entry:
    """A parsed playbook plus the summary projection and any load failure."""

    summary: PlaybookSummary
    playbook: Any | None
    stages: tuple[StageDetail, ...] = ()
    declared_patterns: tuple[str, ...] = ()


class PlaybookLibrary:
    """The donor's playbook tree, loaded once and served whole.

    Reloading is explicit (:meth:`reload`) rather than watched: the tree changes
    when an operator edits a scenario, and a survey operator is the only party who
    knows that. A watcher would rebuild every view on a keystroke in an editor.
    """

    def __init__(self, root: Path | None = None) -> None:
        self._root = root
        self._entries: dict[str, _Entry] = {}
        self._loaded = False

    @property
    def root(self) -> Path:
        return self._root if self._root is not None else donor().root / "playbooks"

    # ── loading ─────────────────────────────────────────────────────────

    def load(self) -> None:
        """Load every playbook under the donor tree. Idempotent."""
        if self._loaded:
            return
        root = self.root
        entries: dict[str, _Entry] = {}
        if not root.is_dir():
            self._entries = {}
            self._loaded = True
            _LOGGER.warning("ghostline: playbook root not found at %s", root)
            return

        taxonomy = donor().get("ghostline.taxonomy")
        # `donor().get` yields the donor *module*; the catalogue wants the class in
        # it. A module that imports but does not export `Playbook` is as unusable as
        # one that will not import, so both land in the same named-absence branch.
        playbook_module = donor().get("ghostline.playbook")
        playbook_cls = getattr(playbook_module, "Playbook", None)

        for path in sorted((*root.rglob("*.yaml"), *root.rglob("*.yml"))):
            entry = self._parse(path, playbook_cls, taxonomy)
            entries[entry.summary.playbook_id] = entry
        self._entries = entries
        self._loaded = True
        _LOGGER.info("ghostline: loaded %d playbook(s) from %s", len(entries), root)

    def reload(self) -> int:
        """Force a re-read of the tree; returns the number of playbooks loaded."""
        self._loaded = False
        self.load()
        return len(self._entries)

    def _parse(self, path: Path, playbook_cls: Any | None, taxonomy: Any | None) -> _Entry:
        playbook_id = path.stem
        missing: list[str] = []

        if playbook_cls is None:
            # The donor's parser is unavailable. The file still exists and the UI
            # still has to show that; it just cannot be executed, so it is served
            # as not-loadable rather than as an empty plan.
            missing.append(
                "ghostline.playbook (the donor's YAML schema validator is not importable — "
                "playbooks can be listed but not loaded or simulated)"
            )
            return _Entry(
                summary=self._invalid_summary(
                    playbook_id,
                    path,
                    "donor playbook validator unavailable",
                    missing=tuple(missing),
                ),
                playbook=None,
            )

        try:
            # Read the bytes ourselves with an explicit UTF-8 and hand the donor a
            # decoded string, rather than letting `Playbook.from_file` read it.
            #
            # The donor's `from_file` does `p.read_text()` with no encoding, which
            # resolves to the process's *locale* encoding. On a Windows operator box
            # that is cp1251 or cp1252, and every non-ASCII character in a scenario
            # name becomes mojibake on screen — the UI showed a playbook as
            # "HR Benefits â€" Open-Enrollment", which reads as data corruption in the
            # API rather than as an encoding default in a vendor file.
            #
            # `from_string` is the donor's own public entry point for pre-decoded YAML,
            # so this repairs it through an existing donor API rather than patching the
            # vendor tree, and it pins the encoding once for every playbook instead of
            # inheriting whatever the machine's locale happens to be.
            playbook = playbook_cls.from_string(
                path.read_text(encoding="utf-8"), source=str(path)
            )
        except Exception as exc:  # noqa: BLE001 - a bad file is a report, not a crash
            missing.append(
                "ghostline.playbook.from_string rejected this file "
                "(the donor's PlaybookError carries the reason)"
            )
            return _Entry(
                summary=self._invalid_summary(playbook_id, path, str(exc), missing=tuple(missing)),
                playbook=None,
            )

        if taxonomy is None:
            missing.append(
                "ghostline.taxonomy (stage triggers / prompts / silence timings "
                "are not served — the donor taxonomy module is not importable)"
            )

        stages = self._stages(playbook, taxonomy)
        declared = tuple(s.success_regex for s in playbook.sequence if s.success_regex)
        branching = any(
            s.goto_on_success is not None or s.goto_on_fail is not None for s in playbook.sequence
        )
        techniques = _TECHNIQUES.get(playbook_id, _DEFAULT_TECHNIQUES)
        summary = PlaybookSummary(
            playbook_id=playbook_id,
            name=playbook.meta.name,
            author=playbook.meta.author,
            version=float(playbook.meta.version),
            culture=getattr(playbook.meta, "culture", None),
            description=getattr(playbook.meta, "description", None),
            stage_count=len(playbook.sequence),
            first_stage=playbook.first_stage.name,
            stage_names=playbook.stage_names,
            has_branching=branching,
            persona_name=playbook.persona.name,
            techniques=techniques,
            mapping_source=ATTACK_MAPPING_SOURCE,
            source_path=str(path),
            valid=True,
            invalid_reason=None,
            missing=tuple(missing),
        )
        return _Entry(summary=summary, playbook=playbook, stages=stages, declared_patterns=declared)

    def _invalid_summary(
        self,
        playbook_id: str,
        path: Path,
        reason: str,
        *,
        missing: tuple[str, ...],
    ) -> PlaybookSummary:
        return PlaybookSummary(
            playbook_id=playbook_id,
            name=playbook_id,
            author=None,
            version=0.0,
            culture=None,
            description=None,
            stage_count=0,
            first_stage="",
            stage_names=(),
            has_branching=False,
            persona_name="",
            techniques=(),
            mapping_source=ATTACK_MAPPING_SOURCE,
            source_path=str(path),
            valid=False,
            invalid_reason=reason,
            missing=missing,
        )

    def _stages(self, playbook: Any, taxonomy: Any | None) -> tuple[StageDetail, ...]:
        out: list[StageDetail] = []
        for position, config in enumerate(playbook.sequence):
            name = config.stage.name
            out.append(
                StageDetail(
                    stage=name,
                    position=position,
                    persona=config.persona,
                    has_custom_prompt=config.custom_prompt is not None,
                    custom_prompt=config.custom_prompt,
                    success_regex=config.success_regex,
                    goto_on_success=config.goto_on_success.name if config.goto_on_success else None,
                    goto_on_fail=config.goto_on_fail.name if config.goto_on_fail else None,
                    max_cycles=config.max_cycles,
                    silent_until=playbook.effective_silent_until(config.stage)
                    if playbook.stage_for(config.stage) is not None
                    else config.silent_until,
                    ambient_ratio=playbook.effective_ambient_ratio(config.stage)
                    if playbook.stage_for(config.stage) is not None
                    else config.ambient_ratio,
                    language_hint=config.language_hint,
                    operator_note=config.operator_note,
                    psych_triggers=self._taxonomy_get(taxonomy, "PSYCH_TRIGGERS", name),
                    default_prompt=self._taxonomy_get(taxonomy, "STAGE_PROMPTS", name),
                    checkin_line=self._taxonomy_get(taxonomy, "STAGE_CHECKINS", name),
                    captures_credential=_is_credential_pattern(config.success_regex),
                )
            )
        return tuple(out)

    @staticmethod
    def _taxonomy_get(taxonomy: Any | None, table: str, stage_name: str) -> tuple[str, ...] | None:
        if taxonomy is None:
            return None
        table_obj = getattr(taxonomy, table, None)
        if table_obj is None:
            return None
        for member in getattr(taxonomy, "SalesStage", ()):  # pragma: no branch
            if member.name == stage_name:
                value = table_obj.get(member)
                if isinstance(value, list):
                    return tuple(value)
                if isinstance(value, str):
                    return (value,)
                return None
        return None

    # ── access ──────────────────────────────────────────────────────────

    def summaries(self) -> tuple[PlaybookSummary, ...]:
        self.load()
        return tuple(
            sorted((e.summary for e in self._entries.values()), key=lambda s: s.playbook_id)
        )

    def entry(self, playbook_id: str) -> _Entry | None:
        self.load()
        return self._entries.get(playbook_id)

    def summary(self, playbook_id: str) -> PlaybookSummary | None:
        entry = self.entry(playbook_id)
        return entry.summary if entry else None

    def playbook(self, playbook_id: str) -> Any | None:
        entry = self.entry(playbook_id)
        return entry.playbook if entry else None

    def stages(self, playbook_id: str) -> tuple[StageDetail, ...]:
        entry = self.entry(playbook_id)
        return entry.stages if entry else ()

    def redactor(self, playbook_id: str) -> Redactor:
        """A redactor bound to one playbook's declared success patterns.

        Falls back to the generic shapes for an unknown or invalid playbook, so a
        transcript is never stored unscubbed just because the plan is unknown.
        """
        entry = self.entry(playbook_id)
        if entry is None:
            return Redactor()
        # Only the credential-shaped stages contribute their pattern. A DISCOVERY
        # stage whose success_regex is `\b(single|married|family)\b` is fishing for
        # an answer, not a secret, and feeding it to the redactor would blank out
        # the very words that make a transcript readable.
        return Redactor(
            tuple(
                stage.success_regex
                for stage in entry.stages
                if stage.captures_credential and stage.success_regex
            )
        )

    def validation_errors(self) -> dict[str, str]:
        """playbook_id -> the donor's rejection reason, for playbooks that failed."""
        self.load()
        return {
            pid: entry.summary.invalid_reason
            for pid, entry in self._entries.items()
            if not entry.summary.valid and entry.summary.invalid_reason
        }

    def named_absences(self) -> tuple[str, ...]:
        """Everything the catalogue could not serve, named."""
        self.load()
        out: list[str] = []
        if not self.root.is_dir():
            out.append(
                f"GET /specops/ghostline/playbooks (donor playbook tree absent at {self.root})"
            )
        if donor().get("ghostline.playbook") is None:
            out.append(
                "GET /specops/ghostline/playbooks/{id} (the donor's Playbook validator is "
                "not importable, so no playbook can be loaded or simulated)"
            )
        if donor().get("ghostline.taxonomy") is None:
            out.append(
                "stage psych_triggers / default_prompt / checkin_line (the donor taxonomy "
                "module is not importable)"
            )
        for entry in self._entries.values():
            out.extend(entry.summary.missing)
        return tuple(dict.fromkeys(out))


def _is_credential_pattern(pattern: str | None) -> bool:
    """True when a stage's success pattern is fishing for a secret rather than a state.

    Decided by shape, and the shape has to be the *bare* secret: a quantifier on a
    bare run of four or more digits, or a credential keyword. Literal scaffolding does
    not count, which is what separates the donor's CLOSE ``\\b\\d{6}\\b`` (a one-time
    code) from its DISCOVERY ``\\.\\d{3}$`` (a kernel version suffix). Getting this
    wrong in the permissive direction labels a kernel check as a credential stage in
    the UI, which is a false statement about the scenario.

    This decides whether the stage's pattern is added to the redactor at all, so the
    same answer has to be right twice: right for what the UI claims, and right for
    what gets scrubbed.
    """
    if not pattern:
        return False
    lowered = pattern.lower()
    secret_worded = any(
        token in lowered
        for token in ("password", "passcode", "secret", "credential", "otp", "pin", "cvv")
    )
    if secret_worded:
        return True
    # Strip the scaffolding that cannot carry a digit class of its own. `\d` is
    # deliberately NOT stripped — removing its backslash would leave a bare `d{6}`
    # and the quantifier lookup would stop finding it.
    stripped = re.sub(r"\\[bBwWsW]|\^|\$", "", lowered)
    for run in re.findall(r"\\?d\{(\d+)(?:,(\d*))?\}|\[0-9\]\{(\d+)(?:,(\d*))?\}", stripped):
        low = int(run[0] or run[2] or 0)
        high = run[1] or run[3] or ""
        top = int(high) if high else low
        if max(low, top) >= 4:
            return True
    return False


_LIBRARY = PlaybookLibrary()


def library() -> PlaybookLibrary:
    """The process-wide playbook library."""
    return _LIBRARY
