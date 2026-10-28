# AI-native dynamic documentation and semantic graph

Status: **implementation contract** for the generated documentation workflow.

The repository already has a useful structural model in `platform_model/build.py` and `docs/platform/`. Keep it: it remains the authority for component counts, import resolution, reachability, maturity, gaps and existing capability views. The semantic graph introduced by `tools/semantic_docgraph.py` is a complementary navigation and traceability layer, not a replacement for that model.

## Design rule

Documentation is a versioned engineering interface. It must let a new engineer or an AI coding agent answer these questions with short, reproducible queries:

1. What is the intended behaviour and which invariant or acceptance criterion governs it?
2. Which component, route, event, store and public symbol implement that behaviour?
3. Which code imports, calls or publishes that component, and what is its path into the production application?
4. Which tests exercise the claimed behaviour rather than merely import the module?
5. What evidence is current, what is heuristic, and what still requires a live-stack check?

A source file being present, a symbol being declared, or a test importing it does **not** prove runtime reachability or behavioural correctness. Edges and status values must preserve that distinction.

## Authoritative sources and derived views

| Source | Authority | Derived links |
|---|---|---|
| `specs/*/spec.md`, `plan.md`, `tasks.md` | Product intent, constraints, acceptance criteria, work state | Spec-to-code and acceptance-to-test coverage |
| `docs/adr/` | Recorded architectural decisions and rationale | Decision-to-component / contract links |
| `apps/shared/contracts/`, event schemas and `EVENT_CATALOG` | Wire/domain contracts and event vocabulary | Contract, producer/consumer and version links |
| Application entrypoints, routers, workers and dependency wiring | Actual code topology | Route, module, call and import graph |
| Unit, contract, integration and E2E tests | Executed assertions and test boundaries | Test-to-behaviour edges, with test type kept explicit |
| `platform_model/` and `docs/platform/` | Existing platform inventory, reachability and maturity model | Complementary inventory summaries and documented known gaps |
| `apps/webapp/src/` and Playwright scripts | UI navigation, surfaces, states and responsive assertions | Route-to-screen, screen-to-component and visual evidence |

Generated documents must never become competing, hand-maintained sources of truth.

## Semantic graph

Run from the repository root:

```bash
# Build a local graph and a compact module-level context packet.
python tools/semantic_docgraph.py --output artifacts/semantic-docgraph.json
python tools/semantic_docgraph.py --context apps/control-plane/context_engine/engine.py

# Strict inventory/syntax check (requires Node dependencies and the Rust toolchain).
python tools/semantic_docgraph.py --check --output artifacts/semantic-docgraph.json

# Python AST unit tests without booting the service stack.
python -m unittest apps/shared/tests/contract/test_semantic_docgraph.py
```

The graph records Python/TypeScript/JavaScript/Rust AST symbols, imports and locally resolvable calls, candidate HTTP route declarations, catalogued event types, docs/spec links, configuration files and root-level source files. CSS/SCSS/HTML and protocol/SQL files receive source inventory nodes, while parser-backed languages expose AST symbols. JavaScript module files (`.mjs`/`.cjs`) are included in the TypeScript compiler parser sweep. Node IDs are stable paths/symbol names; file content hashes make staleness inspectable. Relationships carry source paths and line numbers whenever the parser exposes them.

The TypeScript compiler API is used for TS/TSX/JS/JSX syntax trees. Rust syntax is parsed with `syn`. Python uses the standard-library `ast` module. Parser failures are explicit findings rather than silently degraded regex output. Raw imports are recorded for all three languages; first-party module-edge resolution currently covers Python imports and relative TypeScript/JavaScript imports. Cargo crate/module alias resolution remains a visible follow-up rather than a guessed edge. The strict check inventories tracked source-like files under `apps/`, `bench/`, `benchmarks/`, `tools/`, `platform_model/`, `implementation/` and executable/schema examples under `specs/`, plus tracked source files at the repository root. It also inventories first-party configuration in application, deployment, contract, specification, agent and GitHub workflow directories. Vendored donors, generated build trees, caches, installed dependencies and known temporary root directories are explicitly excluded. `--check` compares the source inventory with `git ls-files` and fails if a tracked source candidate appears outside the declared scan roots. The coverage percentage applies to that declared scope, not to every file in the repository.

## Evidence labels

Every report and agent response should distinguish these evidence levels:

- **Static declaration** — a definition, route, event name, config key or import exists in the checked-in source.
- **Repository linkage** — source-backed imports, calls, references or known entrypoint wiring connect elements.
- **Tested behaviour** — a named test executes an assertion for the relevant acceptance criterion.
- **Runtime verified** — the behaviour was exercised against the actual configured service stack and dependencies.
- **Unverified / heuristic** — the current evidence does not justify a stronger claim.

A test import is not a behavioural assertion. An event name in a catalog is not proof of a producer, consumer, broker registration or durable handler. A route decorator is not proof that the application router mounts it. A frontend API client is not proof that the endpoint is packaged in the production wheel.

## Agent workflow

1. Start at this file and `AGENTS.md`. Read only the domain spec, relevant ADRs and generated model pages required for the current task.
2. Use `python tools/semantic_docgraph.py --context <path>` to gather a compact symbol/relationship packet for the likely implementation.
3. Follow relevant links in `docs/platform/golden-path.md`, `gaps.md`, `reachability.md`, `maturity.md`, and the owning domain's spec.
4. Turn each requirement into an acceptance criterion and point it at an executable test. Do not infer completion from symbol counts.
5. Change implementation, tests and any source-of-truth specification/ADR together. Regenerate the legacy model when its scan roots changed.
6. Run relevant contract tests, package/build checks and (for UI work) the Playwright screenshot sweeps. Record commands, commit SHA, service prerequisites and artifact links.
7. Review the graph diff for missing symbols, stale links, parser errors and unexpected relationship changes.

For focused investigations, ask the graph for one component at a time; do not inject the entire repository into the model context. When a dependency or runtime assertion remains unverified, make that explicit instead of promoting a static edge to a fact.

## Required quality gates

- Every in-scope source file has exactly one module inventory entry.
- No source syntax/parser failures are silently dropped.
- Internal documentation links resolve or are listed as broken links.
- Semantic relationships carry source evidence; inferred relationships are labelled as inferred.
- Specs, tests, and code have explicit coverage relationships where a claim is made. No blanket "100% behavioural coverage" claim is made from file inventory.
- `docs/platform/` continues to pass the existing `platform_model.build --check` / contract suite.
- Agent instructions remain short and route to relevant detailed material; they must not duplicate the entire architecture.

## Design references

For the repository-specific findings and prioritized gaps, see the [architecture review](architecture-review-2026-10.md). This process adapts intent alignment, domain decomposition and spec-grounded verification ideas from the [Harness Engineering Playbook](https://github.com/lipingtababa/harness-engineering-playbook), especially its [intent-alignment chapter](https://github.com/lipingtababa/harness-engineering-playbook/blob/gitbook/en/chapters/02a-intent-alignment.md), [verification chapter](https://github.com/lipingtababa/harness-engineering-playbook/blob/gitbook/en/chapters/03-verification.md) and [agent-ready PRD architecture](https://github.com/lipingtababa/harness-engineering-playbook/blob/gitbook/en/chapters/prd-architecture/agent-ready-prd-architecture.md). The playbook itself marks parts of its content as an early draft; its ideas are design inputs, not authoritative facts about this repository.
