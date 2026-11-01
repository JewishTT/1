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
