# ER baseline — the current matcher, measured

**Task**: T084 · **Feature**: `030-global-platform-upgrade`
**Subject**: `apps/zero/zero/resolution/fellegi_sunter.py`, canonical per ADR-030-06 D1
**Corpus**: `bench/fixtures/global_upgrade/identity/pairs.jsonl` (T076, DON-ER-001)
**Machine-readable result**: `benchmarks/er-baseline.json`, written by the same run

> T084's own words: *"No numbers before this exists."* Every number below was produced by
> running the command printed beside it, on the corpus identified by the sha256 printed beside
> it, in the environment recorded beside it. Anything not so produced is written
> **`NOT MEASURED`** with the reason. Nothing here is estimated, rounded from literature, or
> carried over from a previous run.

---

## How to reproduce

```powershell
.venv\Scripts\python.exe benchmarks\er_baseline.py
```

Writes `benchmarks/er-baseline.json` and prints it. The corpus is verified before measurement:
every record's `blob_digest` must equal `sha256(source_text)` and its `char_span` must resolve
to the record's `name` (contract 02 R8). A record that does not resolve aborts the run.

| | |
|---|---|
| Command | `.venv\Scripts\python.exe benchmarks\er_baseline.py` |
| Corpus | `bench/fixtures/global_upgrade/identity/pairs.jsonl` |
| Corpus sha256 | `e0cf42ea4697a6c80422196e611bda7f5bedf6d41558a9a8a0af4fdee134b853` |
| Run recorded here | `2026-10-19T01:14:24Z` |
| Python | 3.11.9 |
| Platform | `Windows-10-10.0.26200-SP0`, `AMD64` |
| Splink | **not consulted.** T105 is Phase 8; this file measures the current matcher only. |

---

## Corpus under measurement

| | |
|---|---|
| Pairs | 49 |
| Labelled, non-ambiguous | **39** (22 `match`, 17 `non_match`) |
| Ambiguous (excluded from both denominators) | 10 |
| Provenance `authored` / `synthetic` | 35 / 14 |
| Distinct records | 84 |
| Measurement unit | one pair, scored independently. No clustering, no union-find, no transitive closure. |

Ambiguous pairs are excluded because counting them either way measures the label set's ambiguity
rather than the matcher. They are still scored, and reported separately below.

## The matcher under measurement

| | |
|---|---|
| Comparison fields | `name`, `email`, `phone`, `org` — the module's own four constructors |
| Blocking keys | `email`, `phone`, `name` (exact / digit-normalised / Soundex) |
| `lambda_prior` | 0.01 (constructor default, not overridden) |
| `max_iterations` | 25 |
| Level priors | **not overridden** — the module's shipped defaults |
| Training pairs | the corpus's own 137 blocked pairs. **No held-out split.** |
| Calibration status | `UNCALIBRATED` — no threshold fitted against held-out labels |

**Operating point: posterior > 0.5 ⟺ weight > 0 bits.** This is `FellegiSunter.match(threshold=0.0)`,
the module's own default, and a prior a human chose. It was **not** fitted against these labels.
The full sweep is below so the trade-off is visible rather than reduced to one number.

---

## Measured results

All five quantities T084 names, on the 39 labelled pairs.

### Pair recall

| | |
|---|---|
| **0.863636** (19 / 22) | `match` pairs scoring above the operating point |
| Missed | `ID-A012` (−44.28 bits), `ID-A013` (−31.79 bits), `ID-A022` (−77.47 bits) |

### Candidate-pair reduction (blocking)

| | |
|---|---|
| **0.9607** | `1 − 137 / 3486` over the 84 distinct records |
| Blocking recall | **1.0** (22 / 22). No `match` pair was missed by blocking. |

`1 − blocked_pairs / (n(n−1)/2)`. Blocking and scoring are separate stages and are reported
separately; blocking is not doing any of the discrimination work here, it is only avoiding pairs.

### False-merge rate

