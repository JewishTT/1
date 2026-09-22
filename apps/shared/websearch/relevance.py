"""Entity relevance re-ranking for web-search hits (web-discovery core).

A search engine returns *query-relevant* hits, which is not the same as
*entity-relevant* hits. This module scores each hit against the entity's actual
identifiers (FIO tokens, phone, email, domain, handle…) so the pipeline trains
on the *entity*, not on the phrasing of the query.

Scoring is deterministic and explainable: base is the provider score, plus
explicit bonus for exact identifier evidence (email/phone/domain) in URL, title,
snippet. Degenerate inputs must never crash: empty identifiers score 0 extra.
"""

from __future__ import annotations

import re
import urllib.parse

from websearch.contracts import DiscoveryCandidate, SearchHit
from websearch.queries import identifiers_to_tokens

_PHONE_DIGITS = re.compile(r"\d", re.I)
_TOKEN = re.compile(r"[a-z0-9]+")


def _digits_of(value: str) -> str:
    return "".join(_PHONE_DIGITS.findall(str(value)))


def entity_relevance_score(
    hit: SearchHit, identifiers: dict[str, str], *, weight_exact: float = 1.5
) -> float:
    """Entity-relevance score in [0, +inf): unknown-but-on-topic < evidence-hit.

    Exact identifier evidence (email/phone/domain) is worth far more than a
    loose token overlap, so a page containing the phone number outranks a page
    that merely mentions the same words.
    """
    base = float(hit.score or 0.0)
    if not identifiers:
        return base
    hay = f"{hit.uri} {hit.title} {hit.snippet}".lower()
    hay_no_scheme = f"{hit.title} {hit.snippet}".lower()

    # Exact identifiers: email, phone (digits), domain, crypto/handle/txid.
    exact_bonus = 0.0
    for key, value in identifiers.items():
        v = str(value).lower().strip()
        if not v or len(v) < 2:
            continue
        if "@" in v or "email" in key:  # email-like
            if v in hay or v in hay_no_scheme:
                exact_bonus += weight_exact * 2.0
            continue
        if "phone" in key or "tel" in key:
            digits = _digits_of(value)
            hay_digits = _digits_of(f"{hit.uri} {hit.title} {hit.snippet}")
            # country-code tolerant: any 7+ digit suffix of the identifier that
            # appears verbatim in the page is phone evidence.
            if len(digits) >= 7 and any(
                len(digits[i:]) >= 7 and digits[i:] in hay_digits for i in range(len(digits) - 6)
            ):
                exact_bonus += weight_exact * 2.0
            continue
        if "domain" in key or "website" in key:
            host = (
                urllib.parse.urlparse(hit.uri).netloc.lower()
                if hit.uri.startswith(("http://", "https://"))
                else hit.uri.lower()
            )
            if v.strip(".") in host or host.endswith("." + v.strip(".")):
                exact_bonus += weight_exact * 2.0
            continue
        if v in hay_no_scheme:
            exact_bonus += weight_exact * 1.2

    # Loose token overlap against the normalized identifier token list.
    tokens = identifiers_to_tokens(identifiers).split()
    if tokens:
        title_toks = set(_TOKEN.findall(hit.title.lower()))
        snip_toks = set(_TOKEN.findall(hit.snippet.lower()))
        overlaps = sum(1 for t in tokens if t in title_toks)
        overlaps += sum(1 for t in tokens if t in snip_toks)
        exact_bonus += min(1.0, overlaps * 0.3)

    return max(base, base + exact_bonus)


def rerank_for_entity(
    hits: list[SearchHit],
    identifiers: dict[str, str],
    *,
    query: str,
    intent: str = "",
    tenant_id: str = "",
    min_score: float = 1.5,
    top_k: int = 10,
) -> list[DiscoveryCandidate]:
    """Entity-relevant ranking of provider hits into discovery candidates.

    Threshold ``min_score`` keeps junk out; providers that score only in (0,1)
    are suppressed unless they carry exact identifier evidence. Results are
    deterministic (sorted by relevance desc, then uri).
    """
    scored: list[DiscoveryCandidate] = []
    for hit in hits:
        rel = entity_relevance_score(hit, identifiers)
        if rel < min_score and rel == 0.0:
            continue
        host = (
            urllib.parse.urlparse(hit.uri).netloc
            if hit.uri.startswith(("http://", "https://"))
            else ""
        )
        scored.append(
            DiscoveryCandidate(
                uri=hit.uri,
                host=host,
                title=hit.title,
                snippet=hit.snippet,
                relevance=round(rel, 4),
                query_text=query,
                intent=intent,
                provider=hit.provider,
                tenant_id=tenant_id,
            )
        )
    scored.sort(key=lambda c: (c.relevance, c.uri), reverse=True)
    return scored[:top_k]
