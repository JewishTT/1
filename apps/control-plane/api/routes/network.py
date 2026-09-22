"""Network analytics API (T041/T043/T056/T058/T059/T060; FR-008).

Base path ``/api/v1/network`` — the analyst-facing HTTP surface for the
projection plane's network-structure stack: structural measures, community
detection, hypergraph metrics, temporal paths, quantitative TDA features
(diagram distance, entropy, landscapes, Betti curves) and spatiotemporal
persistent homology (PHoDMS).

Design rules honoured here:

- STRUCTURAL ONLY (I-6): these endpoints never mint entities, never claim
  identity — they describe the shape of an already-built projection.
- HONEST EMPTY (I-3): graphs with no edges, series with no bars, and clouds
  that are out of bounds return explicit empty/null states, never guesses.
- CONTENT-ADDRESSED (I-12): digests are sha256 over canonical payloads.
- DEFERRED, NEVER TRUNCATED (I-6): inputs outside the scope boundary are
  refused with 422 ``scope_refused``, not silently cut.

Module-level imports stay minimal so the app boots without the projection
sources on sys.path; projection/science packages are imported inside handlers
(the workspace venv injects every member source dir; apps/science precedes
apps/projection, which shadows ``tda`` — so projection's ``features`` module is
bridged by its own file path, keeping the authored implementation reachable).
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/network", tags=["network"])

_FEATURES_MODULE = None
_FEATURES_PATH = Path(__file__).resolve().parents[3] / "projection" / "tda" / "features.py"


class EdgeModel(BaseModel):
    source: str
    target: str
    edge_type: str = "link"
    properties: dict[str, Any] = Field(default_factory=dict)


class TimedEdgeModel(BaseModel):
    source: str
    target: str
    t: float
    edge_id: str = ""


class MeasuresRequest(BaseModel):
    edges: list[EdgeModel]


class CommunitiesRequest(BaseModel):
    edges: list[EdgeModel]


class HypergraphRequest(BaseModel):
    observations: dict[str, list[str]]
    min_degree: int = Field(default=1, ge=1)


class TemporalRequest(BaseModel):
    edges: list[TimedEdgeModel]
    source: str | None = None
    target: str | None = None


class DiagramFeaturesRequest(BaseModel):
    entity_id: str
    series: list[float]
    lag: int = Field(default=2, ge=1)
    embed_dim: int = Field(default=2, ge=2)
    max_dim: int = Field(default=1, ge=0, le=2)
    budget: int = Field(default=8192, ge=1, le=65536)
    prev_diagrams: dict[int, list[list[float | None]]] | None = None
    metric: str = Field(default="bottleneck", pattern="^(bottleneck|wasserstein)$")


class PhodmsRequest(BaseModel):
    clouds: list[list[list[float]]]
    thresholds: list[float] = Field(default_factory=lambda: [0.5, 1.0, 1.5, 2.0])


def _build_view(edges: list[EdgeModel]):
    from graph.adjacency import build_adjacency

    tuples = [(edge.source, edge.target, edge.edge_type) for edge in edges]
    return build_adjacency(tuples)


def _scope_guard(condition: bool) -> None:
    if not condition:
        raise HTTPException(
            status_code=422,
            detail={"error": "scope_refused", "policy": "contracts/scope-boundary.md"},
        )


def _load_projection_features() -> Any | None:
    """Bridge projection/tda/features.py (shadowed by science/tda on PYTHONPATH).

    Lazily imported once, cached at module scope. Honest ``None`` when the
    authored module is not present on disk (a deployment without the projection
    sources degrades to a plain structural digest instead of crashing).
    """
    global _FEATURES_MODULE
    if _FEATURES_MODULE is not None:
        return _FEATURES_MODULE
    if not _FEATURES_PATH.exists():
        _FEATURES_MODULE = False
        return None
    spec = importlib.util.spec_from_file_location("projection_tda_features", _FEATURES_PATH)
    if spec is None or spec.loader is None:
        _FEATURES_MODULE = False
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules["projection_tda_features"] = module  # dataclass/repr lookups
    spec.loader.exec_module(module)
    _FEATURES_MODULE = module
    return module


@router.post("/measures")
async def post_measures(body: MeasuresRequest) -> dict[str, Any]:
    """Structural measures over an explicit edge set (T059)."""
    from metrics.network_measures import network_measures

    view = _build_view(body.edges)
    measures = network_measures(view)
    payload = measures.as_dict()
    payload["degree_centrality"] = view.degree_centrality()
    payload["n_edges_explicit"] = len(view.edges)
    payload["structural_only"] = True  # I-6
    return payload


@router.post("/communities")
async def post_communities(body: CommunitiesRequest) -> dict[str, Any]:
    """Community partition via deterministic label propagation (T059)."""
    from metrics.community import label_propagation, modularity

    view = _build_view(body.edges)
    partition = label_propagation(view)
    communities: dict[str, list[str]] = {}
    for node in sorted(partition):
        communities.setdefault(partition[node], []).append(node)
    return {
        "structural_only": True,
        "n_nodes": len(view.nodes),
        "n_edges": len(view.edges),
        "community_count": len(communities),
        "modularity_q": round(float(modularity(partition, view)), 9),
        "communities": communities,
    }


@router.post("/hypergraph")
async def post_hypergraph(body: HypergraphRequest) -> dict[str, Any]:
    """Co-mention hypergraph metrics over observations (T058)."""
    from metrics.hypergraph_metrics import hypergraph_from_observations

    if not body.observations:
        raise HTTPException(status_code=422, detail="empty observation set")
    hypergraph = hypergraph_from_observations(body.observations, min_degree=body.min_degree)
    payload = hypergraph.as_dict()
    payload["hyperedge_sizes"] = {str(k): v for k, v in hypergraph.edge_sizes().items()}
    payload["node_degrees"] = {
        node: hypergraph.node_degree(node) for node in hypergraph.nodes
    }
    payload["structural_only"] = True
    return payload


@router.post("/temporal")
async def post_temporal(body: TemporalRequest) -> dict[str, Any]:
    """Temporal journeys, reachability and motif counts (T041/T060)."""
    from metrics.temporal_paths import TemporalGraph, TimedEdge

    if not body.edges:
        raise HTTPException(status_code=422, detail="empty edge set")
    graph = TemporalGraph(
        edges=[
            TimedEdge(source=edge.source, target=edge.target, t=edge.t, edge_id=edge.edge_id)
            for edge in body.edges
        ]
    )
    payload: dict[str, Any] = {
        "structural_only": True,
        "n_nodes": len(graph.nodes),
        "n_edges": graph.num_edges(),
        "nodes": graph.nodes,
        "distance_matrix": graph.temporal_distance_matrix(),
        "motifs": graph.count_temporal_motifs(),
        "timeline": graph.timeline(),
    }
    if body.source is not None:
        payload["reachable_from"] = graph.reachable_from(body.source)
    if body.source is not None and body.target is not None:
        journey, arrival = graph.journey(body.source, body.target)
        payload["journey"] = (
            [
                {
                    "source": edge.source,
                    "target": edge.target,
                    "t": edge.t,
                    "edge_id": edge.edge_id,
                }
                for edge in journey
            ],
            arrival,
        )
    return payload


@router.post("/diagram-features")
async def post_diagram_features(body: DiagramFeaturesRequest) -> dict[str, Any]:
    """Quantitative TDA features over VR diagrams (T043; unifies both stacks).

    The diagram itself is produced by the pure-python science stack
    (``tda.persistence``), then the projection plane's diagram-distance
    features (bottleneck/Wasserstein amplitude, persistence entropy,
    landscapes, Betti curves) and real between-window drift are computed by the
    authored ``projection.tda.features`` module — bridged via file path because
    the ``tda`` top-level name collides between the two first-party apps.
    """
    from tda.persistence import from_distance_matrix
    from tda.series import embedding_distance_matrix

    features_module = _load_projection_features()
    if features_module is None:
        raise HTTPException(status_code=501, detail="projection features unavailable")

    _scope_guard(0 < len(body.series) <= 256)
    _scope_guard(len(body.series) >= body.lag * body.embed_dim)

    try:
        barcodes = from_distance_matrix(
            embedding_distance_matrix(body.series, lag=body.lag, dim=body.embed_dim),
            max_dim=body.max_dim,
            budget=body.budget,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "topology_scope_exceeded", "detail": str(exc)},
        ) from exc

    diagrams: dict[int, list[list[float | None]]] = {}
    for barcode in barcodes.barcodes:
        if not barcode.bars:
            continue
        bars: list[list[float | None]] = []
        for birth, death in barcode.bars:
            bars.append([float(birth), None if (death is None or math.isinf(death)) else float(death)])
        diagrams[int(barcode.dimension)] = bars

    pairs: dict[int, list[tuple[float, float | None]]] = {
        int(dim): [(float(p[0]), None if p[1] is None else float(p[1])) for p in bars]
        for dim, bars in diagrams.items()
    }

    # The projection feature set cannot vectorize an empty diagram
    # (betti_curve max over zero pairs) — feed it only live dimensions and
    # keep empty diagrams honest (structurally empty, never a guess).
    present_dims: list[int] = [dim for dim in (0, 1) if pairs.get(dim)]
    if not present_dims:
        features: dict[str, Any] = {"structural_only": True, "dimensions": {}}
    else:
        features = features_module.compute_features(pairs, dimensions=tuple(present_dims))
    features_digest = features_module.features_digest(features)

    payload: dict[str, Any] = {
        "entity_id": body.entity_id,
        "provider": "vr-z2-science+features",
        "structural_only": True,  # I-6
        "series_len": len(body.series),
        "diagrams": diagrams,
        "features": features,
        "features_digest": features_digest,
    }

    prev = body.prev_diagrams
    if prev:
        prev_pairs: dict[int, list[tuple[float, float | None]]] = {}
        for dim, bars in prev.items():
            prev_pairs[int(dim)] = [
                (float(p[0]), None if p[1] is None else float(p[1])) for p in bars
            ]
        drift: dict[str, dict[str, Any]] = {}
        for dim in sorted(prev_pairs):
            cur = pairs.get(dim, [])
            prev_d = prev_pairs[dim]
            if not cur and not prev_d:
                continue
            drift[str(dim)] = features_module.drift(prev_d, cur, metric=body.metric)
        payload["drift"] = drift
    return payload


@router.post("/phodms")
async def post_phodms(body: PhodmsRequest) -> dict[str, Any]:
    """Spatiotemporal persistent homology fragments (T056, PHoDMS).

    Bounded by scope: ``n_times <= 6`` and ``n_points <= 8`` else refused —
    the β₀ surface is O(n_times² · combinations) and we defer rather than cut.
    """
    from tda.phodms import betti_zero_surface, rank_invariant

    n_times = len(body.clouds)
    n_points = len(body.clouds[0]) if n_times else 0
    _scope_guard(2 <= n_times <= 6)
    _scope_guard(2 <= n_points <= 8)
    _scope_guard(2 <= len(body.thresholds) <= 16)
    _scope_guard(all(len(cloud) == n_points for cloud in body.clouds))

    surface = betti_zero_surface(body.clouds, body.thresholds)
    invariant = rank_invariant(
        clouds=body.clouds,
        thresholds=body.thresholds,
        dim=0,
        s1=0,
        t1=0,
        t2=min(1, n_times - 1),
        s2=1,
        t3=0,
        t4=min(1, n_times - 1),
    )
    return {
        "structural_only": True,
        "n_times": n_times,
        "n_points": n_points,
        "n_thresholds": len(body.thresholds),
        "betti_zero_surface": surface,
        "rank_invariant": invariant.as_dict(),
    }