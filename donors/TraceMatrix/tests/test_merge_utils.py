from orchestrator.app.services.merge_utils import merge_username_hits

def test_merge_dedup():
    sa = [{"site": "GitHub", "url": "https://github.com/alice", "source": "social-analyzer"}]
    mg = [
        {"site": "GitHub", "url": "https://github.com/alice", "source": "maigret"},
        {"site": "Reddit", "url": "https://reddit.com/u/alice", "source": "maigret"},
    ]
    merged = merge_username_hits(sa, mg)
    assert len(merged) == 2
    assert any(h["source"] == "social-analyzer" for h in merged)
    assert any("reddit" in h["url"] for h in merged)

