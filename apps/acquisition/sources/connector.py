"""Turn a source definition into scheduled tasks and, when executed, into observations.

The seam is deliberately narrow. A source is a configuration; this module is the only place
that knows how to turn one into work, and it emits events and nothing else. It does not
decide what a mention is, whether a relation holds, or what an entity is — those belong to
the interpretation stages that consume what it publishes.

The donor collapsed this into one pass: fetch the last page, parse it, infer relations, and
write a graph edge. Split here, so each stage is independently replayable, independently
versioned, and independently droppable. A source produces an ``observation.created`` per
page; what any downstream stage makes of that page is a separate decision it may make
differently tomorrow without re-fetching anything.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from sources.catalogue import SourceDefinition, load_catalogue
from sources.executor import AcquisitionError, CapturePage, HttpSourceExecutor, page_count

OBSERVATION_PREFIX = "OBS-"
DEFAULT_CATEGORY = "unknown"


def observation_id(source_id: str, query: str, page: int, content_digest: str) -> str:
    """Content-addressed observation id.

    Includes the resolved query and the content digest, so two queries to one source can
    never collide, and a page whose bytes changed is a different observation rather than an
    overwrite. This is the defect that made a cached response for one query serve as an
    answer to another.
    """
    from domain.relation_identity import digest128

    material = "|".join([source_id, query, str(page), content_digest])
    return OBSERVATION_PREFIX + digest128(material)


@dataclass(frozen=True)
class AcquisitionTask:
    """The unit of work. A plain mapping, because the scheduler already accepts one."""

    task_id: str
    source_id: str
    source_name: str
    query: str
    category: str
    tenant_id: str = "default-tenant"
    investigation_id: str = ""
    #: The runtime that executes this task, or "" for the HTTP/system path. Carried on the
    #: task because ``adapters.registry.resolve_task`` branches on exactly this key: with it
    #: absent from ``to_task`` the explicit-runtime branch was unreachable and every task
    #: fell through to capability selection, which routes a connector-shaped source to the
    #: HTTP executor that refuses it.
    runtime_ref: str = ""
    #: The bound registry refs and constraints a query compiler produced for this task.
    #: Free-form because the compiler's shape is the science layer's, and acquisition must
    #: not import it -- but carried, so the constraint reaches the runtime instead of being
    #: dropped between planning and execution.
    query_ref: str = ""
    constraints: tuple[Mapping[str, Any], ...] = ()

    def to_task(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "query": self.query,
            "category": self.category,
            "tenant_id": self.tenant_id,
            "investigation_id": self.investigation_id,
            "runtime_ref": self.runtime_ref,
            "query_ref": self.query_ref,
            "constraints": [dict(item) for item in self.constraints],
        }


def tasks_for(
    definition: SourceDefinition,
    query: str,
    *,
    tenant_id: str = "default-tenant",
    investigation_id: str = "",
) -> AcquisitionTask:
    """One task per (source, query). Pagination is the worker's concern, not the task's —
    a task says *what to collect*, and the definition says how many pages that is."""
    from domain.relation_identity import digest128

    task_id = "TSK-" + digest128(f"{definition.source_id}|{query}|{tenant_id}")
    return AcquisitionTask(
        task_id=task_id,
        source_id=definition.source_id,
        source_name=definition.name,
        query=query,
        category=definition.category or DEFAULT_CATEGORY,
        tenant_id=tenant_id,
        investigation_id=investigation_id,
        # Carried from the definition so a runtime-backed source reaches the runtime that
        # can actually run it, instead of the HTTP executor that refuses it.
        runtime_ref=definition.runtime_ref,
    )


def plan(
    query: str,
    *,
    tenant_id: str = "default-tenant",
    investigation_id: str = "",
    only_keyless: bool = True,
    categories: Iterable[str] | None = None,
) -> tuple[AcquisitionTask, ...]:
    """Every runnable source becomes a task. Deterministic order, so a plan replays."""
    definitions, _ = load_catalogue()
    wanted = set(categories) if categories else None
    out: list[AcquisitionTask] = []
    for definition in definitions:
        if not definition.enabled:
            continue
        if only_keyless and definition.requires_key:
            continue
        if wanted is not None and definition.category not in wanted:
            continue
        out.append(
            tasks_for(
                definition, query, tenant_id=tenant_id, investigation_id=investigation_id
            )
        )
    out.sort(key=lambda t: t.task_id)
    return tuple(out)


class SourceConnector:
    """Execute a definition, one observation per page.

    The connector emits observations and stops. It never emits a mention, a candidate, a
    claim or an edge, and it holds no graph.

    **WP-C T041: the connector now writes its evidence before it claims it.**

    It previously built the ``observation.created`` event inline, carrying a
    ``content_digest`` and no ``raw_ref``, and never touched an object store. Every
    consumer of that event was unable to resolve it to bytes: the platform recorded
    that something had been observed when it had only been claimed. With a ``gate``
    injected, each page is ingested through the single observation gate and the event
    returned is the gate's — which carries the raw reference the bytes were stored
    under.

    The gate is optional so this module stays importable and testable with no store and
    no science layer. Without it the connector behaves exactly as it did, *including*
    the defect, and :func:`events.evidence_store_guard.require_stored_evidence` will
    refuse the result at publication. That is deliberate: a deployment that forgets to
    wire the gate fails loudly instead of publishing unresolvable evidence.
    """

    def __init__(
        self,
        executor: HttpSourceExecutor | None = None,
        *,
        gate: Any | None = None,
        artifact_sink_factory: Callable[[SourceDefinition], Any] | None = None,
    ) -> None:
        self.executor = executor or HttpSourceExecutor()
        self.gate = gate
        # Production can route each source through ArtifactSink without teaching this
        # transport layer how a particular storage backend or identity provider works.
        # The factory receives the validated, declarative source definition so the
        # capture's independence family and time basis are never inferred from its URL.
        self.artifact_sink_factory = artifact_sink_factory

    def definition_for(self, source_id: str) -> SourceDefinition | None:
        definitions, _ = load_catalogue()
        for definition in definitions:
            if definition.source_id == source_id:
                return definition
        return None

    async def collect(
        self, task: AcquisitionTask
    ) -> AsyncIterator[tuple[CapturePage, dict[str, Any]]]:
        """Yield ``(capture, event)`` per page, in order."""
        definition = self.definition_for(task.source_id)
        if definition is None:
            raise AcquisitionError("unknown_source", f"no definition for {task.source_id}")
        ceiling = page_count(definition.pagination)
        async for capture in self.executor.capture(definition, task.query):
            event = await self._event_for(task, definition, capture, ceiling)
            yield capture, event

    async def _event_for(
        self,
        task: AcquisitionTask,
        definition: SourceDefinition,
        capture: CapturePage,
        ceiling: int,
    ) -> dict[str, Any]:
        """The published event for one page, from the gate when one is wired.

        The descriptive fields the connector has always supplied — page, ceiling,
        query, parser, entity hints — are *merged onto* the gate's event rather than
        replacing it. They describe the retrieval, not the evidence, and the gate
        knows nothing about them. The merge keeps the gate's identity and raw
        reference authoritative and treats everything the connector contributes as
        annotation, which is what it is.
        """
        enrichment = {
            "task_id": task.task_id,
            "investigation_id": task.investigation_id,
            "source_name": capture.source_name,
            "category": definition.category,
            "query": capture.query,
            "page": capture.page,
            "page_count": ceiling,
            "url": capture.url,
            "status": capture.status,
            "content_type": capture.content_type,
            "byte_length": capture.byte_length,
            "retrieved_at": capture.retrieved_at,
            "elapsed_s": round(capture.elapsed_s, 6),
            "truncated": capture.truncated,
            "parser": definition.parser,
            "parser_is_identity": definition.parser_is_identity,
            "applies_to": list(definition.applies_to),
            "entity_hints": list(definition.entity_hints),
            "contact": definition.contact,
        }

        if self.artifact_sink_factory is not None:
            # The one production path: immutable raw object first, then a first-class
            # Capture, then an Observation through the gate. The gate owns event identity
            # and broker publication; the worker must not build a second event.
            from datetime import UTC, datetime
            from domain.acquisition_artifact import AcquisitionArtifact
            from domain.capture import CaptureTimeBasis

            if not definition.source_family or not definition.time_basis:
                raise AcquisitionError(
                    "source_capture_provenance_missing",
                    f"{definition.name} must declare source_family and time_basis before "
                    "it can enter the raw-first ArtifactSink path",
                )
            try:
                time_basis = CaptureTimeBasis(definition.time_basis)
            except ValueError as exc:
                raise AcquisitionError(
                    "source_time_basis_invalid",
                    f"{definition.name} declares unknown time_basis {definition.time_basis!r}",
                ) from exc
            if self.gate is None:
                raise AcquisitionError(
                    "observation_gate_unavailable",
                    "ArtifactSink requires the canonical ObservationGate",
                )
            sink = self.artifact_sink_factory(definition)
            artifact = AcquisitionArtifact(
                task_id=task.task_id,
                source_id=task.source_id,
                worker_ref="worker-http",
                target_uri=capture.url,
                locator="blob",
                capture_locator="blob",
                body=capture.body,
                content_type=capture.content_type or "application/octet-stream",
                fetched_at=datetime.fromtimestamp(capture.retrieved_at, tz=UTC),
                transport="http",
                producer="source-connector",
                producer_version="0.1.0",
                metadata={
                    "parser_hint": definition.parser,
                    "parser_is_identity": definition.parser_is_identity,
                    "source_name": definition.name,
                    "query": capture.query,
                    "page": capture.page,
                    "page_count": ceiling,
                    "status": capture.status,
                    "truncated": capture.truncated,
                    "elapsed_s": round(capture.elapsed_s, 6),
                    "redirected_from": list(capture.redirected_from),
                    "entity_hints": list(definition.entity_hints),
                    "applies_to": list(definition.applies_to),
                },
            )
            accepted = await sink.accept(
                artifact,
                tenant_id=task.tenant_id,
                investigation_id=task.investigation_id or None,
                work_id=task.task_id,
                time_basis=time_basis,
            )
            return {
                "event_type": "observation.created",
                "event_version": "2.0",
                "event_id": accepted.event_id or "",
                "observation_id": accepted.observation_id,
                "tenant_id": task.tenant_id,
                "source_id": capture.source_id,
                "task_id": task.task_id,
                "investigation_id": task.investigation_id,
                "content_digest": accepted.content_digest,
                "raw_ref": accepted.raw_ref,
                "capture_id": accepted.capture_id,
                "locator": accepted.locator,
                "lifecycle": "created",
                "artifact_sink_accepted": True,
                **enrichment,
            }

        if self.gate is None:
            # No gate: the pre-WP-C shape, preserved so the module stays usable
            # without a store. Publication is refused downstream by
            # ``require_stored_evidence`` because there is no ``raw_ref``.
            return {
                "event_type": "observation.created",
                "event_version": "1.0",
                "event_id": observation_id(
                    task.source_id, task.query, capture.page, capture.content_digest
                ),
                "tenant_id": task.tenant_id,
                "source_id": capture.source_id,
                "content_digest": capture.content_digest,
                **enrichment,
            }

        ingested = await self.gate.ingest(
            body=capture.body,
            uri=capture.url,
            tenant_id=task.tenant_id,
            investigation_id=task.investigation_id,
            source_id=capture.source_id,
            content_type=capture.content_type,
            collector="source-connector",
        )
        return {
            "event_type": "observation.created",
            "event_version": "2.0",
            "event_id": str(ingested.get("observation_id", "") or ""),
            "observation_id": str(ingested.get("observation_id", "") or ""),
            "tenant_id": task.tenant_id,
            "source_id": capture.source_id,
            "content_digest": capture.content_digest,
            "raw_ref": str(ingested.get("raw_ref", "") or ""),
            "lifecycle": str(ingested.get("status", "") or ""),
            **enrichment,
        }

    async def aclose(self) -> None:
        await self.executor.aclose()
