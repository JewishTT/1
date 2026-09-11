"""First-class typed property for the canonical knowledge model (feature 005, US1).

Ported pattern: FollowTheMoney (MIT) `followthemoney/property.py` — a property
with a declared type, original value, and optional confidence. Values are kept
as strings (FtM convention) and validated by the schema registry on admission.

   Source repo : donors/followthemoney (https://github.com/alephdata/followthemoney)
   License     : MIT
   What changed: kept Property semantics; dropped type-cleaning/parsing layers;
                 confidence added for reviewer strength (source: vitni pattern).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Property:
    """A typed, schema-validated attribute of an Entity.

    ``original_value`` is the immutable value as extracted (I-1); ``value`` may
    be the canonical/normalized form. Values are strings (FtM convention) —
    numbers/dates are stored as their canonical string forms.
    """

    name: str
    type: str = "text"
    value: str = ""
    original_value: str = ""
    confidence: float | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("property name is required")
        if self.value is None:
            raise ValueError(f"property {self.name}: value must not be None")

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "value": self.value,
            "original_value": self.original_value or self.value,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Property:
        return cls(
            name=data["name"],
            type=data.get("type", "text"),
            value=data.get("value", ""),
            original_value=data.get("original_value") or data.get("value", ""),
            confidence=data.get("confidence"),
        )