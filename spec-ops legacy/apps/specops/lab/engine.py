"""The Red-Team Lab engine.

The engine owns campaigns, templates, senders, AiTM sessions, artifacts, assessments and
reports. It is deliberately process-local: the boundary, the audit chain and the
engagement fabric are the durable/authoritative pieces, and this increment does not
pretend an in-memory dict is a database. Every mutating method checks the boundary and
the RoE gate before it does anything.
"""

from __future__ import annotations

import hashlib
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from specops.engagement import EventKind, campaign_funnel, fabric, subject_profiles
from specops.emulation import REGISTRY as EMULATION
from specops.roe.gate import REGISTRY as ROE
from specops.roe.gate import require_confirmed_roe

from specops.lab.artifacts import ArtifactStore
from specops.lab.audit import AuditLog
from specops.lab.boundary import (
    AuthorizationRefused,
    LabBoundary,
    LabNotFound,
    SetupRequired,
    TargetRefused,
    validate_roster,
)
from specops.lab.models import (
    AitmSession,
    ArtifactKind,
    Assessment,
    Campaign,
    CampaignState,
    FigureStatus,
    LabRecipient,
    Report,
    ReportFigure,
    Sender,
    SessionState,
    Template,
    now_iso,
)
from specops.lab.readiness import readiness

DEFAULT_TEMPLATE = "tpl-lure"
DEFAULT_SENDER = "snd-lab"


def _tenant(ctx: Any) -> str:
    return getattr(ctx, "tenant_id", None) or "default-tenant"


def _actor(ctx: Any) -> str:
    return getattr(ctx, "user_id", None) or "system"


def _corr(correlation_id: str) -> str:
    return correlation_id or f"corr-{uuid.uuid4().hex[:10]}"


