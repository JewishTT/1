import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GhostlineCanvas } from "./GhostlineCanvas";
import type {
  GlCallWire,
  GlPlaybookDetailWire,
  GlPlaybookSummaryWire,
  GlSimulationWire,
  GlStageWire,
  GlStatusWire,
  GlVoiceWire,
} from "../lib/api";
import { ApiError } from "../lib/http";

/**
 * The GhostLine surface, mounted (Feature 031).
 *
 * Three things are asserted here that per-function unit tests of `model.ts` could
 * not:
 *
 *   1. **The gate's refusal is rendered as a refusal.** A 409 from the server is the
 *      rules-of-engagement gate saying no. If it rendered as an ordinary error an
 *      operator would read "something broke" and try again, when the only thing that
 *      changes the outcome is a supervisor re-recording a sign-off.
 *   2. **A setup gap is not a refusal.** A 424 names a variable or a package. Rendering
 *      both in the same red would train an operator that the tool is refusing them
 *      rather than telling them what to do, so the two carry different `data-kind`s
 *      and the tests below assert on them separately.
 *   3. **The capture counter is on screen.** Not because a test needs it, but because
 *      an assessment record that does not visibly show `0` requires the operator to
 *      take the platform's word for it.
 */

vi.mock("../lib/api", () => ({
  api: {
    ghostlineStatus: vi.fn(),
    listGhostlinePlaybooks: vi.fn(),
    getGhostlinePlaybook: vi.fn(),
    reloadGhostlinePlaybooks: vi.fn(),
    simulateGhostlinePlaybook: vi.fn(),
    listGhostlineVoices: vi.fn(),
    registerGhostlineVoice: vi.fn(),
    cloneGhostlineVoice: vi.fn(),
    forgetGhostlineVoice: vi.fn(),
    startGhostlineRuntime: vi.fn(),
    stopGhostlineRuntime: vi.fn(),
    dialGhostline: vi.fn(),
    listGhostlineCalls: vi.fn(),
    getGhostlineCall: vi.fn(),
    logGhostlineTurn: vi.fn(),
    completeGhostlineCall: vi.fn(),
    ghostlineAnalytics: vi.fn(),
    exportGhostlineAnalytics: vi.fn(),
  },
}));

const { api } = await import("../lib/api");
const mock = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

// ── fixtures ─────────────────────────────────────────────────────────

function status(overrides: Partial<GlStatusWire> = {}): GlStatusWire {
  return {
    donor: {
      donor_id: "ghostline",
      repo: "https://github.com/mbhatt1/GhostLine",
      license: "MIT",
      root: "donors/ghostline",
      present: true,
      playbooks_root: "donors/ghostline/playbooks",
      stage_engine: { ready: ["ghostline.taxonomy", "ghostline.playbook"], absent: [] },
      live_edges: { ready: [], absent: ["ghostline.telephony.twilio"] },
      roles: {},
    },
    config: {
      model: "openai/gpt-4o-mini",
      litellm_api_base: null,
      tts_model: "eleven_multilingual_v2",
      stt_model: "nova-2",
      stt_language: "en-US",
      samples_root: "donors/ghostline/assets",
      playbooks_root: "donors/ghostline/playbooks",
      ledger_path: "logs/ghostline/calls.jsonl",
      log_level: "INFO",
    },
    providers: [
      {
        name: "twilio",
        configured: false,
        env_var: "GHOSTLINE_TWILIO_ACCOUNT_SID",
        detail: "Outbound PSTN placement.",
      },
      {
        name: "elevenlabs",
        configured: true,
        env_var: "GHOSTLINE_ELEVENLABS_API_KEY",
        detail: "TTS and voice cloning.",
      },
    ],
    blockers: ["twilio: set GHOSTLINE_TWILIO_ACCOUNT_SID"],
    runtime: {
      state: "stopped",
      voice_id: null,
      voice_name: null,
      playbook_id: null,
      playbook_name: null,
      model: "openai/gpt-4o-mini",
      capabilities: { modality: "text", source: "default", needs_deepgram: true },
      ws_url: null,
      public_url: null,
      tunnel_provider: null,
      port: null,
      started_at: null,
      media_route_served: false,
      blockers: [],
      missing: [],
    },
    counts: { playbooks: 1, playbooks_valid: 1, voices: 1, calls: 0 },
    playbook_validation_errors: {},
    missing: [],
    ...overrides,
  };
}

