# Contracts

Phase 1 output — the stable interface contracts of the donor-pattern integration. Implementation must preserve these; consumers must program only against these. These extend the feature 001 contracts (`contracts/README.md` in `001-global-osint-platform`).

| File | Contract | Owner | Donor |
|---|---|---|---|
| [statement.md](./statement.md) | Statement record shape (dataset_id, first/last seen, original_value, extraction_version, provenance) | interpretation, admission, projection | FollowTheMoney |
| [correlation-review.md](./correlation-review.md) | CorrelationEdge possible_match + ReviewDecision ACCEPT/REJECT/UNCERTAIN | admission, control-plane, projection | OpenOSINT / Vitni |
| [connector.md](./connector.md) | Connector registry + AcquisitionWorker compliance | acquisition, control-plane | SpiderFoot / reNgine |
| [parser.md](./parser.md) | ParserAdapter `can_parse`/`parse` interface | interpretation | NetForensicAI |
| [ontology-pack.md](./ontology-pack.md) | OntologyPack versioned schema pack | shared, interpretation, admission | kafSIEM |

## Rules

- No vendor-specific types cross application boundaries (Constitution C-4/C-5).
- Donor patterns are adopted as contracts only — no donor code, no donor dependencies (FR-014).
- Correlation/review/ontology are projection/event artifacts, never sources of truth (I-4/I-12).
- Contract changes require a new version or ADR — never a silent break (Constitution Governance).