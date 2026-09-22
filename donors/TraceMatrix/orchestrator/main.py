from typing import List, Optional, Dict, Any, Set
import os
import re
import asyncio
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, EmailStr
import httpx

# Χρήση libphonenumber για πιο αξιόπιστη αναγνώριση
import phonenumbers
from phonenumbers import NumberParseException
DEFAULT_REGION = os.getenv("PHONE_DEFAULT_REGION", "US")  # π.χ. "GR"

from fastapi.staticfiles import StaticFiles
from pathlib import Path

from hybrid_rrf import reciprocal_rank_fusion
from opensearch_client import create_index_if_not_exists, index_doc, bm25_search, knn_search, get_all_docs
from phoneinfoga_connector import phoneinfoga_lookup
from profession_filter import matches_profession
from providers_min import google_search, verify_email_reacher
from scrape_embed import fetch_and_embed, get_model
from harvester_connector import run_theharvester
# NEW services
from app.services.holehe_service import holehe_lookup_and_index
from app.services.maigret_service import maigret_lookup
from app.services.opensearch_client import ensure_indices

app = FastAPI(title="OSINT Orchestrator (OSS)")

# Ensure OpenSearch indices on startup (idempotent)
@app.on_event("startup")
async def _startup_indices():
    try:
        await ensure_indices()
    except Exception:
        pass

# Mount static directory for exported CSVs
app.mount(
    "/exports",
    StaticFiles(directory=os.getenv("EXPORT_DIR", "/app/exports")),
    name="exports",
)

# Regex patterns for extraction
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(
    r"(?:\+|00)?\s?(?:\d[\s\-\.\(\)]?){7,16}\d"  # πολύ-ανεκτικό διεθνές pattern
)

KNOWN_USER_PATTERNS = [
    ("twitter.com", lambda path: path.split("/")[1] if len(path.split("/"))>1 else None),
    ("x.com", lambda path: path.split("/")[1] if len(path.split("/"))>1 else None),
    ("github.com", lambda path: path.split("/")[1] if len(path.split("/"))>1 else None),
    ("linkedin.com/in", lambda path: path.split("/")[-1] if "linkedin.com/in/" in path else None),
    ("instagram.com", lambda path: path.split("/")[1] if len(path.split("/"))>1 else None),
    ("facebook.com", lambda path: path.split("/")[1] if len(path.split("/"))>1 else None),
]


class SearchRequest(BaseModel):
    name: str
    keywords: Optional[List[str]] = []
    limit: Optional[int] = 10


class VerifyEmailReq(BaseModel):
    email: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/search")
def search(req: SearchRequest):
    q = f"\"{req.name}\" " + " ".join(req.keywords or [])
    try:
        google_hits = google_search(q, num=min(req.limit, 10))
    except Exception as e:
        google_hits = [{"error": "google_error", "message": str(e)}]
    ranked_urls = [it.get('url') for it in google_hits if it.get('url')]
    merged = reciprocal_rank_fusion([ranked_urls], k=req.limit)
    out = []
    for u in merged:
        snippet = next((i.get("snippet") for i in google_hits if i.get("url") == u), "")
        prof_ok = matches_profession(snippet + " " + (req.name or ""))
        out.append({"url": u, "snippet": snippet, "profession_match": prof_ok})
    return {"query": q, "results": out, "meta": {"google_count": len(google_hits)}}


@app.post("/verify_email")
def verify_email(req: VerifyEmailReq):
    res = verify_email_reacher(req.email)
    if not res:
        raise HTTPException(status_code=500, detail="Reacher call failed")
    return res


class IngestReq(BaseModel):
    urls: list[str]
    source: str | None = "web"


@app.post("/ingest_urls")
def ingest_urls(req: IngestReq):
    create_index_if_not_exists()
    results = []
    for u in req.urls:
        try:
            emb = fetch_and_embed(u)
            doc = {"url": u, "title": "", "snippet": "", "source": req.source, **emb}
            index_doc(doc)
            results.append({"url": u, "status": "ok", "chars": len(emb.get("content", ""))})
        except Exception as e:
            results.append({"url": u, "status": f"error:{e}"})
    return {"ingested": results}


class HybridReq(BaseModel):
    query: str
    k: int = 10


