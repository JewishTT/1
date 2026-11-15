"""Engagement fabric (Feature 032): one lifecycle for every SpecOps channel.

The CI/SpecOps department had two live channels and no shared record. Email counted
``sent / opened / clicked / submitted``; voice counted ``placed / outcome``. Neither
could answer "who engaged, how deep, in what order", because they counted in different
currencies — so comparing a phishing campaign against a voice drill produced two
unrelated numbers.

Harvested from ``donors/phishingclub`` (AGPL-3.0): its fourteen-event lifecycle, its
multi-stage depth model, its separation of training compliance from phishing risk, and
its anonymisation-by-pseudonym. What was refused — their palette, their SvelteKit
frontend, their submitted-data storage — is listed in ``taxonomy.DONT_HERITATE``.

``taxonomy``  the closed event vocabulary and the shared stage ladder
``fabric``    the append-only, anonymisable event log
``funnel``    the projection, and the training separation it enforces structurally
``config``    where the log lives, which is the retention question
"""

from specops.engagement.config import clear_engagement_config_cache, engagement_dir, events_path
from specops.engagement.fabric import (
    EngagementEvent,
    EngagementFabric,
    PayloadRefused,
    fabric,
)
from specops.engagement.funnel import (
    CampaignFunnel,
    FunnelResult,
    SubjectProfile,
    campaign_funnel,
    project,
    subject_profiles,
)
from specops.engagement.taxonomy import (
    DEFINITIONS,
    DONT_HERITATE,
    FUNNEL_STAGES,
    EventKind,
    EventTrack,
    Stage,
    event_display_name,
    is_credential_bearing,
    position_in_funnel,
    track_of,
)

__all__ = [
    "CampaignFunnel",
    "DEFINITIONS",
    "DONT_HERITATE",
    "EngagementEvent",
    "EngagementFabric",
    "EventKind",
    "EventTrack",
    "FUNNEL_STAGES",
    "FunnelResult",
    "PayloadRefused",
    "Stage",
    "SubjectProfile",
    "campaign_funnel",
    "clear_engagement_config_cache",
    "engagement_dir",
    "event_display_name",
    "events_path",
    "fabric",
    "is_credential_bearing",
    "position_in_funnel",
    "project",
    "subject_profiles",
    "track_of",
]
