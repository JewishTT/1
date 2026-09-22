"""Phone harvesters (spec/010 §0.4): messenger presence + dork generation.

``WhatsAppPresenceHarvester`` and ``TelegramPresenceHarvester`` probe
``wa.me``/``t.me`` through the injected transport (Ignorant / DIGI-NETRA
style, deterministic with a fake transport). ``PhoneDorkHarvester`` generates
the PhoneInfoga-style Google dork variants of a number for later search —
pure string generation, no network.

   Source repos: donors/ignorant (MIT), donors/DIGI-NETRA (MIT),
   donors/PhoneInfoga (MIT) dork patterns.
"""

from __future__ import annotations

import re

from ..type_detector import InputType, SeedInput
from .contracts import HarvestResult, ObservationCandidate
from .registry import HarvestContext

_E164_OK = re.compile(r"^\+[1-9][0-9]{6,14}$")


def e164_digits(value: str) -> str:
    """Normalize to bare digits (``+12025550199`` → ``12025550199``)."""
    return "".join(ch for ch in value if ch.isdigit())


class WhatsAppPresenceHarvester:
    """Phone → WhatsApp presence probe via ``wa.me``."""

    name = "whatsapp_presence"
    required_types = frozenset({InputType.PHONE})
    method = "WhatsApp enumeration via wa.me (Ignorant / DIGI-NETRA style)"
    license = "MIT"
    attribution = "donors/ignorant, donors/DIGI-NETRA"

    def run(self, seed: SeedInput, ctx: HarvestContext) -> HarvestResult:
        if not _E164_OK.match(seed.raw_value):
            return HarvestResult(module=self.name, notes=("not an E.164 number",))
        digits = e164_digits(seed.raw_value)
        url = f"https://wa.me/{digits}"
        if not ctx.transport.exists(url, timeout=8.0):
            return HarvestResult(module=self.name, notes=("whatsapp presence not confirmed",))
        candidate = ObservationCandidate(
            value=f"whatsapp:{digits}",
            kind="presence",
            confidence=0.9,
            source_module=self.name,
            method=self.method,
            raw_fields={"e164": seed.raw_value, "wa_url": url},
            evidence="wa.me resource responded",
        )
        return HarvestResult(module=self.name, candidates=(candidate,))


class TelegramPresenceHarvester:
    """Phone → Telegram presence probe via ``t.me``."""

    name = "telegram_presence"
    required_types = frozenset({InputType.PHONE})
    method = "Telegram enumeration via t.me (Ignorant style)"
    license = "MIT"
    attribution = "donors/ignorant"

    def run(self, seed: SeedInput, ctx: HarvestContext) -> HarvestResult:
        if not _E164_OK.match(seed.raw_value):
            return HarvestResult(module=self.name, notes=("not an E.164 number",))
        digits = e164_digits(seed.raw_value)
        url = f"https://t.me/{digits}"
        if not ctx.transport.exists(url, timeout=8.0):
            return HarvestResult(module=self.name, notes=("telegram presence not confirmed",))
        candidate = ObservationCandidate(
            value=f"telegram:{digits}",
            kind="presence",
            confidence=0.85,
            source_module=self.name,
            method=self.method,
            raw_fields={"e164": seed.raw_value, "tg_url": url},
            evidence="t.me resource responded",
        )
        return HarvestResult(module=self.name, candidates=(candidate,))


class PhoneDorkHarvester:
    """PhoneInfoga-style dork queries for a number (pure string generation)."""

    name = "phone_dorks"
    required_types = frozenset({InputType.PHONE})
    method = "PhoneInfoga-style Google dork generation"
    license = "MIT"
    attribution = "donors/PhoneInfoga dork pattern"

    def run(self, seed: SeedInput, ctx: HarvestContext) -> HarvestResult:
        digits = e164_digits(seed.raw_value)
        national = digits[1:] if len(digits) > 1 else digits
        if len(national) > 9:
            pretty = f"+{digits[0]} {national[:3]} {national[3:6]} {national[6:]}-{national[9:]}"
        else:
            pretty = seed.raw_value
        forms = (digits, f"+{digits}", pretty, "".join(ch for ch in seed.raw_value if ch.isdigit()))
        variants: list[tuple[str, str]] = []
        seen: set[str] = set()
        for form in forms:
            if form and form not in seen:
                seen.add(form)
                variants.append((form, "dork-variant"))
        candidates = [
            ObservationCandidate(
                value=f'"{variant}"',
                kind="dork_query",
                confidence=0.15,
                source_module=self.name,
                method=self.method,
                raw_fields={"phone_form": variant},
                evidence="PhoneInfoga dork form",
            )
            for variant, _pattern in variants
        ]
        return HarvestResult(module=self.name, candidates=tuple(candidates))


MODULES = (
    WhatsAppPresenceHarvester(),
    TelegramPresenceHarvester(),
    PhoneDorkHarvester(),
)