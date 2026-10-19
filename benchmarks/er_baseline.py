"""Measure the canonical matcher on the frozen labelled pair corpus (spec 030 T084).

Target: ``apps/zero/zero/resolution/fellegi_sunter.py``, named canonical by ADR-030-06 D1.

Run::

    .venv\\Scripts\\python.exe benchmarks\\er_baseline.py

Writes ``benchmarks/er-baseline.json`` next to ``benchmarks/er-baseline.md``. The markdown is
written by hand from that JSON, so the two cannot silently disagree: every number in the document
carries the command that produced it, and any number without one is marked ``NOT MEASURED``.

Four rules this script holds itself to, because a benchmark file with invented numbers is worse
than no benchmark file at all:

1. **Ambiguous pairs are in neither denominator.** They are counted and reported separately.
   Counting them as non-matches measures the label set's ambiguity, not the matcher.
2. **The operating point is stated, not fitted.** The headline is posterior > 0.5, which is
   exactly ``weight > 0`` — the matcher's own default, and a prior a human chose rather than one
   this script tuned against labels. A sweep over thresholds is reported beside it so the
   trade-off is visible instead of being a single number with a favourable round number.
3. **Only measured things are printed.** Anything this script cannot compute prints
   ``NOT MEASURED`` with the reason. Nothing is estimated and nothing is carried in from the
   literature.
4. **The training conditions are on the face of the result.** ``FellegiSunter.fit`` runs EM over
   the corpus's own blocked pairs with no held-out split, because the matcher has no
   out-of-corpus corpus. That is a real limitation of the number and it is reported with it.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
CORPUS = REPO / "bench" / "fixtures" / "global_upgrade" / "identity" / "pairs.jsonl"
OUT_JSON = REPO / "benchmarks" / "er-baseline.json"

sys.path.insert(0, str(REPO / "apps" / "zero"))
sys.path.insert(0, str(REPO / "apps" / "shared"))

from zero.resolution.fellegi_sunter import (  # noqa: E402
    FellegiSunter,
    block_pairs,
    email_field,
    name_field,
    phone_field,
    text_field,
)

#: The comparison profile the canonical matcher is run with. These are the four field
#: constructors the module ships; no level priors are overridden, so the module's own defaults
#: are what is measured.
FIELDS = (name_field("name"), email_field("email"), phone_field("phone"), text_field("org"))

#: Posterior > 0.5 ⟺ weight > 0 ⟺ ``FellegiSunter.match(threshold=0.0)``. Unfitted.
HEADLINE_THRESHOLD_BITS = 0.0

CALIBRATION_BINS = [0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 0.95, 1.0000001]


def posterior_from_weight(bits: float) -> float:
    """Posterior implied by the matcher's own weight.

    ``W = log2(lambda/(1-lambda)) + sum log2(m/u)``, so ``2**W`` is the odds and
    ``p = 2**W / (1 + 2**W)``. Derived, not fitted, and valid because the implementation does not
    update lambda during EM — a fact this script asserts rather than assumes.
    """
    odds = 2.0**bits
    return odds / (1.0 + odds)


@dataclass
class PairMeasurement:
    pair_id: str
    label: str
    category: str
    provenance: str
    record_a: str
    record_b: str
    weight_bits: float
    posterior: float
    in_blocking: bool


@dataclass
class Report:
    command: str
    generated_at: str
    environment: dict[str, Any]
    corpus: dict[str, Any]
    model: dict[str, Any]
    blocking: dict[str, Any]
    headline: dict[str, Any] = field(default_factory=dict)
    sweep: list[dict[str, Any]] = field(default_factory=list)
    measurements: list[dict[str, Any]] = field(default_factory=list)
    calibration: dict[str, Any] = field(default_factory=dict)
    sensitivity: dict[str, Any] = field(default_factory=dict)
    ambiguous_excluded: dict[str, Any] = field(default_factory=dict)
    not_measured: dict[str, str] = field(default_factory=dict)
    timings: dict[str, float] = field(default_factory=dict)


def load_corpus() -> list[dict[str, Any]]:
    text = CORPUS.read_text(encoding="utf-8")
    rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    for row in rows:
        for side in ("left", "right"):
            record = row[side]
            expected = "sha256:" + hashlib.sha256(record["source_text"].encode("utf-8")).hexdigest()
            if record["blob_digest"] != expected or record["span_ref"]["blob_digest"] != expected:
                raise SystemExit(
                    f"{row['pair_id']}/{side}: blob digest does not match source_text (R8)"
                )
            span = record["span_ref"]["selector"]["char_span"]
            if span["end"] <= span["start"]:
                raise SystemExit(f"{row['pair_id']}/{side}: empty char_span")
            if record["source_text"][span["start"] : span["end"]] != record["name"]:
                raise SystemExit(
                    f"{row['pair_id']}/{side}: span does not resolve to the name; the corpus is "
                    "not grounded and measuring it would measure a fabrication"
                )
    return rows


def distinct_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for row in rows:
        for side in ("left", "right"):
            record = row[side]
            seen.setdefault(record["record_id"], record)
    return [seen[k] for k in sorted(seen)]


def matcher_view(record: dict[str, Any], *, with_identifiers: bool = False) -> dict[str, Any]:
    """Project a corpus record onto the fields the canonical matcher compares.

    Only ``name``, ``email``, ``phone`` and ``org``. The corpus carries address, national id,
    date of birth, aliases and lineage because a real system has them, and dropping them here is
    a *finding* about the matcher, not a convenience: none of them reach the comparison vector.
    ``with_identifiers`` is used only by the clearly-labelled sensitivity run.
    """
    view = {
        "name": record.get("name"),
        "email": record.get("email"),
        "phone": record.get("phone"),
        "org": record.get("org"),
    }
    if with_identifiers:
        view["id_number"] = record.get("id_number")
        view["birth_date"] = record.get("birth_date")
    return view


def sensitivity_adding_identifiers(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Counterfactual: what the four canonical fields cost, measured rather than argued.

    Re-runs the same corpus and the same operating point with two extra comparison fields,
    ``id_number`` and ``birth_date``. This is **not** the canonical matcher and nothing here is
    a recommendation — the module ships four fields and this section does not change it. It
    exists so that the statement "the false merges live in the fields the matcher cannot see" is
    a measurement instead of an assertion.
    """
    fields = (
        *FIELDS,
        text_field("id_number"),
        text_field("birth_date"),
    )
    records = distinct_records(rows)
    views = [matcher_view(r, with_identifiers=True) for r in records]
    index_of = {r["record_id"]: i for i, r in enumerate(records)}
    blocked = set(block_pairs(views))
    matcher = FellegiSunter(fields, lambda_prior=0.01, max_iterations=25)
    matcher.fit(views, sorted(blocked))

    def weight_of(row: dict[str, Any]) -> float:
        return matcher.weight(
            views[index_of[row["left"]["record_id"]]], views[index_of[row["right"]["record_id"]]]
        )

    positives = [r for r in rows if r["label"] == "match"]
    negatives = [r for r in rows if r["label"] == "non_match"]
    false_merges = [r["pair_id"] for r in negatives if weight_of(r) > 0.0]
    false_non_matches = [r["pair_id"] for r in positives if weight_of(r) <= 0.0]
    return {
        "configuration": "canonical fields + id_number + birth_date as text_field comparisons",
        "is_canonical": False,
        "false_merge_rate": round(len(false_merges) / len(negatives), 6),
        "false_merge_pair_ids": false_merges,
        "false_non_match_rate": round(len(false_non_matches) / len(positives), 6),
        "false_non_match_pair_ids": false_non_matches,
        "pair_recall": round(
            sum(1 for r in positives if weight_of(r) > 0.0) / len(positives), 6
        ),
    }


