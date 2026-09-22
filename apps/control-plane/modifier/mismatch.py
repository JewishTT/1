"""Entity/ID mismatch modifier (T094).

The modifier watches observed identifiers and decides whether an entity record
must be created/modified/merged. It is *badge-aware*: identifier badges (email,
handle, phone, domain, crypto address, ...) come with match semantics, and
entity links are deduplicated before any write so one entity can never be
created twice from the same observed identity.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Badge -> case/canonicalization semantics for identity matching.
BADGE_MATCH_SPEC: dict[str, str] = {
    "email": "fold",
    "handle": "fold",
    "domain": "fold",
    "phone": "digits",
    "crypto": "fold",
    "username": "fold",
    "txid": "norm-body",
}


def normalize_value(badge: str, raw: str) -> str:
    """Canonicalize an identifier for a badge before matching."""
    value = (raw or "").strip()
    if not value:
        return value
    if BADGE_MATCH_SPEC.get(badge) == "fold":
        return value.lower()
    if BADGE_MATCH_SPEC.get(badge) == "digits":
        digits = "".join(ch for ch in value if ch.isdigit())
        return digits[-10:] if len(digits) > 10 else digits
    if BADGE_MATCH_SPEC.get(badge) == "norm-body":
        return value
    return value


def badge_match(observed: dict[str, str], known: dict[str, str]) -> dict[str, object]:
    """Compare observed identifier badges against an entity's known identifiers.

    Returns ``matched`` (badges whose canonical values agree), ``mismatched``
    (badges present on both sides with different canonical values) and the
    per-badge ``reasons``.
    """
    matched: dict[str, str] = {}
    mismatched: dict[str, tuple[str, str]] = {}
    reasons: list[str] = []
    badges = sorted(set(observed) | set(known))
    for badge in badges:
        if badge not in BADGE_MATCH_SPEC:
            reasons.append(f"{badge}:no-spec")
        lhs = normalize_value(badge, observed.get(badge, ""))
        rhs = normalize_value(badge, known.get(badge, ""))
        if observed.get(badge) and known.get(badge):
            if lhs and lhs == rhs:
                matched[badge] = lhs
            else:
                mismatched[badge] = (lhs or "<missing>", rhs or "<missing>")
        elif observed.get(badge) and not known.get(badge):
            reasons.append(f"{badge}:new")
        elif known.get(badge) and not observed.get(badge):
            reasons.append(f"{badge}:not-observed")
    return {"matched": matched, "mismatched": mismatched, "reasons": reasons}


@dataclass(frozen=True)
class EntityLink:
    """A candidate entity/probe identity link."""

    entity: str
    identifiers: dict[str, str]
    scores: dict[str, float] = field(default_factory=dict)
    observed_at: str = ""

    def identifiers_by_badge(self, badge: str) -> list[str]:
        return [normalize_value(badge, v) for k, v in self.identifiers.items() if k == badge]


def dedupe_entity_links(
    candidates: list[EntityLink], *, require: str = "any"
) -> list[list[EntityLink]]:
    """Group entity links that share at least one canonical identifier.

    ``require="any"`` groups on any shared badge; ``require="all"`` requires
    every shared badge to agree. Returns disjoint groups preserving input order.
    """
    groups: list[list[EntityLink]] = []

    def shares(a: EntityLink, b: EntityLink) -> bool:
        common_badges = set(a.identifiers).intersection(b.identifiers)
        if not common_badges:
            return False
        for badge in sorted(common_badges):
            a_vals = set(a.identifiers_by_badge(badge))
            b_vals = set(b.identifiers_by_badge(badge))
            overlap = a_vals & b_vals
            if overlap:
                if require == "any":
                    return True
                continue
            if require == "all":
                return False
        return require == "all"

    for candidate in candidates:
        placed = False
        for group in groups:
            if any(shares(candidate, member) for member in group):
                group.append(candidate)
                placed = True
                break
        if not placed:
            groups.append([candidate])
    return groups


def pick_canonical(group: list[EntityLink]) -> EntityLink:
    """Pick the canonical link for a deduped group (highest aggregate score)."""

    def total(link: EntityLink) -> float:
        score = sum(link.scores.values()) if link.scores else 0.0
        bonus = float(len(link.identifiers)) * 0.1
        return score + bonus

    return max(group, key=total)


def modify_urgency(entity: str, links: list[EntityLink]) -> dict[str, object]:
    """Classify a modification request from links claiming the same entity.

    HIGH: conflicting canonical values for one identifier badge across links.
    MEDIUM: same identity (no conflict), but more than one source/link formed it.
    LOW: single link, no change needed.
    """
    if not links:
        return {"entity": entity, "urgency": "MEDIUM", "disposition": "NEW", "links": 0}
    badges = {badge for link in links for badge in link.identifiers}
    conflicts: list[str] = []
    for badge in sorted(badges):
        values = {
            normalize_value(badge, v)
            for link in links
            for k, v in link.identifiers.items()
            if k == badge
        }
        if len(values) > 1:
            conflicts.append(badge)
    if conflicts:
        return {
            "entity": entity,
            "urgency": "HIGH",
            "disposition": "CONFLICT",
            "links": len(links),
            "conflict_badges": conflicts,
        }
    if len({link.entity for link in links}) > 1 or len(links) > 1:
        return {
            "entity": entity,
            "urgency": "MEDIUM",
            "disposition": "MODIFY",
            "links": len(links),
        }
    return {"entity": entity, "urgency": "LOW", "disposition": "UNCHANGED", "links": 1}