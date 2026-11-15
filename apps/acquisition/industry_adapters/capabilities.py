"""Curated capability policy derived from industry tool surveys.

Reference modules are not copied or executed. Capabilities must be reimplemented
behind the acquisition allowlist, explicit engagement scope, budget ledger, and
immutable observation gate before they become runnable.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CapabilityReference:
    reference_id: str
    upstream_project: str
    upstream_module: str
    disposition: str
    rationale: str


CAPABILITY_REFERENCES: tuple[CapabilityReference, ...] = (
    CapabilityReference(
        "domain-registration-posture", "TheBigBrother", "domain_oracle",
        "reimplement-with-allowlist",
        "RDAP and DNS posture are useful, but upstream runtime lacks Cognitive egress and provenance controls.",
    ),
    CapabilityReference(
        "tls-certificate-posture", "TheBigBrother", "ssl_sentinel",
        "implemented-in-cognitive",
        "Cognitive TLS posture is bound to an authorization scope and port 443 only.",
    ),
    CapabilityReference(
        "passive-subdomain-discovery", "theHarvester", "subdomains",
        "external-rest-sidecar",
        "Use the finite REST API; keep GPL-2.0-only code outside the Python 3.11-3.13 workspace.",
    ),
    CapabilityReference(
        "entity-economic-interchange", "FollowTheMoney", "entity-model",
        "optional-interchange",
        "Use a curated schema/property allowlist and a separate provenance sidecar; never auto-merge identities.",
    ),
)

_BLOCKED_MODULES: dict[str, str] = {
    "face_matcher": "biometric identification and face matching are not part of the connector fabric",
    "cam_vector": "camera discovery and surveillance pivots are not permitted in this integration",
    "stealer_parser": "stolen credentials and infostealer logs are excluded",
    "breach_vault": "private breach and credential data are excluded",
    "hlr_analyzer": "subscriber and SIM identity enrichment is excluded",
    "digital_footprint": "cross-service account enumeration is excluded",
    "shadow_clone": "username enumeration and identity correlation are excluded",
    "persona_synthesizer": "personality and identity profiling are excluded",
    "deep_identity": "synthetic identity and biometric profiling are excluded",
    "ransom_negotiator": "extortion negotiation and private victim data are excluded",
    "tripwire_vault": "tracking pixels and covert personal tracking are excluded",
}


def blocked_capability_reason(module_name: str) -> str | None:
    return _BLOCKED_MODULES.get(module_name.strip().lower())


def require_approved_capability(module_name: str, *, registered: frozenset[str]) -> None:
    name = module_name.strip().lower()
    reason = blocked_capability_reason(name)
    if reason is not None:
        raise PermissionError(reason)
    if name not in registered:
        raise LookupError(f"capability is not registered for execution: {name}")
