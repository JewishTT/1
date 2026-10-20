"""Splink 5.0.0 as a linkage *proposer*, behind the platform's resolution contract.

Spec 030 CE-001 §15.5, DON-ER-003/005, task T105. ADR-030-06. Feature 034 pins Splink 5.0.0.

**Upstream**   : https://github.com/moj-analytical-services/splink
**Revision**   : 5.0.0 (pinned)
**Licence**    : MIT (code). Model weights: none shipped.
**Mode**       : B — upstream package behind a COGNITIVE contract.
**Backend**    : DuckDB (in-process, no separate server).

**The one rule this module exists to enforce.** Splink proposes; it does not decide. Its output
is a :class:`ResolutionCandidate` with a comparison vector and a score whose *semantics* are
named. Nothing here writes identity, and nothing here is wired to write identity.

That is not caution, it is the finding from the 029 audit: the existing matcher was able to
commit a merge on a threshold whose own profile declared itself uncalibrated. A second engine
that could do the same would not be an improvement, it would be a second way to be wrong.

**Production requirement.** Splink 5.0.0 is the sole production pair-linkage implementation
for the person-research vertical. The adapter is mandatory in the production composition root.
Splink cannot merge entities directly; its output becomes a ``possible_match`` plus field
comparison vector, source-span refs, blocking-rule IDs, model fingerprint and score semantics.
Human review and the existing admission gate own merge decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import shape documented, not exercised at runtime
    from resolution.candidate import Candidate

__all__ = [
    "SPLINK_VERSION_PINNED",
    "SPLINK_VERSION_SUPPORTED",
    "ComparisonVectorEntry",
    "ResolutionCandidate",
    "ScoreSemantics",
    "SplinkAdapter",
    "SplinkResult",
    "SplinkUnavailable",
    "DuckDBBackend",
]

# Exact pin for Feature 034. Splink 5.0.0 was released 28 September 2026.
SPLINK_VERSION_PINNED = "5.0.0"
SPLINK_VERSION_SUPPORTED = "==5.0.0"


class SplinkUnavailable(RuntimeError):
    """Splink is not installed in this environment.

    Raised rather than degraded. An absent linker is a capability gap with a named cause, and
    reporting it as "no matches found" would turn a missing dependency into a finding about the
    data.
    """


class ScoreSemantics(StrEnum):
    """What a score means, so a decision cannot read it as something else.

    ``match_probability`` is Splink's calibrated probability that two records match, given the
    trained model. ``uncalibrated_weight`` is a match weight with no probability interpretation.
    ``blocking_only`` means the pair was surfaced by a blocking rule and never scored.
    """

    MATCH_PROBABILITY = "match_probability"
    UNCALIBRATED_WEIGHT = "uncalibrated_weight"
    BLOCKING_ONLY = "blocking_only"


@dataclass(frozen=True, slots=True)
class ComparisonVectorEntry:
    """One field comparison, preserved in Splink's own terms.

    Kept even though the platform does not read it today: a merge an analyst cannot interrogate
    is a merge they have to take on faith, and the vector is the only thing that makes it
    interrogable.
    """

    field: str
    comparison_level: str | None
    value_l: Any
    value_r: Any


@dataclass(frozen=True, slots=True)
class ResolutionCandidate:
    """What Splink proposes, in platform vocabulary. Never a decision.

    Normalised from Splink 5.0.0 output. The score carries explicit semantics
    (``match_probability`` vs ``match_weight`` vs ``blocking_only``) and the model
    fingerprint identifies the trained settings and blocking rules. No candidate score
    is written into ``Entity`` as identity.
    """

    pair_key: str
    left_id: str
    right_id: str
    score: float | None
    score_semantics: ScoreSemantics
    comparison_vector: tuple[ComparisonVectorEntry, ...]
    model_fingerprint: str
    """Identifies the trained model and the blocking rules. Without it a score cannot be
    compared with another score, because two runs may have trained on different data."""
    splink_version: str = SPLINK_VERSION_PINNED
    blocking_rules_digest: str = ""
    """Digest of the blocking rules that generated this pair; enables audit of pair coverage."""
    source_lineage_roots: tuple[str, ...] = ()
    """Lineage roots of the evidence behind each record; syndicated copies count as one root."""
    span_refs: tuple[str, ...] = ()
    """Evidence span references anchored to the underlying observations."""
    notes: dict[str, Any] = field(default_factory=dict)

    @property
    def decision_weight(self) -> float:
        """A usable priority number, or ``0.0`` when nothing was scored.

        Deliberately not usable as a merge threshold by itself. It exists for *ordering*
        candidates for review, which is the one thing a proposal may legitimately do.
        """
        return float(self.score) if self.score is not None else 0.0

    def requires_human_or_policy_decision(self) -> bool:
        """Always True. Present so that a caller cannot forget the check."""
        return True

    def to_candidate(self) -> Candidate:
        """Adapt to the existing candidate record without deciding anything.

        Lands as ``OPEN`` with the pair's evidence written into ``reasons`` so a reviewer sees
        which field comparisons produced the proposal. There is no code path from here to
        ``ACCEPTED``; that transition belongs to the resolution decision service, which records
        who or what decided and why.
        """
        from resolution.candidate import Candidate, CandidateState

        reasons = [
            (
                f"splink/{self.splink_version} score={self.score} "
                f"semantics={self.score_semantics} model={self.model_fingerprint}"
            ),
        ]
        if self.blocking_rules_digest:
            reasons.append(f"blocking_rules={self.blocking_rules_digest}")
        for entry in self.comparison_vector:
            reasons.append(
                f"{entry.field}:{entry.comparison_level or '-'} "
                f"l={entry.value_l!r} r={entry.value_r!r}"
            )
        return Candidate(
            pair_key=self.pair_key,
            candidate_a=self.left_id,
            candidate_b=self.right_id,
            raw_pair_score=float(self.score) if self.score is not None else 0.0,
            reasons=reasons,
            state=CandidateState.OPEN,
        )


@dataclass(frozen=True, slots=True)
class SplinkResult:
    """One run's output, with enough context to reproduce or challenge it."""

    candidates: tuple[ResolutionCandidate, ...]
    model_fingerprint: str
    training_row_count: int | None = None
    """Rows the model was trained on. A score from a model trained on nine rows and a score from
    a model trained on ninety thousand are different claims."""
    calibrated: bool = False
    notes: dict[str, Any] = field(default_factory=dict)

    @property
    def is_comparable_to_another_run(self) -> bool:
        """Whether another run's scores can be laid beside these.

        False for an uncalibrated run, because an uncalibrated match weight is a distance in an
        arbitrary space and two such spaces are not the same space.
        """
        return self.calibrated


