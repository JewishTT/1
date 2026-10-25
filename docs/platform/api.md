# HTTP API surface

Extracted from `@router.<method>` decorators in `apps/control-plane/api/routes/`.

## `connectors` — `apps/control-plane/api/routes/connectors.py`

| Method | Path | Line |
|---|---|---|
| POST | `/register` | 67 |
| POST | `/{name}/activate` | 79 |
| GET | `/recon-plans` | 98 |
| POST | `/{name}/recon-plans` | 103 |

## `discovery` — `apps/control-plane/api/routes/discovery.py`

| Method | Path | Line |
|---|---|---|
| POST | `/run` | 286 |

## `dossier` — `apps/control-plane/api/routes/dossier.py`

| Method | Path | Line |
|---|---|---|
| POST | `/enrich` | 87 |
| GET | `/{entity_ref}` | 160 |

## `entities` — `apps/control-plane/api/routes/entities.py`

| Method | Path | Line |
|---|---|---|
| GET | `/{entity_id}/worldline` | 556 |
| GET | `/{entity_id}/admission` | 593 |
| GET | `/{entity_id}/stream` | 636 |
| GET | `/{entity_id}/invariant` | 671 |
| GET | `/{entity_id}/materialization-status` | 704 |
| GET | `/{entity_id}/temporal-history` | 750 |
| GET | `/{entity_id}/temporal-history/at` | 763 |
| POST | `/{entity_id}/temporal-materializations` | 781 |
| GET | `/{entity_id}/temporal-history/current` | 814 |
| GET | `/{entity_id}/temporal-features` | 830 |
| GET | `/temporal-materializations/health` | 849 |
| GET | `/temporal-materializations/{run_id}` | 859 |
| POST | `/{entity_id}/correlations` | 870 |
| GET | `/graph` | 1014 |
| GET | `/{entity_id}` | 1153 |
| GET | `/{entity_id}/correlations` | 1182 |
| POST | `/{target_id}/review` | 1204 |
| GET | `/{target_id}/reviews` | 1233 |
| POST | `/{entity_id}/cc-temporality` | 1242 |

## `fabric` — `apps/control-plane/api/routes/fabric.py`

| Method | Path | Line |
|---|---|---|
| GET | `/badges` | 205 |
| GET | `/engines` | 214 |
| GET | `/engines/{engine}` | 219 |
| POST | `/engines/select` | 229 |
| POST | `/engines/match` | 251 |
| POST | `/tool/badge` | 259 |
| POST | `/tool/reobserve` | 275 |
| POST | `/tool/etag` | 280 |
| POST | `/modifier/match` | 293 |
| POST | `/modifier/dedupe-links` | 298 |
| POST | `/modifier/urgency` | 315 |
| POST | `/search` | 331 |
| GET | `/search/badge` | 360 |
| GET | `/frontier/status` | 386 |
| POST | `/frontier/enqueue` | 399 |
| POST | `/frontier/pop` | 426 |
| POST | `/frontier/{frontier_id}/complete` | 437 |
| POST | `/frontier/{frontier_id}/retry` | 445 |
| POST | `/frontier/{frontier_id}/cancel` | 455 |
| POST | `/frontier/cooldown` | 463 |
| GET | `/pools` | 476 |
| POST | `/pools/{kind}/fail` | 491 |
| POST | `/partitions/resolve` | 504 |
| POST | `/backpressure/verdict` | 521 |
| POST | `/throttle/rate` | 547 |
| POST | `/bulk/plan` | 566 |
| GET | `/bulk/cdx` | 584 |
| POST | `/bulk/replay` | 633 |

## `findings` — `apps/control-plane/api/routes/findings.py`

| Method | Path | Line |
|---|---|---|
| GET | `/{finding_id}` | 85 |
| GET | `/{finding_id}/lineage` | 97 |

## `investigation_context` — `apps/control-plane/api/routes/investigation_context.py`

| Method | Path | Line |
|---|---|---|
| POST | `/{investigation_id}/context` | 108 |
| GET | `/{investigation_id}/context` | 147 |
| GET | `/{investigation_id}/context/revisions` | 170 |
| GET | `/{investigation_id}/context/frontier` | 185 |
| POST | `/{investigation_id}/context/ingest` | 203 |
| POST | `/{investigation_id}/context/obligations/{obligation_id}/actions/{action_id}/attempts` | 255 |
| POST | `/{investigation_id}/context/replay` | 295 |

## `investigations` — `apps/control-plane/api/routes/investigations.py`

