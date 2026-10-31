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
    The upstream HTTP cache key is ``sha256(METHOD \\\\0 URL \\\\0 BODY)``. 72 of the source
    definitions put their query in ``tool.params`` rather than in the URL, which made the
    key constant across every query. :func:`_flatten_params` folds the params into the URL
    at load time, so the cache key cannot collide, and the executor needs no knowledge of
    where the query lived.

``pagination`` is absent from the schema
    The legacy corpus had no explicit provider pagination declarations; the schema now accepts bounded page/offset declarations.
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
    #: The runtime that executes this source, or "" when the ordinary HTTP/system path
    #: handles it. Absent until now, which left three things broken at once: the context
    #: engine's catalogue bridge filtered every descriptor out because it read this and got
    #: "", ``AcquisitionTask.to_task`` had no way to name a runtime, and the connector
    #: registry's explicit-runtime branch was unreachable because no task could ever set
    #: the key it reads.
    #:
    #: Optional rather than required because 151 of the existing sources genuinely run
    #: through the HTTP or system executor. Making it mandatory would mean inventing a
    #: ``runtime_ref`` for sources that have none, which is the kind of fiction that later
    #: reads as a routing decision.
    runtime_ref: str = ""
    #: Cost class for planning. "cheap" is the honest default: a source that never declared
    #: one has not been shown to be expensive, and claiming otherwise would bias selection
    #: against it.
    cost_class: str = "cheap"
    #: Connector configuration for a runtime-backed source, verbatim from the definition.
    #: Passed through untouched so the runtime owns the meaning of its own config keys.
    runtime_config: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)
    definition: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)
    #: FR-014: this source's declared ability to find a thing it was asked to look for,
    #: as a fraction in [0, 1]. **``None`` means the source has never declared one**, and
    #: that is the only safe default -- every one of the 151 sources that never say so
    #: is genuinely unquantified, and a default of 1.0 would certify all of them as
    #: exhaustive searches.
    #:
    #: The field exists because a zero-result from an undeclared source is
    #: ``INFORMATIONAL_ONLY`` and may not become a qualified absence (contract 03 rule 2,
    #: contract 07 ``DETECTION_POWER_UNKNOWN``). Without a place to *declare* the power,
    #: the only way for a caller to reach a qualified absence is to write the number at
    #: the point where it is trying to justify a negative finding -- which is the wrong
    #: place for a measurement and the reason absences get manufactured.
    #:
    #: ``None`` is not the same as ``0.0``: a declared zero is a source that has said it
    #: cannot see into this corpus, and a declared zero is informative in a way that an
    #: unmeasured one is not.
    detection_power: float | None = None
    #: How ``detection_power`` was established. Absent alongside a ``None`` power; required
    #: alongside a number, so a bare float is never read as a measurement (U3's rule about
    #: numbers without semantics, applied to source declarations).
    detection_power_method: str = ""
    #: Source independence family and temporal basis are explicit provenance fields,
    #: not inferred from the runtime name or URL. A raw-first capture path refuses a
    #: definition that does not declare an acceptable family.
    source_family: str = ""
    time_basis: str = ""

    def __post_init__(self) -> None:
        if self.detection_power is None:
            if self.detection_power_method:
                raise CatalogueError(
                    "detection_power_without_value",
                    f"{self.source_id} declares how its detection power was measured but not "
                    "the value itself; a method with no number constrains nothing",
                )
            return
        if not 0.0 <= float(self.detection_power) <= 1.0:
            raise CatalogueError(
                "detection_power_out_of_range",
                f"{self.source_id} declares detection_power={self.detection_power!r}; a power "
                "outside [0, 1] is not a measurement (FR-014)",
            )
        if not str(self.detection_power_method).strip():
            raise CatalogueError(
                "detection_power_without_method",
                f"{self.source_id} declares detection_power={self.detection_power!r} with no "
                "method. A number a reader cannot re-check is a number they cannot contest",
            )

    @property
    def may_support_qualified_absence(self) -> bool:
        """Whether a zero-result from this source can underwrite an absence claim.

        False for every source that has not declared a detection power, with no
        exceptions and no regard for how good its coverage looks. This is the single
        check FR-014 turns on.
        """
        return self.detection_power is not None

    @property
    def is_runtime_backed(self) -> bool:
        return bool(self.runtime_ref)

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
            # Present so a consumer can tell "runs on no named runtime" from "the field
            # was never populated". Omitting the key entirely would make the two
            # indistinguishable over HTTP.
            "runtime_ref": self.runtime_ref,
            "cost_class": self.cost_class,
            # Present and possibly null so a consumer can tell "this source declares no
            # detection power" from "the field was never populated" -- the first is a
            # fact about the source and the second is a fact about the loader. Over HTTP
            # the two are otherwise indistinguishable, and only the first is FR-014's
            # subject.
            "detection_power": self.detection_power,
            "detection_power_method": self.detection_power_method,
            "may_support_qualified_absence": self.may_support_qualified_absence,
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