class DuckDBBackend:
    """DuckDB backend marker for Splink 5.0.0.

    Splink 5 uses DuckDB as its in-process analytical engine. This class records
    the backend choice and the database path so the deployment can verify it.
    """

    def __init__(self, *, database: str = ":memory:") -> None:
        self.database = database

    def connect(self) -> Any:
        """Open a DuckDB connection. Imported lazily so Splink is optional at import."""
        try:
            import duckdb  # type: ignore[import-not-found]
        except ImportError as exc:
            raise SplinkUnavailable(
                "duckdb is not installed; Splink 5.0.0 requires the DuckDB backend"
            ) from exc
        return duckdb.connect(self.database)


class SplinkAdapter:
    """Adapter over ``splink==5.0.0`` that produces proposals, not decisions.

    The heavy lifting is done by Splink's own ``Linker`` with the DuckDB backend.
    This class owns three things Splink has no opinion about: that the output is a
    proposal, that the score carries its semantics, and that the model that produced
    it is named.

    Production obligation: the adapter is mandatory in the production composition root.
    If Splink 5.0.0 cannot be imported or the DuckDB backend cannot open, the
    identity-resolution worker is blocked -- no ``PairwiseResolver`` fallback.
    """

    def __init__(
        self,
        *,
        version: str = SPLINK_VERSION_PINNED,
        backend: DuckDBBackend | None = None,
    ) -> None:
        self._version = version
        self._backend = backend or DuckDBBackend()

    @staticmethod
    def _require() -> Any:
        try:
            import splink
        except ImportError as exc:
            raise SplinkUnavailable(
                "splink is not installed; Splink 5.0.0 is mandatory for the "
                "person-research identity-resolution worker. This is a capability "
                "gap, not a finding about the data."
            ) from exc
        actual = str(getattr(splink, "__version__", "unknown"))
        if actual != SPLINK_VERSION_PINNED:
            raise SplinkUnavailable(
                f"splink version {actual} is installed but {SPLINK_VERSION_PINNED} "
                "is required; fail closed"
            )
        return splink

    def available(self) -> bool:
        try:
            self._require()
            self._backend.connect()
        except SplinkUnavailable:
            return False
        return True

    def version(self) -> str:
        splink = self._require()
        return str(getattr(splink, "__version__", self._version))

    @staticmethod
    def pair_key(left_id: str, right_id: str) -> str:
        """Order-independent pair identity.

        Sorted, because ``(a,b)`` and ``(b,a)`` are one pair and two ids for one pair
        means one candidate is proposed twice and reviewed twice.
        """
        return "|".join(sorted((str(left_id), str(right_id))))

    def to_candidate(
        self,
        *,
        left_id: str,
        right_id: str,
        score: float | None,
        score_semantics: ScoreSemantics,
        comparison_vector: tuple[ComparisonVectorEntry, ...],
        model_fingerprint: str,
        blocking_rules_digest: str = "",
        source_lineage_roots: tuple[str, ...] = (),
        span_refs: tuple[str, ...] = (),
        **notes: Any,
    ) -> ResolutionCandidate:
        return ResolutionCandidate(
            pair_key=self.pair_key(left_id, right_id),
            left_id=str(left_id),
            right_id=str(right_id),
            score=score,
            score_semantics=score_semantics,
            comparison_vector=comparison_vector,
            model_fingerprint=model_fingerprint,
            splink_version=self._version,
            blocking_rules_digest=blocking_rules_digest,
            source_lineage_roots=source_lineage_roots,
            span_refs=span_refs,
            notes=dict(notes),
        )

    def to_result(
        self,
        candidates: tuple[ResolutionCandidate, ...],
        *,
        model_fingerprint: str,
        training_row_count: int | None = None,
        calibrated: bool = False,
        **notes: Any,
    ) -> SplinkResult:
        """Wrap a run. Ordered by descending score so a review queue starts at the top.

        Ties break on ``pair_key`` so two runs over the same model produce the same order.
        """
        ordered = tuple(
            sorted(candidates, key=lambda c: (-c.decision_weight, c.pair_key))
        )
        return SplinkResult(
            candidates=ordered,
            model_fingerprint=model_fingerprint,
            training_row_count=training_row_count,
            calibrated=calibrated,
            notes=dict(notes),
        )

    def link_records(
        self,
        *,
        records: list[dict[str, Any]],
        settings: dict[str, Any],
        blocking_rules_digest: str,
    ) -> SplinkResult:
        """Run Splink 5.0.0 linkage over the supplied records.

        ``records`` are dictionaries with the fields declared in the person
        comparison schema. ``settings`` is the Splink settings dict (blocking rules,
        comparison levels, m/u parameters). Returns a :class:`SplinkResult` whose
        candidates are :class:`ResolutionCandidate` proposals only.

        This method does not commit any identity. It emits proposals for the
        admission/review gate.
        """
        splink = self._require()
        conn = self._backend.connect()

        try:
            from splink.duckdb.duckdb_linker import DuckDBLinker  # type: ignore

            linker = DuckDBLinker(
                input_dataframe_or_table=records,
                settings=settings,
                connection=conn,
                input_table_aliases=["person_records"],
            )

            try:
                linker.estimate_parameters_using_expectation_maximisation(
                    "person_records"
                )
                calibrated = True
            except Exception:
                calibrated = False

            predictions = linker.predict(threshold_match_probability=0.0)
            df = predictions.as_pandas_dataframe()

            candidates: list[ResolutionCandidate] = []
            for _, row in df.iterrows():
                left = str(row.get("unique_id_l", ""))
                right = str(row.get("unique_id_r", ""))
                if not left or not right or left == right:
                    continue
                score = row.get("match_probability")
                semantics = (
                    ScoreSemantics.MATCH_PROBABILITY
                    if calibrated
                    else ScoreSemantics.UNCALIBRATED_WEIGHT
                )
                vector: list[ComparisonVectorEntry] = []
                for col in df.columns:
                    if col.startswith("cf_"):
                        vector.append(
                            ComparisonVectorEntry(
                                field=col[3:],
                                comparison_level=str(row.get(col, "")),
                                value_l=row.get(f"{col}_l"),
                                value_r=row.get(f"{col}_r"),
                            )
                        )
                candidates.append(
                    self.to_candidate(
                        left_id=left,
                        right_id=right,
                        score=float(score) if score is not None else None,
                        score_semantics=semantics,
                        comparison_vector=tuple(vector),
                        model_fingerprint=self._fingerprint(settings),
                        blocking_rules_digest=blocking_rules_digest,
                    )
                )

            return self.to_result(
                candidates=tuple(candidates),
                model_fingerprint=self._fingerprint(settings),
                training_row_count=len(records),
                calibrated=calibrated,
            )
        finally:
            try:
                conn.close()
            except Exception:
                pass

    @staticmethod
    def _fingerprint(settings: dict[str, Any]) -> str:
        """Deterministic fingerprint of the settings + blocking rules."""
        import hashlib

        material = json.dumps(settings, sort_keys=True)
        return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


__all__ = [
    "SPLINK_VERSION_PINNED",
    "SPLINK_VERSION_SUPPORTED",
    "ComparisonVectorEntry",
    "ResolutionCandidate",
    "ScoreSemantics",
    "SplinkAdapter",
    "SplinkResult",
    "SplinkUnavailable",
    "DuckDBBackend",
]