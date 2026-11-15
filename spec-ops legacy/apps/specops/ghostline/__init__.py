"""GhostLine donor integration (Feature 031): voice-borne social engineering, gated.

GhostLine is an LLM-driven vishing operative: it places a PSTN call through Twilio,
transcribes the target with Deepgram, answers through a persuasion model, speaks back
with ElevenLabs, and runs a twelve-stage playbook to decide when to press. This package
wraps it as one of the CI/SpecOps department's subjects rather than as a script.

The division of labour across the submodules is the whole design:

``loader``     imports the vendored donor and reports exactly which parts run here
``config``     reads the platform's own credentials; reports readiness, never a secret
``catalog``    serves the donor's playbook library, with the platform's ATT&CK mapping
``engine``     runs the donor's stage machine as a dry-run simulator
``voices``     the ``clone`` verb, plus premade-voice registration
``runtime``    the ``serve`` verb, as an inspectable lifecycle
``telephony``  the ``call`` verb, minus the shell-variable tunnel URL
``redaction``  where an elicited credential is stopped from being stored
``ledger``     what an exercise produced: calls, turns, outcomes, aggregates
``service``    the composition the router calls; safety ordering lives here

Every surface answers in the department's envelope: what was served, what was not,
and whether a figure is tenant-wide. Nothing here reports a zero for something it did
not measure, and nothing here bypasses :mod:`specops.roe.gate`.
"""

from specops.ghostline.catalog import PlaybookLibrary, library
from specops.ghostline.config import GhostlineConfig, clear_config_cache, get_config
from specops.ghostline.engine import simulate
from specops.ghostline.ledger import CallLedger, ledger
from specops.ghostline.loader import donor, donor_readiness
from specops.ghostline.redaction import Redactor, generic_redactor
from specops.ghostline.runtime import RuntimeController, runtime
from specops.ghostline.service import GateRefused, Service
from specops.ghostline.telephony import DialBlocked
from specops.ghostline.voices import Voice, VoiceUnavailable, voices

__all__ = [
    "CallLedger",
    "DialBlocked",
    "GateRefused",
    "GhostlineConfig",
    "PlaybookLibrary",
    "Redactor",
    "RuntimeController",
    "Service",
    "Voice",
    "VoiceUnavailable",
    "clear_config_cache",
    "donor",
    "donor_readiness",
    "generic_redactor",
    "get_config",
    "ledger",
    "library",
    "runtime",
    "simulate",
    "voices",
]
