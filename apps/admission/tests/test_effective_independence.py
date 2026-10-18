"""WP-E T071: corroboration counts *origins*, not hostnames.

**The defect.** ``WarcIntake`` measured independence with ``len(self.hosts)`` — the
number of distinct registrable hostnames asserting a triple. The audit found this on the
live path, with ``SourceIndependenceEngine`` — a real derivation-graph transitive-closure
model sitting next to it with **zero non-test importers**.

A hostname is not a source. One newsroom syndicating a press release to twenty partner
sites produces twenty hostnames and one piece of evidence. The old measure scored that
as broad corroboration, which is exactly how a single assertion becomes a "well
confirmed" claim that no analyst can audit, because the twenty documents are the same
document.

The fix is not "count fewer things". It is to make the platform say **which** measure it
used, and to let a caller supply real lineage so the distinction can be made at all.
"""

from __future__ import annotations

import pytest

from engine.admission import AdmissionEngine, AdmitDecision
from engine.calibration import AdmissionInput, CalibrationProfile, MediaProfile
from engine.intake import IntakeClaim, WarcIntake

pytestmark = pytest.mark.unit


class Doc:
    """Minimal stand-in for an interpreted WARC document.

    Copied from ``test_intake.py`` rather than imported: that module's ``Doc`` is a
    test fixture defined at import time alongside its helpers, and importing across
    test modules makes one file's edits break another's collection.
    """

    def __init__(
        self,
        document_id: str,
        url: str,
        *,
        notes: tuple[str, ...] = (),
        is_revisit: bool = False,
        text: str = "",
        body_sha256: str = "",
    ) -> None:
        self.document_id = document_id
        self.url = url
        self.notes = notes
        self.is_revisit = is_revisit
        self.text = text
        self.body_sha256 = body_sha256


def _claim(doc_id: str, triple: tuple[str, str, str], evidence: str = "") -> IntakeClaim:
    subject, relation, obj = triple
    return IntakeClaim(
        subject=subject,
        relation=relation,
        object_value=obj,
        document_id=doc_id,
        subject_kind="organisation",
        confidence=0.8,
        evidence_id=evidence or f"EVD-{doc_id}",
        relation_id=relation,
    )


TRIPLE = ("org-1", "owned_by", "person-1")


def _docs(hosts: list[str]) -> list[Doc]:
    return [Doc(f"d{i}", f"https://{host}.example/p") for i, host in enumerate(hosts)]


# ---------------------------------------------------------------------------
# The syndication case
# ---------------------------------------------------------------------------

def test_twenty_mirrors_of_one_origin_are_one_source():
    """The headline case: twenty domains, one press release.

    Twenty distinct hostnames, because syndication is what syndication does. One
    lineage root, because they are all the same document.

    **What is asserted is the corroboration figure, not the final disposition.** The
    candidate is still admitted — via ``accept_qualified_structurally``, which is a
    separate policy about how much a confident single extraction is worth. Before this
    change it was admitted via ``accept_strong_corroboration``, because twenty hostnames
    pushed corroboration to 1.0. Same outcome, entirely different justification, and
    only one of them is true.

    Asserting ``DEFER`` here would be asserting a policy about single-document
    admission that this change does not make and has no evidence to make. The change
    is to stop calling republication corroboration.
    """
    hosts = [f"partner{i}" for i in range(20)]
    documents = _docs(hosts)
    claims = [_claim(doc.document_id, TRIPLE) for doc in documents]

    result = WarcIntake().run(
        documents,
        claims,
        lineage_by_document={doc.document_id: "origin-press-release" for doc in documents},
    )
    decision = result.decisions[0]

    counts = decision.evidence_counts
    assert counts["hosts"] == 20
    assert counts["effective_sources"] == 1
    assert counts["independence_measured_on"] == "lineage"

    assert "accept_strong_corroboration" not in decision.reason_codes, (
        "twenty mirrors of one origin must not be admitted as corroborated"
    )
    assert decision.reason_codes == ["accept_qualified_structurally"]


def test_without_lineage_the_mirrors_would_have_looked_corroborated():
    """The counterfactual, so the test above cannot pass vacuously.

    Same twenty hostnames, no lineage declared. Corroboration is computed on hosts and
    clears the accept bar. That is precisely the number T071 exists to stop trusting —
    shown here so the difference is a measurement rather than an assertion.
    """
    hosts = [f"partner{i}" for i in range(20)]
    documents = _docs(hosts)
    claims = [_claim(doc.document_id, TRIPLE) for doc in documents]

    decision = WarcIntake().run(documents, claims).decisions[0]

    assert decision.evidence_counts["independence_measured_on"] == "hosts"
    assert "accept_strong_corroboration" in decision.reason_codes


def test_corroboration_does_not_rise_with_mirror_count():
    """Adding mirrors of one origin must not move the score at all.

    This is the property that matters. A measure that grows with the number of
    copies is measuring republication, not confirmation.
    """
    base_docs = _docs(["a", "b"])
    base_claims = [_claim(doc.document_id, TRIPLE) for doc in base_docs]
    base = WarcIntake().run(
        base_docs, base_claims, lineage_by_document={d.document_id: "origin" for d in base_docs}
    )

    many_docs = _docs([f"m{i}" for i in range(30)])
    many_claims = [_claim(doc.document_id, TRIPLE) for doc in many_docs]
    many = WarcIntake().run(
        many_docs, many_claims, lineage_by_document={d.document_id: "origin" for d in many_docs}
    )

    def independence(result):
        return result.decisions[0].evidence_counts["effective_sources"]

    assert independence(many) == independence(base) == 1


