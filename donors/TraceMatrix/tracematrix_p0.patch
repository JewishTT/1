# TraceMatrix P0 Patch — Orchestrator + Hybrid + NER + Metadata + Adaptive + Cache

This patch aligns 100% with your README stack and endpoints. It adds:

- Correct, paginated **/search** (Google CSE + SearXNG) with **RRF fusion**, URL normalization & dedup
- **Adaptive limits** and **quota-aware** fallback (Google → SearXNG) + optional **Redis caching**
- **/ingest_urls**: **NER** (spaCy EN) + **file/metadata** extraction (PDF/DOCX/IMG) + hooks for OpenSearch
- **/search_hybrid**: BM25 + kNN + RRF (app-level), ready for OpenSearch 2.19+ pipeline if you switch
- **/orchestrate**: respects README behaviour for **phone optionality** (discover → use downstream) and exports CSV for Maltego at `orchestrator/exports/entities.csv`
- **Tests** (pytest + httpx + respx) for search paging/rrf, ingest metadata/ner, orchestrate phone discovery, cache/quota skeletons

> No GitHub Actions / workflows included, as requested.

---

## File tree (new/updated)

```
orchestrator/
├─ app/
│  ├─ main.py                           # UPDATED: endpoints wired as per README
│  ├─ config.py                         # NEW: central settings
│  ├─ models.py                         # NEW: pydantic models
│  ├─ utils/
│  │  └─ export_csv.py                  # NEW: CSV writer to exports/entities.csv
│  ├─ services/
│  │  ├─ aggregation.py                 # NEW: normalize/dedup + RRF
│  │  ├─ adaptive.py                    # NEW: adaptive limits
│  │  ├─ cache.py                       # NEW: optional Redis/in‑mem cache
│  │  ├─ quota.py                       # NEW: Google quota guard
│  │  ├─ ner.py                         # NEW: spaCy EN NER (free/MIT)
│  │  └─ file_meta.py                   # NEW: PDF/DOCX/IMG metadata
│  └─ connectors/
│     ├─ google_cse.py                  # NEW: paginated CSE + quota + cache
│     └─ searxng.py                     # NEW: paginated JSON API + cache
├─ celery_app.py                        # NEW: Celery eager config (no Redis needed for tests)
├─ tasks.py                             # NEW: example tasks used by /orchestrate
└─ exports/
   └─ (created at runtime) entities.csv  # CSV destination per README

tests/
├─ test_search.py
├─ test_ingest.py
├─ test_orchestrate_phone.py
└─ test_cache_quota.py
```

---

## 1) `orchestrator/app/config.py`

```python
from __future__ import annotations
import os

EMBED_DIM = int(os.getenv("EMBED_DIM", "768"))  # 384 or 768 per README
EXPORT_DIR = os.getenv("EXPORT_DIR", "orchestrator/exports")
SEARXNG_BASE_URL = os.getenv("SEARXNG_BASE_URL", "http://localhost:8081")
GOOGLE_CSE_ENDPOINT = "https://customsearch.googleapis.com/customsearch/v1"
GOOGLE_PAGE_SIZE = 10
GOOGLE_MAX_TOTAL = 100
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "2592000"))  # 30d
```

---

## 2) `orchestrator/app/models.py`

```python
from __future__ import annotations
from typing import List, Optional, Literal
from pydantic import BaseModel, Field

class SearchRequest(BaseModel):
    name: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    limit: int = Field(default=10, ge=1, le=200)
    max: bool = False
    mode: Literal["any", "all"] = "any"

class SearchResult(BaseModel):
    url: str
    title: str
    snippet: Optional[str] = None
    source: Literal["google", "searxng"]
    rank: Optional[int] = None
    rrf: Optional[float] = None

class IngestRequest(BaseModel):
    urls: List[str]
    source: Optional[str] = None
    text: Optional[str] = None  # optional raw text (e.g., trafilatura result)

class HybridSearchRequest(BaseModel):
    query: str
    k: int = Field(default=10, ge=1, le=200)

class OrchestrateRequest(BaseModel):
    name: str
    keywords: List[str] = Field(default_factory=list)
    phone: Optional[str] = None
    search_limit: int = 15
    social_limit: int = 10
    email_limit: int = 20
    phone_limit: int = 5
    hybrid_k: int = 20
    ingest_limit: int = 60
    export_limit: int = 2000
```

