# Parser Contract (NetForensicAI pattern)

A unified parser interface for deterministic finding extraction (FR-010, US4). Implemented by `apps/interpretation/parsers/registry.py`.

## ParserAdapter

```text
class ParserAdapter:
    def can_parse(self, artifact) -> bool: ...
    def parse(self, artifact) -> list[Finding]: ...
```

- `can_parse(artifact)` — content-type / shape detection (HTML, JSON, CSV, PDF, Email, Archive, ...).
- `parse(artifact)` — deterministic, isolated normalization to `Finding`s (segments/mentions), never raw document SQL/execution.
- Findings carry offsets, language hints, and versioned extractor provenance.

## Rules

- Parsers are selected via a registry, never hard-coded dispatch in domain logic (C-5).
- Heavy/unsafe parsers (PDF, OCR, archives) run in isolated worker classes with CPU/memory/timeout/archive limits (C-7).
- A malformed parser or artifact must never take down the pipeline — registry falls back to plain text and dead-letter/quarantine on repeated failure (FR-028).
- Same input → same output (deterministic, reproducible evidence).
- No vendor-specific parser types cross application boundaries; adapter is the only interface consumers see.