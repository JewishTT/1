## Change summary

<!-- What changed and why? -->

## Architecture and runtime path

- [ ] Relevant constitution/spec/ADR reviewed.
- [ ] Runtime path traced beyond catalogue or mock declarations.
- [ ] Tenant boundaries, authorization, budgets, egress and evidence lineage preserved.
- [ ] Architecture docs / ADR updated when the design changes.

## Verification

- [ ] Regression/contract tests added and run.
- [ ] make hygiene passes.
- [ ] uv run python -m platform_model.build --check passes.
- [ ] Relevant app tests pass.
- [ ] UI screenshot tests inspected for UI changes.
- [ ] Live/stack tests run when applicable; missing infra/provider credentials are stated.

## Operational honesty

- [ ] No fabricated metrics, fake health, seeded production records, or unlabelled mocks.
- [ ] Unavailable integrations are explicitly represented as unavailable.
- [ ] Generated artifacts, local output, secrets and temporary files are not committed.

## Evidence

<!-- Paste commands, results, CI artifact links, and known limitations. -->