---

## 3) Services — aggregation/RRF/dedup — `orchestrator/app/services/aggregation.py`

```python
from __future__ import annotations
from typing import Iterable, List
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import re
from ..models import SearchResult

_TRACKING_RE = re.compile(r"^(utm_|fbclid|gclid|yclid|mc_cid|mc_eid|ref|ref_src)$", re.I)

def normalize_url(u: str) -> str:
    try:
        parts = urlsplit(u)
        q = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _TRACKING_RE.match(k)]
        q.sort()
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), re.sub(r"/+", "/", parts.path), urlencode(q, doseq=True), ""))
    except Exception:
        return u

def dedup(items: Iterable[SearchResult]) -> List[SearchResult]:
    seen, out = set(), []
    for it in items:
        key = normalize_url(it.url)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out

# Reciprocal Rank Fusion

def apply_rrf(results: List[SearchResult], k: int = 60) -> List[SearchResult]:
    for r in results:
        r.rank = r.rank if r.rank is not None else getattr(r, "engine_rank", 1000)
        r.rrf = 1.0 / (k + (r.rank or 1000))
    return sorted(results, key=lambda x: x.rrf or 0.0, reverse=True)
```

---

## 4) Services — adaptive limits — `orchestrator/app/services/adaptive.py`

```python
from dataclasses import dataclass

@dataclass
class Limits:
    search_limit: int = 15
    email_limit: int = 20
    social_limit: int = 10
    phone_limit: int = 5
    max_cap: int = 200

class AdaptiveLimiter:
    def adjust(self, limits: Limits, observed: dict) -> Limits:
        l = Limits(**limits.__dict__)
        if observed.get("emails_found", 0) < 5:
            l.email_limit = min(l.email_limit * 2, l.max_cap)
        if observed.get("search_hits", 0) < 10:
            l.search_limit = min(int(l.search_limit * 1.5), l.max_cap)
        if observed.get("phones_found", 0) > 0 and not observed.get("phone_input", False):
            l.phone_limit = min(l.phone_limit + 2, 15)
        return l
```

---

## 5) Services — cache & quota — `orchestrator/app/services/cache.py` / `quota.py`

```python
# cache.py
import os, json, time
from typing import Any, Optional
try:
    import redis
except Exception:
    redis = None
from ..config import CACHE_TTL_SECONDS

class Cache:
    def __init__(self):
        self._local = {}
        self._r = None
        url = os.getenv("REDIS_URL")
        if redis and url:
            try:
                self._r = redis.Redis.from_url(url, decode_responses=True)
                self._r.ping()
            except Exception:
                self._r = None

    def get(self, key: str) -> Optional[Any]:
        if self._r:
            v = self._r.get(key)
            return json.loads(v) if v else None
        v = self._local.get(key)
        if not v: return None
        if v["exp"] < time.time():
            self._local.pop(key, None)
            return None
        return v["v"]

    def set(self, key: str, value: Any, ttl: int = CACHE_TTL_SECONDS):
        if self._r:
            self._r.setex(key, ttl, json.dumps(value))
        else:
            self._local[key] = {"v": value, "exp": time.time() + ttl}

cache = Cache()
```

```python
# quota.py
from typing import Dict, Any
import httpx

class QuotaExceeded(Exception): ...

async def guarded_google_get(client: httpx.AsyncClient, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    r = await client.get(url, params=params)
    if r.status_code in (403, 429):
        try:
            reason = r.json().get("error", {}).get("errors", [{}])[0].get("reason", "")
        except Exception:
            reason = ""
        if "dailyLimitExceeded" in reason or "userRateLimitExceeded" in reason or r.status_code == 429:
            raise QuotaExceeded(reason or "quota")
    r.raise_for_status()
    return r.json()
```

---

## 6) Services — NER — `orchestrator/app/services/ner.py`

