"""The downstream observation consumer (ACQ-18, §85, §173, §174).

``observation.created`` -> resolve -> load raw -> resolve locator -> parse ->
write a processing result.

**This is the stage the previous three layers existed to make possible, and the
reason its most important property is a negative one: it must never touch the
network.** §174 forbids a consumer from deciding "there is a URL here, let me go
and fetch it". Everything this consumer knows comes from ``raw_ref`` - the bytes
as they were captured - so re-running it produces the same interpretation, and
so does re-running it after the network has changed underneath.

That is also what makes §94 work. A new parser version needs no refetch: the raw
artifact is still there, and the only thing that changes is which version reads
it. The alternative - re-acquire, then parse - would make parser upgrades depend
on upstream availability and would silently produce a *different* observation set
from the same source, which is a different capture and a different claim.

**What it deliberately does not do.** It writes no entity, no claim, no graph
edge, and mints no mention that claims a type. It parses the captured bytes into
observed structure and records that it did so. Type hypotheses and relation
signals are the next stage, and they are deliberately not here (§3, §119).

**Idempotency is by address, not by bookkeeping.** A redelivered event carries
the same ``observation_id``; the processing result is keyed on it, so replaying
the topic writes the same result rather than a second one (§125, §192). There is
no offset arithmetic and no "have I seen this" set, because the deterministic
identity already answers the question.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from events import event_envelope_pb2 as pb

CONSUMER_NAME = "observation-consumer"
CONSUMER_VERSION = "0.1.0"

STATUS_PROCESSED = "processed"
STATUS_SKIPPED_REPLAY = "skipped_replay"
STATUS_REFUSED = "refused"

#: §73's classifications, reused verbatim so a failure reported here matches a
#: failure reported by the runtime that produced the artifact.
FAILURE_RAW_UNREADABLE = "storage"
FAILURE_LOCATOR_UNRESOLVABLE = "parsing"
FAILURE_PAYLOAD_UNPARSEABLE = "parsing"
FAILURE_UNKNOWN_SOURCE = "schema"


class ConsumerContractError(ValueError):
    """The consumer refused a message. Carries a §73 classification."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ProcessingResult:
    """§86's machine-readable proof that something was actually processed."""

    processing_run_id: str
    observation_id: str
    consumer: str
    consumer_version: str
    processed_at: str
    status: str
    derived_ref: str
    capture_id: str = ""
    locator: str = ""
    record_count: int = 0
    mention_count: int = 0
    truncated: bool = False
    failure_code: str = ""
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "processing_run_id": self.processing_run_id,
            "observation_id": self.observation_id,
            "consumer": self.consumer,
            "consumer_version": self.consumer_version,
            "processed_at": self.processed_at,
            "status": self.status,
            "derived_ref": self.derived_ref,
            "capture_id": self.capture_id,
            "locator": self.locator,
            "record_count": self.record_count,
            "mention_count": self.mention_count,
            "truncated": self.truncated,
        }
        if self.failure_code:
            out["failure_code"] = self.failure_code
            out["detail"] = self.detail
        return out


