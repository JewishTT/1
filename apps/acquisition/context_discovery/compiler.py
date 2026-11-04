"""Deterministic Context-to-Discovery compiler for public, governed research.

This is a strategy planner, not a crawler and not a claim generator. It turns an
analyst's context plus explicit entity anchors into bounded SearXNG tasks. Search
results are always DISCOVERY_ONLY; fetching, Capture/Observation persistence,
admission and budgets remain owned by the existing platform services.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from .models import (
    DiscoveryPlan,
    DiscoveryQuery,
    EntitySeed,
    EvidenceFacet,
    FacetCoverage,
    ResearchContext,
)


_COMPILER_VERSION = "context-discovery-v1"
_TOKEN = re.compile(r"[\w][\w.-]{2,}", re.UNICODE)
_DOMAIN_MENTION = re.compile(r"(?i)(?<![\w-])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}(?![\w-])")
_QUOTED = re.compile(r"[\u0022\u0027]([^\u0022\u0027]{3,160})[\u0022\u0027]")
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
_STOPWORDS = frozenset(
    "about after also among and any are area because been before being between brief but "
    "case context data detail did does from have into investigation involving relevant "
    "research regarding should that the their them there these they this those through "
    "under using was were what when where which while with within without".split()
)
_FACET_PRIORITY = {
    EvidenceFacet.IDENTITY: 90,
    EvidenceFacet.OFFICIAL_RECORDS: 85,
    EvidenceFacet.AFFILIATIONS: 78,
    EvidenceFacet.PUBLIC_STATEMENTS: 75,
    EvidenceFacet.PUBLICATIONS: 65,
    EvidenceFacet.HISTORICAL_WEB: 62,
    EvidenceFacet.TECHNICAL_INFRASTRUCTURE: 60,
    EvidenceFacet.PUBLIC_INCIDENTS: 58,
    EvidenceFacet.RELATIONSHIPS: 55,
}


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _quote(value: str) -> str:
    """Quote a phrase without allowing it to inject a second search operator."""
    cleaned = " ".join(str(value).replace('"', " ").replace("'", " ").split())
    return f'"{cleaned}"'


def _time_suffix(context: ResearchContext) -> str:
    values = []
    if context.time_from:
        values.append(f"after:{context.time_from}")
    if context.time_to:
        values.append(f"before:{context.time_to}")
    return " " + " ".join(values) if values else ""


def _context_terms(text: str, *, limit: int = 8) -> tuple[str, ...]:
    """Pick stable topical terms; this is a fallback, not an NLP entity resolver."""
    terms: list[str] = []
    seen: set[str] = set()
    for token in _TOKEN.findall(text):
        lowered = token.casefold().strip("._-")
        if len(lowered) < 4 or lowered in _STOPWORDS or lowered.isdigit():
            continue
        if _EMAIL.search(token) or lowered in seen:
            continue
        seen.add(lowered)
        terms.append(token)
        if len(terms) >= limit:
            break
    return tuple(terms)


def _infer_explicit_seeds(context: ResearchContext) -> tuple[EntitySeed, ...]:
    """Infer only explicit quoted phrases and domain literals; never guess a person."""
    if context.entities:
        return context.entities
    seeds: list[EntitySeed] = []
    seen: set[str] = set()
    for phrase in _QUOTED.findall(context.context_text):
        name = " ".join(phrase.split())
        key = name.casefold()
        if key not in seen and not _EMAIL.search(name):
            seen.add(key)
            seeds.append(EntitySeed(ref=f"topic-{_digest(key)[:12]}", name=name, kind="topic"))
    for domain in _DOMAIN_MENTION.findall(context.context_text):
        value = domain.lower()
        if value in seen:
            continue
        seen.add(value)
        seeds.append(EntitySeed(ref=f"domain-{_digest(value)[:12]}", name=value, domains=(value,), kind="domain"))
    return tuple(seeds)


@dataclass(frozen=True, slots=True)
class _Candidate:
    facet: EvidenceFacet
    strategy: str
    query: str
    subject_ref: str | None
    specificity: int


class ContextDiscoveryCompiler:
    """Compile investigative context into deterministic, bounded public-search work."""

    def compile(self, context: ResearchContext) -> DiscoveryPlan:
        if not isinstance(context, ResearchContext):
            raise TypeError("compile expects a validated ResearchContext")
        seeds = _infer_explicit_seeds(context)
        terms = _context_terms(context.context_text)
        candidates: list[_Candidate] = []
        time_suffix = _time_suffix(context)

        if seeds:
            for seed in seeds:
                candidates.extend(self._for_seed(seed, context.facets, terms, time_suffix))
        else:
            candidates.extend(self._for_context(context.facets, terms, time_suffix))

        # Deterministic dedup keeps the strongest facet/strategy identity. Query text
        # is provider-agnostic; SearXNG executes only public web-search syntax.
        unique: dict[tuple[str, str], _Candidate] = {}
        for item in candidates:
            normalized = " ".join(item.query.split())
            if not normalized or len(normalized) > 512:
                continue
            key = (item.facet.value, normalized.casefold())
            existing = unique.get(key)
            if existing is None or item.specificity > existing.specificity:
                unique[key] = _Candidate(
                    facet=item.facet,
                    strategy=item.strategy,
                    query=normalized,
                    subject_ref=item.subject_ref,
                    specificity=item.specificity,
                )
        ordered = sorted(
            unique.values(),
            key=lambda item: (
                -_FACET_PRIORITY[item.facet],
                -item.specificity,
                item.facet.value,
                item.query.casefold(),
            ),
        )
        truncated = len(ordered) > context.max_queries
        selected = ordered[: context.max_queries]

        context_material = {
            "tenant_id": context.tenant_id,
            "investigation_id": context.investigation_id,
            "context_text": context.context_text,
            "entities": [
                {"ref": seed.ref, "name": seed.name, "aliases": seed.aliases,
                 "domains": seed.domains, "kind": seed.kind}
                for seed in seeds
            ],
            "facets": [item.value for item in context.facets],
            "time_from": context.time_from,
            "time_to": context.time_to,
        }
        context_digest = _digest(context_material)
        tasks: list[DiscoveryQuery] = []
        for ordinal, item in enumerate(selected):
            query_id = _digest({
                "context_digest": context_digest,
                "facet": item.facet.value,
                "strategy": item.strategy,
                "query": item.query,
                "subject_ref": item.subject_ref,
                "compiler": _COMPILER_VERSION,
            })[:24]
            tasks.append(
                DiscoveryQuery(
                    query_id=query_id,
                    ordinal=ordinal,
                    facet=item.facet,
                    strategy=item.strategy,
                    query=item.query,
                    subject_ref=item.subject_ref,
                    priority=_FACET_PRIORITY[item.facet],
                )
            )

        counts = Counter(task.facet for task in tasks)
        coverage = tuple(
            FacetCoverage(
                facet=facet,
                status="planned" if counts[facet] else "not_plannable",
                planned_queries=counts[facet],
                reason="" if counts[facet] else self._missing_reason(facet, seeds),
            )
            for facet in context.facets
        )
        warnings: list[str] = []
        if not seeds:
            warnings.append(
                "No explicit entity anchors were supplied or safely inferred; the plan uses topical terms only."
            )
        if truncated:
            warnings.append(
                f"Query budget reached: {len(ordered)} candidates were reduced to {context.max_queries} tasks."
            )
        if EvidenceFacet.PUBLIC_INCIDENTS in context.facets:
            warnings.append(
                "Incident queries target public advisories and disclosure notices only; breached datasets and stolen credentials are not collected."
            )
        warnings.append(
            "A planned query is not proof of exhaustive internet coverage; source outages, indexing gaps, robots policies and licensing restrictions remain explicit runtime outcomes."
        )
        plan_id = "DP-" + _digest({
            "context_digest": context_digest,
            "query_ids": [task.query_id for task in tasks],
            "compiler": _COMPILER_VERSION,
        })[:24]
        return DiscoveryPlan(
            plan_id=plan_id,
            context_digest=context_digest,
            tenant_id=context.tenant_id,
            investigation_id=context.investigation_id,
            tasks=tuple(tasks),
            coverage=coverage,
            warnings=tuple(warnings),
            truncated=truncated,
        )

    def _for_seed(
        self,
        seed: EntitySeed,
        facets: Iterable[EvidenceFacet],
        terms: tuple[str, ...],
        time_suffix: str,
    ) -> list[_Candidate]:
        out: list[_Candidate] = []
        anchors = (seed.name, *seed.aliases)
        term_clause = " ".join(terms[:4])
        for anchor in anchors:
            quoted = _quote(anchor)
            if EvidenceFacet.IDENTITY in facets:
                out.append(_Candidate(EvidenceFacet.IDENTITY, "exact_phrase", quoted + time_suffix, seed.ref, 100))
                if term_clause:
                    out.append(_Candidate(
                        EvidenceFacet.IDENTITY, "contextual_web",
                        f"{quoted} {_quote(term_clause)}{time_suffix}", seed.ref, 92,
                    ))
            out.extend(self._facet_queries(seed, anchor, facets, time_suffix))

        for domain in seed.domains:
            if EvidenceFacet.TECHNICAL_INFRASTRUCTURE in facets:
                out.append(_Candidate(
                    EvidenceFacet.TECHNICAL_INFRASTRUCTURE, "certificate_transparency",
                    f'site:crt.sh "{domain}"{time_suffix}', seed.ref, 96,
                ))
                out.append(_Candidate(
                    EvidenceFacet.TECHNICAL_INFRASTRUCTURE, "public_dns_registry",
                    f'"{domain}" (RDAP OR DNS OR certificate OR nameserver){time_suffix}', seed.ref, 88,
                ))
                out.append(_Candidate(
                    EvidenceFacet.TECHNICAL_INFRASTRUCTURE, "domain_scoped_search",
                    f'site:{domain} (about OR contact OR services OR products){time_suffix}', seed.ref, 85,
                ))
            if EvidenceFacet.HISTORICAL_WEB in facets:
                out.append(_Candidate(
                    EvidenceFacet.HISTORICAL_WEB, "archive_discovery",
                    f'"{domain}" (archive OR snapshot OR "Wayback Machine"){time_suffix}', seed.ref, 82,
                ))
        return out

    def _facet_queries(
        self,
        seed: EntitySeed,
        anchor: str,
        facets: Iterable[EvidenceFacet],
        time_suffix: str,
    ) -> list[_Candidate]:
        q = _quote(anchor)
        out: list[_Candidate] = []
        domains = seed.domains
        for facet in facets:
            if facet is EvidenceFacet.IDENTITY:
                continue
            if facet is EvidenceFacet.AFFILIATIONS:
                out.append(_Candidate(
                    facet, "public_affiliations",
                    f'{q} (leadership OR subsidiary OR affiliate OR employer OR partner){time_suffix}',
                    seed.ref, 75,
                ))
            elif facet is EvidenceFacet.OFFICIAL_RECORDS:
                out.append(_Candidate(
                    facet, "public_records",
                    f'{q} (official OR registry OR filing OR annual report OR government){time_suffix}',
                    seed.ref, 80,
                ))
                if seed.kind == "organization":
                    out.append(_Candidate(
                        facet, "public_filings",
                        f'site:sec.gov {q} OR site:opencorporates.com {q}{time_suffix}',
                        seed.ref, 86,
                    ))
                for domain in domains:
                    out.append(_Candidate(
                        facet, "first_party_documents",
                        f'site:{domain} {q} filetype:pdf{time_suffix}', seed.ref, 98,
                    ))
            elif facet is EvidenceFacet.PUBLIC_STATEMENTS:
                out.append(_Candidate(
                    facet, "public_statements",
                    f'{q} (press release OR statement OR speech OR interview OR announcement){time_suffix}',
                    seed.ref, 72,
                ))
            elif facet is EvidenceFacet.PUBLICATIONS:
                out.append(_Candidate(
                    facet, "research_publications",
                    f'{q} (paper OR publication OR study OR report) (site:crossref.org OR site:openalex.org OR site:arxiv.org){time_suffix}',
                    seed.ref, 74,
                ))
            elif facet is EvidenceFacet.HISTORICAL_WEB and not domains:
                out.append(_Candidate(
                    facet, "archive_discovery",
                    f'{q} (archive OR snapshot OR "Wayback Machine"){time_suffix}', seed.ref, 68,
                ))
            elif facet is EvidenceFacet.PUBLIC_INCIDENTS:
                out.append(_Candidate(
                    facet, "public_incident_advisories",
                    f'{q} (security advisory OR incident report OR breach notification OR vulnerability) '
                    f'(site:cisa.gov OR site:cert.europa.eu OR site:enisa.europa.eu){time_suffix}',
                    seed.ref, 84,
                ))
            elif facet is EvidenceFacet.RELATIONSHIPS:
                out.append(_Candidate(
                    facet, "public_relationships",
                    f'{q} (partner OR subsidiary OR acquisition OR collaboration OR "joint venture" OR ownership){time_suffix}',
                    seed.ref, 70,
                ))
        return out

    def _for_context(
        self,
        facets: Iterable[EvidenceFacet],
        terms: tuple[str, ...],
        time_suffix: str,
    ) -> list[_Candidate]:
        if not terms:
            return []
        phrase = _quote(" ".join(terms[:6]))
        out = []
        if EvidenceFacet.IDENTITY in facets:
            out.append(_Candidate(EvidenceFacet.IDENTITY, "contextual_web", phrase + time_suffix, None, 40))
        for facet in facets:
            if facet is EvidenceFacet.IDENTITY:
                continue
            if facet is EvidenceFacet.PUBLIC_INCIDENTS:
                query = f'{phrase} (advisory OR incident report OR disclosure) (site:cisa.gov OR site:cert.europa.eu){time_suffix}'
            elif facet is EvidenceFacet.PUBLICATIONS:
                query = f'{phrase} (publication OR paper OR report) (site:crossref.org OR site:openalex.org OR site:arxiv.org){time_suffix}'
            elif facet is EvidenceFacet.HISTORICAL_WEB:
                query = f'{phrase} (archive OR historical OR snapshot){time_suffix}'
            else:
                query = f'{phrase} {facet.value.replace("_", " ")}{time_suffix}'
            out.append(_Candidate(facet, "context_facet", query, None, 35))
        return out

    @staticmethod
    def _missing_reason(facet: EvidenceFacet, seeds: tuple[EntitySeed, ...]) -> str:
        if facet is EvidenceFacet.TECHNICAL_INFRASTRUCTURE and not any(seed.domains for seed in seeds):
            return "no_domain_anchor"
        if not seeds:
            return "no_explicit_entity_anchor"
        return "no_safe_query_template"
