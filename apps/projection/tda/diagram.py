"""Persistence diagram model + deterministic content addressing (FR-008/010).

A persistence diagram is the *signature* of an atomic entity's topology
across scales (L3). To satisfy Invariant I-12 (rebuildable, no hidden state)
and the "honest, rebuilt, content-addressed" rule, every diagram is reduced
to a lossless, deterministic serialization -> ``diagram_hash``. Two runs over
the same input MUST produce byte-identical diagrams; the hash then identifies
the analysis output itself (drift is measured *between* hashes).
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

_PERSISTENCE_EPS = 1e-9


def persistence(birth: float, death: float | None) -> float:
    """Scaled duration of a homological class; None-death => +inf."""
    if death is None:
        return float("inf")
    return float(death) - float(birth)


def simplify(
    pairs: Sequence[tuple[float, float | None]],
    *,
    epsilon: float = _PERSISTENCE_EPS,
) -> list[tuple[float, float | None]]:
    """Drop classes whose survival is below ``epsilon`` (deterministic)."""
    return [(b, d) for b, d in pairs if persistence(b, d) >= epsilon]


class PersistenceDiagram:
    """One topology signature: {dimension: [(birth, death), ...]}."""

    def __init__(self, raw: dict[int, Sequence[tuple[float, float | None]]]) -> None:
        self._diagrams: dict[int, list[tuple[float, float | None]]] = {
            int(d): simplify(list(pairs), epsilon=0.0)
            for d, pairs in raw.items()
            if pairs
        }

    # -- deterministic serialization --------------------------------------

    def to_canonical(self) -> str:
        """Byte-reproducible JSON (no NaN, floats rounded to 1e-9)."""
        sections: list[str] = []
        for dim in sorted(self._diagrams):
            points = []
            for birth, death in self._diagrams[dim]:
                d_str = "inf" if death is None else f"{death:.9f}"
                points.append(f"[{birth:.9f},{d_str}]")
            sections.append(f'"{dim}":[{",".join(points)}]')
        return "{" + ",".join(sections) + "}"

    @property
    def diagram_hash(self) -> str:
        material = self.to_canonical().encode("utf-8")
        return hashlib.sha256(material).hexdigest()

    def dims(self) -> list[int]:
        return sorted(self._diagrams)

    def points(self, dim: int) -> list[tuple[float, float | None]]:
        return self._diagrams.get(dim, [])

    def __getitem__(self, dim: int) -> list[tuple[float, float | None]]:
        return self.points(dim)

    def __len__(self) -> int:
        return sum(len(v) for v in self._diagrams.values())

    def __repr__(self) -> str:
        return f"PersistenceDiagram(hash={self.diagram_hash[:12]}…)"

    # -- structural claim -------------------------------------------------

    def structural_claim(self, entity_id: str) -> dict:
        """Compact, content-addressed claim blueprint (never an identity, FR-013)."""
        return {
            "entity_id": entity_id,
            "diagram_hash": self.diagram_hash,
            "dimensions": [int(d) for d in self.dims()],
            "classes_by_dim": {int(d): len(self._diagrams[d]) for d in self.dims()},
            "structural_only": True,  # I-6: never an identity claim
        }


__all__ = ["PersistenceDiagram", "persistence", "simplify"]