@app.post("/search_hybrid")
def search_hybrid(req: HybridReq):
    create_index_if_not_exists()
    bm = bm25_search(req.query, size=req.k)
    model = get_model()
    qv = model.encode([req.query])[0].tolist()
    kn = knn_search(qv, size=req.k)
    bm_urls = [d["url"] for d in bm]
    kn_urls = [d["url"] for d in kn]
    fused_urls = reciprocal_rank_fusion([bm_urls, kn_urls], k=req.k)
    url_to_doc = {d["url"]: d for d in bm + kn}
    out = [url_to_doc.get(u, {"url": u}) for u in fused_urls]
    return {"query": req.query, "results": out}


@app.get("/export_csv")
def export_csv(limit: Optional[int] = None):
    """
    Export all indexed documents to CSV.
    Args:
        limit: Optional limit on number of results. If None, exports all documents.
    """
    create_index_if_not_exists()

    # Χρήση get_all_docs για όλα τα αποτελέσματα ή bm25_search με limit
    if limit is None:
        hits = get_all_docs()
    else:
        export_limit = min(limit, 10000)  # OpenSearch max
        hits = bm25_search("*", size=export_limit)

    rows = []
    for h in hits:
        rows.append({
            "Person": "",
            "Email": "",
            "Phone": "",
            "URL": h.get("url", ""),
            "Title": h.get("title", ""),
            "Snippet": h.get("snippet", ""),
            "Content_Preview": (h.get("content", "") or "")[:200],  # First 200 chars
            "Source": h.get("source", ""),
            "Score": h.get("_score", 0)
        })

    import pandas as pd
    import time, uuid

    # Determine output directory (with env override)
    out_dir_str = os.getenv("EXPORT_DIR", "/app/exports")
    out_dir = Path(out_dir_str)

    # Ensure directory exists and handle conflicts if it's a file
    if out_dir.exists() and not out_dir.is_dir():
        backup = out_dir.with_name(out_dir.name + ".bak")
        out_dir.rename(backup)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Unique filename to prevent race conditions
    fname = f"entities_{int(time.time())}_{uuid.uuid4().hex[:8]}.csv"
    out_path = out_dir / fname

    pd.DataFrame(rows).to_csv(out_path, index=False)

    # Return metadata + download path
    download_path = f"/exports/{fname}"
    return {
        "status": "ok",
        "file": str(out_path),
        "download_url": download_path,
        "rows": len(rows),
        "message": f"Exported {len(rows)} documents to CSV at {download_path}"
    }


from social_connectors import social_analyzer_username


class SocialReq(BaseModel):
    username: str


@app.post("/social_lookup")
def social_lookup(req: SocialReq):
    return social_analyzer_username(req.username)


# NEW: Email accounts via Holehe
class EmailAccountsReq(BaseModel):
    email: EmailStr


@app.post("/email_accounts")
async def email_accounts(req: EmailAccountsReq):
    try:
        hits = await holehe_lookup_and_index(req.email)
        return {"email": req.email, "hits": hits}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# NEW: Maigret lookup endpoint
class MaigretReq(BaseModel):
    username: str = Field(..., min_length=2)


@app.post("/maigret_lookup")
async def maigret_lookup_route(req: MaigretReq):
    try:
        hits = await maigret_lookup(req.username)
        return {"username": req.username, "hits": hits}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class HarvestReq(BaseModel):
    domain: str
    limit: int = 50
    source: str = "all"

@app.post("/harvest_email")
def harvest_email(req: HarvestReq):
    """Συλλογή emails & subdomains με theHarvester"""
    return run_theharvester(req.domain, req.limit, req.source)

class PhoneReq(BaseModel):
    number: str

@app.post("/phone_lookup")
def phone_lookup(req: PhoneReq):
    """OSINT lookup τηλεφώνου με PhoneInfoga"""
    return phoneinfoga_lookup(req.number)


# Helper functions for orchestrate endpoint
def _norm_phone(p: Optional[str]) -> Optional[str]:
    if not p: return None
    return re.sub(r"[^0-9+]", "", p)


def _extract_urls(items: List[Dict[str, Any]]) -> List[str]:
    urls = []
    for it in items:
        if not isinstance(it, dict): continue
        u = it.get("url") or it.get("link")
        if u and isinstance(u, str):
            urls.append(u)
    return urls


def _extract_emails(texts: List[str]) -> Set[str]:
    found = set()
    for t in texts:
        if not isinstance(t, str): continue
        for m in EMAIL_RE.findall(t):
            found.add(m.lower())
    return found


