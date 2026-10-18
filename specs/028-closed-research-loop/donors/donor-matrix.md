# Donor Matrix

**Feature**: 028-closed-research-loop
**Verification date**: 2026-10-13

---

## Method, and its limits — read this before the table

Every row was checked against the **GitHub REST API** (repo metadata, exact-name
search), **raw.githubusercontent.com** licence files, the **HuggingFace API**, and direct
page fetches. The web-search provider was unavailable for this session, so any project
not published on GitHub could not be checked at all.

"Last activity" is GitHub `pushed_at`. Licence is the **code** licence unless stated.

**Nine names in the original candidate list do not resolve to a project that matches
the description given.** That is the single most consequential finding in this
document, and it is why the list is worth checking before it is integrated.

---

## 1. Not found — no integration is possible on the name given

| Name | What was searched | Result |
|---|---|---|
| **ranknexus** | GitHub `in:name` exact | Only `kprabhu-github/landingpage` ("ranknexus lp", 0★, **no licence**). Not a project. |
| **fuse** (RRF / rank fusion) | GitHub `in:name` exact | **No rank-fusion library named `fuse` exists.** 39 unrelated `fuse` repos: JS fuzzy search, Go filesystem, sensor fusion, ESB, functional language. |
| **QUANTA** (BM25 + vectors + graph) | GitHub `in:name`, 156 matches | **None is a retrieval stack.** Resolves to a Rust timing library, a game server, a NeurIPS fine-tuning repo, a blockchain, a PDF layout tool, a CMS. |
| **IntelShed** | GitHub, all query forms | **Zero results of any kind.** |
| **worker-browser** | GitHub `in:name` exact | **Zero repos with that name.** |
| **Stablerank** | `gousto/stablerank`, "gousto stablerank" | `gousto/stablerank` → **404**. Search → 0. |
| **OptLLM** | `microsoft/OptLLM` | **404 — the canonical repo is gone.** Only 1★ forks remain, unlicensed. |
| **lcc** (local-context-compiler) | GitHub `in:name`, 172 matches | No such project. Dominated by `drh/lcc` (a C compiler). One context-adjacent repo (`lucasmartins-ai/lcc`, context trimming for Claude Code) that does not match the description. |
| **nax** (Context Engine v2) | GitHub `in:name`, 91 matches | **No match.** |

**Verdict for all nine: REJECT — not integrable on the name given.** If any of these is
a real project the owner has in mind, it needs a URL. Nothing here may be added as a
dependency.

---

## 2. Ambiguous — the name resolves to several different projects

Integrating any of these by name would be a coin flip.

| Name | Candidates | Verdict |
|---|---|---|
| **WebFind** | `Gaurav-Wankhede/webfind` (Rust agent search, **no licence**), `BedIsHome/WebFinder` (MIT), `boltalex389/webfinder` (MIT, dormant since 2020), `jainab02/WebFinder` | **AMBIGUOUS** — needs a URL |
| **Kipi** | `assafkip/kipi` (OSINT graph platform, **Elastic License 2.0**, 75★) vs `assafkip/kipi-system` (MIT, 113★, a *different product* by the same author) | **AMBIGUOUS + licence blocker** |
| **Ontograph** | `openshuyi/ontograph-core` (MIT), `kmaurinjones/ontograph` (**no licence**), `NinePts/OntoGraph` (dormant 2019), `edgesentry/ontographia` (Apache-2.0), `julka01/OntoGraphRAG` | **AMBIGUOUS** — five unrelated projects |
| **grounded-context** | `cdevarenne/grounded-context` (MIT, 1★) vs `MValentimTech/grounded-context` (Apache-2.0, 0★) | **AMBIGUOUS** |
| **vincio** | `Ohswedd/vincio` ("context engineering platform, context packets" — matches the category) vs `vinyassystems/vincio` (collaborative workspace) | **AMBIGUOUS** — plausible candidate identified, needs confirmation |
| **AutoMix** | `automix-llm/automix` (LLM routing) vs `MZehren/Automix` (**DJ mixing**) vs `csteinmetz1/automix-toolkit` vs `sony/FxNorm-automix` (**audio**) | **AMBIGUOUS** — the intended one is probably `automix-llm/automix` |

---

## 3. Verified — with a blocker or a caveat

