"""SpecOps Red-Team Lab (Feature 036).

The department surface is `api.routes.specops_lab`; the engine is `LabEngine`. Every
action runs through `LabBoundary`, which requires a live lab and a confirmed RoE. The
full Phishing Club donor is reached through the local-service adapter in
`specops.lab.phishingclub`.
"""

from specops.lab.artifacts import ArtifactStore
from specops.lab.audit import AuditEvent, AuditLog
from specops.lab.boundary import (
    AuthorizationRefused,
    CapabilityDisabled,
    EgressDenied,
    ExternalAssetRefused,
    LabBoundary,
    LabError,
    LabNotFound,
    SetupRequired,
    TargetRefused,
    is_valid_identity,
    validate_roster,
)
from specops.lab.engine import LAB, LabEngine
from specops.lab.models import (
    AitmSession,
    Artifact,
    ArtifactKind,
    Assessment,
    Campaign,
    CampaignState,
    FigureStatus,
    LabRecipient,
    LabStatus,
    Report,
    ReportFigure,
    Sender,
    SessionState,
    Template,
    now_iso,
)
from specops.lab.readiness import donor_state, readiness

__all__ = [
    "LAB",
    "AitmSession",
    "Artifact",
    "ArtifactKind",
    "ArtifactStore",
    "Assessment",
    "AuditEvent",
    "AuditLog",
    "AuthorizationRefused",
    "Campaign",
    "CampaignState",
    "CapabilityDisabled",
    "EgressDenied",
    "ExternalAssetRefused",
    "FigureStatus",
    "LabBoundary",
    "LabEngine",
    "LabError",
    "LabNotFound",
    "LabRecipient",
    "LabStatus",
    "Report",
    "ReportFigure",
    "Sender",
    "SessionState",
    "SetupRequired",
    "TargetRefused",
    "Template",
    "donor_state",
    "is_valid_identity",

    "now_iso",

    "readiness",
    "validate_roster",
]
