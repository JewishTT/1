"""WARC intake → candidates → assertions → admission decisions.

This is the seam between interpretation and admission. Interpretation produces
provenance-bearing claims out of archived captures; admission has to decide
whether each claim is strong enough to become knowledge. The two apps are
separately deployable and must not import each other, so the contract between
them is structural and defined here:

* a **document** is anything exposing ``document_id``, ``url``, ``text``,
  ``body_sha256``, ``record_id``, ``warc_date``, ``is_revisit`` and ``notes``
  (a ``WarcDocument`` satisfies this as-is);
* a **claim** is an :class:`IntakeClaim` — subject, relation, object, plus the
  document and evidence refs it was read from;
* a **resolver** is an injected callable that reports whether a claim's subject
  was matched to an already-admitted entity, which is what makes
  ``ACCEPT_EXISTING`` reachable.

The one piece of real logic here is *cross-document aggregation*. A claim seen
in three documents from three different hosts is not three claims, it is one
claim with corroboration — and a claim copied across mirrors of one site is one
claim with none. Aggregating before deciding (rather than admitting each sighting
separately) is what keeps the admission lane from minting duplicate entities,
and it is why ``ACCEPT_EXISTING`` can be decided from evidence rather than from
a prior merge having already happened.

Hostile input is quarantined, never dropped: a capture whose digest failed
verification, whose payload was truncated, or that returned an error status
cannot contribute corroboration, and the reason is recorded so the record stays
replayable (FR-013, SC-007).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from .admission import AdmissionEngine, AdmissionResult, AdmitDecision
from .assertions import AssertionExtractor, EvidenceLink, EvidenceRef, ExtractedAssertion
from .calibration import AdmissionInput, MediaProfile

# Document notes that disqualify a capture from contributing corroboration.
UNTRUSTWORTHY_NOTE_PREFIXES = (
    "record_truncated",
    "http_error_status",
    "content_encoding_undecodable",
)

Resolver = Callable[["IntakeClaim"], "Match | None"]


@dataclass(frozen=True)
class Match:
    """Resolution verdict: this claim's subject is an already-admitted entity."""

    entity_id: str
    score: float = 0.0
    confirmed: bool = False


@dataclass(frozen=True)
class IntakeClaim:
    """One provenance-bearing claim read out of a single document."""

    subject: str
    relation: str
    object_value: str
    document_id: str
    subject_kind: str = "entity"
    confidence: float = 0.0
    evidence_id: str = ""
    relation_id: str = ""

    @property
    def claim_id(self) -> str:
        return claim_id_for(self.subject, self.relation, self.object_value)

    @property
    def triple(self) -> tuple[str, str, str]:
        return (self.subject, self.relation, self.object_value)


@dataclass(frozen=True)
class QuarantineRecord:
    """A capture excluded from admission, preserved with a stable reason."""

    document_id: str
    reason: str
    url: str = ""
    body_sha256: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "document_id": self.document_id,
            "reason": self.reason,
            "url": self.url,
            "body_sha256": self.body_sha256,
        }


@dataclass
class IntakeResult:
    """Outcome of one intake run: what was decided, asserted, and parked."""

    decisions: list[AdmissionResult] = field(default_factory=list)
    assertions: list[ExtractedAssertion] = field(default_factory=list)
    quarantined: list[QuarantineRecord] = field(default_factory=list)
    documents_seen: int = 0
    claims_seen: int = 0
    revisits_seen: int = 0

    def counts_by_decision(self) -> dict[str, int]:
        counts = {decision.value: 0 for decision in AdmitDecision}
        for decision in self.decisions:
            counts[decision.decision.value] += 1
        return counts

    def decisions_of(self, decision: AdmitDecision) -> list[AdmissionResult]:
        return [d for d in self.decisions if d.decision is decision]

    @property
    def accepted_entities(self) -> list[str]:
        """Entities admitted, whether new or merged into an existing one."""
        return [d.target_entity_id or d.candidate_id for d in self.decisions
                if d.decision in (AdmitDecision.ACCEPT_NEW, AdmitDecision.ACCEPT_EXISTING)]


def claim_id_for(subject: str, relation: str, object_value: str) -> str:
    """Content-derived claim id, so the same triple always collapses to one."""
    stable = f"{subject}|{relation}|{object_value}"
    return "CL-" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:16]


def host_of(url: str) -> str:
    """Registrable-ish host used as the independence key (I-11)."""
    if not url:
        return ""
    host = (urlsplit(url).hostname or "").lower()
    return host.removeprefix("www.")


def _document_attr(document, name: str, default=None):
    return getattr(document, name, default)


