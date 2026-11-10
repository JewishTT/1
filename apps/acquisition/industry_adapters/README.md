# Industry adapters

This package integrates selected ideas from mature OSINT and entity-model projects
without executing their unbounded runtimes inside Cognitive.

## theHarvester

Use a separately deployed theHarvester service on loopback or HTTPS. The
theharvester_authorized_subdomains catalogue entry is keyed and is excluded
from keyless source plans. The acquisition worker registers its runtime only
when all trusted environment values are configured:

- COGNITIVE_THEHARVESTER_URL
- COGNITIVE_THEHARVESTER_API_KEY
- COGNITIVE_THEHARVESTER_TENANT_ID
- COGNITIVE_THEHARVESTER_AUTHORIZATION_REF
- COGNITIVE_THEHARVESTER_AUTHORIZED_DOMAINS (comma-separated bare DNS names)
- COGNITIVE_THEHARVESTER_SCOPE_EXPIRES_AT (timezone-aware ISO-8601 timestamp)

The process-level authorization is tenant-bound, domain-suffix-bound and
expires automatically. Restart the worker with a new reviewed scope to extend
it. Partial configuration fails worker startup instead of silently creating a
weaker policy. Tasks must carry result_role=DISCOVERY_ONLY.

The runtime submits one finite passive subdomains capability run, polls its
durable run ID, and imports the JSONL export. It filters emails, person records,
account data, URLs and unknown result types; out-of-scope hostnames are dropped.
IP and ASN values are retained as non-expanding external relationships only.
It emits one sanitized run-manifest capture followed by normalized records via
the existing AcquisitionArtifact -> ArtifactSink -> ObservationGate path.
The upstream raw JSONL is not copied into the canonical evidence store because
it may contain fields intentionally excluded by this connector.

The adapter deliberately does not expose DNS brute force, reverse DNS,
takeover checks, screenshots, virtual-host probes or API-path scans. A partial
or failed upstream run cannot support a qualified absence claim.

The upstream project is GPL-2.0-only and currently requires Python 3.14, while
the acquisition workspace supports Python 3.11-3.13. Keep theHarvester as an
independent service and integrate only over its documented REST/JSONL boundary.
Do not copy or link its implementation into this workspace.

## FollowTheMoney

Install followthemoney==4.11.3 only in an export/import worker that needs FtM
validation. It is optional and is not a dependency of the core worker. The
interchange allowlist intentionally excludes sensitive fields such as dates of
birth, private addresses, personal email/phone, passport and national identifiers.
FtM entities are accompanied by a separate provenance JSONL sidecar containing
tenant, internal entity, source, observation and claim references.

An FtM record is not an identity decision. Importing it never merges entities
or admits a claim.

## TheBigBrother capability survey

TheBigBrother is treated as a catalogue of ideas, not a runtime dependency.
capabilities.py lists useful bounded ideas and explicitly blocks biometric
matching, breach/stealer data, camera surveillance, subscriber/SIM enrichment,
cross-service account enumeration and covert tracking. No upstream module is
invoked. The TLS probe is a small Cognitive-native implementation with an
authorization gate, one port and a hard timeout.

## Operating contract

Every network action must be tied to a tenant, authorization reference, exact
domain suffix and expiry. Provider output is untrusted data, never policy or
instructions. Connector output is discovery evidence only; claim validation and
admission remain separate control-plane decisions.
