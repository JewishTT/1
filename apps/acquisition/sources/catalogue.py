"""Source catalogue: declarative OSINT source definitions.

A source is a *configuration*, not an implementation. One loader plus one executor covers
every definition in the catalogue, so adding an integration means writing YAML, not Python.

This module is the boundary between the donor's catalogue and our substrate. It reads a
source definition and produces a :class:`SourceDefinition` whose every field has been
validated, normalised and given an identity. Nothing here performs I/O, decides anything, or
knows what an entity, a relation or a graph edge is.

Six defects in the upstream catalogue schema are corrected here rather than in the YAML,
because they are properties of the loader and every reader would otherwise have to repeat
them:

``params`` must reach the cache key
    The upstream HTTP cache key is ``sha256(METHOD \\\\0 URL \\\\0 BODY)``. 72 of the 146
    definitions put their query in ``tool.params`` rather than in the URL, which made the
    key constant across every query. :func:`_flatten_params` folds the params into the URL
    at load time, so the cache key cannot collide, and the executor needs no knowledge of
    where the query lived.

``pagination`` is absent from the schema
    Zero of the 146 definitions declare it, so multi-page sources silently returned page one.
    :func:`_derive_pagination` infers a page strategy from ``per_page``/``limit``/``page``
    where the definition already carries one, and records that the inference happened.

``contact`` is absent from 98 definitions
    The upstream policy maps an unrecognised contact class to the most exposing level, so a
    missing value silently forbids passive-only operation. We default to ``active`` and
    *record* that the value was defaulted, so the restriction is visible rather than implied.

``kind`` is absent from 127 definitions
    We derive it from the ``tool`` body: a ``url`` means HTTP, a ``binary`` means a local tool.

``requires_key`` without ``key_env``
    Keyed definitions must name the environment variable. An unnamed one is a definition that
    cannot run, and it is refused at load time with a named reason.

``parser`` resolving to a no-op
    Ten names are ``lambda x: x`` in the upstream parser table — they return their input.
    Those are recorded as :attr:`SourceDefinition.parser_is_identity` so a consumer can see
    that a source's structured output will in fact be raw.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CATALOGUE_ROOT = Path(__file__).parent / "estorides"

SOURCE_ID_PREFIX = "SRC-"

#: Contact classes, ordered by how much they touch the target. Mirrors the donor's ordering
#: and its fail-closed rule, with the default made explicit rather than implied.
CONTACT_LEVELS: Mapping[str, int] = {
    "none": 0,
    "public_api": 1,
    "search_engine": 2,
    "archive": 3,
    "passive_dns": 4,
    "active": 5,
}

DEFAULT_CONTACT = "active"

#: Parser names that are identity functions upstream — the payload comes back unparsed.
IDENTITY_PARSERS: frozenset[str] = frozenset({"raw_text", "raw", "identity", "json"})

_HTTP_STATUS_RE = re.compile(r"\s+")


class CatalogueError(ValueError):
    """A source definition is unusable and names the reason it was dropped.

    Carries a stable snake_case ``code`` so a dropped definition is countable by reason
    rather than only visible in a log line.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Pagination:
    """How to advance from one page to the next, and when to stop.

    ``max_pages`` is a real ceiling, not a hint: the executor stops there and records that
    it stopped. ``page_size`` is a *request* bound and a *stop trigger*; without it the
    executor cannot know a page is short and would fetch the ceiling every time.
    """

    strategy: str = "none"  # none | page | cursor | offset
    param: str = "page"
    page_size: int = 0
    max_pages: int = 10
    cursor_param: str = "cursor"
    cursor_path: str = "next"
    list_path: str = ""
    offset_param: str = "offset"
    limit_param: str = "limit"
    inferred: bool = False

    @property
    def enabled(self) -> bool:
        return self.strategy != "none"

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "param": self.param,
            "page_size": self.page_size,
            "max_pages": self.max_pages,
            "cursor_path": self.cursor_path,
            "list_path": self.list_path,
            "inferred": self.inferred,
        }


