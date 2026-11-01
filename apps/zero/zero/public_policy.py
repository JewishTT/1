"""Production allow-list for the public zero-layer collection profile.

The full offline harvester catalogue remains available to contract tests. Live public
research only retains technical/public-page leads and generic organisational contact
channels; it does not turn a website crawl into personal-contact or account profiling.
"""

from __future__ import annotations

from .harvesters.contracts import ObservationCandidate
from urllib.parse import urlsplit

from .type_detector import InputType, SeedInput

_GENERIC_MAILBOXES = frozenset({
    "abuse", "admin", "billing", "careers", "contact", "finance", "hello",
    "hr", "info", "jobs", "legal", "marketing", "media", "office", "partners",
    "postmaster", "press", "privacy", "recruiting", "sales", "security",
    "support", "team", "webmaster",
})

_BLOCKED_KINDS = frozenset({
    "phone", "presence", "breach", "dork_query", "geo", "influence_score",
    "home_address", "personal_address", "face", "biometric", "credential",
})

_ALLOWED_PUBLIC_KINDS = frozenset({
    "domain", "dns_record", "url", "technology", "certificate",
    "public_document", "publication", "public_name", "public_role",
    "public_affiliation", "public_organization", "public_document_title",
    "public_document_summary", "public_document_published_at", "public_page_link",
})


def allow_public_candidate(seed: SeedInput, candidate: ObservationCandidate) -> bool:
    """Fail closed unless a candidate is a declared public technical lead."""
    if seed.detected_type not in {InputType.DOMAIN, InputType.URL}:
        return False
    kind = str(candidate.kind).strip().lower()
    if kind in _BLOCKED_KINDS:
        return False
    if kind == "email":
        local = str(candidate.value).rsplit("@", 1)[0].strip().lower()
        return local in _GENERIC_MAILBOXES
    if kind == "social_profile":
        # Only a link actually present on the fetched page; no guessed username templates.
        return candidate.source_module == "social_link_extractor"
    if kind == "public_page_link":
        if candidate.source_module != "public_document_metadata":
            return False
        parent = urlsplit(str(candidate.raw_fields.get("parent_url") or seed.raw_value))
        target = urlsplit(str(candidate.value or ""))
        try:
            parent_host = (parent.hostname or "").encode("idna").decode("ascii").lower()
            target_host = (target.hostname or "").encode("idna").decode("ascii").lower()
            return (
                parent.scheme.lower() == "https"
                and target.scheme.lower() == "https"
                and bool(parent_host)
                and target_host == parent_host
                and parent.port in (None, 443)
                and target.port in (None, 443)
                and not target.username
                and not target.password
            )
        except (UnicodeError, ValueError):
            return False
    return kind in _ALLOWED_PUBLIC_KINDS


__all__ = ["allow_public_candidate"]