def _extract_usernames_from_urls(urls: List[str]) -> Set[str]:
    found = set()
    for u in urls:
        try:
            parsed = urlparse(u)
            domain = parsed.netloc.lower()
            path = parsed.path
            for pattern_domain, extractor in KNOWN_USER_PATTERNS:
                if pattern_domain in domain:
                    username = extractor(path)
                    if username and username.strip() and username not in ("", "home", "explore", "search"):
                        found.add(username.strip())
        except Exception:
            continue
    return found


def _dedupe_and_fix_keywords(words: List[str]) -> List[str]:
    """Μικρό normalizer για κοινά typos· επεκτάσιμο."""
    fixes = {
        "enginner": "engineer",
        "sofware": "software",
        "progrmmer": "programmer",
    }
    seen: Set[str] = set()
    out: List[str] = []
    for w in words:
        if not isinstance(w, str):
            continue
        w2 = fixes.get(w.lower().strip(), w)
        if w2 not in seen:
            out.append(w2)
            seen.add(w2)
    return out


def _extract_phones(texts: List[str]) -> List[str]:
    """
    Επιστρέφει ΜΟΝΟ έγκυρα τηλέφωνα σε E.164, χρησιμοποιώντας libphonenumber.
    - Σαρώνουμε μόνο κείμενα (όχι URLs εκτός αν είναι tel: — ο caller τα αποφεύγει).
    """
    candidates: Set[str] = set()
    for t in texts:
        if not isinstance(t, str):
            continue
        # αποφύγετε τεράστια blobs ψηφίων (πιθ. IDs)
        if len(re.sub(r"\D", "", t)) > 30:
            continue
        for match in phonenumbers.PhoneNumberMatcher(t, DEFAULT_REGION):
            num = match.number
            if phonenumbers.is_possible_number(num) and phonenumbers.is_valid_number(num):
                e164 = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
                candidates.add(e164)
    return sorted(candidates)


class OrchestrateRequest(BaseModel):
    name: Optional[str] = Field(default=None)
    keywords: List[str] = Field(default_factory=list)
    phone: Optional[str] = Field(default=None, description="E.164 preferred")
    # global & step-specific limits
    limit: int = 25
    search_limit: int = 10
    social_limit: int = 10
    email_limit: int = 20
    phone_limit: int = 5
    hybrid_k: int = 15
    ingest_limit: int = 50
    export_limit: int = 1000
    include_phoneinfoga: bool = True