| | |
|---|---|
| **0.176471** (3 / 17) | `non_match` pairs scoring **above** the operating point |
| The three | `ID-A018` (+8.47), `ID-A021` (+8.47), `ID-S03` (+9.27) |

### False-non-match rate

| | |
|---|---|
| **0.136364** (3 / 22) | `match` pairs scoring **at or below** the operating point |
| The three | `ID-A012` (−44.28), `ID-A013` (−31.79), `ID-A022` (−77.47) |

### Calibration

Posterior derived from the matcher's own weight (`p = 2**W / (1 + 2**W)`). `lambda` is not
updated by this EM implementation, so the prior stays at 0.01 and the posteriors are not
prior-corrected.

| Metric | Value |
|---|---|
| Expected calibration error | **0.154503** |
| Brier score | **0.153695** |

| Posterior bin | n | mean predicted | observed match rate |
|---|---|---|---|
| [0.00, 0.10) | 17 | 0.000 | 0.176 |
| [0.90, 0.95) | 1 | 0.909 | 1.000 |
| [0.95, 1.00] | 21 | 0.997 | 0.857 |

Only three bins are populated, and the top one is where the miscalibration lives: the 21 pairs in
`[0.95, 1.00]` carry a mean predicted posterior of 0.997 and an observed match rate of 0.857. That
bin contains 18 true matches **and all three false merges** — `ID-A018`, `ID-A021` and `ID-S03`
are all scored at 0.997–0.998. A score that says "0.997" cannot be used to distinguish "these are
the same person, confirmed" from "these are two different people at the same desk".

### Precision on proposed pairs

| | |
|---|---|
| **0.863636** (19 TP / 22 proposed) | 22 non-ambiguous pairs above the operating point |

---

## Threshold sweep

Cut points are drawn from the observed weight distribution, not from the labels. A "nice number"
grid sits entirely inside the empty gap between the two clusters the weights form and prints the
same row seven times, which reads as stability and is really just a blank region.

| threshold (bits) | false-merge | false-non-match | pair recall | precision | proposed |
|---|---|---|---|---|---|
| −86.26 | 0.941 | 0.000 | 1.000 | 0.579 | 38 |
| −82.50 | 0.588 | 0.000 | 1.000 | 0.688 | 32 |
| −77.47 | 0.412 | 0.045 | 0.955 | 0.750 | 28 |
| −73.71 | 0.235 | 0.045 | 0.955 | 0.840 | 25 |
| −44.28 | 0.235 | 0.091 | 0.909 | 0.833 | 24 |
| −32.71 | 0.176 | 0.091 | 0.909 | 0.870 | 23 |
| −31.79 | 0.176 | 0.136 | 0.864 | 0.864 | 22 |
| **0.00** | **0.176** | **0.136** | **0.864** | **0.864** | **22** |
| +3.32 | 0.176 | 0.182 | 0.818 | 0.857 | 21 |
| +6.25 | 0.176 | 0.227 | 0.773 | 0.850 | 20 |
| +8.35 | 0.176 | 0.545 | 0.455 | 0.769 | 13 |
| +8.47 | 0.059 | 0.909 | 0.091 | 0.667 | 3 |
| +9.27 | 0.000 | 0.909 | 0.091 | 1.000 | 2 |
| +12.11 | 0.000 | 1.000 | 0.000 | — | 0 |

(Full table, one row per distinct observed weight: `benchmarks/er-baseline.json` → `sweep`.)

The false-merge rate is flat at 0.176 across the entire useful range of the curve and can only be
reduced by pushing the threshold above +8.4 bits, at which point **91 % of true matches have
already been lost**. There is no threshold on this corpus that is both safe and useful.

---

## What the weights actually show

