"""SEC EDGAR full-index as a second acquisition stream (T010, FR-027).

Why this source, and not a second crawl-shaped one
---------------------------------------------------

FR-027 asks for a non-API, non-Common-Crawl stream whose temporality is
*genuinely* different, and the temptation was a sitemap or another bulk archive.
Both were rejected, for the same reason: a sitemap's ``<lastmod>`` and a second
crawl's index entry are both *publisher-asserted modification instants observed
by whoever published an index*, which is the ``INDEX_CATALOGUE`` temporality
Common Crawl already occupies. Attaching one would have made the seam look
exercised while re-testing the same mapping — a seam with two implementations of
one shape is still an untested architecture for the other shape.

EDGAR's **full submission index** files are a different kind of thing:

* They are a **public register**, not a publisher's index of its own retrievals.
  The instant in a row is the registrar's *acceptance datetime* — the moment a
  submission became part of the public record. That is a fact about the world, it
  is written into an archive that is never rewritten, and it is not a statement
  about any reader's observation of anything.
* They are distributed as **static files** over plain HTTPS
  (``.../Archives/edgar/full-index/<year>/QTR<n>/full-index.<yyyymmdd>.zip``, and
  the sibling ``daily-index/.../form.<yyyymmdd>.idx``), with no API, no key, no
  query language and no pagination protocol. That makes them a peer of Common
  Crawl's WARC/CDX distribution rather than a different kind of dependency.
* Their rows are **one line per submission** —
  ``CIK|Company Name|Form Type|Date Filed|Filename`` — so the shape is unlike a
  web page's index entry: no bytes, no offsets, no digests, and a document
  addressed by an immutable path in a closed archive.

The mapping onto the six axes, and what it costs
------------------------------------------------

One axis is supplied and five are not, and the two supplied cases are on opposite
sides of the seam from Common Crawl's:

=====================  ===================  =========================================
axis                   this stream           why
=====================  ===================  =========================================
``fetched_at``         **not supplied**      an index row states when the *registrar
                                            accepted* a filing; nothing in the
                                            distribution records when any party
                                            downloaded it. Substituting the
                                            acceptance date would make every read
                                            of a closed archive look like a live
                                            fetch — FR-006, FR-025.
``observed_at``        **not supplied**      this is a fact about *this platform's*
                                            read of the row. A source cannot state
                                            it, and a stream that fills it in is
                                            asserting something about its reader.
``published_at``       **supplied**          ``date filed``: acceptance *is* the
                                            publication event for an EDGAR
                                            submission — the instant the document
                                            entered the public record.
``valid_from``         **not supplied**      the period of report is a property of
``valid_to``                              the filing's *contents*, which the index
                                            has not read. An index entry has no
                                            validity interval to map.
``known_from``         **not supplied**      the acceptance instant is already bound
                                            to ``published_at``. Binding the same
                                            field to the knowledge axis as well
                                            would be two axes answering one
                                            question, which is precisely the
                                            conflation FR-007 exists to stop.
=====================  ===================  =========================================

Two findings this mapping produced rather than concealed:

1. **Day granularity.** ``date filed`` is ``YYYYMMDD``. Turning a recorded day
   into an instant requires choosing an instant inside it, and
   :func:`iso_utc_from_filed_date` fixes the canonical lower bound (``00:00:00Z``)
   and is the *only* place that convention is written down, so a caller reading
   ``published_at`` off the declared field has to go through it. The instant is
   therefore a stated convention rather than a measurement — a
   :attr:`~domain.capture.CaptureTimeBasis.PUBLICATION` record whose ``Capture``
   side is an honest absence, and whose ``published_at`` side is honest but
   day-quantised.
2. **No per-record content digest.** The index is a catalogue and carries no hash
   of the document it names, while :class:`~domain.capture.Capture` requires
   ``content_digest`` because bytes that cannot be named cannot be deduplicated,
   verified or replayed. The adapter therefore **requires the caller to supply one**
   — read from a WARC sidecar, or computed over the bytes that were actually
   retrieved — and returns ``None`` for a row without it. The tempting
   alternative, hashing the accession number or the path, would produce a stable
   *record identity* while claiming to be a *content* digest, and that
   substitution is the same class of error as promoting an index timestamp into a
   fetch time: a plausible value in a field whose meaning it does not have.

Nothing here reads the network or a clock. The raw record is the ``Mapping`` a
caller has already parsed out of an index file, and the keys this adapter reads
are :data:`REQUIRED_RAW_FIELDS` and :data:`OPTIONAL_RAW_FIELDS`, so a caller knows
what it has to supply before it gets a refusal.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from domain.capture import Capture, CaptureTimeBasis
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
STREAM_ID = "sec-edgar.full-index"
ADAPTER_REF = "adapters.sec_edgar:EdgarFullIndexAdapter"

#: Root every EDGAR document path is relative to. The index's ``Filename`` column
#: carries paths under ``/Archives/``, so this is the one piece of the target URI
#: that is not in the row — and it is a constant of the distribution, not a
#: derivation from the record.
ARCHIVE_ROOT = "https://www.sec.gov/Archives/"

#: Independence family. Every EDGAR row is the U.S. Securities and Exchange
#: Commission speaking once, so a thousand filings are one independent source and
#: FR-034's publication count has to stay separate from it (constitution IV).
SOURCE_FAMILY = "sec-edgar"

_NO_FETCH_TIME = (
    "an EDGAR index row states when the registrar accepted the submission into the "
    "public record; nothing in the distribution states when any party downloaded the "
    "file, and substituting the acceptance date would make every read of a closed "
    "archive look like a live fetch (FR-006, FR-025)"
)
_NO_OBSERVATION = (
    "observed_at is when this platform read the row; it is a fact about the reader, "
    "which a source cannot state and a stream must not assert on the source's behalf"
)
_NO_VALIDITY = (
    "the period of report is a property of the filing's contents, which the index "
    "has not read; an index entry has no validity interval to map"
)
_NO_KNOWLEDGE = (
    "the acceptance instant is already bound to published_at; binding the same field "
    "to the knowledge axis as well would be two axes answering one question (FR-007)"
)

#: Raw-record keys the adapter cannot proceed without. ``content_digest`` is the
#: load-bearing one and the reason is in this module's docstring: an index row names
#: a document, not its bytes, and a capture that cannot name its own bytes cannot be
#: deduplicated, verified or replayed.
REQUIRED_RAW_FIELDS: tuple[str, ...] = ("document_path", "content_digest")

#: Raw-record keys it reads when present and treats as honest absences when not.
#: ``content_length`` and ``media_type`` are absent from an index row; a caller
#: holding the bytes may supply them, and one that does not leaves them out rather
#: than having them guessed from the filename.
OPTIONAL_RAW_FIELDS: tuple[str, ...] = ("date_filed", "content_length", "media_type")

#: The raw field the ``published_at`` axis is declared against, named once so the
#: declaration and a caller reading the row cannot drift apart.
PUBLISHED_AT_FIELD = "date filed"


def iso_utc_from_filed_date(value: object) -> str | None:
    """An EDGAR ``YYYYMMDD`` acceptance date as ISO-UTC, or ``None`` if unparseable.

    Deterministic, and the single place the day-granularity convention is written
    down: the canonical lower bound of the recorded day, ``00:00:00Z``. The
    convention is not a measurement and does not pretend to be one — the register
    records a day, and a reader who needs a finer instant has to say which one
    they chose.

    The counterpart of :func:`cc_extract.iso_utc_from_cc_timestamp`, which does
    the same job for Common Crawl at second granularity. Two streams, two
    granularities, one axis.
    """
    text = str(value or "").strip()
    if len(text) != 8 or not text.isdigit():
        return None
    return f"{text[0:4]}-{text[4:6]}-{text[6:8]}T00:00:00Z"


@dataclass(frozen=True)
class EdgarFullIndexAdapter:
    """Maps one EDGAR full-index submission row onto a :class:`Capture`.

    ``index_uri`` names the index *file* the row came from and is part of every
    capture's locator, so the same submission reached through two different index
    releases is two captures of one payload — which is the distinction FR-009 and
    :attr:`~domain.capture.Capture.payload_key` exist to keep. It defaults to empty
    rather than to a plausible URL: a locator that guesses which file a row came
    from names a file nobody verified.
    """

    source_id: str = "sec-edgar-full-index"
    index_uri: str = ""

    def declaration(self) -> StreamDeclaration:
        """The stream's identity and its statement about all six axes.

        ``REGISTRAR_ACCEPTANCE`` rather than ``INDEX_CATALOGUE``, and the
        difference is the whole reason this stream was chosen: the row's instant is
        when a filing entered the public record, not when a publisher indexed its
        own retrieval. Had it been bound to ``observed_at`` instead, the registry
        row would have said so and the claim would have been rejectable.
        """
        return StreamDeclaration(
            stream_id=STREAM_ID,
            kind=StreamKind.PUBLIC_REGISTER,
            temporality=StreamTemporality.REGISTRAR_ACCEPTANCE,
            axes=(
                AxisBinding(
                    axis=TimeAxis.FETCHED_AT,
                    supplied=False,
                    reason=_NO_FETCH_TIME,
                ),
                AxisBinding(
                    axis=TimeAxis.OBSERVED_AT,
                    supplied=False,
                    reason=_NO_OBSERVATION,
                ),
                AxisBinding(
                    axis=TimeAxis.PUBLISHED_AT,
                    supplied=True,
                    source_field=PUBLISHED_AT_FIELD,
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

        Returns ``None`` for a row missing a document path or a content digest.
        The digest is the load-bearing case and the reason is in this module's
        docstring: an index row does not name bytes, and a capture that cannot
        name its own bytes cannot be deduplicated, verified or replayed — so the
        caller supplies the digest of what was actually retrieved, or the row
        produces nothing.
        """
        if not isinstance(record, Mapping):
            return None
        document_path = str(record.get("document_path", "")).strip().lstrip("/")
        digest = str(record.get("content_digest", "")).strip()
        if not document_path or not digest:
            return None
        length = self._as_length(record.get("content_length"))
        return Capture(
            tenant_id=context.tenant_id,
            source_id=self.source_id,
            source_family=SOURCE_FAMILY,
            target_uri=ARCHIVE_ROOT + document_path,
            locator=self._locator(document_path, record),
            content_digest=digest,
            content_length=length,
            media_type=str(record.get("media_type", "") or "").strip(),
            fetched_at=None,
            time_basis=CaptureTimeBasis.PUBLICATION,
            transport="sec-edgar-archive-read",
            ingest_batch_id=context.ingest_batch_id,
            ingest_attempt=context.ingest_attempt,
            recorded_by=context.recorded_by,
        )

    def _locator(self, document_path: str, record: Mapping[str, object]) -> str:
        """Which index line led here, addressed the way a WARC offset addresses a page.

        The EDGAR analogue of ``warc-file@offset,length``: the index file is the
        container and the submission row is the record inside it. ``target_uri``
        already names the document, so the locator's whole job is to say *which
        index file* named it — the byte-exact position this copy of the record came
        from, which is what makes two index releases of one filing two captures of
        one payload rather than one capture.
        """
        return f"{self.index_uri}#{document_path}"

    @staticmethod
    def _as_length(value: object) -> int | None:
        """A reported length, or ``None`` when the row does not report one.

        An unparseable or negative length is absence rather than zero, because a
        zero here would claim the document is empty and the whole point of reading
        the archive is to find out what is in it.
        """
        if value is None or str(value).strip() == "":
            return None
        try:
            length = int(str(value).strip())
        except (TypeError, ValueError):
            return None
        return length if length > 0 else None


__all__ = [
    "ADAPTER_REF",
    "ARCHIVE_ROOT",
    "OPTIONAL_RAW_FIELDS",
    "PUBLISHED_AT_FIELD",
    "REQUIRED_RAW_FIELDS",
    "SOURCE_FAMILY",
    "STREAM_ID",
    "EdgarFullIndexAdapter",
    "iso_utc_from_filed_date",
]
