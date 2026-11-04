# Context-to-Discovery Fabric

## Objective

Turn an approved investigation context into a reproducible, bounded set of public-source discovery actions. The compiler is a strategy layer, not a second crawler, event bus or evidence store. It uses the existing research-case lifecycle, source policy, budget reservation, dispatcher, acquisition worker and Capture/Observation pipeline.

The initial compiler is deterministic. Explicit typed entity anchors are preferred; quoted phrases and domain literals may be inferred as topics. Its token extraction is a conservative fallback, not natural-language understanding or entity resolution. A future semantic context interpreter must preserve source spans, distinguish analyst assertions from model hypotheses, expose uncertainty and write its outputs as typed, reviewable context amendments.

## Search strategy slices

For each public entity anchor, the compiler can create bounded queries for:

- exact phrases, aliases and context-specific combinations;
- first-party sites and public documents (including PDFs);
- public registries, filings and official records;
- public roles, affiliations, statements and relationships;
- scholarly and publication indexes;
- historical-web and archive discovery;
- public DNS, RDAP and certificate-transparency material;
- public incident advisories and disclosure notices.

Dork syntax is constrained to public search operators such as `site:` and `filetype:` plus quoted phrases. Public incident coverage means advisory, disclosure and incident-report metadata. It does not mean acquiring stolen credential collections, stealer logs or restricted breached datasets. The system does not attempt authenticated access, access-control bypass or private-contact extraction.

## Research Case execution lifecycle

The operational route is the existing case workflow:

1. Create a research case with typed public subject anchors, purpose/basis, jurisdiction, temporal window, source allowlist and a durable budget reference.
2. An administrator approves the exact scope and its policy digest.
3. `POST /api/v1/research-cases/{case_id}/plan` compiles the case obligations and context into persisted `ResearchAction` proposals. The returned `discovery_plan` reports planned queries, truncation, facets with no safe query and the resolved policy/catalogue source.
4. Discovery actions remain `DISCOVERY_ONLY` and require explicit operator approval. They do not satisfy evidence obligations.
5. `POST /api/v1/research-cases/{case_id}/actions/approve` appends immutable approved action versions. `POST /api/v1/research-cases/{case_id}/run` reserves the case's durable request/byte/record/concurrency/time budgets before publishing requests.
6. The existing `CaseDispatchExecutor → PlanDispatcher → Dispatcher → acquisition.request → worker` path executes the SearXNG runtime.
7. The worker persists every runtime artifact through the canonical `ArtifactSink`: raw object first, then Capture, Observation and the broker-acknowledged event. Search-result records remain unverified leads, not admitted assertions.
8. Only a later governed fetch of a selected public lead can create the source-document Capture/Observation used for interpretation and claim admission.

The standalone `POST /api/v1/discovery/plan` route is a preview helper for an investigation. It does not dispatch or bypass source policy, action approval or durable budgets.

## Boundedness and coverage

The source policy in force is authoritative. For the current SearXNG profile, the plan query cap is derived from `max_requests / max_pages` (currently 20 requests / 5 pages, hence at most four actions per run). A query marked planned is only scheduled intent, not a successful fetch. A facet marked `not_plannable` is an explicit gap, not an empty search result. Truncation and missing anchors are surfaced to the analyst.

Runtime coverage must separately record provider health, rate-limit responses, licensing/terms, robots policy, search-index limitations, budget exhaustion, parser success, raw-object read-back and Observation acknowledgement. The system must never label a search as exhaustive merely because every planned task completed.

## Adaptive expansion

The intended next stage is a feedback-driven strategy loop. It should use admitted facts, verified source metadata and explicit coverage gaps to propose new facets, source adapters, aliases, archive slices and time windows. Search snippets may suggest leads but cannot become identity truth or spawn unrestricted recursive collection. Provider adapters must declare their execution contract, licence/terms state, egress hosts, parser, cost envelope and evidence role before being eligible.

A provider-specific source that is not attested or whose worker integration is absent remains a visible capability gap. Do not silently route it through generic HTTP or claim support because a YAML file exists.

## API preview example

```json
{
  "investigation_id": "INV-EXAMPLE",
  "context_text": "Review the public history, filings and security disclosures concerning Acme Systems.",
  "entities": [
    {
      "ref": "entity-acme",
      "name": "Acme Systems",
      "aliases": ["Acme"],
      "domains": ["acme.example"],
      "kind": "organization"
    }
  ],
  "facets": ["identity", "official_records", "public_incidents"],
  "time_from": "2020-01-01",
  "time_to": "2026-11-04",
  "max_queries": 48
}
```

## Release-gate coverage snapshot

| Slice | Current status | What this means |
|---|---|---|
| Public web search and dorking | Integrated through SearXNG and the governed case worker | Bounded result pages become Capture/Observation-backed discovery leads |
| First-party pages and public PDFs | Discoverable; source fetch requires the approved lead-harvest path | A search hit alone is not yet source evidence |
| Public filings, registry and publication sources | Present in the acquisition catalogue; not all are wired into this case discovery plan | Catalogue presence is not proof of case-path execution |
| Common Crawl, Wayback and certificate transparency | Existing adapters and proofs exist in other acquisition/discovery paths | Not yet a multi-provider context plan in this case workflow |
| Public incident disclosures | Searchable as public advisory/report leads | Restricted raw datasets are not collected |
| Adaptive follow-up | Not yet closed-loop in this increment | Coverage gaps are surfaced, but do not yet launch autonomous multi-round plans |

The current integrated Research Case search path is intentionally conservative: the source policy permits up to 20 requests and up to 5 pages per request, so one planning round emits at most four SearXNG actions. Raising that cap requires a policy/budget change and measured provider, parser, storage and Redpanda throughput—not a local compiler constant.
