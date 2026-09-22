"""
Test to verify that the fallback orchestration no longer returns empty results.
This test addresses the issue where /orchestrate with fallback=true returns:
  "mode": "fallback_websearch_empty",
  "message": "Web search returned 0 URLs; empty index → cannot hybrid"

The test ensures:
1. Web search returns valid URLs
2. Ingest processes those URLs successfully
3. Hybrid search returns results
4. Export generates CSV/JSON with data
"""
import os
import time
import json
import requests
import pytest

ORCH_URL = os.getenv("ORCH_URL", "http://localhost:8000")


def wait_ready(url: str, tries: int = 60, delay: int = 2) -> bool:
    """Wait for orchestrator to be ready."""
    for _ in range(tries):
        try:
            r = requests.get(f"{url}/docs", timeout=2)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(delay)
    return False


def wait_for_searxng(tries: int = 30, delay: int = 2) -> bool:
    """Wait for SearXNG to be ready."""
    searxng_url = os.getenv("SEARXNG_URL", "http://localhost:8081")
    for _ in range(tries):
        try:
            r = requests.get(f"{searxng_url}/search", params={"q": "test", "format": "json"}, timeout=2)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(delay)
    return False


@pytest.fixture(scope="module")
def orchestrator_ready():
    """Ensure orchestrator and dependencies are ready."""
    assert wait_ready(ORCH_URL), "Orchestrator did not become ready"
    # Give SearXNG time to initialize
    wait_for_searxng()
    yield


def test_orchestrate_fallback_returns_results(orchestrator_ready):
    """
    Test that orchestrate with fallback=true returns actual results, not empty.

    This test verifies the fix for the issue where the endpoint returned:
    {
      "status": "ok",
      "mode": "fallback_websearch_empty",
      "message": "Web search returned 0 URLs; empty index → cannot hybrid",
      "exports": {},
      "results_preview": [],
      "summary": {"results": 0},
      "export": {"csv_rows": 0, "paths": {}}
    }
    """
    payload = {
        "name": "Panagiotis Drakatos",
        "keywords": ["athens", "software engineer", "keyword-only orchestration"],
        "search_limit": 15,
        "social_limit": 10,
        "email_limit": 20,
        "phone_limit": 5,
        "hybrid_k": 20,
        "ingest_limit": 60,
        "export_limit": 2000,
        "fallback": True
    }

    # Make the request with a generous timeout since fallback does multiple operations
    resp = requests.post(f"{ORCH_URL}/orchestrate", json=payload, timeout=300)

    # Assert successful response
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    data = resp.json()
    print(f"\n=== Orchestrate Response ===")
    print(json.dumps(data, indent=2))

    # Basic structure checks
    assert "status" in data, "Response missing 'status' field"
    assert data["status"] == "ok", f"Expected status='ok', got '{data.get('status')}'"
    assert "mode" in data, "Response missing 'mode' field"
    assert "summary" in data, "Response missing 'summary' field"
    assert "export" in data, "Response missing 'export' field"

    # The key assertion: mode should NOT be "fallback_websearch_empty"
    assert data["mode"] != "fallback_websearch_empty", (
        f"Fallback web search returned empty results. "
        f"Message: {data.get('message')}. "
        f"This indicates the /search endpoint is not working correctly."
    )

    # If web search succeeded, we should have fallback_hybrid mode
    if data["mode"] == "fallback_hybrid":
        # Should have results
        assert "results_preview" in data, "Response missing 'results_preview' field"

        # Export should have generated files
        export_info = data.get("export", {})
        assert "csv_rows" in export_info, "Export info missing 'csv_rows'"
        assert export_info["csv_rows"] > 0, (
            f"Expected csv_rows > 0, got {export_info['csv_rows']}. "
            f"Fallback completed but no results were exported."
        )

        # Summary should show results
        summary = data.get("summary", {})
        assert "results" in summary, "Summary missing 'results' count"
        assert summary["results"] > 0, (
            f"Expected results > 0, got {summary['results']}"
        )

        # Should have export paths
        assert "paths" in export_info or "csv" in data.get("exports", {}), (
            "No export paths found in response"
        )

        print(f"\n✓ Fallback orchestration succeeded with {summary['results']} results")
        print(f"✓ Exported {export_info['csv_rows']} CSV rows")
    else:
        # If it's not fallback_hybrid, fail with detailed message
        pytest.fail(
            f"Unexpected mode: '{data['mode']}'. "
            f"Expected 'fallback_hybrid' or acceptable alternative. "
            f"Message: {data.get('message')}"
        )


