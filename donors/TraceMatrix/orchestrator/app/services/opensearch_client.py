import os, time
from typing import List, Dict, Any, Optional

try:
    from opensearchpy import OpenSearch, RequestsHttpConnection  # type: ignore
except Exception:  # pragma: no cover - dev/test env without opensearch-py
    OpenSearch = None  # type: ignore
    RequestsHttpConnection = None  # type: ignore

EMAIL_IDX = "email_accounts"
USERNAME_IDX = "usernames"


def _client() -> Optional["OpenSearch"]:
    if OpenSearch is None:
        return None
    url = os.getenv("OPENSEARCH_URL")
    if url:
        return OpenSearch(  # type: ignore
            hosts=[url],
            use_ssl=url.startswith("https://"),
            verify_certs=False,
            connection_class=RequestsHttpConnection,  # type: ignore
            timeout=20,
        )
    host = os.getenv("OPENSEARCH_HOST", "opensearch")
    port = int(os.getenv("OPENSEARCH_PORT", "9200"))
    user = os.getenv("OPENSEARCH_USER", "admin")
    pwd = os.getenv("OPENSEARCH_PASSWORD", "admin")
    return OpenSearch(  # type: ignore
        hosts=[{"host": host, "port": port}],
        http_auth=(user, pwd),
        use_ssl=False,
        verify_certs=False,
        connection_class=RequestsHttpConnection,  # type: ignore
        timeout=20,
    )


async def ensure_indices():
    c = _client()
    if c is None:
        return
    try:
        if not c.indices.exists(index=EMAIL_IDX):
            c.indices.create(index=EMAIL_IDX, body={
                "mappings": {"properties": {
                    "email": {"type": "keyword"},
                    "service": {"type": "keyword"},
                    "exists": {"type": "boolean"},
                    "emailrecovery": {"type": "keyword"},
                    "phoneNumber": {"type": "keyword"},
                    "others": {"type": "object", "enabled": True},
                    "ts": {"type": "date"}
                }}
            })
        if not c.indices.exists(index=USERNAME_IDX):
            c.indices.create(index=USERNAME_IDX, body={
                "mappings": {"properties": {
                    "username": {"type": "keyword"},
                    "site": {"type": "keyword"},
                    "url": {"type": "keyword"},
                    "source": {"type": "keyword"},
                    "ts": {"type": "date"}
                }}
            })
    except Exception:
        # Ignore errors during local dev/tests (service may be down)
        pass


async def index_email_accounts(email: str, hits: List[Dict[str, Any]]):
    if not hits:
        return
    c = _client()
    if c is None:
        return
    try:
        import json
        now = int(time.time() * 1000)
        actions = []
        for h in hits:
            actions.append({"index": {"_index": EMAIL_IDX}})
            actions.append({
                "email": email,
                "service": h.get("name") or h.get("service"),
                "exists": h.get("exists", True),
                "emailrecovery": h.get("emailrecovery"),
                "phoneNumber": h.get("phoneNumber"),
                "others": h.get("others"),
                "ts": now,
            })
        body = "\n".join(json.dumps(x) for x in actions) + "\n"
        c.bulk(body=body)
    except Exception:
        # Non-fatal if OS is not reachable
        pass
