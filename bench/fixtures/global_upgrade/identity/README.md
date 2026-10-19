# Labelled identity pair corpus (spec 030 T076, DON-ER-001)

**Files**

| File | What it is |
|---|---|
| `pairs.jsonl` | The corpus. One JSON object per line, one labelled pair per line. Frozen. |
| `build_corpus.py` | Builds it. `--verify` re-derives and compares; exits non-zero on drift. |

```powershell
.venv\Scripts\python.exe bench\fixtures\global_upgrade\identity\build_corpus.py            # rebuild
.venv\Scripts\python.exe bench\fixtures\global_upgrade\identity\build_corpus.py --verify   # check
```

## Shape

```text
pair_id, label (match | non_match | ambiguous), ambiguous, category,
provenance (authored | synthetic), generator, rationale, ambiguity_reason,
left, right
```

Each side is a record:

```text
record_id, entity_type, name, email, phone, org, address, id_number, birth_date,
aliases, lineage_root, source_text, blob_digest,
span_ref { observation_ref, blob_digest, selector.char_span{start,end,encoding},
           source_locator{uri,fragment}, selector_semantics_version }
```

`source_text` is the evidence the fields were read from. `blob_digest` is
`sha256(source_text)` and the `char_span` resolves to the `name` inside it — every record is
grounded per spec 030 contract 02 R4/R8, and `benchmarks/er_baseline.py` re-verifies every
record's digest and span before it measures anything, failing loudly if one does not resolve.

`selector_semantics_version` is `document_char/1` on every record. Only that variant is emitted;
contract 02 R2 forbids silently comparing across conventions, so no other variant appears here.

## Counts

| | Pairs |
|---|---|
| total | **49** |
| `match` | 22 |
| `non_match` | 17 |
| `ambiguous` | 10 |
| provenance `authored` | 35 |
| provenance `synthetic` | 14 |
| distinct records | 84 |

Denominators for a measurement are `match` and `non_match` only: **39 labelled pairs**.
Ambiguous pairs are counted, reported and excluded from both sides.

## What the two provenances mean

**`authored`** — hand-written cases. Each stands for a situation that occurs in identity
resolution: a name transliterated between registries, a German `Nachname, Vorname` ordering, a
company's legal form abbreviated two ways, a surname changed on marriage, a company number
reformatted with a hyphen, two people sharing a co-working desk, a family firm sharing a
mailbox, a national identifier differing in one digit.

These are **authored, not sampled**. No capture was made; no real person is in them. They are
realistic and deliberately chosen to exercise failure modes, which means they are *not*
representative of any population and their rates say nothing about prevalence. That limitation
is carried into `benchmarks/er-baseline.md` rather than left here.

**`synthetic`** — deterministic template expansion, no RNG. `SYNTHETIC_VARIANTS` in
`build_corpus.py` is a fixed 12-row table of (suffix, name_a, name_b, transformation); the two
`ID-S9x` pairs are fixed true-negative controls. Every synthetic pair carries
`provenance: "synthetic"` and a `generator` string naming the exact table row or function that
produced it, so a reviewer can regenerate any one case in isolation.

## Category coverage (T076)

| Required | Where |
|---|---|
| transliteration variants | `ID-A001`–`ID-A010`, `ID-S02`, `ID-S03`, `ID-S07`, `ID-S10` |
| same-name / different person | `ID-A014`–`ID-A017`, `ID-A018` |
| company alias | `ID-A011` |
| name change | `ID-A013` |
| shared address | `ID-A018`–`ID-A020` |
| old / new identifiers | `ID-A010`, `ID-A012`, `ID-A022` |
| conflicting dates | `ID-A021` |
| incomplete fields | `ID-A022`, `ID-A023`, `ID-S08` |
| true negatives | `ID-A032`–`ID-A035`, `ID-S91`, `ID-S92` |
| **ambiguous** | `ID-A024`–`ID-A031`, `ID-S07`, `ID-S10` |

## The ten ambiguous pairs

They exist because a corpus without them cannot measure a false-merge rate honestly. Hard cases
get quietly excluded, the hard denominator disappears, and the rate that comes out describes only
the easy remainder.

- `ID-A024` — two aggregators, byte-identical records. One person listed twice, or two people
  identical on every published field. Indistinguishable.
- `ID-A025` — identical but for the last digit of a national id (`…344` vs `…345`).
- `ID-A026` — same id, same contact, three-year date-of-birth gap.
- `ID-A027` — Latin transliteration of an umlaut name, ids differ in the last digit.
- `ID-A028` — same name, employer, mailbox and phone; ids differ; dates of birth 31 years apart.
- `ID-A029` — different given names, one shared firm mailbox, one shared address.
- `ID-A030` — same name, mailbox, address and birth date; three different national ids.
- `ID-A031` — name change and email change with no identifier and no birth date on either side.
- `ID-S07`, `ID-S10` — synthetic umlaut and accent variants where the variant and a second
  person are equally consistent with the record.

## `lineage_root`

Every record carries the origin its document ultimately derives from. Several records share a root
on purpose: `ID-A024`'s two aggregators have different roots, while the `LR-tekhnolab-*` family
and the `LR-weber-*` family deliberately share one. This is the field corroboration counts
under T080 — twenty mirrors of one press release are one source wearing twenty hats — and it is
what separates a corroboration count from a hostname count.

## Limits

1. **Small.** 39 labelled pairs. One case is worth 5.9 points of false-merge rate and 4.5 points
   of false-non-match rate. Every rate derived from this corpus is a point estimate with no error
   bar.
2. **Constructed.** Difficulty is chosen, not sampled. The false-merge rate is a property of
   this corpus.
3. **Half synthetic.** The synthetic half varies only the name surface; it cannot stand in for
   real data on any axis it does not touch.
4. **No non-Latin regime.** One Han-script pair and several Latin-diacritic pairs. Not enough to
   characterise transliteration, which is where this matcher is weakest.
5. **The matcher sees four fields.** `name`, `email`, `phone`, `org`. Address, national id, date
   of birth and aliases are in the corpus and are deliberately *not* passed to the canonical
   matcher — that is a finding about the matcher, not a gap in the corpus.