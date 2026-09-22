"""Belief-landscape flow: gradient field, streamlines, attractors, forecast (T053).

Reduction of the Belief Landscape Framework (BLF, MIT) "trajectory analyzer /
predictor" to a deterministic, dependency-free operator: a belief scalar field
over a regular grid yields a gradient/flow field; streamlines descend the
potential toward attractors; attractor endpoints are clustered greedily
(replacing DBSCAN) into basins; a forecast extrapolates a point by following
the aggregate flow.

   Source repo : donors/BeliefLandscapeFramework/src/core/trajectory_analyzer.py
                 and src/analysis/trajectory_predictor.py
   License     : MIT
   What changed: DBSCAN/pandas/scipy ODE → greedy radius clustering + Euler
                 integration on a regular grid; no external dependencies.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np


def gradient_field(values: np.ndarray) -> np.ndarray:
    """Central-difference gradient (vx, vy) on a 2-D grid, zero at borders."""
    field = np.asarray(values, dtype=float)
    if field.ndim != 2:
        raise ValueError("gradient_field expects a 2-D grid")
    grad_y, grad_x = np.gradient(field)
    return np.stack([grad_x, grad_y], axis=-1)


@dataclass
class FlowField:
    """Normalized descent flow field (toward potential minima)."""
    values: np.ndarray
    gradient: np.ndarray
    flow: np.ndarray
    speed: np.ndarray

    @classmethod
    def from_values(cls, values: np.ndarray) -> FlowField:
        gradient = gradient_field(values)
        norms = np.linalg.norm(gradient, axis=-1, keepdims=True)
        flow = np.zeros_like(gradient)
        np.divide(
            -gradient,
            norms,
            out=flow,
            where=norms > 0,
        )
        return cls(values=values, gradient=gradient, flow=flow, speed=norms[..., 0])

    def flow_at(self, x: float, y: float) -> tuple[float, float]:
        """Bilinear lookup of the flow direction at continuous coordinates."""
        grid_y, grid_x = self.values.shape
        xi = min(max(x, 0.0), float(grid_x - 1 - 1e-9))
        yi = min(max(y, 0.0), float(grid_y - 1 - 1e-9))
        x0 = int(xi)
        y0 = int(yi)
        tx = xi - x0
        ty = yi - y0
        x1 = min(x0 + 1, grid_x - 1)
        y1 = min(y0 + 1, grid_y - 1)
        top = (1 - tx) * self.flow[y0, x0] + tx * self.flow[y0, x1]
        bottom = (1 - tx) * self.flow[y1, x0] + tx * self.flow[y1, x1]
        return tuple((1 - ty) * top + ty * bottom)

    def speed_at(self, x: float, y: float) -> float:
        grid_y, grid_x = self.values.shape
        xi = min(max(x, 0.0), float(grid_x - 1 - 1e-9))
        yi = min(max(y, 0.0), float(grid_y - 1 - 1e-9))
        return float(self.speed[int(yi), int(xi)])


def streamline(
    field: FlowField,
    start: tuple[float, float],
    *,
    max_steps: int = 400,
    step_size: float = 0.05,
    flow_threshold: float = 1e-6,
) -> list[tuple[float, float]]:
    """Integrate a descent path from ``start`` until flow vanishes."""
    x, y = start
    path = [(x, y)]
    for _ in range(max_steps):
        vx, vy = field.flow_at(x, y)
        speed = field.speed_at(x, y)
        if speed <= flow_threshold:
            break
        x += vx * step_size
        y += vy * step_size
        x = max(0.0, min(float(field.values.shape[1] - 1), x))
        y = max(0.0, min(float(field.values.shape[0] - 1), y))
        if (x, y) == path[-1]:
            break
        path.append((x, y))
    return path


@dataclass(frozen=True)
class Attractor:
    """A clustered basin endpoint of the belief landscape."""
    name: int
    center: tuple[float, float]
    basin_size: int
    radius: float


@dataclass
class BeliefLandscape:
    """Analysis result: flow field, streamlines, attractor basins."""
    values: np.ndarray
    field: FlowField
    streamlines: list[list[tuple[float, float]]]
    attractors: list[Attractor]

    def as_dict(self) -> dict[str, Any]:
        return {
            "grid": list(self.values.shape),
            "num_streamlines": len(self.streamlines),
            "attractors": [
                {
                    "name": attractor.name,
                    "center": attractor.center,
                    "basin_size": attractor.basin_size,
                    "radius": attractor.radius,
                }
                for attractor in self.attractors
            ],
            "mean_basin_size": (
                sum(attractor.basin_size for attractor in self.attractors) / len(self.attractors)
                if self.attractors
                else 0.0
            ),
        }


def _greedy_attractors(
    endpoints: list[tuple[float, float]],
    radius: float,
) -> list[Attractor]:
    if not endpoints:
        return []
    clusters: list[list[tuple[float, float]]] = []
    for point in endpoints:
        assigned = False
        for cluster in clusters:
            center = tuple(np.mean(cluster, axis=0))
            if (point[0] - center[0]) ** 2 + (point[1] - center[1]) ** 2 <= radius * radius:
                cluster.append(point)
                assigned = True
                break
        if not assigned:
            clusters.append([point])
    return [
        Attractor(
            name=index,
            center=tuple(map(float, np.mean(cluster, axis=0))),
            basin_size=len(cluster),
            radius=radius,
        )
        for index, cluster in enumerate(clusters)
    ]


def analyze_landscape(
    values: np.ndarray,
    seeds: Sequence[tuple[float, float]] | None = None,
    *,
    max_steps: int = 400,
    step_size: float = 0.05,
    flow_threshold: float = 1e-6,
    cluster_radius: float = 0.1,
) -> BeliefLandscape:
    """Full landscape analysis: flow, streamlines, attractor basins, forecast model.

    Seeds default to all grid midpoints (deterministic); streamlines run from
    each seed; endpoints are clustered into attractor basins.
    """
    field = FlowField.from_values(values)
    if seeds is None:
        grid_y, grid_x = values.shape
        seeds = [
            (col + 0.5, row + 0.5)
            for row in range(grid_y)
            for col in range(grid_x)
        ]
    streamlines = [
        streamline(field, seed, max_steps=max_steps, step_size=step_size, flow_threshold=flow_threshold)
        for seed in seeds
    ]
    endpoints = [path[-1] for path in streamlines if len(path) > 1]
    attractors = _greedy_attractors(endpoints, cluster_radius)
    return BeliefLandscape(
        values=np.asarray(values, dtype=float),
        field=field,
        streamlines=streamlines,
        attractors=attractors,
    )


@dataclass
class ForecastPath:
    """Baseline forecast: follow aggregate flow starting from a given point."""
    start: tuple[float, float]
    steps: int
    path: list[tuple[float, float]]
    destination: tuple[float, float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "destination": self.destination,
            "steps": self.steps,
            "path": self.path,
        }


def forecast(
    landscape: BeliefLandscape,
    start: tuple[float, float],
    *,
    steps: int = 60,
    step_size: float = 0.05,
) -> ForecastPath:
    """Extrapolate a belief position forward along the aggregate flow."""
    path = streamline(
        landscape.field,
        start,
        max_steps=steps,
        step_size=step_size,
        flow_threshold=0.0,
    )
    return ForecastPath(
        start=start,
        steps=len(path) - 1,
        path=path,
        destination=path[-1],
    )