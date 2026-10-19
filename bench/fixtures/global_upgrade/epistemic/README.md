# Epistemic fixture corpus (spec 030 T064, US3)

**Files**

| File | What it is |
|---|---|
| `cases.jsonl` | The corpus. One JSON object per line, one case per line. Frozen. |
| `build_corpus.py` | Builds it. `--verify` re-derives and compares; exits non-zero on drift. |

```powershell
.venv\Scripts\python.exe bench\fixtures\global_upgrade\epistemic\build_corpus.py            # rebuild
.venv\Scripts\python.exe bench\fixtures\global_upgrade\epistemic\build_corpus.py --verify   # check
```

## Provenance — read this before quoting any number from here

**Every case is `provenance: "synthetic"`. Every `source_licence` is `synthetic`.**

Nothing in this corpus was crawled. No upstream source was fetched, no registry was
queried, no licence was read off a real terms page, and no detection power was measured
on anything. Each case is a hand-constructed *description* of a situation the epistemic
layer has to survive, with source objects that exist only inside the fixture.

That is why `applicable_measurement` carries a `status` on every case, and why it is
always `not_performed_for_this_fixture`. The `method` string names what a real catalogue
entry would have to cite to earn a declared detection power — a seeded known-positive
trial, a recall measurement against a labelled held-out set, a dual enumeration of a
self-declared-complete universe. Naming the measurement is what lets a reader see exactly
what is missing when `detection_power` is null. Claiming it was performed would be the
same defect the corpus exists to catch, with a licence field attached.

The identity corpus beside this one (`../identity/`) is the model: it carries the same
`provenance` discipline and the same `--verify` gate.

## Shape

```text
case_id, category, provenance, generator, source_licence,
ground_truth, expected, prohibited_false_inference, applicable_measurement,
sources[], proposition, evidence[], predicate_raw?, preconditions_all_declared?
```

`expected` is written independently of the case and is what the tests compare against:

```text
research_state { disposition, query, truth_state, absence, evidence, scope },
research_state_name (null when the case sits off the thirteen anchors),
stage_status, error_code, may_claim_universal_negative,
predicate_resolution_state?, predicate_label?
```

`research_state_name` is `null` on three cases — `EPI-SNR-KNOWN-01`,
`EPI-SNR-UNKNOWN-01`, `EPI-SNR-KNOWN-02`'s sibling, and `EPI-SAT-02`. That is not a gap.
Those records are real and none of the thirteen names describes them, which is the
evidence that the model is dimensions rather than a fourteenth enum: `EPI-SAT-02` is
saturated-with-scope *and* contradicted, and a flat enum would have had to lie about one
of the two.

## Counts

| | Cases |
|---|---|
| total | **23** |
| positive_only | 2 |
| negative_only | 2 (one `negative_support`, one `refuted`) |
| both | 3 (recency, majority, single high score) |
| unknown | 2 (cue-phrase predicate, header-only predicate) |
| unsupported_source | 2 (parser cannot express; capability absent) |
| failed_source | 2 (unreachable host; mid-enumeration timeout) |
| searched_no_result, **known** detection power | 2 (one `searched_no_result`, one `qualified_absence`) |
| searched_no_result, **unknown** detection power | 3 (undeclared; declared-but-0.2; two unquantified sources) |
| unknown_not_investigated | 1 |
| no_observations | 1 |
| inconclusive | 1 |
| saturated_with_scope | 2 (exhausted-and-empty; exhausted-and-contradicted) |
| distinct source objects | 33 |
| `source_licence == "synthetic"` | **23 / 23** |

## The independent test, as five cases

The user story's independent test names five inputs and requires four distinct,
non-collapsed outcomes. All five are here, and the test asserts pairwise distinctness
across a wider set than four — distinctness is not a property of exactly four things.

| Input | Case | Record |
|---|---|---|
| unreachable source | `EPI-FAIL-01` | `failed / not_run / neither / informational_only` |
| zero-result, declared detection power | `EPI-SNR-KNOWN-02` | `completed / ran_zero_match / neither / qualified_absence` |
| zero-result, **undeclared** detection power | `EPI-SNR-UNKNOWN-01` | `completed / ran_zero_match / neither / informational_only` |
| two sources disagreeing | `EPI-BOTH-01` | `completed / ran_matched / both / conflicted` |
| unknown predicate | `EPI-UNK-01` | typed `unknown` candidate, label and span intact |

The third row is the centre of the corpus and `EPI-SNR-KNOWN-01` is its control: same
disposition, same query axis, same truth state — differing only in whether the source
declared what it would have found. That pair is what makes "a qualified absence was
manufactured" a test failure rather than a code-reading exercise.

## `prohibited_false_inference`

Every case names the inference most likely to be drawn and the reason it is wrong, plus
an `assertion` — the name of a predicate the test evaluates against the real answer:

| `assertion` | Meaning | Cases |
|---|---|---|
| `may_claim_universal_negative` | the answer must not support "it does not exist" | 16 |
| `contradiction_resolved` | the conflict must survive | 4 |
| `predicate_dropped` | the raw label and span must reach the API | 2 |
| `is_qualified_absence` | must **not** be a qualified absence | 1 |
| `is_negative_support` | inconclusive must not read as refutation | 1 |
| `is_refuted` | negative support must not read as a checked denial | 1 |
| `none` | no inference is being prohibited (the one supported universal claim) | 1 |

This is what stops the corpus being documentation. The test does not read the prose and
hope; it reads the `assertion` name, evaluates it against a `ResearchState` the platform
actually constructed from the case, and fails when the platform disagrees. Change the
engine and `EPI-SNR-UNKNOWN-01` goes red.

## Limits

1. **Nothing here was observed.** These are constructed situations. Any rate derived from
   this corpus is a property of the constructions.
2. **The sources are fictional and so are their licences.** `synthetic` is the accurate
   answer and no real licence is claimed anywhere in this directory.
3. **Detection powers are declared, not measured.** A fixture that asserts `0.93` is
   asserting a property of a source that exists only in the fixture. That is sufficient
   to test the *rule* (declared + above threshold ⇒ absence available) and is not
   evidence about any real source's recall.
4. **No multilingual, no paywall, no adversarial cases.** Two of the twenty-three are
   the only ones where the predicate has no cue phrase, which is thinner than the
   vocabulary-mismatch problem deserves.
5. **One subject class.** Every proposition is a beneficial-ownership claim. The
   epistemic algebra is subject-agnostic; the corpus does not demonstrate that by
   testing two.
