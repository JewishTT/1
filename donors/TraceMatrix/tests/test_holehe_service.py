import asyncio, json
import pytest
import orchestrator.app.services.holehe_service as hs

class DummyProc:
    def __init__(self, rc, out):
        self.returncode = rc
        self._out = out
    async def communicate(self):
        return self._out.encode(), b""
    def kill(self):
        pass


@pytest.mark.asyncio
async def test_holehe_parses_and_filters(monkeypatch):
    sample = '\n'.join([
        json.dumps({"name": "twitter", "exists": True, "rateLimit": False, "emailrecovery": "ex****@g.com"}),
        json.dumps({"name": "instagram", "exists": False, "rateLimit": False}),
    ])

    async def fake_create(*a, **k):
        return DummyProc(0, sample)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    calls = []

    async def fake_index(email, hits):
        calls.append((email, hits))

    monkeypatch.setattr(hs, "index_email_accounts", fake_index)

    res = await hs.holehe_lookup_and_index("someone@example.com")
    assert len(res) == 1 and res[0]["name"] == "twitter"
    assert calls and calls[0][0] == "someone@example.com"