function stage(overrides: Partial<GlStageWire> = {}): GlStageWire {
  return {
    stage: "RAPPORT",
    position: 0,
    persona: "professional",
    has_custom_prompt: true,
    custom_prompt: "Hi there, this is IT support.",
    success_regex: null,
    goto_on_success: null,
    goto_on_fail: null,
    max_cycles: 1,
    silent_until: 5,
    ambient_ratio: 0.05,
    language_hint: null,
    operator_note: null,
    psych_triggers: ["reciprocity", "similarity"],
    default_prompt: "Establish natural connection.",
    checkin_line: "Just checking?",
    captures_credential: false,
    ...overrides,
  };
}

function playbook(overrides: Partial<GlPlaybookSummaryWire> = {}): GlPlaybookSummaryWire {
  return {
    playbook_id: "it-test",
    name: "IT Support Test",
    author: "test@example.com",
    version: 1.1,
    culture: "en-US",
    description: "Simple IT support test scenario",
    stage_count: 1,
    first_stage: "RAPPORT",
    stage_names: ["RAPPORT"],
    has_branching: false,
    persona_name: "Alex Morgan",
    techniques: [{ id: "T1566.002", reason: "Phishing: Spearphishing Voice" }],
    mapping_source: "platform-declared",
    source_path: "donors/ghostline/playbooks/it-test.yaml",
    valid: true,
    invalid_reason: null,
    missing: [],
    ...overrides,
  };
}

const voice: GlVoiceWire = {
  voice_id: "21m00Tcm4TlvDq8ikWAM",
  name: "support desk",
  origin: "premade",
  created_at: "2026-10-16T10:00:00+00:00",
  sample_ref: null,
  sample_bytes: null,
  notes: null,
};

function envelope<T>(body: T) {
  return { served: ["/specops/ghostline"], missing: [], scope: "tenant-wide" as const, ...body };
}

beforeEach(() => {
  vi.clearAllMocks();
  mock.ghostlineStatus.mockResolvedValue(envelope(status()));
  mock.listGhostlinePlaybooks.mockResolvedValue(envelope({ playbooks: [playbook()], invalid: {} }));
  mock.getGhostlinePlaybook.mockResolvedValue(
    envelope({
      playbook: playbook(),
      stages: [
        stage(),
        stage({
          stage: "CLOSE",
          position: 1,
          success_regex: "\\b\\d{6}\\b",
          captures_credential: true,
        }),
      ],
      persona: {
        name: "Alex Morgan",
        background: "Senior support engineer",
        voice: "warm",
        persuasion_principles: [],
        do: [],
        dont: [],
      },
      defaults: { persona: "professional" },
    } satisfies GlPlaybookDetailWire),
  );
  mock.listGhostlineVoices.mockResolvedValue(envelope({ voices: [voice] }));
  mock.listGhostlineCalls.mockResolvedValue(envelope({ calls: [] as GlCallWire[] }));
  mock.ghostlineAnalytics.mockResolvedValue(
    envelope({
      analytics: {
        campaign: null,
        call_count: 0,
        completed_count: 0,
        in_progress_count: 0,
        turn_count: 0,
        stage_counts: {},
        outcomes: {},
        by_campaign: {},
        redaction_kinds: {},
        capture_passwords: false,
        credentials_captured: 0,
        conversion_rate: null,
      },
    }),
  );
});

// ── the canvas ───────────────────────────────────────────────────────