| Method | Path | Line |
|---|---|---|
| GET | `/{investigation_id}` | 247 |
| PATCH | `/{investigation_id}` | 257 |
| POST | `/{investigation_id}/pause` | 292 |
| POST | `/{investigation_id}/resume` | 304 |
| POST | `/{investigation_id}/complete` | 316 |
| POST | `/{investigation_id}/archive` | 328 |

## `manual_assertions` — `apps/control-plane/api/routes/manual_assertions.py`

| Method | Path | Line |
|---|---|---|
| POST | `/investigations/{investigation_id}/assertions/entity` | 135 |
| POST | `/investigations/{investigation_id}/assertions/relation` | 221 |
| GET | `/investigations/{investigation_id}/assertions` | 360 |
| POST | `/investigations/{investigation_id}/context/ensure` | 404 |

## `metrics` — `apps/control-plane/api/routes/metrics.py`

| Method | Path | Line |
|---|---|---|
| GET | `/pools` | 52 |

## `network` — `apps/control-plane/api/routes/network.py`

| Method | Path | Line |
|---|---|---|
| POST | `/measures` | 129 |
| POST | `/communities` | 143 |
| POST | `/hypergraph` | 163 |
| POST | `/temporal` | 180 |
| POST | `/diagram-features` | 221 |
| POST | `/phodms` | 306 |

## `platform` — `apps/control-plane/api/routes/platform.py`

| Method | Path | Line |
|---|---|---|
| GET | `/health` | 92 |
| GET | `/sources` | 105 |
| POST | `/tick` | 122 |

## `quarantine` — `apps/control-plane/api/routes/quarantine.py`

| Method | Path | Line |
|---|---|---|
| GET | `/{record_id}` | 40 |
| POST | `/{record_id}/replay` | 48 |
| POST | `/{record_id}/re-evaluate` | 56 |

## `research_cases` — `apps/control-plane/api/routes/research_cases.py`

| Method | Path | Line |
|---|---|---|
| GET | `/{case_id}` | 161 |
| PATCH | `/{case_id}/scope` | 174 |
| POST | `/{case_id}/approve` | 207 |
| POST | `/{case_id}/plan` | 230 |
| GET | `/{case_id}/actions` | 249 |
| POST | `/{case_id}/actions/approve` | 262 |
| POST | `/{case_id}/run` | 286 |
| POST | `/{case_id}/pause` | 312 |
| GET | `/{case_id}/obligations` | 328 |
| GET | `/{case_id}/coverage` | 383 |
| GET | `/{case_id}/claims` | 396 |
| GET | `/{case_id}/timeline` | 411 |
| GET | `/{case_id}/graph` | 431 |
| POST | `/{case_id}/identity-reviews` | 449 |
| POST | `/{case_id}/claim-disputes` | 473 |
| POST | `/{case_id}/report` | 497 |
| POST | `/{case_id}/close` | 519 |
| POST | `/{case_id}/retention-action` | 541 |

## `resolutions` — `apps/control-plane/api/routes/resolutions.py`

| Method | Path | Line |
|---|---|---|
| GET | `/{investigation_id}/resolutions` | 53 |
| POST | `/{investigation_id}/resolutions/decide` | 71 |

## `science_causal` — `apps/control-plane/api/routes/science_causal.py`

| Method | Path | Line |
|---|---|---|
| POST | `/classify` | 53 |
| POST | `/models` | 75 |
| GET | `/models/{model_id}` | 94 |
| GET | `/models` | 108 |

## `science_claims` — `apps/control-plane/api/routes/science_claims.py`

| Method | Path | Line |
|---|---|---|
| POST | `/claims` | 98 |
| GET | `/claims/{claim_id}` | 119 |
| GET | `/claims` | 127 |
| POST | `/claims/{claim_id}/status` | 132 |
| POST | `/calibration` | 153 |
| GET | `/calibration/{model_id}` | 173 |

## `science_hypotheses` — `apps/control-plane/api/routes/science_hypotheses.py`

| Method | Path | Line |
|---|---|---|
| POST | `/{hypothesis_id}/evidence` | 75 |
| POST | `/{hypothesis_id}/discard` | 98 |
| POST | `/plan` | 125 |
| GET | `/coverage` | 155 |

## `science_review` — `apps/control-plane/api/routes/science_review.py`

| Method | Path | Line |
|---|---|---|
| GET | `/{claim_id}` | 59 |
| POST | `/{claim_id}/comment` | 87 |
| POST | `/{claim_id}/status` | 104 |
| POST | `/{claim_id}/ladder` | 139 |

