"""Gluing with triple coherence (spec 025 §10.1–§10.2, Appendix I.3, ADR-0031).

The single reason this module exists, in ADR-0031's words: "pairwise compatibility
of sections is not local-global compatibility on overlaps; the cocycle condition on
triple overlaps is a separate requirement."

Three cells can each agree with each other pairwise and still be jointly
inconsistent -- the classic example is three axes whose pairwise projections
correlate but whose triple does not. Pairwise-only gluing reports that as a clean
merge. So §10.2 step 6 restricts to the *triple* overlap and checks that the three
pairwise-compatible restrictions actually agree there.

Three rules are enforced as code rather than as documentation, because ADR-0031
marks the third as "a code-level guard, not a comment":

1. ``GLUED`` may never be returned while ``triples_unchecked > 0``. A gluing that
   skipped coherence checks has not established local-global consistency and must
   not claim it.
2. ``BLOCKED`` is not ``FALSE``. It means the current evidence is insufficient,
   and the obstructions say which check failed.
3. Truncation is recorded, never silent. Unchecked triples are counted and an
   obstruction carries the reason, per §8.3.

`GLUED` is expected to be rare. ADR-0031 says so: "PARTIALLY_GLUED will be the
common verdict, not GLUED. That is the correct outcome, not a defect."
"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from itertools import combinations
from typing import Any

from context.locality import (
    ContextCell,
    Obstruction,
    ObstructionKind,
    Scope,
    ScopeIntersection,
    ScopeKind,
    _digest,
    intersect_scopes,
)
from context.operators.compatibility import (
    CompatibilityAssessment,
    CompatibilityVerdict,
    assess_pair,
)


class GluingVerdict(enum.StrEnum):
    """§10.1."""

    GLUED = "glued"
    PARTIALLY_GLUED = "partially_glued"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class GluingProfile:
    """How strict this gluing attempt is allowed to be.

    ``allows_partial_gluing`` is what separates ``BLOCKED`` from
    ``PARTIALLY_GLUED``. A caller that cannot tolerate a partial merge sets it
    false and gets a refusal instead of a caveated result.
    """

    allows_partial_gluing: bool = True
    max_triples: int = 20_000
    max_bucket_size: int = 256
    method_fingerprint: str = "gluing.operator.v1"


@dataclass(frozen=True, slots=True)
class Overlap:
    """A non-empty overlap between two cells (§8.2)."""

    overlap_id: str
    cell_ids: tuple[str, ...]
    overlap_scope: Scope
    assessment: CompatibilityAssessment | None = None

    def __post_init__(self) -> None:
        if len(self.cell_ids) < 2:
            raise ValueError("an overlap joins at least two cells")
        if self.overlap_id and self.overlap_id != self.address():
            raise ValueError(
                f"declared overlap_id {self.overlap_id!r} but material addresses to {self.address()}"
            )
        if not self.overlap_id:
            object.__setattr__(self, "overlap_id", self.address())

    def _material(self) -> dict[str, Any]:
        return {
            "cell_ids": sorted(self.cell_ids),
            "scope_kind": self.overlap_scope.kind.value,
            "scope_members": sorted(self.overlap_scope.members),
        }

    def address(self) -> str:
        return f"OVL-{_digest(self._material())}"


@dataclass(frozen=True, slots=True)
class GluingResult:
    """§10.1, transcribed."""

    context_id: str
    input_cells: tuple[str, ...]
    verdict: GluingVerdict
    merged_scope: Scope
    merged_state_refs: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    obstructions: tuple[Obstruction, ...] = ()
    triples_checked: int = 0
    triples_unchecked: int = 0
    completeness: Mapping[str, Any] = field(default_factory=dict)
    method_fingerprint: str = ""
    gluing_id: str = ""

    def __post_init__(self) -> None:
        # ADR-0031 rule 3, enforced here so no caller can construct an
        # inconsistent result even by bypassing `glue`.
        if self.verdict is GluingVerdict.GLUED and self.triples_unchecked > 0:
            raise ValueError(
                "GLUED may never be returned while triples_unchecked > 0 "
                "(ADR-0031 rule 3, spec §10.2)"
            )
        if not self.gluing_id:
            object.__setattr__(self, "gluing_id", f"GLU-{_digest(self._material())}")

    def _material(self) -> dict[str, Any]:
        return {
            "context_id": self.context_id,
            "input_cells": sorted(self.input_cells),
            "verdict": self.verdict.value,
            "merged_scope_members": sorted(self.merged_scope.members),
            "triples_checked": self.triples_checked,
            "triples_unchecked": self.triples_unchecked,
            "conflicts": sorted(self.conflicts),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "gluing_id": self.gluing_id,
            "context_id": self.context_id,
            "input_cells": list(self.input_cells),
            "verdict": self.verdict.value,
            "merged_scope": {
                "kind": self.merged_scope.kind.value,
                "members": sorted(self.merged_scope.members),
                "unknown": self.merged_scope.unknown,
            },
            "merged_state_refs": list(self.merged_state_refs),
            "conflicts": list(self.conflicts),
            "obstructions": [item.as_dict() for item in self.obstructions],
            "triples_checked": self.triples_checked,
            "triples_unchecked": self.triples_unchecked,
            "completeness": dict(self.completeness),
            "method_fingerprint": self.method_fingerprint,
        }


def overlap_scope(left: ContextCell, right: ContextCell) -> Scope | None:
    """The shared scope of two cells, or ``None`` when they do not meet.

    An ``UNKNOWN`` intersection is still an overlap: §7.2 keeps undetermined scopes
    reachable, so a pair whose compatibility was never established stays in the
    gluing attempt and produces an obstruction rather than vanishing.
    """
    verdict = intersect_scopes(left.scope, right.scope)
    if verdict is ScopeIntersection.EMPTY:
        return None
    shared = left.scope.members & right.scope.members
    return Scope(
        kind=left.scope.kind,
        members=shared,
        unknown=bool(left.scope.unknown or right.scope.unknown),
    )


def discover_overlaps(
    cells: Sequence[ContextCell],
    *,
    max_bucket_size: int = 256,
) -> tuple[tuple[Overlap, ...], tuple[Obstruction, ...]]:
    """§8.3 / Appendix I.1: bounded blocking, no all-pairs comparison.

    Cells are bucketed by *shared scope members* only. That is the blocking key
    §8.3 lists as "scope intersection != EMPTY", applied as an index rather than a
    scan. A bucket over ``max_bucket_size`` produces a ``BUCKET_OVERFLOW``
    obstruction naming the key, and the bucket is skipped rather than silently
    truncated -- ADR-0031 rule 2.
    """
    index: dict[str, list[str]] = {}
    for cell in cells:
        for member in cell.scope.members:
            index.setdefault(member, []).append(cell.cell_id)

    obstructions: list[Obstruction] = []
    seen: dict[tuple[str, str], ContextCell] = {}
    for cell in cells:
        for member in cell.scope.members:
            bucket = sorted(set(index.get(member, ())))
            if len(bucket) > max_bucket_size:
                obstructions.append(
                    Obstruction(
                        kind=ObstructionKind.BUCKET_OVERFLOW,
                        detail=(
                            f"blocking key {member!r} holds {len(bucket)} cells, "
                            f"over max_bucket_size {max_bucket_size}; bucket skipped"
                        ),
                        subject_refs=tuple(bucket),
                    )
                )
                continue
            for other in bucket:
                if other == cell.cell_id:
                    continue
                # Canonical key: without sorting, (a, b) and (b, a) are different
                # keys and every pair is discovered twice, doubling both the
                # comparison work and the obstruction count.
                pair = (other, cell.cell_id) if other < cell.cell_id else (cell.cell_id, other)
                if pair in seen:
                    continue
                seen[pair] = cell

    by_id = {cell.cell_id: cell for cell in cells}
    overlaps: list[Overlap] = []
    for left_id, right_id in sorted(seen):
        left = by_id.get(left_id)
        right = by_id.get(right_id)
        if left is None or right is None:
            continue
        scope = overlap_scope(left, right)
        if scope is None:
            continue
        overlaps.append(
            Overlap(
                overlap_id="",
                cell_ids=tuple(sorted((left_id, right_id))),
                overlap_scope=scope,
            )
        )

    # The overlap id is content-addressed over the scope, so assessment needs a
    # second pass: `assess_pair` records which overlap it judged.
    by_id = {cell.cell_id: cell for cell in cells}
    assessed: list[Overlap] = []
    for overlap in overlaps:
        left = by_id[overlap.cell_ids[0]]
        right = by_id[overlap.cell_ids[1]]
        assessed.append(
            replace(
                overlap,
                assessment=assess_pair(left, right, overlap_id=overlap.overlap_id),
            )
        )
    return tuple(assessed), tuple(obstructions)


def enumerate_triangles(
    overlaps: Sequence[Overlap],
    *,
    max_triples: int,
) -> tuple[tuple[tuple[str, str, str], ...], int]:
    """Appendix I.3: triangles of the overlap graph, in stable id order, bounded.

    Returns the enumerated triples and the number left unchecked. Triples are
    drawn only from cells that pairwise overlap, so no phantom triangles are
    manufactured.
    """
    adjacency: dict[str, set[str]] = {}
    for overlap in overlaps:
        left, right = overlap.cell_ids[0], overlap.cell_ids[1]
        adjacency.setdefault(left, set()).add(right)
        adjacency.setdefault(right, set()).add(left)

    candidates: list[tuple[str, str, str]] = []
    for node in sorted(adjacency):
        neighbours = sorted(adjacency[node])
        for left, right in combinations(neighbours, 2):
            if right in adjacency.get(left, ()):  # triangle, not a wedge
                candidates.append(tuple(sorted((node, left, right))))  # type: ignore[arg-type]
    unique = sorted(set(candidates))
    return tuple(unique[:max_triples]), max(0, len(unique) - max_triples)


def coherent_on_triple(
    triple: tuple[str, str, str],
    overlaps: Mapping[tuple[str, str], Overlap],
    cells: Mapping[str, ContextCell],
) -> tuple[bool, str]:
    """The cocycle-style check of §10.2 step 6.

    Three pairwise-compatible cells must agree on the *triple* overlap. Agreement
    is tested on the shared entity and relation refs inside the triple's common
    scope: if two restrictions both claim to cover the same referent but disagree
    about it, the pairwise agreement was an artefact of restricting to different
    places.
    """
    left_id, middle_id, right_id = triple
    keys = (
        (left_id, middle_id),
        (left_id, right_id),
        (middle_id, right_id),
    )
    for key in keys:
        if key not in overlaps:
            return False, f"pair {key} is absent from the overlap graph"

    left, middle, right = cells[left_id], cells[middle_id], cells[right_id]

    # The triple overlap: what all three scopes actually share.
    common = left.scope.members & middle.scope.members & right.scope.members
    for name, cell in (("left", left), ("middle", middle), ("right", right)):
        if not cell.scope.members:
            return False, f"{name} cell has no determined scope"

    # Disagree about a referent all three share: pairwise agreement was local only.
    shared_entities = [cell.entity_refs for cell in (left, middle, right)]
    reference_sets = [frozenset(refs) for refs in shared_entities]
    if common:
        union = frozenset().union(*reference_sets)
        for referent in sorted(union & frozenset(common)):
            claims = [referent in refs for refs in reference_sets]
            if len(set(claims)) > 1 and any(claims):
                return (
                    False,
                    f"referent {referent} is claimed by some but not all of the triple",
                )

    shared_relations = [frozenset(cell.relation_refs) for cell in (left, middle, right)]
    if common:
        relation_union = frozenset().union(*shared_relations)
        for relation in sorted(relation_union & frozenset(common)):
            claims = [relation in refs for refs in shared_relations]
            if len(set(claims)) > 1 and any(claims):
                return (
                    False,
                    f"relation {relation} is claimed by some but not all of the triple",
                )
    return True, "triple restrictions agree on the triple overlap"


def glue(
    cells: Sequence[ContextCell],
    *,
    context_id: str,
    profile: GluingProfile | None = None,
    precomputed_overlaps: Sequence[Overlap] | None = None,
    extra_obstructions: Sequence[Obstruction] = (),
) -> GluingResult:
    """Appendix I.3, faithfully. Cells in, one verdict out."""
    settings = profile or GluingProfile()
    by_id = {cell.cell_id: cell for cell in cells}

    if precomputed_overlaps is not None:
        overlaps = tuple(precomputed_overlaps)
        blocking_obstructions: tuple[Obstruction, ...] = ()
    else:
        overlaps, blocking_obstructions = discover_overlaps(
            cells, max_bucket_size=settings.max_bucket_size
        )

    overlaps_by_pair = {overlap.cell_ids: overlap for overlap in overlaps}
    conflicts: list[str] = []
    obstructions: list[Obstruction] = list(blocking_obstructions) + list(extra_obstructions)

    compatible_cells: list[ContextCell] = []
    for overlap in overlaps:
        assessment = overlap.assessment
        left_id, right_id = overlap.cell_ids
        if assessment is None:
            continue
        if assessment.verdict is CompatibilityVerdict.INCOMPATIBLE:
            conflicts.append(f"{left_id}~{right_id}")
            obstructions.append(
                Obstruction(
                    kind=ObstructionKind.SOURCE_CONFLICT,
                    detail=(
                        f"pairwise incompatibility on "
                        f"{[d.value for d in assessment.blocking_dimensions]}"
                    ),
                    subject_refs=overlap.cell_ids,
                )
            )
        elif assessment.verdict is CompatibilityVerdict.UNRESOLVED:
            obstructions.append(
                Obstruction(
                    kind=ObstructionKind.MISSING_COVERAGE,
                    detail=(
                        f"undetermined dimensions "
                        f"{[d.value for d in assessment.missing_evidence]}"
                    ),
                    subject_refs=overlap.cell_ids,
                )
            )
            compatible_cells.extend(cell for cell in (by_id[left_id], by_id[right_id])
                                    if cell is not None)
        else:
            compatible_cells.extend(cell for cell in (by_id[left_id], by_id[right_id])
                                    if cell is not None)

    triples, unchecked = enumerate_triangles(overlaps, max_triples=settings.max_triples)
    checked = 0
    for triple in triples:
        coherent, reason = coherent_on_triple(triple, overlaps_by_pair, by_id)
        checked += 1
        if not coherent:
            conflicts.append("~".join(triple))
            obstructions.append(
                Obstruction(
                    kind=ObstructionKind.TRIPLE_INCONSISTENCY,
                    detail=reason,
                    subject_refs=tuple(triple),
                )
            )

    if unchecked:
        obstructions.append(
            Obstruction(
                kind=ObstructionKind.BUCKET_OVERFLOW,
                detail=(
                    f"{unchecked} triple(s) not checked under max_triples "
                    f"{settings.max_triples}; local-global coherence unproven"
                ),
                subject_refs=tuple(sorted({c for triple in triples for c in triple})),
            )
        )

    # ADR-0031 rule 3, at the decision site as well as in __post_init__.
    if conflicts and not settings.allows_partial_gluing:
        verdict = GluingVerdict.BLOCKED
    elif conflicts or obstructions or unchecked:
        verdict = GluingVerdict.PARTIALLY_GLUED
    else:
        verdict = GluingVerdict.GLUED

    merged_members = (
        frozenset().union(*(cell.scope.members for cell in compatible_cells))
        if compatible_cells
        else frozenset()
    )
    merged_unknown = any(cell.scope.unknown for cell in compatible_cells)
    merged_scope = Scope(
        kind=compatible_cells[0].scope.kind if compatible_cells else ScopeKind.ENTITY,
        members=merged_members,
        unknown=merged_unknown,
    )

    return GluingResult(
        context_id=context_id,
        input_cells=tuple(sorted(cell.cell_id for cell in cells)),
        verdict=verdict,
        merged_scope=merged_scope,
        merged_state_refs=tuple(
            sorted({ref for cell in compatible_cells for ref in cell.state_refs})
        ),
        conflicts=tuple(sorted(set(conflicts))),
        obstructions=tuple(obstructions),
        triples_checked=checked,
        triples_unchecked=unchecked,
        completeness={"compatibility_mode": "partial" if settings.allows_partial_gluing else "strict"},
        method_fingerprint=settings.method_fingerprint,
    )
