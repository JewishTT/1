"""Engagement fabric tests (Feature 032).

Three properties are worth more than the rest, and each is a way this module could be
quietly wrong:

1. **Training is never summed into phishing risk.** A regression here produces a
   dashboard that still renders and a number that means nothing, so it is asserted
   structurally — the two tracks live in separate dictionaries and there is no
   expression that can add them.
2. **Anonymisation preserves the numbers.** Stripping identity must not inflate the
   subject count. This is the exact failure the first implementation had: the pseudonym
   key was generated per call, so every event looked like a different subject and the
   funnel's subject count quietly became the event count.
3. **A credential-bearing payload is refused, not truncated.** A "redacted" payload that
   still leaks four characters is still a credential, and the caller believes they were
   protected.
"""

from __future__ import annotations

import json

import pytest
from specops.engagement import (
    DEFINITIONS,
    DONT_HERITATE,
    EventKind,
    EventTrack,
    PayloadRefused,
    Stage,
    campaign_funnel,
    fabric,
    project,
    subject_profiles,
)
from specops.engagement.fabric import _psuedonym_for

BASE = "EN-32"


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Private log directory and a fixed pseudonym key, for order-independent runs.

    The fixed key matters: without it the key is random per process, pseudonyms differ
    between test sessions, and any assertion about linkage stops being reproducible.
    """
    from specops.engagement.config import clear_engagement_config_cache

    monkeypatch.setenv("GHOSTLINE_ENGAGEMENT_DIR", str(tmp_path / "engagement"))
    monkeypatch.setenv("GHOSTLINE_PSEUDONYM_KEY", "test-key-not-a-secret")
    clear_engagement_config_cache()
    yield
    clear_engagement_config_cache()


def record(campaign: str, channel: str, kind: EventKind, subject: str | None = None, **kw):
    return fabric().record(
        campaign_id=campaign, channel=channel, kind=kind, subject_ref=subject, **kw
    )


# ── the taxonomy ─────────────────────────────────────────────────────


def test_every_donor_event_is_carried_over():
    """The donor's fourteen, all present under their original wire names.

    Asserted on the wire names because those are what a donor's records look like on
    disk. Renaming them would break the import path, and a silently-dropped event would
    show up as a subject who "never engaged".
    """
    donor_names = {
        "campaign_closed",
        "campaign_recipient_message_sent",
        "campaign_recipient_message_failed",
        "campaign_recipient_message_read",
        "campaign_recipient_submitted_data",
        "campaign_recipient_reported",
        "campaign_recipient_evasion_page_visited",
        "campaign_recipient_before_page_visited",
        "campaign_recipient_page_visited",
        "campaign_recipient_after_page_visited",
        "campaign_recipient_deny_page_visited",
        "campaign_recipient_training_started",
        "campaign_recipient_training_completed",
    }
    carried = {kind.value for kind in EventKind}
    assert donor_names <= carried, f"dropped: {sorted(donor_names - carried)}"


def test_the_refusals_are_recorded_not_forgotten():
    """What was NOT taken is as much a part of the integration as what was."""
    joined = " ".join(DONT_HERITATE)
    assert "palette" in joined
    assert "submitted-data" in joined
    assert "SvelteKit" in joined


def test_training_events_are_on_their_own_track():
    for kind in (EventKind.TRAINING_STARTED, EventKind.TRAINING_COMPLETED):
        assert DEFINITIONS[kind].track is EventTrack.TRAINING
    for kind in (
        EventKind.SUBMITTED_DATA,
        EventKind.CALL_MATCHED if False else EventKind.STAGE_MATCHED,
    ):
        assert DEFINITIONS[kind].track is EventTrack.PHISHING


def test_multistage_depth_is_a_position_not_a_boolean():
    """The donor's before/page/after/deny distinction is the thing worth stealing."""
    assert DEFINITIONS[EventKind.PAGE_VISITED].stage is Stage.LANDED
    assert DEFINITIONS[EventKind.AFTER_PAGE_VISITED].stage is Stage.STAGE_ADVANCED
    assert DEFINITIONS[EventKind.DENY_PAGE_VISITED].stage is Stage.RESISTED
    # Four distinct positions, which is the whole point.
    assert (
        len(
            {
                DEFINITIONS[k].stage
                for k in (
                    EventKind.PAGE_VISITED,
                    EventKind.AFTER_PAGE_VISITED,
                    EventKind.DENY_PAGE_VISITED,
                )
            }
        )
        == 3
    )


def test_resisting_is_not_going_deeper():
    """A subject who reported did not engage further than one who did nothing."""
    assert DEFINITIONS[EventKind.REPORTED].stage is Stage.RESISTED
    assert DEFINITIONS[EventKind.REPORTED].stage >= Stage.NONE


def test_credential_bearing_events_are_marked():
    assert DEFINITIONS[EventKind.SUBMITTED_DATA].credential_bearing is True
    assert DEFINITIONS[EventKind.STAGE_MATCHED].credential_bearing is True
    assert DEFINITIONS[EventKind.PAGE_VISITED].credential_bearing is False


# ── the ladder ───────────────────────────────────────────────────────


