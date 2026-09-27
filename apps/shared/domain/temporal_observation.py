"""Source-stated temporal facts, as their own records (feature 019, CD-5).

The gap this module exists to close, stated as plainly as it can be: a registrar's
acceptance instant, a publisher's issue date, a release's effective interval - these are
*about the world*, they arrive with the source, and until now the platform had nowhere to
put them. ``Capture`` is a record of an act of retrieval, and widening it with a
``published_at`` would have been the easy wrong answer twice over: it would make a
retrieval record carry a fact about the world, and it would leave a single nullable
timestamp unable to say whether the value was absent, unparsed, or never looked for.

So the value is separate, and it is a record in its own right rather than a field.

**Why not just another timestamp column.** The interesting cases are not "one more
instant". They are: an acceptance date stated at *day* granularity, so that midnight UTC
is an artefact of parsing rather than a fact anybody stated; the same date appearing in
two documents with two different meanings; and a fact whose open end is unknown, which is
the common case and must not be padded to "now". Each of those is unrepresentable in a
``datetime | None`` and representable here, because :attr:`SourceTemporalObservation`
carries the raw text, the precision, the basis, and an optional range end.

**Why the axis vocabulary lives here and not in the stream registry.**
:data:`apps.acquisition.stream.TimeAxis` already names the six axes a stream may express
time on, and it is the right list. But a stream declaration is a *promise about an
adapter*; the axes are a fact about the world, and the observation is a fact about the
world. So the enum is defined here and :mod:`apps.acquisition.stream` binds its historical
name to it. One definition, two names, and the two vocabularies cannot drift apart —
which they would, silently, if each had its own copy of six strings.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Any

from domain.capture import CaptureTimeBasis
from domain.relation_identity import canonical_material, digest128

#: Prefix for the content address, so a stored observation is recognisable by eye.
OBSERVATION_ID_PREFIX = "STO-"


class TemporalAxis(StrEnum):
    """Which kind of time a stated fact is on (FR-026's six, and only those six).

    An *axis* answers "what kind of time is this" and a
    :class:`~domain.capture.CaptureTimeBasis` answers "how do we know it" - two different
    questions, which is why they are two vocabularies. ``published_at`` under basis
    ``PUBLICATION`` is a registrar's acceptance instant read from the register; the same
    axis under ``DERIVED`` is a snapshot interval computed from a day-granularity field.
    Collapsing the pair would lose exactly the distinction a reader needs in order to
    discount a date.

    Closed on purpose. A seventh axis is refused by name, with the six listed in the
    refusal, so the caller is told what the platform *can* express rather than only what it
    cannot. FR-026 counts six, and the open end of ``known_from`` is carried as
    :attr:`SourceTemporalObservation.stated_value_end` rather than invented as a seventh
    kind of time - a range's end is not a new kind of time, and the temptation to add it
    is exactly how a temporal vocabulary quietly becomes unbounded.
    """

    FETCHED_AT = "fetched_at"
    OBSERVED_AT = "observed_at"
    PUBLISHED_AT = "published_at"
    VALID_FROM = "valid_from"
    VALID_TO = "valid_to"
    KNOWN_FROM = "known_from"


#: Every axis, in the order FR-007 enumerates them. Named so a refusal can point at the
#: list rather than merely refusing, and so a caller can iterate the vocabulary rather
#: than re-typing six strings.
TEMPORAL_AXES: tuple[TemporalAxis, ...] = tuple(TemporalAxis)

#: The one axis that is a range rather than an instant. A fact became knowable at a start
#: and stopped being knowable at an open end that is usually still open.
RANGE_AXES: frozenset[TemporalAxis] = frozenset({TemporalAxis.KNOWN_FROM})


class TemporalPrecision(StrEnum):
    """How fine the source's own statement was, before we parsed it.

    This is the field that stops the platform from inventing precision. An EDGAR
    ``date filed`` is a *day*; parsing it to ``2024-03-15T00:00:00Z`` produces an instant
    that is a convention, not an observation, and a reader who cannot see the difference
    will compare it against a second-resolution fact and draw a conclusion from the noise.

    - :attr:`SECOND` — the source stated a time of day.
    - :attr:`MINUTE` / :attr:`HOUR` — stated to that resolution.
    - :attr:`DAY` / :attr:`MONTH` / :attr:`YEAR` — a calendar date, or part of one. The
      parsed instant is the *start* of the stated interval and the reader is told so here
      rather than being left to assume midnight was measured.
    - :attr:`RANGE` — the source stated an interval, not a point. Paired with
      :attr:`SourceTemporalObservation.stated_value_end`.
    - :attr:`UNKNOWN` — the source stated a value and we do not know how fine it was. An
      honest gap, and distinct from :attr:`~domain.capture.CaptureTimeBasis.ABSENT`,
      which means there was no value at all.
    """

    SECOND = "second"
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"
    MONTH = "month"
    YEAR = "year"
    RANGE = "range"
    UNKNOWN = "unknown"


#: Axes that are a point in time, so a range end on one of them is a contradiction rather
#: than a refinement.
POINT_AXES: frozenset[TemporalAxis] = frozenset(set(TEMPORAL_AXES) - RANGE_AXES)


class TemporalObservationContractError(ValueError):
    """A stated temporal fact cannot be recorded from these fields.

    A ``ValueError`` carrying a stable snake_case ``code``, matching
    :class:`domain.capture.CaptureContractError` and
    :class:`domain.relation_claim.RelationContractError` so one caller can switch on any of
    them.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


def _coerce_enum(enum_cls, value: object, field: str, allowed: list[str]):
    """Coerce through a closed vocabulary, refusing an outsider *and listing the six*.

    A raw ``ValueError`` from ``Enum(value)`` would technically be a refusal, but it
    answers the wrong question: it says the string is not a member without saying what
    *is*. A caller who hit this on a real source - a register with a seventh date column,
    a publisher schema that grew one - would have no idea whether the platform had a home
    for their value under another name or genuinely lacked the concept. Listing the
    vocabulary in the refusal makes the second reading available and costs one line.
    """
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(value)
    except ValueError as exc:
        raise TemporalObservationContractError(
            f"{field}_unknown",
            f"{value!r} is not a {field}; the closed vocabulary is {allowed}. A value the "
            "platform has no name for is a finding to report, not one to round to the "
            "nearest member - mapping an unknown axis onto a known one would put the wrong "
            "kind of time into the world with the right kind's confidence",
        ) from exc


def _iso(value: Any) -> str | None:
    """One instant as canonical text. ``None`` means honestly absent, not "unknown"."""
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TemporalObservationContractError(
            "stated_value_type",
            f"a stated temporal value must be a datetime, got {type(value).__name__}",
        )
    if value.tzinfo is None:
        raise TemporalObservationContractError(
            "stated_value_naive",
            f"a stated temporal value must carry a timezone: {value.isoformat()} is naive, "
            "and assuming UTC would put a fact in the world that no source stated",
        )
    return value.astimezone(datetime.fromisoformat("1970-01-01T00:00:00+00:00").tzinfo).isoformat()


def _parse(value: Any) -> datetime:
    """One ISO-8601 instant, with a missing timezone refused rather than assumed.

    The timezone check is repeated here rather than trusted to ``__post_init__``: this runs
    on the *way in* from a stored row, and a row that lost its offset would otherwise be
    silently read as UTC - the exact padding :class:`SourceTemporalObservation` exists to
    prevent, arriving by the back door.
    """
    moment = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if moment.tzinfo is None:
        raise TemporalObservationContractError(
            "stated_value_naive",
            f"stored instant {moment.isoformat()} has no timezone, and assuming UTC would "
            "turn a recorded value into a value nobody stated",
        )
    return moment


@dataclass(frozen=True)
class SourceTemporalObservation:
    """One instant a source stated, kept exactly as stated.

    Frozen, content-addressed and tenant-scoped, like everything else that is a durable
    claim about the world. The fields are grouped by what they answer:

    * **Which fact** — :attr:`temporal_axis` says *what kind* of time this is, and
      :attr:`capture_ref` says which retrieval it was read from. The link is by
      reference, never embedded, so re-capturing the same document cannot produce two
      observations that disagree about a fact.
    * **What was said** — :attr:`raw_value` is the source's own text, verbatim, and
      :attr:`stated_value` is what we parsed out of it. Both are kept because a parser is
      a claim: with the raw text present, a reader can check the parse instead of trusting
      it, and a bug in the parser is visible rather than invisible.
    * **How well** — :attr:`precision` is the source's resolution. This is what makes
      :attr:`stated_value` honest: a day-precision fact parsed to midnight carries a
      ``precision`` that says so.
    * **How we know** — :attr:`basis` reuses
      :class:`~domain.capture.CaptureTimeBasis` rather than inventing a parallel
      vocabulary. ``PUBLICATION`` means the value is a world fact the register stated;
      ``DERIVED`` means we computed it; ``ABSENT`` means the source had no such field,
      which is different from having one we failed to read.
    * **Where** — :attr:`evidence_location` names the raw field, exactly as
      :class:`apps.acquisition.stream.AxisBinding` requires of a supplied axis. A stated
      time with no field behind it is a conclusion, not an observation.

    ``stated_value_end`` is the open end of a range, and only a range axis may carry one:
    :attr:`TemporalAxis.KNOWN_FROM` is the one such axis, and an open end is the ordinary
    case rather than a missing field to be defaulted to "now" - defaulting it would
    assert that a fact stopped being knowable at the moment we looked.
    """

    temporal_axis: TemporalAxis
    capture_ref: str
    stated_value: datetime | None = None
    stated_value_end: datetime | None = None
    raw_value: str = ""
    precision: TemporalPrecision = TemporalPrecision.UNKNOWN
    basis: CaptureTimeBasis = CaptureTimeBasis.PUBLICATION
    evidence_location: str = ""
    tenant_id: str = "default-tenant"
    observation_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "temporal_axis", _coerce_enum(
            TemporalAxis, self.temporal_axis, "temporal_axis", [a.value for a in TEMPORAL_AXES],
        ))
        object.__setattr__(self, "precision", _coerce_enum(
            TemporalPrecision, self.precision, "precision", [p.value for p in TemporalPrecision],
        ))
        object.__setattr__(self, "basis", _coerce_enum(
            CaptureTimeBasis, self.basis, "basis", [b.value for b in CaptureTimeBasis],
        ))
        object.__setattr__(self, "raw_value", str(self.raw_value or ""))
        object.__setattr__(self, "evidence_location", str(self.evidence_location or ""))

        if not str(self.capture_ref).strip():
            raise TemporalObservationContractError(
                "capture_ref_required",
                "a stated temporal fact must name the capture it was read from: an instant "
                "with no retrieval behind it cannot be checked against anything anybody "
                "actually fetched (I-3)",
            )
        if not str(self.tenant_id).strip():
            # Added by the constitutional suite (feature 019, T037). The database already
            # refuses this with ``ck_temporal_observation_tenant``, and both
            # :class:`domain.relation_candidate.RelationCandidate` and
            # :class:`extractors.signals.signal.RelationSignal` refused it here - so this
            # type was the single place a stated instant could be minted with no tenant, and
            # a value type that lets one exist is a row waiting to be written without one.
            # A constitutional property only counts if every type keeps it the same way.
            raise TemporalObservationContractError(
                "tenant_required",
                f"a stated temporal fact must be tenant-scoped, got {self.tenant_id!r}; '' "
                "is not a tenant (constitution IV). NOT NULL in the schema is not enough, "
                "because '' is a string",
            )
        if not self.evidence_location:
            raise TemporalObservationContractError(
                "evidence_location_required",
                f"a stated value on axis {self.temporal_axis.value!r} names no "
                "evidence_location: a time nobody can locate in the source is a conclusion "
                "the platform made and is presenting as an observation",
            )
        if self.basis is CaptureTimeBasis.ABSENT and self.stated_value is not None:
            raise TemporalObservationContractError(
                "absent_basis_with_value",
                f"basis=absent is a stated emptiness, but this observation carries "
                f"{self.stated_value.isoformat()}; one of the two is a lie",
            )
        if self.stated_value is None and self.basis is not CaptureTimeBasis.ABSENT:
            raise TemporalObservationContractError(
                "value_missing_without_absent_basis",
                f"basis={self.basis.value!r} claims a value was read, but stated_value is "
                "None. If the source had no such field, say so with "
                "basis=CaptureTimeBasis.ABSENT; if we failed to read one that exists, that "
                "is a finding to report, not a record to write",
            )
        if self.stated_value_end is not None:
            if self.temporal_axis not in RANGE_AXES:
                raise TemporalObservationContractError(
                    "range_end_on_point_axis",
                    f"axis {self.temporal_axis.value!r} is a point in time, so "
                    f"stated_value_end={self.stated_value_end.isoformat()} contradicts it. "
                    f"Only {sorted(a.value for a in RANGE_AXES)} is a range; inventing a "
                    "seventh axis for an open end is what CD-5 forbids",
                )
            if self.stated_value is None:
                raise TemporalObservationContractError(
                    "range_end_without_start",
                    "a range needs its start: stated_value_end is set while stated_value is "
                    "None, which is an interval with no beginning",
                )
        if self.stated_value is not None and self.stated_value_end is not None:
            if self.stated_value_end < self.stated_value:
                raise TemporalObservationContractError(
                    "range_end_before_start",
                    f"the open end {self.stated_value_end.isoformat()} precedes the start "
                    f"{self.stated_value.isoformat()}",
                )
        if self.temporal_axis in RANGE_AXES and self.precision is not TemporalPrecision.RANGE:
            # Derived from the axis rather than asked for, for the same reason a
            # candidate's predicate state is derived from its refs: the axis already says
            # the value is an interval, and a caller's label adds nothing. It matters most
            # for the open case, where a start with no end is still a range and a caller
            # who said `day` was describing the *start's* resolution - not claiming the
            # fact was a point. The start's own fineness is still recorded: a reader
            # wanting it reads the raw text.
            object.__setattr__(self, "precision", TemporalPrecision.RANGE)

        derived = self._derived_id()
        carried = self.observation_id
        if carried and carried != derived:
            raise TemporalObservationContractError(
                "observation_id_mismatch",
                f"observation carries {carried!r} but its own content addresses to "
                f"{derived!r}; a content address is derived, never trusted",
            )
        object.__setattr__(self, "observation_id", derived)

    def _material(self) -> dict[str, Any]:
        """The material the content address is taken over (FR-005's discipline)."""
        return {
            "tenant_id": self.tenant_id,
            "temporal_axis": str(self.temporal_axis),
            "capture_ref": self.capture_ref,
            "stated_value": _iso(self.stated_value),
            "stated_value_end": _iso(self.stated_value_end),
            "raw_value": self.raw_value,
            "precision": str(self.precision),
            "basis": str(self.basis),
            "evidence_location": self.evidence_location,
        }

    def _derived_id(self) -> str:
        return OBSERVATION_ID_PREFIX + digest128(canonical_material(self._material()))

    @property
    def is_range(self) -> bool:
        """Whether this observation is an interval rather than an instant."""
        return self.temporal_axis in RANGE_AXES

    @property
    def is_ordered_precision(self) -> bool:
        """Whether the parsed instant is the *start* of the interval the source stated.

        True for anything coarser than a second. This is the flag a consumer should read
        before doing arithmetic on :attr:`stated_value`, and it exists because the failure
        it prevents is invisible: the arithmetic succeeds and the answer is wrong by up to
        a year.
        """
        return self.precision in (
            TemporalPrecision.DAY,
            TemporalPrecision.MONTH,
            TemporalPrecision.YEAR,
        )

    def with_id(self) -> SourceTemporalObservation:
        """A copy carrying its own content address. The id is already derived, so this
        re-derives it under a tenant change and refuses a stale one."""
        return replace(self, observation_id="")

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._material(),
            "observation_id": self.observation_id,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> SourceTemporalObservation:
        raw_start = payload.get("stated_value")
        raw_end = payload.get("stated_value_end")
        return cls(
            temporal_axis=TemporalAxis(str(payload["temporal_axis"])),
            capture_ref=str(payload.get("capture_ref", "")),
            stated_value=None if raw_start in (None, "") else _parse(raw_start),
            stated_value_end=None if raw_end in (None, "") else _parse(raw_end),
            raw_value=str(payload.get("raw_value", "")),
            precision=TemporalPrecision(str(payload.get("precision", "unknown"))),
            basis=CaptureTimeBasis(str(payload.get("basis", "publication"))),
            evidence_location=str(payload.get("evidence_location", "")),
            tenant_id=str(payload.get("tenant_id", "default-tenant")),
        )


