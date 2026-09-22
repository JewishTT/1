"""Unit tests for Layer 3 enrichment modules + feedback loop (spec/010 §0.9)."""

from __future__ import annotations

from zero.enrichment.feedback import FeedbackLoop, ZeroLayerSeed
from zero.enrichment.modules import ENRICHERS, run_enrichers
from zero.harvesters.contracts import ObservationCandidate
from zero.type_detector import InputType, SeedInput, TypeDetector


def _seed(value: str) -> SeedInput:
    return TypeDetector().detect(value)


class TestEnricherRegistry:
    def test_at_least_eight_enrichers_registered(self) -> None:
        assert len(ENRICHERS) >= 8

    def test_names_unique_and_sorted(self) -> None:
        names = [e.name for e in ENRICHERS]
        assert len(names) == len(set(names))


class TestReverseEmailUsername:
    def test_email_to_username(self) -> None:
        candidates = run_enrichers(_seed("alice.moon@corp.co"))
        usernames = [c.value for c in candidates if c.kind == "username"]
        assert "alice.moon" in usernames


class TestEmailToBreach:
    def test_mock_breach_hits(self) -> None:
        candidates = run_enrichers(_seed("victim@acme.com"))
        breaches = [c for c in candidates if c.kind == "breach"]
        assert breaches, "acme.com must be in mock breach index"
        assert any("Marriott" in c.value for c in breaches)

    def test_unknown_domain_no_breach(self) -> None:
        candidates = run_enrichers(_seed("victim@not-in-index.io"))
        assert [c for c in candidates if c.kind == "breach"] == []


class TestDomainToDns:
    def _resolver(self, _domain: str) -> dict:
        return {"MX": ["mx1.acme.com", "mx2.acme.com"], "TXT": ["v=spf1 -all"]}

    def test_resolver_injected(self) -> None:
        candidates = run_enrichers(_seed("acme.com"), {"dns_records": self._resolver})
        records = [c for c in candidates if c.kind == "dns_record"]
        values = {c.value for c in records}
        assert "mx1.acme.com" in values
        assert "v=spf1 -all" in values

    def test_without_resolver_no_records(self) -> None:
        assert run_enrichers(_seed("acme.com")) == []


class TestUrlToSocial:
    def test_recognizes_social_host(self) -> None:
        candidates = run_enrichers(_seed("https://github.com/octocat"))
        profiles = [c for c in candidates if c.kind == "social_profile"]
        assert any(c.value.endswith("octocat") for c in profiles)

    def test_non_social_host_ignored(self) -> None:
        candidates = run_enrichers(_seed("https://plain-site.example.com/path"))
        assert all(c.kind != "social_profile" for c in candidates)


class TestPhoneToWhatsapp:
    def test_projects_id(self) -> None:
        candidates = run_enrichers(_seed("+12025550199"))
        presence = [c for c in candidates if c.kind == "presence"]
        assert "whatsapp:12025550199" in {c.value for c in presence}


class TestUsernameToGitHub:
    def test_github_profile(self) -> None:
        candidates = run_enrichers(_seed("octocat"))
        profiles = [c for c in candidates if c.kind == "social_profile"]
        assert "https://github.com/octocat" in {c.value for c in profiles}


class TestNameToEmailPatterns:
    def test_personal_emails_from_name_and_domain(self) -> None:
        candidates = run_enrichers(
            _seed("John Smith"), {"domain": "example.com"}
        )
        emails = [c.value for c in candidates if c.kind == "email"]
        assert "john.smith@example.com" in emails

    def test_without_domain_nothing(self) -> None:
        assert run_enrichers(_seed("John Smith")) == []


class TestEmailToLinkedIn:
    def test_profile_from_local_part(self) -> None:
        candidates = run_enrichers(_seed("jane.doe@corp.co"))
        profiles = [c.value for c in candidates if c.kind == "social_profile"]
        assert "https://linkedin.com/in/jane.doe" in profiles