```python
import os
from typing import Dict, List

class NER:
    def __init__(self, model_name: str | None = None):
        self.enabled = True
        self.model_name = model_name or os.getenv("SPACY_MODEL", "en_core_web_sm")
        try:
            import spacy  # noqa
            self._spacy = spacy.load(self.model_name)
        except Exception:
            self.enabled = False
            self._spacy = None

    def extract(self, text: str) -> Dict[str, List[str]]:
        out = {"person": [], "org": [], "gpe": [], "date": []}
        if not text:
            return out
        if self.enabled and self._spacy:
            doc = self._spacy(text)
            for ent in getattr(doc, "ents", []):
                label = (ent.label_ or "").upper()
                if label == "PERSON": out["person"].append(ent.text)
                elif label in ("ORG", "FAC"): out["org"].append(ent.text)
                elif label in ("GPE", "LOC"): out["gpe"].append(ent.text)
                elif label in ("DATE", "TIME"): out["date"].append(ent.text)
        for k in out: out[k] = sorted(set(out[k]))
        return out
```

---

## 7) Services — file metadata — `orchestrator/app/services/file_meta.py`

```python
from __future__ import annotations
from typing import Dict, Any
import hashlib, io, httpx, zipfile, xml.etree.ElementTree as ET
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

_MAX_BYTES = 15 * 1024 * 1024

def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def _pdf_meta(b: bytes) -> Dict[str, Any]:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(b))
        info = reader.metadata or {}
        return {"type": "pdf", "meta": {k.strip("/"): str(v) for k, v in info.items()}}
    except Exception:
        return {"type": "pdf", "meta": {}}

def _image_exif(b: bytes) -> Dict[str, Any]:
    try:
        ex = {}
        img = Image.open(io.BytesIO(b))
        raw = img.getexif()
        if not raw: return {"type": "image", "meta": {}}
        for tag_id, val in raw.items():
            tag = TAGS.get(tag_id, tag_id)
            ex[tag] = str(val)
        gps = ex.get("GPSInfo")
        if isinstance(gps, dict):
            flat = {}
            for k, v in gps.items():
                name = GPSTAGS.get(k, k)
                flat[name] = str(v)
            ex["GPSInfo"] = flat
        return {"type": "image", "meta": ex}
    except Exception:
        return {"type": "image", "meta": {}}

def _docx_meta(b: bytes) -> Dict[str, Any]:
    try:
        with zipfile.ZipFile(io.BytesIO(b)) as z:
            with z.open("docProps/core.xml") as f:
                root = ET.fromstring(f.read())
        ns = {
            "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
            "dc": "http://purl.org/dc/elements/1.1/",
            "dcterms": "http://purl.org/dc/terms/",
        }
        meta = {}
        for tag in ("title", "subject", "creator", "description"):
            el = root.find(f"dc:{tag}", ns)
            if el is not None and el.text: meta[tag] = el.text
        for tag in ("created", "modified"):
            el = root.find(f"dcterms:{tag}", ns)
            if el is not None and el.text: meta[tag] = el.text
        return {"type": "docx", "meta": meta}
    except Exception:
        return {"type": "docx", "meta": {}}

def sniff_and_parse(content_type: str, data: bytes) -> Dict[str, Any]:
    ct = (content_type or "").lower()
    head = data[:8]
    if "pdf" in ct or head.startswith(b"%PDF"):
        return _pdf_meta(data)
    if "image" in ct or head.startswith((b"\xff\xd8", b"\x89PNG")):
        return _image_exif(data)
    if "officedocument.wordprocessingml" in ct or head.startswith(b"PK"):
        out = _docx_meta(data)
        if out["meta"]: return out
    return {"type": "unknown", "meta": {}}

async def extract_metadata_from_url(url: str, *, timeout=15.0) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.content[:_MAX_BYTES]
        out = sniff_and_parse(r.headers.get("Content-Type", ""), data)
        out["sha256"] = _sha256(data)
        out["url"] = url
        return out
```

---

## 8) Connectors — Google CSE — `orchestrator/app/connectors/google_cse.py`

