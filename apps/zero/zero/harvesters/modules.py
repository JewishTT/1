"""Aggregated harvest modules (spec/010): one MODULES list per input type.

Central collection so ``HarvesterRegistry.register_all()`` can import a single
deterministic module table. Order is irrelevant — dispatch re-sorts by name.
"""

from __future__ import annotations

from .domain import MODULES as _DOMAIN
from .git import MODULES as _GIT
from .image import MODULES as _IMAGE
from .phone import MODULES as _PHONE
from .url import MODULES as _URL
from .username import MODULES as _USERNAME

MODULES = _DOMAIN + _URL + _GIT + _IMAGE + _USERNAME + _PHONE