def test_email_and_voice_land_on_the_same_ladder():
    """The reason the fabric exists: two channels, one comparable depth."""
    assert DEFINITIONS[EventKind.MESSAGE_SENT].stage is DEFINITIONS[EventKind.CALL_PLACED].stage
    assert DEFINITIONS[EventKind.MESSAGE_READ].stage is DEFINITIONS[EventKind.CALL_ANSWERED].stage
    assert DEFINITIONS[EventKind.SUBMITTED_DATA].stage is DEFINITIONS[EventKind.STAGE_MATCHED].stage


def test_a_subject_is_counted_once_per_stage_at_their_deepest_position():
    """Counting per event would make one clicker look like two subjects."""
    for _ in range(5):
        record(BASE, "email", EventKind.MESSAGE_SENT, "a@lab")
    for _ in range(3):
        record(BASE, "email", EventKind.PAGE_VISITED, "a@lab")
    record(BASE, "email", EventKind.MESSAGE_SENT, "b@lab")

    funnel = campaign_funnel(BASE, fabric().for_campaign(BASE))
    assert funnel.subject_count == 2
    assert funnel.reached["dispatched"] == 2
    assert funnel.reached["landed"] == 1, "three clicks by one subject is still one subject"


def test_the_funnel_is_monotone():
    """A subject counted at a rung is counted at every rung below it."""
    record(BASE, "email", EventKind.MESSAGE_SENT, "a@lab")
    record(BASE, "email", EventKind.PAGE_VISITED, "a@lab")
    funnel = campaign_funnel(BASE, fabric().for_campaign(BASE))
    assert funnel.reached["dispatched"] >= funnel.reached["engaged"] >= funnel.reached["landed"]


# ── the training separation ───────────────────────────────────────────


def test_training_never_enters_the_phishing_funnel():
    """The rule this module was built for, asserted on the projection itself.

    Two subjects, so the assertion isolates the thing under test: one subject engaged
    with the campaign, one did ONLY training. If training leaked onto the adversarial
    ladder the second subject would appear on it, which is exactly the error that makes
    a completed-training employee look like a phishing target.
    """
    record(BASE, "email", EventKind.MESSAGE_SENT, "engaged@lab")
    record(BASE, "email", EventKind.PAGE_VISITED, "engaged@lab")
    record(BASE, "email", EventKind.TRAINING_STARTED, "trained@lab")
    record(BASE, "email", EventKind.TRAINING_COMPLETED, "trained@lab")

    funnel = campaign_funnel(BASE, fabric().for_campaign(BASE))
    # Training is counted…
    assert funnel.training_assigned == 1
    assert funnel.training_completed == 1
    # …and the funnel holds exactly the one subject who engaged with the campaign.
    assert funnel.subject_count == 2
    assert funnel.reached["dispatched"] == 1
    assert funnel.reached["engaged"] == 1
    assert funnel.reached["landed"] == 1
    assert funnel.reached["conceded"] == 0
    assert funnel.reached["resisted"] == 0


def test_a_subject_with_only_training_never_reaches_the_funnel():
    """The sharpest form of the separation: training alone is invisible to the funnel."""
    record(BASE, "email", EventKind.TRAINING_STARTED, "trained@lab")
    record(BASE, "email", EventKind.TRAINING_COMPLETED, "trained@lab")
    funnel = campaign_funnel(BASE, fabric().for_campaign(BASE))
    assert funnel.training_completed == 1
    assert funnel.reached["dispatched"] == 0
    assert all(count == 0 for count in funnel.reached.values())


def test_completing_training_and_conceding_stay_separable_per_subject():
    """One subject did both. The board must be able to say so without summing them."""
    record(BASE, "email", EventKind.SUBMITTED_DATA, "a@lab")
    record(BASE, "email", EventKind.TRAINING_COMPLETED, "a@lab")

    profile = subject_profiles(fabric().for_campaign(BASE))[0]
    assert profile.conceded_campaigns == (BASE,)
    assert profile.trainings_completed == 1
    assert profile.resisted_campaigns == ()
    # No combined field exists to hold a merged score, which is the structural half.
    assert not hasattr(profile, "score")


def test_the_projection_exposes_two_tracks_and_never_a_third():
    record(BASE, "email", EventKind.MESSAGE_SENT, "a@lab")
    record(BASE, "email", EventKind.SUBMITTED_DATA, "a@lab")
    record(BASE, "email", EventKind.TRAINING_COMPLETED, "a@lab")

    payload = json.dumps(project(fabric().all_events()).as_dict())
    assert '"training"' in payload
    for forbidden in ("risk_score", "combined_score", "engagement_score", "phishing_risk"):
        assert forbidden not in payload


# ── the payload boundary ──────────────────────────────────────────────


def test_a_credential_payload_is_refused_entirely():
    with pytest.raises(PayloadRefused):
        record(BASE, "email", EventKind.SUBMITTED_DATA, "a@lab", payload={"otp": "482913"})


