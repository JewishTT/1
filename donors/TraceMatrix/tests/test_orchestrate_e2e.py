import os, time, json, requests

ORCH_URL = os.getenv("ORCH_URL", "http://localhost:8000")

def wait_ready(url, tries=60):
    for _ in range(tries):
        try:
            r = requests.get(f"{url}/docs", timeout=2)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError("Orchestrator not ready")

def test_orchestrate_happy_path():
    assert wait_ready(ORCH_URL)
    payload = {
        "name": "Panagiotis Drakatos",
        "keywords": ["athens","software engineer","keyword-only orchestration"],
        "search_limit": 15,
        "social_limit": 10,
        "email_limit": 20,
        "phone_limit": 5,
        "hybrid_k": 20,
        "ingest_limit": 60,
        "export_limit": 2000,
        "fallback": True
    }
    resp = requests.post(f"{ORCH_URL}/orchestrate", json=payload, timeout=300)
    assert resp.status_code == 200
    data = resp.json()
    # Minimum structural assertions so E2E δεν "κλειδώνει" υλοποίηση
    assert "summary" in data
    assert "export" in data
    # Αν γίνεται export CSV, να έχει μέγεθος/paths
    if isinstance(data.get("export"), dict):
        assert "csv_rows" in data["export"]
        assert data["export"]["csv_rows"] >= 0