def observations_by_axis(
    observations: list[SourceTemporalObservation] | tuple[SourceTemporalObservation, ...],
) -> dict[TemporalAxis, SourceTemporalObservation]:
    """Index one observation per axis, refusing a second value for an axis already held.

    A refusal rather than a last-one-wins because a duplicate is a disagreement between
    two extractions of the same fact, and picking either silently would resolve it by
    arrival order - the platform deciding, without recording that it decided, which of two
    readings of the world to believe.
    """
    found: dict[TemporalAxis, SourceTemporalObservation] = {}
    for observation in observations:
        existing = found.get(observation.temporal_axis)
        if existing is not None and existing != observation:
            raise TemporalObservationContractError(
                "conflicting_temporal_observation",
                f"axis {observation.temporal_axis.value!r} is stated twice and differently: "
                f"{existing.observation_id} says {existing.stated_value}, "
                f"{observation.observation_id} says {observation.stated_value}. Both are "
                "kept; a caller must choose, and the choice is recorded (I-3, FR-006)",
            )
        found[observation.temporal_axis] = observation
    return found


__all__ = [
    "OBSERVATION_ID_PREFIX",
    "POINT_AXES",
    "RANGE_AXES",
    "TEMPORAL_AXES",
    "SourceTemporalObservation",
    "TemporalAxis",
    "TemporalObservationContractError",
    "TemporalPrecision",
    "observations_by_axis",
]
