from __future__ import annotations
from typing import Dict, List, Any, Tuple
import hashlib
try:
    import httpx  # type: ignore
except Exception:  # pragma: no cover - handled gracefully
    httpx = None  # type: ignore
from .config import filename_from_template
from .exporter import export
from .media_discovery import discover_media


def _hash_title(title: str) -> str:
    return hashlib.sha1((title or "").strip().lower().encode("utf-8")).hexdigest()


async def _call_local(client: "httpx.AsyncClient", path: str, json_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Helper to call local FastAPI endpoints consistently."""
    r = await client.post(f"http://localhost:8000{path}", json=json_payload)
    r.raise_for_status()
    return r.json()


async def web_search(cfg: Dict[str, Any], payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Use existing /search service to collect candidate web URLs."""
    if httpx is None:
        return []
    name = str(payload.get("name") or "")
    keywords = payload.get("keywords") or []
    limit = int(payload.get("search_limit") or cfg.get("fallback", {}).get("search_limit", 10))
    timeout = cfg.get("guardrails", {}).get("timeouts", {}).get("per_step_s", 20)
    async with httpx.AsyncClient(timeout=timeout) as client:  # type: ignore[attr-defined]
        try:
            j = await _call_local(client, "/search", {"name": name, "keywords": keywords, "limit": limit})
            results = j.get("results") or []
            # Normalize shape: url, title, score
            out: List[Dict[str, Any]] = []
            for it in results:
                url = it.get("url")
                if not url:
                    continue
                out.append({
                    "url": url,
                    "title": it.get("title"),
                    "score": it.get("rrf"),
                    "source": "web_search",
                })
            return out
        except Exception:
            return []


async def ingest_urls(urls: List[str], *, text: str | None = None, timeout: float | None = None) -> Dict[str, Any] | None:
    if not urls or httpx is None:
        return None
    async with httpx.AsyncClient(timeout=timeout or 20.0) as client:  # type: ignore[attr-defined]
        try:
            return await _call_local(client, "/ingest_urls", {"urls": urls, "text": text or ""})
        except Exception:
            return None


async def run_hybrid(cfg: Dict[str, Any], payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    if httpx is None:
        return []
    name = payload.get("name", "")
    keywords = payload.get("keywords", [])
    query = f"{name} " + " ".join(keywords)
    results: List[Dict[str, Any]] = []

    timeout = cfg.get("guardrails", {}).get("timeouts", {}).get("per_step_s", 20)
    async with httpx.AsyncClient(timeout=timeout) as client:  # type: ignore[attr-defined]
        # Prefer internal /search_hybrid if exists
        try:
            k = (
                cfg.get("plan", {})
                .get("steps", [{}])
                [2]
                .get("engines", {})
                .get("opensearch", {})
                .get("k", 20)
            )
            j = await _call_local(client, "/search_hybrid", {"query": query, "k": k})
            for it in (j.get("results", []) or []):
                results.append(
                    {
                        "url": it.get("url"),
                        "title": it.get("title"),
                        "domain": it.get("domain"),
                        "source": it.get("source", "hybrid"),
                        "score": it.get("rrf") or it.get("score"),
                    }
                )
        except Exception:
            pass
    # Dedupe
    seen = set()
    deduped: List[Dict[str, Any]] = []
    for r in results:
        key = (r.get("url") or "") + "|" + _hash_title(r.get("title", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    return deduped


async def fallback_orchestrate(cfg: Dict[str, Any], payload: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    New fallback path when no URLs provided:
      1) Web search to collect candidate URLs
      2) Ingest top-N URLs
      3) Hybrid search over non-empty index
      4) Discover media (images, pdfs)
      5) Export (CSV/JSON), optionally split by entity
    Returns: (exports_meta, results_list)
    If web search yields 0 URLs, returns ({}, []).
    """
    # 1) Web search
    web_hits = await web_search(cfg, payload)
    urls = [h.get("url") for h in (web_hits or []) if h.get("url")]
    if not urls:
        return ({}, [])

    # 2) Ingest
    ingest_limit = int(payload.get("ingest_limit") or cfg.get("fallback", {}).get("ingest_limit", 10))
    await ingest_urls(urls[:ingest_limit], text=None)

    # 3) Hybrid
    results = await run_hybrid(cfg, payload)

    # 4) Media
    media = await discover_media(cfg, payload)
    results.extend(media or [])

    # 5) Export
    exp_cfg = next((s for s in cfg.get("plan", {}).get("steps", []) if s.get("name") == "export"), None)
    if not exp_cfg:
        outdir = payload.get("export_dir") or "exports"
        fname = filename_from_template("run_{yyyy}{mm}{dd}_{HH}{MM}{SS}_{slug(name)}.ext", payload.get("name", "run"))
        csv_path, json_path = export(results, outdir, fname, payload.get("name", "run"), formats=("csv", "json"), split_by_entity=True)
        return ({"csv": csv_path, "json": json_path}, results)

    outdir = exp_cfg.get("dir") or payload.get("export_dir") or "exports"
    fname = filename_from_template(exp_cfg.get("filename_template", "run_{yyyy}{mm}{dd}_{HH}{MM}{SS}_{slug(name)}.ext"), payload.get("name", "run"))
    csv_path, json_path = export(
        results,
        outdir,
        fname,
        payload.get("name", "run"),
        formats=tuple(exp_cfg.get("formats", ["csv", "json"])),
        split_by_entity=bool(exp_cfg.get("split_by_entity", True)),
    )
    return ({"csv": csv_path, "json": json_path}, results)
