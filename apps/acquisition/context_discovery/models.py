"""Typed contracts for context-driven, public-source discovery planning.

Plans contain query intents, not evidence. Search results remain DISCOVERY_ONLY until
fetched through the canonical Capture/Observation path and reviewed by the platform.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any


_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
_SECRET = re.compile(
    r"(?i)(?:bearer\s+[A-Za-z0-9._~-]{12,}|(?:api[_-]?key|password|passwd|secret|access[_-]?token)\s*[:=]\s*\S+)"
)
_DOMAIN = re.compile(
    r"(?=.{1,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[A-Za-z]{2,63}"
)
_PHONE = re.compile(r"(?<!\w)\+?\d[\d().\s-]{7,}\d(?!\w)")


class EvidenceFacet(StrEnum):
    """Public evidence categories a research plan may seek."""

    IDENTITY = "identity"
    AFFILIATIONS = "affiliations"
    OFFICIAL_RECORDS = "official_records"
    PUBLIC_STATEMENTS = "public_statements"
    PUBLICATIONS = "publications"
    HISTORICAL_WEB = "historical_web"
    TECHNICAL_INFRASTRUCTURE = "technical_infrastructure"
    PUBLIC_INCIDENTS = "public_incidents"
    RELATIONSHIPS = "relationships"


DEFAULT_FACETS: tuple[EvidenceFacet, ...] = tuple(EvidenceFacet)


@dataclass(frozen=True, slots=True)
class EntitySeed:
    """An analyst-supplied public entity anchor; never an inferred identity match."""

    ref: str
    name: str
    aliases: tuple[str, ...] = ()
    domains: tuple[str, ...] = ()
    kind: str = "organization"

    def __post_init__(self) -> None:
        ref = str(self.ref).strip()
        name = " ".join(str(self.name).split())
        if not ref or len(ref) > 128:
            raise ValueError("entity seed ref must contain 1-128 characters")
        if not name or len(name) > 256:
            raise ValueError("entity seed name must contain 1-256 characters")
        if _EMAIL.search(name) or _PHONE.search(name):
            raise ValueError("direct personal contact identifiers are not supported as search anchors")
        if self.kind not in {"organization", "public_person", "domain", "product", "topic"}:
            raise ValueError("entity seed kind must be organization, public_person, domain, product or topic")
        aliases = []
        for raw in self.aliases:
            alias = " ".join(str(raw).split())
            if not alias or len(alias) > 256:
                continue
            if _EMAIL.search(alias) or _PHONE.search(alias):
                raise ValueError("direct personal contact identifiers are not supported as search anchors")
            aliases.append(alias)
        domains = []
        declared_domains = self.domains or ((name,) if self.kind == "domain" else ())
        for raw in declared_domains:
            domain = str(raw).strip().lower().rstrip(".")
            if not _DOMAIN.fullmatch(domain):
                raise ValueError(f"invalid public domain anchor: {raw!r}")
            domains.append(domain)
        object.__setattr__(self, "ref", ref)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "aliases", tuple(sorted(set(aliases), key=str.casefold)))
        object.__setattr__(self, "domains", tuple(sorted(set(domains))))


@dataclass(frozen=True, slots=True)
class ResearchContext:
    """The bounded context from which a deterministic discovery plan is compiled."""

    tenant_id: str
    investigation_id: str
    context_text: str
    entities: tuple[EntitySeed, ...] = ()
    facets: tuple[EvidenceFacet, ...] = DEFAULT_FACETS
    time_from: str | None = None
    time_to: str | None = None
    max_queries: int = 64

    def __post_init__(self) -> None:
        tenant = str(self.tenant_id).strip()
        investigation = str(self.investigation_id).strip()
        context = " ".join(str(self.context_text).split())
        if not tenant or not investigation:
            raise ValueError("tenant_id and investigation_id are required")
        if not context or len(context) > 12_000:
            raise ValueError("context_text must contain 1-12000 characters")
        if _EMAIL.search(context) or _SECRET.search(context):
            raise ValueError("context contains a direct contact identifier or credential-like material")
        if not 1 <= self.max_queries <= 128:
            raise ValueError("max_queries must be between 1 and 128")
        start = date.fromisoformat(self.time_from) if self.time_from else None
        end = date.fromisoformat(self.time_to) if self.time_to else None
        if start and end and end < start:
            raise ValueError("time_to must not precede time_from")
        facets = tuple(dict.fromkeys(EvidenceFacet(item) for item in self.facets))
        if not facets:
            raise ValueError("at least one evidence facet must be selected")
        entity_refs = [item.ref for item in self.entities]
        if len(entity_refs) != len(set(entity_refs)):
            raise ValueError("entity seed refs must be unique")
        object.__setattr__(self, "tenant_id", tenant)
        object.__setattr__(self, "investigation_id", investigation)
        object.__setattr__(self, "context_text", context)
        object.__setattr__(self, "facets", facets)


@dataclass(frozen=True, slots=True)
class DiscoveryQuery:
    """One bounded public-search task, ready for the existing dispatcher contract."""

    query_id: str
    ordinal: int
    facet: EvidenceFacet
    strategy: str
    query: str
    subject_ref: str | None
    provider: str = "searxng"
    source_id: str = ""
    source_name: str = "searxng_public_search"
    runtime_ref: str = "searxng"
    result_role: str = "DISCOVERY_ONLY"
    max_pages: int = 5
    priority: int = 50

    def as_dispatch_task(
        self, *, plan_id: str, context: ResearchContext, context_digest: str,
        source_id: str, source_name: str,
    ) -> dict[str, Any]:
        """Adapt the plan to the established Dispatcher task shape; do not dispatch here."""
        if not source_id or not source_name:
            raise ValueError("the installed source catalogue must resolve source_id and source_name")
        task_id = f"discovery-{self.query_id}"
        return {
            "task_id": task_id,
            "query": self.query,
            "source_id": source_id,
            "source_name": source_name,
            "runtime_ref": self.runtime_ref,
            "category": "08. Knowledge",
            "required_capabilities": ["http"],
            "tenant_id": context.tenant_id,
            "case_id": context.investigation_id,
            "investigation_id": context.investigation_id,
            "plan_id": plan_id,
            "query_ref": self.query_id,
            "subject_ref": self.subject_ref or "",
            "evidence_facet": self.facet.value,
            "discovery_strategy": self.strategy,
            "context_digest": context_digest,
            "result_role": self.result_role,
            "idempotency_key": f"{plan_id}:{self.query_id}",
            "max_pages": self.max_pages,
            "constraints": [
                {"kind": "public_source_only"},
                {"kind": "discovery_only"},
                {"kind": "no_access_control_bypass"},
                {"kind": "no_private_contact_extraction"},
                *(
                    [{"kind": "time_window", "from": context.time_from, "to": context.time_to}]
                    if context.time_from or context.time_to else []
                ),
            ],
        }


@dataclass(frozen=True, slots=True)
class FacetCoverage:
    """Planning coverage, not proof that the network contains no other material."""

    facet: EvidenceFacet
    status: str
    planned_queries: int
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "facet": self.facet.value,
            "status": self.status,
            "planned_queries": self.planned_queries,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class DiscoveryPlan:
    plan_id: str
    context_digest: str
    tenant_id: str
    investigation_id: str
    tasks: tuple[DiscoveryQuery, ...]
    coverage: tuple[FacetCoverage, ...]
    warnings: tuple[str, ...] = ()
    truncated: bool = False
    status: str = "PLANNED_NOT_DISPATCHED"
    compiler_version: str = "context-discovery-v1"

    def as_dict(self, *, context: ResearchContext, source_id: str, source_name: str) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "context_digest": self.context_digest,
            "tenant_id": self.tenant_id,
            "investigation_id": self.investigation_id,
            "status": self.status,
            "compiler_version": self.compiler_version,
            "query_count": len(self.tasks),
            "truncated": self.truncated,
            "coverage": [item.as_dict() for item in self.coverage],
            "warnings": list(self.warnings),
            "tasks": [
                {
                    "query_id": item.query_id,
                    "ordinal": item.ordinal,
                    "facet": item.facet.value,
                    "strategy": item.strategy,
                    "query": item.query,
                    "subject_ref": item.subject_ref,
                    "provider": item.provider,
                    "source_id": source_id,
                    "source_name": source_name,
                    "runtime_ref": item.runtime_ref,
                    "result_role": item.result_role,
                    "priority": item.priority,
                    "dispatch_task": item.as_dispatch_task(
                        plan_id=self.plan_id, context=context, context_digest=self.context_digest,
                        source_id=source_id, source_name=source_name,
                    ),
                }
                for item in self.tasks
            ],
            "guarantees": {
                "results_are_unverified_leads": True,
                "claim_admission_allowed": False,
                "raw_content_on_event_bus": False,
                "access_control_bypass": False,
                "private_contact_collection": False,
            },
        }
