"""The donor's stage machine, driven without a telephone.

``ghostline.playbook_runner.PlaybookRunner`` is the donor's actual transition logic:
``success_regex`` matching, ``max_cycles`` exhaustion, ``goto_on_success`` /
``goto_on_fail`` resolution, and the terminal ``compromised`` / ``abandoned`` exits.
It is pure logic with no I/O, which makes it the one part of GhostLine that can be
exercised in full inside the control plane -- and that is worth surfacing, because a
spearphish playbook that is wrong about its own branches is discovered by its
victim rather than by its author.

So the simulator runs the donor's runner over a scripted transcript and reports what
*would* have happened: which stage each utterance landed in, whether the declared
pattern matched, what the machine would have said next, and how the call would have
ended. Nothing is dialled, no credential is sent, no provider is called.

Two properties the router depends on:

* **No persistence.** A simulation writes nothing to the ledger. It is a dry run by
  construction, not a run flagged dry afterwards.
* **Redaction on the way out.** The utterances an operator pastes in are the same
  utterances a target would say, so they go through the playbook's redactor before
  they appear in the trace. The simulation shows the shape of what was elicited,
  never the value.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from specops.ghostline.catalog import library
from specops.ghostline.loader import donor

__all__ = (
    "SimulationResult",
    "SimulationStep",
    "SimulationUnavailable",
    "simulate",
)

_LOGGER = logging.getLogger(__name__)

#: Cap on a scripted transcript. The runner is synchronous and cheap, but an
#: unbounded list from a request body is a denial-of-service surface with no upside.
_MAX_UTTERANCES = 200


class SimulationUnavailable(Exception):
    """The donor's stage machine could not be loaded, so nothing can be simulated."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class SimulationStep:
    """One utterance, and the transition the donor's runner made from it."""

    index: int
    utterance: str
    stage_before: str
    stage_after: str
    success: bool
    cycles_remaining: int
    matched_pattern: str | None
    #: What the stage machine would have said next, per the playbook's greeting for
    #: the stage it landed in. ``None`` when the playbook declares no custom prompt.
    next_line: str | None
    #: True when the runner signalled a terminal state at this step.
    exited: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "utterance": self.utterance,
            "stage_before": self.stage_before,
            "stage_after": self.stage_after,
            "success": self.success,
            "cycles_remaining": self.cycles_remaining,
            "matched_pattern": self.matched_pattern,
            "next_line": self.next_line,
            "exited": self.exited,
        }


@dataclass(frozen=True, slots=True)
class SimulationResult:
    """The whole dry run: the trace, the terminal state, and the safety counters."""

    playbook_id: str
    playbook_name: str
    steps: tuple[SimulationStep, ...]
    final_stage: str | None
    outcome: str | None
    outcome_reason: str | None
    #: Structural, not computed: no credential is captured, ever, in a simulation or
    #: a live call. Rendered so the invariant is visible on the surface where the
    #: credential would otherwise have been.
    capture_passwords: bool = False
    credentials_captured: int = 0
    #: Redaction kinds that fired, so the operator can see the transcript was scrubbed.
    redaction_kinds: tuple[str, ...] = field(default=())
    #: Anything the simulation could not exercise, named.
    missing: tuple[str, ...] = field(default=())

    def as_dict(self) -> dict[str, Any]:
        return {
            "playbook_id": self.playbook_id,
            "playbook_name": self.playbook_name,
            "steps": [s.as_dict() for s in self.steps],
            "final_stage": self.final_stage,
            "outcome": self.outcome,
            "outcome_reason": self.outcome_reason,
            "capture_passwords": self.capture_passwords,
            "credentials_captured": self.credentials_captured,
            "redaction_kinds": list(self.redaction_kinds),
            "missing": list(self.missing),
        }


