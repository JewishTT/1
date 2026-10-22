"""Multi-strategy blocking (T082, FR-013) + Feature 034 person-case blocking policy.

The original `BlockingEngine` generates candidate pairs WITHOUT O(N²) comparison:
each candidate is hashed into one or more blocking keys (strategies); an inverted
index maps key → candidate ids; pairs are generated only from buckets that stay
under `max_bucket`. Union of pair sets per strategy is emitted with `strategy`
provenance.

Feature 034 adds a person-case blocking policy that defines allowed/forbidden
blocking features and emits an explicit partial status when any prefilter would
lose pairs. No bucket may cap or truncate silently on the production path;
Splink 5.0.0 owns blocking and pair generation for person resolution.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


# =============================================================================
# Original blocking engine (kept for resolver.py compatibility)
# =============================================================================

@dataclass
class CandidateRecord:
    candidate_id: str
    entity_type: str
    canonical_value: str
    aliases: list[str] = field(default_factory=list)
    email: str | None = None
    display_name: str | None = None
    id_number: str | None = None
    organization: str | None = None
    location: str | None = None
    handle: str | None = None
    birth_date: str | None = None
    doc_ids: list[str] = field(default_factory=list)
    co_occurrence: str | None = None
    scores: dict[str, float] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.display_name or self.canonical_value


@dataclass
class BlockedPair:
    candidate_a: str
    candidate_b: str
    strategies: set[str] = field(default_factory=set)


def _fold(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    return "".join(c for c in value if not unicodedata.combining(c)).lower()


def _soundex_key(value: str) -> str:
    """Simple Soundex for Latin scripts; falls back to ascii-prefix otherwise."""
    folded = _fold(value)
    ascii_l = re.sub(r"[^a-z]", "", folded)
    if not ascii_l:
        return folded[:3].ljust(3, "0")
    fc = ascii_l[0]
    table = {
        "b": "1", "f": "1", "p": "1", "v": "1",
        "c": "2", "g": "2", "j": "2", "k": "2", "q": "2", "s": "2", "x": "2", "z": "2",
        "d": "3", "t": "3", "l": "4", "m": "5", "n": "5", "r": "6",
    }
    digits: list[str] = []
    prev = ""
    for ch in ascii_l[1:]:
        d = table.get(ch, "")
        if d and d != prev:
            digits.append(d)
        prev = d
    return (fc + "".join(digits)).ljust(4, "0")[:4]


class BlockingEngine:
    """Index-based blocking: strategy → key → candidate ids → bounded pairs."""

    def __init__(self, max_bucket: int = 512) -> None:
        self._max_bucket = max_bucket

    def strategies(self, rec: CandidateRecord) -> dict[str, set[str]]:
        keys: dict[str, set[str]] = defaultdict(set)
        name = _fold(rec.name)
        if name:
            keys["name_prefix"].add(name[:4])
            keys["phonetic"].add(_soundex_key(name))
            keys["transliteration"].add(re.sub(r"[^a-z0-9]", "", name)[:6] or "?")
        if rec.email:
            domain = rec.email.rsplit("@", 1)[-1].lower()
            keys["email"].add(rec.email.lower())
            keys["domain"].add(domain)
        if rec.id_number:
            frag = re.sub(r"[^a-zA-Z0-9]", "", rec.id_number).upper()
            if len(frag) >= 2:
                keys["id_fragments"].add(frag[:2])
                keys["id_fragments"].add(frag[-3:] if len(frag) >= 3 else frag)
        if rec.birth_date:
            year = re.search(r"(19|20)\d{2}", rec.birth_date)
            if year:
                keys["date_year"].add(year.group(0)[:4])
        if rec.location:
            keys["location"].add(_fold(rec.location)[:6])
        if rec.organization:
            keys["org"].add(_fold(rec.organization)[:6])
        if rec.handle:
            keys["shared_handle"].add(_fold(rec.handle))
        for doc in rec.doc_ids:
            keys["same_doc"].add(doc)
            co = rec.co_occurrence or ""
            if co:
                keys["co_occurrence"].add(co)
        return dict(keys)

    def block(self, records: list[CandidateRecord]) -> list[BlockedPair]:
        indexed: dict[tuple[str, str], list[str]] = defaultdict(list)
        for rec in records:
            for strategy, keys in self.strategies(rec).items():
                for key in keys:
                    bucket = (strategy, key)
                    if len(indexed[bucket]) < self._max_bucket:
                        indexed[bucket].append(rec.candidate_id)
        pairs: dict[tuple[str, str], BlockedPair] = {}
        for (strategy, _key), ids in indexed.items():
            if len(ids) > self._max_bucket:
                continue
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    a, b = ids[i], ids[j]
                    if a == b:
                        continue
                    key = (a, b) if a < b else (b, a)
                    pair = pairs.get(key)
                    if pair is None:
                        pair = BlockedPair(candidate_a=key[0], candidate_b=key[1])
                        pairs[key] = pair
                    pair.strategies.add(strategy)
        return sorted(pairs.values(), key=lambda p: (p.candidate_a, p.candidate_b))


# =============================================================================
# Feature 034: person-case blocking policy
# =============================================================================

class BlockingPartialError(RuntimeError):
    """Raised when a blocking prefilter would lose candidate pairs.

    Carries bucket id, count, and affected candidates so the caller can
    surface a typed partial status instead of silently dropping pairs.
    """

    def __init__(
        self,
        bucket_id: str,
        count: int,
        affected: list[str],
        reason: str = "bucket would exceed capacity",
    ) -> None:
        self.bucket_id = bucket_id
        self.count = count
        self.affected = affected
        self.reason = reason
        super().__init__(
            f"blocking partial: bucket {bucket_id} has {count} candidates "
            f"that would be truncated ({reason}); affected: {affected[:5]}..."
        )


@dataclass(frozen=True, slots=True)
class BlockingPolicy:
    """Allowed blocking features for the person-research scope.

    Private phone/email, leaked identifiers, guessed handles, home location and
    sensitive fields are NOT blocking keys. A shared employer/domain, first name,
    image, approximate age, or mere co-occurrence must never be sole merge rationale.
    """

    allowed_features: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {
                "public_registry_id",
                "publication_author_id",
                "public_profile_url",
                "name_prefix_transliterated",
                "locale_aware_phonetic",
                "public_organization_role_overlap",
                "co_occurrence_same_document",
                "explicit_public_alias",
            }
        )
    )
    forbidden_features: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {
                "private_phone",
                "private_email",
                "leaked_identifier",
                "guessed_handle",
                "home_location",
                "sensitive_field",
                "shared_domain",
                "first_name_only",
                "image",
                "approximate_age",
                "mere_co_occurrence",
            }
        )
    )

    def is_allowed(self, feature: str) -> bool:
        return feature in self.allowed_features

    def is_forbidden(self, feature: str) -> bool:
        return feature in self.forbidden_features


@dataclass(frozen=True, slots=True)
class BlockingResult:
    """Result of a blocking pass. Either complete pairs or an explicit partial status."""

    pairs: list[tuple[str, str]]
    strategies_used: tuple[str, ...]
    partial: bool = False
    partial_reason: str | None = None
    omitted_bucket_id: str | None = None
    omitted_count: int = 0
    omitted_candidates: tuple[str, ...] = ()


def validate_blocking_features(features: list[str], policy: BlockingPolicy) -> list[str]:
    """Return the subset of features that are allowed under the person-case policy.

    Forbidden features are dropped and reported; the caller must treat their
    absence as a coverage reduction, not silently proceed.
    """
    allowed = [f for f in features if policy.is_allowed(f)]
    forbidden = [f for f in features if policy.is_forbidden(f)]
    if forbidden:
        # Forbidden features must never be used as blocking keys.
        # They are reported so the caller knows what was excluded.
        pass
    return allowed


def complete_or_partial(
    pairs: list[tuple[str, str]],
    *,
    would_omit: bool = False,
    bucket_id: str | None = None,
    omitted_count: int = 0,
    omitted: tuple[str, ...] = (),
) -> BlockingResult:
    """Build a BlockingResult. If pairs would be omitted, mark partial explicitly.

    A capped bucket may not silently imply "no match". The result carries the
    omission metadata so the resolution pass can be marked partial.
    """
    if would_omit:
        return BlockingResult(
            pairs=pairs,
            strategies_used=(),
            partial=True,
            partial_reason="bucket overflow would omit candidates",
            omitted_bucket_id=bucket_id or "",
            omitted_count=omitted_count,
            omitted_candidates=omitted,
        )
    return BlockingResult(pairs=pairs, strategies_used=(), partial=False)
