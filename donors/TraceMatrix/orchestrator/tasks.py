from .celery_app import celery_app

@celery_app.task(name="tasks.scrape_and_ingest")
def scrape_and_ingest(urls: list[str]) -> dict:
    # Hook: Trafilatura + NER + file_meta + OpenSearch bulk
    return {"ok": True, "count": len(urls)}

@celery_app.task(name="tasks.username_scan")
def username_scan(username: str) -> dict:
    # Hook: Social-Analyzer / Sherlock / Maigret
    return {"username": username, "sources_found": 0}