| Name | Upstream | Licence | Last activity | Caveat |
|---|---|---|---|---|
| **Docling** | `docling-project/docling` | MIT (code) | v2.138.0, 12 Oct 2026 | **Code and models are licensed separately.** `ibm-granite/granite-docling-258M` is Apache-2.0; `ds4sd/docling-ibm-models` returned **HTTP 401** and its licence could not be read. Review model terms before production. |
| **dedupe** | `dedupeio/dedupe` | MIT | 29 Jul 2025 | **No releases, ~14 months stale** |
| **giotto-tda** | `giotto-ai/giotto-tda` | **AGPL-3.0** | v0.6.2, 30 May 2024 | **Copyleft, and ~16 months stale.** The constitution requires a documented deployment/compliance design for AGPL — not a blocker, but a decision, not a default. |
| **Raphtory** | `Pometry/Raphtory` | **GPL-3.0** | 13 Oct 2026 | Copyleft. Active. |
| **RCL** | `IRLab-UDC/rcl` (SIGIR 2026) | **NO LICENSE FILE** | 25 Jun 2026 | **All rights reserved. There is no grant to integrate.** Methodology-only at most, via the paper. |
| **Common Crawl** | `commoncrawl.org`; tooling under the `commoncrawl` GitHub org | Code Apache-2.0/MIT; **data separately licensed** | active | **See §4. This is a data-licence blocker, not a code one.** |
| **Phoenix** | `Arize-ai/phoenix` | **Elastic License 2.0** | 13 Oct 2026 | Source-available, **not OSI open source** |
| **TorchGeo** | `torchgeo/torchgeo` (moved from `microsoft/`) | MIT (code) | 13 Oct 2026 | **Per-dataset licences for weights/data, not enumerated** |
| **OpenSanctions** | `opensanctions/opensanctions` | MIT (code) | 13 Oct 2026 | **Sanctions/PEP data is separately licensed** — terms not fetched |

### Notable URL corrections

Three intuitive guesses were wrong and are corrected here, because they would otherwise
be repeated:

- GROBID is `grobidOrg/grobid`, **not** `kermitt2/grobid` (404).
- Raphtory is `Pometry/Raphtory`, **not** `raphtory/raphtory`.
- GUDHI lives in `GUDHI/gudhi-devel`; `gudhi/gudhi` 404s.

Also: Timesketch is under `google/`, eo-learn under `sentinel-hub/` (not `NASA-AMMOS/`).

---

## 4. Common Crawl — the material finding

The Common Crawl **ToU** grants only a "limited, non-assignable, non-transferable,
non-sublicensable, non-exclusive, limited license". Three terms matter to this platform
specifically:

1. **Liability is capped at $100.**
2. **JAMS arbitration in California.**
3. **§9b requires indemnifying the Foundation** for use of Crawled Content with AI/ML/LLMs
   **including training**.

COGNITIVE is an LLM-assisted ingestion pipeline over crawled content. Clause 3 is not a
formality — it attaches to the exact use case. This needs a legal answer before
Common Crawl is used as a training or enrichment source, and that is not an engineering
decision. It is recorded as a blocker, not resolved.

---

## 5. Verified and clean

| Name | Upstream | Licence | Last activity |
|---|---|---|---|
| Browsertrix Crawler | `webrecorder/browsertrix-crawler` | **AGPL-3.0** | 8 Oct 2026 |
| Redpanda Connect | `redpanda-data/connect` | Apache-2.0 | 13 Oct 2026 |
| OpenAleph | `openaleph/openaleph` | MIT | 11 Oct 2026 |
| GROBID | `grobidOrg/grobid` | Apache-2.0 | 13 Oct 2026 |
| Splink | `moj-analytical-services/splink` | MIT | 13 Oct 2026 |
| FollowTheMoney | `opensanctions/followthemoney` | MIT | 5 Oct 2026 |
| MLflow | `mlflow/mlflow` | Apache-2.0 | 13 Oct 2026 |
| DeepEval | `confident-ai/deepeval` | Apache-2.0 | 12 Oct 2026 |
| GUDHI | `GUDHI/gudhi-devel` | MIT | 12 Oct 2026 |
| scikit-tda | `scikit-tda/scikit-tda` | MIT | 3 Aug 2026 |
| Graphiti | `getzep/graphiti` | Apache-2.0 | 13 Oct 2026 |
| H3 | `uber/h3` | Apache-2.0 | 13 Oct 2026 |
| DuckDB Spatial | `duckdb/duckdb-spatial` | MIT | 13 Oct 2026 |
| eo-learn | `sentinel-hub/eo-learn` | MIT | 9 Sep 2026 |
| Sriti Core | `sriti-ai/sriti-core` | Apache-2.0 | 17 Sep 2026 — **11★, immature** |
| Timesketch | `google/timesketch` | Apache-2.0 | 13 Oct 2026 |
| MISP | `MISP/MISP` | **AGPL-3.0** | 13 Oct 2026 |
| OpenCTI | `OpenCTI-Platform/opencti` | Apache-2.0 | 13 Oct 2026 |
| yente | `opensanctions/yente` | MIT | 12 Oct 2026 |

