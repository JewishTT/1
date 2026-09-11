# AcquisitionWorker Contract

All acquisition engines conform to this interface (Spec FR-005, FR-033 / §72). Concrete implementations: Rust HTTP worker, Crawlee worker, Playwright browser worker, API connector, feed connector, dataset connector, document connector.

## Interface

```text
capabilities() -> CapabilitySet
    // capabilities (source types, content types) mapping to Source.capabilities
    // e.g. {source_types: [HTTP, RSS, Atom], mime: [html, json, xml]}

estimate(task) -> CostEstimate
    // expected_cost, expected_duration, expected_bytes, duplicate_risk
    // input to UtilityScorer; must agree with resource pricing (R-9)

acquire(task) -> AcquisitionOutcome
    // outcome: observation_created | unchanged | duplicate | failed
    // on success: raw object persisted via Storage contract (content-addressed),
    // Observation payload emitted with provenance + timing
```

## Requirements

- Workers are isolated pools per class (HTTP vs Browser etc.) — no mixing (Spec FR-005 / §18).
- Browser fabric is escalation-only; never the default path for the whole workload (§17).
- Workers never bypass auth/CAPTCHA/paywall/access controls (Constitution VII).
- Failure paths return structured failure reasons → dispatch retry/cooldown/dead-letter per retry budgets (FR-028).
- Idempotency: `acquire(task)` is keyed by `task_id`; a retried identical task must not duplicate observations (FR-024).
- Worker choice comes from Source.capabilities + strategy resolution, never hard-coded in domain logic (C-5).

## Typical implementations at v1

- `worker-http` — Rust (tokio/reqwest): HTTP-first path, conditional acquisition (etag/last-modified), content hashing, canonicalization, dedup at request/url/hash layers, response sufficiency check.
- `worker-browser` — Playwright + Chromium pool: escalation path for JS-required content; isolated pool, per-context resource/CPU limits, egress policy (FR-029).
- `connector-feed` / `connector-api` / `connector-dataset` / `connector-document` — strategy-specific, same contract.