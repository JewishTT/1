"""Git harvesters (spec/010 §0.3): commit-email discovery.

``CommitEmailHarvester`` extracts author/committer emails from git-log style
text (``Author: Name <email>`` lines). The text is read from
``seed.metadata["git_log"]`` — a git-recon style scraper upstream collects that
log, the core parser stays a pure deterministic transform (gitsnitch /
gh-mailto / GitFive method). No repository access here.
"""

from __future__ import annotations

import re

from ..type_detector import InputType, SeedInput
from .contracts import HarvestResult, ObservationCandidate
from .registry import HarvestContext

_AUTHOR_RE = re.compile(
    r"(?:Author|Committer|Signed-off-by|co-authored-by)[:\s]+(.*?)\s*<([^>@\s]+@[^>\s]+)>",
    re.IGNORECASE,
)
_COMMIT_LINE_VALID = re.compile(r"^[a-f0-9]{40}$", re.IGNORECASE)


def git_log_email(text: str) -> list[tuple[str, str, str]]:
    """Return ``(name, email, role)`` tuples found in a git-log text blob."""
    found: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    role_prefixes = {
        "author": "author",
        "committer": "committer",
        "signed-off-by": "signoff",
        "co-authored-by": "coauthor",
    }
    for match in _AUTHOR_RE.finditer(text):
        role_label = match.group(0).split(":", 1)[0].strip().lower()
        role = role_prefixes.get(role_label, "author")
        name = " ".join(match.group(1).split())
        email = match.group(2).lower()
        key = (name, email)
        if key in seen:
            continue
        seen.add(key)
        found.append((name, email, role))
    return found


class CommitEmailHarvester:
    """Username/email seed with a ``git_log`` metadata blob → commit emails."""

    name = "git_commit_email"
    required_types = frozenset({InputType.USERNAME, InputType.EMAIL})
    method = "git-commit email extractor (gitsnitch / gh-mailto / GitFive)"
    license = "MIT"
    attribution = "donors/gitsnitch, donors/gh-mailto (codeGROOVE-dev), donors/GitFive"

    def run(self, seed: SeedInput, ctx: HarvestContext) -> HarvestResult:
        git_log = str(ctx.seed.metadata.get("git_log") or "")
        if not git_log:
            return HarvestResult(module=self.name, notes=("no git_log metadata provided",))
        candidates = [
            ObservationCandidate(
                value=email,
                kind="email",
                confidence=0.85,
                source_module=self.name,
                method=self.method,
                raw_fields={"name": name, "role": role, "seed": seed.raw_value},
                evidence=f"git commit {role} identity",
            )
            for name, email, role in git_log_email(git_log)
        ]
        return HarvestResult(module=self.name, candidates=tuple(candidates))


MODULES = (CommitEmailHarvester(),)