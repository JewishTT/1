"""JSON path resolution for declarative source parsing (spec 025 §33).

A parser family needs to reach a value nested inside arbitrary API responses, and the shape
of those responses is not ours to choose. This module is the one place that knows how to
read ``a.b[0].c`` out of whatever an endpoint returned.

**Why not a full expression language.** Because the alternative is worse: a parser config
that can compute can also lie. Every path here is a *read* -- it resolves to a value or to
nothing, and it never transforms, defaults, or invents. A field declared at
``data.asns[0].asn`` that is absent yields ``None`` and the declaration is reported as
unresolved, which is the honest outcome. An expression language would let a config decide
what a missing value *means*, and every source would then mean something different.

**Wildcards collect rather than pick.** ``results[*].ip`` yields every match, because a
source with three records and a path pointing at ``[0]`` is a source that quietly drops two
thirds of what it fetched. The single-value paths (``[0]``) stay available, but they are the
explicit choice of whoever wrote them.

Nothing here knows what an entity is. It resolves paths to values; deciding that a value is
an AS number belongs to the family layer.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from typing import Any

__all__ = ["MISSING", "Missing", "collect_path", "path_exists", "resolve_path"]

#: ``name``, ``name[0]``, ``name[*]`` -- one segment.
_SEGMENT_RE = re.compile(r"([^.\[\]]+)|\[(\*|\d+)\]")

#: Sentinel distinguishing "the path resolved to null" from "the path does not exist".
#:
#: A payload field legitimately set to ``null`` and an absent field look identical under
#: ``.get()``, and the difference matters: the first says the source reported "no value",
#: the second says we did not find the field we expected. Collapsing them makes a schema
#: change look like an empty result.
Missing = object()

MISSING = Missing


def _segments(path: str) -> list[tuple[str, str]]:
    """``"a.b[0].c"`` -> ``[("a", ""), ("b", "0"), ("c", "")]``."""
    out: list[tuple[str, str]] = []
    for match in _SEGMENT_RE.finditer(str(path or "")):
        name, index = match.group(1), match.group(2)
        if name:
            out.append((name, ""))
        elif index:
            out.append(("", index))
    return out


def resolve_path(document: Any, path: str) -> Any:
    """The single value at ``path``, or :data:`MISSING`.

    A wildcard resolves to its first match here so that a single-valued field declaration
    does not need to know whether the source returns a list. Use :func:`collect_path` when
    every match matters.
    """
    found = collect_path(document, path)
    return found[0] if found else MISSING


def collect_path(document: Any, path: str) -> list[Any]:
    """Every value reachable at ``path``, following wildcards.

    Returns ``[]`` when nothing matches, which callers distinguish from a matched ``None``
    via :func:`path_exists` -- see :data:`Missing` for why that distinction is load-bearing.
    """
    values: list[Any] = [document]
    for name, index in _segments(path):
        nxt: list[Any] = []
        for value in values:
            nxt.extend(_step(value, name, index))
        values = nxt
        if not values:
            return []
    return values


def path_exists(document: Any, path: str) -> bool:
    """Whether ``path`` resolves at all, including to ``None``."""
    return bool(collect_path(document, path))


def _step(value: Any, name: str, index: str) -> Iterator[Any]:
    if name:
        if isinstance(value, Mapping) and name in value:
            yield value[name]
        return
    if index == "*":
        if isinstance(value, Mapping):
            yield from value.values()
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            yield from value
        return
    # A numeric index. Refused on a mapping rather than falling back to the ``n``-th key:
    # silently indexing a dict by position is how a source's "first" record becomes
    # whatever happened to be first in the JSON.
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        position = int(index)
        if 0 <= position < len(value):
            yield value[position]