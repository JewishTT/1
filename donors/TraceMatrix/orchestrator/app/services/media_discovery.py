from __future__ import annotations
from typing import Dict, Any, List
import os
import httpx

SEARXNG_URL = os.getenv("SEARXNG_URL") or os.getenv("SEARXNG_BASE_URL") or "http://searxng:8080"
DEFAULT_TIMEOUT = float(os.getenv("MEDIA_DISCOVERY_TIMEOUT", "10"))


def _mk_query(name: str | None, keywords: List[str] | None) -> str:
    parts: List[str] = []
    if name:
        parts.append(name.strip())
    if keywords:
        parts.extend([k for k in keywords if k])
    return " ".join(parts).strip()


async def discover_media(cfg: Dict[str, Any] | None, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Return list of dicts for images & pdfs discovered via SearxNG JSON endpoints.
    items:
      - images: {url, title, domain, source="image", media_type="image"}
      - pdfs:   {url, title, domain, source="pdf",   media_type="pdf"}
    """
    name = (payload or {}).get("name", "")
    keywords = (payload or {}).get("keywords", [])
    q = _mk_query(name, keywords)

    out: List[Dict[str, Any]] = []
    timeout = DEFAULT_TIMEOUT

    images_limit = int(os.getenv("MEDIA_IMAGES_LIMIT", "20"))
    pdfs_limit = int(os.getenv("MEDIA_PDFS_LIMIT", "15"))

    async with httpx.AsyncClient(timeout=timeout) as client:
        # Images (primary: images category)
        images_out: List[Dict[str, Any]] = []
        try:
            r = await client.get(
                f"{SEARXNG_URL.rstrip('/')}/search",
                params={"q": q, "format": "json", "categories": "images", "language": "en"},
            )
            r.raise_for_status()
            j = r.json()
            for it in j.get("results", [])[: images_limit]:
                images_out.append(
                    {
                        "url": it.get("img_src") or it.get("url"),
                        "title": it.get("title"),
                        "domain": it.get("parsed_url", ""),
                        "source": "image",
                        "media_type": "image",
                    }
                )
        except Exception:
            # swallow and try fallback below
            pass

        # Fallback for images: general category; pick likely images (thumbnail or url with image extension)
        if not images_out:
            try:
                r = await client.get(
                    f"{SEARXNG_URL.rstrip('/')}/search",
                    params={"q": q, "format": "json", "categories": "general", "language": "en"},
                )
                r.raise_for_status()
                j = r.json()
                exts = (".jpg", ".jpeg", ".png", ".webp", ".gif")
                for it in j.get("results", [])[: images_limit]:
                    url = it.get("img_src") or it.get("thumbnail") or it.get("url") or ""
                    if isinstance(url, str) and url.lower().endswith(exts):
                        images_out.append(
                            {
                                "url": url,
                                "title": it.get("title"),
                                "domain": it.get("parsed_url", ""),
                                "source": "image",
                                "media_type": "image",
                            }
                        )
            except Exception:
                pass

        out.extend([x for x in images_out if x.get("url")])

        # PDFs (primary: files category with filetype:pdf)
        pdfs_out: List[Dict[str, Any]] = []
        try:
            r = await client.get(
                f"{SEARXNG_URL.rstrip('/')}/search",
                params={
                    "q": f"filetype:pdf {q}",
                    "format": "json",
                    "categories": "files",
                    "language": "en",
                },
            )
            r.raise_for_status()
            j = r.json()
            for it in j.get("results", [])[: pdfs_limit]:
                pdfs_out.append(
                    {
                        "url": it.get("url"),
                        "title": it.get("title"),
                        "domain": it.get("parsed_url", ""),
                        "source": "pdf",
                        "media_type": "pdf",
                    }
                )
        except Exception:
            # swallow and try fallback below
            pass

        # Fallback for PDFs: general category with filetype:pdf and filter on .pdf suffix
        if not pdfs_out:
            try:
                r = await client.get(
                    f"{SEARXNG_URL.rstrip('/')}/search",
                    params={
                        "q": f"filetype:pdf {q}",
                        "format": "json",
                        "categories": "general",
                        "language": "en",
                    },
                )
                r.raise_for_status()
                j = r.json()
                for it in j.get("results", [])[: pdfs_limit]:
                    url = it.get("url") or ""
                    if isinstance(url, str) and url.lower().endswith(".pdf"):
                        pdfs_out.append(
                            {
                                "url": url,
                                "title": it.get("title"),
                                "domain": it.get("parsed_url", ""),
                                "source": "pdf",
                                "media_type": "pdf",
                            }
                        )
            except Exception:
                pass

        out.extend([x for x in pdfs_out if x.get("url")])

    return [x for x in out if x.get("url")]  # drop empties
