# Context-to-Discovery Fabric

The Context-to-Discovery compiler turns a tenant-scoped investigation brief and explicit public entity anchors into a reproducible, bounded search plan. It is the strategy layer above the existing SearXNG runtime, acquisition dispatcher, frontier and Capture/Observation pipeline. It does not create a second queue.

The first implementation is deterministic. Explicit entity anchors are preferred; quoted phrases and domain literals may be inferred as topics. Keyword heuristics are not an NLP identity resolver. A future model-backed interpreter must implement the same typed contract, retain source spans and expose uncertainty.

## Search slices

The default plan fans each anchor across several public information surfaces: exact-phrase search, first-party domain pages, public PDF documents, official registries and filings, public affiliations and statements, scholarly indexes, historical web archives, public DNS/RDAP/certificate-transparency references, and official incident advisories.

Dork syntax is limited to public search operators such as `site:` and `filetype:` plus quoted phrases. It does not attempt authenticated access or private-contact extraction. Incident coverage means public advisories and disclosure notices.

## Execution contract

Each plan item is a Dispatcher-compatible task for the existing SearXNG runtime (`source_id=searxng.search`, `runtime_ref=searxng`, `result_role=DISCOVERY_ONLY`). Tasks retain tenant/investigation scope, context digest, query reference and idempotency key.

`POST /api/v1/discovery/plan` validates the investigation's tenant and state, then returns a preview. It does not dispatch tasks or bypass durable budget reservation, source policy or approval checks. Returned tasks must pass through the configured Dispatcher. Search snippets remain unverified discovery leads; only a later governed fetch can create immutable Capture/Observation evidence.

## Coverage semantics

A facet marked `planned` means the compiler emitted one or more queries. It does not mean a source answered, that the internet was exhaustively searched, or that evidence exists. `not_plannable` records a missing anchor or safe query template. Runtime coverage must additionally account for provider health, licensing, robots restrictions, search-index gaps, budgets, parser success, raw-object read-back and Observation event acknowledgement.

The compiler is a plan producer, not an unrestricted crawler. Adaptive follow-up should consume newly admitted public facts and explicit coverage gaps, not untrusted snippets as identity truth.

## API example

A preview request uses explicit entity anchors and a bounded facet/time selection:

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

The response includes a stable `plan_id`, `context_digest`, facet-level planning coverage and dispatcher-compatible task manifests. It is a reviewable plan only; the API does not publish events or schedule workers.
