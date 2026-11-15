"""Transcript redaction: the donor is repaired here, not declined.

GhostLine's playbooks succeed on a *spoken* secret -- ``success_regex: "\\b\\d{6}\\b"``
on a CLOSE stage means "the target read back the one-time code" -- and the donor logs
the utterance verbatim into its ``messages`` table. That is the donor working exactly
as designed.

It also collides with this platform's rules-of-engagement gate, which pins
``CAPTURE_PASSWORDS = False``: credentials entered during an assessment are not
captured, not logged, not stored. An assessment still needs to know *that* a target
complied; it does not need the secret itself, and storing the secret would make the
platform the custodian of every credential it ever elicited.

So the redaction is a repair on transfer, which is what the constitution calls for:
the donor's functionality is preserved -- the stage machine still matches, the call
still records ``compromised`` -- and only the *persistence of the secret* is cut. The
cut sits here, at the single boundary every transcript crosses, so the donor's own
call handler never has to be forked to comply.

Two properties make this safe to rely on:

* **Shape, not value.** Every pattern reports the *kind* that matched
  (``otp``/``account-number``/``credential-value``). A caller can assert "an OTP was
  elicited" without the API ever being able to return the digits.
* **Fail closed.** An unparseable pattern still scrubs -- it falls back to the
  generic shapes rather than passing the text through, because the cost of a false
  positive is a redacted digit in a transcript and the cost of a false negative is
  a stored password.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

__all__ = ("REDACTION", "RedactionResult", "Redactor", "generic_redactor")

#: The literal written in place of a matched secret. A fixed marker rather than a
#: partial mask: a partial mask leaks length, and length is a free variable an
#: attacker can iterate over.
REDACTION: Final[str] = "[redacted:no-capture]"

#: Author-declared patterns, grouped by the kind of secret the playbook is fishing
#: for. A playbook's own ``success_regex`` is always applied first and its kind is
#: named ``playbook-success`` so the operator can see *which* declared shape fired.
_GENERIC: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    (
        "credential-value",
        # The separator is REQUIRED, not optional. With it optional, any sentence
        # containing the word "secret" matched its next word as a value -- "nothing
        # secret here" came back with "here" redacted, which trains an operator to
        # ignore the redaction marker and therefore stops reading it.
        re.compile(
            r"(?i)\b(password|passcode|passphrase|pass word|secret|credential)"
            r"\s*(?:is|are|was|were|:|=|=>)\s*[\"']?([\w!@#$%^&*.\-]{3,})[\"']?"
        ),
    ),
    (
        "otp",
        re.compile(
            r"(?i)\b(?:one[- ]time\s+(?:code|password|pin)|otp|verification code)\b"
            r"\s*(?:is|are|:|=|=>)?\s*(\d{4,10})"
        ),
    ),
    # A bare 4-8 digit run said alone is the shape every one of the donor's own
    # CLOSE-stage success_regexes matches, so it is redacted even when the playbook
    # declared no pattern at all. The lookbehind also rejects a hyphen, which keeps
    # an identifier like `SEC-4217` readable: a ticket number is not a credential,
    # and a transcript full of redacted ticket numbers is a transcript nobody reads.
    ("digit-run", re.compile(r"(?<![\w.\-])\d{4,8}(?![\w.])")),
    # Long digit runs: routing / account / card / IBAN fragments.
    ("account-number", re.compile(r"(?<![\w.\-])\d{9,17}(?![\w.])")),
)

#: Words that look like credentials to a reader but are never scrubbed, because
#: redacting them would gut the transcript an operator needs to read.
_ALLOWLIST: Final[frozenset[str]] = frozenset(
    {
        "2024",
        "2025",
        "2026",
        "3000",
        "3001",
        "4000",
        "5000",
        "8000",
        "8080",
        "8443",
        "911",
        "112",
    }
)


@dataclass(frozen=True, slots=True)
class RedactionResult:
    """A scrubbed string plus the *kinds* of secret that were removed."""

    text: str
    kinds: tuple[str, ...]

    @property
    def scrubbed(self) -> bool:
        return bool(self.kinds)

    def as_dict(self) -> dict[str, object]:
        return {"text": self.text, "kinds": list(self.kinds), "scrubbed": self.scrubbed}


class Redactor:
    """Scrubs credential-shaped spans from text.

    Built from a playbook's declared ``success_regex`` set plus the generic shapes.
    Instances are cheap and stateless; the compiled patterns are the only state.
    """

    def __init__(self, declared: tuple[str, ...] = ()) -> None:
        self._declared: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
            ("playbook-success", re.compile(pattern, re.IGNORECASE))
            for pattern in declared
            if _compiles(pattern)
        )
        self._uncompilable: tuple[str, ...] = tuple(
            pattern for pattern in declared if not _compiles(pattern)
        )

    @property
    def patterns(self) -> tuple[str, ...]:
        """The declared patterns this redactor could not compile.

        Surfaced rather than swallowed: a playbook with a broken regex is a
        playbook whose stage machine will not fire, and the operator needs to see
        that next to the transcript, not discover it as a silent pass-through.
        """
        return self._uncompilable

    def scrub(self, text: str) -> RedactionResult:
        """Return ``text`` with every credential-shaped span replaced.

        Order matters and it is not cosmetic. The generic shapes run FIRST because they
        understand value extraction -- ``(password|secret)\\s*(?:is|:|=)\\s*(value)``
        knows the word is a marker and the thing after it is the secret. A playbook's
        declared pattern usually does not: the donor's own CLOSE-stage regex is
        ``\\b(password)\\b``, whose only capture group is the marker word. Applied first
        it would replace "password" and leave the value standing in the open, and the
        generic pattern would then find no marker to key off and pass it through.
        """
        if not text:
            return RedactionResult(text="", kinds=())
        kinds: list[str] = []
        out = text
        for kind, pattern in (*_GENERIC, *self._declared):
            out, hit = _apply(out, pattern, kind)
            if hit:
                kinds.append(kind)
        return RedactionResult(text=out, kinds=tuple(dict.fromkeys(kinds)))


def _apply(text: str, pattern: re.Pattern[str], kind: str) -> tuple[str, bool]:
    """Replace matches of ``pattern``; report whether anything was replaced."""
    hit = False

    def _replace(match: re.Match[str]) -> str:
        nonlocal hit
        groups = [g for g in match.groups() if g]
        if not groups:
            # No capture groups: the whole match is the secret.
            target = match.group(0)
        else:
            # With groups, the LAST one is the secret. A pattern like
            # `(password|secret)\s*(\w+)` captures the lead-in word first and the
            # value second; redacting the lead-in would leave the password sitting
            # in the transcript with a redacted noun in front of it.
            target = groups[-1]
        if target.strip() in _ALLOWLIST:
            return match.group(0)
        hit = True
        return match.group(0).replace(target, REDACTION, 1)

    return pattern.sub(_replace, text), hit


def _compiles(pattern: str) -> bool:
    try:
        re.compile(pattern)
    except re.error:
        return False
    return bool(pattern.strip())


def generic_redactor() -> Redactor:
    """A redactor with no playbook patterns -- the generic shapes alone.

    Used wherever the playbook is unknown (an inbound call, a legacy row in the
    ledger), so a transcript is never stored unscubbed just because the caller did
    not say which playbook produced it.
    """
    return Redactor()