Stale but real: **FrugalGPT** `stanford-futuredata/FrugalGPT` (Apache-2.0, 10 Feb 2025,
~20 months, no releases) · **RouteLLM** `lm-sys/RouteLLM` (Apache-2.0, 10 Aug 2024,
~26 months, no releases).

---

## 6. Integration decisions

The governing constraint is the audit, not the donor list. `audit/current-state-audit.md`
§3 shows the platform currently has **three observation producers that bypass its own
gate**, **four identity schemes**, a **random UUID on one of them**, and **spans that
are discarded before they reach a finding**.

Adding producers multiplies exactly the violations that are already there.

| Decision | Candidates | Why |
|---|---|---|
| **REJECT** | ranknexus, fuse, QUANTA, IntelShed, worker-browser, Stablerank, OptLLM, lcc, nax | No project by that name |
| **BLOCKED — needs a URL** | WebFind, Ontograph, grounded-context, vincio | Name resolves to several unrelated projects |
| **BLOCKED — licence** | Common Crawl data | Indemnity clause covering the platform's own use case |
| **BLOCKED — no grant** | RCL | No LICENSE file |
| **METHODOLOGY ONLY** | Microsoft GraphRAG, FrugalGPT, RouteLLM, AutoMix (if confirmed), OpenCTI, Timesketch | Patterns to study; generated summaries are not evidence |
| **DEFERRED — after contracts hold** | Docling, GROBID, Splink, Redpanda Connect, H3, DuckDB Spatial, OpenAleph, Browsertrix | All are individually sound. None should receive data while the gate and identity defects stand. |

---

## 7. The eight claims that must not be assumed

Each was checked against what the measurement actually supports:

| Claim | Status | What is actually true |
|---|---|---|
| "RRF is the only correct fusion" | **Unproven** | No retrieval benchmark exists for this platform. Fusion choice depends on the query and the eval set. |
| "Never normalise scores" | **Half true** | Keeping vectors is right. Collapsing different uncertainty semantics into one scalar is what is wrong. `services/query_planner.py` already retains components — its tests assert exactly this. |
| "The graph only ever expands the frontier" | **Unproven as an absolute** | Expansion vs. ranking-feature is an empirical question requiring a golden query set. None exists. |
| "TDA is noise-independent / automatically reliable" | **False** | Stability depends on correct preconditions, scale, filtration and noise level. No robustness measurement exists. |
| "FrugalGPT/RouteLLM save 96.8% / 44.1% / 90%+ / <1%" | **Third-party figures** | Measured on *their* datasets. They are not acceptance evidence here, and both repos are 20–26 months stale. |
| "LLM is unnecessary in Discovery" | **A hypothesis** | LLM-generated queries are a trade-off to be measured, not a philosophical prohibition. |
| "LLM-as-Judge becomes deterministic after formalising the narrative" | **False** | Formalising a narrative does not make a model deterministic. It makes the *prompt* stable. Sampling remains. |
| "A library existing means a production capability exists" | **Demonstrably false here** | The audit found 13 capabilities marked complete with no production caller — including a TDA plane that has never run outside tests. |

---

## 8. Re-verification

Licences and maintenance status change. Before any of §6 is acted on:

```powershell
# licence
curl -sL https://raw.githubusercontent.com/<org>/<repo>/<ref>/LICENSE | Select-Object -First 3
# maintenance
curl -sL https://api.github.com/repos/<org>/<repo> | ConvertFrom-Json | Select-Object pushed_at, license
```

Re-run for every row at the moment of integration, not from this document. This is a
snapshot dated 2026-10-13.