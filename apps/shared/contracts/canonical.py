"""Canonical serialisation and digest helpers (spec 030 contract 08 / T033, FR-032, P10).

Everything in the platform that claims "the same input produces the same identity" bottoms out
here. Two properties make that claim worth anything, and both are enforced by refusing rather
than by defaulting:

**Stable ordering, at every level.** ``json.dumps(sort_keys=True)`` sorts the top level of a
mapping. It does not reach inside a ``dict`` reached through a ``default`` hook, it does not
give two equal-but-differently-built sets a deterministic order, and it does not stop a
``str()`` from leaking process-local state into the bytes that get hashed. This module
normalises the *whole* structure first and only then serialises, so ordering is a property of
the value rather than of how the value was assembled.

**No uncontrolled stringification.** The obvious shortcut for "some type I did not think about"
is ``json.dumps(..., default=str)``. That is how ``<object object at 0x7f3a1c04d5e0>`` ends up
inside a content address, and it is why a digest computed in one process stops matching the same
digest computed in another: the memory address is different every run, so two identical logical
inputs hash differently, forever, with no error and no test that notices. The existing
``domain.relation_identity`` helper still carries that ``default=_normalise`` fallback for its
hot path. This module is the
identity-critical path and therefore has **no fallback at all**: an unrecognised type raises
:class:`CanonicalError`. A declared escape hatch exists for callers that know what they are
doing -- a ``canonical_form()`` method -- but it is opt-in per type, never discovered by
probing for ``__str__``.

**Timestamps are normalised, and a naive one is refused.** ``datetime.isoformat()`` renders the
offset it happens to carry, so the same instant expressed in two timezones is two strings and two
digests. Everything here is folded to UTC and rendered with a ``Z``. A *naive* datetime is refused
outright rather than assumed to be UTC: an instant that does not say which instant it means is
not a timestamp, and defaulting it manufactures a fact the producer never asserted.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import re
from collections.abc import Mapping
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from pathlib import PurePath
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

__all__ = [
    "CanonicalError",
    "UnhashableForIdentity",
    "canonical_bytes",
    "canonical_form",
    "canonical_json",
    "canonicalize",
    "digest_of",
    "instant_text",
    "normalize_instant",
]

#: ``0x`` followed by six or more hex digits. The signature of a memory address in CPython's
#: default ``repr`` (``<Foo object at 0x7f3a1c04d5e0>``) and of ``f"{id(x):#x}"``.
_ADDRESS_LIKE = re.compile(r"0x[0-9A-Fa-f]{6,}")

#: A type carrying a method with this name is asked how it canonicalises itself. This is the
#: one sanctioned way for a type outside this module's knowledge to reach a digest, and it has
#: to be spelled out in source rather than discovered by probing for ``__str__``.
_CANONICAL_FORM = "canonical_form"


class CanonicalError(ValueError):
    """A value cannot be reduced to a canonical form.

    Raised at the point of failure rather than papered over. The default reading of an
    unserialisable value is "there is no such value", and the default reading of a value
    serialised with ``str()`` is "the value is whatever its repr said today" - which is how a
    content address acquires a dependency on the heap layout of the process that computed it.
    """


class UnhashableForIdentity(CanonicalError):
    """A value reached a digest carrying something process-local in it.

    Separate from :class:`CanonicalError` because the remedy differs: a value of an unknown
    *type* needs a ``canonical_form()``, while a string that merely *looks* like a memory
    address needs its real content. Neither can be resolved by falling back to ``str()``.
    """


@runtime_checkable
class _SelfCanonicalizing(Protocol):
    """A type that knows how it canonicalises itself. Opt-in, never inferred."""

    def canonical_form(self) -> Any: ...


def normalize_instant(value: datetime) -> datetime:
    """Fold one aware datetime to UTC, or refuse a naive one.

    The refusal is the point. ``datetime.now()`` in a process that never set ``TZ`` produces a
    naive value that looks exactly like a UTC instant, and folding it silently would pin a
    wall-clock reading to a timezone nobody chose. FR-020 gives source facts eight typed
    clocks; a clock that does not say which clock it is not one of them.
    """
    if not isinstance(value, datetime):
        raise CanonicalError(f"expected a datetime, got {type(value).__name__}")
    if value.tzinfo is None or value.utcoffset() is None:
        raise CanonicalError(
            f"naive datetime {value.isoformat()} cannot be canonicalised: an instant that does "
            "not state its offset is not an instant (FR-020)"
        )
    return value.astimezone(UTC)


def instant_text(value: datetime) -> str:
    """The one canonical text for an instant: UTC, ``Z``-suffixed, second-or-finer precision."""
    return normalize_instant(value).isoformat().replace("+00:00", "Z")


def _canonical_float(value: float) -> float:
    if math.isnan(value) or math.isinf(value):
        # json would emit the bare tokens NaN/Infinity, which are not JSON and are not
        # orderable across implementations. A non-finite quantity is a missing measurement,
        # and the caller should say so with None (FR-016).
        raise CanonicalError(
            f"{value!r} has no canonical form; report an unmeasured quantity as null, not as "
            "NaN or Infinity"
        )
    # -0.0 and 0.0 are the same number and must not be two different digests.
    return 0.0 if value == 0.0 else value


def _enum_value(value: Enum) -> Any:
    return _normalize(value.value, path=f"<{type(value).__name__}.value>")


def _normalize(value: Any, *, path: str) -> Any:
    """Reduce one value to something :func:`json.dumps` renders deterministically.

    Recursive, and total: every branch either returns a canonical leaf or raises. There is no
    branch that returns ``str(value)``.
    """
    if value is None or isinstance(value, bool | str):
        # A StrEnum member is already its own value; isinstance keeps that without a copy.
        return value
    if isinstance(value, int):
        # IntEnum lands here; int() gives the number json renders, not the member's repr.
        return int(value)
    if isinstance(value, float):
        return _canonical_float(value)
    if isinstance(value, bytes | bytearray):
        return {"$bytes": bytes(value).hex()}
    if isinstance(value, datetime):
        return instant_text(value)
    if isinstance(value, date):
        return {"$date": value.isoformat()}
    if isinstance(value, time):
        return {"$time": value.isoformat()}
    if isinstance(value, timedelta):
        return {"$duration_seconds": value.total_seconds()}
    if isinstance(value, Decimal):
        # str(), deliberately: a Decimal's value is exact and its shortest round-trip form is
        # stable, which float() is not. This is a declared conversion, not a fallback.
        return {"$decimal": str(value)}
    if isinstance(value, UUID):
        return {"$uuid": str(value)}
    if isinstance(value, PurePath):
        return {"$path": value.as_posix()}
    if isinstance(value, Enum):
        return _enum_value(value)
    if isinstance(value, Mapping):
        return _normalize_mapping(value, path=path)
    if isinstance(value, set | frozenset):
        return _normalize_set(value, path=path)
    if isinstance(value, list | tuple):
        # Order is load-bearing here: a directed pair and a sequence of reads are not the
        # same value, so a sequence is never sorted.
        return [_normalize(item, path=f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, _SelfCanonicalizing) and not dataclasses.is_dataclass(value):
        return _normalize(value.canonical_form(), path=f"{path}.canonical_form()")
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _normalize_dataclass(value, path=path)

    raise CanonicalError(
        f"{type(value).__name__} at {path} has no canonical form and will not be reduced with "
        f"str()/repr(): a memory address or a repr in a content address makes the digest a "
        f"function of the heap layout. Give {type(value).__name__} a "
        f"{_CANONICAL_FORM}() method, or pass a plain mapping."
    )


def _normalize_mapping(value: Mapping[Any, Any], *, path: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, item in value.items():
        name = _mapping_key(key, path=path)
        if name in out:
            raise CanonicalError(
                f"two distinct mapping keys at {path} both canonicalise to {name!r}; the "
                "canonical form would lose one of them"
            )
        out[name] = _normalize(item, path=f"{path}.{name}")
    return out


def _mapping_key(key: Any, *, path: str) -> str:
    if isinstance(key, str):
        return key
    if isinstance(key, bool | int | float):
        return json.dumps(key)
    if isinstance(key, Enum):
        return _mapping_key(key.value, path=path)
    if isinstance(key, UUID | PurePath | datetime | date):
        return str(key)
    raise CanonicalError(
        f"mapping key {type(key).__name__} at {path} cannot be reduced to a string without "
        "str(), which is how two distinct keys collapse into one"
    )


def _normalize_set(value: set[Any] | frozenset[Any], *, path: str) -> list[Any]:
    # Normalise first, then sort by serialised form: two sets of different types holding
    # "equal" members must land in the same order regardless of member type.
    items = [_normalize(item, path=f"{path}{{...}}") for item in value]
    return sorted(items, key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False))


def _normalize_dataclass(value: Any, *, path: str) -> dict[str, Any]:
    fields = {f.name: getattr(value, f.name) for f in dataclasses.fields(value)}
    return _normalize_mapping(fields, path=path)


def canonicalize(value: Any) -> Any:
    """The canonical, JSON-renderable form of ``value``.

    Keys sorted, sets ordered, datetimes folded to UTC, and no value produced by ``str()`` or
    ``repr()``. Raises :class:`CanonicalError` for a type this module does not know and
    :class:`UnhashableForIdentity` for one that carries process-local text.
    """
    reduced = _normalize(value, path="$")
    _reject_address_like(reduced, path="$")
    return reduced


def _reject_address_like(value: Any, *, path: str) -> None:
    """Refuse a canonical form that carries a memory address.

    Belt and braces, and not redundant: the normaliser never calls ``str()`` on an unknown
    object, but a caller can still *pass* an address as a string -- ``f"{id(payload):#x}"``
    stored in a field last session -- and that string is otherwise a perfectly well-formed
    canonical leaf. Detecting it here is what makes "no ``id()`` reaches a digest" a checked
    property rather than a convention.
    """
    if isinstance(value, str):
        if _ADDRESS_LIKE.search(value):
            # The offending text is deliberately NOT echoed. An error message carrying a memory
            # address is itself unreproducible, and this message is what shows up in a log
            # line that two runs of the same failure are expected to match.
            raise UnhashableForIdentity(
                f"the string at {path} contains a memory address; identity computed from id() "
                "is different in every process and cannot be replayed"
            )
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_address_like(item, path=f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _reject_address_like(item, path=f"{path}[{index}]")


def canonical_json(value: Any) -> str:
    """Canonical UTF-8 JSON text: sorted keys, no insignificant whitespace, no NaN."""
    return json.dumps(
        canonicalize(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_bytes(value: Any) -> bytes:
    """Canonical JSON as the bytes that actually get hashed."""
    return canonical_json(value).encode("utf-8")


def digest_of(value: Any, *, prefix: str = "sha256:") -> str:
    """The content address of ``value``: ``prefix`` plus the hex SHA-256 of its canonical form."""
    return prefix + hashlib.sha256(canonical_bytes(value)).hexdigest()


def canonical_form(self: Any) -> Any:
    """Attach ``canonical_form()`` to a dataclass so it may be digested.

    Declared opt-in for types outside this module's knowledge. Written as a decorator rather
    than as a protocol check so the escape hatch is visible in the source of the type that
    takes it.
    """
    if not dataclasses.is_dataclass(self):
        raise CanonicalError(f"canonical_form() is for dataclasses; {type(self).__name__} is not")

    def _form() -> Any:
        return {f.name: getattr(self, f.name) for f in dataclasses.fields(self)}

    self.canonical_form = _form  # type: ignore[attr-defined]
    return self