describe("GhostlineCanvas", () => {
  it("offers one tab per CLI verb plus the two surfaces a CLI has no shape for", () => {
    render(<GhostlineCanvas />);
    for (const label of [
      "Runtime",
      "Playbooks",
      "Simulator",
      "Voices",
      "Dialler",
      "Transcripts",
      "Analytics",
    ]) {
      expect(screen.getByRole("tab", { name: new RegExp(label, "i") })).toBeInTheDocument();
    }
  });

  it("states the scope and the capture invariant on the surface itself", () => {
    render(<GhostlineCanvas />);
    expect(screen.getByTestId("gl-canvas")).toHaveAttribute("data-panel", "runtime");
    expect(screen.getByText(/credentials never stored/i)).toBeInTheDocument();
  });
});

// ── runtime ──────────────────────────────────────────────────────────

describe("RuntimePanel", () => {
  it("states what runs in-process and what needs a provider, on every panel", async () => {
    /*
     * This assertion moved to the deck strip and got stronger for the move. It used to
     * hold only on Runtime, which meant switching to the Dialler lost the one thing an
     * operator needs before dialling. It now has to hold after every tab switch, which
     * is the whole reason the deck is fetched at the canvas rather than inside a panel.
     *
     * One render, then walk the tabs: rendering per tab would test four separate
     * canvases, which is not the property being claimed.
     *
     * The timeout is explicit because this is the only test in the file that walks
     * every tab, and four render cycles do not reliably fit the 5s default on a
     * loaded machine. Weakening the assertion to fit the clock would trade a real
     * guarantee for a fast suite.
     */
    render(<GhostlineCanvas />);
    for (const tab of ["Playbooks", "Dialler", "Analytics", "Runtime"]) {
      fireEvent.click(await screen.findByRole("tab", { name: tab }));
      await waitFor(() => expect(screen.getByTestId("gl-deck-engine")).toHaveTextContent("2"));
      expect(screen.getByTestId("gl-deck-edges")).toHaveTextContent("0/1");
      expect(screen.getByTestId("gl-deck-donor")).toHaveTextContent("MIT");
    }
  }, 20_000);

  it("shows provenance on the Runtime panel rather than a second copy of the deck", async () => {
    render(<GhostlineCanvas />);
    await waitFor(() => expect(screen.getByTestId("gl-donor-id")).toHaveTextContent("ghostline"));
    expect(screen.getByTestId("gl-provenance")).toBeInTheDocument();
    expect(screen.getByTestId("gl-donor-repo")).toHaveTextContent("mbhatt1/GhostLine");
    // The four numbers live on the deck exactly once.
    expect(screen.getAllByTestId("gl-deck-engine")).toHaveLength(1);
    expect(screen.queryByTestId("gl-engine-count")).not.toBeInTheDocument();
  });

  it("names the variable to set for each unconfigured provider", async () => {
    render(<GhostlineCanvas />);
    await waitFor(() =>
      expect(screen.getByTestId("gl-providers-twilio-env")).toHaveTextContent(
        "GHOSTLINE_TWILIO_ACCOUNT_SID",
      ),
    );
    // A configured provider does not render its variable — there is nothing to fix.
    expect(screen.queryByTestId("gl-providers-elevenlabs-env")).not.toBeInTheDocument();
  });

  it("cannot start a runtime without both a voice and a playbook", async () => {
    render(<GhostlineCanvas />);
    await waitFor(() => expect(screen.getByTestId("gl-voice-select")).toBeInTheDocument());
    expect(screen.getByTestId("gl-start")).toBeDisabled();
  });

  it("renders a blocked runtime as a setup gap, not as a refusal", async () => {
    mock.startGhostlineRuntime.mockRejectedValue(
      new ApiError(
        424,
        { error: "RuntimeUnavailable", reason: "2 prerequisites are missing", blockers: ["a"] },
        "blocked",
      ),
    );
    render(<GhostlineCanvas />);
    await waitFor(() => expect(screen.getByTestId("gl-voice-select")).toBeInTheDocument());
    fireEvent.change(screen.getByTestId("gl-voice-select"), { target: { value: voice.voice_id } });
    fireEvent.change(screen.getByTestId("gl-playbook-select"), { target: { value: "it-test" } });
    await waitFor(() => expect(screen.getByTestId("gl-start")).toBeEnabled());
    fireEvent.click(screen.getByTestId("gl-start"));

    const refusal = await screen.findByTestId("gl-runtime-refusal");
    await waitFor(() => expect(refusal).toHaveAttribute("data-kind", "setup"));
    expect(refusal).toHaveTextContent("2 prerequisites are missing");
  });
});