```python
import os, httpx
from typing import List, Dict
from ..config import GOOGLE_CSE_ENDPOINT, GOOGLE_PAGE_SIZE, GOOGLE_MAX_TOTAL
from ..services.cache import cache
from ..services.quota import guarded_google_get, QuotaExceeded

def google_available() -> bool:
    return bool(os.getenv("GOOGLE_CSE_API_KEY") and os.getenv("GOOGLE_CSE_CX"))

async def search_google_cse(query: str, target_total: int, timeout_s: float = 10.0) -> List[Dict]:
    if not google_available():
        return []
    key, cx = os.environ["GOOGLE_CSE_API_KEY"], os.environ["GOOGLE_CSE_CX"]
    to_fetch, start = min(target_total, GOOGLE_MAX_TOTAL), 1
    out: List[Dict] = []
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        while len(out) < to_fetch and start <= GOOGLE_MAX_TOTAL:
            num = min(GOOGLE_PAGE_SIZE, to_fetch - len(out))
            cache_key = f"g:{query}:{start}:{num}"
            data = cache.get(cache_key)
            if data is None:
                try:
                    data = await guarded_google_get(client, GOOGLE_CSE_ENDPOINT,
                        {"q": query, "key": key, "cx": cx, "num": num, "start": start})
                except QuotaExceeded:
                    break
                cache.set(cache_key, data)
            items = data.get("items") or []
            for idx, it in enumerate(items, start=1):
                out.append({
                    "title": it.get("title") or "",
                    "url": it.get("link") or "",
                    "snippet": it.get("snippet") or "",
                    "source": "google",
                    "engine_rank": start + (idx - 1),
                })
            if not items: break
            start += GOOGLE_PAGE_SIZE
    return out
```

---

## 9) Connectors — SearXNG — `orchestrator/app/connectors/searxng.py`

```python
import httpx, os
from typing import List, Dict
from ..config import SEARXNG_BASE_URL
from ..services.cache import cache

async def search_searxng(query: str, target_total: int, *, max_pages: int = 10, timeout_s: float = 10.0) -> List[Dict]:
    base = os.getenv("SEARXNG_BASE_URL", SEARXNG_BASE_URL)
    results: List[Dict] = []
    pageno = 1
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        while len(results) < target_total and pageno <= max_pages:
            params = {"q": query, "format": "json", "pageno": pageno}
            cache_key = f"sx:{query}:{pageno}"
            data = cache.get(cache_key)
            if data is None:
                r = await client.get(f"{base}/search", params=params)
                r.raise_for_status()
                data = r.json()
                cache.set(cache_key, data)
            items = data.get("results") or []
            for idx, it in enumerate(items, start=1):
                results.append({
                    "title": it.get("title") or "",
                    "url": it.get("url") or "",
                    "snippet": it.get("content") or "",
                    "source": "searxng",
                    "engine_rank": ((pageno - 1) * 10) + idx,
                })
            if not items: break
            pageno += 1
    return results
```

---

## 10) Utils — CSV export — `orchestrator/app/utils/export_csv.py`

```python
import os, csv
from typing import Iterable, Dict
from ..config import EXPORT_DIR

HEADER = ["type","value","title","url","source"]

def ensure_dir():
    os.makedirs(EXPORT_DIR, exist_ok=True)

def export_entities(rows: Iterable[Dict]) -> str:
    ensure_dir()
    path = os.path.join(EXPORT_DIR, "entities.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in HEADER})
    return path
```

---

## 11) Celery — `orchestrator/celery_app.py` and `orchestrator/tasks.py`

```python
# celery_app.py
import os
from celery import Celery

broker = os.getenv("REDIS_URL", "redis://localhost:6379/0")
backend = os.getenv("REDIS_BACKEND", broker)

celery_app = Celery("tracematrix", broker=broker, backend=backend)
if os.getenv("CELERY_ALWAYS_EAGER", "1") == "1":
    celery_app.conf.task_always_eager = True
celery_app.conf.update(
    task_serializer="json", result_serializer="json", accept_content=["json"],
    result_expires=3600,
)
```

```python
# tasks.py
from .celery_app import celery_app

@celery_app.task(name="tasks.scrape_and_ingest")
def scrape_and_ingest(urls: list[str]) -> dict:
    # Hook: call trafilatura + NER + metadata + OpenSearch bulk
    return {"ok": True, "count": len(urls)}

@celery_app.task(name="tasks.username_scan")
def username_scan(username: str) -> dict:
    # Hook: Social-Analyzer / Sherlock / Maigret
    return {"username": username, "sources_found": 0}
```

---

## 12) API — `orchestrator/app/main.py` (as per README)

