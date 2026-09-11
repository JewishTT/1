"""Claim registration (T093, FR-001/002/007; interface-contracts §1).

Entry point for the Scientific Intelligence Fabric. Every registration runs the
scope-boundary guard first (FR-007), then refuses empty/unresolvable provenance
(FR-001) and undeclared probability methods (FR-002) — a claim's numbers are
always tied to recorded models and immutable observations. On success the claim
is projected into the event-replayable store and emitted as a
``science.claim.registered`` envelope (refs-only, I-5; I-12 rebuildable).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from _events import envelope as _emit
from causal.scope import ensure_scoped
from claims.model import ClaimStatus, CredenceDistribution, EvidenceLink, ScientificClaim
from claims.provenance import Observation, ObservationResolver, validate_provenance
from errors import UnknownModelError

# Declared probability models (FR-002): method id+version -> provenance-generating
# kernel. Only methods registered here may back a claim's distribution.
DECLARED_MODELS: dict[str, dict[str, Any]] = {
    "binomial-kde@1.0": {"family": "posterior-binomial", "description": "binomial posterior with KDE smoothing"},
    "logit@1.0": {"family": "logistic-regression", "description": "logistic calibration kernel"},
}

# Hermetic observation ledger used by the default resolver: observation_id ->
# content-addressed raw sha256 (Constitution I, immutable raw).
_OBSERVATIONS: dict[str, str] = {}


def register_model(model_id: str, *, family: str, description: str = "") -> None:
    """Declare a probability model the fabric will accept (FR-002)."""
    DECLARED_MODELS[model_id] = {"family": family, "description": description}


def set_observations(observations: Mapping[str, str]) -> None:
    """Bind observation_id -> raw_sha256 so provenance can resolve (hermetic default)."""
    _OBSERVATIONS.update(observations)


class _StoredObservation(Observation):
    def __init__(self, observation_id: str, raw_sha256: str) -> None:
        self.observation_id = observation_id
        self.raw_sha256 = raw_sha256


def _resolve_observed(observation_id: str) -> Observation | None:
    raw_sha256 = _OBSERVATIONS.get(observation_id)
    if raw_sha256 is None:
        return None
    return _StoredObservation(observation_id, raw_sha256)


def _claim_id(
    statement: str, method: str, provenance: list[EvidenceLink]
) -> str:
    refs = json.dumps(
        [link.to_ref() for link in provenance], sort_keys=True, default=str
    )
    digest = hashlib.sha256(
        f"{statement}|{method}|{refs}".encode()
    ).hexdigest()[:12]
    return f"SC-{digest}"


def register_claim(
    *,
    project_id: str,
    statement: str,
    distribution: CredenceDistribution,
    provenance: list[EvidenceLink],
    producer_run: str | None = None,
    tenant_id: str = "default-tenant",
    resolver: ObservationResolver | None = None,
    producer: Any = None,
    store: Any = None,
) -> ScientificClaim:
    """Register a fully-provenanced, method-bound probabilistic claim.

    Invariants (interface-contracts §1): provenance non-empty and resolvable to
    immutable observations; ``distribution.method`` must be a declared model;
    person-sensitive statements are refused before anything is computed.
    """
    resolve = resolver if resolver is not None else _resolve_observed

    # FR-007: scope guard FIRST — nothing is computed on a refused outcome.
    ensure_scoped(
        statement,
        entry_point="register_claim",
        actor=tenant_id,
        producer=producer,
    )

    if distribution.method not in DECLARED_MODELS:
        raise UnknownModelError(distribution.method)

    validate_provenance(provenance, resolve)  # FR-001: raises on unresolved chain
    claim = ScientificClaim(
        claim_id=_claim_id(statement, distribution.method, provenance),
        project_id=project_id,
        statement=statement,
        distribution=distribution,
        model_id=distribution.method,
        status=ClaimStatus.DRAFT,
        provenance=provenance,
        producer_run=producer_run,
    )

    payload = claim.to_ref()
    payload["statement"] = statement
    payload["tenant_id"] = tenant_id
    payload["producer_run"] = producer_run
    payload["distribution_ref"] = distribution.method
    payload["distribution"] = {
        "states": distribution.states,
        "labels": distribution.labels,
        "probs": distribution.probs,
        "method": distribution.method,
        "calibration_ref": distribution.calibration_ref,
    }
    env = _emit(
        event_type="science.claim.registered",
        payload=payload,
        producer=producer,
        investigation_id=project_id,
    )
    if store is not None:
        store.apply(env)
    return claim