// ── playbooks ────────────────────────────────────────────────────────

describe("PlaybooksPanel", () => {
  it("shows the ladder with a stage's intent, not just its name", async () => {
    render(<GhostlineCanvas initialPanel="playbooks" />);
    fireEvent.click(await screen.findByTestId("gl-playbook-it-test"));
    await waitFor(() => expect(screen.getByTestId("gl-ladder")).toBeInTheDocument());
    expect(screen.getByTestId("gl-stage-RAPPORT")).toHaveTextContent(
      "open and get permission to talk",
    );
    expect(screen.getByTestId("gl-triggers-RAPPORT")).toHaveTextContent("reciprocity");
  });

  it("marks a credential-eliciting stage rather than hiding its pattern", async () => {
    render(<GhostlineCanvas initialPanel="playbooks" />);
    fireEvent.click(await screen.findByTestId("gl-playbook-it-test"));
    await waitFor(() => expect(screen.getByTestId("gl-stage-CLOSE")).toBeInTheDocument());
    const close = screen.getByTestId("gl-stage-CLOSE");
    expect(close).toHaveAttribute("data-captures", "true");
    expect(screen.getByTestId("gl-captures-CLOSE")).toHaveTextContent("elicits a credential");
    expect(close).toHaveTextContent("\\b\\d{6}\\b");
  });

  it("draws a branch when a stage declares one", async () => {
    mock.getGhostlinePlaybook.mockResolvedValue(
      envelope({
        playbook: playbook({ has_branching: true }),
        stages: [stage({ stage: "URGENCY", goto_on_fail: "OBJECTION" })],
        persona: null,
        defaults: null,
      } satisfies GlPlaybookDetailWire),
    );
    render(<GhostlineCanvas initialPanel="playbooks" />);
    fireEvent.click(await screen.findByTestId("gl-playbook-it-test"));
    await waitFor(() =>
      expect(screen.getByTestId("gl-branch-URGENCY")).toHaveTextContent("OBJECTION"),
    );
  });

  it("attributes the ATT&CK mapping to the platform", async () => {
    render(<GhostlineCanvas initialPanel="playbooks" />);
    const technique = await screen.findByText("T1566.002");
    expect(technique).toHaveAttribute("title", expect.stringContaining("platform-declared"));
  });

  it("reports a playbook the donor rejected instead of hiding it", async () => {
    mock.listGhostlinePlaybooks.mockResolvedValue(
      envelope({
        playbooks: [
          playbook({ valid: false, invalid_reason: "sequence[2] duplicates stage CLOSE" }),
        ],
        invalid: { "it-test": "sequence[2] duplicates stage CLOSE" },
      }),
    );
    render(<GhostlineCanvas initialPanel="playbooks" />);
    expect(await screen.findByTestId("gl-invalid-it-test")).toHaveTextContent("duplicates stage");
  });
});

// ── simulator ────────────────────────────────────────────────────────

