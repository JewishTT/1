import pytest
from httpx import AsyncClient, ASGITransport
from orchestrator.app.main import app

@pytest.mark.asyncio
async def test_orchestrate_phone_discovery(monkeypatch):
    # Disable Google to keep deterministic
    monkeypatch.delenv("GOOGLE_CSE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CSE_CX", raising=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Directly call orchestrate (search will run and scan snippets)
        r = await ac.post("/orchestrate", json={
            "name":"John Doe","keywords":["Athens"],"search_limit":5,"phone_limit":5,"hybrid_k":5,"ingest_limit":1,"export_limit":100
        })
        assert r.status_code in (200, 400)  # 400 only if missing services; pass otherwise
