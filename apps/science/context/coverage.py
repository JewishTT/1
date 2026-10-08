"""Evidence independence and coverage-qualified absence (spec 025 §13A, §14A, §22).

§14A opens with the sentence this module exists for: "Source count is not source
independence, and correlated evidence double-counts." Five hundred outlets
republishing one press release are one observation wearing five hundred hats, and
a confidence figure computed from the raw count is wrong by two and a half orders
of magnitude.

Four rules from §14A.2 are load-bearing and each is enforced here rather than
documented:

1. Update rules consume **groups**, never items. Within a group the contribution
   is ``max`` or a declared discount; across groups contributions combine.
2. ``n_eff`` is computed from the groups and **reported next to the raw count**
   wherever either appears. A system that computes ``n_eff`` and then displays the
   raw count has gained nothing.
3. **Undeterminable dependence collapses to one group** and records
   ``INDEPENDENCE_UNKNOWN``. This is the conservative direction on purpose: when
   lineage is unknown the honest reading is "maybe one source", not "probably many".
4. ``truth_state`` flags are **unaffected** by grouping. Grouping changes scores,
   saturation and contradiction independence; it does not change whether support
   exists. A claim that has support has support even if every supporting item
   came from one press release -- it just does not get stronger for it.

§13A is the mirror image: "searched and found nothing" is evidence only under
declared coverage, and **unknown detection power means ``INFORMATIONAL_ONLY``
always**. Without that, an unsuccessful search would silently become evidence of
absence, which is the single most common way an investigation manufactures a
negative finding.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from context.locality import ObstructionKind, _digest

# -- §14A.1 dependence --------------------------------------------------------


class DependenceBasis(enum.StrEnum):
    """Why two evidence items are considered not independent. §14A.1, verbatim."""

    SAME_UNDERLYING_OBSERVATION = "same_underlying_observation"
    SYNDICATION_LINEAGE = "syndication_lineage"
    SAME_TRANSFORMATION_CHAIN = "same_transformation_chain"
    SAME_EXTRACTION_METHOD = "same_extraction_method"
    SAME_PUBLISHER = "same_publisher"
    SAME_SOURCE_FAMILY = "same_source_family"
    SAME_UPSTREAM_MODEL = "same_upstream_model"


class CorrelationModel(enum.StrEnum):
    """How contributions inside a group combine. §14A.1."""

    DECLARED_DISCOUNT = "declared_discount"
    MAX_ONLY = "max_only"
    PROFILE_SPECIFIC = "profile_specific"


@dataclass(frozen=True, slots=True)
class EvidenceDependencyGroup:
    """A set of evidence items that must not be counted independently."""

    members: tuple[str, ...]
    basis: tuple[DependenceBasis, ...]
    correlation_model: CorrelationModel = CorrelationModel.MAX_ONLY
    assessed_by: str = ""
    group_id: str = ""
    discount: float = 1.0

    def __post_init__(self) -> None:
        if not self.members:
            raise ValueError("a dependency group with no members constrains nothing")
        if len(set(self.members)) != len(self.members):
            raise ValueError(f"duplicate members in group: {sorted(self.members)}")
        object.__setattr__(self, "basis", tuple(self.basis))
        if not 0.0 < self.discount <= 1.0:
            raise ValueError(f"discount must be in (0, 1], got {self.discount}")
        if self.group_id and self.group_id != self.address():
            raise ValueError(
                f"declared group_id {self.group_id!r} but material addresses to {self.address()}"
            )
        if not self.group_id:
            object.__setattr__(self, "group_id", self.address())

    def _material(self) -> dict[str, Any]:
        return {
            "members": sorted(self.members),
            "basis": sorted(item.value for item in self.basis),
            "correlation_model": self.correlation_model.value,
            "discount": self.discount,
        }

    def address(self) -> str:
        return f"EDG-{_digest(self._material())}"

    @property
    def size(self) -> int:
        return len(self.members)


@dataclass(frozen=True, slots=True)
class IndependenceAssessment:
    """The result of grouping a bag of evidence items. §14A.2.

    ``groups`` is empty when dependence could not be determined for any item; the
    items are then treated as a single implicit group, which is the conservative
    reading the spec mandates.
    """

    raw_count: int
    n_eff: float
    groups: tuple[EvidenceDependencyGroup, ...] = ()
    independence_known: bool = True
    obstruction: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "raw_count": self.raw_count,
            "effective_independent_sources": self.n_eff,
            "independence_known": self.independence_known,
            "group_count": len(self.groups),
            "groups": [
                {"group_id": group.group_id, "members": list(group.members), "size": group.size}
                for group in self.groups
            ],
            "obstruction": self.obstruction,
        }

    def as_display(self) -> str:
        """Rule 2: ``n_eff`` shown next to the raw count, never instead of it."""
        if self.independence_known:
            return f"{self.n_eff:g} independent of {self.raw_count} items"
        return f"{self.n_eff:g} independent of {self.raw_count} items (independence unknown)"


def assess_independence(
    items: Sequence[str],
    lineage: Mapping[str, str],
    *,
    assessed_by: str = "",
) -> IndependenceAssessment:
    """Group evidence items by shared lineage root. §14A.2 rule 3.

    ``lineage`` maps an evidence id to the id of the observation it ultimately
    derives from. Items sharing a root are one group, whatever route each took --
    which is what catches syndication, re-extraction and re-transformation
    together rather than needing a rule per mechanism.

    An item with no lineage entry cannot be placed. Per §14A.2 it joins a single
    implicit group with the rest of the unplaceable items, ``n_eff`` collapses, and
    ``independence_known`` is False so the UI can say so.
    """
    raw = list(items)
    if not raw:
        return IndependenceAssessment(raw_count=0, n_eff=0.0, groups=())

    buckets: dict[str, list[str]] = {}
    unplaceable: list[str] = []
    for item in raw:
        root = lineage.get(item)
        if root is None or not root:
            unplaceable.append(item)
        else:
            buckets.setdefault(root, []).append(item)

    groups: list[EvidenceDependencyGroup] = []
    for root, members in buckets.items():
        groups.append(
            EvidenceDependencyGroup(
                members=tuple(sorted(members)),
                basis=(DependenceBasis.SAME_UNDERLYING_OBSERVATION,),
                assessed_by=assessed_by,
            )
        )
    if unplaceable:
        # One group, full weight. The conservatism comes from collapsing them into
        # a single group -- which already drives `n_eff` down -- not from zeroing
        # their contribution. A zero discount would mean "contributes nothing",
        # which is a different claim from "we cannot tell whether these agree".
        groups.append(
            EvidenceDependencyGroup(
                members=tuple(sorted(unplaceable)),
                basis=(DependenceBasis.SAME_UNDERLYING_OBSERVATION,),
                correlation_model=CorrelationModel.DECLARED_DISCOUNT,
                assessed_by=assessed_by,
                discount=0.5,
            )
        )

    known = not unplaceable
    return IndependenceAssessment(
        raw_count=len(raw),
        n_eff=float(len(groups)),
        groups=tuple(sorted(groups, key=lambda item: item.group_id)),
        independence_known=known,
        obstruction=(
            ""
            if known
            else "lineage unknown for "
            f"{sorted(unplaceable)}; treated as one group (INDEPENDENCE_UNKNOWN)"
        ),
    )


def group_contribution(
    assessment: IndependenceAssessment,
    *,
    discount: float = 1.0,
) -> dict[str, float]:
    """Combine contributions across groups, not within them. §14A.2 rule 1.

    Within a group the largest single contribution wins -- a group cannot make
    itself stronger by repeating. Across groups contributions add, which is the
    independence assumption, and that assumption is itself declared (§16).
    """
    by_member = {
        member: group.discount for group in assessment.groups for member in group.members
    }
    combined = 0.0
    per_group: dict[str, float] = {}
    for group in assessment.groups:
        best = max((by_member.get(member, 1.0) for member in group.members), default=0.0)
        per_group[group.group_id] = round(best * discount, 9)
        combined += best * discount
    return {
        "combined": round(combined, 9),
        **{group_id: value for group_id, value in sorted(per_group.items())},
    }


# -- §13A coverage-qualified absence -----------------------------------------


class AbsenceAdmissibility(enum.StrEnum):
    """§13A. ``INFORMATIONAL_ONLY`` contributes ``NEITHER``."""

    NEGATIVE_EVIDENCE = "negative_evidence"
    INFORMATIONAL_ONLY = "informational_only"


@dataclass(frozen=True, slots=True)
class CoverageThresholds:
    """The active profile's bars for admitting a negative finding. §13A.

    Defaults are deliberately strict: an absence is the easiest thing in an
    investigation to get wrong, so the thresholds require positive declared
    coverage *and* declared detection power before anything counts.
    """

    min_coverage: float = 0.8
    min_detection_power: float = 0.5


@dataclass(frozen=True, slots=True)
class CoverageQualifiedAbsence:
    """"Searched and found nothing", recorded with what it cost to believe.

    §13A: "A non-search ('not searched') is not an object of this type and never
    contributes." The distinction is enforced by requiring ``sources`` to be
    non-empty -- an absence with nowhere it looked is not an absence.
    """

    context_id: str
    query: str
    sources: tuple[str, ...]
    coverage: float | None = None
    detection_power: float | None = None
    errors_accounted: bool = True
    research_action_ref: str = ""
    window: tuple[str, str] = ()
    relevance: str = ""
    method_fingerprint: str = ""
    thresholds: CoverageThresholds = CoverageThresholds()
    absence_id: str = ""
    admissibility: AbsenceAdmissibility = AbsenceAdmissibility.INFORMATIONAL_ONLY

    def __post_init__(self) -> None:
        if not self.query:
            raise ValueError("an absence must state what was looked for")
        if not self.sources:
            raise ValueError(
                "a non-search is not a coverage-qualified absence; "
                "declare where the search happened (§13A)"
            )
        if self.coverage is not None and not 0.0 <= self.coverage <= 1.0:
            raise ValueError(f"coverage must be in [0, 1], got {self.coverage}")
        if self.detection_power is not None and not 0.0 <= self.detection_power <= 1.0:
            raise ValueError(
                f"detection_power must be in [0, 1], got {self.detection_power}"
            )
        if not self.relevance:
            raise ValueError(
                "§13A: an absence must be relevant to a falsifiable prediction "
                "before it may contribute negative support"
            )
        object.__setattr__(
            self,
            "admissibility",
            self._decide_admissibility(),
        )
        if not self.absence_id:
            object.__setattr__(self, "absence_id", self.address())

    def _decide_admissibility(self) -> AbsenceAdmissibility:
        """Unknown coverage or unknown detection power is always INFORMATIONAL_ONLY."""
        if self.coverage is None or self.detection_power is None:
            return AbsenceAdmissibility.INFORMATIONAL_ONLY
        if not self.errors_accounted:
            return AbsenceAdmissibility.INFORMATIONAL_ONLY
        if self.coverage < self.thresholds.min_coverage:
            return AbsenceAdmissibility.INFORMATIONAL_ONLY
        if self.detection_power < self.thresholds.min_detection_power:
            return AbsenceAdmissibility.INFORMATIONAL_ONLY
        return AbsenceAdmissibility.NEGATIVE_EVIDENCE

    def _material(self) -> dict[str, Any]:
        return {
            "context_id": self.context_id,
            "query": self.query,
            "sources": sorted(self.sources),
            "coverage": self.coverage,
            "detection_power": self.detection_power,
            "errors_accounted": self.errors_accounted,
            "relevance": self.relevance,
        }

    def address(self) -> str:
        return f"CQA-{_digest(self._material())}"

    @property
    def contributes_negative_support(self) -> bool:
        """§13A: only a ``NEGATIVE_EVIDENCE`` absence may contribute."""
        return self.admissibility is AbsenceAdmissibility.NEGATIVE_EVIDENCE

    def as_dict(self) -> dict[str, Any]:
        return {
            "absence_id": self.absence_id,
            "context_id": self.context_id,
            "query": self.query,
            "sources": list(self.sources),
            "coverage": self.coverage,
            "detection_power": self.detection_power,
            "errors_accounted": self.errors_accounted,
            "admissibility": self.admissibility.value,
            "contributes_negative_support": self.contributes_negative_support,
            "research_action_ref": self.research_action_ref,
            "window": list(self.window),
            "relevance": self.relevance,
            "method_fingerprint": self.method_fingerprint,
        }


# -- §22 saturation ------------------------------------------------------------


class SaturationVerdict(enum.StrEnum):
    """§22.2."""

    UNSATURATED = "unsaturated"
    SATURATED = "saturated"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


class SaturationReason(enum.StrEnum):
    """§22.1: saturation is not "we searched a lot".

    The same vocabulary carries both directions. ``*_MET`` codes record conditions
    that were satisfied and support a ``SATURATED`` verdict; the others record what
    is still missing and explain a refusal. A saturated verdict with no reason
    codes is therefore not constructible -- the platform cannot say "done" without
    saying what was actually achieved.
    """

    # -- conditions that support saturation --
    COVERAGE_MET = "coverage_met"
    INDEPENDENCE_MET = "independence_met"
    SOURCE_FAMILIES_MET = "source_families_met"
    #: The search has stopped teaching us anything. §22.1 counts this *for*
    #: saturation; only a gain still above threshold keeps work open.
    MARGINAL_GAIN_DECLINED = "marginal_gain_declined"

    # -- conditions that block saturation --
    INSUFFICIENT_COVERAGE = "insufficient_coverage"
    INSUFFICIENT_INDEPENDENCE = "insufficient_independence"
    NARROW_SOURCE_FAMILIES = "narrow_source_families"
    UNEXPLORED_CAPABILITY = "unexplored_capability"
    #: Another step would still teach us something.
    MARGINAL_GAIN_REMAINS = "marginal_gain_remains"
    OPEN_CONTRADICTIONS = "open_contradictions"
    UNRESOLVED_OBSTRUCTIONS = "unresolved_obstructions"
    UNKNOWN_INPUTS = "unknown_inputs"


@dataclass(frozen=True, slots=True)
class SaturationState:
    """§22.2, with ``distinct_sources`` and ``n_eff`` kept as separate fields.

    Keeping both is the point: an analyst who sees only ``distinct_sources`` reads
    a syndication cluster as broad coverage.
    """

    obligation_id: str
    verdict: SaturationVerdict
    reason_codes: tuple[SaturationReason, ...] = ()
    coverage: float | None = None
    distinct_sources: int = 0
    effective_independent_sources: float = 0.0
    source_families: int = 0
    marginal_gain: float | None = None
    unexplored_capability_classes: tuple[str, ...] = ()
    contradiction_count: int = 0
    unresolved_obstruction_count: int = 0
    qualified_absences: tuple[str, ...] = ()
    saturation_id: str = ""

    def __post_init__(self) -> None:
        if self.verdict is SaturationVerdict.SATURATED and not self.reason_codes:
            raise ValueError(
                "§22.1: saturation is not 'we searched a lot'; a SATURATED verdict "
                "must carry its reason codes"
            )
        # A syndication cluster can saturate on independence grounds even though
        # its effective count is below its raw count, so a gap between the two is
        # not itself incoherent. What cannot stand is claiming independence was
        # met while only one effective source exists.
        if (
            self.verdict is SaturationVerdict.SATURATED
            and SaturationReason.INDEPENDENCE_MET in self.reason_codes
            and self.effective_independent_sources <= 1.0
            and self.distinct_sources > 1
        ):
            raise ValueError(
                "SATURATED claims independence met while effective sources <= 1"
            )
        if not self.saturation_id:
            material = {
                "obligation_id": self.obligation_id,
                "verdict": self.verdict.value,
                "reasons": sorted(item.value for item in self.reason_codes),
                "distinct": self.distinct_sources,
                "n_eff": self.effective_independent_sources,
            }
            object.__setattr__(self, "saturation_id", f"SAT-{_digest(material)}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "saturation_id": self.saturation_id,
            "obligation_id": self.obligation_id,
            "verdict": self.verdict.value,
            "reason_codes": [item.value for item in self.reason_codes],
            "coverage": self.coverage,
            "distinct_sources": self.distinct_sources,
            "effective_independent_sources": self.effective_independent_sources,
            "source_families": self.source_families,
            "marginal_gain": self.marginal_gain,
            "unexplored_capability_classes": list(self.unexplored_capability_classes),
            "contradiction_count": self.contradiction_count,
            "unresolved_obstruction_count": self.unresolved_obstruction_count,
            "qualified_absences": list(self.qualified_absences),
        }


def assess_saturation(
    obligation_id: str,
    *,
    assessment: IndependenceAssessment,
    coverage: float | None = None,
    source_families: int = 0,
    marginal_gain: float | None = None,
    unexplored_capability_classes: Sequence[str] = (),
    contradiction_count: int = 0,
    unresolved_obstruction_count: int = 0,
    qualified_absences: Sequence[str] = (),
    min_coverage: float = 0.8,
    min_n_eff: int = 2,
    min_source_families: int = 2,
    marginal_gain_threshold: float = 0.05,
) -> SaturationState:
    """§22.1/§22.2: decide whether an obligation is done, and say why.

    Saturation is evaluated on ``n_eff`` and on source-family diversity, never on
    the raw source count. Every path that refuses returns explicit reason codes, so
    "not saturated" always names the missing ingredient rather than being a bare
    negative.
    """
    blocking: list[SaturationReason] = []
    satisfied: list[SaturationReason] = []

    if unresolved_obstruction_count or contradiction_count:
        blocking.append(SaturationReason.OPEN_CONTRADICTIONS)
    if coverage is None:
        blocking.append(SaturationReason.UNKNOWN_INPUTS)
    elif coverage < min_coverage:
        blocking.append(SaturationReason.INSUFFICIENT_COVERAGE)
    else:
        satisfied.append(SaturationReason.COVERAGE_MET)
    if assessment.n_eff < min_n_eff:
        blocking.append(SaturationReason.INSUFFICIENT_INDEPENDENCE)
    else:
        satisfied.append(SaturationReason.INDEPENDENCE_MET)
    if source_families < min_source_families:
        blocking.append(SaturationReason.NARROW_SOURCE_FAMILIES)
    else:
        satisfied.append(SaturationReason.SOURCE_FAMILIES_MET)
    if unexplored_capability_classes:
        blocking.append(SaturationReason.UNEXPLORED_CAPABILITY)
    # §22.1 lists marginal gain among the things saturation *incorporates*, so a
    # declining gain argues for saturation rather than against it. Only a gain
    # still above the threshold -- meaning another step would still teach us
    # something -- keeps the obligation open. Reading it the other way round would
    # have made an exhausted search look unsaturated forever.
    if marginal_gain is None:
        pass
    elif marginal_gain > marginal_gain_threshold:
        blocking.append(SaturationReason.MARGINAL_GAIN_REMAINS)
    else:
        satisfied.append(SaturationReason.MARGINAL_GAIN_DECLINED)

    if unresolved_obstruction_count:
        verdict = SaturationVerdict.BLOCKED
    elif blocking:
        verdict = SaturationVerdict.UNSATURATED
    else:
        verdict = SaturationVerdict.SATURATED

    return SaturationState(
        obligation_id=obligation_id,
        verdict=verdict,
        # A SATURATED verdict carries what was achieved; a refusal carries what is
        # missing. Neither is ever emitted without a reason.
        reason_codes=tuple(
            dict.fromkeys(satisfied if verdict is SaturationVerdict.SATURATED else blocking)
        ),
        coverage=coverage,
        distinct_sources=assessment.raw_count,
        effective_independent_sources=assessment.n_eff,
        source_families=source_families,
        marginal_gain=marginal_gain,
        unexplored_capability_classes=tuple(sorted(unexplored_capability_classes)),
        contradiction_count=contradiction_count,
        unresolved_obstruction_count=unresolved_obstruction_count,
        qualified_absences=tuple(sorted(qualified_absences)),
    )


def independence_obstruction(assessment: IndependenceAssessment):
    """The ``SEMANTIC_OBSTRUCTION`` an unknown-lineage assessment implies.

    Recorded rather than swallowed: §14A.2 rule 3 says to record
    ``INDEPENDENCE_UNKNOWN``, and an obstruction is how this platform records that
    kind of thing.
    """
    if assessment.independence_known:
        return None
    from context.locality import Obstruction

    return Obstruction(
        kind=ObstructionKind.PROVENANCE_OBSTRUCTION,
        detail=f"INDEPENDENCE_UNKNOWN: {assessment.obstruction}",
        subject_refs=tuple(
            member for group in assessment.groups for member in group.members
        ),
    )
