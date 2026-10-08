"""The natural-language adapter seam (FR-025-052, T025-096) -- subordinate by construction.

The requirement is not "support natural language". It is that any natural-language
compilation be *subordinate* to the deterministic grammar. An adapter here therefore
cannot decide what a question means. Its only power is to propose text in the grammar of
:mod:`context.query_grammar`; the grammar decides whether that text parses and what it
means. A proposal that is not valid grammar raises :class:`QueryParseError` and there is
no fallback path that interprets it anyway.

That is why this module contains no model call. FR-025-061 forbids an LLM owning
admission, and a prompt inside the compiler is exactly where that would start. What the
module does provide is everything needed to *use* an adapter without trusting it:

:class:`ProposalRecord` captures the question, the proposed grammar text, and the
``ast_id`` that resulted -- or the parse failure. Replaying a record reproduces the
digest, which is what makes a natural-language query a re-runnable experiment under §36's
replay identity rather than a one-off.

:class:`RecordedProposalAdapter` replays such records instead of proposing anything. It is
the adapter used in tests, in replay, and anywhere a proposal must be reproducible. A live
adapter implements :class:`NaturalQueryAdapter` and inherits the same subordination,
because :func:`compile_proposal` is the only way its output becomes an AST.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from context.query_ast import QueryAST
from context.query_grammar import QueryParseError, parse


@dataclass(frozen=True, slots=True)
class ProposalRecord:
    """One natural-language compilation, with enough to reproduce it.

    ``ast_id`` is empty when the proposal was refused. Keeping refusals in the record
    rather than discarding them is deliberate: a proposal that stopped being grammatical is
    evidence about the question, and a replay that only stores successes cannot show that
    anything changed.
    """

    question: str
    proposed_text: str
    ast_id: str = ""
    refused: str = ""
    #: Which adapter produced it, and any model identity. Part of the §36 replay identity:
    #: the same question through a different adapter is a different experiment.
    adapter_ref: str = "recorded"

    @property
    def accepted(self) -> bool:
        return bool(self.ast_id) and not self.refused

    def as_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "proposed_text": self.proposed_text,
            "ast_id": self.ast_id,
            "refused": self.refused,
            "adapter_ref": self.adapter_ref,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ProposalRecord:
        return cls(
            question=str(payload.get("question", "")),
            proposed_text=str(payload.get("proposed_text", "")),
            ast_id=str(payload.get("ast_id", "") or ""),
            refused=str(payload.get("refused", "") or ""),
            adapter_ref=str(payload.get("adapter_ref", "recorded") or "recorded"),
        )


class NaturalQueryAdapter(Protocol):
    """Proposes grammar text for a question. Never interprets the result.

    The return type is the grammar's own surface syntax, not an AST. That is the whole
    contract: an adapter that returned an AST would be able to assert meaning directly,
    which is precisely what FR-025-052 rules out.
    """

    adapter_ref: str

    def propose(self, question: str) -> str: ...


@dataclass(frozen=True, slots=True)
class CompileOutcome:
    """What compiling a proposal produced, or why it did not."""

    record: ProposalRecord
    ast: QueryAST | None = None

    @property
    def accepted(self) -> bool:
        return self.ast is not None and self.record.accepted

    def as_dict(self) -> dict[str, Any]:
        return {
            "record": self.record.as_dict(),
            "ast": self.ast.as_dict() if self.ast else None,
        }


def compile_proposal(
    question: str,
    proposed_text: str,
    *,
    adapter_ref: str = "recorded",
    as_of: str = "",
) -> CompileOutcome:
    """Turn an adapter's proposal into an AST, through the deterministic grammar.

    The proposal is the only thing that varies. Everything that decides meaning --
    tokenizing, the productions, the completeness of the result -- is
    :func:`context.query_grammar.parse`, so a live adapter and a recorded one produce
    indistinguishable ASTs for the same proposal text.
    """
    try:
        ast = parse(proposed_text, as_of=as_of)
    except QueryParseError as exc:
        first_line = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        return CompileOutcome(
            record=ProposalRecord(
                question=question,
                proposed_text=proposed_text,
                refused=first_line,
                adapter_ref=adapter_ref,
            )
        )
    return CompileOutcome(
        record=ProposalRecord(
            question=question,
            proposed_text=proposed_text,
            ast_id=ast.ast_id,
            adapter_ref=adapter_ref,
        ),
        ast=ast,
    )


@dataclass(slots=True)
class RecordedProposalAdapter:
    """Replays recorded proposals. The default adapter, and the one tests use.

    A question with no recorded proposal raises :class:`KeyError` rather than guessing.
    Guessing is what an adapter without a record would have to do, and it would make the
    compiled AST depend on which questions happened to be recorded -- which is the
    opposite of the reproducibility this module exists to provide.
    """

    proposals: Mapping[str, str]
    adapter_ref: str = "recorded"

    def propose(self, question: str) -> str:
        try:
            return self.proposals[question]
        except KeyError:
            raise KeyError(
                f"no recorded proposal for {question!r}; "
                "record one before replaying this question"
            ) from None

    def compile(self, question: str, *, as_of: str = "") -> CompileOutcome:
        return compile_proposal(
            question,
            self.propose(question),
            adapter_ref=self.adapter_ref,
            as_of=as_of,
        )


@dataclass(slots=True)
class ProposalLedger:
    """Accumulates compilations so a run can be replayed from its own record.

    Appended to on every compile, accepted or refused. §36 asks for the recorded batch
    boundaries and the ordered sequence; a ledger of proposals is the query-side half of
    that, and it is what lets "the same input produced the same AST" be asserted against
    the run that actually happened rather than against a fresh compilation.
    """

    records: list[ProposalRecord] = field(default_factory=list)

    def record(self, outcome: CompileOutcome) -> CompileOutcome:
        self.records.append(outcome.record)
        return outcome

    def compile(
        self,
        adapter: NaturalQueryAdapter,
        question: str,
        *,
        as_of: str = "",
    ) -> CompileOutcome:
        """Propose, compile, and record in one step."""
        try:
            proposed = adapter.propose(question)
        except KeyError as exc:
            outcome = CompileOutcome(
                record=ProposalRecord(
                    question=question,
                    proposed_text="",
                    refused=str(exc).strip("'"),
                    adapter_ref=getattr(adapter, "adapter_ref", "unknown"),
                )
            )
            return self.record(outcome)
        return self.record(
            compile_proposal(
                question, proposed, adapter_ref=adapter.adapter_ref, as_of=as_of
            )
        )

    def as_dict(self) -> dict[str, Any]:
        return {"records": [record.as_dict() for record in self.records]}

    def replay(self, *, as_of: str = "") -> tuple[QueryAST | None, ...]:
        """Recompile every record and check the digests still hold.

        Returns the ASTs produced, in record order, with a ``None`` for each refusal. A
        replay whose digest differs from the recorded one returns a *different* AST, which
        is the signal :meth:`verify` turns into an error -- the mismatch is silent
        otherwise, because the AST is still perfectly well formed.
        """
        rebuilt: list[QueryAST | None] = []
        for record in self.records:
            outcome = compile_proposal(
                record.question,
                record.proposed_text,
                adapter_ref=record.adapter_ref,
                as_of=as_of,
            )
            rebuilt.append(outcome.ast)
        return tuple(rebuilt)

    def verify(self, *, as_of: str = "") -> list[str]:
        """Report records whose replay no longer reproduces the recorded digest.

        Returns the questions that drifted, so a caller can fail on them. Named rather
        than raised because a ledger may legitimately span an adapter change, and the
        useful answer is *which* questions moved, not a single exception.
        """
        drifted: list[str] = []
        for record, rebuilt in zip(self.records, self.replay(as_of=as_of), strict=True):
            replayed = rebuilt.ast_id if rebuilt else ""
            if replayed != record.ast_id:
                drifted.append(record.question)
        return drifted


def equivalent(outcomes: Sequence[CompileOutcome]) -> bool:
    """Whether several outcomes compiled to the same AST.

    The check FR-025-050 asks for, stated over outcomes so the golden cases can compare a
    structured parse against an adapter proposal directly rather than by eye.
    """
    digests = {outcome.record.ast_id for outcome in outcomes}
    return len(digests) == 1 and "" not in digests