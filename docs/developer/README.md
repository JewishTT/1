# Developer showcase

This is the entry point for people building, reviewing, operating, or extending COGNITIVE. It links the machine-generated architecture model to the real workflows that keep the repository reproducible.

## Start here

| Surface | What it is for |
| --- | --- |
| AI-native workflow | [ai-native-workflow.md](ai-native-workflow.md): spec-first, context-aware human/agent development loop and review contract. |
| Service operations | [operations.md](operations.md): local stack, health, migrations, telemetry truthfulness, recovery and acceptance. |
| Source onboarding | [source-onboarding.md](source-onboarding.md): add a public or explicitly authorized source without bypassing policy. |
| Platform model | [../platform/index.md](../platform/index.md): generated inventory of modules, APIs, events, imports, tests and capabilities. |
| Verified gaps | [../platform/gaps.md](../platform/gaps.md): machine-checked defects and evidence proving they remain open. |
| Architecture | [../architecture/overview.md](../architecture/overview.md): runtime flow, stores, event backbone and projection boundaries. |
| Contributing | [../CONTRIBUTING.md](../CONTRIBUTING.md): repository conventions and standard validation commands. |

## Developer command deck

    uv sync --locked --all-packages --all-groups
    make doctor
    make hygiene
    make test-fast
    make ui-check
    make platform-model-check

For a real local stack:

    make up
    uv run python -m bench.run --scenario smoke-val
    make down

Live acceptance is intentionally separate from hermetic tests. It depends on Docker, provider reachability, and sometimes credentials. A skipped or unavailable live proof is not a pass.

## Runtime map

    Investigation context → Discovery planner → Policy and approval
        → Dispatcher and bounded workers → ArtifactSink
        → Immutable raw object + Capture/Observation → Redpanda
        → Interpretation and admission → PostgreSQL canonical state
        → Search, graph, analytics and temporal projections
        → Findings and analyst review → Feedback and replanning

This is the target end-to-end shape, not a blanket assertion that every provider or every arrow is production-complete. The generated reachability, maturity, and gaps pages distinguish wired execution from test-only, orphaned, and unfinished capabilities.

## Current development evidence

- Context-to-public-discovery is implemented as a first governed vertical slice in PR #7; its current case execution provider is SearXNG.
- The repository source catalogue is broader than the paths proven through the governed case lifecycle. Count a source as integrated only after policy, runtime, parser, egress, durable evidence persistence, replay, and live read-back have been demonstrated.
- The service reports some operational metrics and DLQ capabilities as unavailable until their tenant-scoped backends are connected. This is intentional; fabricated status is not a developer showcase.
- Never infer exhaustive Internet coverage. Public indexes, archives, licensed datasets, provider limits, unindexed content, and legal restrictions create measurable coverage gaps.

## Review-ready evidence

Every PR should state the changed runtime path, tenant/security implications, tests run, live checks skipped and why, screenshot artifact references for UI work, database migration compatibility, and known residual gaps. The PR template encodes this minimum.
