"""Aggregated harvest modules (spec/010): one MODULES list per input type.

Central collection so ``HarvesterRegistry.register_all()`` can import a single
deterministic module table. Order is irrelevant — dispatch re-sorts by name.
"""

from __future__ import annotations

from .domain import MODULES as _DOMAIN
from .git import MODULES as _GIT
from .image import MODULES as _IMAGE
from .url import MODULES as _URL
from .username import MODULES as _USERNAME

# Phone-to-messenger account probing is deliberately not registered in the
# production module table. Those adapters remain importable for isolated tests,
# but a phone number must not be used to test private messaging-account presence.
MODULES = _DOMAIN + _URL + _GIT + _IMAGE + _USERNAME