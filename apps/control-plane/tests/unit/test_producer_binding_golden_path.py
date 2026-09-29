"""Phase 4C / C3: the golden path binds, and a capture end is not a mention.

Feature 021, spec FR-016, FR-018, FR-019, FR-094; brief §25 and §26; ``repair/ARBITRATION.md`` §8.

**What was broken.** :attr:`semantic_path.execution.SignalStep.discovered` was handed to
assembly holding deferred addresses, and assembly groups by participant reference — so every
discovered signal grouped under its own ``surface@…`` string, forever: uncorroborable,
unjoinable against any mention id the platform holds, and reported as though it had been read.
:class:`~domain.mention_occurrence_index.MentionOccurrenceIndex` existed, was tested, was
fail-closed, and **nothing on the path called it**. This file drives the real path with a real
producer and asserts the discovered signals carry real ``MN-`` ids when they reach assembly.

**Why the binding cannot be "reconcile the two addressings" by remapping.** The mention layer
addresses whole entity spans at extractor granularity; a producer addresses the cue group that
matched. For the golden sentence those are different spans of the same sentence, read by two
instruments, and :class:`MentionOccurrenceKey`'s five keys — capture, segment, span, normalised
surface, **extractor** — exist precisely so that is *two mentions* (FR-018). What 4C does is
register the producer's own read and resolve through that; the argument is on
:func:`extractors.signals.mentions.bind_producer_signals`.

**The consequence that is easy to get wrong and is asserted here.** A bound ``MN-`` is a mention
of the *producer's* occurrence, so a discovered signal does **not** group with the orchestrator's
declared signal under :func:`semantic_path.assembly.pair_of` — they name different mentions, and
the declared hypothesis is unaffected by any producer. That is the correct outcome, not a bug to
be fixed by merging the two ids.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from domain.capture import Capture
from domain.mention_occurrence_index import MENTION_ID_PREFIX
from domain.relation_identity import canonical_material, digest128
from extractors.signals.lexical import LexicalCueExtractor
from extractors.signals.metadata import MetadataExtractor

from semantic_path.execution import ExecutionStage, golden_request, run_until

pytestmark = pytest.mark.unit

#: A sentence the deterministic extractor set and the lexical cue table both read. The cue is
#: ``works_for``'s, and the cue groups are ``CEO`` and ``Acme`` — deliberately *not* the whole
#: entity spans the mention layer finds, which is the whole of the reconciliation problem.
_SENTENCE = "John Smith became CEO of Acme."


def _retrieval(document: str) -> Capture:
    """A real :class:`domain.capture.Capture` over ``document``.

    Needed rather than the derived one :func:`semantic_path.execution._acquisition_capture`
    builds, because that helper returns a capture the *request* did not carry and
    :attr:`ExecutionRequest.capture` stays ``None`` — so
    :attr:`semantic_path.execution.ExtractionScope.document_ref` is empty and the metadata
    producer refuses with ``metadata_document_ref_required``. It is the producer that surfaces
    the inconsistency, because the metadata producer is the only one that must name the
    retrieval it is describing. The inconsistency is reported rather than repaired here;
    repairing it would change ``RelationSignal.capture_ref``, which is in ``_material()``, and
    re-key every stored signal on the golden path.
    """
    return Capture(
        tenant_id="default-tenant",
        source_id="src-golden-path",
        source_family="src-golden-path",
        target_uri="urn:cognitive:golden:metadata-author",
        content_digest=digest128(canonical_material(document)),
        media_type="text/html",
        # A stated time from the request rather than a clock read, for the reason the capture
        # module gives: a defaulted fetch time would make replay non-deterministic (VII).
        fetched_at=datetime(2020, 6, 1, tzinfo=UTC),
    )


def test_a_discovered_producer_signal_reaches_assembly_with_real_mention_ids() -> None:
    """The path, end to end: a producer runs, its signal binds, assembly sees ``MN-``.

    The assertion is on :attr:`SignalStep.discovered` rather than on the binder, because the
    defect was never the binder — it was that nothing called it. A test on the binder alone
    would keep passing with the seam unwired, which is the state this file exists to end.
    """
    result = run_until(
        golden_request(_SENTENCE, producers=(LexicalCueExtractor(),)),
        ExecutionStage.SIGNALS,
    )
    step = result.signals
    assert step is not None
    assert step.discovered, "the lexical producer found nothing in a sentence it can read"
    for signal in step.discovered:
        for participant in signal.participants:
            assert participant.mention_ref.startswith(MENTION_ID_PREFIX), (
                f"participant {participant.mention_ref!r} reached assembly unresolved; a "
                "deferred address that reaches assembly is a participant that addresses nothing "
                "and reports as though it had been read"
            )
        # The address it came from is on the record, so a reader can recover which occurrence of
        # which document the end became (I-3).
        assert signal.extra["bound_participants"]
        assert all(
            address.startswith("surface@") for address in signal.extra["bound_participants"]
        )
    # And the declared hypothesis is untouched: it is the caller's own statement, addressed by
    # the mention layer's ids, and no producer is allowed to move it.
    assert step.declared.participants[0].mention_ref == result.mentions.subject.mention_id
    assert result.mentions.subject.mention_id.startswith(MENTION_ID_PREFIX)
    # The report is complete: nothing was seen and lost on the way.
    assert step.complete, step.unattributed
    # The declared signal and the discovered one are two pairs, because they name two different
    # mentions. Asserted because the tempting "fix" is to merge the ids, and this is why not.
    pairs = {candidate.subject_mention_ref for candidate in step.report.candidates}
    assert step.declared.participants[0].mention_ref in pairs
    assert step.declared.participants[0].mention_ref not in {
        p.mention_ref for s in step.discovered for p in s.participants
    }


def test_the_golden_path_is_unchanged_when_no_producer_runs() -> None:
    """The regression half, and the one a producer-binding change can quietly break.

    A request with no producers must produce exactly the candidates it produced before 4C: the
    declared hypothesis alone, one candidate, and no reference to any producer. Asserted on the
    candidate ids rather than on the stage, because an id is the thing a downstream row is keyed
    on and a stage that "succeeded" says nothing about what it wrote.
    """
    result = run_until(golden_request(_SENTENCE), ExecutionStage.SIGNALS)
    step = result.signals
    assert step is not None
    assert step.discovered == ()
    assert step.complete
    assert len(step.report.candidates) == 1
    candidate = step.report.candidates[0]
    assert candidate.signal_refs == (step.declared.signal_id,)
    assert candidate.extraction_rule_id == step.declared.producer_ref


def test_a_run_that_named_no_retrieval_is_refused_before_any_mention_id_is_minted() -> None:
    """A mention address is five keys and the first is the retrieval.

    The honest sequencing matters here, so it is stated rather than smoothed over. The **first**
    refusal is the mention layer's own: with no capture and no retrievable content,
    :func:`mention_id_for` has a blank ``capture_ref`` and
    :class:`~domain.mention_occurrence_index.MentionOccurrenceKey` refuses it with
    ``mention_occurrence_key_incomplete`` before a single ``MN-`` exists. 4C's own guard — the
    ``producer_occurrence_scope_unavailable`` below it — is therefore **defence in depth on this
    path**, and is asserted at the unit level instead
    (``test_binding_refuses_a_blank_capture_rather_than_minting_under_an_invented_scope``).

    What this test pins is the *property* rather than which layer says it: a run with no
    retrieval mints no mention id, and the refusal names the retrieval as the missing key.
    Asserted by code, because the alternative failure is a silent skip-and-report-as-absent,
    which is the confusion I-3 exists to prevent.
    """
    from domain.mention_occurrence_index import MentionBindingError

    from semantic_path.execution import SemanticExecutionError

    request = golden_request(
        _SENTENCE, producers=(LexicalCueExtractor(),), capture=None, content_digest=None
    )
    with pytest.raises((MentionBindingError, SemanticExecutionError)) as caught:
        run_until(request, ExecutionStage.SIGNALS)
    code = getattr(caught.value, "code", "")
    assert code in {"mention_occurrence_key_incomplete", "producer_occurrence_scope_unavailable"}
    assert "capture_ref" in str(caught.value) or "FR-018" in str(caught.value)


def test_a_capture_end_is_a_retrieval_and_survives_the_binding_as_itself() -> None:
    """C4 through the path: the metadata producer's document end, and what it becomes.

    ``<meta name="author" content="…">`` gives one end that is the *retrieval* rather than an
    occurrence. A capture id is already a real content-addressed durable id
    (:class:`domain.capture.Capture`), so it needs no binding and minting a mention for it would
    put a second identity on one fact (I-2). It is carried through unchanged, and the
    occurrence end beside it is bound normally — which is the pair of assertions that shows the
    decision was made per-end rather than by refusing the whole producer.
    """
    head = (
        '<head><meta name="author" content="jane@acme.example"></head>'
        "<p>John Smith works at Acme.</p>"
    )
    result = run_until(
        golden_request(
            head, producers=(MetadataExtractor(),), capture=_retrieval(head)
        ),
        ExecutionStage.SIGNALS,
    )
    step = result.signals
    assert step is not None
    assert step.discovered, "the metadata producer found nothing in a document with a meta tag"
    for signal in step.discovered:
        ends = [p.mention_ref for p in signal.participants]
        assert any(end.startswith("capture:") for end in ends), ends
        for end in ends:
            if end.startswith("capture:"):
                assert not end.startswith(MENTION_ID_PREFIX), (
                    "a capture end was minted a mention; the retrieval is already a durable id "
                    "and a mention for it would be a second identity on one fact (I-2)"
                )
            else:
                assert end.startswith(MENTION_ID_PREFIX), (
                    f"the occurrence end {end!r} was not bound, so the producer's read of this "
                    "document is unreconciled"
                )
        # The record says which end was which, so a reader need not parse the prefix to know.
        assert signal.extra["bound_participants"][0].startswith("capture:")
    assert step.complete, step.unattributed
