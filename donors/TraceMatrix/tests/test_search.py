import pytest
import respx
import httpx
from httpx import AsyncClient, ASGITransport
from orchestrator.app.main import app

GOOGLE = "https://customsearch.googleapis.com/customsearch/v1"
SEARX = "http://localhost:8081/search"

@pytest.mark.asyncio
async def test_search_paginates_and_rrf(monkeypatch):
    monkeypatch.setenv("GOOGLE_CSE_API_KEY", "x")
    monkeypatch.setenv("GOOGLE_CSE_CX", "x")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with respx.mock(assert_all_called=False) as mock:
            mock.get(GOOGLE).mock(side_effect=[
                httpx.Response(200, json={"items":[{"title":"A","link":"https://a","snippet":""}]}),
                httpx.Response(200, json={"items":[{"title":"B","link":"https://b","snippet":""}]}),
            ])
            mock.get(SEARX).respond(200, json={"results":[{"title":"S1","url":"https://s1","content":""}]})
            r = await ac.post("/search", json={"name":"John","keywords":["architect"],"limit":5})
            j = r.json()
            assert r.status_code == 200
            assert j["count"] >= 2
            assert all("rrf" in x for x in j["results"])
