"""Adapters over the discipline code that already exists (spec 025 §30.4).

    Donor implementation -> Adapter -> ReasoningOperator -> Registry

Every operator in this module is a thin wrapper around working, tested code in
this same package. Nothing here re-implements a discipline. That is the whole
point of §30.4 -- "Donors are implementation sources, not domain authorities" --
applied to the platform's own first-party packages.

What an adapter adds is the part the discipline code does not have: a declared
determinism class, a numeric mode, a declared cost, an input/output contract, and
an explanation. The discipline function keeps its own signature and semantics; the
adapter makes it selectable and auditable.

Determinism was assigned per operator from the code, not defaulted:

* ``EXACT`` -- integer/structural output: change points, macro-state graphs.
* ``FLOAT_QUANTIZED`` -- float output with no tolerance contract, e.g. barcodes,
  order parameters, Wasserstein distances.
* ``FIXED_POINT`` -- reserved for declared-scale quantities; nothing here claims
  it yet, because nothing here declares a scale.

Registrations are explicit and idempotent rather than import-time magic, so a
caller can build an isolated registry in a test and a caller can see exactly
which capabilities exist.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from context.locality import CellKind
from context.operators.base import (
    ComplexityClass,
    ComplexityModel,
    ContractRef,
    Determinism,
    ExplanationTrace,
    MemoryClass,
    NumericMode,
    OperatorClass,
    OperatorRegistration,
    OperatorResult,
    Tier,
    ValidationResult,
)
from context.operators.registry import _Registry

# Contracts are named per §30.2 so a consumer can check shape before running.
CELL_VIEW = ContractRef("context_cell_view", "1.0")
SERIES_VIEW = ContractRef("temporal_series_view", "1.0")
GRAPH_VIEW = ContractRef("structure_graph_view", "1.0")
EVIDENCE_VIEW = ContractRef("evidence_view", "1.0")
PREDICTION_VIEW = ContractRef("prediction_view", "1.0")
HYPOTHESIS_VIEW = ContractRef("hypothesis_view", "1.0")
TRAJECTORY_VIEW = ContractRef("field_trajectory_view", "1.0")
LANDSCAPE_VIEW = ContractRef("belief_landscape_view", "1.0")

VERDICT = ContractRef("operator_verdict", "1.0")
BARCODE_SET = ContractRef("barcode_collection", "1.0")
CHANGE_POINTS = ContractRef("change_point_list", "1.0")
STRUCTURE_RESULT = ContractRef("structure_analysis_result", "1.0")
CAUSAL_CONCLUSION = ContractRef("causal_conclusion", "1.0")
CALIBRATION_REPORT = ContractRef("calibration_report", "1.0")
RANKED_OPPORTUNITIES = ContractRef("ranked_opportunity_list", "1.0")
ROBUSTNESS_REPORT = ContractRef("robustness_report", "1.0")
PHASE_REPORT = ContractRef("phase_report", "1.0")
BELIEF_LANDSCAPE = ContractRef("belief_landscape", "1.0")
MACRO_GRAPH = ContractRef("macro_transition_graph", "1.0")

#: Dependency versions recorded from the moment of registration (R7): a
#: fingerprint retrofitted later cannot be trusted to describe a past run.
DEPENDENCY_FINGERPRINT = "science-0.1.0+numpy"


class _Adapter:
    """Shared plumbing: identity, contracts, determinism, explanation.

    Subclasses declare metadata and implement :meth:`_compute`. This keeps the
    ten adapters below to their real content -- the call and the capability set --
    instead of ten copies of protocol boilerplate.
    """

    id: str = ""
    operator_class: OperatorClass = OperatorClass.NORMALIZATION
    input_contract: ContractRef = CELL_VIEW
    output_contract: ContractRef = VERDICT
    determinism: Determinism = Determinism.FLOAT_QUANTIZED
    numeric_mode: NumericMode = NumericMode.FLOAT_QUANTIZED
    complexity: ComplexityModel = ComplexityModel()
    capabilities: frozenset[str] = frozenset()
    tier: Tier = Tier.STATISTICAL
    summary: str = ""

    version: str = "1.0"

    def validate_input(self, input_view: Any) -> ValidationResult:
        if self.input_contract.name == "temporal_series_view":
            return self._validate_series(input_view)
        if self.input_contract.name == "belief_landscape_view":
            return self._validate_landscape(input_view)
        if input_view is None:
            return ValidationResult.reject("input_view is required")
        return ValidationResult.accept()

    def _validate_series(self, input_view: Any) -> ValidationResult:
        values = getattr(input_view, "values", None)
        if values is None:
            return ValidationResult.reject("input_view must expose .values")
        if len(values) == 0:
            return ValidationResult.reject("series carries no samples")
        return ValidationResult.accept()

    def _validate_landscape(self, input_view: Any) -> ValidationResult:
        size = getattr(input_view, "size", None)
        if size is None:
            return ValidationResult.reject("input_view must expose .size")
        if int(size) == 0:
            return ValidationResult.reject("point cloud is empty")
        return ValidationResult.accept()

    def _compute(self, input_view: Any, parameters: Any, seed: int) -> Any:
        raise NotImplementedError

    def run(self, input_view: Any, parameters: Any = None, seed: int = 0) -> OperatorResult:
        validation = self.validate_input(input_view)
        if not validation.ok:
            return OperatorResult(
                operator_id=self.id,
                operator_version=self.version,
                determinism=self.determinism,
                value=None,
                deferred=True,
                deferral_reason="; ".join(validation.errors) or "input rejected",
            )
        value = self._compute(input_view, parameters, seed)
        return OperatorResult(
            operator_id=self.id,
            operator_version=self.version,
            determinism=self.determinism,
            value=value,
            dependency_fingerprint=DEPENDENCY_FINGERPRINT,
            method_fingerprint=f"{self.id}@{self.version}",
            explanation=self._explain(parameters, seed),
        )

    def _explain(
        self, parameters: Any, seed: int
    ) -> ExplanationTrace:
        return ExplanationTrace(
            operator_id=self.id,
            summary=self.summary or f"{self.id} adapter",
            inputs_used=(str(self.input_contract),),
            parameters_used=dict(parameters) if isinstance(parameters, dict) else {},
            seed=seed,
        )

    def explain(self, result: OperatorResult) -> ExplanationTrace:
        return result.explanation or ExplanationTrace(
            operator_id=self.id, summary="no trace recorded"
        )


class TdaOperator(_Adapter):
    id = "tda.persistence"
    operator_class = OperatorClass.TDA
    input_contract = ContractRef("distance_matrix", "1.0")
    output_contract = BARCODE_SET
    determinism = Determinism.FLOAT_QUANTIZED
    complexity = ComplexityModel(
        time=ComplexityClass.ON_CUBED, memory=MemoryClass.QUADRATIC, budget_ms=2000
    )
    capabilities = frozenset({"persistence", "topology", "clustering", "barcodes"})
    summary = "Vietoris-Rips filtration, Z2 reduction, birth-death bars"

    def _compute(self, input_view: Any, parameters: Any, seed: int) -> Any:
        from scitda.persistence import from_distance_matrix

        options = parameters if isinstance(parameters, dict) else {}
        return from_distance_matrix(
            input_view,
            max_dim=int(options.get("max_dim", 2)),
            budget=int(options.get("budget", 4096)),
        )


class ChangePointOperator(_Adapter):
    id = "temporal.change_point"
    operator_class = OperatorClass.CHANGE_POINT
    input_contract = SERIES_VIEW
    output_contract = CHANGE_POINTS
    determinism = Determinism.EXACT
    numeric_mode = NumericMode.EXACT
    complexity = ComplexityModel(time=ComplexityClass.ON, memory=MemoryClass.LINEAR)
    capabilities = frozenset({"change_point", "regime_boundary", "drift"})
    tier = Tier.DETERMINISTIC
    summary = "windowed mean-shift detection with non-maximum suppression"

    def _compute(self, input_view: Any, parameters: Any, seed: int) -> Any:
        from temporal.changedetect import ChangeDetectParams, detect_change_points

        options = parameters if isinstance(parameters, dict) else {}
        return detect_change_points(
            input_view,
            ChangeDetectParams(
                window=int(options.get("window", 5)),
                min_shift=float(options.get("min_shift", 1.0)),
                min_spacing=int(options.get("min_spacing", 6)),
            ),
        )


class StructureOperator(_Adapter):
    id = "structure.analyze"
    operator_class = OperatorClass.GRAPH_ANALYSIS
    input_contract = GRAPH_VIEW
    output_contract = STRUCTURE_RESULT
    determinism = Determinism.FLOAT_QUANTIZED
    complexity = ComplexityModel(
        time=ComplexityClass.ON_SQUARED, memory=MemoryClass.LINEAR, budget_ms=5000
    )
    capabilities = frozenset({"graph_structure", "motif", "spectral", "null_model"})
    summary = "budget-bounded structural kernel with degree-preserving null model"

    def _compute(self, input_view: Any, parameters: Any, seed: int) -> Any:
        from structure.graph import AnalysisBudget, NullParams, analyze
        from structure.model import StructureKind

        options = parameters if isinstance(parameters, dict) else {}
        kind = options.get("kind", StructureKind.MOTIF)
        if isinstance(kind, str):
            kind = StructureKind(kind)
        return analyze(
            input_view,
            budget=options.get("budget") or AnalysisBudget(),
            kind=kind,
            null_params=options.get("null_params") or NullParams(),
        )


class CausalOperator(_Adapter):
    id = "causal.classify"
    operator_class = OperatorClass.CAUSAL
    input_contract = EVIDENCE_VIEW
    output_contract = CAUSAL_CONCLUSION
    determinism = Determinism.FLOAT_QUANTIZED
    capabilities = frozenset({"causal", "attribution", "refutation"})
    summary = "staged identification/estimation/refutation classification"

    def _compute(self, input_view: Any, parameters: Any, seed: int) -> Any:
        from causal.infer import classify

        options = parameters if isinstance(parameters, dict) else {}
        return classify(
            input_view,
            options.get("model"),
            outcome_attribute=options.get("outcome_attribute"),
            possible_confounders=options.get("possible_confounders"),
        )


class CalibrationOperator(_Adapter):
    id = "calibration.assess"
    operator_class = OperatorClass.CALIBRATION
    input_contract = PREDICTION_VIEW
    output_contract = CALIBRATION_REPORT
    determinism = Determinism.FLOAT_QUANTIZED
    capabilities = frozenset({"calibration", "brier", "ece", "overconfidence"})
    summary = "decile reliability, Brier score, expected calibration error"

    def _compute(self, input_view: Any, parameters: Any, seed: int) -> Any:
        from claims.calibration import calibrate

        options = parameters if isinstance(parameters, dict) else {}
        return calibrate(
            options.get("model_id", "unidentified"),
            input_view,
            thresholds=options.get("thresholds"),
        )


class InformationGainOperator(_Adapter):
    id = "gain.plan_collection"
    operator_class = OperatorClass.INFORMATION_GAIN
    input_contract = HYPOTHESIS_VIEW
    output_contract = RANKED_OPPORTUNITIES
    determinism = Determinism.FLOAT_QUANTIZED
    capabilities = frozenset({"information_gain", "discrimination", "collection_planning"})
    summary = "expected-KL ranking with discriminating pair selection"

    def _compute(self, input_view: Any, parameters: Any, seed: int) -> Any:
        from hypotheses.gain import plan_collection

        options = parameters if isinstance(parameters, dict) else {}
        return plan_collection(
            options.get("project_id", "default-tenant"),
            list(input_view),
            int(options.get("budget", 5)),
            hypotheses=options.get("hypotheses"),
        )


class RobustnessOperator(_Adapter):
    id = "robustness.analyze"
    operator_class = OperatorClass.SATURATION
    input_contract = EVIDENCE_VIEW
    output_contract = ROBUSTNESS_REPORT
    determinism = Determinism.FLOAT_QUANTIZED
    capabilities = frozenset({"robustness", "sensitivity", "flip_rate", "stability"})
    summary = "perturbation grid over missing/flip/bias families with flip rates"

    def _compute(self, input_view: Any, parameters: Any, seed: int) -> Any:
        from robustness.perturb import PerturbationGrid
        from robustness.report import analyze_robustness

        options = parameters if isinstance(parameters, dict) else {}
        return analyze_robustness(
            options.get("claim_id", ""),
            input_view,
            perturbations=options.get("perturbations") or PerturbationGrid(),
        )


class RegimeOperator(_Adapter):
    id = "regime.phase"
    operator_class = OperatorClass.REGIME
    input_contract = TRAJECTORY_VIEW
    output_contract = PHASE_REPORT
    determinism = Determinism.FLOAT_QUANTIZED
    complexity = ComplexityModel(
        time=ComplexityClass.ON, memory=MemoryClass.LINEAR, budget_ms=500
    )
    capabilities = frozenset({"regime", "phase", "critical_slowing", "hysteresis"})
    summary = "Kuramoto order parameter, Ginzburg-Landau potential, hysteresis loop area"

    def _compute(self, input_view: Any, parameters: Any, seed: int) -> Any:
        from operators.phase import analyze_trajectory

        options = parameters if isinstance(parameters, dict) else {}
        return analyze_trajectory(
            input_view,
            control_path=options.get("control_path"),
            backward_field=options.get("backward_field"),
            r_critical=float(options.get("r_critical", 1.5)),
        )


class BeliefLandscapeOperator(_Adapter):
    id = "state.belief_landscape"
    operator_class = OperatorClass.STATE_ESTIMATION
    input_contract = LANDSCAPE_VIEW
    output_contract = BELIEF_LANDSCAPE
    determinism = Determinism.FLOAT_QUANTIZED
    complexity = ComplexityModel(
        time=ComplexityClass.ON_SQUARED, memory=MemoryClass.QUADRATIC, budget_ms=3000
    )
    capabilities = frozenset({"belief_state", "attractor", "forecast"})
    summary = "gradient flow, attractor basins, aggregate forecast path"

    def _compute(self, input_view: Any, parameters: Any, seed: int) -> Any:
        from beliefs.landscape import analyze_landscape

        options = parameters if isinstance(parameters, dict) else {}
        return analyze_landscape(
            input_view,
            seeds=options.get("seeds"),
            max_steps=int(options.get("max_steps", 400)),
            step_size=float(options.get("step_size", 0.05)),
        )


class KineticsOperator(_Adapter):
    id = "state.macro_pathways"
    operator_class = OperatorClass.STATE_ESTIMATION
    input_contract = SERIES_VIEW
    output_contract = MACRO_GRAPH
    determinism = Determinism.EXACT
    numeric_mode = NumericMode.EXACT
    complexity = ComplexityModel(time=ComplexityClass.ON, memory=MemoryClass.LINEAR)
    capabilities = frozenset({"macro_state", "pathway", "bottleneck", "transition"})
    tier = Tier.DETERMINISTIC
    summary = "macro-state discretization with min-edge-flux dominant pathways"

    def _compute(self, input_view: Any, parameters: Any, seed: int) -> Any:
        from kinetics.pathways import build_macro_graph

        options = parameters if isinstance(parameters, dict) else {}
        values = getattr(input_view, "values", input_view)
        return build_macro_graph(values, float(options.get("tolerance", 0.1)))


class CompatibilityOperator(_Adapter):
    id = "compatibility.assess"
    operator_class = OperatorClass.COMPATIBILITY
    input_contract = ContractRef("cell_pair", "1.0")
    output_contract = ContractRef("compatibility_assessment", "1.0")
    determinism = Determinism.EXACT
    numeric_mode = NumericMode.EXACT
    complexity = ComplexityModel(time=ComplexityClass.O1, memory=MemoryClass.CONSTANT)
    capabilities = frozenset({"compatibility", "locality", "pairwise", "overlap"})
    #: Tier 0 because §9's dimensions are deterministic structural comparisons --
    #: no statistical discipline is involved.
    tier = Tier.DETERMINISTIC
    summary = "eight-dimension assessment with refutation reachable, no weighted score"

    def _compute(self, input_view: Any, parameters: Any, seed: int) -> Any:
        from context.operators.compatibility import assess_pair

        left, right = input_view
        options = parameters if isinstance(parameters, dict) else {}
        return assess_pair(
            left,
            right,
            overlap_id=options.get("overlap_id", ""),
            method_fingerprint=options.get("method_fingerprint", ""),
            overrides=options.get("overrides"),
        )


class GluingOperator(_Adapter):
    id = "gluing.glue"
    operator_class = OperatorClass.GLUING
    input_contract = ContractRef("cell_collection", "1.0")
    output_contract = ContractRef("gluing_result", "1.0")
    determinism = Determinism.EXACT
    numeric_mode = NumericMode.EXACT
    complexity = ComplexityModel(
        time=ComplexityClass.ON_SQUARED, memory=MemoryClass.LINEAR, budget_ms=5000
    )
    capabilities = frozenset({"gluing", "triple_coherence", "merge", "coherence"})
    tier = Tier.DETERMINISTIC
    summary = "bounded blocking plus cocycle-style triple coherence; GLUED never claimed unchecked"

    def _compute(self, input_view: Any, parameters: Any, seed: int) -> Any:
        from context.operators.gluing import GluingProfile, glue

        cells, context_id = input_view
        options = parameters if isinstance(parameters, dict) else {}
        profile = options.get("profile") or GluingProfile(
            allows_partial_gluing=bool(options.get("allows_partial_gluing", True)),
            max_triples=int(options.get("max_triples", 20_000)),
            max_bucket_size=int(options.get("max_bucket_size", 256)),
        )
        return glue(cells, context_id=context_id, profile=profile)


class IndependenceOperator(_Adapter):
    id = "independence.assess"
    operator_class = OperatorClass.INDEPENDENCE
    input_contract = ContractRef("evidence_lineage_view", "1.0")
    output_contract = ContractRef("independence_assessment", "1.0")
    determinism = Determinism.EXACT
    numeric_mode = NumericMode.FIXED_POINT
    complexity = ComplexityModel(time=ComplexityClass.ON, memory=MemoryClass.LINEAR)
    capabilities = frozenset({"independence", "n_eff", "dependency_group", "syndication"})
    #: Deterministic: grouping is a partition of declared lineage, not a statistic.
    tier = Tier.DETERMINISTIC
    summary = "lineage-derived dependency groups; unknown lineage collapses to one group"

    def _compute(self, input_view: Any, parameters: Any, seed: int) -> Any:
        from context.coverage import assess_independence

        items, lineage = input_view
        options = parameters if isinstance(parameters, dict) else {}
        return assess_independence(
            list(items),
            dict(lineage),
            assessed_by=str(options.get("assessed_by") or self.id),
        )


class SaturationOperator(_Adapter):
    id = "saturation.assess"
    operator_class = OperatorClass.SATURATION
    input_contract = ContractRef("obligation_progress_view", "1.0")
    output_contract = ContractRef("saturation_state", "1.0")
    determinism = Determinism.FLOAT_QUANTIZED
    complexity = ComplexityModel(time=ComplexityClass.O1, memory=MemoryClass.CONSTANT)
    capabilities = frozenset({"saturation", "closure", "coverage", "termination"})
    tier = Tier.DETERMINISTIC
    summary = "closure decision on n_eff, families and coverage, never on raw count"

    def _compute(self, input_view: Any, parameters: Any, seed: int) -> Any:
        from context.coverage import assess_saturation

        obligation_id, assessment = input_view
        options = parameters if isinstance(parameters, dict) else {}
        return assess_saturation(
            obligation_id,
            assessment=assessment,
            coverage=options.get("coverage"),
            source_families=int(options.get("source_families", 0)),
            marginal_gain=options.get("marginal_gain"),
            unexplored_capability_classes=options.get("unexplored_capability_classes", ()),
            contradiction_count=int(options.get("contradiction_count", 0)),
            unresolved_obstruction_count=int(options.get("unresolved_obstruction_count", 0)),
            qualified_absences=options.get("qualified_absences", ()),
        )


class DialecticsOperator(_Adapter):
    """§18: expose the strongest competing interpretation rather than converging.

    Generating a counter-hypothesis is the cheap half; the expensive half is
    refusing to let a straw man stand in for a real rival. The parity audit is
    carried in the result so a weakened antithesis is visible downstream rather
    than silently inflating the thesis.
    """

    id = "dialectics.counter_hypothesis"
    operator_class = OperatorClass.DIALECTICS
    input_contract = ContractRef("hypothesis_space_view", "1.0")
    output_contract = ContractRef("dialectical_pair_list", "1.0")
    determinism = Determinism.EXACT
    numeric_mode = NumericMode.EXACT
    complexity = ComplexityModel(time=ComplexityClass.ON, memory=MemoryClass.LINEAR)
    capabilities = frozenset({
        "dialectics", "counter_hypothesis", "steelman_parity", "premise_extraction",
    })
    tier = Tier.DETERMINISTIC
    summary = "counter-hypothesis generation with a recorded steelman parity audit"

    def _compute(self, input_view: Any, parameters: Any, seed: int) -> Any:
        from context.dialectics import generate_counter_hypotheses

        space, thesis = input_view
        options = parameters if isinstance(parameters, dict) else {}
        pairs, outcome = generate_counter_hypotheses(
            space,
            thesis,
            templates=tuple(options.get("templates", ())),
            budget=int(options.get("budget", 8)),
            evidence_available=bool(options.get("evidence_available", True)),
        )
        return {"pairs": pairs, "outcome": outcome}


class ArgumentationOperator(_Adapter):
    """§19/§18: rank the non-dominated candidates under a declared mode.

    §20.3 removed the v1 multiplicative utility and replaced it with declared
    ranking modes, so this operator ranks rather than multiplies and names the mode
    it used.
    """

    id = "argumentation.rank"
    operator_class = OperatorClass.ARGUMENTATION
    input_contract = ContractRef("candidate_list", "1.0")
    output_contract = ContractRef("ranked_candidate_list", "1.0")
    determinism = Determinism.EXACT
    numeric_mode = NumericMode.EXACT
    complexity = ComplexityModel(time=ComplexityClass.ON_LOG_N, memory=MemoryClass.LINEAR)
    capabilities = frozenset({"argumentation", "ranking", "dominance", "tradeoff"})
    tier = Tier.DETERMINISTIC
    summary = "declared ranking modes; never the removed multiplicative utility"

    def _compute(self, input_view: Any, parameters: Any, seed: int) -> Any:
        from context.argumentation import rank_candidates

        options = parameters if isinstance(parameters, dict) else {}
        return rank_candidates(
            list(input_view), mode=str(options.get("mode") or "LEXICOGRAPHIC")
        )


class GrowthOperator(_Adapter):
    """§I.7's omitted branch: a change batch may open new scopes, not only refine.

    This is the step that lets an investigation deepen. Without it the pseudocode's
    ``recompute_cells`` has no creation branch, and an observation revealing a new
    scope has nowhere to go -- so the context either drops it (forbidden by §0.2) or
    folds it into a neighbour and flattens.
    """

    id = "growth.extend_cells"
    operator_class = OperatorClass.NORMALIZATION
    input_contract = ContractRef("cell_collection_change_view", "1.0")
    output_contract = ContractRef("growth_result", "1.0")
    determinism = Determinism.EXACT
    numeric_mode = NumericMode.EXACT
    complexity = ComplexityModel(
        time=ComplexityClass.ON_SQUARED, memory=MemoryClass.LINEAR, budget_ms=2000
    )
    capabilities = frozenset({"growth", "cell_creation", "anchoring", "change_batch"})
    tier = Tier.DETERMINISTIC
    summary = "anchored cell creation for scopes no cell covers; refusals recorded"

    def _compute(self, input_view: Any, parameters: Any, seed: int) -> Any:
        from context.growth import extend_or_recompute_cells

        context_id, cells, incoming = input_view
        options = parameters if isinstance(parameters, dict) else {}
        return extend_or_recompute_cells(
            context_id,
            list(cells),
            dict(incoming),
            revealed_by=options.get("revealed_by"),
            invalidated=options.get("invalidated", ()),
            kind=options.get("kind", CellKind.DOCUMENT),
            temporal_slice=tuple(options.get("temporal_slice", ())),
            semantic_regime_ref=str(options.get("semantic_regime_ref") or ""),
            produced_by=str(options.get("produced_by") or self.id),
            method_fingerprint=str(options.get("method_fingerprint") or f"{self.id}@{self.version}"),
        )


class CompletenessOperator(_Adapter):
    """§33/Appendix P: the mode is derived from conditions, never requested.

    Exposed as an operator so the check cannot be skipped by a caller that simply
    does not call it -- the registry is the only way to reach it, and an absent
    capability returns an explicit gap rather than a silent default.
    """

    id = "completeness.assess"
    operator_class = OperatorClass.SATURATION
    input_contract = ContractRef("search_evidence_view", "1.0")
    output_contract = ContractRef("completeness_requirement", "1.0")
    determinism = Determinism.EXACT
    numeric_mode = NumericMode.EXACT
    complexity = ComplexityModel(time=ComplexityClass.O1, memory=MemoryClass.CONSTANT)
    capabilities = frozenset({
        "completeness", "coverage_mode", "universal_claim", "downgrade",
    })
    tier = Tier.DETERMINISTIC
    summary = "derives the achievable completeness mode and names unmet conditions"

    def _compute(self, input_view: Any, parameters: Any, seed: int) -> Any:
        from context.completeness import assess_completeness

        universe, evidence = input_view
        # No parameters are accepted here on purpose: the mode is a function of the
        # declared evidence, so a parameter that could override it would let a caller
        # assert a completeness the evidence does not support.
        return assess_completeness(universe=universe, **dict(evidence))


def build_default_registry() -> _Registry:
    """A registry holding every adapter in this module.

    Constructed on demand rather than at import time, so an isolated test can
    build an empty registry and assert on absence.
    """
    registry = _Registry()
    adapters: Sequence[type[_Adapter]] = (
        TdaOperator,
        ChangePointOperator,
        StructureOperator,
        CausalOperator,
        CalibrationOperator,
        InformationGainOperator,
        RobustnessOperator,
        RegimeOperator,
        BeliefLandscapeOperator,
        KineticsOperator,
        CompatibilityOperator,
        GluingOperator,
        IndependenceOperator,
        SaturationOperator,
        DialecticsOperator,
        ArgumentationOperator,
        GrowthOperator,
        CompletenessOperator,
    )
    for adapter in adapters:
        instance = adapter()
        registry.register(
            OperatorRegistration(
                operator=instance,
                capabilities=instance.capabilities,
                tier=instance.tier,
                license="platform-first-party",
                parameter_schema={"type": "object"},
                supports_incremental=False,
                supports_replay=True,
            )
        )
    return registry


def all_capabilities() -> frozenset[str]:
    """Every capability the built-in disciplines provide."""
    return build_default_registry().capabilities()