@dataclass(frozen=True)
class SourceDefinition:
    """One validated source: everything needed to schedule and execute it, nothing more."""

    source_id: str
    name: str
    enabled: bool
    category: str
    description: str
    parser: str
    applies_to: tuple[str, ...]
    entity_hints: tuple[str, ...]
    requires_key: bool
    key_env: str
    contact: str
    contact_inferred: bool
    kind: str
    kind_inferred: bool
    os_requirement: str
    tool: Mapping[str, Any]
    pagination: Pagination
    parser_is_identity: bool
    source_path: str
    logs_queries: bool = False
    definition: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def contact_level(self) -> int:
        """Numeric exposure of this source. Unknown classes are the most exposing."""
        return CONTACT_LEVELS.get(self.contact, CONTACT_LEVELS[DEFAULT_CONTACT])

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "name": self.name,
            "enabled": self.enabled,
            "category": self.category,
            "description": self.description,
            "parser": self.parser,
            "parser_is_identity": self.parser_is_identity,
            "applies_to": list(self.applies_to),
            "entity_hints": list(self.entity_hints),
            "requires_key": self.requires_key,
            "key_env": self.key_env,
            "contact": self.contact,
            "contact_level": self.contact_level,
            "contact_inferred": self.contact_inferred,
            "kind": self.kind,
            "kind_inferred": self.kind_inferred,
            "pagination": self.pagination.to_dict(),
        }


def source_id_for(name: str) -> str:
    """Content-addressed source id, so the same definition always names the same source."""
    from domain.relation_identity import digest128

    return SOURCE_ID_PREFIX + digest128(canonical(name))


def canonical(value: Any) -> str:
    from domain.relation_identity import canonical_material

    return canonical_material(value)


def _flatten_params(tool: Mapping[str, Any]) -> dict[str, Any]:
    """Fold ``tool.params`` into ``tool.url`` so the query is part of the cache key.

    The upstream key hashed only method, URL and body. 72 definitions carry their whole
    query in ``params``, so two different queries to one source produced the same key and a
    cached response for the first was returned for the second. Folding at load time means
    no downstream component can get this wrong.
    """
    params = tool.get("params") or {}
    if not isinstance(params, Mapping) or not params:
        return dict(tool)
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    url = str(tool.get("url") or "")
    if not url:
        return dict(tool)
    parts = urlsplit(url)
    merged = parse_qsl(parts.query, keep_blank_values=True) + [
        (k, v) for k, v in params.items()
    ]
    merged_tool = {k: v for k, v in tool.items() if k != "params"}
    merged_tool["url"] = urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(merged), parts.fragment)
    )
    return merged_tool


def _derive_pagination(tool: Mapping[str, Any]) -> Pagination:
    """Read a page strategy out of the tool body, or declare there is none.

    Upstream ships no ``pagination`` key at all, so this inference is what makes a
    multi-page source return more than its first page. The result records that it was
    inferred, so a definition that genuinely does not paginate is distinguishable from one
    whose strategy we failed to see.
    """
    if tool.get("binary"):
        return Pagination()  # a local tool runs once
    url = str(tool.get("url") or "")
    if not url:
        return Pagination()
    # The page hints live in the *query*, which for most definitions arrived as
    # `tool.params` and was folded into the URL by ``_flatten_params``. Reading only the
    # tool body would therefore find nothing, which is how this inference passed over every
    # multi-page source in the catalogue the first time.
    from urllib.parse import parse_qsl, urlsplit

    query = dict(parse_qsl(urlsplit(url).query, keep_blank_values=True))
    if "cursor" in query or "next" in query or "after" in query:
        return Pagination(strategy="cursor", inferred=True)
    for key in ("per_page", "page_size", "limit", "page", "offset"):
        if key in query:
            raw = query[key]
            size = int(raw) if str(raw).isdigit() else 0
            strategy = "offset" if key == "offset" else "page"
            return Pagination(
                strategy=strategy,
                param=key,
                page_size=size,
                inferred=True,
            )
    return Pagination()


