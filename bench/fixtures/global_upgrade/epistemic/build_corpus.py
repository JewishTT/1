"""Build the frozen epistemic fixture corpus (spec 030 T064, US3).

Every case is ``provenance: "synthetic"`` and that is not a hedge, it is the accurate
description of the work: **nothing here was crawled**. No upstream source was fetched, no
registry was queried, no licence was read off a real terms page. Each case is a
hand-constructed description of a situation the epistemic layer has to survive, and the
``source_licence`` field says ``synthetic`` on every one of them for exactly that reason.

Writing ``authored`` or naming a real source here would be a different kind of dishonesty
from the one this corpus exists to catch: it would put an implied upstream claim into a
record whose entire subject is whether claims are supported. A fixture that asserted an
uncorroborated provenance would be the defect with a test suite attached.

Each case states five things, and the fifth is why this file exists:

* ``ground_truth`` -- what is actually the case in the world, independently of what any
  system concluded.
* ``expected`` -- the :class:`context.epistemic.ResearchState` axes, the contract-03
  ``StageStatus`` and the contract-07 ``ErrorCode`` the platform must produce.
* ``prohibited_false_inference`` -- the inference a reader is most likely to draw and
  **must not**, with the reason and a machine-checkable assertion name. The tests read
  that assertion name and evaluate it against the real answer, so the corpus cannot
  drift into documentation.
* ``applicable_measurement`` -- the measurement that *would* establish detection power for
  this case's source class, and its ``status``. Every one says
  ``not_performed_for_this_fixture``: the method is named so a reader knows what an
  undeclared power is costing, and the status is honest that it was not carried out.
* ``source_licence`` -- ``synthetic``. On every case. Never a licence nobody granted.

Run::

    python build_corpus.py             # writes cases.jsonl
    python build_corpus.py --verify    # re-derives and compares; non-zero exit on drift
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
CORPUS = HERE / "cases.jsonl"

#: The measurement that establishes a detection power, per source class. Named rather
#: than performed: it is what a real catalogue entry would have to cite, and recording it
#: is what lets a reader see exactly what is missing when ``detection_power`` is null.
MEASURES: dict[str, dict[str, str]] = {
    "closed_registry": {
        "quantity": "detection_power",
        "method": (
            "seeded known-positive trial against a private shard: plant N records the "
            "platform is entitled to see, run the same query shape, report the fraction "
            "returned. Requires an account, so it is not available to an unattended run"
        ),
    },
    "full_text_index": {
        "quantity": "detection_power",
        "method": (
            "recall against a labelled held-out set of documents known to contain the "
            "target string, at the same query shape and the same freshness window"
        ),
    },
    "structured_endpoint": {
        "quantity": "detection_power",
        "method": (
            "exhaustive enumeration over a universe the endpoint itself declares complete, "
            "cross-checked against a second enumeration of the same universe"
        ),
    },
    "synthetic_unmeasured": {
        "quantity": "detection_power",
        "method": (
            "none available. The source is constructed for this corpus and has no "
            "enumeration anyone can check it against, which is why its power is undeclared"
        ),
    },
}


def _source(
    source_id: str,
    name: str,
    *,
    measure_class: str,
    detection_power: float | None = None,
    detection_power_method: str = "",
    coverage_estimate: float | None = None,
    reachable: bool = True,
    supports_query_kind: bool = True,
    capability_available: bool = True,
    errors_accounted: bool = True,
    budget_truncated: bool = False,
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "name": name,
        "reaches_platform": reachable,
        "supports_query_kind": supports_query_kind,
        "capability_available": capability_available,
        "errors_accounted": errors_accounted,
        "budget_truncated": budget_truncated,
        "coverage_estimate": coverage_estimate,
        "declared_detection_power": detection_power,
        "detection_power_method": detection_power_method,
        "measurement_class": measure_class,
        "licence": "synthetic",
    }


def _proposition(
    subject: str, predicate: str, obj: str, scope: str = ""
) -> dict[str, str]:
    return {"subject": subject, "predicate": predicate, "object": obj, "scope": scope}


def _no_inference(inference: str, because: str, assertion: str) -> dict[str, str]:
    return {"inference": inference, "because": because, "assertion": assertion}


#: The eight case families T064 requires, plus the four the independent test names and
#: the off-anchor records that prove the model is dimensions rather than an enum.
#:
#: Built by explicit literal rather than by a loop over the expected answer, because a
#: generator that derived the expectation from the case would make the corpus unable to
#: fail. Each expectation is written down independently and the tests compare.

CASES: list[dict[str, Any]] = [
    # -- positive only -------------------------------------------------------
    {
        "case_id": "EPI-POS-01",
        "category": "positive_only",
        "provenance": "synthetic",
        "generator": "CASES['EPI-POS-01']",
        "source_licence": "synthetic",
        "ground_truth": (
            "One reachable source states the proposition affirmatively. Nothing anywhere "
            "denies it. It is true."
        ),
        "sources": [_source("SRC-SYN-P1", "synthetic bulletin A", measure_class="full_text_index",
                            detection_power=0.91, detection_power_method="held-out recall",
                            coverage_estimate=0.88)],
        "proposition": _proposition("Kestrel Logistics", "beneficial_owner", "M. Aldrin"),
        "evidence": [{"ref": "EVD-1", "positive": True, "source_id": "SRC-SYN-P1"}],
        "expected": {
            "research_state": {
                "disposition": "completed", "query": "ran_matched", "truth_state": "true_only",
                "absence": "not_applicable", "evidence": "observed", "scope": "undeclared",
            },
            "research_state_name": "positive_support",
            "stage_status": "succeeded",
            "error_code": None,
            "may_claim_universal_negative": False,
        },
        "prohibited_false_inference": _no_inference(
            "this source is exhaustive over the world",
            "one supporting source says nothing about what the rest of the world contains",
            "may_claim_universal_negative",
        ),
        "applicable_measurement": {"class": "full_text_index", **MEASURES["full_text_index"],
                                   "status": "not_performed_for_this_fixture"},
    },
    {
        "case_id": "EPI-POS-02",
        "category": "positive_only",
        "provenance": "synthetic",
        "generator": "CASES['EPI-POS-02']",
        "source_licence": "synthetic",
        "ground_truth": (
            "Two sources agree affirmatively and are independent of each other. It is true, "
            "and it is corroborated by two separate observations."
        ),
        "sources": [
            _source("SRC-SYN-P2", "synthetic bulletin B", measure_class="full_text_index",
                    detection_power=0.88, detection_power_method="held-out recall",
                    coverage_estimate=0.81),
            _source("SRC-SYN-P3", "synthetic bulletin C", measure_class="full_text_index",
                    detection_power=0.86, detection_power_method="held-out recall",
                    coverage_estimate=0.79),
        ],
        "proposition": _proposition("Kestrel Logistics", "beneficial_owner", "M. Aldrin"),
        "evidence": [
            {"ref": "EVD-1", "positive": True, "source_id": "SRC-SYN-P2"},
            {"ref": "EVD-2", "positive": True, "source_id": "SRC-SYN-P3"},
        ],
        "expected": {
            "research_state": {
                "disposition": "completed", "query": "ran_matched", "truth_state": "true_only",
                "absence": "not_applicable", "evidence": "observed", "scope": "undeclared",
            },
            "research_state_name": "positive_support",
            "stage_status": "succeeded",
            "error_code": None,
            "may_claim_universal_negative": False,
        },
        "prohibited_false_inference": _no_inference(
            "two agreeing sources make this exhaustive",
            "corroboration is agreement about what was found, not a statement about what "
            "was not",
            "may_claim_universal_negative",
        ),
        "applicable_measurement": {"class": "full_text_index", **MEASURES["full_text_index"],
                                   "status": "not_performed_for_this_fixture"},
    },
    # -- negative only -------------------------------------------------------
    {
        "case_id": "EPI-NEG-01",
        "category": "negative_only",
        "provenance": "synthetic",
        "generator": "CASES['EPI-NEG-01']",
        "source_licence": "synthetic",
        "ground_truth": (
            "One reachable source states the proposition as false, as an observation rather "
            "than as an exhaustive denial. It is false, on the evidence available."
        ),
        "sources": [_source("SRC-SYN-N1", "synthetic ledger A", measure_class="full_text_index",
                            detection_power=0.84, detection_power_method="held-out recall",
                            coverage_estimate=0.82)],
        "proposition": _proposition("Arden Freight", "beneficial_owner", "P. Okonkwo"),
        "evidence": [{"ref": "EVD-3", "positive": False, "source_id": "SRC-SYN-N1"}],
        "expected": {
            "research_state": {
                "disposition": "completed", "query": "ran_matched", "truth_state": "false_only",
                "absence": "not_applicable", "evidence": "observed", "scope": "undeclared",
            },
            "research_state_name": "negative_support",
            "stage_status": "succeeded",
            "error_code": None,
            "may_claim_universal_negative": False,
        },
        "prohibited_false_inference": _no_inference(
            "this is a refutation",
            "negative support is evidence leaning false; a refutation is a checked denial, "
            "and the two are separate states that must not be merged",
            "is_refuted",
        ),
        "applicable_measurement": {"class": "full_text_index", **MEASURES["full_text_index"],
                                   "status": "not_performed_for_this_fixture"},
    },
    {
        "case_id": "EPI-NEG-02",
        "category": "negative_only",
        "provenance": "synthetic",
        "generator": "CASES['EPI-NEG-02']",
        "source_licence": "synthetic",
        "ground_truth": (
            "A source explicitly denies the proposition: the entity is stated not to have "
            "the relation. This is a refutation, not merely negative support."
        ),
        "sources": [_source("SRC-SYN-N2", "synthetic registry denial", measure_class="structured_endpoint",
                            detection_power=0.97, detection_power_method="dual enumeration",
                            coverage_estimate=0.99)],
        "proposition": _proposition("Halden Group", "beneficial_owner", "R. Vasse"),
        "evidence": [{"ref": "EVD-4", "positive": False, "source_id": "SRC-SYN-N2",
                      "explicit_denial": True}],
        "expected": {
            "research_state": {
                "disposition": "completed", "query": "ran_matched", "truth_state": "false_only",
                "absence": "not_applicable", "evidence": "refuted", "scope": "undeclared",
            },
            "research_state_name": "refuted",
            "stage_status": "succeeded",
            "error_code": None,
            "may_claim_universal_negative": False,
        },
        "prohibited_false_inference": _no_inference(
            "a denial is the same as a universal negative",
            "one registry denied this relation; the denial is about the relation, not "
            "about the entity's existence anywhere",
            "may_claim_universal_negative",
        ),
        "applicable_measurement": {"class": "structured_endpoint", **MEASURES["structured_endpoint"],
                                   "status": "not_performed_for_this_fixture"},
    },
    # -- both / contradiction ------------------------------------------------
    {
        "case_id": "EPI-BOTH-01",
        "category": "both",
        "provenance": "synthetic",
        "generator": "CASES['EPI-BOTH-01']",
        "source_licence": "synthetic",
        "ground_truth": (
            "Two independent sources state opposite things about the same proposition. One "
            "is true and the other is not, and the platform has no basis for choosing."
        ),
        "sources": [
            _source("SRC-SYN-B1", "synthetic bulletin D", measure_class="full_text_index",
                    detection_power=0.9, detection_power_method="held-out recall",
                    coverage_estimate=0.83),
            _source("SRC-SYN-B2", "synthetic bulletin E", measure_class="full_text_index",
                    detection_power=0.9, detection_power_method="held-out recall",
                    coverage_estimate=0.85),
        ],
        "proposition": _proposition("Corvid Marine", "beneficial_owner", "T. Bramley"),
        "evidence": [
            {"ref": "EVD-5", "positive": True, "source_id": "SRC-SYN-B1", "observed_at": "2026-02-01"},
            {"ref": "EVD-6", "positive": False, "source_id": "SRC-SYN-B2", "observed_at": "2026-02-02"},
        ],
        "expected": {
            "research_state": {
                "disposition": "completed", "query": "ran_matched", "truth_state": "both",
                "absence": "not_applicable", "evidence": "conflicted", "scope": "undeclared",
            },
            "research_state_name": "both_contradiction",
            "stage_status": "succeeded",
            "error_code": None,
            "may_claim_universal_negative": False,
        },
        "prohibited_false_inference": _no_inference(
            "the newer source wins",
            "recency is a reason a record was written later, not evidence that it is true",
            "contradiction_resolved",
        ),
        "applicable_measurement": {"class": "full_text_index", **MEASURES["full_text_index"],
                                   "status": "not_performed_for_this_fixture"},
    },
    {
        "case_id": "EPI-BOTH-02",
        "category": "both",
        "provenance": "synthetic",
        "generator": "CASES['EPI-BOTH-02']",
        "source_licence": "synthetic",
        "ground_truth": (
            "Three sources say one thing, one says the opposite. The minority is right. A "
            "platform that resolves by document count would get this case wrong, which is "
            "why it is in the corpus rather than left to the argument."
        ),
        "sources": [
            _source(f"SRC-SYN-B3{i}", f"synthetic bulletin F{i}", measure_class="full_text_index",
                    detection_power=0.87, detection_power_method="held-out recall",
                    coverage_estimate=0.8) for i in range(3)
        ] + [_source("SRC-SYN-B30", "synthetic bulletin G", measure_class="full_text_index",
                     detection_power=0.93, detection_power_method="held-out recall",
                     coverage_estimate=0.92)],
        "proposition": _proposition("Corvid Marine", "beneficial_owner", "T. Bramley"),
        "evidence": [
            {"ref": "EVD-7", "positive": True, "source_id": "SRC-SYN-B30"},
            {"ref": "EVD-8", "positive": False, "source_id": "SRC-SYN-B31"},
            {"ref": "EVD-9", "positive": False, "source_id": "SRC-SYN-B32"},
        ] + [
            {"ref": f"EVD-1{i}", "positive": True, "source_id": f"SRC-SYN-B3{i}"} for i in range(3)
        ],
        "expected": {
            "research_state": {
                "disposition": "completed", "query": "ran_matched", "truth_state": "both",
                "absence": "not_applicable", "evidence": "conflicted", "scope": "undeclared",
            },
            "research_state_name": "both_contradiction",
            "stage_status": "succeeded",
            "error_code": None,
            "may_claim_universal_negative": False,
        },
        "prohibited_false_inference": _no_inference(
            "three sources outvote one",
            "a document count measures how many times something was written, not how many "
            "independent observations were made; the four sources here share one origin and "
            "are one observation in four hats",
            "contradiction_resolved",
        ),
        "applicable_measurement": {"class": "full_text_index", **MEASURES["full_text_index"],
                                   "status": "not_performed_for_this_fixture"},
    },
    {
        "case_id": "EPI-BOTH-03",
        "category": "both",
        "provenance": "synthetic",
        "generator": "CASES['EPI-BOTH-03']",
        "source_licence": "synthetic",
        "ground_truth": (
            "One source scores 0.97 and three score 0.21. The high score is a property of "
            "the scoring function applied to that document, not of the world."
        ),
        "sources": [
            _source(f"SRC-SYN-B4{i}", f"synthetic bulletin H{i}", measure_class="full_text_index",
                    coverage_estimate=0.8) for i in range(3)
        ] + [_source("SRC-SYN-B40", "synthetic bulletin I", measure_class="full_text_index",
                     coverage_estimate=0.9)],
        "proposition": _proposition("Corvid Marine", "beneficial_owner", "T. Bramley"),
        "evidence": [
            {"ref": "EVD-20", "positive": False, "source_id": "SRC-SYN-B40", "score": 0.21},
            {"ref": "EVD-21", "positive": False, "source_id": "SRC-SYN-B41", "score": 0.21},
            {"ref": "EVD-22", "positive": False, "source_id": "SRC-SYN-B42", "score": 0.21},
            {"ref": "EVD-23", "positive": True, "source_id": "SRC-SYN-B43", "score": 0.97},
        ],
        "expected": {
            "research_state": {
                "disposition": "completed", "query": "ran_matched", "truth_state": "both",
                "absence": "not_applicable", "evidence": "conflicted", "scope": "undeclared",
            },
            "research_state_name": "both_contradiction",
            "stage_status": "succeeded",
            "error_code": None,
            "may_claim_universal_negative": False,
        },
        "prohibited_false_inference": _no_inference(
            "the 0.97 source outranks the three 0.21 sources",
            "a score is a ranking of documents by a declared policy; it is not a claim "
            "about which of two incompatible statements is true, and no policy version may "
            "convert it into one",
            "contradiction_resolved",
        ),
        "applicable_measurement": {"class": "full_text_index", **MEASURES["full_text_index"],
                                   "status": "not_performed_for_this_fixture"},
    },
    # -- unknown predicate ---------------------------------------------------
    {
        "case_id": "EPI-UNK-01",
        "category": "unknown",
        "provenance": "synthetic",
        "generator": "CASES['EPI-UNK-01']",
        "source_licence": "synthetic",
        "ground_truth": (
            "A document states a relation whose predicate the platform's vocabulary does not "
            "contain. The words are 'originator of'. The relation exists; the platform does "
            "not have a name for it."
        ),
        "sources": [_source("SRC-SYN-U1", "synthetic filing", measure_class="full_text_index",
                            detection_power=0.8, detection_power_method="held-out recall",
                            coverage_estimate=0.7)],
        "proposition": _proposition("Thornbury PLC", "UNMAPPED", "J. Skead"),
        "predicate_raw": {
            "label": "originator of", "origin": "observed_surface",
            "span_ref": "SEG-7", "char_start": 412, "char_end": 425,
        },
        "evidence": [{"ref": "EVD-30", "positive": True, "source_id": "SRC-SYN-U1"}],
        "expected": {
            "research_state": {
                "disposition": "completed", "query": "ran_matched", "truth_state": "true_only",
                "absence": "not_applicable", "evidence": "observed", "scope": "undeclared",
            },
            "research_state_name": "positive_support",
            "stage_status": "succeeded",
            "error_code": None,
            "predicate_resolution_state": "unknown",
            "predicate_label": "originator of",
            "may_claim_universal_negative": False,
        },
        "prohibited_false_inference": _no_inference(
            "the predicate is unmapped so the relation can be discarded",
            "dropping it makes 'we did not understand it' indistinguishable from 'the "
            "relation does not exist', which is the silent drop FR-013 forbids",
            "predicate_dropped",
        ),
        "applicable_measurement": {"class": "full_text_index", **MEASURES["full_text_index"],
                                   "status": "not_performed_for_this_fixture"},
    },
    {
        "case_id": "EPI-UNK-02",
        "category": "unknown",
        "provenance": "synthetic",
        "generator": "CASES['EPI-UNK-02']",
        "source_licence": "synthetic",
        "ground_truth": (
            "The relation appears only as a table column header. There is no trigger phrase, "
            "so there is no span. The label must survive anyway, and the absence of a span "
            "must be reported as the absence of a span rather than filled in from elsewhere."
        ),
        "sources": [_source("SRC-SYN-U2", "synthetic spreadsheet export",
                            measure_class="synthetic_unmeasured")],
        "proposition": _proposition("Thornbury PLC", "UNMAPPED", "J. Skead"),
        "predicate_raw": {
            "label": "Originating counterparty", "origin": "observed_surface",
            "span_ref": "", "char_start": None, "char_end": None,
        },
        "evidence": [{"ref": "EVD-31", "positive": True, "source_id": "SRC-SYN-U2"}],
        "expected": {
            "research_state": {
                "disposition": "completed", "query": "ran_matched", "truth_state": "true_only",
                "absence": "not_applicable", "evidence": "observed", "scope": "undeclared",
            },
            "research_state_name": "positive_support",
            "stage_status": "succeeded",
            "error_code": None,
            "predicate_resolution_state": "unknown",
            "predicate_label": "Originating counterparty",
            "may_claim_universal_negative": False,
        },
        "prohibited_false_inference": _no_inference(
            "with no span there is no predicate",
            "a header names the relation just as a sentence does; borrowing another field's "
            "span to fill the gap would be a fabricated citation",
            "predicate_dropped",
        ),
        "applicable_measurement": {"class": "synthetic_unmeasured",
                                   **MEASURES["synthetic_unmeasured"],
                                   "status": "not_performed_for_this_fixture"},
    },
    # -- unsupported source --------------------------------------------------
    {
        "case_id": "EPI-UNSUP-01",
        "category": "unsupported_source",
        "provenance": "synthetic",
        "generator": "CASES['EPI-UNSUP-01']",
        "source_licence": "synthetic",
        "ground_truth": (
            "The request is well formed and the source is reachable, but the source's "
            "parser cannot express this format. The system cannot represent the query; it "
            "did not run and match nothing."
        ),
        "sources": [_source("SRC-SYN-X1", "synthetic binary export", measure_class="synthetic_unmeasured",
                            reachable=True, supports_query_kind=False)],
        "proposition": _proposition("Meridian Foods", "beneficial_owner", "S. Ilyin"),
        "evidence": [],
        "expected": {
            "research_state": {
                "disposition": "unrepresentable", "query": "unrunnable", "truth_state": "neither",
                "absence": "not_applicable", "evidence": "none", "scope": "undeclared",
            },
            "research_state_name": "query_unsupported",
            "stage_status": "unsupported",
            "error_code": "UNSUPPORTED_QUERY",
            "may_claim_universal_negative": False,
        },
        "prohibited_false_inference": _no_inference(
            "the source returned nothing so the entity is not there",
            "a parser that cannot process a format returns unsupported; it does not return "
            "a zero-length document with status succeeded",
            "may_claim_universal_negative",
        ),
        "applicable_measurement": {"class": "synthetic_unmeasured",
                                   **MEASURES["synthetic_unmeasured"],
                                   "status": "not_performed_for_this_fixture"},
    },
    {
        "case_id": "EPI-UNSUP-02",
        "category": "unsupported_source",
        "provenance": "synthetic",
        "generator": "CASES['EPI-UNSUP-02']",
        "source_licence": "synthetic",
        "ground_truth": (
            "No operator in the registry provides the capability the query needs. Nothing "
            "was attempted, so nothing failed either."
        ),
        "sources": [_source("SRC-SYN-X2", "synthetic registry with no such operator",
                            measure_class="synthetic_unmeasured",
                            capability_available=False)],
        "proposition": _proposition("Meridian Foods", "beneficial_owner", "S. Ilyin"),
        "evidence": [],
        "expected": {
            "research_state": {
                "disposition": "unrepresentable", "query": "unrunnable", "truth_state": "neither",
                "absence": "not_applicable", "evidence": "none", "scope": "undeclared",
            },
            "research_state_name": "query_unsupported",
            "stage_status": "blocked",
            "error_code": "CAPABILITY_UNAVAILABLE",
            "may_claim_universal_negative": False,
        },
        "prohibited_false_inference": _no_inference(
            "no capability means no result means nothing is there",
            "capability unavailability is a statement about the platform, and conflating it "
            "with a zero-result is how a missing operator becomes a negative finding",
            "may_claim_universal_negative",
        ),
        "applicable_measurement": {"class": "synthetic_unmeasured",
                                   **MEASURES["synthetic_unmeasured"],
                                   "status": "not_performed_for_this_fixture"},
    },
    # -- failed source -------------------------------------------------------
    {
        "case_id": "EPI-FAIL-01",
        "category": "failed_source",
        "provenance": "synthetic",
        "generator": "CASES['EPI-FAIL-01']",
        "source_licence": "synthetic",
        "ground_truth": (
            "The host does not resolve. The platform never reached the source, so it saw "
            "nothing, and 'saw nothing because the door was locked' is not evidence about "
            "the contents of the room."
        ),
        "sources": [_source("SRC-SYN-F1", "synthetic unreachable host",
                            measure_class="synthetic_unmeasured", reachable=False)],
        "proposition": _proposition("Ostara Metals", "beneficial_owner", "L. Fenwick"),
        "evidence": [],
        "expected": {
            "research_state": {
                "disposition": "failed", "query": "not_run", "truth_state": "neither",
                "absence": "informational_only", "evidence": "none", "scope": "undeclared",
            },
            "research_state_name": "source_unavailable",
            "stage_status": "failed",
            "error_code": "SOURCE_UNAVAILABLE",
            "may_claim_universal_negative": False,
        },
        "prohibited_false_inference": _no_inference(
            "the source is down so the entity is not in it",
            "an unreachable source saw nothing at all; a transport failure is not a "
            "coverage statement and never was",
            "may_claim_universal_negative",
        ),
        "applicable_measurement": {"class": "synthetic_unmeasured",
                                   **MEASURES["synthetic_unmeasured"],
                                   "status": "not_performed_for_this_fixture"},
    },
    {
        "case_id": "EPI-FAIL-02",
        "category": "failed_source",
        "provenance": "synthetic",
        "generator": "CASES['EPI-FAIL-02']",
        "source_licence": "synthetic",
        "ground_truth": (
            "The source responded for two hours and then timed out mid-enumeration. "
            "Partial enumeration is partial coverage, and the untruncated remainder is "
            "unknown rather than empty."
        ),
        "sources": [_source("SRC-SYN-F2", "synthetic slow endpoint",
                            measure_class="structured_endpoint", reachable=True,
                            errors_accounted=True, budget_truncated=True)],
        "proposition": _proposition("Ostara Metals", "beneficial_owner", "L. Fenwick"),
        "evidence": [],
        "expected": {
            "research_state": {
                "disposition": "bounded", "query": "ran_matched", "truth_state": "neither",
                "absence": "informational_only", "evidence": "inconclusive",
                "scope": "undeclared",
            },
            "research_state_name": "blocked_partial",
            "stage_status": "partial",
            "error_code": "PARTIAL_OUTPUT",
            "may_claim_universal_negative": False,
        },
        "prohibited_false_inference": _no_inference(
            "the timeout means the rest of the corpus is empty",
            "the untruncated remainder was never read; a bound on the search is a bound on "
            "the search, not a fact about the world",
            "may_claim_universal_negative",
        ),
        "applicable_measurement": {"class": "structured_endpoint", **MEASURES["structured_endpoint"],
                                   "status": "not_performed_for_this_fixture"},
    },
    # -- searched no result, KNOWN detection power ----------------------------
    {
        "case_id": "EPI-SNR-KNOWN-01",
        "category": "searched_no_result_known_detection_power",
        "provenance": "synthetic",
        "generator": "CASES['EPI-SNR-KNOWN-01']",
        "source_licence": "synthetic",
        "ground_truth": (
            "A source that has declared it would have found the thing was asked, and found "
            "nothing. The honest statement is 'searched, no result'. Declared power plus "
            "declared coverage is what would raise it further; it is not raised here."
        ),
        "sources": [_source("SRC-SYN-K1", "synthetic closed registry",
                            measure_class="closed_registry", detection_power=0.93,
                            detection_power_method="seeded known-positive trial",
                            coverage_estimate=0.91)],
        "proposition": _proposition("Pellworth Holdings", "beneficial_owner", "C. Nunes"),
        "evidence": [],
        # The control for EPI-SNR-UNKNOWN-01: same disposition, same query axis, same
        # truth state, same coverage -- the *only* difference is that this source has
        # declared what it would have found and that one never has. It is deliberately
        # NOT a qualified absence, because FR-014's other four preconditions (declared
        # universe, freshness, capability availability, untruncated budget) are unmet
        # here and this case does not claim them. EPI-SNR-KNOWN-02 is the case that does.
        "expected": {
            "research_state": {
                "disposition": "completed", "query": "ran_zero_match", "truth_state": "neither",
                "absence": "searched_no_result", "evidence": "none", "scope": "undeclared",
            },
            "research_state_name": "searched_no_result",
            "stage_status": "no_result",
            "error_code": "EXPECTED_NO_RESULT",
            "may_claim_universal_negative": False,
        },
        "prohibited_false_inference": _no_inference(
            "declared detection power alone makes this a qualified absence",
            "FR-014 names six preconditions; a source's power is one of them and this case "
            "declares the universe and coverage only",
            "is_qualified_absence",
        ),
        "applicable_measurement": {"class": "closed_registry", **MEASURES["closed_registry"],
                                   "status": "not_performed_for_this_fixture"},
    },
    {
        "case_id": "EPI-SNR-KNOWN-02",
        "category": "searched_no_result_known_detection_power",
        "provenance": "synthetic",
        "generator": "CASES['EPI-SNR-KNOWN-02']",
        "source_licence": "synthetic",
        "ground_truth": (
            "Every FR-014 precondition is declared: a complete universe, coverage above "
            "threshold, freshness stated, capability present, budget untruncated, and a "
            "source that has declared its detection power. 'It does not exist' is available."
        ),
        "sources": [_source("SRC-SYN-K2", "synthetic complete registry",
                            measure_class="closed_registry", detection_power=0.94,
                            detection_power_method="seeded known-positive trial",
                            coverage_estimate=0.96)],
        "proposition": _proposition("Pellworth Holdings", "beneficial_owner", "C. Nunes"),
        "evidence": [],
        "all_fr014_preconditions_declared": True,
        "expected": {
            "research_state": {
                "disposition": "completed", "query": "ran_zero_match", "truth_state": "neither",
                "absence": "qualified_absence", "evidence": "none", "scope": "undeclared",
            },
            "research_state_name": "qualified_absence",
            "stage_status": "no_result",
            "error_code": "EXPECTED_NO_RESULT",
            "may_claim_universal_negative": True,
        },
        "prohibited_false_inference": _no_inference(
            "this generalises beyond the declared universe",
            "the qualified absence holds for the universe that was declared and for no other",
            "none",
        ),
        "applicable_measurement": {"class": "closed_registry", **MEASURES["closed_registry"],
                                   "status": "not_performed_for_this_fixture"},
    },
    # -- searched no result, UNKNOWN detection power --------------------------
    {
        "case_id": "EPI-SNR-UNKNOWN-01",
        "category": "searched_no_result_unknown_detection_power",
        "provenance": "synthetic",
        "generator": "CASES['EPI-SNR-UNKNOWN-01']",
        "source_licence": "synthetic",
        "ground_truth": (
            "The source was searched, the query executed, and nothing matched. The source "
            "has never declared what it would have found. This is the centre of the corpus: "
            "the only defensible statement is what was observed, never that the thing is "
            "absent."
        ),
        "sources": [_source("SRC-SYN-U-01", "synthetic unmeasured corpus",
                            measure_class="synthetic_unmeasured", coverage_estimate=0.9)],
        "proposition": _proposition("Pellworth Holdings", "beneficial_owner", "C. Nunes"),
        "evidence": [],
        "expected": {
            "research_state": {
                "disposition": "completed", "query": "ran_zero_match", "truth_state": "neither",
                "absence": "informational_only", "evidence": "none", "scope": "undeclared",
            },
            "research_state_name": None,
            "stage_status": "no_result",
            "error_code": "DETECTION_POWER_UNKNOWN",
            "may_claim_universal_negative": False,
        },
        "prohibited_false_inference": _no_inference(
            "C. Nunes does not exist",
            "the source never said it would have found them. Coverage of 0.9 says how much "
            "of the source was read, not what the source can see; a source indexed from "
            "filings alone has a coverage of 0.9 over filings and 0 over anything else",
            "may_claim_universal_negative",
        ),
        "applicable_measurement": {"class": "synthetic_unmeasured",
                                   **MEASURES["synthetic_unmeasured"],
                                   "status": "not_performed_for_this_fixture"},
    },
    {
        "case_id": "EPI-SNR-UNKNOWN-02",
        "category": "searched_no_result_unknown_detection_power",
        "provenance": "synthetic",
        "generator": "CASES['EPI-SNR-UNKNOWN-02']",
        "source_licence": "synthetic",
        "ground_truth": (
            "The source declared a detection power of 0.2. That is a declared number and "
            "it is still far too low to underwrite an absence: it says the search would miss "
            "four of every five things that were there."
        ),
        "sources": [_source("SRC-SYN-U-03", "synthetic weak index",
                            measure_class="full_text_index", detection_power=0.2,
                            detection_power_method="held-out recall", coverage_estimate=0.97)],
        "proposition": _proposition("Pellworth Holdings", "beneficial_owner", "C. Nunes"),
        "evidence": [],
        "expected": {
            "research_state": {
                "disposition": "completed", "query": "ran_zero_match", "truth_state": "neither",
                "absence": "informational_only", "evidence": "none", "scope": "undeclared",
            },
            "research_state_name": None,
            "stage_status": "no_result",
            "error_code": "DETECTION_POWER_UNKNOWN",
            "may_claim_universal_negative": False,
        },
        "prohibited_false_inference": _no_inference(
            "it declared a power, so it counts",
            "declared is not the same as sufficient; 0.2 is a declaration that the search "
            "was mostly blind, and FR-014's threshold is what decides, not the presence of "
            "a number",
            "may_claim_universal_negative",
        ),
        "applicable_measurement": {"class": "full_text_index", **MEASURES["full_text_index"],
                                   "status": "not_performed_for_this_fixture"},
    },
    {
        "case_id": "EPI-SNR-UNKNOWN-03",
        "category": "searched_no_result_unknown_detection_power",
        "provenance": "synthetic",
        "generator": "CASES['EPI-SNR-UNKNOWN-03']",
        "source_licence": "synthetic",
        "ground_truth": (
            "Two sources were searched and returned nothing. Neither declared a power, so "
            "neither can underwrite the other's silence; two unquantified searches add up "
            "to one unquantified search."
        ),
        "sources": [
            _source("SRC-SYN-U-04", "synthetic unmeasured corpus A",
                    measure_class="synthetic_unmeasured", coverage_estimate=0.85),
            _source("SRC-SYN-U-05", "synthetic unmeasured corpus B",
                    measure_class="synthetic_unmeasured", coverage_estimate=0.9),
        ],
        "proposition": _proposition("Pellworth Holdings", "beneficial_owner", "C. Nunes"),
        "evidence": [],
        "expected": {
            "research_state": {
                "disposition": "completed", "query": "ran_zero_match", "truth_state": "neither",
                "absence": "informational_only", "evidence": "none", "scope": "undeclared",
            },
            "research_state_name": None,
            "stage_status": "no_result",
            "error_code": "DETECTION_POWER_UNKNOWN",
            "may_claim_universal_negative": False,
        },
        "prohibited_false_inference": _no_inference(
            "two independent unquantified searches establish an absence",
            "independence multiplies evidence about what was found; it cannot multiply a "
            "power that neither source declared",
            "may_claim_universal_negative",
        ),
        "applicable_measurement": {"class": "synthetic_unmeasured",
                                   **MEASURES["synthetic_unmeasured"],
                                   "status": "not_performed_for_this_fixture"},
    },
    # -- not investigated / nothing collected --------------------------------
    {
        "case_id": "EPI-NOTINV-01",
        "category": "unknown_not_investigated",
        "provenance": "synthetic",
        "generator": "CASES['EPI-NOTINV-01']",
        "source_licence": "synthetic",
        "ground_truth": (
            "Nobody has looked. There is no observation, no source contact and no coverage "
            "statement. This is not a negative finding; it is the absence of one."
        ),
        "sources": [],
        "proposition": _proposition("Vantor Biotech", "beneficial_owner", "N. Achebe"),
        "evidence": [],
        "expected": {
            "research_state": {
                "disposition": "not_investigated", "query": "not_run", "truth_state": "neither",
                "absence": "not_applicable", "evidence": "none", "scope": "undeclared",
            },
            "research_state_name": "unknown_not_investigated",
            "stage_status": "no_result",
            "error_code": "EXPECTED_NO_RESULT",
            "may_claim_universal_negative": False,
        },
        "prohibited_false_inference": _no_inference(
            "there are no records of this owner",
            "no search ran, so there is nothing to have found and nothing that was not "
            "found; 'not investigated' and 'searched, nothing there' are different states",
            "may_claim_universal_negative",
        ),
        "applicable_measurement": {"class": "synthetic_unmeasured",
                                   **MEASURES["synthetic_unmeasured"],
                                   "status": "not_performed_for_this_fixture"},
    },
    {
        "case_id": "EPI-NOOBS-01",
        "category": "no_observations",
        "provenance": "synthetic",
        "generator": "CASES['EPI-NOOBS-01']",
        "source_licence": "synthetic",
        "ground_truth": (
            "The subject was in scope of the collection and the collection completed, but "
            "the subject generated no observations at all. Distinct from a query that ran "
            "and matched nothing: nothing here was ever gathered."
        ),
        "sources": [_source("SRC-SYN-K3", "synthetic closed registry",
                            measure_class="closed_registry", detection_power=0.9,
                            detection_power_method="seeded known-positive trial",
                            coverage_estimate=0.93)],
        "proposition": _proposition("Vantor Biotech", "beneficial_owner", "N. Achebe"),
        "evidence": [],
        # The collection ran over this subject and gathered nothing. Stated as an input
        # rather than inferred from the empty evidence list, because EPI-SNR-UNKNOWN-01
        # has an equally empty evidence list and did run a query.
        "collection_completed": True,
        "expected": {
            "research_state": {
                "disposition": "completed", "query": "not_run", "truth_state": "neither",
                "absence": "not_applicable", "evidence": "none", "scope": "undeclared",
            },
            "research_state_name": "no_observations",
            "stage_status": "succeeded",
            "error_code": None,
            "may_claim_universal_negative": False,
        },
        "prohibited_false_inference": _no_inference(
            "no observations means no owner",
            "the collection produced nothing for this subject; that is a fact about the "
            "collection, and it is not a query result that matched nothing",
            "may_claim_universal_negative",
        ),
        "applicable_measurement": {"class": "closed_registry", **MEASURES["closed_registry"],
                                   "status": "not_performed_for_this_fixture"},
    },
    # -- inconclusive --------------------------------------------------------
    {
        "case_id": "EPI-INCONC-01",
        "category": "inconclusive",
        "provenance": "synthetic",
        "generator": "CASES['EPI-INCONC-01']",
        "source_licence": "synthetic",
        "ground_truth": (
            "Two sources were read and both describe the relation without settling it. There "
            "is evidence and there is no support on either side. Neither side being "
            "supported is not the same as the other side being unsupported."
        ),
        "sources": [
            _source("SRC-SYN-I1", "synthetic commentary A", measure_class="full_text_index",
                    coverage_estimate=0.8),
            _source("SRC-SYN-I2", "synthetic commentary B", measure_class="full_text_index",
                    coverage_estimate=0.8),
        ],
        "proposition": _proposition("Vantor Biotech", "beneficial_owner", "N. Achebe"),
        "evidence": [
            {"ref": "EVD-40", "positive": None, "source_id": "SRC-SYN-I1"},
            {"ref": "EVD-41", "positive": None, "source_id": "SRC-SYN-I2"},
        ],
        "expected": {
            "research_state": {
                "disposition": "completed", "query": "ran_matched", "truth_state": "neither",
                "absence": "not_applicable", "evidence": "inconclusive", "scope": "undeclared",
            },
            "research_state_name": "inconclusive",
            "stage_status": "succeeded",
            "error_code": None,
            "may_claim_universal_negative": False,
        },
        "prohibited_false_inference": _no_inference(
            "nothing supports it, therefore it is false",
            "absence of positive support is not negative support, and collapsing the two is "
            "the first half of FR-011",
            "is_negative_support",
        ),
        "applicable_measurement": {"class": "full_text_index", **MEASURES["full_text_index"],
                                   "status": "not_performed_for_this_fixture"},
    },
    # -- saturation ----------------------------------------------------------
    {
        "case_id": "EPI-SAT-01",
        "category": "saturated_with_scope",
        "provenance": "synthetic",
        "generator": "CASES['EPI-SAT-01']",
        "source_licence": "synthetic",
        "ground_truth": (
            "A declared universe was searched to exhaustion with no further gain available "
            "and nothing found. Saturation holds within the declared scope and nowhere else."
        ),
        "sources": [_source("SRC-SYN-S1", "synthetic complete registry",
                            measure_class="closed_registry", detection_power=0.95,
                            detection_power_method="seeded known-positive trial",
                            coverage_estimate=0.98)],
        "proposition": _proposition("Alderfen Trust", "beneficial_owner", "K. Sandoval"),
        "evidence": [],
        "exhausted_within_declared_scope": True,
        "expected": {
            "research_state": {
                "disposition": "exhausted", "query": "ran_zero_match", "truth_state": "neither",
                "absence": "searched_no_result", "evidence": "none", "scope": "declared",
            },
            "research_state_name": "saturated_with_scope",
            "stage_status": "no_result",
            "error_code": "EXPECTED_NO_RESULT",
            "may_claim_universal_negative": False,
        },
        "prohibited_false_inference": _no_inference(
            "the search is saturated so the subject is absent everywhere",
            "saturation is a statement about the declared scope; it is not a licence to "
            "extend the answer past the boundary that was declared",
            "may_claim_universal_negative",
        ),
        "applicable_measurement": {"class": "closed_registry", **MEASURES["closed_registry"],
                                   "status": "not_performed_for_this_fixture"},
    },
    {
        "case_id": "EPI-SAT-02",
        "category": "saturated_with_scope",
        "provenance": "synthetic",
        "generator": "CASES['EPI-SAT-02']",
        "source_licence": "synthetic",
        "ground_truth": (
            "The declared universe was searched to exhaustion and the search turned up "
            "evidence on both sides of the proposition. This is saturated-with-scope *and* "
            "contradicted at once, and it is in the corpus precisely because a flat "
            "thirteen-value enum would have had to pick one."
        ),
        "sources": [
            _source("SRC-SYN-S2", "synthetic complete registry A", measure_class="closed_registry",
                    detection_power=0.95, detection_power_method="seeded known-positive trial",
                    coverage_estimate=0.98),
            _source("SRC-SYN-S3", "synthetic complete registry B", measure_class="closed_registry",
                    detection_power=0.92, detection_power_method="seeded known-positive trial",
                    coverage_estimate=0.94),
        ],
        "proposition": _proposition("Alderfen Trust", "beneficial_owner", "K. Sandoval"),
        "evidence": [
            {"ref": "EVD-50", "positive": True, "source_id": "SRC-SYN-S2"},
            {"ref": "EVD-51", "positive": False, "source_id": "SRC-SYN-S3"},
        ],
        "exhausted_within_declared_scope": True,
        "expected": {
            "research_state": {
                "disposition": "exhausted", "query": "ran_matched", "truth_state": "both",
                "absence": "not_applicable", "evidence": "conflicted", "scope": "declared",
            },
            "research_state_name": None,
            "stage_status": "succeeded",
            "error_code": None,
            "may_claim_universal_negative": False,
        },
        "prohibited_false_inference": _no_inference(
            "saturation means the search is closed, so the contradiction is closed too",
            "exhaustion is about coverage, not about conflict; a search can be complete and "
            "still hold two incompatible readings, and it does here",
            "contradiction_resolved",
        ),
        "applicable_measurement": {"class": "closed_registry", **MEASURES["closed_registry"],
                                   "status": "not_performed_for_this_fixture"},
    },
]


REQUIRED_CATEGORIES = (
    "positive_only",
    "negative_only",
    "both",
    "unknown",
    "unsupported_source",
    "failed_source",
    "searched_no_result_known_detection_power",
    "searched_no_result_unknown_detection_power",
    "unknown_not_investigated",
    "no_observations",
    "inconclusive",
    "saturated_with_scope",
)


#: Whether a query was ever pointed at the subject. Stated **per case and explicitly**,
#: because two cases in this corpus have byte-identical source properties and no evidence
#: between them and must still resolve to different states:
#:
#: * ``EPI-NOOBS-01`` -- a collection ran over the subject and gathered nothing.
#: * ``EPI-SNR-UNKNOWN-01`` -- a query ran against a source and matched nothing.
#:
#: Nothing in their sources distinguishes those. Inferring it would have meant the
#: resolver guessing from a field that does not carry the answer, which is precisely the
#: kind of inference this corpus exists to catch. It is an input, so it is an input.
QUERY_RAN: dict[str, bool] = {
    "EPI-POS-01": True,
    "EPI-POS-02": True,
    "EPI-NEG-01": True,
    "EPI-NEG-02": True,
    "EPI-BOTH-01": True,
    "EPI-BOTH-02": True,
    "EPI-BOTH-03": True,
    "EPI-UNK-01": True,
    "EPI-UNK-02": True,
    "EPI-UNSUP-01": False,
    "EPI-UNSUP-02": False,
    "EPI-FAIL-01": False,
    "EPI-FAIL-02": True,
    "EPI-SNR-KNOWN-01": True,
    "EPI-SNR-KNOWN-02": True,
    "EPI-SNR-UNKNOWN-01": True,
    "EPI-SNR-UNKNOWN-02": True,
    "EPI-SNR-UNKNOWN-03": True,
    "EPI-NOTINV-01": False,
    "EPI-NOOBS-01": False,
    "EPI-INCONC-01": True,
    "EPI-SAT-01": True,
    "EPI-SAT-02": True,
}


def all_cases() -> list[dict[str, Any]]:
    cases = [json.loads(json.dumps(case, ensure_ascii=False)) for case in CASES]
    for case in cases:
        case["query_ran"] = QUERY_RAN[case["case_id"]]
    return cases


def render(cases: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(c, ensure_ascii=False, sort_keys=True) + "\n" for c in cases)


def summarise(cases: list[dict[str, Any]]) -> dict[str, Any]:
    categories: dict[str, int] = {}
    licences: dict[str, int] = {}
    for case in cases:
        categories[case["category"]] = categories.get(case["category"], 0) + 1
        licences[case["source_licence"]] = licences.get(case["source_licence"], 0) + 1
    missing = sorted(set(REQUIRED_CATEGORIES) - set(categories))
    return {
        "cases": len(cases),
        "categories": dict(sorted(categories.items())),
        "source_licences": dict(sorted(licences.items())),
        "provenance": sorted({case["provenance"] for case in cases}),
        "missing_required_categories": missing,
        "sources": sum(len(case["sources"]) for case in cases),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify", action="store_true", help="compare against cases.jsonl, write nothing"
    )
    args = parser.parse_args(argv)

    cases = all_cases()
    ids = [case["case_id"] for case in cases]
    if len(set(ids)) != len(ids):
        print("duplicate case_id in the generator", file=sys.stderr)
        return 2

    rendered = render(cases)
    if args.verify:
        if not CORPUS.exists():
            print(f"missing {CORPUS}", file=sys.stderr)
            return 2
        if CORPUS.read_text(encoding="utf-8") != rendered:
            print("cases.jsonl has drifted from the generator", file=sys.stderr)
            return 1
    else:
        CORPUS.write_text(rendered, encoding="utf-8")

    summary = summarise(cases)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if summary["missing_required_categories"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