def simulate(playbook_id: str, utterances: list[str]) -> SimulationResult:
    """Run ``utterances`` through the donor's stage machine for ``playbook_id``.

    Raises :class:`SimulationUnavailable` when the donor's runner is not importable
    or the playbook is not loadable -- the caller renders that as a named absence,
    never as an empty trace that would read as "nothing would have happened".
    """
    runner_cls = _runner_class()
    entry = library().entry(playbook_id)
    if entry is None or entry.playbook is None:
        reason = (
            entry.summary.invalid_reason
            if entry is not None and entry.summary.invalid_reason
            else f"playbook {playbook_id!r} is not in the donor library"
        )
        raise SimulationUnavailable(reason)

    playbook = entry.playbook
    runner = runner_cls(playbook)
    redactor = library().redactor(playbook_id)

    # What the caller sees back is scrubbed; what the machine evaluated is the raw
    # text, because matching a redacted string would change the outcome.
    display = [redactor.scrub(u) for u in utterances[:_MAX_UTTERANCES]]
    kinds: list[str] = []
    for scrubbed in display:
        kinds.extend(scrubbed.kinds)

    steps: list[SimulationStep] = []
    outcome: str | None = None
    reason: str | None = None
    final_stage: str | None = None

    for index, raw in enumerate(utterances[:_MAX_UTTERANCES]):
        stage_before = runner.current_stage
        result = runner.evaluate(raw)
        exited = result.exit_ is not None
        steps.append(
            SimulationStep(
                index=index,
                utterance=display[index].text if index < len(display) else "",
                stage_before=stage_before.name,
                stage_after=result.next_stage.name,
                success=result.success,
                cycles_remaining=result.cycles_remaining,
                matched_pattern=_redact_match(result.matched_pattern, redactor),
                next_line=_line_for(entry, result.next_stage.name),
                exited=exited,
            )
        )
        if exited and result.exit_ is not None:
            outcome = result.exit_.outcome
            reason = redactor.scrub(result.exit_.reason).text
            final_stage = result.exit_.final_stage.name
            break

    if outcome is None and steps:
        final_stage = runner.current_stage.name

    missing: list[str] = []
    if len(utterances) > _MAX_UTTERANCES:
        missing.append(
            f"utterances[{_MAX_UTTERANCES}:] ({len(utterances) - _MAX_UTTERANCES} "
            f"truncated; the runner accepts at most {_MAX_UTTERANCES} steps)"
        )
    for pattern in redactor.patterns:
        missing.append(
            f"redaction pattern {pattern!r} is not a valid regex and was not applied "
            "(the generic credential shapes were used instead)"
        )
    if donor().get("ghostline.agent.reply_generator") is None:
        missing.append(
            "the generated reply for each step (the donor's persuasion model needs "
            "openai-agents + litellm, neither installed in the platform environment) — "
            "the stage machine itself ran in full"
        )

    return SimulationResult(
        playbook_id=playbook_id,
        playbook_name=entry.summary.name,
        steps=tuple(steps),
        final_stage=final_stage,
        outcome=outcome,
        outcome_reason=reason,
        redaction_kinds=tuple(dict.fromkeys(kinds)),
        missing=tuple(missing),
    )


def _runner_class() -> Any:
    module = donor().get("ghostline.playbook_runner")
    runner_cls = getattr(module, "PlaybookRunner", None)
    if runner_cls is None:
        raise SimulationUnavailable(
            "the donor's PlaybookRunner is not importable, so no stage machine is "
            "available to simulate"
        )
    return runner_cls


def _line_for(entry: Any, stage_name: str) -> str | None:
    """The greeting the donor would speak on entering ``stage_name``."""
    playbook = entry.playbook
    for config in playbook.sequence:
        if config.stage.name == stage_name and config.custom_prompt:
            return config.custom_prompt.strip()
    return None


def _redact_match(matched: str | None, redactor: Any) -> str | None:
    """A matched span is, by construction, the credential the stage was fishing for.

    The span is reported as its *kind* only. Returning the match would hand back
    exactly the thing the redaction boundary exists to withhold -- and on a CLOSE
    stage that match is the one-time code itself.
    """
    if matched is None:
        return None
    scrubbed = redactor.scrub(matched)
    if scrubbed.scrubbed:
        return f"matched ({', '.join(scrubbed.kinds)})"
    # Not credential-shaped: the pattern matched a state word ("yes", "married"),
    # which is the ordinary case and is safe to show.
    return matched