def _derive_kind(tool: Mapping[str, Any], declared: str) -> tuple[str, bool]:
    if declared:
        return declared, False
    if tool.get("binary"):
        return "system_app", True
    if tool.get("url"):
        return "http", True
    return "unknown", True


def _derive_contact(declared: str) -> tuple[str, bool]:
    if declared:
        value = str(declared).strip().lower()
        if value in CONTACT_LEVELS:
            return value, False
        # An unrecognised class is the most exposing one, so a typo cannot quietly widen
        # what an operator believes they are doing. The default is recorded, not implied.
        return DEFAULT_CONTACT, True
    return DEFAULT_CONTACT, True


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(str(v) for v in value)
    return ()


def load_source(path: Path) -> SourceDefinition:
    """Parse and validate one definition. Raises :class:`CatalogueError` if it cannot run."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise CatalogueError("definition_not_a_mapping", f"{path.name} is not a mapping")

    name = str(raw.get("name") or "").strip()
    if not name:
        raise CatalogueError("source_without_name", f"{path.name} declares no name")

    tool = raw.get("tool")
    if not isinstance(tool, Mapping) or not (tool.get("url") or tool.get("binary")):
        raise CatalogueError("source_without_tool", f"{name} declares no url or binary")

    requires_key = bool(raw.get("requires_key"))
    key_env = str(raw.get("key_env") or "").strip()
    if requires_key and not key_env:
        raise CatalogueError(
            "keyed_source_without_key_env",
            f"{name} requires a key but names no key_env, so it cannot be run",
        )

    tool = _flatten_params(tool)
    contact, contact_inferred = _derive_contact(str(raw.get("contact") or ""))
    kind, kind_inferred = _derive_kind(tool, str(raw.get("kind") or ""))
    parser = str(raw.get("parser") or "raw_text")
    category = _HTTP_STATUS_RE.sub(" ", str(raw.get("category") or "")).strip()

    return SourceDefinition(
        source_id=source_id_for(name),
        name=name,
        enabled=bool(raw.get("enabled", False)),
        category=category,
        description=_HTTP_STATUS_RE.sub(" ", str(raw.get("description") or "")).strip(),
        parser=parser,
        applies_to=_as_tuple(raw.get("applies_to")),
        entity_hints=_as_tuple(raw.get("entity_hints")),
        requires_key=requires_key,
        key_env=key_env,
        contact=contact,
        contact_inferred=contact_inferred,
        kind=kind,
        kind_inferred=kind_inferred,
        os_requirement=str(raw.get("os") or "any"),
        tool=dict(tool),
        pagination=_derive_pagination(tool),
        parser_is_identity=parser in IDENTITY_PARSERS,
        source_path=str(path),
        logs_queries=bool(raw.get("logs_queries", False)),
        definition=dict(raw),
    )


def load_catalogue(
    root: Path | None = None,
) -> tuple[tuple[SourceDefinition, ...], dict[str, list[str]]]:
    """Load every definition under ``root``, deterministically.

    Returns the definitions sorted by ``source_id`` plus a rejection report keyed by reason.
    A definition that cannot run is *counted*, not logged and forgotten, so the catalogue's
    real coverage is measurable rather than assumed.
    """
    base = root or CATALOGUE_ROOT
    paths = sorted(p for ext in ("*.yaml", "*.yml") for p in base.rglob(ext))
    accepted: list[SourceDefinition] = []
    rejected: dict[str, list[str]] = {}
    for path in paths:
        try:
            accepted.append(load_source(path))
        except CatalogueError as exc:
            rejected.setdefault(exc.code, []).append(f"{path.name}: {exc.message}")
    accepted.sort(key=lambda s: s.source_id)
    for names in rejected.values():
        names.sort()
    return tuple(accepted), rejected