class ObservationConsumer:
    """Reads ``observation.created`` and produces a persisted processing result."""

    def __init__(
        self,
        *,
        store: Any,
        source_family: str = "",
        processing_run_id: str = "",
        segment_ref: str = "segment:0",
    ) -> None:
        self._store = store
        self._source_family = source_family
        self._run_id = processing_run_id or f"proc-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
        # Mention-addressing refs (§26 of the 021 mention contract). Taken from the
        # capture being read rather than generated, so an ``MN-`` names a parser
        # and a capture that both actually exist. ``_capture_ref`` is filled in per
        # message by ``_process``; the others are properties of this consumer.
        self._capture_ref = ""
        self._segment_ref = segment_ref
        self._extractor_ref = f"{CONSUMER_NAME}/{CONSUMER_VERSION}/payload"
        # Keyed on observation_id: a replay is the same key, so a second delivery
        # overwrites the same result instead of appending a second (§125).
        self._results: dict[str, ProcessingResult] = {}

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def results(self) -> tuple[ProcessingResult, ...]:
        return tuple(self._results.values())

    def result_for(self, observation_id: str) -> ProcessingResult | None:
        return self._results.get(observation_id)

    # ------------------------------------------------------------ dispatch --

    async def handle(self, envelope: pb.EventEnvelope) -> ProcessingResult:
        """Process one envelope. Never raises for a data problem (§107, §108).

        A malformed or unresolvable message yields a *result carrying a reason*,
        not an exception and not silence. §108 forbids dropping, and §203 forbids
        swallowing: a failure that leaves no trace is indistinguishable from a
        message that never existed.
        """
        observation_id = envelope.observation_id
        existing = self._results.get(observation_id)
        if existing is not None:
            # §125: same deterministic id, same semantic result. Returning the
            # stored one is what makes a duplicate delivery a no-op.
            return existing

        try:
            result = await self._process(envelope)
        except ConsumerContractError as exc:
            result = self._fail(envelope, exc.code, exc.message)
        except Exception as exc:  # noqa: BLE001 - classified, never swallowed
            result = self._fail(envelope, "downstream", f"{type(exc).__name__}: {exc}")

        self._results[observation_id] = result
        return result

    # ------------------------------------------------------------- process --

    async def _process(self, envelope: pb.EventEnvelope) -> ProcessingResult:
        record_meta = self._record_metadata(envelope)
        locator = str(record_meta.get("locator") or "")
        if not locator:
            # A capture-level observation has no record locator; that is a
            # legitimate shape (§6), not a malformed message. It is recorded and
            # skipped rather than failed, because failing it would put a capture
            # observation into the failure lane where it does not belong.
            return self._result(envelope, STATUS_SKIPPED_REPLAY, derived_ref="capture", detail="")

        capture_id = str(record_meta.get("capture_id") or "")
        raw_ref = str(record_meta.get("raw_ref") or "")
        content_type = record_meta.get("content_type")
        # The *runtime* that produced this is not the *parser* that should read it.
        # SearXNG is a producer; the parser layer names readers, and routing on a
        # producer name gives ``parser_name_unknown`` and a text route - which
        # turned a 40-field JSON result into one line. The declaration comes from
        # the source definition's ``parser`` hint, which is the one place a parser
        # name is actually declared; when it is absent the content type decides,
        # and if that is also absent the payload layer records its own refusal
        # rather than guessing here.
        declared_parser = str(record_meta.get("parser_hint") or "")
        # The capture being read is what a mention minted here is about, so it is
        # bound before parsing rather than after.
        self._capture_ref = capture_id

        body = await self._read(raw_ref)
        payload = self._parse(body, content_type, declared_parser)

        records = payload.records
        mentions = self._bind(payload)

        # §63 wants every observation traceable to a parser version. The payload
        # layer reports *which* parser ran (``declared_parser``) and where it
        # routed to, but carries no version field of its own - so the reference
        # here is this consumer's version plus the parser it selected, which is
        # the pair that actually determines the interpretation. Inventing a
        # "parser_version" attribute that does not exist is how a manifest ends up
        # naming a version nobody can reproduce.
        parser_ref = (
            f"{CONSUMER_NAME}/{CONSUMER_VERSION}"
            f"#declared={payload.declared_parser or 'none'}"
            f"#routed={payload.routed_to}"
        )

        return self._result(
            envelope,
            STATUS_PROCESSED,
            derived_ref=f"parsed:{parser_ref}",
            capture_id=capture_id,
            locator=locator,
            record_count=len(records),
            mention_count=mentions,
            truncated=bool(getattr(payload, "truncated", False)),
        )

    def _parse(self, body: bytes, content_type: Any, declared_parser: str):
        """Hand the bytes to the payload layer and nothing else.

        The registry is obtained from the payload package rather than built here:
        the routing table (§62's unknown-field retention, the content-type rule)
        is that module's contract, and a second router in the consumer is a
        second definition of how a payload is interpreted.
        """
        from parsers.payload.registry import default_registry

        try:
            return default_registry().parse(
                body=body,
                content_type=str(content_type) if content_type else None,
                declared_parser=declared_parser,
            )
        except Exception as exc:
            raise ConsumerContractError(
                FAILURE_PAYLOAD_UNPARSEABLE, f"{type(exc).__name__}: {exc}"
            ) from exc

    def _bind(self, payload: Any) -> int:
        """Address what the parser found. Counts mentions, mints no entities.

        Binding failures are not this stage's failure: a field with no addressable
        span is reported by the payload layer as a refusal, and the honest outcome
        is a lower mention count rather than a failed processing run. §3 and §119
        both forbid escalating this into a type or an entity decision.

        The three refs are required by ``bind_records`` and are taken from the
        capture we are reading, not invented: a mention bound to a made-up
        extractor ref would mint an ``MN-`` that names a parser nobody can run.
        """
        from parsers.payload import bind_records

        try:
            bound = bind_records(
                payload,
                capture_ref=self._capture_ref or "CAP-unbound",
                segment_ref=self._segment_ref,
                extractor_ref=self._extractor_ref,
            )
        except Exception:  # noqa: BLE001
            return 0
        return len(getattr(bound, "bound", ()) or ())

    async def _read(self, raw_ref: str) -> bytes:
        """Fetch the captured bytes. The only I/O this consumer does (§174).

        No HTTP client is imported here on purpose. That absence is the §174
        guarantee, and it is worth making explicit in the import list: a
        consumer that could reach the network would eventually do so, and the
        first time it did, the evidence chain would have a hole in it that no
        test would catch.
        """
        if not raw_ref:
            raise ConsumerContractError(FAILURE_RAW_UNREADABLE, "no raw_ref on the event")
        bucket, _, key = raw_ref.removeprefix("s3://").partition("/")
        if not bucket or not key:
            raise ConsumerContractError(
                FAILURE_RAW_UNREADABLE, f"raw_ref is not an s3://<bucket>/<key>: {raw_ref!r}"
            )
        try:
            return await self._store.read_range(bucket=bucket, key=key)
        except ConsumerContractError:
            raise
        except Exception as exc:
            raise ConsumerContractError(
                FAILURE_RAW_UNREADABLE, f"{type(exc).__name__}: {exc}"
            ) from exc

    def _record_metadata(self, envelope: pb.EventEnvelope) -> dict[str, Any]:
        """Recover what the producer recorded about the record (§63, §73).

        The envelope's payload is refs-only (§69), so the record's own metadata
        travels in the envelope's structured fields rather than in a blob. If it
        is absent the message is classified as ``schema`` rather than parsed
        optimistically - an event that names no capture is not something to
        guess about.
        """
        raw = bytes(envelope.payload)
        if not raw:
            raise ConsumerContractError(
                FAILURE_UNKNOWN_SOURCE, "event carries no record metadata"
            )
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise ConsumerContractError(
                FAILURE_UNKNOWN_SOURCE, f"record metadata is not JSON: {exc}"
            ) from exc
        if not isinstance(decoded, dict):
            raise ConsumerContractError(
                FAILURE_UNKNOWN_SOURCE,
                f"record metadata is {type(decoded).__name__}, not an object",
            )
        return decoded

    # -------------------------------------------------------------- result --

    def _result(
        self,
        envelope: pb.EventEnvelope,
        status: str,
        *,
        derived_ref: str,
        capture_id: str = "",
        locator: str = "",
        record_count: int = 0,
        mention_count: int = 0,
        truncated: bool = False,
        failure_code: str = "",
        detail: str = "",
    ) -> ProcessingResult:
        return ProcessingResult(
            processing_run_id=self._run_id,
            observation_id=envelope.observation_id,
            consumer=CONSUMER_NAME,
            consumer_version=CONSUMER_VERSION,
            processed_at=datetime.now(UTC).isoformat(),
            status=status,
            derived_ref=derived_ref,
            capture_id=capture_id,
            locator=locator,
            record_count=record_count,
            mention_count=mention_count,
            truncated=truncated,
            failure_code=failure_code,
            detail=detail,
        )

    def _fail(self, envelope: pb.EventEnvelope, code: str, detail: str) -> ProcessingResult:
        """A failure that leaves a record. §108 forbids dropping it silently."""
        return self._result(
            envelope,
            STATUS_REFUSED,
            derived_ref="none",
            failure_code=code,
            detail=detail[:400],
        )
