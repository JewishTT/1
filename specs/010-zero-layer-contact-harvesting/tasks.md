# Tasks: Zero-Layer Contact Harvesting Pipeline

**Spec**: `specs/010-zero-layer-contact-harvesting/spec.md` · **Plan**: `plan.md`
Формат: `- [ ] TNNN — действие — target`

## Phase 0 — Type Detection (Layer 1)
- [x] T100 — Regex+heuristic type detector для 8 input types — `apps/zero/zero/type_detector.py` (✅ 8 типов + UNKNOWN, byte-magic, Soundex)
- [x] T101 — SeedInput schema + deterministic confidence scoring — реализовано в `apps/zero/zero/type_detector.py` (⚠️ target `apps/shared/contracts/` deviated — см. отчёт)
- [x] T102 — Harvester spawner на основе detected type — `apps/zero/zero/harvesters/registry.py` + `harvest_wave.py` (✅ default wave регистрирует полный checked-in module table через `register_all()`; фактический запуск каждого built-in module проверяется unit tests; live worker parallelism остаётся отдельным T183).

## Phase 1 — Harvest Modules (Layer 1–2)
- [x] T110 — Domain harvesters: email-permutation, subdomain-discovery, DNS, social — `apps/zero/zero/harvesters/domain.py` (✅ breach реализован как enricher `email_to_breach`, mock-индекс)
- [x] T111 — Email/username harvesters: Maigret/Sherlock worker-adapters, git-email — `apps/zero/zero/harvesters/{username,git}.py` (⚠️ Holehe не реализован — только worker-init)
- [x] T112 — Phone harvesters: WhatsApp/Telegram presence, PhoneInfoga dorks — `apps/zero/zero/harvesters/phone.py` (⚠️ carrier-lookup/QR-phone — backlog)
- [x] T113 — Image harvesters: QR, EXIF, OCR worker — `apps/zero/zero/harvesters/image.py` (⚠️ face detection — backlog)
- [x] T114 — URL harvesters: content scrape, link extraction, embedded contacts — `apps/zero/zero/harvesters/url.py`
- [x] T115 — Free-text name harvesters: permutation, social — `apps/zero/zero/harvesters/domain.py` + enrichment (⚠️ public records — backlog)

## Phase 2 — Entity Resolution (Layer 2, no AI)
- [x] T120 — Fellegi-Sunter probabilistic matcher (Splink-порт) — `apps/zero/zero/resolution/fellegi_sunter.py`
- [x] T121 — Graph topology: transitive closure, community detection (greedy modularity) — `apps/zero/zero/resolution/graph.py`
- [ ] T122 — EntityResolutionObservation → observation_gate

## Phase 3 — Enrichment + Feedback (Layer 3)
- [ ] T130 — spaCy NER pipeline (8 entity types) — не реализовано: вместо spaCy детерминированный `type_detector` (constraint "NO AI")
- [ ] T131 — 50+ enricher-modules — `apps/zero/zero/enrichment/modules.py` (✅ framework + 11 enricher-ов; до 50+ — backlog)
- [x] T132 — Feedback loop: enrichment → Kafka `zero_layer.feedback_seeds` → авто-trigger type_detector — `apps/zero/zero/enrichment/feedback.py` (✅ топик зарегистрирован в `apps/shared/events/topics.py`)
- [ ] T133 — EnrichmentObservation → observation_gate

## Phase 3.5 — Donor Acquisition (DONE 2026-09-21)
- [x] T170 — Клонировать 52 zero-layer донора в `donors/` (--depth 1) — ✅ выполнено, см. §0.12 inventory (10-ZERO-LAYER.md)
- [x] T171 — Резолв недоступных URL через GitHub API: sherlock→sherlock-project, user-scanner→kaifcodec, Profil3r→Greyjedix, email2phonenumber→martinvigo, gh-mailto→codeGROOVE-dev, erfert→grisuno/estorides + lazyaddon — ✅ выполнено
- [x] T172 — Sources-From-Everywhere спецификация (§0.11: web/Tor/TG/social/git/breach/phone/net/keyless) — ✅ выполнено
- [x] T173 — Frontend-дизайн (§0.13: 10 компонентов, дизайн-система, 3 модуля над OSINT-ядром) — ✅ выполнено
- [ ] T174 — Валидировать каждый клонированный донор: README-конспект + license-заголовок в §0.2–0.7 таблицы (по мере интеграции)
- [ ] T175 — Тест-фикстуры из клонированных доноров → `bench/fixtures/zero_layer/`