def test_genuinely_independent_origins_still_corroborate():
    """The fix must not collapse real corroboration into real redundancy.

    Two documents from two unrelated origins are two pieces of evidence, and the
    platform must say so. A gate that refuses everything is not a gate.
    """
    documents = _docs(["a", "b"])
    claims = [_claim(doc.document_id, TRIPLE) for doc in documents]

    result = WarcIntake().run(
        documents,
        claims,
        lineage_by_document={"d0": "origin-alpha", "d1": "origin-beta"},
    )
    decision = result.decisions[0]

    assert decision.evidence_counts["effective_sources"] == 2
    assert decision.decision is AdmitDecision.ACCEPT_NEW


# ---------------------------------------------------------------------------
# Declaring which measure was used
# ---------------------------------------------------------------------------

def test_without_lineage_the_measure_is_declared_not_hidden():
    """No lineage supplied ⇒ measured on hosts, and the decision says so.

    Silently falling back is the failure mode this prevents: a reader who sees
    "hosts: 20" must be able to find out that nobody established whether those twenty
    were one source or twenty.
    """
    documents = _docs(["a", "b"])
    claims = [_claim(doc.document_id, TRIPLE) for doc in documents]

    decision = WarcIntake().run(documents, claims).decisions[0]

    assert decision.evidence_counts["independence_measured_on"] == "hosts"
    assert decision.evidence_counts["effective_sources"] == 2


def test_partial_lineage_is_used_as_given_and_nothing_is_invented():
    """A document with no declared origin counts as its own root.

    That is the conservative direction: unproven lineage must not manufacture
    corroboration, and it must not collapse into "we don't know" either, because a
    cluster of unproven documents is still evidence somebody should look at.
    """
    documents = _docs(["a", "b"])
    claims = [_claim(doc.document_id, TRIPLE) for doc in documents]

    decision = WarcIntake().run(
        documents, claims, lineage_by_document={"d0": "origin-alpha"}
    ).decisions[0]

    counts = decision.evidence_counts
    assert counts["independence_measured_on"] == "lineage"
    # d0 declares an origin; d1 declares nothing and is its own root.
    assert counts["effective_sources"] == 2


# ---------------------------------------------------------------------------
# The calibration gate, end to end through intake
# ---------------------------------------------------------------------------


def test_a_resolver_score_cannot_fuse_subjects_through_intake():
    """T070 and T071 together: a high resolver score on an uncalibrated profile routes
    to review rather than merging, and the withheld merge names itself.

    Both changes have to hold on the same path, because that is where they meet in
    production: intake computes corroboration, feeds it to admission, and admission
    decides whether two subjects become one.
    """
    documents = _docs(["a", "b"])
    claims = [_claim(doc.document_id, TRIPLE) for doc in documents]

    result = WarcIntake().run(
        documents, claims, resolver=lambda c: _match("E-existing", 0.99)
    )
    decision = result.decisions[0]

    assert decision.decision is not AdmitDecision.ACCEPT_EXISTING
    assert any("calibration_undeclared" in code for code in decision.reason_codes)


def test_a_registered_calibration_restores_merging_through_intake():
    profiles = MediaProfile()
    profiles.register(CalibrationProfile(entity_type="organisation", version="org-v2"))
    documents = _docs(["a", "b"])
    claims = [_claim(doc.document_id, TRIPLE) for doc in documents]

    result = WarcIntake(profiles=profiles).run(
        documents, claims, resolver=lambda c: _match("E-existing", 0.99)
    )
    decision = result.decisions[0]

    assert decision.decision is AdmitDecision.ACCEPT_EXISTING
    assert decision.target_entity_id == "E-existing"


# ---------------------------------------------------------------------------
# Calibration identity itself
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "version,calibrated",
    [
        ("UNCALIBRATED-v1", False),
        ("uncalibrated-v1", False),
        ("  UNCALIBRATED-v1  ", False),
        ("", False),
        ("org-linked-v2", True),
        ("ipv4-fitted-2026-09", True),
    ],
)
def test_calibration_identity_is_case_and_whitespace_insensitive(version: str, calibrated: bool):
    """A profile that declares itself uncalibrated with different casing is still
    uncalibrated. Otherwise the gate is defeated by a string literal."""
    from engine.calibration import CalibrationProfile as Profile

    assert Profile(entity_type="x", version=version).is_calibrated is calibrated


def test_an_uncalibrated_profile_names_itself():
    from engine.calibration import CalibrationProfile as Profile

    profile = Profile(entity_type="x")
    assert "UNCALIBRATED-v1" in profile.merge_bar()
    assert Profile(entity_type="x", version="fitted-v1").merge_bar() == ""


def _match(entity_id: str, score: float):
    from engine.intake import Match

    return Match(entity_id=entity_id, score=score)


def test_the_engine_itself_refuses_an_uncalibrated_merge():
    """Direct engine call, so the gate is pinned independently of intake."""
    engine = AdmissionEngine()
    result = engine.decide(
        AdmissionInput(
            candidate_id="c1",
            entity_type="person",
            corroboration_score=0.9,
            structural_score=0.9,
            matched_entity_id="E-1",
            match_score=0.99,
        )
    )
    assert result.decision is AdmitDecision.ACCEPT_NEW
    assert any("calibration_undeclared" in code for code in result.reason_codes)