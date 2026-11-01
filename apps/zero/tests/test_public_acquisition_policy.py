from __future__ import annotations

from zero.harvesters.contracts import ObservationCandidate
from zero.harvest_wave import HarvestWave
from zero.harvesters.transport import DictTransport
from zero.public_policy import allow_public_candidate
from zero.type_detector import InputType, SeedInput, TypeDetector


def _candidate(value: str, kind: str, module: str = "fixture") -> ObservationCandidate:
    return ObservationCandidate(value, kind, 0.8, module, "deterministic fixture")


def test_public_domain_keeps_technical_leads_and_role_mailboxes() -> None:
    seed = TypeDetector().detect("example.org")
    assert allow_public_candidate(seed, _candidate("api.example.org", "domain"))
    assert allow_public_candidate(seed, _candidate("security@example.org", "email"))
    assert allow_public_candidate(
        seed, _candidate("https://github.com/example", "social_profile", "social_link_extractor")
    )


def test_public_profile_suppresses_personal_or_enumerative_outputs() -> None:
    seed = TypeDetector().detect("https://example.org/about")
    blocked = (
        _candidate("+12025550199", "phone", "embedded_contacts"),
        _candidate("alice@example.org", "email", "embedded_contacts"),
        _candidate("whatsapp:12025550199", "presence", "whatsapp_presence"),
        _candidate("2024:private breach", "breach", "email_to_breach"),
        _candidate('"12025550199"', "dork_query", "phone_dorks"),
        _candidate("https://github.com/alice", "social_profile", "social_pattern"),
    )
    assert all(not allow_public_candidate(seed, item) for item in blocked)


def test_public_professional_metadata_is_allowed_only_from_a_url_seed() -> None:
    seed = TypeDetector().detect("https://example.org/about")
    for kind in ("public_name", "public_role", "public_affiliation", "public_organization", "public_document_title"):
        assert allow_public_candidate(seed, _candidate("Public Example", kind))
    name_seed = TypeDetector().detect("Example Person")
    assert not allow_public_candidate(name_seed, _candidate("Minister", "public_role"))


def test_non_public_seed_types_fail_closed() -> None:
    seed = SeedInput("Jane Doe", InputType.NAME, 0.6)
    assert not allow_public_candidate(seed, _candidate("api.example.org", "domain"))


def test_production_filter_removes_personal_leads_before_all_stages() -> None:
    html = (
        "<html><body>"
        "Public desk security@example.org. Personal alice@example.org. Call +12025550199."
        '<a href="https://github.com/example-org">repository</a>'
        "</body></html>"
    )
    wave = HarvestWave(
        transport=DictTransport(bodies={"https://example.org/about": html}),
        max_depth=1,
        enable_enrichment=False,
        candidate_allowed=allow_public_candidate,
    )
    wave.run(["https://example.org/about"])
    for record in wave.stage_records:
        values = [candidate.value for candidate in record.candidates]
        assert "security@example.org" in values or record.stage != "HARVEST"
        assert "alice@example.org" not in values
        assert "12025550199" not in values


def test_public_page_feedback_is_same_origin_and_source_bound() -> None:
    seed = TypeDetector().detect("https://example.org/about")
    allowed = _candidate("https://example.org/official", "public_page_link", "public_document_metadata")
    allowed.raw_fields["parent_url"] = seed.raw_value
    denied = _candidate("https://evil.example.net/collect", "public_page_link", "public_document_metadata")
    denied.raw_fields["parent_url"] = seed.raw_value
    wrong_source = _candidate("https://example.org/official", "public_page_link", "other-module")
    wrong_source.raw_fields["parent_url"] = seed.raw_value
    assert allow_public_candidate(seed, allowed)
    assert not allow_public_candidate(seed, denied)
    assert not allow_public_candidate(seed, wrong_source)


def test_public_page_feedback_wave_stays_on_host_and_keeps_parent_context() -> None:
    from zero.enrichment.feedback import FeedbackLoop
    from zero.harvesters.public_document import PublicDocumentHarvester
    from zero.harvesters.registry import HarvesterRegistry

    root = "https://example.org/about"
    child = "https://example.org/official"
    transport = DictTransport(bodies={
        root: '<html><body><a href="/official">Official</a><a href="https://outside.test/x">outside</a></body></html>',
        child: '<html><head><title>Official public profile</title></head><body></body></html>',
    })
    registry = HarvesterRegistry(max_workers=1)
    registry.register(PublicDocumentHarvester())
    wave = HarvestWave(
        registry=registry,
        transport=transport,
        max_depth=2,
        min_new_seeds=1,
        enable_enrichment=False,
        feedback=FeedbackLoop(kinds=frozenset({"public_page_link"})),
        seed_context={root: {
            "discovery_observation_id": "OBS-SEARCH-1",
            "source_id": "searxng-public",
            "action_ref": "action-1",
        }},
        candidate_allowed=allow_public_candidate,
    )
    summaries = wave.run([root])
    assert [summary.seeds_in for summary in summaries] == [1, 1]
    child_records = [record for record in wave.stage_records if record.seed_value == child]
    assert child_records
    assert all(record.parent_capture_url == root for record in child_records)
    assert all(record.discovery_observation_id == "OBS-SEARCH-1" for record in child_records)
    assert all(record.source_id == "searxng-public" for record in child_records)