def test_search_endpoint_returns_results(orchestrator_ready):
    """
    Test that the /search endpoint (used by fallback) returns results.
    This is a diagnostic test to help identify if the issue is in /search.
    """
    payload = {
        "name": "Panagiotis Drakatos",
        "keywords": ["athens", "software engineer"],
        "limit": 15
    }

    resp = requests.post(f"{ORCH_URL}/search", json=payload, timeout=30)

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    data = resp.json()
    print(f"\n=== Search Response ===")
    print(json.dumps(data, indent=2))

    assert "results" in data, "Response missing 'results' field"
    assert "count" in data, "Response missing 'count' field"

    results = data.get("results", [])

    # This is the root cause check - if this fails, /search is not configured properly
    assert len(results) > 0, (
        f"Search endpoint returned 0 results. "
        f"This is why fallback orchestration fails. "
        f"Check that:\n"
        f"  1. SearXNG is running and accessible at {os.getenv('SEARXNG_URL', 'http://localhost:8081')}\n"
        f"  2. Google CSE credentials are set (GOOGLE_CSE_API_KEY, GOOGLE_CSE_CX)\n"
        f"  3. Search engines are returning data"
    )

    # Verify result structure
    for result in results[:3]:
        assert "url" in result, "Search result missing 'url' field"
        assert result["url"], "Search result has empty URL"
        assert "title" in result, "Search result missing 'title' field"

    print(f"\n✓ Search endpoint returned {len(results)} results")


def test_ingest_endpoint_works(orchestrator_ready):
    """
    Test that the /ingest_urls endpoint works correctly.
    This is used by fallback after web search.
    """
    test_urls = [
        "https://www.example.com",
        "https://www.wikipedia.org"
    ]

    payload = {
        "urls": test_urls,
        "text": "Test ingestion for Panagiotis Drakatos"
    }

    resp = requests.post(f"{ORCH_URL}/ingest_urls", json=payload, timeout=60)

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    data = resp.json()
    print(f"\n=== Ingest Response ===")
    print(json.dumps(data, indent=2))

    assert "count" in data, "Response missing 'count' field"
    assert data["count"] == len(test_urls), f"Expected count={len(test_urls)}, got {data['count']}"

    print(f"\n✓ Ingest endpoint processed {data['count']} URLs")


def test_hybrid_search_endpoint_works(orchestrator_ready):
    """
    Test that the /search_hybrid endpoint works.
    This is used by fallback after ingestion.
    """
    payload = {
        "query": "Panagiotis Drakatos software engineer",
        "k": 20
    }

    resp = requests.post(f"{ORCH_URL}/search_hybrid", json=payload, timeout=30)

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    data = resp.json()
    print(f"\n=== Hybrid Search Response ===")
    print(json.dumps(data, indent=2))

    assert "results" in data, "Response missing 'results' field"
    assert "query" in data, "Response missing 'query' field"

    # Results may be empty if index is empty, but endpoint should work
    results = data.get("results", [])
    print(f"\n✓ Hybrid search returned {len(results)} results")


if __name__ == "__main__":
    # Allow running as standalone script for debugging
    print("Testing orchestrator fallback fix...")
    print(f"Orchestrator URL: {ORCH_URL}")

    if not wait_ready(ORCH_URL):
        print("❌ Orchestrator is not ready")
        exit(1)

    print("✓ Orchestrator is ready")

    # Run the main test
    try:
        test_orchestrate_fallback_returns_results(None)
        print("\n✅ All tests passed! Fallback orchestration is working correctly.")
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        exit(1)