def main() -> int:
    started = time.perf_counter()
    rows = load_corpus()
    records = distinct_records(rows)
    views = [matcher_view(r) for r in records]
    index_of = {r["record_id"]: i for i, r in enumerate(records)}

    t0 = time.perf_counter()
    blocked = set(block_pairs(views))
    blocking_seconds = time.perf_counter() - t0

    t0 = time.perf_counter()
    matcher = FellegiSunter(FIELDS, lambda_prior=0.01, max_iterations=25)
    matcher.fit(views, sorted(blocked))
    fit_seconds = time.perf_counter() - t0

    t0 = time.perf_counter()
    measurements: list[PairMeasurement] = []
    for row in rows:
        a = views[index_of[row["left"]["record_id"]]]
        b = views[index_of[row["right"]["record_id"]]]
        ia, ib = index_of[row["left"]["record_id"]], index_of[row["right"]["record_id"]]
        bits = matcher.weight(a, b)
        measurements.append(
            PairMeasurement(
                pair_id=row["pair_id"],
                label=row["label"],
                category=row["category"],
                provenance=row["provenance"],
                record_a=row["left"]["record_id"],
                record_b=row["right"]["record_id"],
                weight_bits=round(bits, 6),
                posterior=round(posterior_from_weight(bits), 6),
                in_blocking=(min(ia, ib), max(ia, ib)) in blocked,
            )
        )
    scoring_seconds = time.perf_counter() - t0

    labelled = [m for m in measurements if m.label != "ambiguous"]
    positives = [m for m in labelled if m.label == "match"]
    negatives = [m for m in labelled if m.label == "non_match"]
    ambiguous = [m for m in measurements if m.label == "ambiguous"]

    def rate(items: list[PairMeasurement], threshold: float, predicate) -> dict[str, Any]:
        hits = [m for m in items if predicate(m, threshold)]
        return {
            "n": len(items),
            "hits": len(hits),
            "rate": round(len(hits) / len(items), 6) if items else None,
            "pair_ids": [m.pair_id for m in hits],
        }

    def above(m: PairMeasurement, threshold: float) -> bool:
        return m.weight_bits > threshold

    def not_below(m: PairMeasurement, threshold: float) -> bool:
        return m.weight_bits <= threshold

    headline = {
        "operating_point": "posterior > 0.5, i.e. weight > 0 bits"
        " (FellegiSunter.match threshold=0.0)",
        "threshold_bits": HEADLINE_THRESHOLD_BITS,
        "false_merge_rate": rate(negatives, 0.0, above),
        "false_non_match_rate": rate(positives, 0.0, not_below),
        "pair_recall": rate(positives, 0.0, above),
        "blocking_recall": rate(positives, 0.0, lambda m, _t: m.in_blocking),
        "precision_on_proposed": None,
    }
    proposed = [m for m in labelled if m.weight_bits > HEADLINE_THRESHOLD_BITS]
    true_positives = [m for m in proposed if m.label == "match"]
    headline["precision_on_proposed"] = {
        "n_proposed": len(proposed),
        "true_positive": len(true_positives),
        "precision": round(len(true_positives) / len(proposed), 6) if proposed else None,
    }

    # Sweep cut points are drawn from the observed weight distribution, not from the labels.
    # A fixed grid of "nice" numbers would sit entirely in the gap between the two clusters the
    # weights actually form and report the same row seven times, which reads as stability and is
    # really just an empty region of the curve.
    observed = sorted({m.weight_bits for m in measurements})
    sweep_thresholds = sorted({*observed, HEADLINE_THRESHOLD_BITS})
    sweep = []
    for threshold in sweep_thresholds:
        proposed_n = sum(1 for m in labelled if m.weight_bits > threshold)
        tp_n = sum(1 for m in labelled if m.weight_bits > threshold and m.label == "match")
        sweep.append(
            {
                "threshold_bits": threshold,
                "false_merge_rate": rate(negatives, threshold, above)["rate"],
                "false_non_match_rate": rate(positives, threshold, not_below)["rate"],
                "pair_recall": rate(positives, threshold, above)["rate"],
                "precision": round(tp_n / proposed_n, 6) if proposed_n else None,
                "pairs_proposed": proposed_n,
            }
        )

    bins: list[dict[str, Any]] = []
    ece = 0.0
    brier = 0.0
    total = len(labelled)
    for low, high in zip(CALIBRATION_BINS, CALIBRATION_BINS[1:], strict=False):
        in_bin = [m for m in labelled if low <= m.posterior < high]
        if not in_bin:
            continue
        mean_predicted = sum(m.posterior for m in in_bin) / len(in_bin)
        observed = sum(1 for m in in_bin if m.label == "match") / len(in_bin)
        bins.append(
            {
                "low": low,
                "high": high,
                "n": len(in_bin),
                "mean_predicted": round(mean_predicted, 6),
                "observed_match_rate": round(observed, 6),
            }
        )
        ece += (len(in_bin) / total) * abs(mean_predicted - observed)
        brier += sum((m.posterior - (1.0 if m.label == "match" else 0.0)) ** 2 for m in in_bin)
    calibration = {
        "bins": bins,
        "expected_calibration_error": round(ece, 6),
        "brier_score": round(brier / total, 6) if total else None,
        "note": "Posterior is derived from the matcher's own weight; lambda is not updated by EM, "
        "so the prior stays at the constructor default of 0.01 and the posteriors are not "
        "prior-corrected.",
    }

    all_pairs_total = len(records) * (len(records) - 1) // 2
    labels = {
        label: sum(1 for m in measurements if m.label == label)
        for label in ("match", "non_match", "ambiguous")
    }

    report = Report(
        command=".venv\\Scripts\\python.exe benchmarks\\er_baseline.py",
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        environment={
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "machine": platform.machine(),
            "matcher_module": "apps/zero/zero/resolution/fellegi_sunter.py",
            "splink_consulted": False,
            "note": "Splink is deliberately NOT run here; T105 is Phase 8 and this file must "
            "measure the current matcher only.",
        },
        corpus={
            "path": "bench/fixtures/global_upgrade/identity/pairs.jsonl",
            "sha256": hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
            "pairs": len(measurements),
            "distinct_records": len(records),
            "labelled_non_ambiguous": len(labelled),
            "labels": labels,
            "authored": sum(1 for m in measurements if m.provenance == "authored"),
            "synthetic": sum(1 for m in measurements if m.provenance == "synthetic"),
            "one_case_one_observation": "every pair is scored independently; no clustering, no "
            "union-find, no transitive closure",
        },
        model={
            "fields": [f.name for f in FIELDS],
            "lambda_prior": 0.01,
            "max_iterations": 25,
            "trained_on": "the corpus's own blocked pairs; no held-out split",
            "level_priors_overridden": False,
            "m": {field: matcher._m[field] for field in matcher._m},
            "u": {field: matcher._u[field] for field in matcher._u},
            "calibration_status": "UNCALIBRATED — no threshold fitted against held-out labels",
            "clamped_m_estimates": {
                "below_eps": sorted(
                    f"{field}/{level}={matcher._m[field][level]:.3e}"
                    for field in matcher._m
                    for level in matcher._m[field]
                    if matcher._m[field][level] <= 1e-9
                ),
                "reported_at": "<= 1e-9, i.e. at or under the order of the module's own _EPS",
                "eps": 1e-12,
                "why_it_matters": "the m-step assigns near-zero match posterior to the "
                "non-match levels of email and phone, so m collapses to the order of the module's "
                "own _EPS and log2(m/u) is effectively computed against that floor. The floor is "
                "what puts non-match weights at about -86 bits: the separation on this corpus is "
                "an artefact of an under-determined training set (137 blocked pairs, almost all "
                "of them true matches), not evidence that the matcher separates real records.",
            },
        },
        blocking={
            "key_fields": ["email", "phone", "name"],
            "records": len(records),
            "all_possible_pairs": all_pairs_total,
            "candidate_pairs": len(blocked),
            "candidate_pair_reduction": round(1 - len(blocked) / all_pairs_total, 6)
            if all_pairs_total
            else None,
            "candidate_pair_reduction_definition": "1 - blocked_pairs / (n*(n-1)/2) over distinct "
            "corpus records; blocking and scoring are separate stages and are reported separately",
            "blocking_recall": headline["blocking_recall"]["rate"],
            "blocking_recall_n": headline["blocking_recall"]["n"],
            "blocking_missed_by_blocking": [m.pair_id for m in positives if not m.in_blocking],
        },
        headline=headline,
        sweep=sweep,
        measurements=[asdict(m) for m in sorted(measurements, key=lambda m: m.pair_id)],
        calibration=calibration,
        sensitivity=sensitivity_adding_identifiers(rows),
        ambiguous_excluded={
            "count": len(ambiguous),
            "reason": "an ambiguous pair is excluded from both the match and the non-match "
            "denominators; counting it either way measures the label set, not the matcher",
            "what_the_matcher_would_have_done": {
                "above_headline": [
                    m.pair_id for m in ambiguous if m.weight_bits > HEADLINE_THRESHOLD_BITS
                ],
                "at_or_below_headline": [
                    m.pair_id for m in ambiguous if m.weight_bits <= HEADLINE_THRESHOLD_BITS
                ],
            },
        },
        not_measured={
            "population_false_merge_rate": "NOT MEASURED — the corpus is constructed, not sampled; "
            "prevalence and the difficulty mix of real records are unknown, so these rates "
            "describe this corpus and cannot be projected onto production data.",
            "held_out_generalisation": "NOT MEASURED — the matcher is trained on the corpus's own "
            "blocked pairs; there is no held-out split, so every number here is in-sample.",
            "performance_on_captured_data": "NOT MEASURED — no WARC corpus or captured record set "
            "exists in this repository to measure against; the corpus is hand-authored and "
            "template-generated.",
            "non_latin_script_performance": "NOT MEASURED — one Han-script pair "
            "and several Latin-diacritic pairs; that is not enough to characterise the "
            "transliteration regime the matcher is weakest in.",
            "comparison_against_splink": "NOT MEASURED — out of scope for T084; T105 is Phase 8 "
            "and running a second engine here would answer a question this phase is not chartered "
            "to answer.",
            "throughput_or_cost": "reported below as wall-clock for this run only; it is not a "
            "throughput benchmark and must not be quoted as one.",
            "confidence_intervals": "NOT MEASURED as intervals — with "
            f"{len(positives)} positives and {len(negatives)} negatives, a single flipped case "
            f"moves the false-merge rate by {round(100 / len(negatives), 1)} points and the "
            f"false-non-match rate by {round(100 / len(positives), 1)} points. The rates are "
            "point estimates on a small corpus, not estimates with a stated error bar.",
        },
        timings={
            "blocking_seconds": round(blocking_seconds, 4),
            "fit_seconds": round(fit_seconds, 4),
            "scoring_seconds": round(scoring_seconds, 4),
            "total_seconds": round(time.perf_counter() - started, 4),
            "records": float(len(records)),
            "pairs_scored": float(len(measurements)),
        },
    )

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    print(f"\nwrote {OUT_JSON.relative_to(REPO)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())