import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  api: {
    labOverview: vi.fn(),
    labAudit: vi.fn(),
    labCreateTemplate: vi.fn(),
    labCreateSender: vi.fn(),
    labCreateCampaign: vi.fn(),
    labLaunchCampaign: vi.fn(),
    labGetCampaign: vi.fn(),
    labStartSession: vi.fn(),
    labCapture: vi.fn(),
    labStopSession: vi.fn(),
    labLaunchOperation: vi.fn(),
    labLinkAssessment: vi.fn(),
    labGenerateReport: vi.fn(),
    labGetReport: vi.fn(),
    labExportReport: vi.fn(),
    labKillSwitch: vi.fn(),
    labTeardown: vi.fn(),
    labReset: vi.fn(),
    listEmulationPlans: vi.fn(),
  },
}));

import type { LabOverviewWire } from "../lib/api";
import { ApiError } from "../lib/http";
import { LabCanvas } from "./LabCanvas";

const { api } = await import("../lib/api");
const mock = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

function overview(overrides: Partial<LabOverviewWire> = {}): LabOverviewWire {
  return {
    served: ["/specops/lab"],
    missing: [],
    scope: "red-team",
    lab: {
      lab_id: "lab-test",
      status: "ready",
      egress_policy: "roe-gated",
      targets: ["*"],
      kill_switch_at: null,
      teardown_at: null,
    },
    readiness: {
      donor: {
        id: "phishingclub",
        path: "donors/phishingclub",
        status: "verified",
        version: "31ff3f544af8",
        license: "AGPL-3.0",
        license_source: null,
        attribution: true,
        blockers: [],
        adapter_served: true,
        service_url: "https://127.0.0.1:8002",
        console_url: "https://127.0.0.1:8002",
        api_key_configured: false,
      },
      encryption: { algorithm: "AES-256-GCM", key_source: "ephemeral", ready: true, error: null },
      full_red_team_enabled: true,
      matrix: [
        { capability: "red-team mode", state: "ready", detail: "full mode · RoE-gated", missing: [] },
        {
          capability: "phishingclub adapter",
          state: "ready",
          detail: "status=verified version=31ff3f544af8 service=https://127.0.0.1:8002",
          missing: [],
        },
      ],
      blockers: [],
      counts: { campaigns: 1, sessions: 1, artifacts: 1, reports: 1 },
    },
    campaigns: [
      {
        campaign_id: "cmp-1",
        tenant_id: "ten-a",
        name: "Q4 lab drill",
        template_id: "tpl-lure",
        sender_id: "snd-lab",
        roster: ["alice@lab.test", "bob@lab.test"],
        state: "draft",
        roe_status: "unconfirmed",
        roe_id: null,
        attack_mapping: ["T1566"],
        scheme: "manual",
        launched_at: null,
        assessment_id: null,
        retention_days: 30,
        funnel: {
          sent: 0,
          opened: 0,
          clicked: 0,
          reported: 0,
          submitted: 0,
          training: { assigned: 0, completed: 0 },
          subject_count: 0,
          source: "derived",
        },
        captured_credentials_count: 0,
      },
    ],
    templates: [
      {
        template_id: "tpl-lure",
        name: "Synthetic multi-stage lure",
        stages: ["landing", "training"],
        assets: ["lab://specops-lab.local/lure/landing.html"],
        variables: {},
        provenance: "synthetic",
        authorized: true,
        created_at: "2026-11-01T00:00:00+00:00",
      },
    ],
    senders: [
      {
        sender_id: "snd-lab",
        name: "Lab SMTP",
        host: "specops-lab.local",
        tls: true,
        dns_ready: true,
        credential_ref: "vault://lab/smtp",
        ready: true,
        missing: [],
        created_at: "2026-11-01T00:00:00+00:00",
      },
    ],
    sessions: [
      {
        session_id: "aitm-1",
        mode: "reverse_proxy",
        target_host: "specops-lab.local",
        state: "running",
        roe_status: "confirmed",
        started_at: "2026-11-01T00:00:00+00:00",
        stopped_at: null,
        retention_expires_at: "2026-11-02T00:00:00+00:00",
        artifact_ids: ["art-1"],
      },
    ],
    artifacts: [
      {
        artifact_id: "art-1",
        session_id: "aitm-1",
        kind: "token",
        redacted_preview: "session-token ***",
        sha256: "a".repeat(64),
        captured_at: "2026-11-01T00:00:00+00:00",
        expires_at: "2026-11-02T00:00:00+00:00",
        available: true,
        access_count: 1,
      },
    ],
    reports: [
      {
        report_id: "rpt-1",
        campaign_id: "cmp-1",
        generated_at: "2026-11-01T00:00:00+00:00",
        figures: {
          sent: { value: 2, status: "derived", source: "engagement:campaign_recipient_message_sent", missing: null },
          operation_abilities: {
            value: null,
            status: "unavailable",
            source: "emulation:operation",
            missing: "no linked operation",
          },
        },
        limitations: ["lab simulation; no production target"],
        provenance: ["engagement:cmp-1", "audit:7"],
        redaction: "raw session tokens and credentials are never included",
        export_digest: null,
      },
    ],
    operations: [
      {
        operation_id: "op-1",
        plan_id: "ael-plan",
        lab_fixture: "specops/lab-target",
        roe_status: "confirmed",
        state: "running",
        abilities: [
          {
            ability_id: "abl-1",
            technique: "T1566",
            tactic: "initial-access",
            executor: "sh",
            state: "executed",
          },
        ],
        started_at: "2026-11-01T00:00:00+00:00",
        halted_reason: null,
      },
    ],
    engagement: {
      channel_funnel: { sent: 2, opened: 2, clicked: 1, reported: 0 },
      training: { assigned: 1, completed: 1 },
      subjects: 2,
      anonymized: false,
    },
    audit: [
      {
        seq: 7,
        tenant_id: "ten-a",
        actor: "user-a",
        action: "campaign.launched",
        object_type: "campaign",
        object_id: "cmp-1",
        outcome: "ok",
        at: "2026-11-01T00:00:00+00:00",
        correlation_id: "corr-1",
        detail: {},
        prev_hash: "GENESIS",
        row_hash: "b".repeat(64),
      },
    ],
    ...overrides,
  };
}