describe("SimulatePanel", () => {
  const simulation: GlSimulationWire = {
    playbook_id: "it-test",
    playbook_name: "IT Support Test",
    steps: [
      {
        index: 0,
        utterance: "hello",
        stage_before: "RAPPORT",
        stage_after: "RAPPORT",
        success: false,
        cycles_remaining: 1,
        matched_pattern: null,
        next_line: "Hi there, this is IT support.",
        exited: false,
      },
    ],
    final_stage: "RAPPORT",
    outcome: null,
    outcome_reason: null,
    capture_passwords: false,
    credentials_captured: 0,
    redaction_kinds: [],
    missing: [],
  };

  it("runs the donor's stage machine and flags a held stage", async () => {
    mock.simulateGhostlinePlaybook.mockResolvedValue(envelope({ simulation }));
    render(<GhostlineCanvas initialPanel="simulate" />);
    fireEvent.change(await screen.findByTestId("gl-sim-script"), {
      target: { value: "hello\nyes that works" },
    });
    fireEvent.click(screen.getByTestId("gl-sim-run"));

    await waitFor(() => expect(screen.getByTestId("gl-sim-trace")).toBeInTheDocument());
    // Held == the machine did not advance. That is the signal an author needs when
    // max_cycles is about to send the call somewhere they did not plan.
    expect(screen.getByTestId("gl-sim-step-0")).toHaveAttribute("data-held", "true");
    expect(screen.getByTestId("gl-sim-held-0")).toHaveTextContent("1 cycle(s) left");
  });

  it("shows the capture counter as zero and names what could not run", async () => {
    mock.simulateGhostlinePlaybook.mockResolvedValue(
      envelope({
        simulation: { ...simulation, missing: ["the generated reply needs openai-agents"] },
      }),
    );
    render(<GhostlineCanvas initialPanel="simulate" />);
    fireEvent.change(await screen.findByTestId("gl-sim-script"), { target: { value: "hello" } });
    fireEvent.click(screen.getByTestId("gl-sim-run"));

    await waitFor(() =>
      expect(screen.getByTestId("gl-sim-no-capture")).toHaveTextContent("0 credentials"),
    );
    expect(screen.getByTestId("gl-sim-missing")).toHaveTextContent("openai-agents");
  });

  it("refuses to run with no script", async () => {
    render(<GhostlineCanvas initialPanel="simulate" />);
    await waitFor(() => expect(screen.getByTestId("gl-sim-run")).toBeDisabled());
  });
});

// ── voices ───────────────────────────────────────────────────────────

describe("VoicesPanel", () => {
  it("registers a premade id — the free-tier path the donor documents but cannot record", async () => {
    mock.registerGhostlineVoice.mockResolvedValue(envelope({ voice }));
    render(<GhostlineCanvas initialPanel="voices" />);
    fireEvent.change(await screen.findByTestId("gl-premade-id"), {
      target: { value: voice.voice_id },
    });
    fireEvent.click(screen.getByTestId("gl-register-voice"));

    await waitFor(() =>
      expect(mock.registerGhostlineVoice).toHaveBeenCalledWith({
        voice_id: voice.voice_id,
        name: voice.voice_id,
        origin: "premade",
      }),
    );
  });

  it("distinguishes a cloned voice from a premade one", async () => {
    render(<GhostlineCanvas initialPanel="voices" />);
    await waitFor(() =>
      expect(screen.getByTestId(`gl-voice-origin-${voice.voice_id}`)).toHaveTextContent("premade"),
    );
  });

  it("renders a 422 from the clone route as a fixable reason", async () => {
    mock.cloneGhostlineVoice.mockRejectedValue(
      new ApiError(
        422,
        { error: "VoiceUnavailable", reason: "sample format .mp3 is not readable" },
        "bad",
      ),
    );
    render(<GhostlineCanvas initialPanel="voices" />);
    fireEvent.change(await screen.findByTestId("gl-clone-name"), { target: { value: "helpdesk" } });
    fireEvent.change(screen.getByTestId("gl-clone-ref"), { target: { value: "sample.mp3" } });
    fireEvent.click(screen.getByTestId("gl-clone-voice"));

    const refusal = await screen.findByTestId("gl-voices-refusal");
    await waitFor(() => expect(refusal).toHaveAttribute("data-kind", "setup"));
    expect(refusal).toHaveTextContent("not readable");
  });
});

