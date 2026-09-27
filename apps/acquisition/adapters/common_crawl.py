"""Common Crawl as an acquisition stream: the first module on the seam (T009).

``specs/018-world-substrate/spec.md`` FR-006, FR-025, D3 and D4. This is the worked
example the specification names: a stream whose index carries an honest instant
that answers a *different question* from "when did we fetch these bytes".

The distinction, stated once so the code below needs no defending:

    A CDX index row says the crawl retrieved ``url`` and published that row at
    ``timestamp``. It does not say when the WARC bytes were fetched, by whom, or
    whether this platform has fetched them at all. Common Crawl retrieved them;
    somebody read the index; this platform has read a line of text.

So ``cc_extract.CaptureObservation`` — which this module **adapts and does not
rewrite** — carries ``observed_at`` and nothing else, and the capture it produces
carries :attr:`~domain.capture.CaptureTimeBasis.INDEX_OBSERVATION` with **no**
``fetched_at`` at all. The index timestamp stays where it belongs, on the
:attr:`~stream.TimeAxis.OBSERVED_AT` binding of this stream's declaration, and
reaching it here is not possible: :class:`~domain.capture.Capture` refuses any pair
of a populated ``fetched_at`` and a basis that is not ``FETCH``, and
:meth:`stream.StreamRegistry.capture` refuses a capture whose fetch time
contradicts the stream's own declaration (FR-025).

That refusal is not defensive decoration. The alternative is one line — pass
``observed_at`` as ``fetched_at`` — and taking it would restore exactly the defect
D3 describes, only now inside a typed value that looks honest: a capture claiming
a retrieval that never happened, at a moment chosen by a publisher's crawl
schedule, with a content address that would thereafter make the fabrication
permanent and replayable.

What the adapter does supply is everything else a capture needs to be a real
acquisition fact: the target URI, the byte-exact ``warc-file@offset,length``
locator, the content digest, the length, and the batch attribution. Those come
from the same index row the timestamp came from, which is the point — the gap is
in the *time*, not in the record.

Two things are deliberately left absent rather than guessed:

* ``media_type`` is empty. :class:`~cc_extract.CaptureObservation` does not carry
  one, and inferring it from a URL suffix would make a guess look like a
  measurement. The WARC record header holds the real value; the index row does not.
* ``content_length`` is absent when the row reports ``0``, because a zero in an
  index row means "not reported" as often as it means "empty", and a capture that
  claims zero bytes of a page it has not read is a claim nothing can check.

A row with no digest produces no capture at all. The index is a catalogue, not a
store, and a capture whose bytes cannot be named is not a capture (FR-006).

Distinct from :mod:`adapters.commoncrawl`, which reads the CC index for
*discovery* — a query planner that wants candidate URLs. This module is on the
acquisition seam and produces :class:`~domain.capture.Capture` records.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from cc_extract import CaptureObservation, normalize_captures
from domain.capture import Capture, CaptureTimeBasis
from domain.temporal_observation import (
    SourceTemporalObservation,
    TemporalAxis,
    TemporalPrecision,
)
from stream import (
    AxisBinding,
    CaptureContext,
    StreamDeclaration,
    StreamKind,
    StreamTemporality,
    TimeAxis,
)

#: The stream's identity in the ``data_stream`` registry, and the module path a
#: deployment resolves the adapter from (I-5).
STREAM_ID = "common-crawl.cdx"
ADAPTER_REF = "adapters.common_crawl:CommonCrawlAdapter"

#: Independence family. Every crawl of every crawl is the same publisher, so two
#: captures from two different crawls are two publications of one source and FR-034
#: must not count them as two independent ones (constitution IV).
SOURCE_FAMILY = "common-crawl"

_NO_FETCH_TIME = (
    "a CDX index row states when the crawl retrieved the url and published that row; "
    "it does not state when the WARC bytes were fetched, by whom, or whether this "
    "platform has fetched them at all, so there is no fetch time to record (FR-006, "
    "FR-025)"
)
_NO_PUBLICATION = (
    "the index publishes the crawl, not the document; a document publication date "
    "lives in the WARC record header, which an index row does not carry"
)
_NO_VALIDITY = (
    "an index row asserts a point observation of a url, not an interval during which "
    "anything about that url was true"
)
_NO_KNOWLEDGE = (
    "when this platform learned of the row is a fact about the reader; the source "
    "cannot state it, and binding the crawl instant here as well as on observed_at "
    "would be two axes answering one question (FR-007)"
)


@dataclass(frozen=True)
class CommonCrawlAdapter:
    """Maps a Common Crawl index row onto a :class:`~domain.capture.Capture`.

    Frozen, and constructed once per source rather than once per record: the stream
    declares itself through :meth:`declaration` and the run's tenant and batch
    arrive per call as a :class:`~stream.CaptureContext`, so one instance serves
    every tenant.

    ``source_id`` is configurable because it names a row in ``sources`` and the
    adapter cannot know which one a deployment minted for this publisher;
    ``source_family`` is not, because independence is a property of the publisher
    and is the same for every deployment.
    """

    source_id: str = "common-crawl"

    def declaration(self) -> StreamDeclaration:
        """The stream's identity and its statement about all six axes.

        One axis supplied, five not, each with its reason. The count is the point:
        a stream that supplied all six would be asserting six measurements it does
        not have, and the reasons are what make the five absences a record rather
        than a silence.
        """
        return StreamDeclaration(
            stream_id=STREAM_ID,
            kind=StreamKind.BULK_ARCHIVE,
            temporality=StreamTemporality.INDEX_CATALOGUE,
            axes=(
                AxisBinding(
                    axis=TimeAxis.FETCHED_AT,
                    supplied=False,
                    reason=_NO_FETCH_TIME,
                ),
                AxisBinding(
                    axis=TimeAxis.OBSERVED_AT,
                    supplied=True,
                    source_field="timestamp",
                ),
                AxisBinding(
                    axis=TimeAxis.PUBLISHED_AT,
                    supplied=False,
                    reason=_NO_PUBLICATION,
                ),
                AxisBinding(
                    axis=TimeAxis.VALID_FROM,
                    supplied=False,
                    reason=_NO_VALIDITY,
                ),
                AxisBinding(
                    axis=TimeAxis.VALID_TO,
                    supplied=False,
                    reason=_NO_VALIDITY,
                ),
                AxisBinding(
                    axis=TimeAxis.KNOWN_FROM,
                    supplied=False,
                    reason=_NO_KNOWLEDGE,
                ),
            ),
        )

    def to_capture(self, record: object, *, context: CaptureContext) -> Capture | None:
        """One index row as one capture, with no fetch time and a stated basis.

        Accepts a :class:`~cc_extract.CaptureObservation` or the raw
        ``Mapping`` an L1 boundary delivers; a mapping is normalised through
        :func:`cc_extract.normalize_captures` — the existing function, unchanged —
        so this module adapts the L1 shape rather than reimplementing it. A row
        ``cc_extract`` drops (no url, no parseable timestamp) and a row with no
        digest both yield ``None``: neither is a capture this stream can honestly
        produce.
        """
        observation = self._as_observation(record)
        if observation is None or not observation.digest.strip():
            return None
        locator = observation.locator if observation.warc_filename.strip() else ""
        return Capture(
            tenant_id=context.tenant_id,
            source_id=self.source_id,
            source_family=SOURCE_FAMILY,
            target_uri=observation.url,
            locator=locator,
            content_digest=observation.digest,
            content_length=observation.length if observation.length > 0 else None,
            media_type="",
            fetched_at=None,
            time_basis=CaptureTimeBasis.INDEX_OBSERVATION,
            transport="cc-warc-range-read" if locator else "cc-index-row",
            ingest_batch_id=context.ingest_batch_id,
            ingest_attempt=context.ingest_attempt,
            recorded_by=context.recorded_by,
        )

    def to_temporal_observations(
        self,
        record: object,
        *,
        context: CaptureContext,
        capture_ref: str,
    ) -> tuple[SourceTemporalObservation, ...]:
        """When the index entry was written, which is a fact about the index (CD-5).

        Common Crawl's ``timestamp`` is the one instant this stream states, and the
        declaration has always bound it to ``observed_at``. The value reached the
        :class:`~cc_extract.CaptureObservation` and stopped there - ``Capture`` cannot hold
        it, because it is not a fetch time and putting it in ``fetched_at`` would promote
        an index entry into a retrieval that never happened here.

        So it is returned as a :class:`SourceTemporalObservation` on the ``observed_at``
        axis, and the basis is what keeps the three CD-5 distinctions sharp:

        * ``INDEX_OBSERVATION``, **not** ``PUBLICATION``. The crawl archive does not know
          when the page was published, and this stream says so - :data:`_NO_PUBLICATION`
          is its declared answer on the ``published_at`` axis. An observer who found a
          publication date here would be reading a fact the index never stated.
        * ``INDEX_OBSERVATION``, **not** ``FETCH``. Nothing here was retrieved by us.
        * precision ``SECOND``, because a CDX timestamp really is second-resolution -
          unlike EDGAR's ``date filed``, which is a day and which the parallel
          observation marks as one. Same axis, same shape, different honest precision.

        A row with no parseable timestamp yields no observation. The capture is already
        refused in that case by :meth:`to_capture`, so in practice this is belt and braces
        rather than a separate path.
        """
        observation = self._as_observation(record)
        if observation is None or not observation.observed_at.strip():
            return ()
        try:
            stated = datetime.fromisoformat(observation.observed_at.replace("Z", "+00:00"))
        except ValueError:
            return ()
        if stated.tzinfo is None:
            return ()
        return (
            SourceTemporalObservation(
                temporal_axis=TemporalAxis.OBSERVED_AT,
                capture_ref=capture_ref,
                stated_value=stated,
                raw_value=observation.observed_at,
                precision=TemporalPrecision.SECOND,
                basis=CaptureTimeBasis.INDEX_OBSERVATION,
                evidence_location="timestamp",
                tenant_id=context.tenant_id,
            ),
        )

    def _as_observation(self, record: object) -> CaptureObservation | None:
        """The L1 value for ``record``, normalising a raw mapping if that is what it is.

        ``normalize_captures`` is a whole-batch function that sorts and dedups, and
        a single-record call through it is the one honest way to reuse it: the sort
        is harmless on a one-element batch and the dedup cannot drop anything. A
        record that is neither shape is not adapted rather than coerced, because
        ``CaptureObservation`` has no tolerant constructor and inventing one here
        would be a second, disagreeing definition of the L1 row.
        """
        if isinstance(record, CaptureObservation):
            return record
        if isinstance(record, Mapping):
            normalized = normalize_captures([record])
            return normalized[0] if normalized else None
        return None


__all__ = [
    "ADAPTER_REF",
    "SOURCE_FAMILY",
    "STREAM_ID",
    "CommonCrawlAdapter",
]
