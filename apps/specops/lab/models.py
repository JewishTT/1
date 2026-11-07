"""Data records for the isolated SpecOps Red-Team Lab (Feature 036).

The lab is deliberately a separate vocabulary from the production CI/SpecOps panels:
campaigns, sessions and artifacts here carry a `tenant_id`, a RoE-bound target and an
explicit RoE reference. Nothing in this module may be used as a production acquisition
path; the boundary in `specops.lab.boundary` is what enforces that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LabStatus(StrEnum):
    READY = "ready"
    KILLED = "killed"
    TORN_DOWN = "torn_down"


class CampaignState(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    SENDING = "sending"
    PARTIAL = "partial"
    COMPLETE = "complete"
    REFUSED = "refused"


class SessionState(StrEnum):
    RUNNING = "running"
    STOPPED = "stopped"
    DENIED = "denied"
    EXPIRED = "expired"


class ArtifactKind(StrEnum):
    COOKIE = "cookie"
    TOKEN = "token"
    CREDENTIAL = "credential"
    HEADER = "header"


class FigureStatus(StrEnum):
    MEASURED = "measured"
    DERIVED = "derived"
    UNAVAILABLE = "unavailable"


@dataclass
class LabRecipient:
    address: str
    display: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"address": self.address, "display": self.display}


@dataclass
class Template:
    template_id: str
    tenant_id: str
    name: str
    stages: tuple[str, ...]
    assets: tuple[str, ...]
    variables: dict[str, str]
    provenance: str
    authorized: bool = True
    created_at: str = field(default_factory=now_iso)

    def as_dict(self) -> dict[str, Any]:
        return {
            "template_id": self.template_id,
            "name": self.name,
            "stages": list(self.stages),
            "assets": list(self.assets),
            "variables": dict(self.variables),
            "provenance": self.provenance,
            "authorized": self.authorized,
            "created_at": self.created_at,
        }


@dataclass
class Sender:
    sender_id: str
    tenant_id: str
    name: str
    host: str
    tls: bool
    dns_ready: bool
    credential_ref: str | None
    created_at: str = field(default_factory=now_iso)

    @property
    def ready(self) -> bool:
        return bool(self.tls and self.dns_ready and self.credential_ref)

    @property
    def missing(self) -> list[str]:
        missing: list[str] = []
        if not self.tls:
            missing.append("TLS is not configured")
        if not self.dns_ready:
            missing.append("DNS readiness has not been verified")
        if not self.credential_ref:
            missing.append("credential_ref is missing (no default credential is substituted)")
        return missing

    def as_dict(self) -> dict[str, Any]:
        return {
            "sender_id": self.sender_id,
            "name": self.name,
            "host": self.host,
            "tls": self.tls,
            "dns_ready": self.dns_ready,
            "credential_ref": self.credential_ref,
            "ready": self.ready,
            "missing": self.missing,
            "created_at": self.created_at,
        }


@dataclass
class Campaign:
    campaign_id: str
    tenant_id: str
    name: str
    template_id: str
    sender_id: str | None
    roster: list[LabRecipient]
    attack_mapping: list[str]
    retention_days: int = 30
    scheme: str = "manual"
    state: CampaignState = CampaignState.DRAFT
    roe_id: str | None = None
    assessment_id: str | None = None
    created_at: str = field(default_factory=now_iso)
    launched_at: str | None = None

    def as_dict(self, *, funnel: dict[str, Any], roe_status: str) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "template_id": self.template_id,
            "sender_id": self.sender_id,
            "roster": [r.address for r in self.roster],
            "state": self.state.value,
            "roe_status": roe_status,
            "roe_id": self.roe_id,
            "attack_mapping": list(self.attack_mapping),
            "scheme": self.scheme,
            "launched_at": self.launched_at,
            "assessment_id": self.assessment_id,
            "retention_days": self.retention_days,
            "funnel": funnel,
            "captured_credentials_count": 0,
        }


@dataclass
class AitmSession:
    session_id: str
    tenant_id: str
    mode: str
    target_host: str
    roe_id: str
    retention_hours: int
    retention_expires_at: str
    state: SessionState = SessionState.RUNNING
    started_at: str = field(default_factory=now_iso)
    stopped_at: str | None = None
    artifact_ids: list[str] = field(default_factory=list)

    def as_dict(self, *, roe_status: str = "confirmed") -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "mode": self.mode,
            "target_host": self.target_host,
            "state": self.state.value,
            "roe_status": roe_status,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
            "retention_expires_at": self.retention_expires_at,
            "artifact_ids": list(self.artifact_ids),
        }


@dataclass
class Artifact:
    artifact_id: str
    tenant_id: str
    session_id: str
    kind: ArtifactKind
    label: str
    ciphertext: bytes
    nonce: bytes
    sha256: str
    redacted_preview: str
    captured_at: str
    expires_at: str
    available: bool = True
    access_count: int = 0
    purged_at: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "session_id": self.session_id,
            "kind": self.kind.value,
            "redacted_preview": self.redacted_preview,
            "sha256": self.sha256,
            "captured_at": self.captured_at,
            "expires_at": self.expires_at,
            "available": self.available,
            "access_count": self.access_count,
        }


@dataclass
class Assessment:
    assessment_id: str
    tenant_id: str
    campaign_id: str
    operation_id: str
    created_at: str = field(default_factory=now_iso)

    def as_dict(self) -> dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "campaign_id": self.campaign_id,
            "operation_id": self.operation_id,
            "created_at": self.created_at,
        }


@dataclass
class ReportFigure:
    value: int | None
    status: FigureStatus
    source: str
    missing: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "status": self.status.value,
            "source": self.source,
            "missing": self.missing,
        }


@dataclass
class Report:
    report_id: str
    tenant_id: str
    campaign_id: str
    figures: dict[str, ReportFigure]
    limitations: list[str]
    provenance: list[str]
    redaction: str
    generated_at: str = field(default_factory=now_iso)
    export_digest: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "campaign_id": self.campaign_id,
            "generated_at": self.generated_at,
            "figures": {name: fig.as_dict() for name, fig in self.figures.items()},
            "limitations": list(self.limitations),
            "provenance": list(self.provenance),
            "redaction": self.redaction,
            "export_digest": self.export_digest,
        }
