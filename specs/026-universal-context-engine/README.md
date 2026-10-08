# 026 — Universal Context Engine

A process-centric context engine for investigations of any abstraction: arbitrary NL goal,
arbitrary domain, one code path.

| Document | Contents |
|---|---|
| [input.md](input.md) | verified audit: what exists, gates, missing links, unimplemented services |
| [spec.md](spec.md) | requirements FR-001…FR-083 |
| [plan.md](plan.md) | phases F1…F7 with gates and ordering rationale |
| [tasks.md](tasks.md) | task list with current status |

**Sole success criterion:** the analyst confirms the data they see in the console.

**Constitution:** `.specify/memory/constitution.md` supersedes this document and every other
practice. Where any of these documents contradicts it, the constitution wins and the
discrepancy is a defect in the document, not in the constitution.

## The problem in one paragraph

The platform collects 145 sources, resolves entities, accounts for evidence independence, and
computes topology — and has no Context Graph, no projection operator, and no closed
investigation loop. Because the engine does not exist, the vocabulary was closed to
compensate: 53 enumerated entity types, a SQL CHECK enforcing them, a 14-predicate cue list.
A closed apparatus on an open-world problem degrades into a flat pile of documents around one
source, which is what the previous build produced.

## The shape

```
NL → QueryIntent ──► π(Q, W) ──► ContextGraph + Gap[]
                       ▲                │
                       └── invariants ◄── obligations ◄── acquisition
```

`π` is one projection operator over ten domain-independent primitives. Any question is a
composition of them; no domain is named inside the engine.