def untrustworthy_reason(document) -> str | None:
    """Return why this capture cannot support corroboration, or None."""
    for note in _document_attr(document, "notes", ()) or ():
        if any(note.startswith(prefix) for prefix in UNTRUSTWORTHY_NOTE_PREFIXES):
            return f"intake.untrustworthy_capture:{note}"
    return None


@dataclass
class _Cluster:
    """All sightings of one triple, and the evidence that aggregates into it.

    **WP-E T071.** ``dependency_roots`` carries the lineage each document ultimately
    derives from. When it is populated it *replaces* ``hosts`` as the independence
    measure, because a hostname is not a source: one site syndicating to twenty
    subdomains is one source wearing twenty hats, and counting the hats as
    corroboration is how a press release becomes twenty independent confirmations.

    ``independence_known`` records which measure was used, so a decision can be read
    correctly rather than assumed. It is ``False`` only when no lineage was supplied
    at all — an honest "we did not measure", never a silent fallback presented as one.
    """

    triple: tuple[str, str, str]
    claims: list[IntakeClaim] = field(default_factory=list)
    document_ids: set[str] = field(default_factory=set)
    hosts: set[str] = field(default_factory=set)
    #: document_id -> the lineage root it ultimately derives from.
    lineage_roots: dict[str, str] = field(default_factory=dict)

    @property
    def publications(self) -> int:
        """Distinct documents asserting the triple (mirrors count once)."""
        return len(self.document_ids)

    @property
    def independence_known(self) -> bool:
        """True once any document in this cluster carries a declared lineage."""
        return bool(self.lineage_roots)

    @property
    def effective_sources(self) -> int:
        """Distinct *origins*, which is what independence actually means.

        With lineage, this is the number of distinct roots. Without, it is the number
        of hosts and the caller is told so via :attr:`independence_known`.
        """
        if self.independence_known:
            return len(set(self.lineage_roots.values()))
        return len(self.hosts)

    @property
    def independent_hosts(self) -> int:
        return len(self.hosts)

    @property
    def best_confidence(self) -> float:
        return max((c.confidence for c in self.claims), default=0.0)

    def corroboration(self) -> float:
        """Corroboration from breadth of publication and true independence.

        Both components start at zero for a single source: one document from one
        origin is an unconfirmed claim, not a corroborated one, and it must fall
        below the profile's defer floor rather than scraping past it. Publication
        alone would let one site farm mirrors for a score, and hosts alone would let a
        site farm subdomains — so the two are averaged.

        **The second component is effective sources, not hosts** (T071). Twenty
        mirrors of one press release on twenty domains now score as one origin.
        """
        by_publication = min(1.0, max(0, self.publications - 1) / 2.0)
        by_independence = min(1.0, max(0, self.effective_sources - 1) / 2.0)
        return round((by_publication + by_independence) / 2.0, 3)

    def independence(self) -> float:
        if not self.effective_sources:
            return 0.0
        return round(min(1.0, (self.effective_sources - 1) / 2.0), 3)


