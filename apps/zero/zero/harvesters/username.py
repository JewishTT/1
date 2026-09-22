"""Username harvesters (spec/010 §0.3): social patterns + worker adapters.

``SocialProfilePatternHarvester`` is the core deterministic "sherlock-style"
projection: username → known profile URL templates with optional existence
probe. ``SherlockWorkerAdapter`` and ``MaigretWorkerAdapter`` are the *thin
worker-command initializers* for the vendored CLI tools (they never shell out
during a synchronous harvest — they emit ``CommandSpec`` for the platform to
schedule, per the task contract).

   Source repos: donors/sherlock (MIT), donors/maigret (MIT) — vendored
   tool data only, as worker initialization.
"""

from __future__ import annotations

import re

from ..type_detector import InputType, SeedInput
from .contracts import CommandSpec, HarvestResult, ObservationCandidate
from .registry import HarvestContext

_HANDLE_OK = re.compile(r"^[a-zA-Z0-9_]{3,30}$")

_PROFILE_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("github.com", "github"),
    ("x.com", "twitter"),
    ("www.reddit.com/user", "reddit"),
    ("instagram.com", "instagram"),
    ("t.me", "telegram"),
    ("linkedin.com/in", "linkedin"),
    ("facebook.com", "facebook"),
    ("medium.com/@", "medium"),
    ("gitlab.com", "gitlab"),
)


class SocialProfilePatternHarvester:
    """Username → probable social profile URLs (sherlock-style patterns)."""

    name = "social_pattern"
    required_types = frozenset({InputType.USERNAME})
    method = "social-profile pattern projection (Sherlock-style)"
    license = "MIT"
    attribution = "donors/sherlock profile template data"

    def run(self, seed: SeedInput, ctx: HarvestContext) -> HarvestResult:
        handle = seed.raw_value
        candidates: list[ObservationCandidate] = []
        for host, platform in _PROFILE_TEMPLATES:
            url = f"https://{host}/{handle}"
            exists = ctx.transport.exists(url)
            confidence = round(0.85 if exists else 0.35, 2)
            candidates.append(
                ObservationCandidate(
                    value=url,
                    kind="social_profile",
                    confidence=confidence,
                    source_module=self.name,
                    method=self.method,
                    raw_fields={"handle": handle, "platform": platform, "verified": exists},
                    evidence=f"social profile projection, verified={exists}",
                )
            )
        return HarvestResult(module=self.name, candidates=tuple(candidates))


class SherlockWorkerAdapter:
    """Worker-mode initialization for the vendored Sherlock CLI (MIT)."""

    name = "sherlock_worker"
    required_types = frozenset({InputType.USERNAME})
    method = "vendored sherlock worker command (username enumeration, 400+ sites)"
    license = "MIT"
    attribution = "donors/sherlock (sherlock-project/sherlock)"

    def run(self, seed: SeedInput, ctx: HarvestContext) -> HarvestResult:
        return HarvestResult(
            module=self.name,
            commands=(
                CommandSpec(
                    tool="sherlock",
                    args=(seed.raw_value, "--timeout", "10"),
                    method=self.method,
                    timeout_s=300.0,
                ),
            ),
        )


class MaigretWorkerAdapter:
    """Worker-mode initialization for the vendored Maigret CLI (MIT)."""

    name = "maigret_worker"
    required_types = frozenset({InputType.USERNAME, InputType.EMAIL})
    method = "vendored maigret worker command (3000+ site dossier by username/email)"
    license = "MIT"
    attribution = "donors/maigret (soxoj/maigret)"

    def run(self, seed: SeedInput, ctx: HarvestContext) -> HarvestResult:
        return HarvestResult(
            module=self.name,
            commands=(
                CommandSpec(
                    tool="maigret",
                    args=(seed.raw_value,),
                    method=self.method,
                    timeout_s=600.0,
                ),
            ),
        )


MODULES = (
    SherlockWorkerAdapter(),
    MaigretWorkerAdapter(),
    SocialProfilePatternHarvester(),
)