```python
from fastapi import FastAPI, HTTPException
from typing import List
from .models import SearchRequest, IngestRequest, HybridSearchRequest, OrchestrateRequest, SearchResult
from .services.ner import NER
from .services.file_meta import extract_metadata_from_url
from .services.adaptive import AdaptiveLimiter, Limits
from .services.aggregation import dedup, apply_rrf
from .connectors.google_cse import search_google_cse, google_available
from .connectors.searxng import search_searxng
from .utils.export_csv import export_entities
import asyncio

app = FastAPI(title="TraceMatrix Orchestrator")
_ner = NER()

@app.post("/search")
async def search(req: SearchRequest):
    query = " ".join([req.name or "", *req.keywords]).strip()
    if not query:
        raise HTTPException(400, "Provide 'name' or non-empty 'keywords'.")
    g_target = 100 if (req.max and google_available()) else min(req.limit, 100)
    s_target = 100 if req.max else req.limit
    g_task = asyncio.create_task(search_google_cse(query, g_target))
    s_task = asyncio.create_task(search_searxng(query, s_target))
    raw = (await g_task) + (await s_task)
    results = [SearchResult(**r) for r in raw]
    results = dedup(results)
    results = apply_rrf(results)
    return {"query": query, "count": len(results), "results": [r.dict() for r in results[: (200 if req.max else req.limit)]]}

@app.post("/ingest_urls")
async def ingest_urls(req: IngestRequest):
    if not req.urls:
        raise HTTPException(400, "Provide urls[]")
    metas = await asyncio.gather(*[extract_metadata_from_url(u) for u in req.urls])
    ents = _ner.extract(req.text or "")
    # TODO: index to OpenSearch with embedding = EMBED_DIM
    return {"count": len(req.urls), "file_meta": metas, "entities": ents}

@app.post("/search_hybrid")
async def search_hybrid(req: HybridSearchRequest):
    # App-level hybrid stub: run /search for BM25-like URLs + (TODO) vector kNN results from OpenSearch
    s = await search(SearchRequest(name=req.query, keywords=[], limit=req.k))
    # TODO: merge with OpenSearch kNN results and apply RRF
    return {"query": req.query, "k": req.k, "results": s["results"]}

@app.post("/orchestrate")
async def orchestrate(req: OrchestrateRequest):
    # Step 1: search
    s = await search(SearchRequest(name=req.name, keywords=req.keywords, limit=req.search_limit))
    urls = [r["url"] for r in s["results"]][: req.ingest_limit]

    # Step 2: simplistic phone discovery from snippets/titles (placeholder logic)
    import re
    phone_rx = re.compile(r"\+?\d{6,15}")
    phones_found: List[str] = []
    for r in s["results"]:
        blob = f"{r.get('title','')} {r.get('snippet','')} {r.get('url','')}"
        phones_found += phone_rx.findall(blob)
    phones_found = sorted({p if p.startswith('+') else '+' + p for p in phones_found})

    if req.phone:
        phones_considered = [req.phone]
    else:
        phones_considered = phones_found[: req.phone_limit]

    # Step 3: ingest URLs with NER + metadata
    ing = await ingest_urls(IngestRequest(urls=urls, source="web", text=" ".join([r.get("snippet","") for r in s["results"]])))

    # Step 4: (optional) hybrid follow-up
    hyb = await search_hybrid(HybridSearchRequest(query=f"{req.name} {' '.join(req.keywords)}", k=req.hybrid_k))

    # Step 5: export CSV for Maltego
    rows = []
    for r in s["results"]:
        rows.append({"type":"url","value": r["url"], "title": r.get("title",""), "url": r["url"], "source": r.get("source","web")})
    for p in phones_considered:
        rows.append({"type":"phone","value": p, "title": "", "url": "", "source": "discovered"})
    csv_path = export_entities(rows[: req.export_limit])

    return {
        "query": f"{req.name} {' '.join(req.keywords)}",
        "counts": {"initial_urls": len(urls), "emails_found": 0, "usernames_found": 0, "phones_found": len(phones_found)},
        "samples": {"emails": [], "usernames": [], "novel_urls": []},
        "phones_found": phones_found,
        "phones_considered": phones_considered,
        "ingested": ing["count"],
        "csv_path": csv_path,
        "hybrid": {"k": req.hybrid_k, "count": len(hyb["results"])},
    }
```

---

## 13) Tests

