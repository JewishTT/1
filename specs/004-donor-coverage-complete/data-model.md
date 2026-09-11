# Data Model: Full Donor Coverage

**Date**: 2026-09-08 | **Feature**: [spec.md](spec.md)

## Scope

This document extends the data model from tracks 001–003 with four additional
adapted donor modules. Each entity carries an **attribution header** in its
implementing module (source repo, license, commit-ish, what-changed) per
**FR-001**.

## 1. TemporalConflict [D] `pg` (projection)

From investigator `graph/temporal_consistency.py` + date primitives from
`graph/dedup.py` → adapted as `apps/shared/donor/temporal.py`.

| field | type | notes |
|---|---|---|
| `conflict_id` | str | `TC-` prefixed, deterministic per event+window. |
| `event_id` | str | subject event / candidate id. |
| `min_date` | datetime | earliest date in conflict set. |
| `max_date` | datetime | latest date in conflict set. |
| `days_apart` | int | date span. |
| `tol_days` | int | tolerance threshold that triggered conflict. |
| `reason` | str | `spread` or `ordering_mismatch`. |

**Functions**: `parse_iso_date(s)` → (y, m, d); `to_iso_date(v)` → "YYYY-MM-DD";
`dates_compatible(a, b, window_days)` → bool; `date_spread_conflict(dates,
tol_days)` → Conflict|None; `ordering_conflicts(event_dates, edges, tol_days)`
→ list[Conflict]; `scan(event_dates, edges, tol_days)` →
`{"events": {...}, "orderings": [...]}`.

**Invariants**: year-only dates never produce conflicts; year-month dates use
month boundary; invalid/unparseable dates are skipped.

## 2. HarvestTarget [D] (in-memory / value class)

From SpiderFoot `spiderfoot/target.py` → adapted as `apps/shared/donor/target.py`.

| field | type | notes |
|---|---|---|
| `raw` | str | original input. |
| `target_type` | TargetType | DOMAIN, IP, EMAIL, URL, USERNAME, ASN... |
| `value` | str | canonical normalized value. |
| `aliases` | list[str] | equivalent raw forms. |

**TargetType registry**: `DOMAIN`, `IPV4`, `IPV6`, `EMAIL`, `URL`, `USERNAME`.

**Functions**: `classify(raw)` → TargetType via regex; `normalize(raw, type)`:
- DOMAIN: lowercase, strip trailing dot, punycode IDNA encode.
- IP: stdlib `ipaddress.ip_address` (canonical form, no leading zeros).
- EMAIL: lowercase local@domain.
- URL: extract hostname via stdlib `urllib.parse`.
- USERNAME: passthrough.

**Adaptation**: `netaddr` dependency rewritten to stdlib `ipaddress` /
`ip_network` (FR-002).

## 3. LinkKind mapping [D] (webapp logic)

From kafSIEM `src/lib/severity.ts` + `src/lib/incident-links.ts` → adapted as
`apps/webapp/src/lib/donor/links.ts`.

| field | type | notes |
|---|---|---|
| `LinkKind` | union | `entity_to_entity`, `mention_to_entity`, `observation_to_mention`, `assertion_supports`, `assertion_contradicts`, `candidate_similar`, `candidate_same_as`, `temporal_follows`, `attribution_source`. |

**Functions**: `linkLabel(kind)` → human-readable string; `linkColor(kind)` →
hex color; `linkStyle(kind)` → CSS class string (plain CSS, no Tailwind);
safe default for unknown kinds.

## 4. Confidence mapping [D] (webapp logic)

From vitni `lib/confidence.ts` → adapted as `apps/webapp/src/lib/donor/confidence.ts`.

| field | type | notes |
|---|---|---|
| `Confidence` | union | `verified`, `unverified`, `asserted`. |

**Functions**: `confidenceBadgeClass(c)` → hex color; `formatConfidenceLabel(c)`
→ display string; safe default for unknown confidence.

## 5. RelationshipType registry [D] (webapp logic)

From vitni `lib/relationshipTypes.ts` → adapted as
`apps/webapp/src/lib/donor/relationshipTypes.ts`.

| field | type | notes |
|---|---|---|
| `RelationshipType` | interface | `id`, `label`, `color`, `bidirectional`, `description`. |

**Functions**: `lookupRelationshipType(id)` → RelationshipType|default;
tested; icon field dropped (react-icons dependency removed, FR-007).

## Relationships summary

```text
CorrelationEdge.observations → Observation.observation_id
TemporalConflict.event_id → Candidate/Entity.entity_id
HarvestTarget.value → Observation.canonical_target
Finding → Claim (verdict/supported/contradicted)
LineageNode.reviewable → ReviewDecision.target
```

## Validation rules

- **FR-002**: All Python modules use stdlib only (netaddr → ipaddress).
- **FR-006**: Each extracted module is wired into a live consumer.
- **FR-007**: UI donor modules are logic-only; no framework/icon port.
- Temporal conflicts are **never auto-resolved** — only flagged for analyst
  review.
- Unknown link kinds, confidence, or relationship types fall through to safe
  defaults (never crash).
