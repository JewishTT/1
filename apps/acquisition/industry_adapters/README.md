# Industry adapters

This package integrates selected ideas from mature OSINT and entity-model projects
without executing their unbounded runtimes inside Cognitive.

## theHarvester

Use a separately deployed theHarvester service on loopback or HTTPS. Configure
COGNITIVE_THEHARVESTER_URL and COGNITIVE_THEHARVESTER_API_KEY in the worker's
secret environment. The adapter submits one finite subdomains capability run,
polls a durable run ID, and imports JSONL with per-source completion metadata.

The adapter deliberately excludes emails, people, breach hits, account names,
URLs, DNS brute force, reverse DNS, takeover checks, screenshots, virtual-host
probes and API-path scans. Hostnames must remain under an unexpired authorized
domain scope. IPs and ASNs are retained only as non-expanding external
relationships. A partial or failed upstream run cannot support a qualified
absence claim.

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
or admits a relation claim.

## TheBigBrother capability survey

TheBigBrother is treated as a catalogue of ideas, not a runtime dependency.
capabilities.py lists useful bounded ideas and explicitly blocks biometric
matching, breach/stealer data, camera surveillance, subscriber/SIM enrichment,
cross-service account enumeration and covert tracking. No upstream module is
invoked. The TLS probe here is a small Cognitive-native implementation with an
authorization gate, one port and a hard timeout.

## Operating contract

Every network action must be tied to a tenant, authorization reference, exact
domain suffix and expiry. The connector emits normalized evidence only; claim
validation/admission stays in the control plane. Provider output is untrusted
data, never policy or instructions.