| Pair | Label | Weight (bits) | Posterior |
|---|---|---|---|
| `ID-A018` two Pavel Sokolovs at one desk | non_match | **+8.47** | 0.997 |
| `ID-A021` Elena Marchetti, id differs in one digit | non_match | **+8.47** | 0.997 |
| `ID-S03` Silua vs Silva, id differs in one digit | non_match | **+9.27** | 0.998 |
| `ID-A023` Hana Novotná, no email, no phone, id differs | non_match | −77.35 | 0.000 |
| `ID-A009` Wang Wei / 王伟 (pinyin ↔ Han) | match | +3.32 | 0.909 |
| `ID-A013` Maria Kovač → Maria Horvat | match | **−31.79** | 0.000 |
| `ID-A012` Acme Ltd / Acme LLC, same company number | match | **−44.28** | 0.000 |
| `ID-A022` Hana Novotna / Hana Novotná, no email, no phone | match | **−77.47** | 0.000 |

Four findings, each a direct consequence of the four fields the matcher compares:

1. **All three false merges are decided by fields the comparison vector does not contain.**
   `ID-A018`, `ID-A021` and `ID-S03` agree exactly on `name`, `email`, `phone` and `org`, so they
   hit the `exact` level on all four. What separates them from a true match — a national
   identifier and a date of birth, both present in the corpus — is not a comparison field. The
   matcher scores them at 0.997–0.998.
2. **Absent is scored exactly as "disagreeing".** `ID-A022` (a true match) and `ID-A023` (a false
   merge candidate whose national id differs) both have no email and no phone at all. Both fall
   to the catch-all level on both fields and land at ≈ −77 bits; the two missing fields cost
   about 74 bits, and the national identifier that separates them costs nothing because it is
   never read. A missing value is not evidence of anything, and here it is scored as evidence of
   difference.
3. **Transliteration fails at the character level.** `ID-A009` is the weakest true match at
   +3.32 bits: `normalize()` does not transliterate, so Soundex over `王伟` yields nothing and
   the pair scores on email, phone and org alone.
4. **The remaining false non-matches are org and surname changes.** `ID-A013` (Kovač → Horvat)
   at −31.79 bits and `ID-A012` (Ltd → LLC) at −44.28 bits both have an unchanged email and
   phone and a shared organisation, and are still pushed below the threshold. Neither a changed
   family name nor a changed legal form is covered by any comparison level.

---

## Why the separation looks so good, and why that is an artefact

The non-match weights bottom out at −86 bits and the match weights top out at +12. A score that
separates that cleanly invites the conclusion that this is a strong matcher. It is not evidence
of that, and the reason is in the fitted parameters:

```
m[email][else] = 3.637e-11      m[phone][else] = 1.376e-65
```

The m-step assigns near-zero match posterior to the non-match levels of email and phone, so `m`
collapses to the order of the module's own `_EPS = 1e-12`, and `log2(m/u)` is effectively
computed against that floor. The floor is what puts non-match weights at −86 bits.

That happened because the training set is the corpus's own 137 blocked pairs and almost all of
them are true matches: there is not enough non-match mass to fit a non-match level. **This is a
property of an under-determined training set, not a measured quality of the matcher**, and no
threshold anywhere on the curve should be read as calibrated because of it.

---

## NOT MEASURED

Each of these is a real number someone would like to quote. None of them was measured, and none
of them is estimated here.

| Quantity | Why not |
|---|---|
| Population false-merge rate | The corpus is constructed, not sampled. Prevalence and the difficulty mix of real records are unknown. These rates describe **this corpus** and cannot be projected onto production data. |
| Held-out generalisation | `FellegiSunter.fit` trains on the corpus's own blocked pairs. There is no held-out split, so every number here is in-sample. |
| Performance on captured data | No WARC corpus or captured record set exists in this repository. The corpus is hand-authored and template-generated. |
| Non-Latin-script performance | One Han-script pair and several Latin-diacritic pairs. Not enough to characterise the transliteration regime, which is where this matcher is weakest. |
| Comparison against Splink | Out of scope for T084. T105 is Phase 8, and running a second engine here would answer a question this phase is not chartered to answer. |
| Confidence intervals | With 22 positives and 17 negatives, one case is worth **5.9 points** of false-merge rate and **4.5 points** of false-non-match rate. These are point estimates with no error bar. |
| Throughput / cost at scale | Wall-clock for this run only, below. 84 records is not a throughput measurement and must not be quoted as one. |