// ── dialler ──────────────────────────────────────────────────────────

describe("DialerPanel", () => {
  it("will not dial before the runtime is up, and says why", async () => {
    render(<GhostlineCanvas initialPanel="dialer" />);
    await waitFor(() => expect(screen.getByTestId("gl-dialer-not-ready")).toBeInTheDocument());
    expect(screen.getByTestId("gl-dialer-not-ready")).toHaveTextContent("runtime is stopped");
    expect(screen.getByTestId("gl-dial")).toBeDisabled();
  });

  it("renders a gate refusal as a refusal and names the rejected number", async () => {
    const running = status();
    running.runtime = {
      ...running.runtime,
      state: "running",
      ws_url: "wss://lab.example/twilio",
      voice_id: "v",
      playbook_id: "it-test",
    };
    mock.ghostlineStatus.mockResolvedValue(envelope(running));
    mock.dialGhostline.mockRejectedValue(
      new ApiError(
        422,
        {
          error: "RosterError",
          reason: "1 target(s) are not on the supervisor-approved roster",
          rejected_targets: ["+15559999999"],
        },
        "refused",
      ),
    );
    render(<GhostlineCanvas initialPanel="dialer" />);
    fireEvent.change(await screen.findByTestId("gl-target"), { target: { value: "+15559999999" } });
    fireEvent.change(screen.getByTestId("gl-roe-id"), { target: { value: "roe-1" } });
    fireEvent.change(screen.getByTestId("gl-roster"), { target: { value: "+15551234567" } });
    await waitFor(() => expect(screen.getByTestId("gl-dial")).toBeEnabled());
    fireEvent.click(screen.getByTestId("gl-dial"));

    const refusal = await screen.findByTestId("gl-dialer-refusal");
    await waitFor(() => expect(refusal).toHaveAttribute("data-kind", "gate"));
    expect(refusal).toHaveTextContent("RosterError");
    expect(screen.getByTestId("gl-dialer-refusal-rejected")).toHaveTextContent("+15559999999");
  });

  it("warns before the gate refuses, not only after", async () => {
    const running = status();
    running.runtime = { ...running.runtime, state: "running", ws_url: "wss://lab.example/twilio" };
    mock.ghostlineStatus.mockResolvedValue(envelope(running));
    render(<GhostlineCanvas initialPanel="dialer" />);
    fireEvent.change(await screen.findByTestId("gl-target"), { target: { value: "+15559999999" } });
    fireEvent.change(screen.getByTestId("gl-roster"), { target: { value: "+15551234567" } });
    expect(await screen.findByTestId("gl-target-unrostered")).toBeInTheDocument();
  });

  it("rejects a malformed number before the request is made", async () => {
    const running = status();
    running.runtime = { ...running.runtime, state: "running", ws_url: "wss://lab.example/twilio" };
    mock.ghostlineStatus.mockResolvedValue(envelope(running));
    render(<GhostlineCanvas initialPanel="dialer" />);
    fireEvent.change(await screen.findByTestId("gl-target"), { target: { value: "5551234567" } });
    expect(screen.getByTestId("gl-target-invalid")).toHaveTextContent("Not E.164");
  });

  it("keeps the capture counter on screen where a credential would otherwise be", async () => {
    render(<GhostlineCanvas initialPanel="dialer" />);
    await waitFor(() =>
      expect(screen.getByTestId("gl-no-capture")).toHaveTextContent("0 credentials"),
    );
  });

  it("never renders the operator's own caller id", async () => {
    mock.ghostlineStatus.mockResolvedValue(
      envelope(
        status({
          providers: [
            {
              name: "twilio_from_number",
              configured: true,
              env_var: "GHOSTLINE_TWILIO_FROM_NUMBER",
              detail: "The caller ID placed on every call.",
            },
          ],
        }),
      ),
    );
    render(<GhostlineCanvas initialPanel="dialer" />);
    await waitFor(() => expect(screen.getByTestId("gl-dialer-providers")).toBeInTheDocument());
    // Configured is reported; the number itself is not served, so it cannot be shown.
    expect(screen.getByTestId("gl-dialer-providers-twilio_from_number")).toBeInTheDocument();
    expect(screen.getByTestId("gl-dialer-providers")).toHaveTextContent(
      "The caller ID placed on every call.",
    );
    expect(screen.getByTestId("gl-dialer-providers")).not.toHaveTextContent(/\+\d{6,}/);
  });
});

