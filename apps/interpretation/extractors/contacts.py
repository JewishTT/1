"""Deterministic contact/identifier extraction (spec 007, US1, R-5).

Pattern layer: email, domain, IP, crypto addresses, messenger/social handles.
Phone numbers additionally normalize to E.164 via phonenumbers. No network,
no ML; every match is a pattern-sourced mention with deterministic confidence.
"""

from __future__ import annotations

import ipaddress
import re

from extractors.types import NormalizedName, TypedMention
from extractors.util import byte_offset

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_DOMAIN = re.compile(r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b", re.IGNORECASE)
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_IPV6 = re.compile(
    r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b|"
    r"\b(?:[0-9a-fA-F]{1,4}:){1,7}:?(?:[0-9a-fA-F]{1,4}:){0,6}[0-9a-fA-F]{1,4}\b"
)
_BTC = re.compile(r"\b(?:bc1[0-9a-z]{25,39}|[13][1-9A-HJ-NP-Za-km-z]{25,34})\b")
_ETH = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
_TRON = re.compile(r"\bT[1-9A-HJ-NP-Za-km-z]{33}\b")
_TELEGRAM_URL = re.compile(r"(?:t\.me/|t\.me/\+|tg://resolve\?domain=)([A-Za-z0-9_]{3,})")
_AT_HANDLE = re.compile(r"(?<![\w@])@([A-Za-z0-9_]{3,})\b")
_SOCIAL = {
    "github.com": "github",
    "linkedin.com/in": "linkedin",
    "linkedin.com/pub": "linkedin",
    "x.com": "x",
    "twitter.com": "twitter",
    "instagram.com": "instagram",
    "vk.com": "vk",
    "facebook.com": "facebook",
    "facebookprofile": "facebook",
    "t.me": "telegram",
}
_SOCIAL_URL = re.compile(
    r"(?:https?://)?(?:www\.)?((?:github\.com|linkedin\.com/in|linkedin\.com/pub|"
    r"x\.com|twitter\.com|instagram\.com|vk\.com|facebook\.com)/[A-Za-z0-9_./-]{1,50})"
)
_PHONE_SKETCH = re.compile(r"(?<![\w])(\+?[0-9][0-9\s\-()\.]{6,19}[0-9])(?![\w])")


def extract_contacts(text: str, lang_hint: str | None = None) -> list[TypedMention]:
    """Deterministic contact mentions (email/phone/handle/domain/ip/crypto)."""
    out: list[TypedMention] = []
    out += _regex_mentions(_EMAIL, "email", text, lang_hint, confidence=1.0)
    out += _regex_mentions(_DOMAIN, "domain", text, lang_hint, confidence=0.9)
    out += _ip_mentions(text, lang_hint)
    out += _crypto_mentions(text, lang_hint)
    out += _phone_mentions(text, lang_hint)
    out += _handle_mentions(text, lang_hint)
    return _dedup(out)


def _regex_mentions(
    pattern: re.Pattern[str], kind: str, text: str, lang: str | None, *, confidence: float
) -> list[TypedMention]:
    out = []
    for m in pattern.finditer(text):
        value = m.group(0)
        if kind == "email":
            value = value.rstrip(".")
        out.append(
            TypedMention(
                kind=kind,
                value=value,
                offset=byte_offset(text, m.start()),
                end_offset=byte_offset(text, m.end()),
                extractor="contacts",
                lang=lang,
                source="pattern",
                confidence=confidence,
            )
        )
    return out


def _ip_mentions(text: str, lang: str | None) -> list[TypedMention]:
    out = []
    for m in _IPV4.finditer(text):
        raw = m.group(0)
        try:
            canonical = str(ipaddress.ip_address(raw))
        except ValueError:
            continue
        if any(o > 255 for o in (int(x) for x in raw.split("."))):
            continue
        out.append(
            TypedMention(
                kind="ip",
                value=raw,
                offset=byte_offset(text, m.start()),
                end_offset=byte_offset(text, m.end()),
                extractor="contacts",
                lang=lang,
                source="pattern",
                confidence=1.0,
                normalized=NormalizedName(canonical=canonical, transforms=["ip-canonical"]),
            )
        )
    for m in _IPV6.finditer(text):
        raw = m.group(0)
        if "::" not in raw and len(raw.split(":")) != 8:
            continue
        try:
            canonical = str(ipaddress.ip_address(raw))
        except ValueError:
            continue
        out.append(
            TypedMention(
                kind="ip",
                value=raw,
                offset=byte_offset(text, m.start()),
                end_offset=byte_offset(text, m.end()),
                extractor="contacts",
                lang=lang,
                source="pattern",
                confidence=1.0,
                normalized=NormalizedName(canonical=canonical, transforms=["ip-canonical"]),
            )
        )
    return out


def _crypto_mentions(text: str, lang: str | None) -> list[TypedMention]:
    out = []
    for m in _BTC.finditer(text):
        raw = m.group(0)
        if len(raw) < 26:
            continue
        out.append(
            TypedMention(
                kind="crypto",
                value=raw,
                offset=byte_offset(text, m.start()),
                end_offset=byte_offset(text, m.end()),
                extractor="contacts",
                lang=lang,
                source="pattern",
                confidence=0.95,
                evidence={"asset": "btc"},
            )
        )
    for m in _ETH.finditer(text):
        raw = m.group(0)
        out.append(
            TypedMention(
                kind="crypto",
                value=raw,
                offset=byte_offset(text, m.start()),
                end_offset=byte_offset(text, m.end()),
                extractor="contacts",
                lang=lang,
                source="pattern",
                confidence=0.95,
                evidence={"asset": "eth"},
            )
        )
    for m in _TRON.finditer(text):
        raw = m.group(0)
        out.append(
            TypedMention(
                kind="crypto",
                value=raw,
                offset=byte_offset(text, m.start()),
                end_offset=byte_offset(text, m.end()),
                extractor="contacts",
                lang=lang,
                source="pattern",
                confidence=0.9,
                evidence={"asset": "tron"},
            )
        )
    return out


def _phone_mentions(text: str, lang: str | None) -> list[TypedMention]:
    import phonenumbers  # type: ignore[import-not-found]

    out = []
    for m in _PHONE_SKETCH.finditer(text):
        raw = m.group(0).strip()
        if len(raw) < 8:
            continue
        canonical = None
        for region in ("RU", "US", "GB"):
            for candidate in (raw, "+" + raw.lstrip("+")):
                try:
                    parsed = phonenumbers.parse(candidate, region)
                    if phonenumbers.is_valid_number(parsed):
                        canonical = phonenumbers.format_number(
                            parsed, phonenumbers.PhoneNumberFormat.E164
                        )
                        break
                except phonenumbers.NumberParseException:
                    continue
            if canonical:
                break
        if canonical is None:
            continue
        out.append(
            TypedMention(
                kind="phone",
                value=raw,
                offset=byte_offset(text, m.start()),
                end_offset=byte_offset(text, m.end()),
                extractor="contacts",
                lang=lang,
                source="pattern",
                confidence=0.9,
                normalized=NormalizedName(canonical=canonical, transforms=["phonenumbers-e164"]),
            )
        )
    return out


def _handle_mentions(text: str, lang: str | None) -> list[TypedMention]:
    out = []
    seen: set[str] = set()
    for m in _TELEGRAM_URL.finditer(text):
        handle = m.group(1)
        domain = (m.group(0).split("/", 1)[0] or "t.me").lower()
        if domain.startswith("tg"):
            domain = "t.me"
        out.append(
            TypedMention(
                kind="handle",
                value="@" + handle,
                offset=byte_offset(text, m.start()),
                end_offset=byte_offset(text, m.end()),
                extractor="contacts",
                lang=lang,
                source="pattern",
                confidence=0.95,
                evidence={"service": "telegram", "url": "https://t.me/" + handle},
            )
        )
        seen.add("tg:" + handle)
    for m in _AT_HANDLE.finditer(text):
        handle = m.group(1)
        if "tg:" + handle in seen:
            continue
        if handle.isdigit():
            continue
        out.append(
            TypedMention(
                kind="handle",
                value="@" + handle,
                offset=byte_offset(text, m.start()),
                end_offset=byte_offset(text, m.end()),
                extractor="contacts",
                lang=lang,
                source="pattern",
                confidence=0.6,
                evidence={"service": "social"},
            )
        )
    for m in _SOCIAL_URL.finditer(text):
        raw = m.group(1)
        service = _SOCIAL.get(raw.split("/", 1)[0].lower(), "social")
        handle = raw.split("/", 1)[1].split("&")[0].split("?")[0].strip("/")
        if not handle or "/" in handle:
            continue
        out.append(
            TypedMention(
                kind="handle",
                value=handle,
                offset=byte_offset(text, m.start()),
                end_offset=byte_offset(text, m.end()),
                extractor="contacts",
                lang=lang,
                source="pattern",
                confidence=0.9,
                evidence={"service": service, "url": "https://" + raw},
            )
        )
    return out


def _dedup(mentions: list[TypedMention]) -> list[TypedMention]:
    seen: dict[tuple[str, str], TypedMention] = {}
    for m in sorted(mentions, key=lambda x: (x.offset, x.kind, x.value)):
        key = (m.offset, m.kind)
        if key not in seen:
            seen[key] = m
    return [seen[k] for k in sorted(seen, key=lambda k: (seen[k].offset, seen[k].kind))]