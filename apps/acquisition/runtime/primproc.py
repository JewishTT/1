"""``PrimProcRuntime``: a runtime decorator that supplements, never replaces.

**What this is.** A wrapper around any :class:`~runtime.AcquisitionWorker` that, for every artefact
whose media type is a cleaning route, emits a **second** artefact: the cleaned content, at its own
locator, with its own digest, derived from the first. The wrapped runtime's artefacts are
yielded first and unchanged. This is a decorator rather than a side path because a side path
would be a place
a caller could forget, and a cleaner that runs only when somebody remembered to call it is not a
stage.

**Why the original is still produced.** §61: the acquisition artefact's ``content_digest`` is the
digest of the bytes the source sent, and §94 asks for "reparse without HTTP". If the decorator
replaced the raw artefact with cleaned bytes, that digest would describe text the source never sent,
the original could not be re-fetched from the store, and re-parsing it under a different
:class:`~parsers.primproc.processor.PrimaryProcessor` version — §133's question — would be
impossible.
So the raw is **supplemented**, and both live in the store.

**§3, and it is worth being blunt about it.** This module mints no entity, no claim, no type and no
relation. It reads bytes and writes bytes. The only identifiers on the derived artefact are the ones
this module constructs for addressing (``primproc:<locator>``) and the ones it copies from the
original — and there is no field on the derived artefact for a semantic judgement, so a consumer
cannot read one out of it even by accident.

**Where the derived artefact's identities come from, and the honest gap.** The directive
asks for ``derived_from`` carrying the original ``observation_id`` and ``capture_id``. Those
two are minted by
:class:`~events.observation_gate.ObservationGate` and :class:`~domain.capture.Capture`,
**downstream** of every runtime, so a runtime decorator standing where this one stands cannot know
them. Three options, and this one takes the third:

1. Mint them here — forbidden, and for the reason :mod:`domain.acquisition_artifact` gives: a
   runtime that could address its own output would make the address a fact about the tool.
2. Leave them out — then the join between a cleaned artefact and the raw it came from is a string
   comparison a consumer has to guess at.
3. **Carry what is known and say what is not.**
   :attr:`~runtime.primproc.PrimProcRuntime.identity_resolver` is an optional callable a caller
   supplies when it *does* hold the sink's ids; with none supplied,
   :func:`~runtime.primproc.derived_from_of` records the fields a runtime genuinely knows —
   ``locator``, ``capture_locator``, ``content_digest``, ``target_uri``, ``task_id``,
   ``source_id``, ``producer``, ``producer_version`` — and leaves
   ``observation_id``/``capture_id`` as empty strings rather than as plausible-looking guesses.
   A consumer can always rebuild them:
   :meth:`~domain.acquisition_artifact.AcquisitionArtifact.observation_identity` is a pure function
   of ``(tenant_id, capture_id, locator, record_digest)``, and the digest is right there.

**The derived artefact is its own capture, deliberately.** ``capture_locator`` is left unset, so
:meth:`~domain.acquisition_artifact.AcquisitionArtifact.effective_capture_locator` returns the
derived locator. §20 says a capture is what physically came back, and cleaned text did not come back
— it was made here, from bytes that came back. Sharing the original's capture locator would put two
different digests under one capture identity and make the capture's ``content_digest`` describe
neither.

**No clock.** The derived artefact carries the **original's** ``fetched_at``. That is both the
honest value — the bytes were fetched then; deriving them now does not move when they were fetched —
and the one that keeps a clock off this path entirely. :class:`~datetime.datetime` is never read
here.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from domain.acquisition_artifact import AcquisitionArtifact

from runtime import RUNTIME_NOT_FOUND, RUNTIME_PROTOCOL_INVALID, CostEstimate, RuntimeError_

#: The locator scheme for a cleaned artefact (§10's per-family namespaces). The family's own name,
#: not a second builder of ``capture:`` — that prefix is reserved by
#: :mod:`domain.mention_occurrence_index` and a repository-wide invariant test scans production
#: source for a second builder of it.
PRIMPROC_LOCATOR_PREFIX: str = "primproc:"

#: This runtime's :data:`~runtime.AcquisitionWorker.runtime_ref`. Reported on the run manifest and
#: on every derived artefact's ``producer``, so a manifest says which stage made a cleaned artefact
#: without importing the code that made it.
PRIMPROC_RUNTIME_REF: str = "primproc"

#: The value on a derived artefact's ``transport``. The bytes were not transported; they were made
#: on this platform from bytes that were. The original transport is preserved under
#: :func:`derived_from_of`, so nothing is lost by saying this plainly.
DERIVED_TRANSPORT: str = "derived"

#: The ``parser_hint`` a cleaned artefact declares. Cleaned content is text and claims no
#: structure, so it declares ``raw_text`` — which :data:`sources.catalogue.IDENTITY_PARSERS`
#: treats as "the payload comes back unparsed", and which the payload registry routes to its text
#: extractor with the identity refusal attached. The original hint (``structured_fields`` for a JSON
#: result, say) describes the **raw** artefact and would be a false description of the cleaned one,
#: so it is preserved under ``derived_from`` rather than copied onto the derived record.
CLEANED_PARSER_HINT: str = "raw_text"

#: The metadata key under which the derivation record rides. Named so a consumer reading the sink's
#: ``record_metadata`` finds it by key rather than by knowing the shape of the record.
DERIVED_FROM_KEY: str = "derived_from"


@runtime_checkable
class PrimaryProcessorPort(Protocol):
    """The slice of the cleaning stage this decorator needs, declared rather than imported.

    **Why a port and not the class.** :mod:`runtime` sits above :mod:`parsers.primproc` in the layer
    graph, so the import is legal — but ``apps/acquisition`` does not declare
    ``cognitive-interpretation`` as a dependency, and adding one changes the workspace graph for the
    sake of a single call. Declaring the four members this module actually uses keeps the coupling
    visible and small, keeps this module importable without the sibling app on the path, and makes
    the decorator's own logic testable against a stand-in.

    :func:`primary_processor` is where the real import happens, and it refuses **by name** when the
    interpretation app is absent — which is the failure an operator needs to be able to read.
    """

    def process(
        self, body: bytes, *, content_type: str | None = None
    ) -> Any:  # -> PrimaryResult, named loosely so this module needs no import
        ...

    def is_cleaning_route(self, content_type: str | None) -> bool: ...

    @property
    def version(self) -> str: ...

    @property
    def schema(self) -> str: ...


def primary_processor(**kwargs: Any) -> PrimaryProcessorPort:
    """The real :class:`~parsers.primproc.PrimaryProcessor`, imported here or refused by name.

    Imported inside the function so that importing :mod:`runtime.primproc` never requires the
    interpretation app to be installed, and refused rather than degraded so that a deployment
    missing it gets a sentence naming the package instead of a ``NameError`` three frames later.
    """
    try:
        from parsers.primproc import PrimaryProcessor
    except ImportError as exc:  # pragma: no cover - a deployment without the sibling app
        raise RuntimeError_(
            RUNTIME_NOT_FOUND,
            "the primproc runtime needs apps/interpretation on the path "
            "(cognitive-interpretation): "
            f"{exc}",
        ) from exc
    return PrimaryProcessor(**kwargs)


@dataclass(frozen=True, slots=True)
class Derivation:
    """What the decorator knows about how a derived artefact came to exist.

    ``observation_id`` and ``capture_id`` are empty unless a caller supplied an
    :attr:`PrimProcRuntime.identity_resolver`; they are **not** reconstructed, because
    reconstructing them needs a ``tenant_id`` this layer does not have, and guessing an identity is
    worse than admitting one is not yet known.
    """

    locator: str
    capture_locator: str
    content_digest: str
    target_uri: str
    task_id: str
    source_id: str
    worker_ref: str
    producer: str
    producer_version: str
    content_type: str
    transport: str
    fetched_at: str
    parser_hint: str
    observation_id: str = ""
    capture_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "locator": self.locator,
            "capture_locator": self.capture_locator,
            "content_digest": self.content_digest,
            "target_uri": self.target_uri,
            "task_id": self.task_id,
            "source_id": self.source_id,
            "worker_ref": self.worker_ref,
            "producer": self.producer,
            "producer_version": self.producer_version,
            "content_type": self.content_type,
            "transport": self.transport,
            "fetched_at": self.fetched_at,
            "parser_hint": self.parser_hint,
            "observation_id": self.observation_id,
            "capture_id": self.capture_id,
        }


@dataclass(frozen=True, slots=True)
class PrimProcRefusal:
    """A cleaning refusal, counted rather than raised.

    A decode this stage refused means **no derived artefact**, and the original is still yielded. A
    bare exception here would kill a run over one mis-encoded page and take the raw bytes down with
    it, which is the §98 failure class in a new place. So the refusal is recorded on the runtime and
    the run manifest reports it.
    """

    locator: str
    code: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"locator": self.locator, "code": self.code, "detail": self.detail}


def derived_from_of(artifact: AcquisitionArtifact) -> dict[str, Any]:
    """The derivation record for one original artefact. Pure, and the single place it is built."""
    record = Derivation(
        locator=artifact.locator,
        capture_locator=artifact.effective_capture_locator(),
        content_digest=artifact.record_digest(),
        target_uri=artifact.target_uri,
        task_id=artifact.task_id,
        source_id=artifact.source_id,
        worker_ref=artifact.worker_ref,
        producer=artifact.producer,
        producer_version=artifact.producer_version,
        content_type=artifact.content_type or "",
        transport=artifact.transport,
        fetched_at=artifact.fetched_at.isoformat(),
        parser_hint=str(artifact.metadata.get("parser_hint", "") or ""),
    )
    return record.to_dict()


def cleaned_locator(artifact: AcquisitionArtifact) -> str:
    """``primproc:<original-locator>`` — §10's per-family scheme, applied to the artefact's own."""
    return f"{PRIMPROC_LOCATOR_PREFIX}{artifact.locator}"


class PrimProcRuntime:
    """Wraps an :class:`~runtime.AcquisitionWorker` and supplements its stream with cleaned content.

    **The contract, in order.** Every artefact the wrapped runtime yields is yielded first,
    unchanged. Then, if its media type is a cleaning route and its bytes decode, a second artefact
    is yielded at :func:`cleaned_locator`. Nothing the wrapped runtime produced is dropped,
    reordered ahead of, or altered — which is the whole reason this is a decorator and not a filter.

    **Streaming, not buffering** (§5, §36). The decorator yields the original the moment it arrives
    and processes the derived artefact immediately after, so a run over an unbounded source stays
    unbounded in the right way. Nothing is accumulated.

    **What a caller gets for its bookkeeping.** :attr:`derived` and :attr:`refusals` are appended as
    the run proceeds and are what a run manifest (§71) reports; :meth:`summary` returns both
    counts in one call so a manifest does not have to know the shape of either.
    """

    def __init__(
        self,
        inner: Any,
        *,
        processor: PrimaryProcessorPort | None = None,
        identity_resolver: Callable[[AcquisitionArtifact], Mapping[str, str]] | None = None,
    ) -> None:
        if not hasattr(inner, "acquire"):
            raise RuntimeError_(
                RUNTIME_PROTOCOL_INVALID,
                f"{type(inner).__name__} has no acquire(); PrimProcRuntime decorates an "
                "AcquisitionWorker and cannot stand in for one",
            )
        self._inner = inner
        self._processor = processor if processor is not None else primary_processor()
        self._identity_resolver = identity_resolver
        self._derived: list[AcquisitionArtifact] = []
        self._refusals: list[PrimProcRefusal] = []

    # -- introspection ------------------------------------------------------ #

    @property
    def runtime_ref(self) -> str:
        """This decorator's own ref.

        The wrapped runtime's ref is kept under :attr:`inner_runtime_ref` and on every derivation
        record, so a manifest can report both without either being lost. One value in this field is
        deliberate: §13 wants a resolved ``runtime_ref`` and a chain of them is not a resolution.
        """
        return PRIMPROC_RUNTIME_REF

    @property
    def execution_class(self) -> str:
        """Derived from the wrapped runtime's class rather than invented.

        A decorator that claimed a class of its own would be asserting something about the
        deployment that only the wrapped runtime knows, and the wrapped runtime's class is the fact.
        """
        return str(getattr(self._inner, "execution_class", ""))

    @property
    def inner_runtime_ref(self) -> str:
        """The wrapped runtime's :data:`~runtime.AcquisitionWorker.runtime_ref`."""
        return str(getattr(self._inner, "runtime_ref", ""))

    @property
    def derived(self) -> tuple[AcquisitionArtifact, ...]:
        return tuple(self._derived)

    @property
    def refusals(self) -> tuple[PrimProcRefusal, ...]:
        return tuple(self._refusals)

    def summary(self) -> dict[str, Any]:
        """Derived-artefact and refusal counts, plus the stage's own version — one manifest read."""
        return {
            "runtime_ref": self.runtime_ref,
            "inner_runtime_ref": self.inner_runtime_ref,
            "primproc_version": self._processor.version,
            "primproc_schema": self._processor.schema,
            "derived": len(self._derived),
            "refusals": [refusal.to_dict() for refusal in self._refusals],
        }

    def capabilities(self) -> list[str]:
        """The wrapped runtime's capabilities plus this decorator's marker.

        Checked against a runtime that has already been resolved by name, never used to choose one
        (§57). The marker is appended rather than replacing anything, because the decorator does
        everything the wrapped runtime does and one thing more.
        """
        inner = self._inner.capabilities() if hasattr(self._inner, "capabilities") else []
        return [*inner, "content-primary-processing"]

    def estimate(self, task: dict[str, Any]) -> CostEstimate:
        """The wrapped runtime's estimate, **doubled** — and stated as an upper bound.

        Every artefact yields at most one derived artefact, and a derived artefact is never larger
        than the artefact it came from, so twice the inner figures is a true upper bound on both. It
        is deliberately not a tighter estimate: a scheduler that budgets on the upper bound is never
        surprised, and a tighter one would have to know the content types before the run starts.
        """
        inner = self._inner.estimate(task)
        return CostEstimate(
            expected_artifacts=inner.expected_artifacts * 2,
            expected_bytes=inner.expected_bytes * 2,
            expected_seconds=inner.expected_seconds,
        )

    async def aclose(self) -> None:
        closer = getattr(self._inner, "aclose", None)
        if closer is not None:
            await closer()

    # -- the run ------------------------------------------------------------ #

    async def acquire(self, task: dict[str, Any]) -> AsyncIterator[AcquisitionArtifact]:
        """Yield every original artefact, and after each one its cleaned supplement.

        The order is the contract: **the original first**, so a sink has accepted the raw bytes and
        minted its addresses before the artefact that names them appears. A consumer reading the
        stream in order therefore never sees a derivation whose parent it has not already been told
        about.
        """
        async for artifact in self._inner.acquire(task):
            yield artifact
            for derived in self._derive(artifact):
                yield derived

    def _derive(self, artifact: AcquisitionArtifact) -> tuple[AcquisitionArtifact, ...]:
        """One artefact in, zero or one out. Total: a refusal yields nothing and is recorded."""
        if not isinstance(artifact, AcquisitionArtifact):
            raise RuntimeError_(
                RUNTIME_PROTOCOL_INVALID,
                f"{type(artifact).__name__} is not an AcquisitionArtifact",
            )
        if not self._processor.is_cleaning_route(artifact.content_type):
            return ()
        try:
            result = self._processor.process(artifact.body, content_type=artifact.content_type)
        except Exception as exc:  # noqa: BLE001 - reported as a refusal, never fatal to the run
            self._refusals.append(
                PrimProcRefusal(
                    locator=artifact.locator,
                    code="primproc_raised",
                    detail=f"{type(exc).__name__}: {exc}",
                )
            )
            return ()
        decode = getattr(result, "decode", None)
        if not getattr(result, "ok", False):
            self._refusals.append(
                PrimProcRefusal(
                    locator=artifact.locator,
                    code=str(getattr(decode, "refusal", "") or "primproc_refused"),
                    detail=str(getattr(decode, "refusal_detail", "") or ""),
                )
            )
            return ()
        derived = self._build(artifact, result)
        self._derived.append(derived)
        return (derived,)

    def _build(self, artifact: AcquisitionArtifact, result: Any) -> AcquisitionArtifact:
        """Assemble the derived artefact.

        Every field is either copied from the original or constructed here; none is guessed. The
        two that needed a decision — ``content_type`` and ``fetched_at`` — are argued in this
        module's docstring and on the fields below.
        """
        provenance = derived_from_of(artifact)
        if self._identity_resolver is not None:
            resolved = self._identity_resolver(artifact)
            provenance["observation_id"] = str(resolved.get("observation_id", "") or "")
            provenance["capture_id"] = str(resolved.get("capture_id", "") or "")
        removals = getattr(result, "removed_bytes_by_reason", {}) or {}
        metadata: dict[str, Any] = {
            DERIVED_FROM_KEY: provenance,
            "primproc_version": str(getattr(result, "version", self._processor.version)),
            "primproc_schema": str(getattr(result, "schema", self._processor.schema)),
            "rule": str(getattr(result, "strategy", "")),
            "decode_rule": str(getattr(getattr(result, "decode", None), "rule", "")),
            "decode_charset": str(getattr(getattr(result, "decode", None), "charset", "")),
            "content_route": str(getattr(result, "route", "")),
            "removed_bytes_by_reason": {str(key): int(value) for key, value in removals.items()},
            "removed_bytes_total": int(getattr(result, "removed_bytes_total", 0)),
            "source_bytes_kept": int(getattr(result, "source_bytes_kept", 0)),
            "entity_expansion_bytes": int(getattr(result, "entity_expansion_bytes", 0)),
            "entities_unescaped": bool(getattr(result, "unescaped", False)),
            "notes": [str(code) for code in getattr(result, "note_codes", ())],
            "line_count": len(getattr(result, "lines", ())),
            "parser_hint": CLEANED_PARSER_HINT,
        }
        return AcquisitionArtifact(
            task_id=artifact.task_id,
            source_id=artifact.source_id,
            worker_ref=artifact.worker_ref,
            target_uri=artifact.target_uri,
            locator=cleaned_locator(artifact),
            body=result.artifact_body(),
            # The cleaned artefact's content type is what it now **is**, not what it came from:
            # UTF-8 text. Declaring ``text/html`` would send a consumer's parser back through markup
            # parsing on bytes that no longer contain markup.
            content_type="text/plain; charset=utf-8",
            # The original's fetch time, deliberately. Deriving text now does not move when the
            # bytes were fetched, and this keeps a clock off the path entirely.
            fetched_at=artifact.fetched_at,
            transport=DERIVED_TRANSPORT,
            producer=self.runtime_ref,
            producer_version=str(getattr(result, "version", self._processor.version)),
            metadata=metadata,
            # capture_locator deliberately unset: the cleaned bytes are a new capture (§20), not a
            # record inside the original one. See this module's docstring.
            capture_locator=None,
            schema=f"{self._processor.schema}+{self._processor.version}",
        )


__all__ = [
    "CLEANED_PARSER_HINT",
    "DERIVED_FROM_KEY",
    "DERIVED_TRANSPORT",
    "PRIMPROC_LOCATOR_PREFIX",
    "PRIMPROC_RUNTIME_REF",
    "Derivation",
    "PrimProcRefusal",
    "PrimProcRuntime",
    "PrimaryProcessorPort",
    "cleaned_locator",
    "derived_from_of",
    "primary_processor",
]
