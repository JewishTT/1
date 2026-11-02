# Layer 0 live source coverage — acceptance profile

This profile tests real, public HTTP integrations from the acquisition catalogue. It does **not**
claim that all 152 catalogue entries are live-tested, nor that an internet-wide search can be
exhaustive. The complete catalogue is validated separately; the selected profile exercises
multiple source families and endpoint/parser shapes through the same production path.

## Safe public acceptance set

The selected input is the public domain `python.org`, the public topic `Python programming language`,
and the public package `requests`. The profile checks:

- Domain registry, public DNS-over-HTTPS, certificate transparency (CertSpotter and crt.sh).
- Internet Archive CDX and availability, and URLscan's public index.
- Wikipedia and DuckDuckGo public discovery.
- Crossref, OpenAlex and arXiv Atom scholarly metadata.
- GitHub public repositories and Reddit public communities.
- GitHub Security Advisories, NVD CVE, CIRCL CVE mirror and the CISA KEV public feed.

The CISA KEV endpoint is a **global feed**, not an entity-filtered query. Its result is counted as
a public-feed ingestion test and is never described as a fact specifically about Python.

## Acceptance meaning

A source is marked PASS only when all of the following hold for one real response page:
1. The catalogue definition is enabled, keyless, HTTP-capable and declares `source_family`,
   `time_basis` and contact level.
2. The real connector returns a successful HTTP response and the declared source parser yields
   at least one record without unresolved required fields.
3. The content-addressed `raw_ref` is read back from ObjectStore and its SHA-256 matches the
   captured page digest.
4. The corresponding Capture and Observation rows are found in PostgreSQL.
5. The protobuf Observation event is read back from Redpanda under its observation key.

HTTP errors, parser/shape mismatches, missing credentials, disabled adapters, timeouts and
provider outages remain distinct statuses. They are not converted to a synthetic PASS.

The separate public-document crawl executes the deterministic `apps/zero` harvester for
`https://www.python.org/about/` with a maximum of two waves, four seeds and twelve physical HTTP
requests. The secure transport pins DNS, blocks private/local targets and redirects, honours
robots.txt, rate-limits the host, and allows only same-origin HTTPS links. Raw captures are
persisted before discovery-only stage records through the canonical ArtifactSink → Capture →
Observation path. These records are leads/technical metadata, not admitted claims.

## Deliberately excluded live profile

Private email/phone discovery, account enumeration, breach/leak endpoints, wireless probing,
biometrics, face matching, home-address inference and credentialed sources are not part of this
public acceptance profile. They remain separately governed capabilities and are never silently
enabled by the broad source inventory.

## Re-running

The GitHub Actions job `acquisition-live-stack-proof` upgrades the PostgreSQL schema, starts
Postgres/MinIO/Redpanda/SearXNG, runs Airbyte and SearXNG proofs, then executes
`apps/acquisition/_prove_public_source_matrix.py`. The machine-readable reports are uploaded as
`public-source-matrix.json` and `zero-layer-live.json`.