## `science_robustness` — `apps/control-plane/api/routes/science_robustness.py`

| Method | Path | Line |
|---|---|---|
| POST | `/robustness` | 95 |
| GET | `/robustness` | 117 |
| GET | `/robustness/{report_id}` | 122 |
| POST | `/experiments` | 130 |
| GET | `/experiments` | 150 |
| POST | `/experiments/reproduce` | 166 |

## `science_structure` — `apps/control-plane/api/routes/science_structure.py`

| Method | Path | Line |
|---|---|---|
| POST | `/analyze` | 36 |
| GET | `/results/{result_id}` | 67 |

## `science_temporal` — `apps/control-plane/api/routes/science_temporal.py`

| Method | Path | Line |
|---|---|---|
| POST | `/series` | 58 |
| POST | `/change-points` | 69 |
| GET | `/series/{series_id}` | 91 |

## `search_rebuild` — `apps/control-plane/api/routes/search_rebuild.py`

| Method | Path | Line |
|---|---|---|
| POST | `/rebuild` | 206 |

## `specops_counterintel` — `apps/control-plane/api/routes/specops_counterintel.py`

| Method | Path | Line |
|---|---|---|
| GET | `/subjects/{subject_id}` | 25 |

## `specops_emulation` — `apps/control-plane/api/routes/specops_emulation.py`

| Method | Path | Line |
|---|---|---|
| GET | `/plans` | 71 |
| GET | `/plans/{plan_id}` | 79 |
| POST | `/operations` | 105 |
| GET | `/operations/{operation_id}` | 124 |

## `specops_engagement` — `apps/control-plane/api/routes/specops_engagement.py`

| Method | Path | Line |
|---|---|---|
| GET | `/taxonomy` | 93 |
| GET | `/board` | 110 |
| GET | `/campaigns/{campaign_id}` | 121 |
| GET | `/timeline` | 136 |
| GET | `/subjects` | 158 |
| POST | `/events` | 169 |
| POST | `/anonymize` | 208 |

## `specops_forensics` — `apps/control-plane/api/routes/specops_forensics.py`

| Method | Path | Line |
|---|---|---|
| GET | `/operations/{operation_id}` | 26 |

## `specops_ghostline` — `apps/control-plane/api/routes/specops_ghostline.py`

| Method | Path | Line |
|---|---|---|
| GET | `/status` | 139 |
| GET | `/playbooks` | 149 |
| GET | `/playbooks/{playbook_id}` | 163 |
| POST | `/playbooks/reload` | 173 |
| POST | `/playbooks/{playbook_id}/simulate` | 180 |
| GET | `/voices` | 204 |
| POST | `/voices` | 210 |
| POST | `/voices/clone` | 233 |
| DELETE | `/voices/{voice_id}` | 257 |
| POST | `/runtime/start` | 277 |
| POST | `/runtime/stop` | 300 |
| POST | `/calls` | 314 |
| GET | `/calls` | 348 |
| GET | `/calls/{call_id}` | 356 |
| POST | `/calls/{call_id}/turns` | 366 |
| POST | `/calls/{call_id}/complete` | 395 |
| GET | `/analytics` | 415 |
| GET | `/analytics/export` | 422 |

## `specops_phishing` — `apps/control-plane/api/routes/specops_phishing.py`

| Method | Path | Line |
|---|---|---|
| POST | `/campaigns` | 58 |
| POST | `/campaigns/{campaign_id}/launch` | 73 |
| GET | `/campaigns/{campaign_id}` | 92 |

## `specops_roe` — `apps/control-plane/api/routes/specops_roe.py`

| Method | Path | Line |
|---|---|---|
| GET | `/{roe_id}` | 71 |

## `specops_social` — `apps/control-plane/api/routes/specops_social.py`

| Method | Path | Line |
|---|---|---|
| POST | `/projections` | 32 |

## `temporal_materializations` — `apps/control-plane/api/routes/temporal_materializations.py`

| Method | Path | Line |
|---|---|---|
| GET | `/temporal-materializations/health` | 11 |
| GET | `/temporal-materializations/{run_id}/audit` | 16 |
| GET | `/temporal-materializations/{run_id}` | 21 |

## `tools` — `apps/control-plane/api/routes/tools.py`

| Method | Path | Line |
|---|---|---|
| POST | `/{tool_id}/enqueue` | 38 |
