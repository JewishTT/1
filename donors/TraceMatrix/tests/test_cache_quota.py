import pytest

GOOGLE = "https://customsearch.googleapis.com/customsearch/v1"

@pytest.mark.asyncio
async def test_quota_guard_raises_on_limit():
    import respx, httpx
    from orchestrator.app.services.quota import guarded_google_get, QuotaExceeded
    with respx.mock() as mock:
        mock.get(GOOGLE).respond(403, json={"error":{"errors":[{"reason":"dailyLimitExceeded"}]}})
        async with httpx.AsyncClient() as c:
            with pytest.raises(QuotaExceeded):
                await guarded_google_get(c, GOOGLE, {"q":"test"})
