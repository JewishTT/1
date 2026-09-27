"""The acquisition seam: one contract, every stream (feature 018, T008).

``specs/018-world-substrate/spec.md`` D-D and FR-024..FR-027, plan decision D4.
Common Crawl is the first module to reach this seam, not the only shape it has to
fit. The failure this module exists to prevent is the one already visible in the
codebase: ``cc_extract.CaptureObservation`` calls the crawl-index timestamp
``observed_at`` and carries no fetch time at all, so the orchestrator had nothing
honest to put in a ``Capture`` and derived a capture id from
``(source_id, observation_id)`` instead. A second stream would have done the same
thing its own way, and "when did we fetch this" would have had as many answers as
there were modules.

So the contract is fixed here, once, and it has three parts:

* :class:`StreamAdapter` — one method that turns a raw record into a
  :class:`~domain.capture.Capture`, and a :meth:`~StreamAdapter.declaration`
  saying what the stream is and how it expresses time. Not a base class and not a
  registry of callables: a Protocol, because an adapter is written by whoever owns
  the source and inheriting a base class would make "is this a stream" a
  question about a type hierarchy rather than about a shape.
* :class:`DataStream` — the registry record. Five fields
  (``stream_id``, ``kind``, ``temporality``, ``time_axes_supplied``,
  ``adapter_ref``) naming the stream and the axes it supplies, which is also the
  row shape of the ``data_stream`` table in migration 019.
* :class:`StreamRegistry` — the registrar, which refuses a stream that cannot
  state its axes.

The axes are :class:`TimeAxis`, the six that already exist across the platform
(``fetched_at``, ``observed_at``, ``published_at``, ``valid_from``, ``valid_to``,
``known_from``) and no others, because FR-026 forbids a stream module from
introducing a temporal field or reinterpreting an existing one. A stream is
attached by *mapping onto* those six, and the cost of the mapping is visible:
a stream whose source has a timestamp the six do not have has to record that it
could not map it, which is a finding, rather than quietly growing a seventh axis.

Every axis is dispositioned, including the ones the stream cannot supply, and the
disposition names the raw field the axis is read from. That is what makes the
FR-026 refusal decidable: a stream that says nothing about ``fetched_at`` is
indistinguishable from a stream that has not thought about it, and a stream that
says "supplied, from ``date_filed``" is claiming something a reader can check.
The axes a stream declares it cannot supply are kept as
:class:`AxisBinding` records with their reason rather than being dropped, so the
gap is recorded instead of being an absence in a list.

Registration is where the refusals live, because that is the last moment a stream
can be refused. :meth:`StreamRegistry.register` raises
:class:`StreamContractError` with a stable snake_case ``code`` and, for an axis
problem, the missing axis named in both the message and ``missing_axes`` — the
same shape as :class:`domain.capture.CaptureContractError`, so one caller can
switch on either.

Beyond the axis statement, the registry enforces two things a Protocol cannot:

* **The declaration must agree with itself.** ``time_axes_supplied`` is the
  derived summary of the six bindings, and a record that disagrees with its own
  summary is refused rather than stored, because the summary is what gets indexed
  and queried while the bindings are what get read for justification.
* **A capture must match the declaration.** :meth:`StreamRegistry.capture`
  re-checks the adapter's output against the stream's own axis bindings before
  handing it back, so a stream that declares ``fetched_at`` as unsupplied and then
  emits a ``fetched_at`` anyway is refused at the seam with
  ``stream_capture_contradicts_declaration`` — the same substitution FR-025
  forbids, caught one layer earlier than the domain type's own refusal would.

No I/O, no clock, no registry import side effects beyond one empty instance: this
module is pure value types and a registrar.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from domain.capture import UNBATCHED_INGEST_BATCH, Capture
from domain.temporal_observation import SourceTemporalObservation, TemporalAxis


#: The stream registry's historical name for the six temporal axes (FR-026), bound to
#: :class:`domain.temporal_observation.TemporalAxis` rather than defined beside it.
#:
#: The axis vocabulary is a fact about the world - what *kind* of time a value is on -
#: and :class:`~domain.temporal_observation.SourceTemporalObservation` is where such a
#: value lives, so that is where the enum belongs. A stream *declaration* is a promise an
#: adapter makes about those same six axes, and a promise about six strings no record can
#: be built from is a promise with no consequence.
#:
#: **A plain alias, and specifically not a subclass.** Two enums with six matching members
#: would drift the first time an axis is added, and drift *silently*, because each would
#: remain internally consistent. A subclass would be worse than a copy: the members would
#: be distinct objects of distinct classes, so ``TimeAxis.X is TemporalAxis.X`` would be
#: False and an ``isinstance`` check would pass or fail according to which name the caller
#: happened to import. One enum, two names, no way to be wrong.
#:
#: The module still offers no way to extend the set: an adapter cannot declare a seventh
#: axis because there is nowhere to put one, and it cannot reinterpret one because
#: :class:`AxisBinding` names the raw field each is read from, so "this stream's
#: ``valid_from`` is actually its publication date" is visible in the registry row rather
#: than buried in a mapping function.
TimeAxis = TemporalAxis

#: Every temporal axis a stream may supply, in the order FR-007 enumerates them.
#:
#: Fixed centrally and referenced by name from the refusal message, so a stream that
#: omits one is told *which* one rather than being told it was incomplete - the
#: refusal names the gap because an incomplete answer to "which of the six" is not an
#: answer at all. The knowledge axis is a range: ``known_until`` is its open end
#: and is carried by :attr:`AxisBinding.range_end_field` rather than being a seventh
#: axis, because FR-007 counts six and the open end of one of them is not a new kind
#: of time. Declared after the enum so it can name the members.
TIME_AXES: tuple[TimeAxis, ...] = tuple(TimeAxis)


class StreamKind(StrEnum):
    """What kind of thing a stream reads, in the vocabulary the registry persists.

    The distinctions here are the ones that change how a stream's time must be
    read, so the vocabulary is deliberately small. ``BULK_ARCHIVE`` and
    ``PUBLIC_REGISTER`` both distribute files over HTTP without an API and are
    separated because their temporality differs, which is what
    :class:`StreamTemporality` records; ``BULK_ARCHIVE`` is a publisher's index of
    retrievals that happened elsewhere, and a public register's records are events
    in the world.
    """

    BULK_ARCHIVE = "bulk_archive"
    PUBLIC_REGISTER = "public_register"
    RELEASE_SNAPSHOT = "release_snapshot"
    SITE_PUBLICATION = "site_publication"


class StreamTemporality(StrEnum):
    """How a stream expresses time, which is not a detail of its adapter (FR-026).

    The five members are the shapes of time a stream can have, and each one
    decides what its timestamps mean before a single record is read. Stating the
    temporality is what makes a mapping checkable: a ``REGISTRAR_ACCEPTANCE``
    stream that binds its instant to ``observed_at`` has made a claim a reader can
    reject, whereas without the temporality the same binding is just a field name.

    - :attr:`FETCH_EVENT` — the stream performs the retrieval and measures it. The
      only temporality that may supply :attr:`TimeAxis.FETCHED_AT`.
    - :attr:`INDEX_CATALOGUE` — the stream reads a publisher's index of retrievals
      that happened elsewhere. Its instants are index entries: honest as an
      *index observation* and not fetch times (FR-025).
    - :attr:`REGISTRAR_ACCEPTANCE` — the stream reads a public register whose
      instants are when a record was accepted into the public record. A world
      fact, on a closed archive, addressed by an accession number.
    - :attr:`RELEASE_SNAPSHOT` — the stream reads versioned releases. Its time is
      an interval over which a whole snapshot is current, so every record in one
      release shares an instant by construction rather than by measurement.
    - :attr:`NO_TEMPORALITY` — the stream expresses no time of its own. A stream
      that still populates a timestamp under this temporality has invented one.
    """

    FETCH_EVENT = "fetch_event"
    INDEX_CATALOGUE = "index_catalogue"
    REGISTRAR_ACCEPTANCE = "registrar_acceptance"
    RELEASE_SNAPSHOT = "release_snapshot"
    NO_TEMPORALITY = "no_temporality"


#: Temporality values under which a stream may supply a real fetch time.
#:
#: A closed set rather than a check for one member, so adding a second fetch-like
#: temporality later is a deliberate edit here and not an accident elsewhere.
FETCH_EVENT_TEMPORALITIES: frozenset[StreamTemporality] = frozenset(
    {StreamTemporality.FETCH_EVENT}
)


class StreamContractError(ValueError):
    """A stream cannot be registered, or contradicts its own registration.

    A ``ValueError`` carrying the stable snake_case ``code`` a validation layer
    reports, shaped like :class:`domain.capture.CaptureContractError` so one caller
    can switch on either. ``missing_axes`` is populated for the FR-026 refusals
    and is empty otherwise, so a caller that must name the gap can read it off the
    error rather than parse the message.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        stream_id: str = "",
        missing_axes: Iterable[TimeAxis] = (),
    ) -> None:
        self.code = code
        self.message = message
        self.stream_id = stream_id
        self.missing_axes: tuple[TimeAxis, ...] = tuple(missing_axes)
        named = ", ".join(axis.value for axis in self.missing_axes)
        super().__init__(f"[{code}] {message}" + (f" (missing: {named})" if named else ""))


