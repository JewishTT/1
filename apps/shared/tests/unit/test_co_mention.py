"""T4-01: co-mention hyperedge facade (FR-011) + TDA wiring smoke."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest

from domain.co_mention import CoMentionFanBuilder, CoMentionHyperedgeWriter, FanMention
from domain.hypergraph import HyperGraph

pytestmark = pytest.mark.unit

T = datetime(2024, 1, 1, 12, 0, 0)


def _mention(entity_id: str, page: str, n: int = 1) -> FanMention:
    return FanMention(entity_id=entity_id, page_url=page, observed_at=T, mention_count=n)


def test_fans_group_co_occurrence() -> None:
    mentions = [
        _mention("e1", "https://news.example/a"),
        _mention("e2", "https://news.example/a"),
        _mention("e3", "https://news.example/b"),
        _mention("e2", "https://news.example/b"),
    ]
    fans = CoMentionFanBuilder().fans(mentions)
    assert ("e1", "e2") in fans
    assert ("e2", "e3") in fans
    # single-mention page cannot form a fan
    mentions2 = [_mention("e1", "https://x.example/sole")]
    assert CoMentionFanBuilder().fans(mentions2) == {}


def test_validated_cut_filters_noise() -> None:
    mentions = []
    for i in range(40):
        mentions.append(_mention(f"e{i % 2}", "https://coin.example/1"))
    mentions.append(_mention("noise-1", "https://noise.example/1"))
    mentions.append(_mention("noise-2", "https://noise.example/1"))
    raw = CoMentionFanBuilder().fans(mentions)
    assert len(raw) >= 1
    validated = CoMentionFanBuilder().validated(mentions, n_trials=100, null_p=0.1)
    member_sets = [tuple(m) for m in validated.to_list()] if hasattr(validated, "to_list") else validated
    # the noisy single co-mention of unrelated names is culled
    assert ("noise-1", "noise-2") not in member_sets


def test_ingest_writes_hyperedges_with_provenance() -> None:
    graph = HyperGraph(provenance_required=True)
    writer = CoMentionHyperedgeWriter(graph, tenant_id="t1")
    mentions = [
        _mention("e1", "https://news.example/a"),
        _mention("e2", "https://news.example/a"),
        _mention("e1", "https://news.example/b"),
        _mention("e3", "https://news.example/b"),
    ]
    edges = writer.ingest(mentions, edge_type="co_mention")
    assert edges
    assert len(graph) >= 1
    first = edges[0]
    assert first.provenance.get("event_id")
    assert first.tenant_id == "t1"
    assert first.weight >= 1.0


def test_ingest_idempotent_duplicate() -> None:
    graph = HyperGraph(provenance_required=True)
    writer = CoMentionHyperedgeWriter(graph, tenant_id="t1")
    mentions = [_mention("e1", "https://n.example/a"), _mention("e2", "https://n.example/a")]
    writer.ingest(mentions, edge_type="co_mention")
    before = len(graph)
    writer.ingest(mentions, edge_type="co_mention")
    assert len(graph) == before  # I-11 idempotency