# Industry OSINT and geospatial integration

## Architectural decisions

Integrate external engineering patterns through narrow contracts, not by
importing unrelated application runtimes into the core process.

### theHarvester

theHarvester runs as a separately deployed authenticated REST service. Cognitive
submits finite passive subdomain runs and imports the documented JSONL export.
The adapter retains per-source outcomes, enforces an expiring authorized-domain
scope, filters non-hostname personal results, refuses redirects and bounds
response bodies.

The upstream is GPL-2.0-only and currently requires Python 3.14; Cognitive
acquisition targets Python 3.11-3.13. The REST boundary avoids an in-process
dependency and keeps licensing/runtime isolation explicit. Zero results are not
absence claims unless a source's detection power is separately measured.

### FollowTheMoney

FollowTheMoney is an optional MIT-licensed interchange model, not a replacement
for Cognitive canonical identity or claim lifecycle. Export uses a curated
schema/property allowlist. Provenance is carried in a second JSONL sidecar so
lineage is not collapsed into third-party entity properties. No operation
automatically merges identities or admits claims.

### TheBigBrother

TheBigBrother is surveyed as a capability catalogue only. Its RDAP/TLS posture
ideas are useful; its runtime is not executed. Cognitive reimplements bounded
probes behind exact domain authorization, hard timeouts and evidence provenance.
Biometric identification, breached credentials, stealer logs, camera
surveillance, ALPR, subscriber/SIM enrichment, cross-service account
enumeration, covert tracking and identity profiling remain excluded.

### God's Eye View

God's Eye View is pinned as an optional Git submodule and runs in its own
loopback-only Node service. The webapp embeds only its public spatial-context
view. No person/case/entity identifier or evidence is passed to it. The
integration excludes named-person search, person tracking, face recognition,
camera/ALPR pivots and voice collection.

The upstream MIT license covers source code only. Every runtime/bundled data
provider retains its own license, terms and attribution requirements. The
default deployment stays keyless and local.

## Performance and language strategy

Acquisition already has a Rust workspace for contracts, HTTP, browser,
discovery, frontier and content routing. New Rust/Go services are not added
merely to increase line count. A native worker must demonstrate a measured
bottleneck, stable versioned contract, backpressure, cancellation,
replay/idempotency, bounded memory and parity tests against the Python
reference before it is promoted.
