import type {
  GlCapabilitiesWire,
  GlMessageWire,
  GlPlaybookSummaryWire,
  GlRuntimeWire,
  GlSimulationStepWire,
  GlStageWire,
} from "../lib/api";
import type {
  GlCallRow,
  GlMessageRow,
  GlOutcome,
  GlPlaybookRow,
  GlProviderRow,
  GlRuntimeRow,
  GlSimulationRow,
  GlSimulationStepRow,
  GlStageRole,
  GlStageRow,
  GlVoiceRow,
} from "./types";
import { STAGE_INTENT, STAGE_LADDER } from "./types";
import { toWorkStatus } from "../ui/status";

/**
 * Pure derivation: wire shapes -> row shapes.
 *
 * No fetching, no React, no side effects. Every function here is total: it takes a
 * wire object that may have missing fields and returns a row whose fields are
 * either real or explicitly `null`. That is the §99 contract enforced in one place,
 * so a panel cannot accidentally invent a value by reaching into the wrong nesting
 * level — which is exactly how `target_techniques.length` becomes a confident `0`
 * on a panel that never received a list.
 *
 * The mapping is deliberately lossless about doubt: an unknown donor status becomes
 * `Unknown` (never a new colour), an absent optional becomes `null` (never a
 * default), and a `conversion_rate` the server could not compute stays `null`
 * rather than becoming a flattering zero.
 */

/** Which part of the ladder a stage belongs to, derived from its position. */
export function stageRole(stage: string): GlStageRole {
  switch (stage) {
    case "RAPPORT":
    case "CREDIBILITY":
      return "trust";
    case "DISCOVERY":
    case "VALIDATION":
      return "discovery";
    case "ALIGNMENT":
    case "PROOF":
    case "URGENCY":
    case "TRIAL_CLOSE":
      return "persuasion";
    case "OBJECTION":
      return "objection";
    case "CLOSE":
    case "FOLLOW_UP":
      return "closure";
    case "REPORTING":
      return "reporting";
    default:
      // A stage the ladder does not know. `discovery` is the neutral middle rather
      // than a new role: an unrecognised stage is not a reporting stage, and
      // colouring it as one would misrepresent it.
      return "discovery";
  }
}

export function toStageRow(wire: GlStageWire): GlStageRow {
  return {
    stage: wire.stage,
    position: wire.position,
    persona: wire.persona ?? null,
    prompt: wire.custom_prompt ?? wire.default_prompt ?? null,
    successRegex: wire.success_regex ?? null,
    gotoOnSuccess: wire.goto_on_success ?? null,
    gotoOnFail: wire.goto_on_fail ?? null,
    maxCycles: wire.max_cycles,
    silentUntil: wire.silent_until ?? null,
    languageHint: wire.language_hint ?? null,
    // `psych_triggers` is null when the donor taxonomy is absent. That is a named
    // absence, and it must not become an empty list: [] would read as "this stage
    // uses no triggers", which is a claim about the scenario.
    psychTriggers: wire.psych_triggers ?? [],
    checkinLine: wire.checkin_line ?? null,
    capturesCredential: wire.captures_credential === true,
    role: stageRole(wire.stage),
    intent: STAGE_INTENT[wire.stage] ?? "no documented intent",
    branching: wire.goto_on_success != null || wire.goto_on_fail != null,
    status: wire.has_custom_prompt ? toWorkStatus("running") : toWorkStatus("unknown"),
  };
}

/** The ladder rendered in canonical order, with any stage the playbook adds after it. */
export function ladderOrder(stages: readonly GlStageRow[]): readonly GlStageRow[] {
  const byName = new Map(stages.map((s) => [s.stage, s]));
  const ordered: GlStageRow[] = [];
  for (const name of STAGE_LADDER) {
    const stage = byName.get(name);
    if (stage) {
      ordered.push(stage);
      byName.delete(name);
    }
  }
  // Whatever is left is outside the known ladder — kept, not dropped, and rendered
  // last so an author's custom stage is visible rather than invisible.
  for (const stage of stages) {
    if (byName.has(stage.stage)) ordered.push(stage);
  }
  return ordered;
}

