"""Science structure API (T124, US5; contracts/science-api.md).

Base path ``/api/science/structure``. Analysis is scoped, complexity-bounded
and DEFERRED (never a truncated guess) when the budget is exceeded. Result
payloads are structural only and carry a permutation-null significance block.
"""

from __future__ import annotations

from typing import Any

from errors import ScopeBoundaryError
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from structure.graph import AnalysisBudget, Graph, NullParams, analyze
from structure.model import StructureKind

router = APIRouter(prefix="/api/science/structure", tags=["science"])

_results: dict[str, dict[str, Any]] = {}


class EdgeInput(BaseModel):
    source: str
    target: str


class AnalyzeRequest(BaseModel):
    graph_ref: str
    edges: list[EdgeInput]
    kind: StructureKind = StructureKind.SPECTRAL
    max_ops: int = 200_000
    max_permutations: int = 200
    n_permutations: int = 200
    seed: int = 42


@router.post("/analyze")
async def post_analyze(body: AnalyzeRequest) -> dict[str, Any]:
    graph = Graph(graph_ref=body.graph_ref)
    for edge in body.edges:
        try:
            graph.add_edge(edge.source, edge.target)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        result = analyze(
            graph,
            budget=AnalysisBudget(
                max_ops=body.max_ops,
                max_permutations=body.max_permutations,
            ),
            kind=body.kind,
            null_params=NullParams(
                n_permutations=body.n_permutations,
                seed=body.seed,
            ),
        )
    except ScopeBoundaryError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "scope_refused", "policy": "contracts/scope-boundary.md"},
        ) from exc
    payload = result.as_dict()
    _results[payload["result_id"]] = payload
    return payload


@router.get("/results/{result_id}")
async def get_result(result_id: str) -> dict[str, Any]:
    result = _results.get(result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="result not found")
    return result