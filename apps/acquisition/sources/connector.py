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

from collections.abc import AsyncIterator, Iterable, Mapping
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
    """

    def __init__(self, executor: HttpSourceExecutor | None = None) -> None:
        self.executor = executor or HttpSourceExecutor()

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
            event = {
                "event_type": "observation.created",
                "event_version": "1.0",
                "event_id": observation_id(
                    task.source_id, task.query, capture.page, capture.content_digest
                ),
                "task_id": task.task_id,
                "tenant_id": task.tenant_id,
                "investigation_id": task.investigation_id,
                "source_id": capture.source_id,
                "source_name": capture.source_name,
                "category": definition.category,
                "query": capture.query,
                "page": capture.page,
                "page_count": ceiling,
                "url": capture.url,
                "status": capture.status,
                "content_type": capture.content_type,
                "content_digest": capture.content_digest,
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
            yield capture, event

    async def aclose(self) -> None:
        await self.executor.aclose()
