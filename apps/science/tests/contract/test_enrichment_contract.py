"""Contract: enrichment knows what it tried, and only the truth about that (spec 026).

The platform's job for an entity is not to answer once. It is to pull until there is nothing
left to pull, and to be exact about the difference between "we asked and there was nothing",
"we could not ask", and "we did not think to ask".

Collapsing those three is how an engine reports itself finished while holding nothing, so the
properties below are the difference between a working enrichment loop and a green dashboard.

**Saturation is measured over the expected surface.** Held attributes alone would score an
entity the platform knows nothing about as 0 unknown — and therefore saturated — stopping the
loop before a single fetch. That bug is why the first version of `plan_enrichment` returned
``saturated: True`` for an empty profile with six outstanding gaps.

**A refusal is not a gap.** It is reported as a capability limitation so the loop does not
retry forever, and it never downgrades an acquired value.

**Conflict is symmetric.** Two sources disagreeing reach ``CONFLICT`` in either arrival order,
because last-write-wins makes the answer depend on ingestion order.

**Corroboration counts independence groups.** Two outlets running one wire story are one
source of evidence however many URLs carry it (ADR-0036).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from context.enrichment import (
    AttributeState,
    CapabilityOffer,
    Coverage,
    EntityProfile,
    merge_offer,
    plan_enrichment,
)

pytestmark = pytest.mark.contract

OFFERS = [
    CapabilityOffer("crt_sh", ("domain",), ("certificate", "subdomain")),
    CapabilityOffer("rdap", ("domain",), ("registrar", "registrant")),
    CapabilityOffer("vt", ("domain",), ("reputation",), key_env="VT_API_KEY"),
    CapabilityOffer("whatweb", ("domain",), ("technology",), binary="whatweb"),
    CapabilityOffer("otx", ("domain", "ip"), ("pulse_count",)),
    CapabilityOffer("generic", (), ("anything",)),
]


class TestCoverageStates:
    def test_a_value_makes_it_acquired(self) -> None:
        state = merge_offer(AttributeState("registrar"), source_id="rdap", values=["Cloudflare"])
        assert state.coverage is Coverage.ACQUIRED
        assert state.values == ("Cloudflare",)

    def test_a_source_that_found_nothing_is_evidence_of_absence(self) -> None:
        # EMPTY is not UNKNOWN. Re-running a source that already answered cannot help.
        state = merge_offer(AttributeState("registrar"), source_id="rdap", values=[])
        assert state.coverage is Coverage.EMPTY
        assert state.coverage.needs_work is False

    def test_absence_does_not_erase_a_value(self) -> None:
        first = merge_offer(AttributeState("x"), source_id="a", values=["1"])
        after = merge_offer(first, source_id="b", values=[])
        assert after.values == ("1",)
        assert after.coverage is Coverage.ACQUIRED

    def test_a_refusal_is_not_a_value_and_not_a_gap(self) -> None:
        state = merge_offer(AttributeState("reputation"), source_id="vt", refused=True)
        assert state.coverage is Coverage.REFUSED
        assert state.coverage.needs_work is False
        assert not state.values

    def test_a_refusal_never_downgrades_an_acquired_value(self) -> None:
        held = merge_offer(AttributeState("x"), source_id="a", values=["1"])
        assert merge_offer(held, source_id="b", refused=True).coverage is Coverage.ACQUIRED

    def test_a_refusal_never_upgrades_absence(self) -> None:
        empty = merge_offer(AttributeState("x"), source_id="a", values=[])
        assert merge_offer(empty, source_id="b", refused=True).coverage is Coverage.EMPTY

    def test_only_unknown_generates_work(self) -> None:
        assert Coverage.UNKNOWN.needs_work is True
        for state in (Coverage.ACQUIRED, Coverage.EMPTY, Coverage.REFUSED, Coverage.CONFLICT):
            assert state.needs_work is False, state

    def test_conflict_does_not_schedule_a_retry(self) -> None:
        # Re-running a source that already disagreed resolves nothing; a conflict needs a
        # discriminating test, which is a different primitive.
        assert Coverage.CONFLICT.needs_work is False


class TestConflictIsSymmetric:
    def _disagree(self, order: tuple[str, str]) -> AttributeState:
        state = AttributeState("owner")
        for source in order:
            value = {"a": "Alice", "b": "Bob"}[source]
            state = merge_offer(state, source_id=source, values=[value])
        return state

    def test_both_orders_reach_conflict(self) -> None:
        forward = self._disagree(("a", "b"))
        backward = self._disagree(("b", "a"))
        assert forward.coverage is Coverage.CONFLICT
        assert backward.coverage is Coverage.CONFLICT
        assert forward.values == backward.values == ("Alice", "Bob")

    def test_agreement_stays_acquired_and_records_the_second_source(self) -> None:
        state = merge_offer(AttributeState("o"), source_id="a", values=["Alice"])
        agreed = merge_offer(state, source_id="b", values=["Alice"])
        assert agreed.coverage is Coverage.ACQUIRED
        assert agreed.sources == ("a", "b")

    def test_the_sources_are_sorted_so_a_diff_means_something(self) -> None:
        state = merge_offer(AttributeState("o"), source_id="z", values=["1"])
        state = merge_offer(state, source_id="a", values=["1"])
        assert state.sources == ("a", "z")


class TestPlanning:
    def _plan(self, **kwargs):
        return plan_enrichment(EntityProfile("REF-1", "domain"), OFFERS, **kwargs)

    def test_an_empty_profile_is_not_saturated(self) -> None:
        # The defect this suite exists for: measured over held attributes alone, an entity
        # we know nothing about scored 0 unknown and stopped the loop before any fetch.
        plan = self._plan(available={"vt": False})
        assert plan.saturation.is_saturated is False
        assert plan.saturation.ratio == 0.0

    def test_saturation_counts_the_expected_surface(self) -> None:
        # Every attribute any offer declares for a domain -- certificate, subdomain,
        # registrar, registrant, reputation, technology, pulse_count, anything -- whether or
        # not we currently hold it.
        plan = self._plan(available={"vt": False})
        assert plan.saturation.total_attributes == 8
        assert plan.saturation.unknown == 8

    def test_the_expected_surface_is_what_the_offers_declare(self) -> None:
        expected = {a for o in OFFERS if o.applies_to("domain") for a in o.attributes}
        plan = self._plan(available={"vt": False})
        assert {g.attribute for g in plan.gaps} == expected

    def test_gaps_are_ordered_by_attribute(self) -> None:
        plan = self._plan(available={"vt": False})
        names = [g.attribute for g in plan.gaps]
        assert names == sorted(names)

    def test_two_identical_plans_are_identical(self) -> None:
        assert self._plan(available={"vt": False}).as_dict() == (
            self._plan(available={"vt": False}).as_dict()
        )

    def test_a_keyed_source_without_a_credential_is_blocked_not_scheduled(self) -> None:
        plan = self._plan(available={"vt": False})
        reputation = next(g for g in plan.gaps if g.attribute == "reputation")
        assert reputation.candidate_sources == ()
        assert reputation.blocked_sources == ("vt",)

    def test_a_missing_binary_is_blocked_not_scheduled(self) -> None:
        plan = self._plan(available={"vt": False})
        technology = next(g for g in plan.gaps if g.attribute == "technology")
        assert technology.candidate_sources == ()
        assert technology.blocked_sources == ("whatweb",)

    def test_a_credential_present_unblocks_the_source(self) -> None:
        plan = self._plan(available={"vt": True})
        reputation = next(g for g in plan.gaps if g.attribute == "reputation")
        assert reputation.candidate_sources == ("vt",)
        assert reputation.blocked_sources == ()

    def test_an_offer_only_applies_to_its_entity_kinds(self) -> None:
        person = plan_enrichment(EntityProfile("REF-2", "person"), OFFERS)
        assert all(
            "crt_sh" not in g.candidate_sources for g in person.gaps
        ), "источник доменов не должен предлагаться для человека"

    def test_an_offer_without_kinds_applies_everywhere(self) -> None:
        # A source that names no kinds is claiming to be general; making it re-declare per
        # kind would silently under-enrich every new entity type.
        person = plan_enrichment(EntityProfile("REF-2", "person"), OFFERS)
        assert any("generic" in g.candidate_sources for g in person.gaps)

    def test_a_resolved_attribute_leaves_the_gap_list(self) -> None:
        profile = EntityProfile("REF-1", "domain")
        profile.attributes["registrar"] = merge_offer(
            AttributeState("registrar"), source_id="rdap", values=["Cloudflare"]
        )
        plan = plan_enrichment(profile, OFFERS, available={"vt": False})
        assert "registrar" not in {g.attribute for g in plan.gaps}


class TestSaturation:
    def _filled(self) -> EntityProfile:
        profile = EntityProfile("REF-1", "domain")
        for name, value in (
            ("certificate", "crt.sh cert"),
            ("subdomain", "www.example.com"),
            ("registrar", "Cloudflare"),
            ("registrant", "Example Inc"),
        ):
            profile.attributes[name] = merge_offer(
                AttributeState(name), source_id="s", values=[value]
            )
        return profile

    def test_it_ratios_resolved_over_expected(self) -> None:
        plan = plan_enrichment(self._filled(), OFFERS, available={"vt": False})
        assert plan.saturation.total_attributes == 8
        assert plan.saturation.acquired == 4
        assert plan.saturation.unknown == 4  # reputation, technology, pulse_count, anything
        assert round(plan.saturation.ratio, 2) == 0.5

    def test_it_is_not_saturated_while_attributes_are_unattempted(self) -> None:
        plan = plan_enrichment(self._filled(), OFFERS, available={"vt": False})
        assert plan.saturation.is_saturated is False

    def test_saturated_and_thinly_evidenced_are_distinguishable(self) -> None:
        # Everything reachable is filled, each from one source: nothing left to attempt, and
        # nothing corroborated. Reporting saturation as coverage would hide the second fact.
        profile = self._filled()
        for offer in OFFERS:
            if not offer.applies_to("domain"):
                continue
            for name in offer.attributes:
                if name in profile.attributes:
                    continue
                profile.attributes[name] = merge_offer(
                    AttributeState(name), source_id=offer.source_id, values=["v"]
                )
        plan = plan_enrichment(profile, OFFERS, available={"vt": False})
        assert plan.saturation.unknown == 0
        assert plan.saturation.is_saturated is True
        assert plan.saturation.corroborated == 0

    def test_corroboration_counts_independence_groups(self) -> None:
        profile = self._filled()
        profile.attributes["registrar"] = merge_offer(
            profile.attributes["registrar"], source_id="wire2", values=["Cloudflare"]
        )
        assert profile.attributes["registrar"].coverage is Coverage.ACQUIRED
        syndicated = plan_enrichment(
            profile, OFFERS, available={"vt": False},
            source_groups={"s": "G1", "wire2": "G1"},
        )
        assert syndicated.saturation.corroborated == 0
        assert syndicated.saturation.distinct_sources >= 2

        independent = plan_enrichment(
            profile, OFFERS, available={"vt": False},
            source_groups={"s": "G1", "wire2": "G2"},
        )
        assert independent.saturation.corroborated >= 1

    def test_an_empty_plan_ratios_to_zero_rather_than_dividing_by_zero(self) -> None:
        empty = plan_enrichment(EntityProfile("REF-x", "unheard-of-kind"), [])
        assert empty.saturation.ratio == 1.0  # nothing wanted, nothing owed
        assert empty.has_work is False


class TestProfileReads:
    def test_known_returns_only_attributes_with_values(self) -> None:
        profile = EntityProfile("REF-1", "domain")
        profile.attributes["a"] = merge_offer(AttributeState("a"), source_id="s", values=["1"])
        profile.attributes["b"] = merge_offer(AttributeState("b"), source_id="s", values=[])
        assert profile.known() == ("a",)

    def test_unresolved_includes_unknown_and_refused(self) -> None:
        profile = EntityProfile("REF-1", "domain")
        profile.attributes["a"] = merge_offer(AttributeState("a"), source_id="s", refused=True)
        profile.attributes["b"] = merge_offer(AttributeState("b"), source_id="s", values=[])
        assert profile.unresolved() == ("a",)

    def test_value_returns_the_first_value_or_the_default(self) -> None:
        profile = EntityProfile("REF-1", "domain")
        profile.attributes["a"] = merge_offer(AttributeState("a"), source_id="s", values=["x", "y"])
        assert profile.value("a") == "x"
        assert profile.value("missing", "fallback") == "fallback"

    def test_the_profile_serialises_deterministically(self) -> None:
        left = EntityProfile("REF-1", "domain")
        right = EntityProfile("REF-1", "domain")
        for profile, order in ((left, ("z", "a")), (right, ("a", "z"))):
            for name in order:
                profile.attributes[name] = merge_offer(
                    AttributeState(name), source_id="s", values=["v"]
                )
        assert left.as_dict() == right.as_dict()


class TestOpenVocabulary:
    def test_a_type_the_platform_has_never_heard_of_is_still_planned_for(self) -> None:
        # The engine carries no domain names. An entity of an unknown kind is enriched by
        # exactly the same code as a domain.
        alien = plan_enrichment(EntityProfile("REF-a", "wetlands-lease"), OFFERS)
        assert alien.has_work
        assert all(g.entity_ref == "REF-a" for g in alien.gaps)

    def test_an_attribute_nobody_declared_is_not_invented(self) -> None:
        profile = EntityProfile("REF-1", "domain")
        plan = plan_enrichment(profile, OFFERS, available={"vt": False})
        assert all(
            g.attribute in {a for offer in OFFERS for a in offer.attributes}
            for g in plan.gaps
        ), "планировщик не должен изобретать атрибуты, которых нет ни в одном предложении"