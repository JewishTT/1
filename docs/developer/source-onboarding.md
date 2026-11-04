# Public source onboarding

A source catalogue entry is metadata, not a working integration. This checklist defines the minimum path for a source to be offered to a Research Case.

## Source admission

1. Document the source owner, public/authorized scope, terms, license, attribution, permitted use, geographic/temporal limits, retention, rate limits and required credentials.
2. Identify the source family and evidence role. Discovery leads must remain DISCOVERY_ONLY; raw captures must not be promoted to verified claims automatically.
3. Add an explicit policy profile: tenant/scope eligibility, request/page/byte/time/concurrency budgets, allowed operations and egress destinations.
4. Add the runtime adapter using the existing acquisition contracts. Validate bounded pagination, cancellation, retries, backoff, timeouts, response size and secret redaction.
5. Add a parser/schema contract with malformed, empty, duplicate, partial and provider-error fixtures.
6. Route every evidence artifact through ArtifactSink. Preserve immutable raw bytes, content hash, provenance, tenant, investigation, source, task and capture time basis.
7. Prove event publication and consumer read-back using the actual stack. Prove replay is idempotent.
8. Add source-specific live acceptance tests with clear credential gates; publish proof as a CI artifact, not a committed run output.
9. Add coverage accounting: planned, attempted, returned, persisted, parsed, admitted, duplicate, rejected, timed out, throttled, and unavailable counts.
10. Add the source to the Research Case planner only after the preceding contracts are proven and explicitly approved.

## Discovery and identity rules

- Search results and archive entries are leads; they are not identity claims.
- Keep candidate identity, source attribution, retrieval time, valid time and observation time separate.
- Resolve conflicts through the platform admission/review process, with provenance and confidence.
- Prefer official registries, first-party statements, scholarly/publication indexes, public filings, public archives, DNS/RDAP/CT datasets and public incident advisories where lawful and relevant.
- Do not acquire credentials, stealer logs, restricted breach datasets, private-contact books, or content obtained by bypassing authentication or access controls.
- Never claim all information on the Internet. Report the actual indexed/source coverage, provider limits, jurisdiction, time window and known exclusions.

## Definition of done

A source is WIRED only when runtime, policy, parser, egress, evidence persistence, event/consumer path, replay, tests, owner, license and live proof agree. Otherwise mark it CATALOG_ONLY, TEST_ONLY, BLOCKED, or UNAVAILABLE with the evidence for that status.