// ── transcripts ──────────────────────────────────────────────────────

describe("TranscriptsPanel", () => {
  const call: GlCallWire = {
    call_id: "gl-abc",
    sid: "CA123",
    target: "+15551234567",
    campaign: "drill",
    persona: "professional",
    playbook_id: "it-test",
    roe_id: "roe-1",
    started_at: "2026-10-16T10:00:00+00:00",
    ended_at: null,
    outcome: null,
    capture_passwords: false,
    credentials_captured: 0,
    notes: null,
    message_count: 1,
    final_stage: "CLOSE",
  };

  it("renders a redacted turn with the kind that was removed, not the value", async () => {
    mock.listGhostlineCalls.mockResolvedValue(envelope({ calls: [call] }));
    mock.getGhostlineCall.mockResolvedValue(
      envelope({
        call: {
          ...call,
          messages: [
            {
              call_id: "gl-abc",
              role: "user",
              content: "my code is [redacted:no-capture]",
              stage: "CLOSE",
              timestamp: "2026-10-16T10:01:00+00:00",
              redaction_kinds: ["playbook-success"],
              sentiment_score: null,
              interest_level: null,
              objection_type: null,
              trigger_used: null,
            },
          ],
        },
      }),
    );
    render(<GhostlineCanvas initialPanel="transcripts" />);
    fireEvent.click(await screen.findByTestId("gl-call-gl-abc"));

    await waitFor(() => expect(screen.getByTestId("gl-turn-0")).toBeInTheDocument());
    expect(screen.getByTestId("gl-turn-0")).toHaveTextContent("[redacted:no-capture]");
    expect(screen.getByTestId("gl-turn-redacted-0")).toHaveTextContent("playbook-success");
    expect(screen.getByTestId("gl-detail-no-capture")).toHaveTextContent("0 credentials");
  });
});

// ── analytics ────────────────────────────────────────────────────────

describe("AnalyticsPanel", () => {
  it("renders an unmeasured rate as an em dash, never as zero", async () => {
    render(<GhostlineCanvas initialPanel="analytics" />);
    await waitFor(() => expect(screen.getByTestId("gl-m-rate")).toHaveTextContent("—"));
    expect(screen.getByTestId("gl-m-rate")).toHaveAttribute("data-muted", "true");
  });

  it("shows the redaction ledger: what was elicited, not what was given", async () => {
    mock.ghostlineAnalytics.mockResolvedValue(
      envelope({
        analytics: {
          campaign: null,
          call_count: 3,
          completed_count: 3,
          in_progress_count: 0,
          turn_count: 40,
          stage_counts: { RAPPORT: 12, CLOSE: 4 },
          outcomes: { compromised: 2, abandoned: 1 },
          by_campaign: { drill: 3 },
          redaction_kinds: { "playbook-success": 2 },
          capture_passwords: false,
          credentials_captured: 0,
          conversion_rate: 0.6667,
        },
      }),
    );
    render(<GhostlineCanvas initialPanel="analytics" />);
    await waitFor(() => expect(screen.getByTestId("gl-redaction-kinds")).toBeInTheDocument());
    expect(screen.getByTestId("gl-redaction-kinds")).toHaveTextContent("playbook-success");
    expect(screen.getByTestId("gl-m-captured")).toHaveTextContent("0");
    expect(screen.getByTestId("gl-m-rate")).toHaveTextContent("67%");
  });
});
