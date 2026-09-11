"""Statement-level provenance value-class — adapted from FollowTheMoney (MIT).

Source: donors/followthemoney/followthemoney/statement/statement.py.
Changes: removed rigour/sqlalchemy/followthemoney couplings; ``prop_type`` made
an optional plain string; ``BASE_ID`` = "id"; keep deterministic ``make_key``
(sha1 over ``dataset.entity.prop.value[@lang][.ext]``) unchanged — IDs must stay
stable because they are used for dedup across datasets (attribute source clause:
"Never change entity ID generation"). Docstrings trimmed to COGNITIVE usage.
"""

from __future__ import annotations

import hashlib
import warnings
from typing import Any, Self, TypedDict, TypeGuard

UNSET = object()

BASE_ID = "id"

NON_LANG_TYPE_NAMES = ("date", "number", "url", "email", "phone")


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def is_not_unset(value: str | None | object) -> TypeGuard[str | None]:
    return value is not UNSET


class StatementDict(TypedDict):
    id: str | None
    entity_id: str
    canonical_id: str
    prop: str
    schema: str
    value: str
    dataset: str
    lang: str | None
    original_value: str | None
    external: bool
    first_seen: str | None
    last_seen: str | None
    origin: str | None


class Statement:
    """A single statement about a property relevant to an entity.

    "In dataset A, entity X has the property `name` set to 'John Smith'. I first
    observed this at K, and last saw it at L." Original_value is preserved as
    immutable (I-1); dataset is the provenance boundary for reprint collapse.
    """

    BASE = BASE_ID

    __slots__ = [
        "_dataset",
        "_entity_id",
        "_external",
        "_lang",
        "_prop",
        "_schema",
        "_value",
        "canonical_id",
        "first_seen",
        "id",
        "last_seen",
        "origin",
        "original_value",
        "prop_type",
    ]

    def __init__(
        self,
        entity_id: str,
        prop: str,
        schema: str,
        value: str,
        dataset: str,
        lang: str | None = None,
        original_value: str | None = None,
        first_seen: str | None = None,
        external: bool = False,
        id: str | None = None,
        canonical_id: str | None = None,
        last_seen: str | None = None,
        origin: str | None = None,
    ) -> None:
        self._entity_id = entity_id
        self.canonical_id = canonical_id or entity_id
        self._prop = prop
        self._schema = schema
        self.prop_type = None
        self._value = value
        self._dataset = dataset

        if lang is not None and self.prop_type in NON_LANG_TYPE_NAMES:
            lang = None
        self._lang = lang

        if not original_value or original_value == value:
            original_value = None
        self.original_value = original_value
        self.first_seen = first_seen
        self.last_seen = last_seen or first_seen
        self._external = external
        self.origin = origin
        if id is None:
            id = self.generate_key()
        self.id = id

    @property
    def entity_id(self) -> str:
        """The (original) ID of the entity this statement is about."""
        return self._entity_id

    @property
    def dataset(self) -> str:
        """The dataset this statement was observed in."""
        return self._dataset

    @property
    def prop(self) -> str:
        """The property name this statement is about."""
        return self._prop

    @property
    def schema(self) -> str:
        """The schema of the entity this statement is about."""
        return self._schema

    @property
    def value(self) -> str:
        """The value of the property captured by this statement."""
        return self._value

    @property
    def lang(self) -> str | None:
        """The language of the property value, if applicable."""
        return self._lang

    @property
    def external(self) -> bool:
        """Whether this statement was observed in an external dataset."""
        return self._external

    def to_dict(self) -> StatementDict:
        return {
            "canonical_id": self.canonical_id,
            "entity_id": self._entity_id,
            "prop": self._prop,
            "schema": self._schema,
            "value": self._value,
            "dataset": self._dataset,
            "lang": self._lang,
            "original_value": self.original_value,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "external": self._external,
            "origin": self.origin,
            "id": self.id,
        }

    def to_csv_row(self) -> dict[str, str | None]:
        data = dict(self.to_dict())
        data["external"] = _bool_text(self._external)
        data["prop_type"] = self.prop_type
        return data

    def to_db_row(self) -> dict[str, Any]:
        data = dict(self.to_dict())
        data["prop_type"] = self.prop_type
        return data

    def __hash__(self) -> int:
        if self.id is None:
            warnings.warn(
                "Hashing a statement without an ID results in undefined behaviour",
                RuntimeWarning,
                stacklevel=2,
            )
        return hash(self.id)

    def __repr__(self) -> str:
        return f"<Statement({self._entity_id!r}, {self._prop!r}, {self._value!r})>"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Statement):
            return False
        return self.id == other.id

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Statement):
            return NotImplemented
        self_key = (self._prop != BASE_ID, self.id or "")
        other_key = (other._prop != BASE_ID, other.id or "")
        return self_key < other_key

    def clone(
        self: Self,
        *,
        entity_id: str | None = None,
        prop: str | None = None,
        schema: str | None = None,
        value: str | None = None,
        dataset: str | None = None,
        lang: str | None | object = UNSET,
        original_value: str | None | object = UNSET,
        first_seen: str | None | object = UNSET,
        external: bool | None = None,
        canonical_id: str | None = None,
        last_seen: str | None | object = UNSET,
        origin: str | None | object = UNSET,
    ) -> Self:
        """Make a deep copy of the statement, overriding the given fields."""
        lang_v = lang if is_not_unset(lang) else self._lang
        ov = original_value if is_not_unset(original_value) else self.original_value
        fs = first_seen if is_not_unset(first_seen) else self.first_seen
        ls = last_seen if is_not_unset(last_seen) else self.last_seen
        origin_v = origin if is_not_unset(origin) else self.origin
        if external is None:
            external = self._external
        if canonical_id is None and self._entity_id != self.canonical_id:
            canonical_id = self.canonical_id

        stmt_id = self.id
        if entity_id is not None and entity_id != self.entity_id:
            stmt_id = None
        if prop is not None and prop != self._prop:
            stmt_id = None
        if schema is not None and schema != self._schema:
            stmt_id = None
        if value is not None and value != self._value:
            stmt_id = None
        if dataset is not None and dataset != self._dataset:
            stmt_id = None
        if external != self._external:
            stmt_id = None
        if lang_v != self._lang:
            stmt_id = None
        return type(self)(
            id=stmt_id,
            entity_id=entity_id or self._entity_id,
            prop=prop or self._prop,
            schema=schema or self._schema,
            value=value or self._value,
            dataset=dataset or self._dataset,
            lang=lang_v,
            original_value=ov,
            first_seen=fs,
            external=external,
            canonical_id=canonical_id,
            last_seen=ls,
            origin=origin_v,
        )

    def generate_key(self) -> str | None:
        return self.make_key(
            self._dataset,
            self._entity_id,
            self._prop,
            self._value,
            self._external,
            lang=self._lang,
        )

    @classmethod
    def make_key(
        cls,
        dataset: str,
        entity_id: str,
        prop: str | None,
        value: str | None,
        external: bool | None,
        lang: str | None = None,
    ) -> str | None:
        """Hash the key properties of a statement record to make a unique ID."""
        if prop is None or value is None:
            return None
        if lang is None:
            key = f"{dataset}.{entity_id}.{prop}.{value}"
        else:
            key = f"{dataset}.{entity_id}.{prop}.{value}@{lang}"
        if external:
            key = f"{key}.ext"
        return hashlib.sha1(key.encode("ascii", "ignore")).hexdigest()

    @classmethod
    def from_dict(cls, data: StatementDict) -> Self:
        return cls(
            entity_id=data["entity_id"],
            prop=data["prop"],
            schema=data["schema"],
            value=data["value"],
            dataset=data["dataset"],
            lang=data.get("lang", None),
            original_value=data.get("original_value", None),
            first_seen=data.get("first_seen", None),
            external=data.get("external", False),
            id=data.get("id", None),
            canonical_id=data.get("canonical_id", None),
            last_seen=data.get("last_seen", None),
            origin=data.get("origin", None),
        )