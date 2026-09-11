# Parser contract (NetForensicAI pattern)

Authoritative contract: [`specs/002-donor-pattern-integration/contracts/parser.md`](../../../specs/002-donor-pattern-integration/contracts/parser.md).

Unified parser interface `can_parse(artifact) -> bool` / `parse(artifact) -> list[Finding]`
(FR-010): deterministic findings, isolated heavy/unsafe parsers (C-7).
Implementation: `apps/interpretation/parsers/registry.py::ParserAdapter` +
`ParserRegistry.register_adapter/can_parse/parse_artifact`.