class TestIpToGeo:
    def test_mock_ip_lookup(self) -> None:
        seed = SeedInput(
            raw_value="8.8.8.8",
            detected_type=InputType.UNKNOWN,
            confidence=0.05,
        )
        candidates = run_enrichers(seed)
        geos = [c for c in candidates if c.kind == "geo"]
        assert any("Mountain View" in c.value for c in geos)


class TestDomainToTechnologies:
    def test_tech_signals_from_injected_html(self) -> None:
        ctx = {"html": '<div class="wp-content">Cloudflare powered React app</div>'}
        candidates = run_enrichers(_seed("acme.com"), ctx)
        techs = {c.value for c in candidates if c.kind == "technology"}
        assert {"WordPress", "Cloudflare", "React"}.issubset(techs)

    def test_no_html_no_tech(self) -> None:
        assert all(c.kind != "technology" for c in run_enrichers(_seed("acme.com")))


class TestSocialToInfluencerScore:
    def test_proxy_score(self) -> None:
        candidates = run_enrichers(_seed("some_long_username_here"))
        scores = [c for c in candidates if c.kind == "influence_score"]
        assert scores and float(scores[0].value) <= 1.0


# ---------------------------------------------------------------------------
# feedback loop
# ---------------------------------------------------------------------------


class TestFeedbackLoop:
    def _candidates(self) -> list[ObservationCandidate]:
        return [
            ObservationCandidate("victim@acme.com", "email", 0.8, "mail", "m"),
            ObservationCandidate("alice", "username", 0.9, "social", "m"),
            ObservationCandidate("+12025550199", "phone", 0.7, "phone", "m"),
            ObservationCandidate("https://example.com", "url", 0.6, "url", "m"),
            ObservationCandidate("noise thing that is unknown", "name", 0.5, "x", "m"),
            ObservationCandidate("victim@acme.com", "email", 0.8, "dup", "m"),
        ]

    def test_new_seeds_dedup_and_redetect(self) -> None:
        loop = FeedbackLoop()
        seeds = loop.new_seeds(self._candidates())
        values = {s.derived_value for s in seeds}
        assert "victim@acme.com" in values
        assert "alice" in values
        assert len(values) == len(seeds)

    def test_seen_seed_suppressed(self) -> None:
        loop = FeedbackLoop()
        first = loop.new_seeds(self._candidates())
        second = loop.new_seeds(
            self._candidates(), seen={f"{s.derived_type.value}:{s.derived_value}" for s in first}
        )
        assert second == []

    def test_derived_type_reasserted(self) -> None:
        loop = FeedbackLoop()
        seeds = loop.new_seeds(self._candidates())
        email_seed = next(s for s in seeds if s.derived_type is InputType.EMAIL)
        assert email_seed.reason.startswith("from email candidate")

    def test_emit_without_producer_is_noop(self) -> None:
        loop = FeedbackLoop()
        seeds = loop.new_seeds(self._candidates())
        assert loop.emit(seeds) == []

    def test_emit_with_mock_producer(self) -> None:
        calls: list[tuple[str, str]] = []

        class Producer:
            def produce(self, topic: str, envelope, key: str = "") -> None:
                calls.append((topic, key))

        loop = FeedbackLoop()
        seeds = loop.new_seeds(self._candidates())
        keys = loop.emit(seeds, producer=Producer())
        assert len(keys) == len(seeds)
        assert all(topic == "zero_layer.feedback_seeds" for topic, _ in calls)


class TestZeroLayerSeedEntity:
    def test_seed_fields(self) -> None:
        seed = ZeroLayerSeed(
            derived_value="bob@x.co",
            derived_type=InputType.EMAIL,
            confidence=0.6,
            reason="harvest",
            source_module="email_permutation",
            original_seed_id="seed-abc",
        )
        assert seed.derived_value == "bob@x.co"
        assert seed.confidence == 0.6