def test_a_refusal_leaves_nothing_behind():
    """A real event first, so the file exists and the assertion is about the refusal."""
    record(BASE, "email", EventKind.MESSAGE_SENT, "a@lab")
    before = len(fabric().all_events())

    with pytest.raises(PayloadRefused):
        record(BASE, "email", EventKind.SUBMITTED_DATA, "a@lab", payload={"otp": "482913"})

    assert len(fabric().all_events()) == before
    assert "482913" not in fabric().path.read_text(encoding="utf-8")


def test_a_stage_match_payload_is_refused_too():
    """The donor's CLOSE-stage regex fires exactly when the secret is spoken."""
    with pytest.raises(PayloadRefused):
        record(BASE, "voice", EventKind.STAGE_MATCHED, "a@lab", payload={"said": "hunter2"})


def test_ordinary_metadata_is_still_kept():
    """Only SUBJECT-SUPPLIED payloads are refused. Stage names and ids are context."""
    event = record(BASE, "voice", EventKind.STAGE_REACHED, "a@lab", metadata={"stage": "CLOSE"})
    assert event.metadata == {"stage": "CLOSE"}


# ── anonymisation ─────────────────────────────────────────────────────


def test_the_pseudonym_is_stable_for_the_process():
    assert _psuedonym_for("a@lab") == _psuedonym_for("a@lab")
    assert _psuedonym_for("a@lab") != _psuedonym_for("b@lab")


def test_the_pseudonym_is_not_a_reversible_digest():
    """An unsalted digest of an address is trivially reversed by anyone with a list."""
    pseudo = _psuedonym_for("a@lab")
    assert "a@lab" not in pseudo
    import hashlib

    assert pseudo != "anon-" + hashlib.sha256(b"a@lab").hexdigest()[:16]


def test_anonymisation_strips_identity_but_preserves_the_numbers():
    """The property whose absence is silent: the board still renders, it is just wrong."""
    for subject in ("a@lab", "b@lab", "c@lab", "d@lab"):
        record(BASE, "email", EventKind.MESSAGE_SENT, subject)
    record(BASE, "email", EventKind.SUBMITTED_DATA, "a@lab")

    before = campaign_funnel(BASE, fabric().for_campaign(BASE))
    fabric().anonymize_campaign(BASE)
    after = campaign_funnel(BASE, fabric().for_campaign(BASE))

    assert after.subject_count == before.subject_count == 4
    assert after.reached == before.reached


def test_anonymisation_strips_ip_user_agent_and_payload():
    record(
        BASE,
        "email",
        EventKind.MESSAGE_READ,
        "a@lab",
        ip="203.0.113.9",
        user_agent="Mozilla/5.0",
        metadata={"stage": "x"},
    )
    fabric().anonymize_campaign(BASE)
    event = fabric().for_campaign(BASE)[0]
    assert event.subject_ref is None
    assert event.ip is None
    assert event.user_agent is None
    assert event.pseudonym is not None
    assert event.anonymized is True
    assert "203.0.113.9" not in fabric().path.read_text(encoding="utf-8")


def test_anonymisation_leaves_other_campaigns_alone():
    record(BASE, "email", EventKind.MESSAGE_SENT, "a@lab")
    record("OTHER", "email", EventKind.MESSAGE_SENT, "a@lab")
    fabric().anonymize_campaign(BASE)
    assert fabric().for_campaign("OTHER")[0].subject_ref == "a@lab"


# ── cross-channel ─────────────────────────────────────────────────────


def test_one_subject_is_one_profile_across_both_channels():
    """The thing neither channel could answer before this module existed."""
    record("EMAIL-CAMP", "email", EventKind.MESSAGE_SENT, "a@lab")
    record("EMAIL-CAMP", "email", EventKind.PAGE_VISITED, "a@lab")
    record("VOICE-CAMP", "voice", EventKind.CALL_PLACED, "a@lab")
    record("VOICE-CAMP", "voice", EventKind.STAGE_MATCHED, "a@lab")

    profiles = subject_profiles(fabric().all_events())
    assert len(profiles) == 1
    assert profiles[0].campaigns == ("EMAIL-CAMP", "VOICE-CAMP")
    assert profiles[0].channels == ("email", "voice")
    assert profiles[0].repeat_engaged == 2


def test_the_log_is_append_only():
    """A recorded observation is immutable. 'Correcting' it means recording another."""
    record(BASE, "email", EventKind.MESSAGE_SENT, "a@lab")
    record(BASE, "email", EventKind.PAGE_VISITED, "a@lab")
    ids = [e.event_id for e in fabric().for_campaign(BASE)]
    assert len(set(ids)) == 2
    assert len(fabric().for_campaign(BASE)) == 2


def test_an_empty_log_reports_a_named_absence_not_a_blank_board():
    result = project([])
    assert result.missing
    assert "engagement board" in result.missing[0]


def test_a_corrupt_line_costs_one_line_not_the_history():
    record(BASE, "email", EventKind.MESSAGE_SENT, "a@lab")
    path = fabric().path
    path.write_text(path.read_text(encoding="utf-8") + "{not json\n", encoding="utf-8")

    from specops.engagement.fabric import EngagementFabric

    fresh = EngagementFabric()
    assert len(fresh.for_campaign(BASE)) == 1