@dataclass(frozen=True)
class AxisBinding:
    """One axis, and what a stream says about it.

    ``supplied`` is the answer; ``source_field`` is the raw field the axis is read
    from, and it is required when ``supplied`` is true because a stream that
    supplies an axis without saying where from has stated a conclusion and not a
    mapping. ``reason`` is required when ``supplied`` is false and is the reason
    the axis is absent, which is the difference between "this source has no such
    field" and "we have not worked out what it means here" (FR-025).

    ``range_end_field`` is only meaningful for a range axis (:attr:`TimeAxis.KNOWN_FROM`),
    where it names the field supplying the open end. It is empty for a point axis
    rather than absent from the type, so a binding has one shape and a reader does
    not have to check the axis before reading the field.
    """

    axis: TimeAxis
    supplied: bool
    source_field: str = ""
    range_end_field: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        """Fail closed on a half-stated binding, naming the axis and the gap."""
        if self.supplied and not str(self.source_field).strip():
            raise StreamContractError(
                "stream_axis_source_field_missing",
                f"axis {self.axis.value} is declared supplied but names no source_field: "
                "a supplied axis must say which raw field it is read from (FR-026)",
                stream_id=self.axis.value,
                missing_axes=(self.axis,),
            )
        if not self.supplied and not str(self.reason).strip():
            raise StreamContractError(
                "stream_axis_reason_missing",
                f"axis {self.axis.value} is declared unsupplied with no reason: an "
                "unstated gap is indistinguishable from an unexamined one (FR-025)",
                stream_id=self.axis.value,
                missing_axes=(self.axis,),
            )

    def to_dict(self) -> dict[str, object]:
        """The binding as a row-shaped mapping, for ``data_stream.axis_declarations``."""
        return {
            "axis": self.axis.value,
            "supplied": self.supplied,
            "source_field": self.source_field,
            "range_end_field": self.range_end_field,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> AxisBinding:
        """Rebuild a binding from its stored mapping, refusing an unknown axis by name."""
        raw_axis = str(payload.get("axis", ""))
        try:
            axis = TimeAxis(raw_axis)
        except ValueError as exc:
            raise StreamContractError(
                "stream_axis_unknown",
                f"{raw_axis!r} is not a time axis; the six are "
                f"{[member.value for member in TimeAxis]} and a stream may not add a "
                "seventh (FR-026)",
                stream_id=raw_axis,
            ) from exc
        return cls(
            axis=axis,
            supplied=bool(payload.get("supplied", False)),
            source_field=str(payload.get("source_field", "")),
            range_end_field=str(payload.get("range_end_field", "")),
            reason=str(payload.get("reason", "")),
        )


@dataclass(frozen=True)
class StreamDeclaration:
    """What a stream says about itself before a single record is read.

    The four fields are what :meth:`StreamAdapter.declaration` returns and what
    :class:`DataStream` is built from. ``axes`` is the whole statement: one
    :class:`AxisBinding` per :data:`TIME_AXES` member, in any order, no duplicates
    and none omitted — the registrar enforces that and refuses by name.
    """

    stream_id: str
    kind: StreamKind
    temporality: StreamTemporality
    axes: tuple[AxisBinding, ...]


@dataclass(frozen=True)
class CaptureContext:
    """The acquisition-run facts a stream cannot know about itself.

    :class:`~domain.capture.Capture` is tenant-scoped and batch-attributed, and
    neither fact belongs to a source: which tenant is ingesting and which
    ingestion attempt this is are properties of *this run over that source*. So
    they travel beside the record rather than inside the adapter, which is what
    lets one registered adapter serve every tenant and every batch instead of
    binding a process-wide singleton to one of them (constitution IV, FR-009).

    ``ingest_batch_id`` defaults to
    :data:`~domain.capture.UNBATCHED_INGEST_BATCH`, the sentinel that records a
    declared absence rather than inventing a batch id — the same value a capture
    takes when no run is being attributed, and the reason a batch-less capture is
    still a real record rather than an unattributable one.
    """

    tenant_id: str
    ingest_batch_id: str = UNBATCHED_INGEST_BATCH
    ingest_attempt: int = 1
    recorded_by: str = ""


@runtime_checkable
class StreamAdapter(Protocol):
    """A source module that produces :class:`~domain.capture.Capture` records (FR-024).

    One method produces captures; the other says what the stream is. That is the
    whole contract, and it is small on purpose: a stream module that needs a third
    required method to be understood is a stream module with its own idea of what
    acquisition means, which is the thing FR-024 forbids.

    ``context`` is keyword-only and required, carrying the run's tenant and batch
    (:class:`CaptureContext`). It is a parameter rather than adapter state so that
    one registered adapter serves every tenant: a stream module bound to a tenant at
    construction time would make the process-wide registrar a single-tenant object,
    and a cross-tenant write would become a matter of which adapter someone
    happened to construct (constitution IV).

    ``to_capture`` returns ``None`` for a record the stream cannot honestly turn
    into a capture — a line it cannot name the bytes of, an entry with no target —
    rather than raising or inventing. An adapter that raises on a malformed record
    turns one bad line into a failed batch, and one that invents a digest turns a
    gap in the source into a lie in the evidence chain.
    """

    def declaration(self) -> StreamDeclaration:
        """The stream's identity, its temporality, and all six axis bindings."""
        ...

    def to_capture(self, record: object, *, context: CaptureContext) -> Capture | None:
        """One raw record as one :class:`Capture`, or ``None`` if it cannot be one."""
        ...


@dataclass(frozen=True)
class DataStream:
    """The registry record for one data stream (FR-024, FR-026, SC-15).

    ``time_axes_supplied`` is the summary — the axes this stream supplies, in
    :data:`TIME_AXES` order — and it is checked against ``axis_bindings`` at
    registration rather than trusted, because it is the column an index and a query
    read while the bindings are what a reader consults for a justification. Both are
    stored: the summary answers "what does this stream have" in one indexed read,
    and the bindings answer "why" including for the axes it does not have.

    ``adapter_ref`` is a dotted path to the module and class implementing
    :class:`StreamAdapter`, never an instance, so the row stays serialisable and a
    deployment can resolve the module it was registered with (I-1, I-5).
    """

    stream_id: str
    kind: StreamKind
    temporality: StreamTemporality
    time_axes_supplied: tuple[TimeAxis, ...]
    axis_bindings: tuple[AxisBinding, ...]
    adapter_ref: str

    @property
    def unsupplied_axes(self) -> tuple[TimeAxis, ...]:
        """The axes this stream states it cannot supply, in :data:`TIME_AXES` order."""
        supplied = set(self.time_axes_supplied)
        return tuple(axis for axis in TIME_AXES if axis not in supplied)

    def binding(self, axis: TimeAxis) -> AxisBinding:
        """The one binding for ``axis``; a registered stream has exactly one."""
        for candidate in self.axis_bindings:
            if candidate.axis == axis:
                return candidate
        raise StreamContractError(
            "stream_axis_undeclared",
            f"stream {self.stream_id!r} has no binding for axis {axis.value}",
            stream_id=self.stream_id,
            missing_axes=(axis,),
        )

    def supplies(self, axis: TimeAxis) -> bool:
        """Whether this stream states it supplies ``axis``."""
        return axis in self.time_axes_supplied

    def to_dict(self) -> dict[str, object]:
        """The record as a ``data_stream`` row mapping.

        Key names match the migration's columns one for one, so the mapping is what
        a repository inserts rather than a shape it has to translate.
        """
        return {
            "stream_id": self.stream_id,
            "kind": self.kind.value,
            "temporality": self.temporality.value,
            "time_axes_supplied": [axis.value for axis in self.time_axes_supplied],
            "axis_declarations": [binding.to_dict() for binding in self.axis_bindings],
            "adapter_ref": self.adapter_ref,
        }

    @classmethod
    def from_adapter(cls, adapter: StreamAdapter, *, adapter_ref: str) -> DataStream:
        """Build the record from an adapter's own declaration.

        Deliberately does no validation of its own. Building a record that the
        registrar would refuse is useful — the refusal message is the interesting
        output, and a module-level constructor that validated would make it
        impossible to observe — so the checks live in one place.
        """
        declaration = adapter.declaration()
        return cls(
            stream_id=declaration.stream_id,
            kind=declaration.kind,
            temporality=declaration.temporality,
            time_axes_supplied=tuple(
                binding.axis
                for binding in sorted(
                    declaration.axes, key=lambda item: TIME_AXES.index(item.axis)
                )
                if binding.supplied
            ),
            axis_bindings=tuple(declaration.axes),
            adapter_ref=adapter_ref,
        )


class StreamRegistry:
    """The registrar: the one place a stream is allowed to be refused (FR-026).

    Registration is the last moment refusal is possible — once a stream is
    registered its captures exist, and by then a stream with an unstated axis has
    already decided what a missing timestamp means. So every axis question is
    asked here and answered by raising :class:`StreamContractError`:

    * an axis of :data:`TIME_AXES` with no binding → ``stream_axis_undeclared``,
      naming the axis;
    * the same axis bound twice → ``stream_axis_duplicated``, naming the axis;
    * a binding missing its source field or its reason → refused by
      :class:`AxisBinding` itself, with the axis;
    * ``time_axes_supplied`` disagreeing with the bindings →
      ``stream_axis_supply_mismatch``, naming the axes the two sides disagree on;
    * a blank ``stream_id`` or ``adapter_ref`` → ``stream_id_missing`` /
      ``stream_adapter_ref_missing``;
    * a non-fetch temporality declaring ``fetched_at`` supplied, or a fetch
      temporality not declaring it → ``stream_temporality_conflict``, naming the
      axis. A stream that claims to have measured a retrieval while its temporality
      says it reads someone else's index has one of the two wrong, and which one is
      not decidable here, so both are refused;
    * a second registration of one ``stream_id`` with a different record →
      ``stream_conflict``. Re-registering an equal record is idempotent, so a module
      imported twice is not an error.

    Adaptation goes through :meth:`capture` rather than through the adapter
    directly, because a Protocol cannot check the adapter's output against the
    adapter's own declaration. A capture whose ``fetched_at`` contradicts the
    stream's binding for :attr:`TimeAxis.FETCHED_AT` raises
    ``stream_capture_contradicts_declaration`` here, one layer before
    :class:`~domain.capture.Capture` would refuse it — and for a stream that
    declares the axis *supplied* while emitting no fetch time at all, this is the
    only check there is, because the domain type cannot know the stream had
    promised one (FR-025).
    """

    def __init__(self) -> None:
        self._streams: dict[str, DataStream] = {}
        self._adapters: dict[str, StreamAdapter] = {}

    def register(self, stream: DataStream, adapter: StreamAdapter) -> DataStream:
        """Register a stream and its adapter, or refuse the stream by name.

        Returns the stored record so a caller can use the canonical ordering and
        the checker's outcome without re-deriving either.
        """
        self._refuse_unusable(stream)
        stream_id = stream.stream_id
        declared = adapter.declaration()
        if declared.stream_id != stream_id:
            raise StreamContractError(
                "stream_declaration_mismatch",
                f"registry record is {stream_id!r} but the adapter declares "
                f"{declared.stream_id!r}; one adapter, one stream id",
                stream_id=stream_id,
            )
        existing = self._streams.get(stream_id)
        if existing is not None and existing != stream:
            raise StreamContractError(
                "stream_conflict",
                f"stream {stream_id!r} is already registered with a different "
                "declaration; a stream's axes are not rewritten in place (FR-026)",
                stream_id=stream_id,
            )
        if existing is not None and self._adapters[stream_id].declaration() != declared:
            raise StreamContractError(
                "stream_conflict",
                f"stream {stream_id!r} is already registered with a different adapter "
                "declaration; a stream's axes are not rewritten in place (FR-026)",
                stream_id=stream_id,
            )
        self._streams[stream_id] = stream
        self._adapters[stream_id] = adapter
        return stream

    def get(self, stream_id: str) -> DataStream:
        """The registered record for ``stream_id``.

        A ``KeyError`` subclass, matching
        :class:`adapters.registry.SourceNotFoundError`: an unregistered stream is
        a caller error, not a contract violation, and is reported differently from
        one.
        """
        try:
            return self._streams[str(stream_id).strip()]
        except KeyError as exc:
            raise StreamNotRegisteredError(
                f"no data stream is registered as {str(stream_id)!r}; registered: "
                f"{sorted(self._streams)}"
            ) from exc

    def adapter_for(self, stream_id: str) -> StreamAdapter:
        """The adapter registered alongside ``stream_id``."""
        self.get(stream_id)
        return self._adapters[str(stream_id).strip()]

    def capture(
        self, stream_id: str, record: object, *, context: CaptureContext
    ) -> Capture | None:
        """Adapt one raw record into a capture, checked against the declaration.

        The returned capture is not stored: this registry is the seam, and where a
        capture is *kept* is
        :class:`domain.capture.InMemoryCaptureRegistry` or the ``captures`` table.
        Keeping the two apart is what lets a stream be exercised — declared,
        registered, adapted — without a store, which is what the seam is for.
        """
        stream = self.get(stream_id)
        capture = self._adapters[stream.stream_id].to_capture(record, context=context)
        if capture is not None:
            self._refuse_contradiction(stream, capture)
        return capture

    def capture_with_observations(
        self, stream_id: str, record: object, *, context: CaptureContext
    ) -> tuple[Capture | None, tuple[SourceTemporalObservation, ...]]:
        """One record as a capture *and* whatever temporal facts it stated (CD-5).

        The seam a stream states a source time through. ``to_capture`` alone cannot carry
        one, and that is the point: a capture is a record of an act of retrieval, so a
        registrar's acceptance instant or a publisher's issue date does not belong on it.
        An adapter that states temporal facts implements ``to_temporal_observations`` and
        this method returns them; one that does not, returns an empty tuple rather than
        being made to implement a method it has no use for.

        **Probed rather than declared, because the adapters are structurally typed.** The
        protocol is satisfied by shape, so adding a required method would either break
        every existing adapter or force them to inherit a base class they deliberately do
        not. A capability that is optional in the way this one genuinely is optional is
        probed, and the fallback is the honest empty answer rather than a silent skip.

        The observations are linked to ``capture.capture_id``, which is why the capture is
        built first and passed in: a stated time with no retrieval behind it cannot be
        checked against what was actually fetched (I-3), so the link is a parameter
        rather than something an adapter invents.
        """
        stream = self.get(stream_id)
        adapter = self._adapters[stream.stream_id]
        capture = adapter.to_capture(record, context=context)
        if capture is None:
            return None, ()
        self._refuse_contradiction(stream, capture)
        produce = getattr(adapter, "to_temporal_observations", None)
        if produce is None:
            return capture, ()
        observations = tuple(
            produce(record, context=context, capture_ref=capture.capture_id)
        )
        for observation in observations:
            if observation.tenant_id != capture.tenant_id:
                raise StreamContractError(
                    "temporal_observation_tenant_mismatch",
                    f"observation {observation.observation_id} is from tenant "
                    f"{observation.tenant_id!r} and its capture belongs to "
                    f"{capture.tenant_id!r}; cross-tenant lineage is refused fail-closed "
                    "(constitution IV)",
                    stream_id=stream.stream_id,
                )
        return capture, observations

    def captures(
        self, stream_id: str, records: Iterable[object], *, context: CaptureContext
    ) -> tuple[Capture, ...]:
        """Adapt an iterable of raw records, dropping the ones that are not captures.

        One refusal stops the batch: a stream that contradicts its own declaration
        is broken, and continuing would produce a lineage of captures some of which
        the stream never claimed.
        """
        return tuple(
            capture
            for capture in (
                self.capture(stream_id, record, context=context) for record in records
            )
            if capture is not None
        )

    def streams(self) -> tuple[DataStream, ...]:
        """Every registered record, in registration order."""
        return tuple(self._streams.values())

    def __contains__(self, stream_id: object) -> bool:
        return str(stream_id) in self._streams

    def __len__(self) -> int:
        return len(self._streams)

    def _refuse_unusable(self, stream: DataStream) -> None:
        """Every check about the record itself, in the order a reader needs them."""
        if not str(stream.stream_id).strip():
            raise StreamContractError(
                "stream_id_missing",
                "a data stream requires a stream_id: the registry is addressed by it "
                "and a capture cannot be traced back to an unnamed source",
            )
        if not str(stream.adapter_ref).strip():
            raise StreamContractError(
                "stream_adapter_ref_missing",
                f"stream {stream.stream_id!r} requires an adapter_ref: the record names "
                "a module, never an instance, so a deployment resolves the adapter it "
                "was registered with (I-5)",
                stream_id=stream.stream_id,
            )
        self._refuse_understated(stream)
        self._refuse_duplicated(stream)
        self._refuse_temporality(stream)
        self._refuse_summary_mismatch(stream)

    def _refuse_understated(self, stream: DataStream) -> None:
        """Refuse a stream that left an axis unsaid, naming every axis it left out."""
        declared = {binding.axis for binding in stream.axis_bindings}
        missing = tuple(axis for axis in TIME_AXES if axis not in declared)
        if missing:
            raise StreamContractError(
                "stream_axis_undeclared",
                f"stream {stream.stream_id!r} does not state "
                f"{len(missing)} of the six time axes; a stream that cannot say which "
                "axes it supplies is not registrable, and 'I did not think about it' is "
                "not an answer about time (FR-026)",
                stream_id=stream.stream_id,
                missing_axes=missing,
            )

    def _refuse_duplicated(self, stream: DataStream) -> None:
        """Refuse two bindings for one axis, naming it."""
        seen: set[TimeAxis] = set()
        duplicated: list[TimeAxis] = []
        for binding in stream.axis_bindings:
            if binding.axis in seen and binding.axis not in duplicated:
                duplicated.append(binding.axis)
            seen.add(binding.axis)
        if duplicated:
            raise StreamContractError(
                "stream_axis_duplicated",
                f"stream {stream.stream_id!r} binds "
                f"{[axis.value for axis in duplicated]} more than once; one axis has one "
                "answer or it has none (FR-026)",
                stream_id=stream.stream_id,
                missing_axes=tuple(duplicated),
            )

    def _refuse_temporality(self, stream: DataStream) -> None:
        """Refuse a fetch-time claim the stream's own temporality contradicts."""
        claims_fetch = stream.supplies(TimeAxis.FETCHED_AT)
        may_fetch = stream.temporality in FETCH_EVENT_TEMPORALITIES
        if claims_fetch == may_fetch:
            return
        if claims_fetch:
            raise StreamContractError(
                "stream_temporality_conflict",
                f"stream {stream.stream_id!r} declares temporality "
                f"{stream.temporality.value!r} and still supplies "
                f"{TimeAxis.FETCHED_AT.value}: only a stream that performs the retrieval "
                "measures it, and the nearest timestamp a stream holds is never "
                "promoted into a fetch time (FR-025)",
                stream_id=stream.stream_id,
                missing_axes=(TimeAxis.FETCHED_AT,),
            )
        raise StreamContractError(
            "stream_temporality_conflict",
            f"stream {stream.stream_id!r} declares temporality "
            f"{stream.temporality.value!r} and refuses to supply "
            f"{TimeAxis.FETCHED_AT.value}: a {stream.temporality.value} stream is one "
            "that measures its own retrieval, so one of the two is wrong (FR-025)",
            stream_id=stream.stream_id,
            missing_axes=(TimeAxis.FETCHED_AT,),
        )

    def _refuse_summary_mismatch(self, stream: DataStream) -> None:
        """Refuse a summary that disagrees with the bindings it summarises."""
        supplied = tuple(
            binding.axis
            for binding in sorted(
                stream.axis_bindings, key=lambda item: TIME_AXES.index(item.axis)
            )
            if binding.supplied
        )
        if supplied != tuple(stream.time_axes_supplied):
            summary = set(stream.time_axes_supplied)
            from_bindings = {binding.axis for binding in stream.axis_bindings if binding.supplied}
            raise StreamContractError(
                "stream_axis_supply_mismatch",
                f"stream {stream.stream_id!r} lists time_axes_supplied "
                f"{[axis.value for axis in stream.time_axes_supplied]} but its bindings "
                f"supply {[axis.value for axis in supplied]}; the summary is the "
                "indexed read and the bindings are the justification, so they may not "
                "disagree (FR-026)",
                stream_id=stream.stream_id,
                missing_axes=tuple(
                    axis for axis in TIME_AXES if (axis in summary) != (axis in from_bindings)
                ),
            )

    def _refuse_contradiction(self, stream: DataStream, capture: Capture) -> None:
        """Refuse a capture that disagrees with the stream that produced it."""
        declared = stream.supplies(TimeAxis.FETCHED_AT)
        if capture.has_fetch_time == declared:
            return
        raise StreamContractError(
            "stream_capture_contradicts_declaration",
            f"stream {stream.stream_id!r} declares {TimeAxis.FETCHED_AT.value} "
            f"{'supplied' if declared else 'unsupplied'} and emitted a capture with "
            f"fetched_at={capture.fetched_at!r} and basis "
            f"{capture.time_basis.value!r}",
            stream_id=stream.stream_id,
            missing_axes=(TimeAxis.FETCHED_AT,),
        )


class StreamNotRegisteredError(KeyError):
    """Raised when a stream id has not been registered (not a contract violation)."""

    def __str__(self) -> str:
        return str(self.args[0]) if self.args else ""


#: The process-wide registrar, following :mod:`adapters.registry`'s single-registry
#: convention: which streams a deployment has attached is a fact about the process,
#: not a value each caller assembles. Empty at import — no module registers itself
#: on import, so a caller decides what is attached and a fresh process starts with
#: nothing rather than with whatever an import order happened to bring in.
STREAMS = StreamRegistry()


__all__ = [
    "FETCH_EVENT_TEMPORALITIES",
    "STREAMS",
    "TIME_AXES",
    "AxisBinding",
    "CaptureContext",
    "DataStream",
    "StreamAdapter",
    "StreamContractError",
    "StreamDeclaration",
    "StreamKind",
    "StreamNotRegisteredError",
    "StreamRegistry",
    "StreamTemporality",
    "TimeAxis",
]
