import asyncio, json
import pytest
import orchestrator.app.services.maigret_service as ms

class DummyProc:
    def __init__(self, rc, out):
        self.returncode = rc
        self._out = out
    async def communicate(self):
        return self._out.encode(), b""
    def kill(self):
        pass


@pytest.mark.asyncio
async def test_maigret_ndjson(monkeypatch):
    sample = '\n'.join([
        json.dumps({"site": "GitHub", "url_user": "https://github.com/alice", "status": "FOUND"}),
        json.dumps({"site": "Twitter", "url_user": "", "status": "NOT_FOUND"}),
    ])

    async def fake_create(*a, **k):
        return DummyProc(0, sample)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    hits = await ms.maigret_lookup("alice")
    assert any("github" in h["url"].lower() for h in hits)