describe("LabCanvas", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mock.labOverview.mockResolvedValue(overview());
  });

  it("keeps the red-team banner and shows the verified donor", async () => {
    render(<LabCanvas />);

    expect(await screen.findByTestId("lab-control-panel")).toBeInTheDocument();
    expect(screen.getByTestId("lab-banner")).toHaveTextContent("full red-team");
    expect(screen.getByTestId("lab-readiness-matrix")).toHaveTextContent("phishingclub adapter");
    expect(screen.getByTestId("lab-readiness-matrix")).toHaveTextContent("verified");
  });

  it("renders a 409 refusal verbatim when launch is blocked", async () => {
    mock.labLaunchCampaign.mockRejectedValue(
      new ApiError(409, { error: "RoEError", reason: "no rules-of-engagement recorded" }, "RoEError"),
    );
    render(<LabCanvas />);
    fireEvent.click(await screen.findByTestId("tab-campaigns"));
    fireEvent.change(screen.getByTestId("lab-roe-id"), { target: { value: "roe-missing" } });
    fireEvent.click(screen.getByTestId("lab-launch-cmp-1"));

    await waitFor(() => {
      expect(screen.getByTestId("lab-campaigns-note")).toHaveTextContent("409 RoEError");
    });
    expect(screen.getByTestId("lab-campaigns-note")).toHaveTextContent("no rules-of-engagement");
  });

  it("shows only the redacted artifact preview", async () => {
    render(<LabCanvas />);
    fireEvent.click(await screen.findByTestId("tab-aitm"));

    expect(screen.getByTestId("lab-session-aitm-1")).toHaveTextContent("session-token ***");
    expect(screen.getByTestId("lab-session-aitm-1")).not.toHaveTextContent("synthetic-token");
  });

  it("names the plan donor and links an operation to a campaign", async () => {
    mock.listEmulationPlans.mockResolvedValue({
      served: ["/api/v1/specops/emulation/plans"],
      missing: [],
      scope: "tenant-wide",
      plans: [
        {
          plan_id: "ael-plan",
          name: "AEL lab plan",
          source_donor: "adversary_emulation_library",
          target_techniques: ["T1566"],
          lab_fixture: "specops/lab-target",
        },
      ],
    });
    mock.labLinkAssessment.mockResolvedValue({
      served: ["/api/v1/specops/lab/assessments"],
      missing: [],
      scope: "red-team",
      assessment: {
        assessment_id: "asmt-1",
        campaign_id: "cmp-1",
        operation_id: "op-1",
        created_at: "2026-11-01T00:00:00+00:00",
      },
    });
    render(<LabCanvas />);
    fireEvent.click(await screen.findByTestId("tab-operations"));

    await waitFor(() => {
      expect(screen.getByTestId("lab-plan-id")).toHaveTextContent("adversary_emulation_library");
    });
    expect(screen.getByTestId("lab-operation-op-1")).toHaveTextContent("T1566");
    fireEvent.change(screen.getByTestId("lab-campaign-link"), { target: { value: "cmp-1" } });
    fireEvent.change(screen.getByTestId("lab-operation-link"), { target: { value: "op-1" } });
    fireEvent.click(screen.getByTestId("lab-link-assessment"));

    await waitFor(() => {
      expect(mock.labLinkAssessment).toHaveBeenCalledWith({
        campaign_id: "cmp-1",
        operation_id: "op-1",
      });
    });
  });

  it("keeps training compliance out of the phishing funnel", async () => {
    render(<LabCanvas />);
    fireEvent.click(await screen.findByTestId("tab-engagement"));

    expect(screen.getByTestId("lab-engagement-funnel")).toHaveTextContent("2");
    expect(screen.getByTestId("lab-engagement-funnel")).not.toHaveTextContent("training");
    expect(screen.getByTestId("lab-training-block")).toHaveTextContent("Training compliance");
    expect(screen.getByTestId("lab-training-block")).toHaveTextContent("1");
  });

  it("renders unavailable figures without a fabricated zero", async () => {
    render(<LabCanvas />);
    fireEvent.click(await screen.findByTestId("tab-reports"));

    const table = screen.getByTestId("lab-report-figures");
    expect(table).toHaveTextContent("operation_abilities");
    expect(table).toHaveTextContent("unavailable");
    expect(table).toHaveTextContent("no linked operation");
    expect(table).toHaveTextContent("derived");
  });

  it("fires the kill switch and reports the stopped state", async () => {
    mock.labKillSwitch.mockResolvedValue({
      served: ["/specops/lab"],
      missing: [],
      scope: "red-team",
      lab: { ...overview().lab, status: "killed", kill_switch_at: "now" },
      stopped_sessions: 1,
      partial_campaigns: 0,
    });
    render(<LabCanvas />);
    fireEvent.click(await screen.findByTestId("lab-kill-switch"));

    await waitFor(() => {
      expect(mock.labKillSwitch).toHaveBeenCalledTimes(1);
      expect(screen.getByTestId("lab-control-note")).toHaveTextContent("Kill switch fired");
    });
  });
});
