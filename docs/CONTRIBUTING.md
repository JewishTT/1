# Contributing to COGNITIVE

## Repo layout

Monorepo: `apps/` (control-plane, acquisition, interpretation, admission,
projection, feedback, shared, webapp, deploy), `bench/`, `docs/`, `specs/`.

## Tooling

- Python: `uv` + `pytest`, lint/format via `ruff`.
- Rust (`apps/acquisition`): `cargo`, `cargo fmt`/`clippy`.
- Frontend (`apps/webapp`): Node 20+ / pnpm, Vitest, TypeScript strict.

## Convention: tests first

Tasks in `specs/*/tasks.md` specify tests that must be written first and
**fail before implementation lands** (Constitution SC-005). When working on a
task, add the invariant/unit/integration tests, see them fail, then implement.

## Gateway constraints (never break)

These contracts are fixed and must not regress:

- `apps/shared/events/event_envelope.proto` — envelope + topic catalog.
- `storage` `s3://knowledge/raw/{tenant}/{ym}/{sha256}` content addressing.
- Domain invariants I-1…I-12 (see `docs/architecture/overview.md`).
- Acquisition worker, graph abstraction, and utility scorer contracts.

Architecture decisions are captured in `docs/adr/` — new trade-offs get an ADR.

## Validation

Run the whole gate before finishing a change:

```bash
# per-app suites
uv run --project apps/<app> pytest apps/<app>/tests -q
cargo test --workspace                                    # apps/acquisition
# webapp
cd apps/webapp && pnpm vitest run && pnpm tsc
# end-to-end on a clean stack
docker compose -f apps/deploy/docker-compose.yml up -d
uv run python -m bench.run --scenario smoke-val
```

Final validation and cleanup: `bench/run.py --scenario smoke-val` must print
`RESULT: PASS` on a clean compose stack (T075).

## Code style

- No comments unless they explain intent; keep them minimal.
- Follow each app's existing patterns (imports, naming, typing).
- Ruff (Python) and prettier + tsc (TS) must be clean.