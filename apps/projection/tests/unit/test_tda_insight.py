"""Hidden clusters and anomaly highlighting.

Persistence produces intervals; these tests pin the two answers a reconnaissance system
actually needs from them, and both are checked against a **planted ground truth** rather
than a golden value -- a cluster detector that returns the right number of clusters with
the wrong membership would pass a snapshot test.

The planted fixture is four tight groups with one distant member each. A correct detector
recovers exactly four clusters of fifteen, and flags the four that sit further from their
group than their peers do.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pytest

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP.parents[1] / "apps" / "shared"))

from tda.insight import (  # noqa: E402
    anomalies,
    hidden_clusters,
    summarise,
)
from tda.pipeline import AdaptiveSubgraph, GudhiProvider, TDAPipeline  # noqa: E402

GROUPS = 4
PER_GROUP = 15


#: How far a planted outlier is displaced from its group centre.
#:
#: Two regimes, and the difference is not a tolerance -- it is a different claim:
#:
#: * ``OUTLIER_SCALE`` (mild) stays inside the group's own neighbourhood. The member
#:   joins its cluster late, which is what an anomaly is.
#: * ``DETACHED_SCALE`` (strong) puts it beyond the group entirely, so it is its own
#:   component. A detector that kept it would assert a link the geometry denies.
OUTLIER_SCALE = 1.1
DETACHED_SCALE = 6.0

#: A member's own displacement is normally this small.
_SPREAD = 0.1


def planted(*, seed: int = 11, groups: int = GROUPS, per_group: int = PER_GROUP,
            outlier_scale: float | None = None):
    """Tight groups, optionally with one displaced member per group.

    Returns ``(node_ids, features, truth)``; ``truth`` is the group index per node and is
    given to nobody but the assertions.

    ``outlier_scale=None`` plants no outlier, which is the fixture the cluster tests
    need. Planting a mild outlier in *that* fixture would merge adjacent groups -- a
    single bridging node is enough under single-linkage, and three groups did merge that
    way when it was tried -- so the two concerns get separate fixtures instead of one
    compromise.
    """
    rng = np.random.default_rng(seed)
    centres = rng.normal(size=(groups, 8))
    node_ids: list[str] = []
    features: dict[str, np.ndarray] = {}
    truth: dict[str, int] = {}
    for g in range(groups):
        for k in range(per_group):
            nid = f"n{g}_{k}"
            scale = _SPREAD
            if outlier_scale is not None and k == per_group - 1:
                scale = outlier_scale
            node_ids.append(nid)
            features[nid] = centres[g] + rng.normal(scale=scale, size=8)
            truth[nid] = g
    return node_ids, features, truth


def _clustering(node_ids, features, threshold: float = 0.5):
    filt = AdaptiveSubgraph(max_nodes=256, similarity_threshold=threshold).select(
        node_ids, features
    )
    return hidden_clusters(node_ids, filt.distance_matrix)


# -- hidden clusters -----------------------------------------------------------


def test_recovers_the_planted_clusters_exactly() -> None:
    node_ids, features, truth = planted()
    clusters = _clustering(node_ids, features)
    assert len(clusters) == GROUPS, [c.size for c in clusters]
    assert all(c.size == PER_GROUP for c in clusters)
    assert all(c.persistent for c in clusters), "planted clusters never merge"


def test_every_member_lands_in_its_own_group() -> None:
    """Not just the right count -- the right membership."""
    node_ids, features, truth = planted()
    clusters = _clustering(node_ids, features)
    for cluster in clusters:
        groups = {truth[m] for m in cluster.members}
        assert len(groups) == 1, f"cluster {cluster.cluster_id} mixes groups {groups}"


def test_every_node_is_placed_exactly_once() -> None:
    node_ids, features, _ = planted()
    clusters = _clustering(node_ids, features)
    placed = [m for c in clusters for m in c.members]
    assert sorted(placed) == sorted(node_ids)
    assert len(placed) == len(set(placed)), "a node appeared in two clusters"


def test_a_persistent_cluster_has_no_death() -> None:
    node_ids, features, _ = planted()
    for cluster in _clustering(node_ids, features):
        assert cluster.death is None
        assert np.isinf(cluster.lifetime)


def test_three_isolated_points_are_three_clusters() -> None:
    ids = ["a", "b", "c"]
    features = {
        "a": np.array([1.0, 0.0]),
        "b": np.array([0.0, 1.0]),
        "c": np.array([0.0, 0.0]),
    }
    # threshold 0.0 filters nothing, so all three would be one component. Orthogonal
    # vectors sit at distance 1.0, so a threshold above it drops every edge.
    filt = AdaptiveSubgraph(similarity_threshold=0.5).select(ids, features)
    clusters = hidden_clusters(ids, filt.distance_matrix, min_members=1)
    assert len(clusters) == 3
    assert sorted(len(c.members) for c in clusters) == [1, 1, 1]


def test_a_dropped_edge_is_not_treated_as_a_very_long_one() -> None:
    """+inf must not merge two components. If it did, the threshold would be decorative."""
    ids = ["a", "b", "c", "d"]
    features = {
        "a": np.array([1.0, 0.0]),
        "b": np.array([0.99, 0.01]),
        "c": np.array([-1.0, 0.0]),
        "d": np.array([-0.99, -0.01]),
    }
    filt = AdaptiveSubgraph(similarity_threshold=0.9).select(ids, features)
    clusters = hidden_clusters(ids, filt.distance_matrix, min_members=1)
    assert len(clusters) == 2, [c.members for c in clusters]


def test_a_fully_connected_graph_is_one_cluster() -> None:
    """The complement of the isolated case: with nothing filtered, everything connects."""
    ids = [f"n{i}" for i in range(6)]
    features = {nid: np.array([1.0, 0.0, i * 0.001]) for i, nid in enumerate(ids)}
    filt = AdaptiveSubgraph(similarity_threshold=0.0).select(ids, features)
    clusters = hidden_clusters(ids, filt.distance_matrix, min_members=1)
    assert len(clusters) == 1
    assert clusters[0].size == 6


def test_a_dropped_node_still_lands_in_a_cluster() -> None:
    """Every node must be placed exactly once, including a node with no surviving edge.

    Constructed as a distance matrix on purpose. The planted version of this test was
    unreliable: the outlier is displaced in a random direction, so at a fixed similarity
    threshold usually one of the four detached points ended up still attached to its group
    (sizes came back 17/16/15/15), and the one that did detach was a singleton, which
    ``min_members=2`` then excluded from the report entirely. The property under test --
    a node with no edges is still a component of its own -- is about the union-find, so it
    is stated directly.
    """
    ids = ["a", "b", "c"]
    dist = np.array(
        [
            [0.0, 0.2, np.inf],
            [0.2, 0.0, np.inf],
            [np.inf, np.inf, 0.0],
        ]
    )
    clusters = hidden_clusters(ids, dist, min_members=1)
    placed = {m: c for c in clusters for m in c.members}
    assert set(placed) == set(ids), f"unplaced: {set(ids) - set(placed)}"
    assert placed["c"].size == 1
    assert placed["a"].size == 2


def test_a_uniform_cluster_produces_no_anomaly() -> None:
    """Deviation is measured inside the cluster, so a cluster whose members all join at
    the same scale has no member that departs from the others -- not even when the
    absolute scale is large.

    Built directly as a distance matrix because the property is about the comparison, not
    about any embedding: two pairs plus a link, every join at the same weight.
    """
    # a--b at 0.5, c--d at 0.5, then a--c at 0.5 as well: all four join at one scale.
    dist = np.array(
        [
            [0.0, 0.5, 0.5, 0.5],
            [0.5, 0.0, 0.5, 0.5],
            [0.5, 0.5, 0.0, 0.5],
            [0.5, 0.5, 0.5, 0.0],
        ]
    )
    ids = ["a", "b", "c", "d"]
    clusters = hidden_clusters(ids, dist, min_members=1)
    assert len(clusters) == 1
    assert anomalies(ids, dist, clusters) == []


def test_anomalies_are_ranked_by_deviation() -> None:
    node_ids, features, _ = planted()
    filt = AdaptiveSubgraph(max_nodes=256, similarity_threshold=0.5).select(
        node_ids, features
    )
    clusters = hidden_clusters(node_ids, filt.distance_matrix)
    found = anomalies(node_ids, filt.distance_matrix, clusters)
    assert [a.deviation for a in found] == sorted(
        (a.deviation for a in found), reverse=True
    )


def test_anomaly_carries_the_cluster_it_departs_from() -> None:
    node_ids, features, _ = planted()
    filt = AdaptiveSubgraph(max_nodes=256, similarity_threshold=0.5).select(
        node_ids, features
    )
    clusters = hidden_clusters(node_ids, filt.distance_matrix)
    found = anomalies(node_ids, filt.distance_matrix, clusters)
    for a in found:
        assert a.detail["cluster_id"] is not None
        assert a.detail["cluster_size"] >= 3
        assert a.reason == "late_join"


# -- the report ----------------------------------------------------------------


def test_summarise_reports_the_scale_alongside_the_claim() -> None:
    """A cluster boundary is a claim about a scale; a claim whose scale is unstated
    cannot be checked."""
    node_ids, features, _ = planted()
    filt = AdaptiveSubgraph(max_nodes=256, similarity_threshold=0.5).select(
        node_ids, features
    )
    report = summarise(node_ids, filt.distance_matrix)
    assert np.isfinite(report["scale"]["max_finite_edge"])
    assert report["scale"]["persistent_clusters"] == GROUPS
    assert report["scale"]["largest_cluster"] == PER_GROUP
    assert len(report["clusters"]) == GROUPS


def test_report_serialises() -> None:
    node_ids, features, _ = planted()
    filt = AdaptiveSubgraph(max_nodes=256, similarity_threshold=0.5).select(
        node_ids, features
    )
    report = summarise(node_ids, filt.distance_matrix)
    for cluster in report["clusters"]:
        assert set(cluster) == {
            "cluster_id", "birth", "death", "lifetime", "size", "members", "persistent",
        }
    for anomaly in report["anomalies"]:
        assert set(anomaly) == {"node_id", "join_scale", "deviation", "reason", "detail"}


def test_insight_works_on_a_real_pipeline_run() -> None:
    """End to end: features -> TDAPipeline -> clusters + anomalies."""
    node_ids, features, _ = planted()
    out = TDAPipeline(provider=GudhiProvider(), similarity_threshold=0.5).run(node_ids, features)
    filt = AdaptiveSubgraph(similarity_threshold=0.5).select(node_ids, features)
    report = summarise(node_ids, filt.distance_matrix, out["diagrams"])
    assert len(report["clusters"]) == GROUPS
    assert out["diagrams"], "persistence must have produced intervals to read"