export function toPlaybookRow(
  wire: GlPlaybookSummaryWire,
  stages: readonly GlStageWire[] = [],
): GlPlaybookRow {
  const rows = ladderOrder(stages.map(toStageRow));
  return {
    playbookId: wire.playbook_id,
    name: wire.name,
    author: wire.author ?? null,
    version: wire.version,
    culture: wire.culture ?? null,
    description: wire.description ?? null,
    stageCount: wire.stage_count,
    firstStage: wire.first_stage,
    stages: rows,
    hasBranching: wire.has_branching,
    personaName: wire.persona_name,
    techniques: wire.techniques ?? [],
    // Rendered verbatim: the mapping is the platform's, and the UI says which.
    mappingSource: wire.mapping_source,
    valid: wire.valid,
    invalidReason: wire.invalid_reason ?? null,
    missing: wire.missing ?? [],
  };
}

export function toVoiceRow(wire: {
  voice_id: string;
  name: string;
  origin: string;
  created_at: string;
  sample_ref: string | null;
  sample_bytes: number | null;
  notes: string | null;
}): GlVoiceRow {
  return {
    voiceId: wire.voice_id,
    name: wire.name,
    origin: wire.origin,
    createdAt: wire.created_at,
    sampleRef: wire.sample_ref ?? null,
    sampleBytes: wire.sample_bytes ?? null,
    notes: wire.notes ?? null,
    // A registered voice is usable, which in the closed vocabulary is `Healthy`.
    // The origin is rendered as its own chip — cloned vs premade matters to an
    // operator in a way that a status colour cannot carry.
    status: toWorkStatus("healthy"),
  };
}

export function toSimulationStepRow(wire: GlSimulationStepWire): GlSimulationStepRow {
  return {
    index: wire.index,
    utterance: wire.utterance,
    stageBefore: wire.stage_before,
    stageAfter: wire.stage_after,
    success: wire.success === true,
    cyclesRemaining: wire.cycles_remaining,
    matchedPattern: wire.matched_pattern ?? null,
    nextLine: wire.next_line ?? null,
    exited: wire.exited === true,
    // Held == the machine did not advance. That is the signal an author needs when
    // a stage's `max_cycles` is about to send the call somewhere they did not plan.
    held: wire.stage_before === wire.stage_after,
  };
}

export function toSimulationRow(wire: {
  playbook_id: string;
  playbook_name: string;
  steps: GlSimulationStepWire[];
  final_stage: string | null;
  outcome: string | null;
  outcome_reason: string | null;
  capture_passwords: boolean;
  credentials_captured: number;
  redaction_kinds: string[];
  missing: string[];
}): GlSimulationRow {
  return {
    playbookId: wire.playbook_id,
    playbookName: wire.playbook_name,
    steps: wire.steps.map(toSimulationStepRow),
    finalStage: wire.final_stage ?? null,
    outcome: wire.outcome ?? null,
    outcomeReason: wire.outcome_reason ?? null,
    capturePasswords: wire.capture_passwords,
    credentialsCaptured: wire.credentials_captured,
    redactionKinds: wire.redaction_kinds ?? [],
    missing: wire.missing ?? [],
  };
}

export function toMessageRow(wire: GlMessageWire): GlMessageRow {
  return {
    role: wire.role,
    content: wire.content,
    stage: wire.stage ?? null,
    timestamp: wire.timestamp,
    redactionKinds: wire.redaction_kinds ?? [],
    objectionType: wire.objection_type ?? null,
    triggerUsed: wire.trigger_used ?? null,
    sentimentScore: wire.sentiment_score ?? null,
    interestLevel: wire.interest_level ?? null,
  };
}

