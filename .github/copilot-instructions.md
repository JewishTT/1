# Copilot instructions

Read AGENTS.md, .specify/memory/constitution.md, and the generated platform model before changing platform behavior.

- Trace a real path through policy, runtime, ArtifactSink, events, consumers, and projections. Do not infer production support from a catalogue entry or mock.
- Add a failing test before implementation; preserve tenant isolation, source authorization, operator approval, budgets, egress, and evidence lineage.
- Prefer maintained project libraries/adapters over new mini-frameworks. Verify license and package boundaries before reuse.
- Unknown telemetry is null/unavailable. Never create sample counters, fake DLQ records, or synthetic green health.
- Operational schema changes use Alembic migrations only. Keep production requests away from create_all().
- Regenerate generated docs with uv run python -m platform_model.build; never hand-edit generated output.
- Keep source acquisition public or explicitly authorized. Respect source policies, provider terms, rate limits, retention and authorization.
- Run focused tests, make hygiene, platform-model checks, and relevant live acceptance/screenshot workflows. State clearly what was not run.
