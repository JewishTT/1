"""Network metrics package: degree measures, community detection, hypergraphs,
temporal paths (T058/T059/T060). Pure-stdlib adaptions of permissive donors.
"""

from .community import label_propagation, modularity, normalized_mutual_information
from .hypergraph_metrics import Hyperedge, Hypergraph, hypergraph_from_observations
from .network_measures import NetworkMeasures, network_measures
from .temporal_paths import TemporalGraph, TimedEdge

__all__ = [
    "Hyperedge",
    "Hypergraph",
    "NetworkMeasures",
    "TemporalGraph",
    "TimedEdge",
    "hypergraph_from_observations",
    "label_propagation",
    "modularity",
    "network_measures",
    "normalized_mutual_information",
]