class LabEngine:
    def __init__(
        self,
        *,
        boundary: LabBoundary | None = None,
        audit: AuditLog | None = None,
        artifacts: ArtifactStore | None = None,
        records: Any | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self.audit = audit or AuditLog()
        self.boundary = boundary or LabBoundary(self.audit)
        self.artifacts = artifacts or ArtifactStore(self.audit)
        self._records = records or fabric()
        self._campaigns: dict[str, Campaign] = {}
        self._operation_tenants: dict[str, str] = {}
        self._templates: dict[tuple[str, str], Template] = {}
        self._senders: dict[tuple[str, str], Sender] = {}
        self._sessions: dict[str, AitmSession] = {}
        self._assessments: dict[str, Assessment] = {}
        self._reports: dict[tuple[str, str], Report] = {}

    # ── seed ────────────────────────────────────────────────────────────

    def _ensure_seed(self, tenant_id: str) -> None:
        key = (tenant_id, DEFAULT_TEMPLATE)
        if key not in self._templates:
            self._templates[key] = Template(
                template_id=DEFAULT_TEMPLATE,
                tenant_id=tenant_id,
                name="Synthetic multi-stage lure",
                stages=("landing", "training"),
                assets=(
                    "lab://specops-lab.local/lure/landing.html",
                    "lab://specops-lab.local/lure/training.html",
                ),
                variables={"first_name": "Lab", "campaign": "Q4"},
                provenance="synthetic",
            )
        sender_key = (tenant_id, DEFAULT_SENDER)
        if sender_key not in self._senders:
            self._senders[sender_key] = Sender(
                sender_id=DEFAULT_SENDER,
                tenant_id=tenant_id,
                name="Lab SMTP",
                host="specops-lab.local",
                tls=True,
                dns_ready=True,
                credential_ref="vault://lab/smtp",
            )

    # ── helpers ─────────────────────────────────────────────────────────

    def _get_campaign(self, tenant_id: str, campaign_id: str) -> Campaign:
        campaign = self._campaigns.get(campaign_id)
        if campaign is None or campaign.tenant_id != tenant_id:
            raise LabNotFound("campaign not found")
        return campaign

    def _get_template(self, tenant_id: str, template_id: str) -> Template:
        template = self._templates.get((tenant_id, template_id))
        if template is None:
            raise TargetRefused(f"template {template_id!r} is not in the lab catalog")
        return template

    def _get_sender(self, tenant_id: str, sender_id: str) -> Sender:
        sender = self._senders.get((tenant_id, sender_id))
        if sender is None:
            raise SetupRequired(f"sender {sender_id!r} is not registered")
        return sender

    def _get_session(self, tenant_id: str, session_id: str) -> AitmSession:
        session = self._sessions.get(session_id)
        if session is None or session.tenant_id != tenant_id:
            raise LabNotFound("session not found")
        return session

    def _require_ready(self) -> None:
        self.boundary.require_ready()

    def _roe_status(self, campaign: Campaign) -> str:
        if not campaign.roe_id:
            return "unconfirmed"
        roe = ROE.get(campaign.roe_id) if ROE is not None else None
        return roe.status().value if roe is not None else "unconfirmed"

    def _funnel(self, campaign_id: str) -> dict[str, Any]:
        result = campaign_funnel(campaign_id, self._records.for_campaign(campaign_id))
        counts = result.event_counts
        return {
            "sent": counts.get(EventKind.MESSAGE_SENT.value, 0),
            "opened": counts.get(EventKind.MESSAGE_READ.value, 0),
            "clicked": counts.get(EventKind.PAGE_VISITED.value, 0),
            "reported": counts.get(EventKind.REPORTED.value, 0),
            "submitted": 0,
            "training": {
                "assigned": result.training_assigned,
                "completed": result.training_completed,
            },
            "subject_count": result.subject_count,
            "source": "derived",
        }

    def _campaign_view(self, campaign: Campaign) -> dict[str, Any]:
        return campaign.as_dict(funnel=self._funnel(campaign.campaign_id), roe_status=self._roe_status(campaign))

    def _expire_sessions(self) -> None:
        current = datetime.now(timezone.utc)
        with self._lock:
            for session in self._sessions.values():
                if session.state is SessionState.RUNNING and datetime.fromisoformat(
                    session.retention_expires_at
                ) <= current:
                    session.state = SessionState.EXPIRED
                    session.stopped_at = now_iso()

    def _engagement(self, tenant_id: str) -> dict[str, Any]:
        campaigns = [c for c in self._campaigns.values() if c.tenant_id == tenant_id]
        events = [event for c in campaigns for event in self._records.for_campaign(c.campaign_id)]
        counts: dict[str, int] = {}
        for event in events:
            counts[event.kind.value] = counts.get(event.kind.value, 0) + 1
        training_assigned = 0
        training_completed = 0
        for campaign in campaigns:
            result = campaign_funnel(campaign.campaign_id, self._records.for_campaign(campaign.campaign_id))
            training_assigned += result.training_assigned
            training_completed += result.training_completed
        return {
            "channel_funnel": {
                "sent": counts.get(EventKind.MESSAGE_SENT.value, 0),
                "opened": counts.get(EventKind.MESSAGE_READ.value, 0),
                "clicked": counts.get(EventKind.PAGE_VISITED.value, 0),
                "reported": counts.get(EventKind.REPORTED.value, 0),
            },
            "training": {"assigned": training_assigned, "completed": training_completed},
            "subjects": len(subject_profiles(events)),
            "anonymized": bool(events) and all(event.anonymized for event in events),
        }

    # ── overview ────────────────────────────────────────────────────────

    def overview(self, ctx: Any) -> dict[str, Any]:
        tenant_id = _tenant(ctx)
        self._ensure_seed(tenant_id)
        self.artifacts.purge_expired()
        self._expire_sessions()
        with self._lock:
            campaigns = [c for c in self._campaigns.values() if c.tenant_id == tenant_id]
            templates = [t for (ten, _), t in self._templates.items() if ten == tenant_id]
            senders = [s for (ten, _), s in self._senders.items() if ten == tenant_id]
            sessions = [s for s in self._sessions.values() if s.tenant_id == tenant_id]
            reports = [r for (ten, _), r in self._reports.items() if ten == tenant_id]
        campaign_views = [self._campaign_view(c) for c in sorted(campaigns, key=lambda c: c.created_at, reverse=True)]
        session_views = [s.as_dict(roe_status=self._roe_status_for_roe(s.roe_id)) for s in sorted(sessions, key=lambda s: s.started_at, reverse=True)]
        artifacts = [
            self.artifacts.view(a.artifact_id, tenant_id=tenant_id, actor=_actor(ctx), correlation_id="overview")
            for s in sessions
            for a in self.artifacts.for_session(s.session_id, tenant_id=tenant_id)
        ]
        plans = EMULATION.plans() if EMULATION is not None else []
        readiness_view = readiness(
            lab=self.boundary.view(),
            key_status=self.artifacts.key_status(),
            emulation_plans=len(plans),
            counts={
                "campaigns": len(campaigns),
                "templates": len(templates),
                "senders": len(senders),
                "sessions": len(sessions),
                "artifacts": len(artifacts),
                "reports": len(reports),
            },
        )
        return {
            "lab": self.boundary.view(),
            "readiness": readiness_view,
            "campaigns": campaign_views,
            "templates": [t.as_dict() for t in sorted(templates, key=lambda t: t.created_at)],
            "senders": [s.as_dict() for s in sorted(senders, key=lambda s: s.created_at)],
            "sessions": session_views,
            "artifacts": artifacts,
            "reports": [r.as_dict() for r in sorted(reports, key=lambda r: r.generated_at, reverse=True)],
            "operations": self._operation_views(tenant_id),
            "engagement": self._engagement(tenant_id),
            "audit": [row.as_dict() for row in self.audit.rows(limit=25, tenant_id=tenant_id)],
        }

    def _roe_status_for_roe(self, roe_id: str | None) -> str:
        if not roe_id:
            return "unconfirmed"
        roe = ROE.get(roe_id) if ROE is not None else None
        return roe.status().value if roe is not None else "unconfirmed"

    # ── catalog ─────────────────────────────────────────────────────────

    def create_template(
        self,
        ctx: Any,
        *,
        name: str,
        stages: list[str],
        assets: list[str],
        variables: dict[str, str] | None = None,
        correlation_id: str = "",
    ) -> dict[str, Any]:
        tenant_id = _tenant(ctx)
        self._ensure_seed(tenant_id)
        if not name.strip():
            raise TargetRefused("template name is empty")
        if not stages:
            raise TargetRefused("a template needs at least one stage")
        for asset in assets:
            self.boundary.validate_asset(
                asset, tenant_id=tenant_id, actor=_actor(ctx), correlation_id=correlation_id
            )
        template = Template(
            template_id=f"tpl-{uuid.uuid4().hex[:8]}",
            tenant_id=tenant_id,
            name=name.strip(),
            stages=tuple(stage.strip() for stage in stages if stage.strip()),
            assets=tuple(assets),
            variables=dict(variables or {}),
            provenance="synthetic",
        )
        with self._lock:
            self._templates[(tenant_id, template.template_id)] = template
        self.audit.append(
            tenant_id=tenant_id,
            actor=_actor(ctx),
            action="template.created",
            object_type="template",
            object_id=template.template_id,
            correlation_id=_corr(correlation_id),
            detail={"stages": len(template.stages), "assets": len(template.assets)},
        )
        return template.as_dict()

    def create_sender(
        self,
        ctx: Any,
        *,
        name: str,
        host: str,
        tls: bool,
        dns_ready: bool,
        credential_ref: str | None,
        correlation_id: str = "",
    ) -> dict[str, Any]:
        tenant_id = _tenant(ctx)
        self._ensure_seed(tenant_id)
        normalised = self.boundary.validate_host(host)
        sender = Sender(
            sender_id=f"snd-{uuid.uuid4().hex[:8]}",
            tenant_id=tenant_id,
            name=name.strip() or normalised,
            host=normalised,
            tls=bool(tls),
            dns_ready=bool(dns_ready),
            credential_ref=(credential_ref or None),
        )
        with self._lock:
            self._senders[(tenant_id, sender.sender_id)] = sender
        self.audit.append(
            tenant_id=tenant_id,
            actor=_actor(ctx),
            action="sender.created",
            object_type="sender",
            object_id=sender.sender_id,
            correlation_id=_corr(correlation_id),
            detail={"host": sender.host, "ready": sender.ready, "missing": sender.missing},
        )
        return sender.as_dict()

    # ── campaigns ───────────────────────────────────────────────────────

    def create_campaign(
        self,
        ctx: Any,
        *,
        name: str,
        template_id: str = DEFAULT_TEMPLATE,
        sender_id: str | None = DEFAULT_SENDER,
        roster: list[str],
        attack_mapping: list[str] | None = None,
        retention_days: int = 30,
        correlation_id: str = "",
    ) -> dict[str, Any]:
        tenant_id = _tenant(ctx)
        self._ensure_seed(tenant_id)
        self._require_ready()
        if not name.strip():
            raise TargetRefused("campaign name is empty")
        if not roster:
            raise TargetRefused("roster is empty; a campaign needs at least one lab identity")
        validate_roster(roster)
        template = self._get_template(tenant_id, template_id)
        sender: Sender | None = None
        if sender_id:
            sender = self._get_sender(tenant_id, sender_id)
            if not sender.ready:
                raise SetupRequired(
                    f"sender {sender.sender_id} is not ready: {'; '.join(sender.missing)}"
                )
        if not 1 <= retention_days <= 365:
            raise TargetRefused("retention_days must be between 1 and 365")
        campaign = Campaign(
            campaign_id=f"cmp-{uuid.uuid4().hex[:10]}",
            tenant_id=tenant_id,
            name=name.strip(),
            template_id=template.template_id,
            sender_id=sender.sender_id if sender else None,
            roster=[LabRecipient(address=address.strip()) for address in roster],
            attack_mapping=list(attack_mapping or []),
            retention_days=retention_days,
        )
        with self._lock:
            self._campaigns[campaign.campaign_id] = campaign
        self.audit.append(
            tenant_id=tenant_id,
            actor=_actor(ctx),
            action="campaign.created",
            object_type="campaign",
            object_id=campaign.campaign_id,
            correlation_id=_corr(correlation_id),
            detail={
                "roster_size": len(campaign.roster),
                "template_id": template.template_id,
                "sender_id": campaign.sender_id,
            },
        )
        return self._campaign_view(campaign)

    def launch_campaign(
        self,
        ctx: Any,
        *,
        campaign_id: str,
        roe_id: str,
        correlation_id: str = "",
    ) -> dict[str, Any]:
        tenant_id = _tenant(ctx)
        self._require_ready()
        with self._lock:
            campaign = self._get_campaign(tenant_id, campaign_id)
            if campaign.state is CampaignState.COMPLETE:
                return self._campaign_view(campaign)
            validate_roster([r.address for r in campaign.roster])
            require_confirmed_roe(ROE.get(roe_id) if ROE is not None else None)
            if campaign.sender_id:
                sender = self._get_sender(tenant_id, campaign.sender_id)
                if not sender.ready:
                    raise SetupRequired(
                        f"sender {sender.sender_id} is not ready: {'; '.join(sender.missing)}"
                    )
            campaign.state = CampaignState.SENDING
            campaign.roe_id = roe_id
            sent = 0
            for index, recipient in enumerate(campaign.roster):
                self._records.record(
                    campaign_id=campaign.campaign_id,
                    channel="email",
                    kind=EventKind.MESSAGE_SENT,
                    subject_ref=recipient.address,
                    metadata={"lab": self.boundary.lab_id, "synthetic": True},
                )
                self._records.record(
                    campaign_id=campaign.campaign_id,
                    channel="email",
                    kind=EventKind.MESSAGE_READ,
                    subject_ref=recipient.address,
                    metadata={"lab": self.boundary.lab_id, "synthetic": True},
                )
                if index < len(campaign.roster) - 1:
                    self._records.record(
                        campaign_id=campaign.campaign_id,
                        channel="email",
                        kind=EventKind.PAGE_VISITED,
                        subject_ref=recipient.address,
                        metadata={"lab": self.boundary.lab_id, "synthetic": True, "stage": "landing"},
                    )
                sent += 1
            campaign.state = CampaignState.COMPLETE
            campaign.launched_at = now_iso()
            view = self._campaign_view(campaign)
        self.audit.append(
            tenant_id=tenant_id,
            actor=_actor(ctx),
            action="campaign.launched",
            object_type="campaign",
            object_id=campaign_id,
            correlation_id=_corr(correlation_id),
            detail={"roe_id": roe_id, "sent": sent},
        )
        return view

    def list_campaigns(self, ctx: Any) -> list[dict[str, Any]]:
        tenant_id = _tenant(ctx)
        self._ensure_seed(tenant_id)
        with self._lock:
            campaigns = [c for c in self._campaigns.values() if c.tenant_id == tenant_id]
        return [self._campaign_view(c) for c in sorted(campaigns, key=lambda c: c.created_at, reverse=True)]

    def get_campaign(self, ctx: Any, campaign_id: str) -> dict[str, Any]:
        return self._campaign_view(self._get_campaign(_tenant(ctx), campaign_id))

    # ── AiTM ────────────────────────────────────────────────────────────

    def start_session(
        self,
        ctx: Any,
        *,
        mode: str,
        target_host: str,
        roe_id: str,
        retention_hours: int = 24,
        correlation_id: str = "",
    ) -> dict[str, Any]:
        tenant_id = _tenant(ctx)
        self._require_ready()
        if mode not in {"reverse_proxy", "remote_browser"}:
            raise TargetRefused("mode must be reverse_proxy or remote_browser")
        if not 1 <= retention_hours <= 720:
            raise TargetRefused("retention_hours must be between 1 and 720")
        host = self.boundary.validate_host(target_host)
        require_confirmed_roe(ROE.get(roe_id) if ROE is not None else None)
        expires = (datetime.now(timezone.utc) + timedelta(hours=retention_hours)).isoformat()
        session = AitmSession(
            session_id=f"aitm-{uuid.uuid4().hex[:10]}",
            tenant_id=tenant_id,
            mode=mode,
            target_host=host,
            roe_id=roe_id,
            retention_hours=retention_hours,
            retention_expires_at=expires,
        )
        with self._lock:
            self._sessions[session.session_id] = session
        self.audit.append(
            tenant_id=tenant_id,
            actor=_actor(ctx),
            action="session.started",
            object_type="session",
            object_id=session.session_id,
            correlation_id=_corr(correlation_id),
            detail={
                "mode": mode,
                "target_host": host,
                "roe_id": roe_id,
                "retention_hours": retention_hours,
            },
        )
        return session.as_dict()

    def list_sessions(self, ctx: Any) -> list[dict[str, Any]]:
        tenant_id = _tenant(ctx)
        self._expire_sessions()
        with self._lock:
            sessions = [s for s in self._sessions.values() if s.tenant_id == tenant_id]
        return [
            s.as_dict(roe_status=self._roe_status_for_roe(s.roe_id))
            for s in sorted(sessions, key=lambda s: s.started_at, reverse=True)
        ]

    def get_session(self, ctx: Any, session_id: str) -> dict[str, Any]:
        self._expire_sessions()
        session = self._get_session(_tenant(ctx), session_id)
        return session.as_dict(roe_status=self._roe_status_for_roe(session.roe_id))

    def capture(
        self,
        ctx: Any,
        *,
        session_id: str,
        kind: str,
        secret: str,
        label: str = "",
        correlation_id: str = "",
    ) -> dict[str, Any]:
        tenant_id = _tenant(ctx)
        self._require_ready()
        session = self._get_session(tenant_id, session_id)
        if session.state is not SessionState.RUNNING:
            raise AuthorizationRefused(f"session {session_id} is {session.state.value}; capture is refused")
        try:
            artifact_kind = ArtifactKind(kind)
        except ValueError as exc:
            raise TargetRefused(f"unknown artifact kind {kind!r}") from exc
        artifact = self.artifacts.capture(
            tenant_id=tenant_id,
            session_id=session_id,
            kind=artifact_kind,
            secret=secret,
            label=label,
            retention_hours=session.retention_hours,
            actor=_actor(ctx),
            correlation_id=_corr(correlation_id),
        )
        with self._lock:
            session.artifact_ids.append(artifact.artifact_id)
        self.audit.append(
            tenant_id=tenant_id,
            actor=_actor(ctx),
            action="session.capture",
            object_type="session",
            object_id=session_id,
            correlation_id=_corr(correlation_id),
            detail={"artifact_id": artifact.artifact_id, "kind": artifact_kind.value},
        )
        return self.artifacts.view(
            artifact.artifact_id,
            tenant_id=tenant_id,
            actor=_actor(ctx),
            correlation_id=_corr(correlation_id),
        )

    def stop_session(self, ctx: Any, session_id: str, *, correlation_id: str = "") -> dict[str, Any]:
        tenant_id = _tenant(ctx)
        session = self._get_session(tenant_id, session_id)
        if session.state is SessionState.RUNNING:
            session.state = SessionState.STOPPED
            session.stopped_at = now_iso()
            self.audit.append(
                tenant_id=tenant_id,
                actor=_actor(ctx),
                action="session.stopped",
                object_type="session",
                object_id=session_id,
                correlation_id=_corr(correlation_id),
                detail={"evidence_preserved": True},
            )
        return session.as_dict(roe_status=self._roe_status_for_roe(session.roe_id))

    # ── operations / assessments ────────────────────────────────────────

    def _operation_views(self, tenant_id: str) -> list[dict[str, Any]]:
        if EMULATION is None:
            return []
        return [
            self._operation_view(op)
            for op in EMULATION.operations()
            if self._operation_tenants.get(op.operation_id) == tenant_id
        ]

    def _operation_view(self, op: Any) -> dict[str, Any]:
        return {
            "operation_id": op.operation_id,
            "plan_id": op.plan_id,
            "lab_fixture": op.lab_fixture,
            "roe_status": "confirmed",
            "state": op.state,
            "abilities": op.abilities,
            "started_at": op.started_at,
            "halted_reason": op.halted_reason,
        }

    def launch_operation(
        self,
        ctx: Any,
        *,
        plan_id: str,
        lab_fixture: str,
        roe_id: str,
        correlation_id: str = "",
    ) -> dict[str, Any]:
        tenant_id = _tenant(ctx)
        self._require_ready()
        if EMULATION is None:
            raise SetupRequired("Caldera/AEL emulation registry is unavailable")
        require_confirmed_roe(ROE.get(roe_id) if ROE is not None else None)
        plan = EMULATION.plan(plan_id)
        if plan is None:
            raise LabNotFound("plan not found")
        if lab_fixture not in {plan.lab_fixture, "specops/lab-target"}:
            raise TargetRefused(
                f"lab fixture {lab_fixture!r} is not the lab target; only specops/lab-target is allowed",
                rejected=[lab_fixture],
            )
        op = EMULATION.create(plan, roe_id)
        self._operation_tenants[op.operation_id] = tenant_id
        self.audit.append(
            tenant_id=tenant_id,
            actor=_actor(ctx),
            action="operation.started",
            object_type="operation",
            object_id=op.operation_id,
            correlation_id=_corr(correlation_id),
            detail={"plan_id": plan_id, "lab_fixture": lab_fixture, "roe_id": roe_id},
        )
        return self._operation_view(op)

    def link_assessment(
        self,
        ctx: Any,
        *,
        campaign_id: str,
        operation_id: str,
        correlation_id: str = "",
    ) -> dict[str, Any]:
        tenant_id = _tenant(ctx)
        campaign = self._get_campaign(tenant_id, campaign_id)
        if (
            EMULATION is None
            or EMULATION.get(operation_id) is None
            or self._operation_tenants.get(operation_id) != tenant_id
        ):
            raise LabNotFound("operation not found")
        assessment = Assessment(
            assessment_id=f"asm-{uuid.uuid4().hex[:10]}",
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            operation_id=operation_id,
        )
        campaign.assessment_id = assessment.assessment_id
        with self._lock:
            self._assessments[assessment.assessment_id] = assessment
        self.audit.append(
            tenant_id=tenant_id,
            actor=_actor(ctx),
            action="assessment.linked",
            object_type="assessment",
            object_id=assessment.assessment_id,
            correlation_id=_corr(correlation_id),
            detail={"campaign_id": campaign_id, "operation_id": operation_id},
        )
        return assessment.as_dict()

    # ── reports ─────────────────────────────────────────────────────────

    def generate_report(self, ctx: Any, campaign_id: str, *, correlation_id: str = "") -> dict[str, Any]:
        tenant_id = _tenant(ctx)
        campaign = self._get_campaign(tenant_id, campaign_id)
        launched = campaign.launched_at is not None
        funnel = self._funnel(campaign_id)
        missing_launch = None if launched else "campaign has not launched; no engagement events recorded"
        sources = {
            "sent": EventKind.MESSAGE_SENT.value,
            "opened": EventKind.MESSAGE_READ.value,
            "clicked": EventKind.PAGE_VISITED.value,
            "reported": EventKind.REPORTED.value,
        }
        figures: dict[str, ReportFigure] = {}
        for name, event_kind in sources.items():
            figures[name] = (
                ReportFigure(int(funnel[name]), FigureStatus.DERIVED, f"engagement:{event_kind}")
                if launched
                else ReportFigure(None, FigureStatus.UNAVAILABLE, "engagement", missing_launch)
            )
        figures["training_completed"] = (
            ReportFigure(
                int(funnel["training"]["completed"]),
                FigureStatus.MEASURED,
                "engagement:campaign_recipient_training_completed",
            )
            if launched
            else ReportFigure(None, FigureStatus.UNAVAILABLE, "engagement", missing_launch)
        )
        captured_credentials = sum(
            1
            for session in self._sessions.values()
            if session.tenant_id == tenant_id
            for artifact in self.artifacts.for_session(session.session_id, tenant_id=tenant_id)
            if artifact.kind is ArtifactKind.CREDENTIAL
        )
        figures["captured_credentials"] = ReportFigure(
            captured_credentials,
            FigureStatus.MEASURED,
            "lab:encrypted-artifact-store",
            None,
        )
        if campaign.assessment_id:
            assessment = self._assessments.get(campaign.assessment_id)
            op = (
                EMULATION.get(assessment.operation_id)
                if assessment
                and EMULATION is not None
                and self._operation_tenants.get(assessment.operation_id) == tenant_id
                else None
            )
            if op is None:
                figures["operation_abilities"] = ReportFigure(
                    None, FigureStatus.UNAVAILABLE, "emulation:operation", "linked operation is not readable"
                )
            else:
                figures["operation_abilities"] = ReportFigure(
                    len(op.abilities), FigureStatus.MEASURED, f"emulation:{op.operation_id}"
                )
        else:
            figures["operation_abilities"] = ReportFigure(
                None, FigureStatus.UNAVAILABLE, "emulation:operation", "no linked operation"
            )
        report = Report(
            report_id=f"rpt-{uuid.uuid4().hex[:10]}",
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            figures=figures,
            limitations=[
                "RoE-bound red-team activity; targets require a confirmed sign-off",
                "Phishing Club donor is served through the local HTTP adapter",
            ],
            provenance=[
                f"engagement:{campaign_id}",
                "donor:phishingclub:31ff3f544af8",
            ],
            redaction="raw session tokens and credentials are never included",
        )
        event = self.audit.append(
            tenant_id=tenant_id,
            actor=_actor(ctx),
            action="report.generated",
            object_type="report",
            object_id=report.report_id,
            correlation_id=_corr(correlation_id),
            detail={"campaign_id": campaign_id, "figures": len(figures)},
        )
        report.provenance.append(f"audit:{event.seq}")
        with self._lock:
            self._reports[(tenant_id, campaign_id)] = report
        return report.as_dict()

    def get_report(self, ctx: Any, campaign_id: str) -> dict[str, Any]:
        report = self._reports.get((_tenant(ctx), campaign_id))
        if report is None:
            raise LabNotFound("report not found")
        return report.as_dict()

    def export_report(self, ctx: Any, campaign_id: str, *, correlation_id: str = "") -> dict[str, Any]:
        tenant_id = _tenant(ctx)
        report = self._reports.get((tenant_id, campaign_id))
        if report is None:
            raise LabNotFound("report not found")
        lines = [
            f"# Lab assessment report — {report.campaign_id}",
            "",
            f"Generated: {report.generated_at}",
            "",
            "## Figures",
            "",
            "| Figure | Value | Status | Source | Missing instrumentation |",
            "|---|---|---|---|---|",
        ]
        for name, figure in report.figures.items():
            value = "unavailable" if figure.value is None else str(figure.value)
            lines.append(
                f"| {name} | {value} | {figure.status.value} | {figure.source} | {figure.missing or ''} |"
            )
        lines += ["", "## Limitations", ""]
        lines += [f"- {item}" for item in report.limitations]
        lines += ["", "## Provenance", ""]
        lines += [f"- {item}" for item in report.provenance]
        lines += ["", "## Redaction", "", report.redaction, ""]
        body = "\n".join(lines)
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        report.export_digest = digest
        self.audit.append(
            tenant_id=tenant_id,
            actor=_actor(ctx),
            action="report.exported",
            object_type="report",
            object_id=report.report_id,
            correlation_id=_corr(correlation_id),
            detail={"campaign_id": campaign_id, "digest": digest, "format": "markdown"},
        )
        return {"format": "markdown", "digest": digest, "body": body}

    # ── lifecycle ───────────────────────────────────────────────────────

    def kill_switch(self, ctx: Any, *, correlation_id: str = "") -> dict[str, Any]:
        tenant_id = _tenant(ctx)
        stopped = 0
        partial = 0
        with self._lock:
            for session in self._sessions.values():
                if session.tenant_id == tenant_id and session.state is SessionState.RUNNING:
                    session.state = SessionState.STOPPED
                    session.stopped_at = now_iso()
                    stopped += 1
            for campaign in self._campaigns.values():
                if campaign.tenant_id == tenant_id and campaign.state is CampaignState.SENDING:
                    campaign.state = CampaignState.PARTIAL
                    partial += 1
        lab = self.boundary.kill_switch(
            tenant_id=tenant_id,
            actor=_actor(ctx),
            correlation_id=_corr(correlation_id),
            stopped_sessions=stopped,
            partial_campaigns=partial,
        )
        return {"lab": lab, "stopped_sessions": stopped, "partial_campaigns": partial}

    def teardown(self, ctx: Any, *, correlation_id: str = "") -> dict[str, Any]:
        tenant_id = _tenant(ctx)
        stopped = 0
        partial = 0
        with self._lock:
            for session in self._sessions.values():
                if session.tenant_id == tenant_id and session.state is SessionState.RUNNING:
                    session.state = SessionState.STOPPED
                    session.stopped_at = now_iso()
                    stopped += 1
            for campaign in self._campaigns.values():
                if campaign.tenant_id == tenant_id and campaign.state is CampaignState.SENDING:
                    campaign.state = CampaignState.PARTIAL
                    partial += 1
            preserved = {
                "campaigns": sum(1 for c in self._campaigns.values() if c.tenant_id == tenant_id),
                "sessions": sum(1 for s in self._sessions.values() if s.tenant_id == tenant_id),
                "artifacts": sum(1 for s in self._sessions.values() if s.tenant_id == tenant_id for _ in s.artifact_ids),
                "reports": sum(1 for (ten, _) in self._reports if ten == tenant_id),
                "audit_rows": len(self.audit.rows(limit=None, tenant_id=tenant_id)),
            }
        lab = self.boundary.teardown(
            tenant_id=tenant_id, actor=_actor(ctx), correlation_id=_corr(correlation_id)
        )
        return {"lab": lab, "preserved": preserved}

    def reset(self, ctx: Any, *, correlation_id: str = "") -> dict[str, Any]:
        return self.boundary.reset(
            tenant_id=_tenant(ctx), actor=_actor(ctx), correlation_id=_corr(correlation_id)
        )

    # ── audit / assertions ──────────────────────────────────────────────

    def audit_view(self, ctx: Any, *, limit: int = 100) -> dict[str, Any]:
        tenant_id = _tenant(ctx)
        rows = self.audit.rows(limit=limit, tenant_id=tenant_id)
        return {
            "events": [row.as_dict() for row in rows],
            "integrity": {"ok": self.audit.verify() is None, "broken_seq": self.audit.verify()},
        }

LAB = LabEngine()