## Phase 4 — Native Spec-Ops Integration
- [ ] T140 — caldera Rust binding (pyo3) → `apps/specops/caldera/`
- [ ] T141 — ael/АEL-lib parser → scenario DSL → `apps/specops/scenarios/`
- [ ] T142 — SPEAR/PhantomStrike detectors → `apps/interpretation/detectors/`
- [ ] T143 — PhishSlayer lab fixture → `deploy/specops/sat/`
- [ ] T144 — Labyrinth Rust deception nodes → `apps/specops/deception/`
- [ ] T145 — Sticks compose fixture → `deploy/specops/lab/`
- [ ] T146 — TripleFantasy pattern catalog → `docs/kb/specops/patterns/`
- [ ] T147 — AzureAD playbook → `docs/kb/identity/`
- [ ] T148 — Operation-Molasses toolkit → `toolkit/`

## Phase 5 — Tactical Frontend
- [ ] T150 — D3.js force-graph component (node-typизация) — `apps/webapp/src/components/zero/LayerGraph.tsx`
- [ ] T151 — Entity inspector с confidence-страйпами + provenance — `apps/webapp/src/components/zero/EntityInspector.tsx`
- [ ] T152 — SSE status stream + harvest cycle metrics — `apps/webapp/src/components/zero/HarvestStream.tsx`
- [ ] T153 — Magma operation-matrix для spec-ops (real-time SSE) — `apps/webapp/src/components/specops/OperationMatrix.tsx`
- [x] T154 — Dark tactical theme + zero-layer styles — `apps/webapp/src/styles/zero/` (✅ product-wide `command-tactical.css` is now part of `styles/layers.css`; Research Case uses the scoped first-party module).

## Phase 6 — Verification
- [ ] T160 — bench/run --scenario zero-layer-smoke (8 seed types → harvest → resolve → enrich → feedback)
- [ ] T161 — Attribution audit + guarding tests для всех harvest-модулей
- [ ] T162 — SC-001…SC-010 validation + matrix-sync в 09-INTEGRATION-MATRIX.md

---

**Трекинг**: отмечать `[x]` по мере закрытия; новые задачи добавляют запись в `09-INTEGRATION-MATRIX.md` и passing guarding test.

## Phase 7 — Canonical evidence stages and production hardening
- [x] T180 — Стабильные HARVEST / ENRICHMENT / RESOLUTION stage records — `apps/zero/zero/harvest_wave.py` (`WaveStageRecord`, run-scoped reset, bounded depth, per-wave metrics, deterministic ordering; unit contracts).
- [x] T181 — Raw-first stage persistence — `apps/zero/zero/evidence.py` (`ZeroLayerEvidenceSink` → shared `AcquisitionArtifact` → canonical `ArtifactSink` → immutable Capture/Observation + refs-only event; `CaptureTimeBasis.ABSENT`; `DISCOVERY_ONLY`, `claim_admission_allowed=false`; integration contract).
- [x] T182 — Authenticated, tenant-scoped and case-governed API/composition wiring — `apps/control-plane/services/zero_layer.py`, `apps/control-plane/api/routes/research_cases.py`, `apps/control-plane/composition.py` (✅ current projected lead IDs only; approved scope + tenant + policy digest; durable request/byte/record/concurrency reservation; idempotency/replay; canonical ArtifactSink and immutable refs; outputs remain `DISCOVERY_ONLY`).
- [ ] T183 — Live public-source adapters through the existing catalogue → durable budget reservation → `PlanDriver` → Kafka worker → secure egress → ArtifactSink path. No raw `httpx` shortcut, no unbounded concurrency, no bypass of robots/licensing/rate/purpose policy. (⚠️ public HTTPS document capture is bounded and case-budgeted, but still runs in the dedicated ZeroLayerCaseService/SecurePublicTransport path rather than the catalogue → PlanDriver → Kafka worker chain).
- [ ] T184 — Promote HARVEST/ENRICHMENT/RESOLUTION payloads to explicit versioned `EntityResolutionObservation` / `EnrichmentObservation` contracts and close T122/T133 with replay + consumer-admission tests.
- [ ] T185 — Replace all deterministic mock lookup tables with real, attested, public and purpose-appropriate enrichers; expand beyond the current 11 modules only when each has license, terms, provenance, budget and live contract evidence.
- [ ] T186 — Bounded file-seed ingestion (image/PDF/DOCX), content-type validation, malware/quarantine policy, parser workers, and immutable raw retention/deletion contracts.
- [ ] T187 — Eight-input-type end-to-end smoke with independent fixtures, replay, retry/DLQ, backpressure and observable stage health; publish coverage/unsupported-source ledger without treating unknown as zero.

**Current boundary**: T180–T182 provide deterministic raw-first stage persistence plus the approved, tenant-scoped public-person API and durable budget/idempotency authority. The dedicated public-document lane currently uses bounded `SecurePublicTransport` and canonical `ArtifactSink`, but T183 remains open until it is driven by the catalogue → `PlanDriver` → Kafka worker chain. T122/T133 typed replayable observation contracts, the 50+ attested-enricher target, runtime execution of `CommandSpec`, bounded file-seed ingestion and the eight-type end-to-end matrix remain open; no mock lookup is presented as live evidence.
