# -*- coding: utf-8 -*-
"""Fix corrupted tail of 10-ZERO-LAYER.md and write clean specops section."""
import io

path = r'C:\Users\tim\Desktop\COGNITIVE\1\docs\architecture\donors\10-ZERO-LAYER.md'

with io.open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Keep everything up to and including line 334 (the NONMOCK paragraph)
head = lines[:334]

clean_tail = u"""
### 0.10.1 caldera \u2014 Apache-2.0 \u2192 P1 (Rust binding, direct import)
- `apps/specops/caldera/src/lib.rs` \u2014 pyo3 binding \u043a caldera.core
- planners \u2192 `apps/science/scenarios/planning/scenario_dsl.rs` (Diamond + atoms + expected-telemetry + ROE)
- Operation \u2192 `app_specops_operation_created` event \u043d\u0430 `specops.telemetry` Kafka topic
- agents \u2192 `apps/specops/agents/` (native Rust agent-runtime, Sandcat-compatible \u043f\u0440\u043e\u0442\u043e\u043a\u043e\u043b)

### 0.10.2 ael \u2014 Apache-2.0 \u2192 P1 (direct YAML parser)
- `apps/specops/scenarios/importers/ael.py` \u2014 \u043f\u0430\u0440\u0441\u0435\u0440 AEL YAML \u2192 scenario DSL v2
- `apps/science/scenarios/atoms/ael_registry` \u2014 attack-atoms registry \u0441 cross-ref \u043d\u0430 zero-layer harvesters

### 0.10.3 adversary_emulation_library \u2014 Apache-2.0 \u2192 P1 (direct import)
- `apps/science/scenarios/atoms/` \u2014 full+micro plans \u043a\u0430\u043a scenario bundles
- \u043a\u0430\u0436\u0434\u044b\u0439 plan \u2192 `scenario_id`, `expected_telemetry`, `atomic_tests[]`

### 0.10.4 PhantomStrike-AI \u2014 MIT \u2192 P1/P2 (scoring formula direct import)
- AI-scoring \u0444\u043e\u0440\u043c\u0443\u043b\u0430 \u2192 `apps/science/findings/severity/phantomstrike_scorers.rs`
- safe-exploit payloads \u2192 `apps/specops/payloads/` (vendored C2 profiles)

### 0.10.5 PhishSlayer \u2014 GPLv3 \u2192 P1 (isolated lab process)
- `deploy/specops/sat/phishslayer-compose.yaml` \u2014 lab fixture
- CMDB import \u2192 `apps/specops/cmdb/phishslayer_models.py`
- KPI schema \u2192 `apps/webapp/components/specops/PhishKPI.tsx`

### 0.10.6 BluePhish \u2014 MIT \u2192 P1 (SAT lab)
- `deploy/specops/sat/bluephish/` \u2014 phishing lab (SMTP/IMAP click-tracking)
- campaign schema \u2192 `apps/specops/campaigns/bluephish_schema.rs`

### 0.10.7 fiercephish \u2014 AGPL \u2192 P2 (isolated campaign service)
- `deploy/specops/sat/fiercephish/` \u2014 campaign scheduling + click-tracking \u0447\u0435\u0440\u0435\u0437 \u0438\u0437\u043e\u043b\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u044b\u0439 \u043f\u0440\u043e\u0446\u0435\u0441\u0441

### 0.10.8 SPEAR \u2014 NO-LICENSE \u2192 P1/P2 (methods only)
- TextCNN/BERT/LLM \u0434\u0435\u0442\u0435\u043a\u0442\u043e\u0440\u044b \u2192 `apps/interpretation/detectors/spear_baseline/`
- LIME adversarial attack \u2192 `apps/tests/adversarial/` (red-team \u0447\u0435\u043a \u0434\u043b\u044f CI \u0434\u0435\u0442\u0435\u043a\u0442\u043e\u0440\u043e\u0432)

### 0.10.9 Sticks \u2014 MIT \u2192 P1 (lab fixture + STIX metric)
- `deploy/specops/lab/sticks-compose.yaml` \u2014 Caldera+Kali+nginx+DB
- STIX procedural-sufficiency \u043c\u0435\u0442\u0440\u0438\u043a\u0430 \u2192 `apps/science/metrics/stix_sufficiency.rs`
- RoE-gate \u2192 `apps/science/scenarios/roe/`

### 0.10.10 TripleFantasy \u2014 MIT \u2192 P2 (pattern catalog)
- `docs/kb/specops/patterns/triplefantasy.md` \u2014 modular C++ implant patterns:
  - AES-256-GCM/ChaCha20 \u0448\u0438\u0444\u0440\u043e\u0432\u0430\u043d\u0438\u0435
  - HKDF key derivation
  - anti-debug/anti-VM detection

### 0.10.11 AzureAD-Attack-Defense \u2192 P2 (KB)
- `docs/kb/identity/azuread_playbook.md` \u2014 Entra ID playbook:
  - password spray \u2192 detection rule `apps/interpretation/detectors/azuread_password_spray.rs`
  - consent grant attack \u2192 detection rule
  - AiTM \u2192 detection rule
  - PRT replay \u2192 detection rule

### 0.10.12 Labyrinth \u2014 AGPL-3.0 \u2192 P1 (native Rust deception)
- `apps/specops/deception/` \u2014 cognitive portal-trap \u043a\u0430\u043a native Rust nodes
- TUI dashboard \u2192 `apps/webapp/components/specops/LabyrinthTUI.tsx`
- web dashboard \u2192 `apps/webapp/components/specops/LabyrinthWeb.tsx`

### 0.10.13 Operation-Molasses \u2014 MIT \u2192 P1 (toolkit + KB)
- `toolkit/operation_molasses/` \u2014 33-phase kill-chain IaC \u0431\u0430\u0437\u0430
- `docs/kb/specops/molasses_33phases.md` \u2014 full phase \u043e\u043f\u0438\u0441\u0430\u043d\u0438\u0435
- short-and-distort disinfo-bot \u2192 `apps/specops/disinfo/molasses_bot.py`

### 0.10.14 PIDSF \u2014 MIT \u2192 P1 (RoE-gate pattern + detection)
- RoE-gate (\u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u043d\u044b\u0439 sign-off) \u2192 `apps/science/scenarios/roe/`
- detection-\u043c\u043e\u0434\u0443\u043b\u044c (permutation+crt.sh scoring) \u2192 `apps/acquisition/enrichment/lookalike/`
"""

with io.open(path, 'w', encoding='utf-8') as f:
    f.writelines(head)
    f.write(clean_tail)

with io.open(path, 'r', encoding='utf-8') as f:
    print('lines:', len(f.readlines()))
