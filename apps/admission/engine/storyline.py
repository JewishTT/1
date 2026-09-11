"""Storyline construction (T031, FR-011, investigator pattern).

Groups assertions into per-subject storylines: an ordered, time-annotated
narrative of what the evidence says about one candidate. Storylines are derived
views over admitted assertions — never a source of truth (I-3/I-4); they feed
the investigation workspace and claim assessment, and stay rebuildable from
evidence/events (I-12).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Storyline:
    storyline_id: str
    subject_id: str
    assertion_ids: list[str] = field(default_factory=list)
    relations: list[str] = field(default_factory=list)
    start: datetime | None = None
    end: datetime | None = None
    claim_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "storyline_id": self.storyline_id,
            "subject_id": self.subject_id,
            "assertion_ids": list(self.assertion_ids),
            "relations": list(self.relations),
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "claim_ids": list(self.claim_ids),
        }


class StorylineBuilder:
    """Builds storylines: one per subject candidate, assertions time-ordered."""

    def build(self, assertions) -> list[Storyline]:
        """assertions: ExtractedAssertion-like objects (subject_candidate_id,
        assertion_id, relation, observed_at) or dicts with the same keys."""
        grouped: dict[str, list] = defaultdict(list)
        for a in assertions:
            subject = self._subject(a)
            grouped[subject].append(a)

        storylines: list[Storyline] = []
        for subject in sorted(grouped):
            items = sorted(grouped[subject], key=self._observed_at)
            times = [self._observed_at(i) for i in items if self._observed_at(i) is not None]
            storyline = Storyline(
                storyline_id="SL-" + uuid.uuid5(uuid.NAMESPACE_OID, subject).hex[:12],
                subject_id=subject,
                assertion_ids=[self._assertion_id(i) for i in items],
                relations=[self._relation(i) for i in items],
                start=min(times) if times else None,
                end=max(times) if times else None,
            )
            storylines.append(storyline)
        return storylines

    @staticmethod
    def _subject(a) -> str:
        if isinstance(a, dict):
            return str(a.get("subject_candidate_id") or "unknown")
        return str(getattr(a, "subject_candidate_id", None) or "unknown")

    @staticmethod
    def _assertion_id(a) -> str:
        if isinstance(a, dict):
            return str(a.get("assertion_id") or "")
        return str(getattr(a, "assertion_id", "") or "")

    @staticmethod
    def _relation(a) -> str:
        if isinstance(a, dict):
            return str(a.get("relation") or "")
        return str(getattr(a, "relation", "") or "")

    @staticmethod
    def _observed_at(a) -> datetime | None:
        if isinstance(a, dict):
            value = a.get("observed_at")
        else:
            value = getattr(a, "observed_at", None)
        return value if isinstance(value, datetime) else None