class WarcIntake:
    """Drive documents + claims through aggregation and admission.

    ``engine`` and ``profiles`` are injectable so the same intake can run
    against a calibrated profile set in production and the bootstrap set in
    tests, without the pipeline knowing which is which.
    """

    def __init__(
        self,
        engine: AdmissionEngine | None = None,
        *,
        profiles: MediaProfile | None = None,
        dataset_id: str = "",
        tenant_id: str = "default-tenant",
        extraction_version: str = "warc-intake-v1",
    ) -> None:
        self._engine = engine or AdmissionEngine(profiles)
        self._extractor = AssertionExtractor()
        self._dataset_id = dataset_id
        self._tenant_id = tenant_id
        self._extraction_version = extraction_version

    def run(
        self,
        documents: Iterable[object],
        claims: Sequence[IntakeClaim] = (),
        *,
        resolver: Resolver | None = None,
        lineage_by_document: Mapping[str, str] | None = None,
    ) -> IntakeResult:
        """Interpret, aggregate and decide. Untrusted captures are quarantined.

        ``lineage_by_document`` maps a document to the origin it ultimately derives
        from (**WP-E T071**). Supplying it replaces hostname counting as the
        independence measure; omitting it leaves the old behaviour *and* marks every
        decision as measured-on-hosts, so a reader can tell which was used.

        The lineage itself is not invented here. A document with no declared origin
        falls back to being its own root — which is the conservative direction: it
        counts as one independent source, not as infinitely corroborated.
        """
        result = IntakeResult()
        trusted: set[str] = set()
        hosts_by_document: dict[str, str] = {}
        for document in documents:
            result.documents_seen += 1
            document_id = str(_document_attr(document, "document_id", "") or "")
            reason = untrustworthy_reason(document)
            if reason is not None:
                result.quarantined.append(
                    QuarantineRecord(
                        document_id=document_id,
                        reason=reason,
                        url=str(_document_attr(document, "url", "") or ""),
                        body_sha256=str(_document_attr(document, "body_sha256", "") or ""),
                    )
                )
                continue
            trusted.add(document_id)
            hosts_by_document[document_id] = host_of(
                str(_document_attr(document, "url", "") or "")
            )
            if _document_attr(document, "is_revisit", False):
                # A revisit proves republication but carries no claims of its own.
                result.revisits_seen += 1

        result.claims_seen = len(claims)
        for cluster in self._cluster(claims, trusted, hosts_by_document, lineage_by_document):
            decision, assertion = self._decide(cluster, resolver)
            result.decisions.append(decision)
            result.assertions.append(assertion)
        return result

    def _cluster(
        self,
        claims: Sequence[IntakeClaim],
        trusted: set[str],
        hosts_by_document: dict[str, str],
        lineage_by_document: dict[str, str] | None = None,
    ) -> list[_Cluster]:
        """Collapse claims into one cluster per triple, in first-seen order."""
        clusters: dict[tuple[str, str, str], _Cluster] = {}
        for claim in claims:
            if claim.document_id not in trusted:
                continue  # a quarantined capture never corroborates anything
            cluster = clusters.setdefault(claim.triple, _Cluster(triple=claim.triple))
            cluster.claims.append(claim)
            cluster.document_ids.add(claim.document_id)
            host = hosts_by_document.get(claim.document_id, "")
            if host:
                cluster.hosts.add(host)
            if lineage_by_document is not None:
                # A document with no declared origin is **its own root**.
                #
                # Skipping it instead would be the wrong direction twice over: the
                # un-declared document would vanish from the independence count, so
                # dropping evidence would *lower* the effective-source figure and
                # manufacture the appearance of concentrated lineage that nobody
                # established. Conservative here means "count it as one source we
                # cannot trace", not "count it as nothing".
                root = lineage_by_document.get(claim.document_id, "") or claim.document_id
                cluster.lineage_roots[claim.document_id] = root
        return list(clusters.values())

    def _decide(
        self, cluster: _Cluster, resolver: Resolver | None
    ) -> tuple[AdmissionResult, ExtractedAssertion]:
        subject, relation, object_value = cluster.triple
        refs = [
            EvidenceRef(
                observation_id=claim.document_id,
                source_id=claim.evidence_id or None,
            )
            for claim in sorted(cluster.claims, key=lambda c: (c.document_id, c.relation_id))
        ]
        link = EvidenceLink(evidence_refs=refs)
        link.publication_count = cluster.publications
        link.independent_source_count = cluster.effective_sources

        assertion = self._extractor.extract(
            subject_candidate_id=subject,
            relation=relation,
            object_value=object_value,
            refs=refs,
            dataset_id=self._dataset_id,
            extraction_version=self._extraction_version,
            tenant_id=self._tenant_id,
        )

        match = resolver(cluster.claims[0]) if resolver is not None else None
        decision = self._engine.decide(
            AdmissionInput(
                candidate_id=claim_id_for(subject, relation, object_value),
                entity_type=cluster.claims[0].subject_kind,
                structural_score=cluster.best_confidence,
                corroboration_score=cluster.corroboration(),
                independence_score=cluster.independence(),
                evidence_counts={
                    "documents": cluster.publications,
                    "hosts": cluster.independent_hosts,
                    # Both are reported, never only the flattering one. An analyst
                    # reading "20 hosts" must be able to see "1 origin" beside it.
                    "effective_sources": cluster.effective_sources,
                    "independence_measured_on": (
                        "lineage" if cluster.independence_known else "hosts"
                    ),
                },
                matched_entity_id=match.entity_id if match else None,
                match_score=match.score if match else 0.0,
                match_confirmed=bool(match and match.confirmed),
            ),
            link,
        )
        decision.assertion = _assertion_record(assertion)
        return decision, assertion


def _assertion_record(assertion: ExtractedAssertion) -> object:
    """Project the evidence assertion onto the temporal AssertionRecord.

    Only fields both models share are copied; the temporal engine owns lifecycle
    transitions, and nothing here mutates either side.
    """
    from .temporal import AssertionRecord

    return AssertionRecord(
        assertion_id=assertion.assertion_id,
        relation=assertion.relation,
        subject_candidate_id=assertion.subject_candidate_id or "",
        object_value=assertion.object_value,
        observed_at=assertion.observed_at,
        valid_from=assertion.valid_from,
        valid_to=assertion.valid_to,
    )