@app.post("/orchestrate")
async def orchestrate(req: OrchestrateRequest):
    """
    Multi-step orchestration endpoint + optional Holehe/Maigret steps.
    """
    phone_norm = _norm_phone(req.phone)
    base_app = os.getenv("ORCHESTRATOR_BASE_URL", "http://127.0.0.1:8000")
    phoneinfoga_base = os.getenv("PHONEINFOGA_BASE_URL", "http://phoneinfoga:8080")  # will append /api

    # διορθώνουμε κοινά typos & dedupe
    base_keywords = _dedupe_and_fix_keywords([*req.keywords])
    if phone_norm:
        base_keywords.append(phone_norm)
    payload_search = {"name": req.name, "keywords": base_keywords, "limit": req.search_limit}

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        # 1) initial search
        r = await client.post(f"{base_app}/search", json=payload_search)
        r.raise_for_status()
        search_data = r.json() or {}
        items = search_data.get("results") or search_data.get("items") or []
        urls_initial = list(dict.fromkeys(_extract_urls(items)))  # de-dupe preserve order

        # pull text για email/τηλέφωνα ΜΟΝΟ από κείμενα (snippet/summary/text/title)
        texts: List[str] = []
        for it in items:
            for k in ("snippet","summary","text","title"):
                v = it.get(k)
                if isinstance(v, str): texts.append(v)

        # emails & usernames
        emails_found = list(_extract_emails(texts))[:req.email_limit]
        usernames_found = list(_extract_usernames_from_urls(urls_initial))[:req.social_limit]

        # 2) phoneinfoga (optional)
        phones_found: List[str] = []
        if not phone_norm:
            phones_found = _extract_phones(texts)[:req.phone_limit]
        phones_considered = [phone_norm] if phone_norm else phones_found

        phoneinfoga = None
        if req.include_phoneinfoga and phones_considered:
            async def pf_lookup(p: str):
                try:
                    pr = await client.get(f"{phoneinfoga_base}/api/numbers/{p}/scan/local")
                    if pr.status_code == 200:
                        return {"phone": p, "result": pr.json()}
                except Exception:
                    pass
                return {"phone": p, "error": True}
            phoneinfoga = await asyncio.gather(*[pf_lookup(p) for p in phones_considered])

        # 3) social lookups (parallel)
        SOCIAL_ANALYZER_BASE = os.getenv("SOCIAL_ANALYZER_BASE", "http://social-analyzer:9005")
        async def social_lookup(u: str):
            try:
                url1 = f"{SOCIAL_ANALYZER_BASE}/api/search"
                url2 = f"{SOCIAL_ANALYZER_BASE}/search"
                sr = await client.post(url1, json={"username": u, "limit": req.social_limit})
                if sr.status_code == 404:
                    sr = await client.post(url2, json={"username": u, "limit": req.social_limit})
                if sr.status_code == 200:
                    return {"username": u, "result": sr.json()}
            except Exception: pass
            return { "username": u, "error": True }

        social_results = await asyncio.gather(*[social_lookup(u) for u in usernames_found])

        # 4) email verification (parallel)
        async def verify_email(e: str):
            try:
                er = await client.post(f"{base_app}/verify_email", json={"email": e})
                if er.status_code == 200: return { "email": e, "result": er.json() }
            except Exception: pass
            return { "email": e, "error": True }

        email_results = await asyncio.gather(*[verify_email(e) for e in emails_found])

        # 4b) Holehe enrichment (optional)
        holehe_runs = None
        if os.getenv("ENABLE_HOLEHE_IN_ORCHESTRATE", "false").lower() == "true" and emails_found:
            holehe_runs = await asyncio.gather(*[holehe_lookup_and_index(e) for e in emails_found])

        # 4c) Maigret cross-validation (optional)
        maigret_runs = None
        if os.getenv("ENABLE_MAIGRET_IN_ORCHESTRATE", "false").lower() == "true" and usernames_found:
            maigret_runs = await asyncio.gather(*[maigret_lookup(u) for u in usernames_found])

        # 5) hybrid search
        q = " ".join(filter(None, [
            req.name, *req.keywords,
            *(phones_considered or []),
            *usernames_found, *emails_found
        ]))
        hr = await client.post(f"{base_app}/search_hybrid", json={"query": q, "k": req.hybrid_k})
        hr.raise_for_status()
        hybrid_data = hr.json() or {}
        hitems = hybrid_data.get("results") or hybrid_data.get("items") or []
        urls_hybrid = list(dict.fromkeys(_extract_urls(hitems)))

        # novel URLs (not in initial)
        novel_urls = [u for u in urls_hybrid if u not in urls_initial][:req.ingest_limit]

        # 6) ingest novel URLs
        ing_ok = 0
        urls_for_ingest = []
        if novel_urls:
            ing_resp = await client.post(f"{base_app}/ingest_urls", json={"urls": novel_urls, "source": "orchestrate"})
            if ing_resp.status_code == 200:
                ing_data = ing_resp.json()
                ingested = ing_data.get("ingested", [])
                for entry in ingested:
                    if entry.get("status") == "ok":
                        ing_ok += 1
                        urls_for_ingest.append(entry.get("url"))

        # 7) export CSV
        csv_path = None
        try:
            csv_resp = await client.get(f"{base_app}/export_csv")
            if csv_resp.status_code == 200:
                csv_data = csv_resp.json()
                csv_path = csv_data.get("file")
        except Exception:
            csv_path = "error"

    return {
        "query": q,
        "counts": {
            "initial_urls": len(urls_initial),
            "hybrid_urls": len(urls_hybrid),
            "novel_urls": len(novel_urls),
            "emails_found": len(emails_found),
            "usernames_found": len(usernames_found),
            "phones_found": len(phones_found) if not phone_norm else 1,
        },
        "samples": {
            "emails": emails_found[:5],
            "usernames": usernames_found[:5],
            "novel_urls": novel_urls[:5],
        },
        "phones_found": phones_found,
        "phones_considered": phones_considered,
        "phoneinfoga": phoneinfoga,
        "social": social_results[:req.limit],
        "emails": email_results[:req.limit],
        "holehe": holehe_runs,
        "maigret": maigret_runs,
        "ingested": { "ok": ing_ok, "urls": urls_for_ingest },
        "csv_path": csv_path
    }