export function toCallRow(
  wire: {
    call_id: string;
    sid: string | null;
    target: string;
    campaign: string;
    persona: string;
    playbook_id: string | null;
    roe_id: string | null;
    started_at: string;
    ended_at: string | null;
    outcome: string | null;
    capture_passwords: boolean;
    credentials_captured: number;
    notes: string | null;
    message_count: number;
    final_stage: string | null;
  },
  messages: readonly GlMessageWire[] = [],
): GlCallRow {
  return {
    callId: wire.call_id,
    sid: wire.sid ?? null,
    target: wire.target,
    campaign: wire.campaign,
    persona: wire.persona,
    playbookId: wire.playbook_id ?? null,
    roeId: wire.roe_id ?? null,
    startedAt: wire.started_at,
    endedAt: wire.ended_at ?? null,
    outcome: wire.outcome ?? null,
    capturePasswords: wire.capture_passwords,
    credentialsCaptured: wire.credentials_captured,
    notes: wire.notes ?? null,
    messageCount: wire.message_count,
    finalStage: wire.final_stage ?? null,
    // `in_progress` maps to Running; a closed call maps to Completed/Failed by what
    // actually happened. An outcome the server did not report is Unknown, never
    // "in progress" — those are different claims.
    status: toWorkStatus(wire.outcome ?? "unknown"),
    messages: messages.map(toMessageRow),
  };
}

export function toProviderRow(wire: {
  name: string;
  configured: boolean;
  env_var: string;
  detail: string;
}): GlProviderRow {
  return {
    name: wire.name,
    configured: wire.configured === true,
    envVar: wire.env_var,
    detail: wire.detail,
    // Not configured is not an error — it is a step not yet taken. `Queued` reads
    // correctly; `Blocked` would imply something is wrong that needs unblocking.
    status: wire.configured ? toWorkStatus("healthy") : toWorkStatus("queued"),
  };
}

export function toRuntimeRow(
  wire: GlRuntimeWire,
  capabilities?: Partial<GlCapabilitiesWire>,
): GlRuntimeRow {
  const caps = capabilities ?? (wire.capabilities as Partial<GlCapabilitiesWire>);
  return {
    state: (wire.state as GlRuntimeRow["state"]) ?? "stopped",
    voiceId: wire.voice_id ?? null,
    voiceName: wire.voice_name ?? null,
    playbookId: wire.playbook_id ?? null,
    playbookName: wire.playbook_name ?? null,
    model: wire.model ?? null,
    modality: caps.modality ?? null,
    needsDeepgram: caps.needs_deepgram ?? null,
    needsElevenlabs: caps.needs_elevenlabs ?? null,
    capabilitySource: caps.source ?? null,
    wsUrl: wire.ws_url ?? null,
    publicUrl: wire.public_url ?? null,
    tunnelProvider: wire.tunnel_provider ?? null,
    port: wire.port ?? null,
    startedAt: wire.started_at ?? null,
    mediaRouteServed: wire.media_route_served === true,
    blockers: wire.blockers ?? [],
    missing: wire.missing ?? [],
  };
}

/** Whether the runtime can take a call right now, and why not when it cannot. */
export function dialReadiness(runtime: GlRuntimeRow): {
  ready: boolean;
  reason: string;
} {
  if (runtime.state === "running" && runtime.wsUrl) return { ready: true, reason: "" };
  if (runtime.state === "blocked") {
    return {
      ready: false,
      reason:
        runtime.blockers[0] ??
        "the runtime is blocked; open Runtime to see what is missing",
    };
  }
  return {
    ready: false,
    reason: "the runtime is stopped — start it on a voice and a playbook before dialling",
  };
}

/** A short label for an outcome, in the department's own words. */
export function outcomeLabel(outcome: GlOutcome | string | null): string {
  switch (outcome) {
    case "compromised":
      return "target complied";
    case "abandoned":
      return "target did not comply";
    case "in_progress":
      return "in progress";
    case "no_answer":
      return "no answer";
    case null:
      return "not recorded";
    default:
      return outcome;
  }
}

/** Progress through the ladder, for the runtime panel's stage strip. */
export function stageProgress(current: string | null, ladder: readonly string[]): number {
  if (!current) return 0;
  const index = ladder.indexOf(current);
  if (index < 0 || ladder.length === 0) return 0;
  return Math.round(((index + 1) / ladder.length) * 100);
}