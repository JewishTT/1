"""The committed corpus: every case's fixture, and the record of what it produced.

``specs/018-world-substrate/spec.md`` FR-020 and SC-13, plan decision D-C. This
module is the **data**; :mod:`semantic_path.corpus` is the runner that drives the
real thirteen-stage path over it and proves three things (invariance, replay as a
fixed point, and the two acceptance chains).

**Why this is data and not a test suite.** The deliverable of feature 018 was
working code running over real sentences; this file is the *record* of what that
code produced, kept beside the code so a reviewer can diff a layer change without
running anything. There is no ``assert`` here and no expectation that a case
fails. A case that makes the path refuse is as legitimate as one that reaches the
worldline, and a test asserting success could not express it at all.

**How the eighteen cases are chosen.** Nine of them are the ordinary path, each
with exactly one instrument changed, so a difference is attributable to that
instrument. The other nine end in a *named refusal*, because the graded verdicts
only mean something if something is allowed to be unresolvable. Between them they
cover all eight situations FR-023 requires, and :func:`graded_coverage` reports
that coverage from the labels below rather than from a hand-maintained list, so a
label that goes missing shows up as an uncovered situation instead of silently
shrinking the corpus.

**What is deliberately absent.** No expected values are written by hand here
except through :data:`EXPECTED`, which is generated and regenerable - see the note
on that table. Writing 18 x 23 expected values by hand is how a baseline rots
silently; generating it and *diffing before regenerating* is how a change to the
recorded world is forced to be an explicit act.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any

import stream as acquisition_stream
from adapters.common_crawl import STREAM_ID as COMMON_CRAWL_STREAM_ID
from adapters.common_crawl import CommonCrawlAdapter
from adapters.sec_edgar import STREAM_ID as EDGAR_STREAM_ID
from adapters.sec_edgar import EdgarFullIndexAdapter
from semantic.blocking import Candidate as BlockingCandidate
from semantic.profiles import SemanticProfile
from semantic.registry import ConceptSchemeBackend, SemanticRegistry
from semantic.resolution import (
    ResolutionCandidate,
)
from semantic.vocabularies import Concept, ConceptScheme

from semantic_path.execution import (
    ExecutionStage,
    golden_request,
)

__all__ = [
    "CASES",
    "EXPECTED",
    "GRADED_SITUATIONS",
    "Acquisition",
    "CaseExpectation",
    "CaseSpec",
    "axis_report",
    "graded_coverage",
    "stream_registry",
]

#: The architect's sentence, and the fixture everything else is a variation of.
GOLDEN_SENTENCE = "John Smith became CEO of Acme in 2020."

#: Every case observes at this instant unless it overrides it. A wall clock would
#: make the corpus non-reproducible, and the whole point of FR-021 is that it is
#: not (constitution VII).
OBSERVED_AT = datetime(2020, 6, 1, tzinfo=UTC)

COMMON_CRAWL_STREAM = COMMON_CRAWL_STREAM_ID
EDGAR_STREAM = EDGAR_STREAM_ID

#: The eight situations FR-023 requires the corpus to exercise. Named here once so
#: :func:`graded_coverage` can report an uncovered situation by name rather than by
#: noticing a shorter list.
GRADED_SITUATIONS: tuple[str, ...] = (
    "ambiguity",
    "unresolvable",
    "cross_tenant_refusal",
    "open_world_unknown_type",
    "non_blocking_validation_finding",
    "non_convergent_collective",
    "temporal_conflict",
    "independence_groups",
)

#: The tenant every case runs in, and the one case 04 tries to read across.
TENANT = "default-tenant"
OTHER_TENANT = "t-other"

#: Must match the request's, or the context layer refuses every row and every case
#: resolves nothing - which looks exactly like a resolver bug and is not one.
INVESTIGATION_ID = "inv-golden-path"

#: The kind vocabulary the universe speaks. A bare ``organization`` is a noun; the
#: blocking kind stage compares against operator ``object_kinds``, which are type
#: references, so a row's ``kind`` has to be one of these to be comparable at all.
_TYPE_REFS = frozenset({"schema:Organization", "schema:Person", "schema:Document"})


# --------------------------------------------------------------------------- #
# Acquisition
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Acquisition:
    """One row of one data stream, as acquisition would hand it to a capture.

    Carries the raw record rather than a built :class:`~domain.capture.Capture`,
    so the capture is produced by the *adapter* through the real
    :class:`~stream.StreamRegistry`. A case that built its own capture would prove
    nothing about the seam it claims to exercise.

    ``ingest_batch_id`` defaults to the declared absence rather than a fabricated
    batch, for the same reason :data:`stream.UNBATCHED_INGEST_BATCH` exists.
    """

    stream_id: str
    record: Mapping[str, Any]
    ingest_batch_id: str = acquisition_stream.UNBATCHED_INGEST_BATCH
    ingest_attempt: int = 1


def stream_registry() -> acquisition_stream.StreamRegistry:
    """A fresh registry carrying both attached adapters.

    Fresh per call on purpose. A case that shared a registry with the case before
    it could see its captures, and the corpus's determinism claim rests on a case
    depending on its own fixture and nothing else.
    """
    registry = acquisition_stream.StreamRegistry()
    for adapter, adapter_ref in (
        (CommonCrawlAdapter(), "adapters.common_crawl:CommonCrawlAdapter"),
        (EdgarFullIndexAdapter(), "adapters.sec_edgar:EdgarFullIndexAdapter"),
    ):
        declared = adapter.declaration()
        registry.register(
            acquisition_stream.DataStream(
                stream_id=declared.stream_id,
                kind=declared.kind,
                temporality=declared.temporality,
                time_axes_supplied=frozenset(
                    binding.axis for binding in declared.axes if binding.supplied
                ),
                axis_bindings=tuple(declared.axes),
                adapter_ref=adapter_ref,
            ),
            adapter,
        )
    return registry


def _acquisition_capture(acquisition: Acquisition):
    """The one capture this case's acquisition produced, computed **once**.

    Built here and handed to the request as well, so the capture in the
    orchestrator's lineage and the capture the acquisition seam emitted are the same
    object by construction. Letting each side build its own would leave two `CAP-`
    addresses describing one fetch - which is the exact defect SC-14 was written to
    catch, reintroduced through the fixtures instead of the machinery.

    Returns ``None`` when the adapter declines the row, which the runner reports as
    a missing capture rather than substituting anything.
    """
    from stream import CaptureContext, StreamContractError

    try:
        return stream_registry().capture(
            acquisition.stream_id,
            dict(acquisition.record),
            context=CaptureContext(
                tenant_id=TENANT,
                ingest_batch_id=acquisition.ingest_batch_id,
                ingest_attempt=acquisition.ingest_attempt,
            ),
        )
    except StreamContractError:
        return None


def axis_report(stream_id: str) -> tuple[tuple[str, str, str], ...]:
    """``(axis, supplied, why)`` for one stream, read off its own declaration.

    The point of the table is the ``supplied=False`` rows: each one carries a
    stated reason, so "this stream cannot tell us when it was fetched" is a fact
    the corpus can print rather than an absence a reader has to infer.
    """
    declared = stream_registry().get(stream_id)
    return tuple(
        (binding.axis.value, str(binding.supplied).lower(), binding.reason or binding.source_field)
        for binding in declared.axis_bindings
    )


# --------------------------------------------------------------------------- #
# Vocabulary and the candidate universe
# --------------------------------------------------------------------------- #


def _concept_schemes() -> dict[str, ConceptScheme]:
    """The two schemes the corpus needs: the org hierarchy and a web scheme.

    Only ``PublicCompany -> Company -> Organization`` is load-bearing, and it is
    what makes an ambiguous mention ambiguous rather than unknown: two candidates
    whose names are both aliases of the same concept are genuinely indistinguishable
    from the vocabulary alone, which is the honest state for case 03.
    """
    orgs = ConceptScheme.from_concepts(
        (
            Concept(concept_id="org:Organization", scheme_id="org", pref_label="organization"),
            Concept(concept_id="org:Company", scheme_id="org", pref_label="company", broader=("org:Organization",)),
            Concept(
                concept_id="org:PublicCompany",
                scheme_id="org",
                pref_label="public company",
                alt_labels=("ПАО", "public company", "joint stock company"),
                broader=("org:Company",),
            ),
            Concept(
                concept_id="org:PrivateCompany",
                scheme_id="org",
                pref_label="private company",
                alt_labels=("Ltd", "private company"),
                broader=("org:Company",),
            ),
            Concept(
                concept_id="org:LegalPerson",
                scheme_id="org",
                pref_label="legal person",
                close_match=("schema:Person",),
            ),
        )
    )
    web = ConceptScheme.from_concepts(
        (
            Concept(concept_id="web:WebProfile", scheme_id="web", pref_label="web profile"),
            Concept(concept_id="web:Account", scheme_id="web", pref_label="account"),
        )
    )
    return {"org": orgs, "web": web}


def _profile(*type_refs: str) -> SemanticProfile:
    """A profile that *declares* ``type_refs`` and nothing else.

    An undeclared type is not a failure - it is ``UNKNOWN`` from the semantic
    stage, which is case 05. A profile that declared everything would make that
    case pass for the wrong reason.
    """
    return SemanticProfile(
        profile_id="corpus",
        version="1",
        type_refs=tuple(type_refs),
        applies_to=frozenset({"investigation", "source=common-crawl", "domain=corpus"}),
    )


def _default_profile() -> SemanticProfile:
    return _profile(
        "schema:Person",
        "schema:Organization",
        "schema:Company",
        "schema:Document",
    )


def _registry() -> SemanticRegistry:
    return SemanticRegistry(
        tenant_id=TENANT,
        backends=tuple(ConceptSchemeBackend(scheme) for scheme in _concept_schemes().values()),
    )


def _acme_acquisition() -> Acquisition:
    """The default acquisition: the golden sentence's document on Common Crawl.

    A function rather than a module constant so every case builds its own. A shared
    object would let one case's mutation reach another, and a case that depends on
    what ran before it cannot be compared to a run of itself.
    """
    return Acquisition(COMMON_CRAWL_STREAM, _acme_record())


def _acme_record(**overrides: Any) -> dict[str, Any]:
    """One Common Crawl index row for the golden sentence's document.

    ``digest`` is required: an index row that does not name bytes is not a capture
    this stream can honestly produce, and the adapter refuses rather than hashing
    the URL and calling it content.
    """
    record = {
        "url": "https://example.test/2020/ceo",
        "timestamp": "20200601120000",
        "status": "200",
        "digest": "sha256:4ec8131d84d000ff209204a6fc974015e8f5a0c1d0a7f2b3c4d5e6f70819200",
        "crawl": "CC-MAIN-2020-24",
        "subset": "warc",
        "warc_filename": "CC-MAIN-2020-24-c0000.warc.gz",
        "offset": 1234,
        "length": 5678,
    }
    record.update(overrides)
    return record


def _edgar_record(**overrides: Any) -> dict[str, Any]:
    """One SEC EDGAR full-index row.

    ``date filed`` is the registrar's acceptance instant, so it binds to
    ``published_at``. It is *not* a fetch time, and the adapter says so by
    declaring ``fetched_at`` unsupplied.
    """
    record = {
        "document_path": "https://www.sec.gov/Archives/edgar/data/0000320193/0000320193200000",
        "date filed": "20200601",
        "content_digest": "sha256:9a1f4c0b7d2e8536c14ba907f3e6d5c4b3a2918076f5e4d3c2b1a09f8e7d6c5",
        "content_length": "18244",
        "media_type": "text/html",
    }
    record.update(overrides)
    return record


def _entity_record(
    entity_ref: str,
    name: str,
    *,
    aliases: tuple[str, ...] = (),
    kind: str = "organization",
    type_refs: tuple[str, ...] = ("schema:Organization",),
    supporting_groups: tuple[str, ...] = ("grp-registry",),
    independence_group: str = "grp-registry",
    tenant_id: str = TENANT,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    support_mention_ids: tuple[str, ...] = (),
) -> ResolutionCandidate:
    """One row of the entity universe resolution is allowed to match against.

    ``entity_ref`` empty means the row has *no established identity* yet, which is
    what case 15 needs: the resolver must mint an anchor rather than adopt one.

    Three fields here look like defaults and are not. ``kind`` is the *type
    reference* rather than a bare ``organization``, because the kind stage of
    blocking compares against the operator's ``object_kinds`` - which are type
    references - and a bare noun simply never matches. ``profile_id`` is empty
    because a row that names a profile which is not the active one is a genuine
    regime mismatch, and every case here runs under the request's own profile.
    ``investigation_id`` must be the request's, or the context layer legitimately
    refuses the row and every case resolves nothing.
    """
    return ResolutionCandidate(
        entity_ref=entity_ref,
        name=name,
        kind=kind if kind in _TYPE_REFS else (type_refs[0] if type_refs else kind),
        type_refs=type_refs,
        aliases=aliases,
        tenant_id=tenant_id,
        investigation_id=INVESTIGATION_ID,
        profile_id="",
        profile_version="",
        ontology_version="ontology-1",
        normalization_version="norm-1",
        source_family="src-registry",
        independence_group=independence_group,
        valid_from=valid_from,
        valid_to=valid_to,
        observed_at=OBSERVED_AT,
        support_mention_ids=support_mention_ids,
        supporting_groups=supporting_groups,
    )


def _acme() -> ResolutionCandidate:
    """The established organisation the golden sentence is about."""
    return _entity_record("ENT-acme", "Acme Corporation", aliases=("Acme",))


def _smith() -> ResolutionCandidate:
    """The established person. ``kind`` and ``type_refs`` differ from the org row,
    which is what lets the kind stage of blocking narrow before the name stage does.
    """
    return _entity_record(
        "ENT-smith",
        "John Smith",
        kind="person",
        type_refs=("schema:Person",),
        independence_group="grp-registry",
    )


def _decoys() -> tuple[BlockingCandidate, ...]:
    """Blocking-only rows: they widen the universe without being resolvable.

    Kept out of the resolution universe deliberately. A decoy that resolution could
    match would make a case's verdict depend on a row that exists only to make the
    reduction ratio look good.
    """
    return (
        BlockingCandidate(
            entity_ref="DECOY-globex",
            name="Globex",
            kind="organization",
            type_refs=("schema:Organization",),
        ),
        BlockingCandidate(
            entity_ref="DECOY-untyped",
            name="Untyped Holding",
            kind="",
            type_refs=(),
        ),
    )


# --------------------------------------------------------------------------- #
# The case
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CaseSpec:
    """One case: what it says, what it runs over, and what it is for.

    ``until`` is the stage the case is expected to reach. A refusal case stops
    early *by design* - the refusal is the result, and running further would mean
    inventing participants for a claim that was never admitted.

    ``request`` is a fully specified :class:`~semantic_path.execution.ExecutionRequest`
    with every timestamp supplied, because the corpus's determinism claim is that
    two runs of the same request are byte-identical and a clock would falsify it.
    """

    case_id: str
    sentence: str
    acquisition: Acquisition
    request: Any
    labels: tuple[str, ...]
    expected_refusal: str = ""
    until: ExecutionStage = ExecutionStage.WORLDLINE
    md: str = ""


def _case(
    case_id: str,
    sentence: str,
    *,
    labels: tuple[str, ...],
    acquisition: Acquisition | None = None,
    expected_refusal: str = "",
    until: ExecutionStage = ExecutionStage.WORLDLINE,
    request_overrides: dict[str, Any] | None = None,
) -> CaseSpec:
    """Build one case, with the golden fixture as the base and one thing changed."""
    overrides = dict(request_overrides or {})
    request = golden_request(
        sentence=sentence,
        acquisition=acquisition or Acquisition(COMMON_CRAWL_STREAM, _acme_record()),
        **overrides,
    )
    return CaseSpec(
        case_id=case_id,
        sentence=sentence,
        acquisition=acquisition or Acquisition(COMMON_CRAWL_STREAM, _acme_record()),
        request=request,
        labels=labels,
        expected_refusal=expected_refusal,
        until=until,
    )


# --------------------------------------------------------------------------- #
# The eighteen cases
# --------------------------------------------------------------------------- #


def _cases() -> tuple[CaseSpec, ...]:
    """The corpus, in the order the runner drives it.

    Grouped as: the ordinary path first, so a reader meets the working case before
    the failing ones; then one instrument changed per case; then the refusals, the
    second stream and the minted anchor.

    Every case's request carries the capture its own acquisition produced, computed
    once by :func:`_acquisition_capture`. That is what makes the orchestrator's
    lineage and the acquisition seam agree on one ``CAP-`` address instead of two
    addresses describing one fetch.
    """
    edgar = Acquisition(EDGAR_STREAM, _edgar_record())
    return (
        CaseSpec(
            case_id="c01-golden-ceo-acme",
            sentence=GOLDEN_SENTENCE,
            acquisition=_acme_acquisition(),
            request=golden_request(capture=_acquisition_capture(_acme_acquisition())),
            labels=("golden_path",),
            md=(
                "The architect's sentence, unmodified, over the full registry universe.\n"
                "\n"
                "The only case whose purpose is to be the ordinary path: two mentions, a cue\n"
                "read as a relation, both ends resolved against established identities, a\n"
                "regime that round-tripped through storage, one claim, one edge, one worldline\n"
                "event. Every other case is this one with one instrument changed, so a\n"
                "difference in any of them is attributable to the change."
            ),
        ),
        CaseSpec(
            case_id="c02-unresolvable-beta-corp",
            sentence="John Smith joined Beta Corp after leaving Acme.",
            acquisition=_acme_acquisition(),
            request=golden_request(
                sentence="John Smith joined Beta Corp after leaving Acme.",
                capture=_acquisition_capture(_acme_acquisition()),
                resolution_candidates=(_acme(), _smith()),
            ),
            labels=("unresolvable",),
            expected_refusal="object_end_unresolved",
            until=ExecutionStage.RESOLUTION,
            md=(
                "``Beta Corp`` has no row in the universe and no alias that would reach one.\n"
                "\n"
                "The point is that the path *refuses* rather than inventing a participant. An\n"
                "unresolved end is a result, and a resolver that quietly picked the nearest\n"
                "candidate would be indistinguishable from one that resolved correctly - right\n"
                "up until the day it was wrong about something that mattered."
            ),
        ),
        CaseSpec(
            case_id="c03-ambiguous-acme-twin",
            sentence=GOLDEN_SENTENCE,
            acquisition=_acme_acquisition(),
            request=golden_request(
                capture=_acquisition_capture(_acme_acquisition()),
                resolution_candidates=(
                    _acme(),
                    _entity_record("ENT-acme-twin", "Acme", aliases=("Acme",)),
                    _smith(),
                ),
            ),
            labels=("ambiguity",),
            expected_refusal="object_end_ambiguous",
            until=ExecutionStage.RESOLUTION,
            md=(
                "Two established records, both reachable from ``Acme``, both organisation-kind.\n"
                "\n"
                "Ambiguity is the result and the whole design rests on it being one: both\n"
                "candidates are listed, the decision names no entity, and nothing downstream is\n"
                "asked to proceed. This is the case that separates a resolver from a coin-flip,\n"
                "and it is also the case the alias-blocking fix made reachable - before it a\n"
                "mention of ``Acme`` did not even see the twin and the answer was\n"
                "``unresolved``, which reads like absence of evidence rather than what it was."
            ),
        ),
        CaseSpec(
            case_id="c04-cross-tenant-acme",
            sentence=GOLDEN_SENTENCE,
            acquisition=_acme_acquisition(),
            request=golden_request(
                capture=_acquisition_capture(_acme_acquisition()),
                resolution_candidates=(
                    _entity_record("ENT-acme", "Acme Corporation", tenant_id=OTHER_TENANT),
                    _smith(),
                ),
            ),
            labels=("cross_tenant_refusal",),
            expected_refusal="object_end_unresolved",
            until=ExecutionStage.RESOLUTION,
            md=(
                "The only match for ``Acme`` lives in another tenant.\n"
                "\n"
                "A refused cross-tenant candidate must not become a *low score* - it must not be\n"
                "comparable at all, because scoring it and ranking it below the tenant's own rows\n"
                "is how a refusal becomes a disclosure. The path refuses at the comparison, not\n"
                "after it, and the corpus records which layer refused."
            ),
        ),
        CaseSpec(
            case_id="c05-open-world-shell-company",
            sentence=GOLDEN_SENTENCE,
            acquisition=_acme_acquisition(),
            request=golden_request(
                capture=_acquisition_capture(_acme_acquisition()),
                type_refs={"person": "schema:Person", "org": "local:shell_company"},
                resolution_candidates=(
                    _entity_record("ENT-shell", "Acme Corporation", aliases=("Acme",)),
                    _smith(),
                ),
            ),
            labels=("open_world_unknown_type",),
            md=(
                "The object end is *recorded* as ``local:shell_company`` - declared by no\n"
                "profile, no vocabulary and no ontology.\n"
                "\n"
                "It flows through the entire path anyway, with the semantic stage returning\n"
                "``UNKNOWN`` (``not_declared_in_profile``) rather than a failure, and the claim is\n"
                "materialised. This is feature 017's load-bearing claim, and it is worth having in\n"
                "a corpus rather than only in a spec: a type nobody declared must be\n"
                "*admissible*, and a gate that rejected it would turn this case from a claim into\n"
                "a control.\n"
                "\n"
                "The undeclared type is on the request, not on the universe row, and that is\n"
                "deliberate. A candidate's ``type_refs`` is simultaneously the blocking filter\n"
                "and the record the operator's contract reads, so a disagreement typed there\n"
                "removes the candidate before any contract is consulted - and the interesting\n"
                "question is what the pipeline *recorded*, not what one row happened to carry."
            ),
        ),
        CaseSpec(
            case_id="c06-wrong-range-document",
            sentence=GOLDEN_SENTENCE,
            acquisition=_acme_acquisition(),
            request=golden_request(
                capture=_acquisition_capture(_acme_acquisition()),
                type_refs={"person": "schema:Person", "org": "schema:Document"},
                resolution_candidates=(
                    _entity_record("ENT-acme-doc", "Acme Corporation", aliases=("Acme",)),
                    _smith(),
                ),
            ),
            labels=("non_blocking_validation_finding",),
            md=(
                "``Person --works_for--> Document``: the claim records its object as a\n"
                "``schema:Document`` under a ``works_for`` operator that declares an organisation.\n"
                "The semantic stage's finding is ``INVALID``.\n"
                "\n"
                "The claim is still materialised, the edge is still projected, and the admission\n"
                "decision is ``operator_view_admits_claim``. A contract contradiction is a fact\n"
                "about the world and is reported; an operator's admission is a separate decision\n"
                "and defaults to admitting. Collapsing the two is how a validation warning\n"
                "becomes a silent deletion - and the finding is on the report either way, so\n"
                "nothing is lost by not gating on it.\n"
                "\n"
                "The disagreement is typed on the request, not on the universe row. A candidate's\n"
                "``type_refs`` is both the blocking filter and the record the contract reads, so\n"
                "a mismatch typed there prunes the candidate before any contract runs - and this\n"
                "case exists precisely to show the contract being reached."
            ),
        ),
        CaseSpec(
            case_id="c07-temporal-disjoint-acme",
            sentence=GOLDEN_SENTENCE,
            acquisition=_acme_acquisition(),
            request=golden_request(
                capture=_acquisition_capture(_acme_acquisition()),
                resolution_candidates=(
                    _entity_record(
                        "ENT-acme-old",
                        "Acme Corporation",
                        aliases=("Acme",),
                        valid_from=datetime(2010, 1, 1, tzinfo=UTC),
                        valid_to=datetime(2015, 1, 1, tzinfo=UTC),
                    ),
                    _smith(),
                ),
            ),
            labels=("temporal_conflict",),
            expected_refusal="object_end_unresolved",
            until=ExecutionStage.RESOLUTION,
            md=(
                "The only candidate's validity window closed in 2015; the reading is from 2020.\n"
                "\n"
                "The window conflict is a ``CONFLICT`` and it *excludes* the candidate, where a\n"
                "type mismatch only weakens. That asymmetry is deliberate and worth stating\n"
                "because it is a policy choice rather than a rule: a contradiction may exclude,\n"
                "an absence may not. The corpus holds both cases so the asymmetry is visible in\n"
                "the recorded verdicts rather than only in a docstring."
            ),
        ),
        CaseSpec(
            case_id="c08-temporal-span-point-claim",
            sentence=GOLDEN_SENTENCE,
            acquisition=_acme_acquisition(),
            request=golden_request(
                capture=_acquisition_capture(_acme_acquisition()),
                valid_to=datetime(2023, 1, 1, tzinfo=UTC),
                resolution_candidates=(_acme(), _smith()),
            ),
            labels=("temporal_conflict", "non_blocking_validation_finding"),
            md=(
                "A point-semantics relation handed a two-year span.\n"
                "\n"
                "The second kind of temporal conflict: not a candidate that cannot be the thing,\n"
                "but a claim whose window contradicts its own operator's declared semantics.\n"
                "Reaches the worldline anyway, with ``interval_on_point_claim`` recorded - the\n"
                "temporal stage reports and the admission stage decides."
            ),
        ),
        CaseSpec(
            case_id="c09-nonconvergent-collective",
            sentence=GOLDEN_SENTENCE,
            acquisition=_acme_acquisition(),
            request=golden_request(
                capture=_acquisition_capture(_acme_acquisition()),
                collective_max_iterations=1,
                resolution_candidates=(_acme(), _smith()),
            ),
            labels=("non_convergent_collective",),
            md=(
                "The collective step is capped at one iteration on an input that needs more.\n"
                "\n"
                "The collective algorithm terminates by a decreasing potential, so this case is\n"
                "about the *guard* rather than about a real oscillation: on hitting the cap the\n"
                "resolver returns the pre-collective sets with ``applied=False`` and a note\n"
                "naming the cap. It must never loop, and it must never quietly return a partial\n"
                "propagation as though it had finished."
            ),
        ),
        CaseSpec(
            case_id="c10-independence-groups-acme",
            sentence=GOLDEN_SENTENCE,
            acquisition=_acme_acquisition(),
            request=golden_request(
                capture=_acquisition_capture(_acme_acquisition()),
                resolution_candidates=(
                    _entity_record(
                        "ENT-acme",
                        "Acme Corporation",
                        aliases=("Acme",),
                        supporting_groups=("grp-registry", "grp-filings"),
                    ),
                    _smith(),
                ),
            ),
            labels=("independence_groups",),
            md=(
                "The organisation is backed by two independent groups rather than one.\n"
                "\n"
                "This case exists because the corroboration was being computed and thrown away:\n"
                "the resolver counted independent support, the claim carried\n"
                "``independent_source_count == 0``, and the ``cross_source`` stage could only\n"
                "ever answer ``UNKNOWN`` with a vacuous reason. Now the groups reach the\n"
                "claim's identity material and the stage answers ``single_independence_group`` -\n"
                "a real verdict about real evidence, which is the difference between graded and\n"
                "decorative."
            ),
        ),
        CaseSpec(
            case_id="c11-no-org-mention-acme",
            sentence="John Smith left Acme in 2023.",
            acquisition=_acme_acquisition(),
            request=golden_request(
                sentence="John Smith left Acme in 2023.",
                capture=_acquisition_capture(_acme_acquisition()),
            ),
            labels=("mention_refusal",),
            expected_refusal="no_mention_of_kind",
            until=ExecutionStage.CONTEXT,
            md=(
                "``left Acme`` is not a role cue, so the relation-aware reader finds no object\n"
                "and ``Acme`` is not an organisation mention.\n"
                "\n"
                "Worth having precisely because it is the case the cue shim would have papered\n"
                "over. A sentence with no relation cue must still yield its plain typed mentions\n"
                "and no relational reading, and it must not error - the absence of a reading is a\n"
                "reading of absence."
            ),
        ),
        CaseSpec(
            case_id="c12-ru-director-romashka",
            sentence="Иван Петров был директором Ромашка в 2019.",
            acquisition=_acme_acquisition(),
            request=golden_request(
                sentence="Иван Петров был директором Ромашка в 2019.",
                capture=_acquisition_capture(_acme_acquisition()),
                language="ru",
                resolution_candidates=(
                    _entity_record("ENT-romashka", "Ромашка", aliases=("Ромашка",)),
                    _entity_record(
                        "ENT-petrov",
                        "Иван Петров",
                        kind="person",
                        type_refs=("schema:Person",),
                    ),
                ),
            ),
            labels=("second_cue_row",),
            md=(
                "The Russian cue row, over a sentence whose organisation has no legal form either.\n"
                "\n"
                "The point of the relational reader being *data* (``RELATION_CUES``) rather than a\n"
                "function per language is that a third relation is a third row. This case is what\n"
                "makes that claim testable instead of merely stated."
            ),
        ),
        CaseSpec(
            case_id="c13-initech-director",
            sentence="Mary Jones is a director of Initech.",
            acquisition=_acme_acquisition(),
            request=golden_request(
                sentence="Mary Jones is a director of Initech.",
                capture=_acquisition_capture(_acme_acquisition()),
                resolution_candidates=(
                    _entity_record("ENT-initech", "Initech"),
                    _entity_record(
                        "ENT-jones",
                        "Mary Jones",
                        kind="person",
                        type_refs=("schema:Person",),
                    ),
                ),
            ),
            labels=("names_in_no_concept",),
            md=(
                "Neither name resolves to a concept in any scheme.\n"
                "\n"
                "Open world at the vocabulary layer as well as the profile layer: the extractor\n"
                "reads the cue and types the object from the *affordance*, not from a concept\n"
                "lookup, so an unrecognised organisation name is still an organisation. A\n"
                "vocabulary that had to know every name before extraction could proceed would be\n"
                "the fixed ontology this platform was built to stop being."
            ),
        ),
        CaseSpec(
            case_id="c14-acquired-beta-corp",
            sentence="Acme acquired Beta Corp in 2021.",
            acquisition=edgar,
            request=golden_request(
                sentence="Acme acquired Beta Corp in 2021.",
                capture=_acquisition_capture(edgar),
                subject_kind="organization",
                object_kind="org",
            ),
            labels=("acquired_verb_is_no_cue", "edgar_stream"),
            expected_refusal="no_mention_of_kind",
            until=ExecutionStage.MENTIONS,
            md=(
                "``acquired`` is a real relation in the world and is **not** one of the cues.\n"
                "\n"
                "Recorded so the corpus does not quietly imply the cue table is a general verb\n"
                "inventory. It is a table of cues the reader understands; ``acquired`` would be a\n"
                "third ``RelationCue`` row and a second operator, and until it is one, this\n"
                "sentence yields mentions and no relation. Also the EDGAR stream, whose\n"
                "acceptance instant binds ``published_at`` and whose fetch time is declared\n"
                "absent."
            ),
        ),
        CaseSpec(
            case_id="c15-minted-identity-anchor",
            sentence=GOLDEN_SENTENCE,
            acquisition=_acme_acquisition(),
            request=golden_request(
                capture=_acquisition_capture(_acme_acquisition()),
                resolution_candidates=(
                    _entity_record("", "Acme Corporation", aliases=("Acme",)),
                    _entity_record(
                        "",
                        "John Smith",
                        kind="person",
                        type_refs=("schema:Person",),
                    ),
                ),
            ),
            labels=("minted_anchor",),
            md=(
                "Neither end has an established identity, so the resolver must **mint** one.\n"
                "\n"
                "The case SC-1 is about. An ``ENT-`` is derived from an anchor mention and the\n"
                "anchor is *recorded*, never re-derived from the current set - so a later mention\n"
                "joins this entity rather than minting a second one. The control that matters is\n"
                "running the same resolution with the caller's scope discarded and the durable\n"
                "identity re-read: the ``ENT-`` must be unchanged. An identity that depends on a\n"
                "caller remembering something is not an identity."
            ),
        ),
        CaseSpec(
            case_id="c16-headquarters-london",
            sentence="Acme is headquartered in London.",
            acquisition=_acme_acquisition(),
            request=golden_request(
                sentence="Acme is headquartered in London.",
                capture=_acquisition_capture(_acme_acquisition()),
                object_kind="place",
            ),
            labels=("place_extent", "mention_refusal"),
            expected_refusal="no_mention_of_kind",
            until=ExecutionStage.CONTEXT,
            md=(
                "``London`` is extracted as a place, and the case asks for a place as the object\n"
                "of ``works_for``.\n"
                "\n"
                "A *kind* that exists is still not a kind that fits, and the request is refused\n"
                "on the mention rather than on the relation. Keeps the two failures apart:\n"
                "nothing was found, versus something was found that cannot stand here."
            ),
        ),
        CaseSpec(
            case_id="c17-visited-kazan",
            sentence="John Smith visited Kazan in 2020.",
            acquisition=_acme_acquisition(),
            request=golden_request(
                sentence="John Smith visited Kazan in 2020.",
                capture=_acquisition_capture(_acme_acquisition()),
                object_kind="place",
            ),
            labels=("no_cue_still_typed", "mention_refusal"),
            expected_refusal="object_end_unresolved",
            until=ExecutionStage.MENTIONS,
            md=(
                "Person and place, no cue, no relational reading.\n"
                "\n"
                "The plain case: extraction is useful without relation. A corpus made only of\n"
                "relations would imply the relational reader is the point of extraction, and it\n"
                "is not - it is one of the instruments.\n"
                "\n"
                "The refusal is ``object_end_unresolved`` rather than ``no_mention_of_kind``\n"
                "because both mentions *were* found: the failure is that no universe row stands\n"
                "for a place. That is the distinction case 16 draws from the other side, and\n"
                "keeping both in the corpus is what stops the two failures from being conflated\n"
                "into one code."
            ),
        ),
        CaseSpec(
            case_id="c18-edgar-registrar-instant",
            sentence=GOLDEN_SENTENCE,
            acquisition=edgar,
            request=golden_request(
                capture=_acquisition_capture(edgar),
                resolution_candidates=(_acme(), _smith()),
            ),
            labels=("edgar_stream",),
            md=(
                "The golden path over the second stream.\n"
                "\n"
                "Same sentence, same result, different acquisition fact: the capture's basis is\n"
                "``publication`` rather than ``index_observation``, and its fetch time is absent\n"
                "in both cases for two *different* stated reasons. This is the case that shows\n"
                "the seam is a seam and not one adapter wearing two names."
            ),
        ),
    )


CASES: tuple[CaseSpec, ...] = _cases()


def graded_coverage() -> tuple[tuple[str, tuple[str, ...]], ...]:
    """``(situation, case ids)`` for every FR-023 situation, computed from labels.

    Derived rather than maintained, so a label that stops being applied shows up as
    an uncovered situation in the runner's own output instead of quietly shrinking
    what the corpus claims to prove.
    """
    return tuple(
        (
            situation,
            tuple(case.case_id for case in CASES if situation in case.labels),
        )
        for situation in GRADED_SITUATIONS
    )


# --------------------------------------------------------------------------- #
# The recorded world
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CaseExpectation:
    """What one case produced, committed, and compared on every run.

    Every field is a read of a real object the path produced, never a restatement
    of the fixture. The five :attr:`layer_digests` are the invariance layers
    themselves (FR-021), committed per case so a reviewer can see a layer change in
    a diff without running anything, and covering the exact identifiers of
    everything the readable fields do not spell out.
    """

    case_id: str
    reached: str
    refusal: str
    mention_values: tuple[tuple[str, str], ...]
    extractor_output: tuple[tuple[str, str], ...]
    mentions_reached: bool
    identity_refusals: tuple[str, ...]
    verdicts: tuple[tuple[str, str, str], ...]
    decision_ids: tuple[str, ...]
    decision_fingerprints: tuple[str, ...]
    identity_refs: tuple[str, ...]
    context_refs: tuple[tuple[str, str], ...]
    capture_refs: tuple[tuple[str, str, str, str], ...]
    claim_ids: tuple[tuple[str, str], ...]
    validation_verdicts: tuple[tuple[str, str, str], ...]
    adverse_codes: tuple[str, ...]
    materialisation: str
    lineage_backward_kinds: tuple[str, ...]
    lineage_forward_kinds: tuple[str, ...]
    lineage_digests: tuple[tuple[str, str], ...]
    edge_refs: tuple[tuple[str, str, str], ...]
    worldline_refs: tuple[str, ...]
    layer_digests: Mapping[str, str]

    def __hash__(self) -> int:
        """Hash over the identifying fields only, skipping the mapping.

        ``@dataclass(frozen=True)`` generates a hash over *every* field, and
        :attr:`layer_digests` is a mapping, so the generated one raises
        ``TypeError: unhashable type: 'dict'`` for every value. A recorded
        expectation is looked up by ``case_id`` and compared field by field, so the
        one thing a hash must agree with is the identity - and hashing the whole
        record would have required either freezing the mapping or dropping a field
        from identity that matters. Every other field *is* included, so two different
        expectations for one case cannot collide.
        """
        return hash(
            (
                self.case_id,
                self.reached,
                self.refusal,
                self.mention_values,
                self.verdicts,
                self.decision_ids,
                self.claim_ids,
                self.adverse_codes,
                self.materialisation,
            )
        )


#: What each case produced when it was recorded, compared on every run.
#:
#: Regenerate deliberately after an intentional change, never to make a red run
#: green, and read the printed diff first: a moved field is a claim about what the
#: change did. A baseline that can be rewritten without a human reading the delta
#: is not a baseline, it is a mirror.
#: What each case produced when it was recorded, compared on every run.
#: Regenerate deliberately after an intentional change, never to make a red run
#: green, and read the printed diff first: a moved field is a claim about what the
#: change did.
#: What each case produced when it was recorded, compared on every run.
#: Regenerate deliberately after an intentional change, never to make a red run
#: green, and read the printed diff first: a moved field is a claim about what the
#: change did.
#: What each case produced when it was recorded, compared on every run.
#: Regenerate deliberately after an intentional change, never to make a red run
#: green, and read the printed diff first: a moved field is a claim about what the
#: change did.
#: What each case produced when it was recorded, compared on every run.
#: Regenerate deliberately after an intentional change, never to make a red run
#: green, and read the printed diff first: a moved field is a claim about what the
#: change did.
EXPECTED: Mapping[str, CaseExpectation] = MappingProxyType(
    {
    'c01-golden-ceo-acme': CaseExpectation(
        case_id='c01-golden-ceo-acme',
        reached='worldline',
        refusal='',
        mention_values=(('person', 'John Smith'), ('org', 'Acme')),
        extractor_output=(('person', 'John Smith'), ('org', 'Acme')),
        mentions_reached=True,
        identity_refusals=(),
        verdicts=(('Acme', 'resolved', 'ENT-161bfa68d0cd4fec89648ca41a89cb1f'), ('John Smith', 'resolved', 'ENT-d15ec1a066455daa3d3faa2e5ad02e52')),
        decision_ids=('RES-f68900b2c65113228897ae8d36820cc4', 'RES-35f3f4036f7ab5d83528e813eb11bf96'),
        decision_fingerprints=('ad5459cbae73e5875a977a31e53565ab', '114009138672815ac2e0f885ca69a57e'),
        identity_refs=('ENT-161bfa68d0cd4fec89648ca41a89cb1f', 'ENT-d15ec1a066455daa3d3faa2e5ad02e52'),
        context_refs=(('observation', 'OBS-0ee0b0449303bd4ca02f8aa3639eab7d'), ('event', 'EVT-0e131d761d3b534e39ba3a343ee5b844'), ('context', 'CX-80759126ea0dc6e6e5d2cdd33a513d23'), ('regime', 'e3ad14842893fa56538726e7bdfaecd6'), ('regime_record', 'd1d6dcc56e751dda2115cd6c4042daf8'), ('interpreted_context', 'CX-15a99f0e005fb033e0983864ea8e7daa'), ('derived_capture', 'CAP-49307347ab61496ec9cf9f68bf0c0664')),
        capture_refs=(('common-crawl.cdx', 'CAP-49307347ab61496ec9cf9f68bf0c0664', 'index_observation', 'absent'),),
        claim_ids=(('RC-7a7fb65c44078fa36a1d7aba46242bb0', 'RL-525273cbaaaf4805b71f3489229fce10'),),
        validation_verdicts=(('structural', 'valid', 'structural_contract_satisfied'), ('semantic', 'valid', 'domain_range_satisfied'), ('temporal', 'valid', 'temporal_contract_satisfied'), ('provenance', 'valid', 'provenance_established'), ('cross_source', 'unknown', 'single_independence_group'), ('graph_level', 'unknown', 'graph_view_absent')),
        adverse_codes=(),
        materialisation='operator_view_admits_claim',
        lineage_backward_kinds=('assertion', 'assertion', 'mention', 'mention', 'segment', 'segment', 'observation', 'capture', 'source'),
        lineage_forward_kinds=('capture', 'observation', 'segment', 'segment', 'mention', 'mention', 'candidate', 'assertion', 'assertion', 'relation', 'relation', 'entity', 'entity'),
        lineage_digests=(('backward', '7d6f4ee625688c665aad01d206f996d9'), ('forward', '0281c39dfed9526c0db45ac291309777')),
        edge_refs=(('RC-7a7fb65c44078fa36a1d7aba46242bb0', 'HE-203fa4782176d027', '6cb1b4675c1c0bf367a7466aad41879c'),),
        worldline_refs=('WL-77d6b497ff11bfc40a76115774946c1b', 'EV-ed01b3458c5646acfb469181d6bcd081'),
        layer_digests={'identity': '9c55b3fd6e84fbd3eec8a7e23845d57a', 'decisions': '41f5630497c7417d702238d06dcc4537', 'claims': '857d92b789a7b3fdce3351a3710745ff', 'context': 'dc2e1594c123d4043cfa093845e839b8', 'edges': '06601949f4c4635bd442c9237c6db44b'},
    ),
    'c02-unresolvable-beta-corp': CaseExpectation(
        case_id='c02-unresolvable-beta-corp',
        reached='resolution',
        refusal='object_end_unresolved',
        mention_values=(('person', 'John Smith'), ('org', 'Beta Corp')),
        extractor_output=(('person', 'John Smith'), ('org', 'Beta Corp')),
        mentions_reached=True,
        identity_refusals=(),
        verdicts=(('John Smith', 'resolved', 'ENT-smith'), ('Beta Corp', 'unresolved', '')),
        decision_ids=('RES-e7c8f1e6cb16c50b749b37c1b39637f3', 'RES-dc5dfdf220eb41d716545e2ec0664123'),
        decision_fingerprints=('174f7572ba9744ac6f285c21dc87eb43', 'c2daae5b6e314ac8dd66ed2b1489a260'),
        identity_refs=('ENT-smith',),
        context_refs=(('observation', 'OBS-ddfb09ea6f3c15088ac2356e3fd919e4'), ('event', 'EVT-6b0d954be8364d8f2cdf2367c134b442'), ('context', 'CX-665d123f7924e2ee0e1bde938b8004d1'), ('regime', 'df39ad041531e38a79316df7ae387c4d'), ('regime_record', '2ad034fa05747a8d4a931764b4842b07'), ('interpreted_context', 'CX-e98061a2bcb9bcd9ab89049984eeaa5f'), ('derived_capture', '')),
        capture_refs=(('common-crawl.cdx', 'CAP-49307347ab61496ec9cf9f68bf0c0664', 'index_observation', 'absent'),),
        claim_ids=(),
        validation_verdicts=(),
        adverse_codes=(),
        materialisation='',
        lineage_backward_kinds=(),
        lineage_forward_kinds=(),
        lineage_digests=(),
        edge_refs=(),
        worldline_refs=(),
        layer_digests={'identity': '67804550e415d1faebcabe440a4dd50b', 'decisions': '1fdd710d540f5ace9b8a9e035a5291d3', 'claims': '5f4e7a904b1d61ab0da8c77c44fa40b5', 'context': 'f8160da5d51ed828381048a3a84ede80', 'edges': '29298042efbabba8e77705f68c69d974'},
    ),
    'c03-ambiguous-acme-twin': CaseExpectation(
        case_id='c03-ambiguous-acme-twin',
        reached='resolution',
        refusal='object_end_ambiguous',
        mention_values=(('person', 'John Smith'), ('org', 'Acme')),
        extractor_output=(('person', 'John Smith'), ('org', 'Acme')),
        mentions_reached=True,
        identity_refusals=('anchor_creation_unrecorded',),
        verdicts=(('Acme', 'ambiguous', ''), ('John Smith', 'resolved', 'ENT-smith')),
        decision_ids=('RES-5b36620419d6546cab9d573d9cff3370', 'RES-d1e6ed8ab3c40a2713f55a3f7ca12ec2'),
        decision_fingerprints=('ffd34d7ca7d07c7d027ad1573ed66fc7', 'a3d1ee6c0cd7b143e8fd2c95fd98dc7d'),
        identity_refs=('ENT-smith',),
        context_refs=(('observation', 'OBS-0ee0b0449303bd4ca02f8aa3639eab7d'), ('event', 'EVT-0e131d761d3b534e39ba3a343ee5b844'), ('context', 'CX-80759126ea0dc6e6e5d2cdd33a513d23'), ('regime', 'e3ad14842893fa56538726e7bdfaecd6'), ('regime_record', 'd1d6dcc56e751dda2115cd6c4042daf8'), ('interpreted_context', 'CX-15a99f0e005fb033e0983864ea8e7daa'), ('derived_capture', '')),
        capture_refs=(('common-crawl.cdx', 'CAP-49307347ab61496ec9cf9f68bf0c0664', 'index_observation', 'absent'),),
        claim_ids=(),
        validation_verdicts=(),
        adverse_codes=(),
        materialisation='',
        lineage_backward_kinds=(),
        lineage_forward_kinds=(),
        lineage_digests=(),
        edge_refs=(),
        worldline_refs=(),
        layer_digests={'identity': '016a658757965b04f79c2be681469fd3', 'decisions': '39531e7adcc6700d19e98885dc53197a', 'claims': '5f4e7a904b1d61ab0da8c77c44fa40b5', 'context': '2bed5f456a772642b48981326bbd7665', 'edges': '29298042efbabba8e77705f68c69d974'},
    ),
    'c04-cross-tenant-acme': CaseExpectation(
        case_id='c04-cross-tenant-acme',
        reached='resolution',
        refusal='object_end_unresolved',
        mention_values=(('person', 'John Smith'), ('org', 'Acme')),
        extractor_output=(('person', 'John Smith'), ('org', 'Acme')),
        mentions_reached=True,
        identity_refusals=(),
        verdicts=(('Acme', 'unresolved', ''), ('John Smith', 'resolved', 'ENT-smith')),
        decision_ids=('RES-1856e07e743a22a411e978e79b572f23', 'RES-45b88ea7e6ec57c2cd3e37ecd14dcd86'),
        decision_fingerprints=('c4c8fd8308ec0997e1ab8cfb043c6aad', '3048191726df078200fe0be15a1cb8f9'),
        identity_refs=('ENT-smith',),
        context_refs=(('observation', 'OBS-0ee0b0449303bd4ca02f8aa3639eab7d'), ('event', 'EVT-0e131d761d3b534e39ba3a343ee5b844'), ('context', 'CX-80759126ea0dc6e6e5d2cdd33a513d23'), ('regime', 'e3ad14842893fa56538726e7bdfaecd6'), ('regime_record', 'd1d6dcc56e751dda2115cd6c4042daf8'), ('interpreted_context', 'CX-15a99f0e005fb033e0983864ea8e7daa'), ('derived_capture', '')),
        capture_refs=(('common-crawl.cdx', 'CAP-49307347ab61496ec9cf9f68bf0c0664', 'index_observation', 'absent'),),
        claim_ids=(),
        validation_verdicts=(),
        adverse_codes=(),
        materialisation='',
        lineage_backward_kinds=(),
        lineage_forward_kinds=(),
        lineage_digests=(),
        edge_refs=(),
        worldline_refs=(),
        layer_digests={'identity': '8976a134074d60df8f9575dabda0be00', 'decisions': '651d9ebe267293c926dc5381d122d125', 'claims': '5f4e7a904b1d61ab0da8c77c44fa40b5', 'context': '2bed5f456a772642b48981326bbd7665', 'edges': '29298042efbabba8e77705f68c69d974'},
    ),
    'c05-open-world-shell-company': CaseExpectation(
        case_id='c05-open-world-shell-company',
        reached='worldline',
        refusal='',
        mention_values=(('person', 'John Smith'), ('org', 'Acme')),
        extractor_output=(('person', 'John Smith'), ('org', 'Acme')),
        mentions_reached=True,
        identity_refusals=(),
        verdicts=(('Acme', 'resolved', 'ENT-shell'), ('John Smith', 'resolved', 'ENT-smith')),
        decision_ids=('RES-175314b41769aa79650a8dd482c53ba7', 'RES-9ab8b8568ad4bc0925aa80f39f025147'),
        decision_fingerprints=('228bee0db9c3bbf7128b6c8c305026e5', 'a6fc7e3bac125e1eaeaa9ff8bcf6a28f'),
        identity_refs=('ENT-shell', 'ENT-smith'),
        context_refs=(('observation', 'OBS-0ee0b0449303bd4ca02f8aa3639eab7d'), ('event', 'EVT-0e131d761d3b534e39ba3a343ee5b844'), ('context', 'CX-80759126ea0dc6e6e5d2cdd33a513d23'), ('regime', 'e3ad14842893fa56538726e7bdfaecd6'), ('regime_record', 'd1d6dcc56e751dda2115cd6c4042daf8'), ('interpreted_context', 'CX-15a99f0e005fb033e0983864ea8e7daa'), ('derived_capture', 'CAP-49307347ab61496ec9cf9f68bf0c0664')),
        capture_refs=(('common-crawl.cdx', 'CAP-49307347ab61496ec9cf9f68bf0c0664', 'index_observation', 'absent'),),
        claim_ids=(('RC-b6b47626022edf5c1d04959f0bf6d0c8', 'RL-2703d00eecc19f26b1ebac18eec45440'),),
        validation_verdicts=(('structural', 'valid', 'structural_contract_satisfied'), ('semantic', 'unknown', 'not_declared_in_profile'), ('temporal', 'valid', 'temporal_contract_satisfied'), ('provenance', 'valid', 'provenance_established'), ('cross_source', 'unknown', 'single_independence_group'), ('graph_level', 'unknown', 'graph_view_absent')),
        adverse_codes=(),
        materialisation='operator_view_admits_claim',
        lineage_backward_kinds=('assertion', 'assertion', 'mention', 'mention', 'segment', 'segment', 'observation', 'capture', 'source'),
        lineage_forward_kinds=('capture', 'observation', 'segment', 'segment', 'mention', 'mention', 'candidate', 'assertion', 'assertion', 'relation', 'relation', 'entity', 'entity'),
        lineage_digests=(('backward', '980d6b72a1ed0382dcd737a12b984a24'), ('forward', 'f2f00c144553f490de8543e3d957e047')),
        edge_refs=(('RC-b6b47626022edf5c1d04959f0bf6d0c8', 'HE-71dd240a7d811562', '14967a61a1e98200b688f666edd85f53'),),
        worldline_refs=('WL-84a5dafd195743a548764f1921454c61', 'EV-35cc18510413d21b814a4d16064b3f59'),
        layer_digests={'identity': '5e5d0a06eaba9b923314cd3275e9555e', 'decisions': '97ea75cddf409191ce50f39ef97cf374', 'claims': '2b49ef1f916d22c88e1241afdd9962ea', 'context': 'ea3df8f3d5343a838f3f0c4ad175bf29', 'edges': 'f0c71a5c646633bc65f0d247c9864e8f'},
    ),
    'c06-wrong-range-document': CaseExpectation(
        case_id='c06-wrong-range-document',
        reached='worldline',
        refusal='',
        mention_values=(('person', 'John Smith'), ('org', 'Acme')),
        extractor_output=(('person', 'John Smith'), ('org', 'Acme')),
        mentions_reached=True,
        identity_refusals=(),
        verdicts=(('Acme', 'resolved', 'ENT-acme-doc'), ('John Smith', 'resolved', 'ENT-smith')),
        decision_ids=('RES-a8297a07f233f21fd285ed0cdb7a1510', 'RES-105fa491177d481866b02ecd90a7d596'),
        decision_fingerprints=('dbd4ff98da87c9f2af98a8c93868262c', '29a6a9deefa0db0b0cb71786cf8363a0'),
        identity_refs=('ENT-acme-doc', 'ENT-smith'),
        context_refs=(('observation', 'OBS-0ee0b0449303bd4ca02f8aa3639eab7d'), ('event', 'EVT-0e131d761d3b534e39ba3a343ee5b844'), ('context', 'CX-80759126ea0dc6e6e5d2cdd33a513d23'), ('regime', 'e3ad14842893fa56538726e7bdfaecd6'), ('regime_record', 'd1d6dcc56e751dda2115cd6c4042daf8'), ('interpreted_context', 'CX-15a99f0e005fb033e0983864ea8e7daa'), ('derived_capture', 'CAP-49307347ab61496ec9cf9f68bf0c0664')),
        capture_refs=(('common-crawl.cdx', 'CAP-49307347ab61496ec9cf9f68bf0c0664', 'index_observation', 'absent'),),
        claim_ids=(('RC-c85343d5835cb49f0f266c104eeb89a8', 'RL-81b78023ee0f216054167d9d29493cb5'),),
        validation_verdicts=(('structural', 'valid', 'structural_contract_satisfied'), ('semantic', 'unknown', 'not_declared_in_profile'), ('temporal', 'valid', 'temporal_contract_satisfied'), ('provenance', 'valid', 'provenance_established'), ('cross_source', 'unknown', 'single_independence_group'), ('graph_level', 'unknown', 'graph_view_absent')),
        adverse_codes=(),
        materialisation='operator_view_admits_claim',
        lineage_backward_kinds=('assertion', 'assertion', 'mention', 'mention', 'segment', 'segment', 'observation', 'capture', 'source'),
        lineage_forward_kinds=('capture', 'observation', 'segment', 'segment', 'mention', 'mention', 'candidate', 'assertion', 'assertion', 'relation', 'relation', 'entity', 'entity'),
        lineage_digests=(('backward', '8f42b13d8e2cb9307ce88a03c5a2a240'), ('forward', '5ce18f6e7507df82e561a6fdd7c07ae2')),
        edge_refs=(('RC-c85343d5835cb49f0f266c104eeb89a8', 'HE-b52bf7227c2c725d', '7898977b8975d051646231e0bfdb9d30'),),
        worldline_refs=('WL-2dcc9346340ca330e0dd808c35e3f7bc', 'EV-754528c9d758454e681b0ad01c0eb441'),
        layer_digests={'identity': '386145722e17cd0a3580b10b2ac546ab', 'decisions': 'a5f34029aad59d4ba80efd1418a9bac1', 'claims': '7f04f057ad91e96fffe5ef6186fc0308', 'context': 'ae5fec12ffa94cc6e4d55e9344103fb5', 'edges': '2e9fe7895ae12e79b04f369e4f34f7a6'},
    ),
    'c07-temporal-disjoint-acme': CaseExpectation(
        case_id='c07-temporal-disjoint-acme',
        reached='resolution',
        refusal='object_end_unresolved',
        mention_values=(('person', 'John Smith'), ('org', 'Acme')),
        extractor_output=(('person', 'John Smith'), ('org', 'Acme')),
        mentions_reached=True,
        identity_refusals=(),
        verdicts=(('Acme', 'unresolved', ''), ('John Smith', 'resolved', 'ENT-smith')),
        decision_ids=('RES-2a3a6bdebb9c365eff6cfeefcc233f5f', 'RES-b2ba4984e3665d6dea1b76112133fd0c'),
        decision_fingerprints=('156555651b831e85c97908aa66edd24b', '4319bdb3972126c058c822e238cbf7f1'),
        identity_refs=('ENT-smith',),
        context_refs=(('observation', 'OBS-0ee0b0449303bd4ca02f8aa3639eab7d'), ('event', 'EVT-0e131d761d3b534e39ba3a343ee5b844'), ('context', 'CX-80759126ea0dc6e6e5d2cdd33a513d23'), ('regime', 'e3ad14842893fa56538726e7bdfaecd6'), ('regime_record', 'd1d6dcc56e751dda2115cd6c4042daf8'), ('interpreted_context', 'CX-15a99f0e005fb033e0983864ea8e7daa'), ('derived_capture', '')),
        capture_refs=(('common-crawl.cdx', 'CAP-49307347ab61496ec9cf9f68bf0c0664', 'index_observation', 'absent'),),
        claim_ids=(),
        validation_verdicts=(),
        adverse_codes=(),
        materialisation='',
        lineage_backward_kinds=(),
        lineage_forward_kinds=(),
        lineage_digests=(),
        edge_refs=(),
        worldline_refs=(),
        layer_digests={'identity': 'c500410de983290e614b8f559a60fa69', 'decisions': 'd835eed1d3499fd3be9b29815c75c92f', 'claims': '5f4e7a904b1d61ab0da8c77c44fa40b5', 'context': '2bed5f456a772642b48981326bbd7665', 'edges': '29298042efbabba8e77705f68c69d974'},
    ),
    'c08-temporal-span-point-claim': CaseExpectation(
        case_id='c08-temporal-span-point-claim',
        reached='worldline',
        refusal='',
        mention_values=(('person', 'John Smith'), ('org', 'Acme')),
        extractor_output=(('person', 'John Smith'), ('org', 'Acme')),
        mentions_reached=True,
        identity_refusals=(),
        verdicts=(('Acme', 'resolved', 'ENT-acme'), ('John Smith', 'resolved', 'ENT-smith')),
        decision_ids=('RES-c9af0649c673cfe061d40d890b0a7e72', 'RES-0e9bbe0162ac3503e9c0d2213663abd3'),
        decision_fingerprints=('58578970a894c9224ffbbd09a9fdcb79', '9431639c252142232a66d2b87c6f5e32'),
        identity_refs=('ENT-acme', 'ENT-smith'),
        context_refs=(('observation', 'OBS-0ee0b0449303bd4ca02f8aa3639eab7d'), ('event', 'EVT-0e131d761d3b534e39ba3a343ee5b844'), ('context', 'CX-80759126ea0dc6e6e5d2cdd33a513d23'), ('regime', 'e3ad14842893fa56538726e7bdfaecd6'), ('regime_record', 'd1d6dcc56e751dda2115cd6c4042daf8'), ('interpreted_context', 'CX-15a99f0e005fb033e0983864ea8e7daa'), ('derived_capture', 'CAP-49307347ab61496ec9cf9f68bf0c0664')),
        capture_refs=(('common-crawl.cdx', 'CAP-49307347ab61496ec9cf9f68bf0c0664', 'index_observation', 'absent'),),
        claim_ids=(('RC-875fdf4266020ad0e7d9b621e456fc32', 'RL-7bf5f7a228a3f3f67536567be08454cc'),),
        validation_verdicts=(('structural', 'valid', 'structural_contract_satisfied'), ('semantic', 'valid', 'domain_range_satisfied'), ('temporal', 'invalid', 'interval_on_point_claim'), ('provenance', 'valid', 'provenance_established'), ('cross_source', 'unknown', 'single_independence_group'), ('graph_level', 'unknown', 'graph_view_absent')),
        adverse_codes=('interval_on_point_claim',),
        materialisation='operator_view_admits_claim',
        lineage_backward_kinds=('assertion', 'assertion', 'mention', 'mention', 'segment', 'segment', 'observation', 'capture', 'source'),
        lineage_forward_kinds=('capture', 'observation', 'segment', 'segment', 'mention', 'mention', 'candidate', 'assertion', 'assertion', 'relation', 'relation', 'entity', 'entity'),
        lineage_digests=(('backward', '38d20f76da6bdcff30a1156d1e0a7d09'), ('forward', 'a58d02f3ff0c4b518a5102746fe000bc')),
        edge_refs=(('RC-875fdf4266020ad0e7d9b621e456fc32', 'HE-18cc0be0976e20e6', '1fcb4a0a32a9f6e592b6710ec66f3e0c'),),
        worldline_refs=('WL-8299fef946a0e48811d77a03ab39a328', 'EV-0ebdc0c1df8b890e2d2f69017b42e558'),
        layer_digests={'identity': '6064afa1d4c2fe6f9eb7895478537d38', 'decisions': 'd3435241fad85178ffef97d7771566fb', 'claims': '11d1e374a5741c153cba61186270dcbe', 'context': '0a39a17f7f0c1d93526d3854003bbf61', 'edges': '6a0fa0c80c938146e578c6f8eed71d95'},
    ),
    'c09-nonconvergent-collective': CaseExpectation(
        case_id='c09-nonconvergent-collective',
        reached='worldline',
        refusal='',
        mention_values=(('person', 'John Smith'), ('org', 'Acme')),
        extractor_output=(('person', 'John Smith'), ('org', 'Acme')),
        mentions_reached=True,
        identity_refusals=(),
        verdicts=(('Acme', 'resolved', 'ENT-acme'), ('John Smith', 'resolved', 'ENT-smith')),
        decision_ids=('RES-2a71bc648386fef0e5b6c8012f8a3345', 'RES-a5a47865ad9fb4c3ef6ccaebd260c403'),
        decision_fingerprints=('408f32c3334d5024df2d640f4b685ca6', '56a183eb1fce78f36897b6b37e975d59'),
        identity_refs=('ENT-acme', 'ENT-smith'),
        context_refs=(('observation', 'OBS-0ee0b0449303bd4ca02f8aa3639eab7d'), ('event', 'EVT-0e131d761d3b534e39ba3a343ee5b844'), ('context', 'CX-80759126ea0dc6e6e5d2cdd33a513d23'), ('regime', 'e3ad14842893fa56538726e7bdfaecd6'), ('regime_record', 'd1d6dcc56e751dda2115cd6c4042daf8'), ('interpreted_context', 'CX-15a99f0e005fb033e0983864ea8e7daa'), ('derived_capture', 'CAP-49307347ab61496ec9cf9f68bf0c0664')),
        capture_refs=(('common-crawl.cdx', 'CAP-49307347ab61496ec9cf9f68bf0c0664', 'index_observation', 'absent'),),
        claim_ids=(('RC-b0cb923eb7e0577ecb1d3cf4543d5021', 'RL-7bf5f7a228a3f3f67536567be08454cc'),),
        validation_verdicts=(('structural', 'valid', 'structural_contract_satisfied'), ('semantic', 'valid', 'domain_range_satisfied'), ('temporal', 'valid', 'temporal_contract_satisfied'), ('provenance', 'valid', 'provenance_established'), ('cross_source', 'unknown', 'single_independence_group'), ('graph_level', 'unknown', 'graph_view_absent')),
        adverse_codes=(),
        materialisation='operator_view_admits_claim',
        lineage_backward_kinds=('assertion', 'assertion', 'mention', 'mention', 'segment', 'segment', 'observation', 'capture', 'source'),
        lineage_forward_kinds=('capture', 'observation', 'segment', 'segment', 'mention', 'mention', 'candidate', 'assertion', 'assertion', 'relation', 'relation', 'entity', 'entity'),
        lineage_digests=(('backward', '38d20f76da6bdcff30a1156d1e0a7d09'), ('forward', 'b9f166abb4840b9f46dcb2cab70b3da2')),
        edge_refs=(('RC-b0cb923eb7e0577ecb1d3cf4543d5021', 'HE-18cc0be0976e20e6', 'd7f931f913e5803fcfd2a6a9ea963313'),),
        worldline_refs=('WL-0a1517a688fabed3d8c7c07df071c3ac', 'EV-482d1c6c94f9656d7bfb4d999d27f497'),
        layer_digests={'identity': '6064afa1d4c2fe6f9eb7895478537d38', 'decisions': '628186a90b1723022a9627d1b8a9fd85', 'claims': 'bc91c3bf3d8b1c4c4bc8a3a8bd964cf5', 'context': '2960086fd657ccd92799839c6e3007e3', 'edges': '5c0d39cfebf14116bbd8700d2a94a639'},
    ),
    'c10-independence-groups-acme': CaseExpectation(
        case_id='c10-independence-groups-acme',
        reached='worldline',
        refusal='',
        mention_values=(('person', 'John Smith'), ('org', 'Acme')),
        extractor_output=(('person', 'John Smith'), ('org', 'Acme')),
        mentions_reached=True,
        identity_refusals=(),
        verdicts=(('Acme', 'resolved', 'ENT-acme'), ('John Smith', 'resolved', 'ENT-smith')),
        decision_ids=('RES-3a07f4684d2a236517d8dbc8dede5fa2', 'RES-3b2e1df7c50331805ec60b909a6cc5b9'),
        decision_fingerprints=('e661a1b354f8cb5fd3c2970e838bf9f1', '5f17173cb5083c9e0f317635da13e50f'),
        identity_refs=('ENT-acme', 'ENT-smith'),
        context_refs=(('observation', 'OBS-0ee0b0449303bd4ca02f8aa3639eab7d'), ('event', 'EVT-0e131d761d3b534e39ba3a343ee5b844'), ('context', 'CX-80759126ea0dc6e6e5d2cdd33a513d23'), ('regime', 'e3ad14842893fa56538726e7bdfaecd6'), ('regime_record', 'd1d6dcc56e751dda2115cd6c4042daf8'), ('interpreted_context', 'CX-15a99f0e005fb033e0983864ea8e7daa'), ('derived_capture', 'CAP-49307347ab61496ec9cf9f68bf0c0664')),
        capture_refs=(('common-crawl.cdx', 'CAP-49307347ab61496ec9cf9f68bf0c0664', 'index_observation', 'absent'),),
        claim_ids=(('RC-7f1775e25fbbed6d339fa4753d47ec11', 'RL-7bf5f7a228a3f3f67536567be08454cc'),),
        validation_verdicts=(('structural', 'valid', 'structural_contract_satisfied'), ('semantic', 'valid', 'domain_range_satisfied'), ('temporal', 'valid', 'temporal_contract_satisfied'), ('provenance', 'valid', 'provenance_established'), ('cross_source', 'valid', 'cross_source_agreement'), ('graph_level', 'unknown', 'graph_view_absent')),
        adverse_codes=(),
        materialisation='operator_view_admits_claim',
        lineage_backward_kinds=('assertion', 'assertion', 'mention', 'mention', 'segment', 'segment', 'observation', 'capture', 'source'),
        lineage_forward_kinds=('capture', 'observation', 'segment', 'segment', 'mention', 'mention', 'candidate', 'assertion', 'assertion', 'relation', 'relation', 'entity', 'entity'),
        lineage_digests=(('backward', '38d20f76da6bdcff30a1156d1e0a7d09'), ('forward', '5a9e0d6888e450b2baffac4ec1c3ccc8')),
        edge_refs=(('RC-7f1775e25fbbed6d339fa4753d47ec11', 'HE-18cc0be0976e20e6', '8294edcabb99c3a27e665f1e4b5856b7'),),
        worldline_refs=('WL-e91586dfd3f035e0efe25c29d8a514b9', 'EV-0e7ad51a3056f2635c66f6d217fde3eb'),
        layer_digests={'identity': '1d99bcbb7f3b6055702c541a4853065b', 'decisions': '27c2d3dd826d6d7391a0d8b6b7512644', 'claims': 'e5a255b2d0cb207cfc68b9ce5bfec8a0', 'context': 'c762263c85527d933fd40ea71cfd0726', 'edges': '1e12b94af049b3c67b16ab14cf79d51e'},
    ),
    'c11-no-org-mention-acme': CaseExpectation(
        case_id='c11-no-org-mention-acme',
        reached='context',
        refusal='no_mention_of_kind',
        mention_values=(),
        extractor_output=(('person', 'John Smith'),),
        mentions_reached=False,
        identity_refusals=(),
        verdicts=(),
        decision_ids=(),
        decision_fingerprints=(),
        identity_refs=(),
        context_refs=(),
        capture_refs=(('common-crawl.cdx', 'CAP-49307347ab61496ec9cf9f68bf0c0664', 'index_observation', 'absent'),),
        claim_ids=(),
        validation_verdicts=(),
        adverse_codes=(),
        materialisation='',
        lineage_backward_kinds=(),
        lineage_forward_kinds=(),
        lineage_digests=(),
        edge_refs=(),
        worldline_refs=(),
        layer_digests={'identity': '01150c274ef44db5a176a03d52ad8836', 'decisions': '01150c274ef44db5a176a03d52ad8836', 'claims': '5f4e7a904b1d61ab0da8c77c44fa40b5', 'context': '23c59a7548cae8fb422178f3d9c718c1', 'edges': '29298042efbabba8e77705f68c69d974'},
    ),
    'c12-ru-director-romashka': CaseExpectation(
        case_id='c12-ru-director-romashka',
        reached='worldline',
        refusal='',
        mention_values=(('person', 'Иван Петров'), ('org', 'Ромашка')),
        extractor_output=(('person', 'Иван Петров'), ('org', 'Ромашка')),
        mentions_reached=True,
        identity_refusals=(),
        verdicts=(('Иван Петров', 'resolved', 'ENT-petrov'), ('Ромашка', 'resolved', 'ENT-romashka')),
        decision_ids=('RES-cf3f1bc286c25ddfd3a5678e846f95f7', 'RES-565afd0b82d137fa2e216e04b12c6936'),
        decision_fingerprints=('088a68a43c20b7ec18e188c955cb9e5e', 'f142a3fa01efe47fd9ab65ff199a9ad9'),
        identity_refs=('ENT-petrov', 'ENT-romashka'),
        context_refs=(('observation', 'OBS-c11e4880e0777fec06d645ed9dd12fb6'), ('event', 'EVT-ad5b78c714a26b18370e27cf07179eb9'), ('context', 'CX-6d034cb353271b8f233af8ae39e9e4dc'), ('regime', '3415a71c7c935434f74e3a26963b8db5'), ('regime_record', '306925b5141b2bfd83293f09b6abe9f5'), ('interpreted_context', 'CX-90d1ee5bfb63b0f93a01a9ed31e87de9'), ('derived_capture', 'CAP-49307347ab61496ec9cf9f68bf0c0664')),
        capture_refs=(('common-crawl.cdx', 'CAP-49307347ab61496ec9cf9f68bf0c0664', 'index_observation', 'absent'),),
        claim_ids=(('RC-cc9a9650d5f0c13076e0f6aa6c4f57e2', 'RL-2a9c1131b1cd5432a446cb96198907fd'),),
        validation_verdicts=(('structural', 'valid', 'structural_contract_satisfied'), ('semantic', 'valid', 'domain_range_satisfied'), ('temporal', 'valid', 'temporal_contract_satisfied'), ('provenance', 'valid', 'provenance_established'), ('cross_source', 'unknown', 'single_independence_group'), ('graph_level', 'unknown', 'graph_view_absent')),
        adverse_codes=(),
        materialisation='operator_view_admits_claim',
        lineage_backward_kinds=('assertion', 'assertion', 'mention', 'mention', 'segment', 'segment', 'observation', 'capture', 'source'),
        lineage_forward_kinds=('capture', 'observation', 'segment', 'segment', 'mention', 'mention', 'candidate', 'assertion', 'assertion', 'relation', 'relation', 'entity', 'entity'),
        lineage_digests=(('backward', 'f729ebbace9b0865ed7b78b6b01c44af'), ('forward', 'a4729a7f86cc9bb9b3047262a1cac9ef')),
        edge_refs=(('RC-cc9a9650d5f0c13076e0f6aa6c4f57e2', 'HE-07ab3e0731f017f1', '8a7c2670bb8861fd3a1ca1fd9b3912e5'),),
        worldline_refs=('WL-4340fb46d207087f640fee599dafb678', 'EV-8b57afee120d7d53eed3defba7b2a0bb'),
        layer_digests={'identity': '7f4bb966f416d2ebed4cdc32fc291eaa', 'decisions': '15c588fff79745d355a81521302f92d3', 'claims': '188d5798954c1a68efc68b1443017f89', 'context': '2c3e5abe92b1db8a012d21581986a09a', 'edges': '65675bc4eba0e3daa5ebce44eec7a008'},
    ),
    'c13-initech-director': CaseExpectation(
        case_id='c13-initech-director',
        reached='worldline',
        refusal='',
        mention_values=(('person', 'Mary Jones'), ('org', 'Initech')),
        extractor_output=(('person', 'Mary Jones'), ('org', 'Initech')),
        mentions_reached=True,
        identity_refusals=(),
        verdicts=(('Initech', 'resolved', 'ENT-initech'), ('Mary Jones', 'resolved', 'ENT-jones')),
        decision_ids=('RES-2deaa5747e68ed7b68a8cda7ff3a0c31', 'RES-2d66638f3f469658e8e62cefd52d9ec0'),
        decision_fingerprints=('730ad857d6538c48e8d4a1d6771d9cc9', 'c9bd7e4ca27506a176cc4f8067e769b2'),
        identity_refs=('ENT-initech', 'ENT-jones'),
        context_refs=(('observation', 'OBS-5456e8abc128b88b58186764ac5872b1'), ('event', 'EVT-4803743289665771635efb496f56cc45'), ('context', 'CX-55a062c489a0b54d0a4e76a7fb53c35a'), ('regime', '0487fc039d8dc829a481cce29b8dcb04'), ('regime_record', 'ee8feb8d165526683a50f630c870a2e1'), ('interpreted_context', 'CX-d7df2e7e8abb08e7a0ec8442cdad57a3'), ('derived_capture', 'CAP-49307347ab61496ec9cf9f68bf0c0664')),
        capture_refs=(('common-crawl.cdx', 'CAP-49307347ab61496ec9cf9f68bf0c0664', 'index_observation', 'absent'),),
        claim_ids=(('RC-5d5002f11ff727cdb4df0ae021feb0a1', 'RL-6908008e681463903190e3ed9436a3da'),),
        validation_verdicts=(('structural', 'valid', 'structural_contract_satisfied'), ('semantic', 'valid', 'domain_range_satisfied'), ('temporal', 'valid', 'temporal_contract_satisfied'), ('provenance', 'valid', 'provenance_established'), ('cross_source', 'unknown', 'single_independence_group'), ('graph_level', 'unknown', 'graph_view_absent')),
        adverse_codes=(),
        materialisation='operator_view_admits_claim',
        lineage_backward_kinds=('assertion', 'assertion', 'mention', 'mention', 'segment', 'segment', 'observation', 'capture', 'source'),
        lineage_forward_kinds=('capture', 'observation', 'segment', 'segment', 'mention', 'mention', 'candidate', 'assertion', 'assertion', 'relation', 'relation', 'entity', 'entity'),
        lineage_digests=(('backward', 'd3a8c57bd3ff4efb8d540557fe80e8b6'), ('forward', 'e5047f133820ae3272e69085c834c66d')),
        edge_refs=(('RC-5d5002f11ff727cdb4df0ae021feb0a1', 'HE-7af09c44bf166042', '9d2f85386aec145a47692c2c2b753c40'),),
        worldline_refs=('WL-b3fe2f1924abaa57287f5360bee35460', 'EV-ac070caf3e1434a357c31549683cd6d8'),
        layer_digests={'identity': 'bc687e5a1881c0f1c71549f5534b2db2', 'decisions': '25d1e3cc0b3c4ab1f7964084331a3201', 'claims': 'eb69286b6e61021e743032566c59eb7c', 'context': '1be556a90e4b4e7cb647009acec9732e', 'edges': '26cd754c5a42f4cee02eecf94a74bb10'},
    ),
    'c14-acquired-beta-corp': CaseExpectation(
        case_id='c14-acquired-beta-corp',
        reached='context',
        refusal='no_mention_of_kind',
        mention_values=(),
        extractor_output=(('org', 'Beta Corp'),),
        mentions_reached=False,
        identity_refusals=(),
        verdicts=(),
        decision_ids=(),
        decision_fingerprints=(),
        identity_refs=(),
        context_refs=(),
        capture_refs=(('sec-edgar.full-index', 'CAP-5690c6be05aac1093079fcf7a2eaa563', 'publication', 'absent'),),
        claim_ids=(),
        validation_verdicts=(),
        adverse_codes=(),
        materialisation='',
        lineage_backward_kinds=(),
        lineage_forward_kinds=(),
        lineage_digests=(),
        edge_refs=(),
        worldline_refs=(),
        layer_digests={'identity': '01150c274ef44db5a176a03d52ad8836', 'decisions': '01150c274ef44db5a176a03d52ad8836', 'claims': '5f4e7a904b1d61ab0da8c77c44fa40b5', 'context': '11ccaeb1946510f0de2f0a14fa3ad24d', 'edges': '29298042efbabba8e77705f68c69d974'},
    ),
    'c15-minted-identity-anchor': CaseExpectation(
        case_id='c15-minted-identity-anchor',
        reached='worldline',
        refusal='',
        mention_values=(('person', 'John Smith'), ('org', 'Acme')),
        extractor_output=(('person', 'John Smith'), ('org', 'Acme')),
        mentions_reached=True,
        identity_refusals=(),
        verdicts=(('Acme', 'resolved', 'ENT-ed0c8a3f060cbfd3f010ce2d52b289ac'), ('John Smith', 'resolved', 'ENT-5171234877158fb71e42224ce9231939')),
        decision_ids=('RES-23467ceaec7b1b46d95781cb517257d7', 'RES-ec5e13e3cbe2b3eed6c8db81298e1908'),
        decision_fingerprints=('977960c48f07a38901a374227dbb1dee', '1fc77a01095762bc3ba9b12b6344d531'),
        identity_refs=('ENT-5171234877158fb71e42224ce9231939', 'ENT-ed0c8a3f060cbfd3f010ce2d52b289ac'),
        context_refs=(('observation', 'OBS-0ee0b0449303bd4ca02f8aa3639eab7d'), ('event', 'EVT-0e131d761d3b534e39ba3a343ee5b844'), ('context', 'CX-80759126ea0dc6e6e5d2cdd33a513d23'), ('regime', 'e3ad14842893fa56538726e7bdfaecd6'), ('regime_record', 'd1d6dcc56e751dda2115cd6c4042daf8'), ('interpreted_context', 'CX-15a99f0e005fb033e0983864ea8e7daa'), ('derived_capture', 'CAP-49307347ab61496ec9cf9f68bf0c0664')),
        capture_refs=(('common-crawl.cdx', 'CAP-49307347ab61496ec9cf9f68bf0c0664', 'index_observation', 'absent'),),
        claim_ids=(('RC-d797ab27de19ec02f0ac105724337492', 'RL-488e6325a47e967b4076b75ca73238a0'),),
        validation_verdicts=(('structural', 'valid', 'structural_contract_satisfied'), ('semantic', 'valid', 'domain_range_satisfied'), ('temporal', 'valid', 'temporal_contract_satisfied'), ('provenance', 'valid', 'provenance_established'), ('cross_source', 'unknown', 'no_independence_recorded'), ('graph_level', 'unknown', 'graph_view_absent')),
        adverse_codes=(),
        materialisation='operator_view_admits_claim',
        lineage_backward_kinds=('assertion', 'assertion', 'mention', 'mention', 'segment', 'segment', 'observation', 'capture', 'source'),
        lineage_forward_kinds=('capture', 'observation', 'segment', 'segment', 'mention', 'mention', 'candidate', 'assertion', 'assertion', 'relation', 'relation', 'entity', 'entity'),
        lineage_digests=(('backward', '16d134e0d74a5b7dfb65ea734a405f73'), ('forward', '2e4b44a02eeffafeaafe8ca06377a65f')),
        edge_refs=(('RC-d797ab27de19ec02f0ac105724337492', 'HE-4715a5cdc43a437d', '0e221a645a291428e94e3a27123fdfc3'),),
        worldline_refs=('WL-45bea7646e4f72c19bbacacaf38170e2', 'EV-2f4466c8227b3588845053ceb44b90b0'),
        layer_digests={'identity': '3cbe98baef25089697159c693714243a', 'decisions': 'dcfad5cfb02d10ad884fa2feef6c0a21', 'claims': '8090094b2417136e528b3e7d63900c3c', 'context': 'c3ccded3905a2063e21972b176989ebb', 'edges': '47f7135eaed58f5912034cd2bbbc683a'},
    ),
    'c16-headquarters-london': CaseExpectation(
        case_id='c16-headquarters-london',
        reached='context',
        refusal='no_mention_of_kind',
        mention_values=(),
        extractor_output=(('place', 'London'),),
        mentions_reached=False,
        identity_refusals=(),
        verdicts=(),
        decision_ids=(),
        decision_fingerprints=(),
        identity_refs=(),
        context_refs=(),
        capture_refs=(('common-crawl.cdx', 'CAP-49307347ab61496ec9cf9f68bf0c0664', 'index_observation', 'absent'),),
        claim_ids=(),
        validation_verdicts=(),
        adverse_codes=(),
        materialisation='',
        lineage_backward_kinds=(),
        lineage_forward_kinds=(),
        lineage_digests=(),
        edge_refs=(),
        worldline_refs=(),
        layer_digests={'identity': '01150c274ef44db5a176a03d52ad8836', 'decisions': '01150c274ef44db5a176a03d52ad8836', 'claims': '5f4e7a904b1d61ab0da8c77c44fa40b5', 'context': '0cd568b7595f6a4ed07d50bcd84340b8', 'edges': '29298042efbabba8e77705f68c69d974'},
    ),
    'c17-visited-kazan': CaseExpectation(
        case_id='c17-visited-kazan',
        reached='mentions',
        refusal='object_end_unresolved',
        mention_values=(('person', 'John Smith'), ('place', 'Kazan')),
        extractor_output=(('person', 'John Smith'), ('place', 'Kazan')),
        mentions_reached=True,
        identity_refusals=(),
        verdicts=(),
        decision_ids=(),
        decision_fingerprints=(),
        identity_refs=(),
        context_refs=(),
        capture_refs=(('common-crawl.cdx', 'CAP-49307347ab61496ec9cf9f68bf0c0664', 'index_observation', 'absent'),),
        claim_ids=(),
        validation_verdicts=(),
        adverse_codes=(),
        materialisation='',
        lineage_backward_kinds=(),
        lineage_forward_kinds=(),
        lineage_digests=(),
        edge_refs=(),
        worldline_refs=(),
        layer_digests={'identity': '01150c274ef44db5a176a03d52ad8836', 'decisions': '01150c274ef44db5a176a03d52ad8836', 'claims': '5f4e7a904b1d61ab0da8c77c44fa40b5', 'context': 'f6a34a0ff86d20308349b504d8bb7cb1', 'edges': '29298042efbabba8e77705f68c69d974'},
    ),
    'c18-edgar-registrar-instant': CaseExpectation(
        case_id='c18-edgar-registrar-instant',
        reached='worldline',
        refusal='',
        mention_values=(('person', 'John Smith'), ('org', 'Acme')),
        extractor_output=(('person', 'John Smith'), ('org', 'Acme')),
        mentions_reached=True,
        identity_refusals=(),
        verdicts=(('Acme', 'resolved', 'ENT-acme'), ('John Smith', 'resolved', 'ENT-smith')),
        decision_ids=('RES-2e531c3f4aa6e2c53c5b4345c0ebef3f', 'RES-1e4cbdd36466b028c92badc9ffffe583'),
        decision_fingerprints=('c410c517744eb9e13fec7be53d5e3a83', '7f8b6738f82b178518bcfd2caf49f8bb'),
        identity_refs=('ENT-acme', 'ENT-smith'),
        context_refs=(('observation', 'OBS-0ee0b0449303bd4ca02f8aa3639eab7d'), ('event', 'EVT-0e131d761d3b534e39ba3a343ee5b844'), ('context', 'CX-80759126ea0dc6e6e5d2cdd33a513d23'), ('regime', 'e3ad14842893fa56538726e7bdfaecd6'), ('regime_record', 'd1d6dcc56e751dda2115cd6c4042daf8'), ('interpreted_context', 'CX-15a99f0e005fb033e0983864ea8e7daa'), ('derived_capture', 'CAP-5690c6be05aac1093079fcf7a2eaa563')),
        capture_refs=(('sec-edgar.full-index', 'CAP-5690c6be05aac1093079fcf7a2eaa563', 'publication', 'absent'),),
        claim_ids=(('RC-b0cb923eb7e0577ecb1d3cf4543d5021', 'RL-7bf5f7a228a3f3f67536567be08454cc'),),
        validation_verdicts=(('structural', 'valid', 'structural_contract_satisfied'), ('semantic', 'valid', 'domain_range_satisfied'), ('temporal', 'valid', 'temporal_contract_satisfied'), ('provenance', 'valid', 'provenance_established'), ('cross_source', 'unknown', 'single_independence_group'), ('graph_level', 'unknown', 'graph_view_absent')),
        adverse_codes=(),
        materialisation='operator_view_admits_claim',
        lineage_backward_kinds=('assertion', 'assertion', 'mention', 'mention', 'segment', 'segment', 'observation', 'capture', 'source'),
        lineage_forward_kinds=('capture', 'observation', 'segment', 'segment', 'mention', 'mention', 'candidate', 'assertion', 'assertion', 'relation', 'relation', 'entity', 'entity'),
        lineage_digests=(('backward', '3ee29d7f7c4b783d3e5d38a70e31e650'), ('forward', 'd4729d31433213599d3296c3fddf735a')),
        edge_refs=(('RC-b0cb923eb7e0577ecb1d3cf4543d5021', 'HE-18cc0be0976e20e6', 'd7f931f913e5803fcfd2a6a9ea963313'),),
        worldline_refs=('WL-0a1517a688fabed3d8c7c07df071c3ac', 'EV-482d1c6c94f9656d7bfb4d999d27f497'),
        layer_digests={'identity': '6064afa1d4c2fe6f9eb7895478537d38', 'decisions': '9f667729094efd3eb6302bec6e474dd5', 'claims': 'bc91c3bf3d8b1c4c4bc8a3a8bd964cf5', 'context': '0b4b11f49e08cced338ce1ed155d68ae', 'edges': '5c0d39cfebf14116bbd8700d2a94a639'},
    ),
    }
)