### Wall-clock, this run only — not a benchmark

| Stage | Seconds |
|---|---|
| Blocking (84 records → 137 pairs) | 0.023 |
| EM fit (25 iterations) | 0.369 |
| Scoring (49 pairs) | 0.010 |
| **Total, including interpreter start** | **1.60** |

Across repeat runs the EM stage varied by roughly 7× (0.37 s – 2.50 s observed). Treat as order
of magnitude.

---

## Ambiguous pairs: what the matcher would have done

Ten pairs, excluded from every rate above, reported because they are the cases where a merge is
both plausible and expensive.

| Above the operating point (the matcher would propose a merge) | `ID-A025` `ID-A026` `ID-A027` `ID-A028` `ID-A029` `ID-A030` `ID-S07` `ID-S10` |
|---|---|
| At or below | `ID-A024` `ID-A031` |

Eight of ten would be proposed. This is the part of the corpus where "no similarity probability
may commit a merge alone" (FR-081) does its work: eight proposals, zero merges, because the gate
in `apps/admission/resolution/gate.py` has no path from a proposal to a MERGE.

---

## Sensitivity: adding `id_number` and `birth_date` as comparison fields

**This is not the canonical matcher and nothing here changes it.** The module ships four fields.
This section exists so the claim below is a measurement rather than an argument.

Same corpus, same blocking, same operating point, two extra `text_field` comparisons:

| | Canonical (4 fields) | + `id_number` + `birth_date` |
|---|---|---|
| False-merge rate | 0.176 (3/17) | **0.176 (3/17)** — same three pairs |
| False-non-match rate | 0.136 (3/22) | 0.091 (2/22) — recovers `ID-A013` |
| Pair recall | 0.864 | 0.909 |

**Adding the two discriminating fields does not remove any false merge.** The intuitive fix does
not work on this corpus, and the reason is the same one as the artefact below: EM is re-fit on
the same 137 blocked pairs, so the new fields land in the same under-determined training set and
the same degenerate `m` estimates reproduce. Recall improves and one true match is recovered;
the expensive errors are untouched.

That is a finding about the training conditions, not about the value of the fields. It has not
been tested against a training set with enough non-match mass to fit one, and that test is not
possible with the data in this repository.

## What this means for the decisions that depend on it

1. **The canonical matcher's own false-merge rate is 0.176 on this corpus, and all three false
   merges are decided by fields the comparison vector does not contain.** The gate refusing
   uncalibrated matchers (T081) is therefore load-bearing rather than precautionary: without it,
   the score would commit `ID-A018`, `ID-A021` and `ID-S03` at a posterior of 0.997–0.998.
2. **The matcher is `UNCALIBRATED` by its own account.** Nothing in this file promotes it past
   that, and ADR-030-06 D6's gate condition remains open.
3. **No Splink comparison is recorded.** `splink_adapter.py` stays benchmark-only and unwired,
   per ADR-030-06 D3.
4. **The measured rates are properties of this corpus.** They are the honest description of what
   this matcher does on these 39 labelled pairs, and nothing more. The `NOT MEASURED` table above
   is part of the result, not a caveat appended to it.

---

## Source

| | |
|---|---|
| Harness | `benchmarks/er_baseline.py` |
| Corpus builder | `bench/fixtures/global_upgrade/identity/build_corpus.py` (`--verify` to check for drift) |
| Corpus notes | `bench/fixtures/global_upgrade/identity/README.md` |
| Machine-readable | `benchmarks/er-baseline.json` (same run; contains every per-pair weight) |
| Matcher under test | `apps/zero/zero/resolution/fellegi_sunter.py`, unmodified |