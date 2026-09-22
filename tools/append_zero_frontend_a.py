# -*- coding: utf-8 -*-
"""Append section 0.13 part A — frontend concept + components."""
import io

path = r'C:\Users\tim\Desktop\COGNITIVE\1\docs\architecture\donors\10-ZERO-LAYER.md'

s = u"""
## 0.13 Frontend \u2014 OSINT Workbench (\u043b\u0443\u0447\u0448\u0438\u0439 \u0432 \u043c\u0438\u0440\u0435 \u0434\u0438\u0437\u0430\u0439\u043d \u043f\u043e\u0432\u0435\u0440\u0445 \u0432\u0441\u0435\u0433\u043e)

**\u041a\u043e\u043d\u0446\u0435\u043f\u0446\u0438\u044f**: \u0435\u0434\u0438\u043d\u044b\u0439 tactical workbench, \u0433\u0434\u0435 **\u0442\u0440\u0438 \u043f\u043b\u0430\u0442\u0444\u043e\u0440\u043c\u0435\u043d\u043d\u044b\u0445 \u043c\u043e\u0434\u0443\u043b\u044f** (OSINT / \u042d\u043a\u043e\u043d\u043e\u043c\u0438\u043a\u0430 / Spec-Ops) \u043f\u0438\u0442\u0430\u044e\u0442\u0441\u044f \u0438\u0437 \u043e\u0434\u043d\u043e\u0433\u043e OSINT-\u044f\u0434\u0440\u0430. Zero-layer \u2014 \u0432\u0445\u043e\u0434\u043d\u0430\u044f \u0442\u043e\u0447\u043a\u0430 \u0432\u0441\u0435\u0433\u043e.

```
+------------------------------------------------------------------+
| COMMAND BAR: [universal seed input | type badge | conf chip]      |
| MODULE SWITCHER: ( OSINT ) ( ECONOMICS ) ( SPEC-OPS )             |
+-----------+--------------------------------------+---------------+
| HARVEST   | FORCE-GRAPH CANVAS                   | ENTITY        |
| RAIL SSE  | D3 v7 + canvas | WebGL >5k nodes    | INSPECTOR     |
| module    | node glyphs | cluster halos          | CONTACTS      |
| status    | edge width = confidence | pivot menu | PROVENANCE    |
|           |                                      | CLAIMS        |
+-----------+--------------------------------------+---------------+
| TIMELINE SCRUBBER (harvest waves | specops telemetry | replay)    |
+------------------------------------------------------------------+
```

### \u041a\u043b\u044e\u0447\u0435\u0432\u044b\u0435 \u043a\u043e\u043c\u043f\u043e\u043d\u0435\u043d\u0442\u044b
| \u041a\u043e\u043c\u043f\u043e\u043d\u0435\u043d\u0442 | \u041f\u0430\u0442\u0442\u0435\u0440\u043d-\u0434\u043e\u043d\u043e\u0440 | \u0424\u0443\u043d\u043a\u0446\u0438\u044f |
|---|---|---|
| UniversalSeedInput | \u2014 | \u0432\u0441\u0442\u0430\u0432\u044c \u0447\u0442\u043e \u0443\u0433\u043e\u0434\u043d\u043e; \u0434\u0435\u0442\u0435\u043a\u0442-\u0431\u0435\u0439\u0434\u0436 \u0434\u043e \u0437\u0430\u043f\u0443\u0441\u043a\u0430; drag&drop \u0444\u0430\u0439\u043b\u043e\u0432 |
| HarvestRail | CogniX (SSE-\u043f\u0440\u043e\u0433\u0440\u0435\u0441\u0441, KPI-timeline) | live-\u0441\u0442\u0430\u0442\u0443\u0441 \u043a\u0430\u0436\u0434\u043e\u0433\u043e \u043c\u043e\u0434\u0443\u043b\u044f; \u0441\u0447\u0451\u0442\u0447\u0438\u043a\u0438 found/\u0432\u0435\u0440\u0438\u0444\u0438\u0446\u0438\u0440\u043e\u0432\u0430\u043d\u043e; waves |
| ForceGraphCanvas | ARGUS (COP), lau-network-science | D3 v7 force-sim + canvas; WebGL-fallback; Louvain-\u0433\u0430\u043b\u043e; pivot-on-node |
| EntityInspector | OSIA (briefing), vitni (evidence) | \u0442\u0430\u0431\u044b Contacts/Provenance/Claims; confidence-\u0441\u0442\u0440\u0430\u0439\u043f\u044b; source_chain |
| TimelineScrubber | vitni (timeline), reNgine (scrollspy) | \u0440\u0435\u043f\u043b\u0435\u0439 harvest-\u0432\u043e\u043b\u043d \u0438 spec-ops \u0442\u0435\u043b\u0435\u043c\u0435\u0442\u0440\u0438\u0438 |
| OperationMatrix | Magma (\u043e\u043f\u0435\u0440\u0430\u0446\u0438\u043e\u043d\u043d\u0430\u044f \u043c\u0430\u0442\u0440\u0438\u0446\u0430) | agents \u00d7 TTP-\u0441\u0435\u0442\u043a\u0430; SSE-\u044f\u0447\u0435\u0439\u043a\u0438; RoE-\u0431\u0430\u043d\u043d\u0435\u0440; kill-switch |
| DeceptionView | Labyrinth (TUI/live log) | live-\u043b\u043e\u0433 \u0432\u0437\u0430\u0438\u043c\u043e\u0434\u0435\u0439\u0441\u0442\u0432\u0438\u0439 \u0430\u0433\u0435\u043d\u0442\u043e\u0432 \u0441 deception-\u043a\u043e\u043d\u0442\u0443\u0440\u043e\u043c |
| PhishKPI | CogniX (KPI-timeline) | CTR/TTR/report-rate SAT-\u043a\u0430\u043c\u043f\u0430\u043d\u0438\u0439 |
| EconLens | TwinMarket / votran | econ-facets \u043a\u043e\u043c\u043f\u0430\u043d\u0438\u0439; \u0441\u0442\u0440\u0435\u0441\u0441-\u0442\u0435\u0441\u0442\u044b; \u043f\u043e\u043b\u0438\u0442\u0438\u043a\u043e-\u044d\u043a\u043e\u043d\u043e\u043c\u0438\u0447\u0435\u0441\u043a\u0438\u0435 \u043f\u0440\u0435\u0434\u0438\u043a\u0442\u043e\u0440\u044b |
| ReportsPalette | OSIA (INTSUM/SITREP) | \u0433\u0435\u043d\u0435\u0440\u0430\u0446\u0438\u044f \u0434\u043e\u043a\u043b\u0430\u0434\u043e\u0432 \u0438\u0437 \u0433\u0440\u0430\u0444\u0430 |
"""

with io.open(path, 'a', encoding='utf-8') as f:
    f.write(s)

with io.open(path, 'r', encoding='utf-8') as f:
    print('lines:', len(f.readlines()))