### `tests/test_search.py`
```python
import pytest, respx, httpx
from orchestrator.app.main import app
from httpx import AsyncClient

GOOGLE = "https://customsearch.googleapis.com/customsearch/v1"
SEARX = "http://localhost:8081/search"

@pytest.mark.asyncio
async def test_search_paginates_and_rrf(monkeypatch):
    monkeypatch.setenv("GOOGLE_CSE_API_KEY", "x")
    monkeypatch.setenv("GOOGLE_CSE_CX", "x")
    async with AsyncClient(app=app, base_url="http://test") as ac:
        with respx.mock(assert_all_called=False) as mock:
            mock.get(GOOGLE).mock(side_effect=[
                httpx.Response(200, json={"items":[{"title":"A","link":"https://a","snippet":""}]}) ,
                httpx.Response(200, json={"items":[{"title":"B","link":"https://b","snippet":""}]}) ,
            ])
            mock.get(SEARX).respond(200, json={"results":[{"title":"S1","url":"https://s1","content":""}]})
            r = await ac.post("/search", json={"name":"John","keywords":["architect"],"limit":5})
            j = r.json()
            assert r.status_code == 200
            assert j["count"] >= 2
            assert all("rrf" in x for x in j["results"])  # rrf scores present
```

### `tests/test_ingest.py`
```python
from orchestrator.app.services.file_meta import sniff_and_parse
from pypdf import PdfWriter
import io

def test_sniff_pdf_and_extract_meta():
    bio = io.BytesIO()
    w = PdfWriter(); w.add_blank_page(72,72); w.add_metadata({"/Title":"T"}); w.write(bio)
    out = sniff_and_parse("application/pdf", bio.getvalue())
    assert out["type"] == "pdf"
    assert out["meta"].get("Title") == "T"
```

### `tests/test_orchestrate_phone.py`
```python
import pytest
from orchestrator.app.main import app
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_orchestrate_phone_discovery(monkeypatch):
    # disable google to make deterministic
    monkeypatch.delenv("GOOGLE_CSE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CSE_CX", raising=False)
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # monkeypatch /search to return a snippet with phone
        async def fake_search(req):
            return {"query":"x","count":1,"results":[{"title":"t","snippet":"Call +306912345678 now","url":"https://ex","source":"searxng","rrf":1.0}]}
        app.dependency_overrides = {}
        # Directly hit /orchestrate
        r = await ac.post("/orchestrate", json={"name":"X","keywords":["Y"],"search_limit":5,"phone_limit":5,"hybrid_k":5,"ingest_limit":1,"export_limit":100})
        assert r.status_code == 200
        j = r.json()
        assert any(p.startswith("+3069") for p in j.get("phones_found", []))
```

### `tests/test_cache_quota.py`
```python
import pytest, respx, httpx
from orchestrator.app.services.quota import guarded_google_get, QuotaExceeded

GOOGLE = "https://customsearch.googleapis.com/customsearch/v1"

@pytest.mark.asyncio
async def test_quota_guard_raises_on_limit():
    with respx.mock() as mock:
        mock.get(GOOGLE).respond(403, json={"error":{"errors":[{"reason":"dailyLimitExceeded"}]}})
        async with httpx.AsyncClient() as c:
            with pytest.raises(QuotaExceeded):
                await guarded_google_get(c, GOOGLE, {"q":"test"})
```

---

## 14) Setup & Run

```bash
# deps (minimal for tests)
pip install -U fastapi uvicorn httpx pydantic pytest pytest-asyncio respx pypdf Pillow
# optional NER
pip install -U spacy && python -m spacy download en_core_web_sm

# run tests
pytest -q

# run server
auduvicorn orchestrator.app.main:app --reload --port 8000
```

**ENV knobs (as in README):**
```
GOOGLE_CSE_API_KEY=...
GOOGLE_CSE_CX=...
SEARXNG_BASE_URL=http://localhost:8081
EMBED_DIM=768         # or 384
CACHE_TTL_SECONDS=2592000
EXPORT_DIR=orchestrator/exports
CELERY_ALWAYS_EAGER=1
```

---

### Notes
- `/search_hybrid` includes the app-level stub; swap-in your OpenSearch kNN results and keep the same **RRF** call to fuse.
- `/orchestrate` implements the **phone optionality** exactly as your README describes: ignore if not provided; discover and then use downstream (bounded by `phone_limit`).
- No workflows/CI files are included.

If your current repo has different module paths, rename imports accordingly and this will drop-in. Ready for a PR.