def _derive_pagination(
    tool: Mapping[str, Any], declared: Mapping[str, Any] | None = None
) -> Pagination:
    """Read a bounded page strategy, preferring an explicit source declaration.

    Inference remains for common page/offset cases. Explicit metadata supports APIs
    whose offset parameter has a provider-specific name (for example, start).
    Cursor pagination is rejected until the executor can follow opaque next-page
    tokens without guessing their semantics.
    """
    if tool.get("binary"):
        return Pagination()  # a local tool runs once
    if declared:
        strategy = str(declared.get("strategy") or "").strip().lower()
        if strategy not in {"page", "offset"}:
            raise CatalogueError(
                "pagination_strategy_unsupported",
                f"explicit pagination strategy {strategy!r} is not supported by the HTTP executor",
            )
        param = str(declared.get("param") or "").strip()
        try:
            page_size = int(declared.get("page_size") or 0)
            max_pages = int(declared.get("max_pages") or 1)
        except (TypeError, ValueError) as exc:
            raise CatalogueError(
                "pagination_config_invalid",
                "explicit pagination page_size and max_pages must be integers",
            ) from exc
        if not param or page_size < 1 or max_pages < 1 or max_pages > 100:
            raise CatalogueError(
                "pagination_config_invalid",
                "explicit pagination requires a param, positive page_size, and max_pages in [1, 100]",
            )
        return Pagination(
            strategy=strategy,
            param=param,
            page_size=page_size,
            max_pages=max_pages,
            inferred=False,
        )
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
    # A credential *pair* is as valid a way to name a secret as a single one: WiGLE
    # authenticates with an API name plus an API token over HTTP Basic, and no single
    # env var can hold both. `basic_auth_env` names the pair; without this the
    # validator rejected a correctly-declared source (issue #45).
    basic_auth_env = _as_tuple((tool or {}).get("basic_auth_env"))
    if requires_key and not key_env and not basic_auth_env:
        raise CatalogueError(
            "keyed_source_without_key_env",
            f"{name} requires a key but names neither key_env nor basic_auth_env, "
            "so it cannot be run",
        )
    if basic_auth_env and len(basic_auth_env) != 2:
        raise CatalogueError(
            "bad_basic_auth_env",
            f"{name} names {len(basic_auth_env)} basic_auth_env variables, expected 2",
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
        pagination=_derive_pagination(
            tool,
            raw.get("pagination") if isinstance(raw.get("pagination"), Mapping) else None,
        ),
        parser_is_identity=parser in IDENTITY_PARSERS,
        source_path=str(path),
        logs_queries=bool(raw.get("logs_queries", False)),
        runtime_ref=str(raw.get("runtime_ref") or "").strip(),
        cost_class=str(raw.get("cost_class") or "cheap"),
        runtime_config=dict(raw.get("runtime_config") or {}),
        definition=dict(raw),
        detection_power=_declared_detection_power(raw),
        detection_power_method=str(raw.get("detection_power_method") or "").strip(),
        source_family=str(raw.get("source_family") or "").strip(),
        time_basis=str(raw.get("time_basis") or "").strip(),
    )


def _declared_detection_power(raw: Mapping[str, Any]) -> float | None:
    """Read a declared detection power, or ``None`` when there is not one.

    ``None`` is the honest answer for every source whose definition does not declare
    one, and it is deliberately not coerced to a number anywhere in this path: a source
    that never said what it would have found has not said it, and the difference between
    "declared zero" and "never declared" is the difference between a known blind spot and
    an unmeasured one.
    """
    value = raw.get("detection_power")
    if value is None or value == "":
        return None
    return float(value)


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
    seen: dict[str, str] = {}
    for path in paths:
        try:
            definition = load_source(path)
        except CatalogueError as exc:
            rejected.setdefault(exc.code, []).append(f"{path.name}: {exc.message}")
            continue
        # Two files declaring one name collide on source_id, and the registry would
        # silently keep whichever sorted last -- a source vanishing with no error.
        # The catalogue had exactly this: hunter_email in both 08_knowledge and
        # 16_people. Report it instead of overwriting.
        previous = seen.get(definition.source_id)
        if previous is not None:
            rejected.setdefault("duplicate_source_id", []).append(
                f"{path.name}: {definition.name} already defined by {previous}"
            )
            continue
        seen[definition.source_id] = path.name
        accepted.append(definition)
    accepted.sort(key=lambda s: s.source_id)
    for names in rejected.values():
        names.sort()
    return tuple(accepted), rejected
