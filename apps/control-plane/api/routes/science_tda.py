"""Topological invariant API (011, FR-008/FR-009; the "TDA in the corner").

Base path ``/api/science/invariant``: a series plus Takens delay-embedding ->
VR persistence (pure-python Z2 reduction, no gudhi required) -> per-dimension
barcodes, stats and a content-addressed digest. Results are STRUCTURAL ONLY
(I-6: never an identity claim) and rebuildable (I-12). ``prev_diagram`` lets a
caller clamp two windows against each other and get a drift signal for the UI.
"""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from tda.persistence import from_distance_matrix
from tda.series import embedding_distance_matrix, takens_embed

router = APIRouter(prefix="/api/science/invariant", tags=["science"])

INF = float("inf")
_DIGEST_EPS_ROUND = 6


class InvariantRequest(BaseModel):
    entity_id: str
    series: list[float]
    lag: int = Field(default=1, ge=1)
    embed_dim: int = Field(default=2, ge=2)
    max_dim: int = Field(default=1, ge=0, le=2)
    budget: int = Field(default=8192, ge=1, le=65536)
    prev_diagram: dict[int, list[list[float | None]]] | None = None


def _normalize_diagrams(diagrams: dict[int, list[list[float | None]]]) -> dict[int, list[list[float | None]]]:
    out: dict[int, list[list[float | None]]] = {}
    for dim, bars in diagrams.items():
        out[int(dim)] = []
        for point in bars:
            birth = float(point[0])
            death_raw = point[1]
            death: float | None
            if death_raw is None or death_raw == "inf":
                death = None
            else:
                death = float(death_raw)
            out[int(dim)].append([birth, death])
    return {dim: bars for dim, bars in out.items() if bars}


def _canonical(diagrams: dict[int, list[list[float | None]]]) -> str:
    parts: list[str] = []
    for dim in sorted(int(k) for k in diagrams):
        points = ",".join(
            f"[{b:.{_DIGEST_EPS_ROUND}f},{'inf' if d is None else f'{d:.{_DIGEST_EPS_ROUND}f}'}]"
            for b, d in diagrams[dim]
        )
        parts.append(f'"{dim}":[{points}]')
    return "{" + ",".join(parts) + "}"


def _digest(diagrams: dict[int, list[list[float | None]]]) -> str:
    return hashlib.sha256(_canonical(diagrams).encode("utf-8")).hexdigest()


def _max_persistence(diagrams: dict[int, list[list[float | None]]], dim: int) -> float:
    return max(
        (death - birth for birth, death in diagrams.get(dim, []) if death is not None),
        default=0.0,
    )


def _stats(diagrams: dict[int, list[list[float | None]]]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for dim, bars in diagrams.items():
        persists = [death - birth for birth, death in bars if death is not None]
        out[str(dim)] = {
            "num_bars": float(len(bars)),
            "mean_persistence": (sum(persists) / len(persists)) if persists else 0.0,
            "max_persistence": max(persists, default=0.0),
            "total_persistence": sum(persists),
        }
    return out


@router.post("")
async def post_invariant(body: InvariantRequest) -> dict[str, Any]:
    """Series + Takens embedding -> VR persistence barcode + digest/drift."""
    embedded = takens_embed(body.series, lag=body.lag, dim=body.embed_dim)
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

    diagrams: dict[int, list[tuple[float, float]]] = {}
    for barcode in barcodes.barcodes:
        if barcode.bars:
            diagrams[int(barcode.dimension)] = barcode.bars
    payload_diagrams: dict[int, list[list[float | None]]] = {
        int(dim): [
            [float(birth), None if (death is None or death == INF) else float(death)]
            for birth, death in bars
        ]
        for dim, bars in diagrams.items()
    }

    sampled = embedded[:512] if len(embedded) <= 512 else embedded[:: len(embedded) // 512]

    answer: dict[str, Any] = {
        "entity_id": body.entity_id,
        "provider": "vr-z2-science",
        "structural_only": True,  # I-6
        "series_len": len(body.series),
        "embedding": {"lag": body.lag, "embed_dim": body.embed_dim, "points": sampled},
        "diagrams": payload_diagrams,
        "stats": _stats(payload_diagrams),
        "digest": _digest(payload_diagrams),
    }

    prev = _normalize_diagrams(body.prev_diagram) if body.prev_diagram is not None else None
    if prev is not None:
        changed = _digest(prev) != _digest(payload_diagrams)
        dim0_prev = _max_persistence(prev, 0)
        dim0_cur = _max_persistence(payload_diagrams, 0)
        answer["drift"] = {
            "metric": "diagram_sha256",
            "changed": changed,
            "delta_max_persistence": round(abs(dim0_cur - dim0_prev), _DIGEST_EPS_ROUND),
        }
    return answer