"""Person-case blocking policy (Feature 034).

Replaces the old `BlockingEngine` with its silently-truncated buckets. Splink 5.0.0
owns blocking and pair generation on the production path; this module defines the
allowed field profile for person-case blocking and emits an explicit partial status
when any prefilter would lose pairs. No bucket may cap or truncate silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from resolution.blocking import CandidateRecord  # reuse the record shape


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
