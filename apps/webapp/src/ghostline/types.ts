import type { WorkStatus } from "../ui/status";

/**
 * GhostLine row vocabulary (Feature 031).
 *
 * GhostLine is a DIFFERENT subject from the rest of the department's panels in one
 * specific way: its outputs are *live actions against people*, not telemetry. A kill
 * chain that failed to execute is a gap; a call that was placed is a thing that
 * happened to a person on a telephone. So the vocabulary here leans on two rules the
 * department already uses and adds a third:
 *
 *   §92  every status is a `WorkStatus`; an unrecognised donor spelling is `Unknown`,
 *        never a new colour.
 *   §99  a field an endpoint does not serve is `null` + the endpoint named in
 *        `missing[]` — never a zero, never a default.
 *   §101 an authorisation fact and a setup fact are different kinds of refusal and
 *        must not share a badge. `GateRefusal` is the gate saying no; `SetupGap` is
 *        something an operator fixes by setting a variable or installing a package.
 */

/** The panels — one CLI verb each, plus the two surfaces a CLI has no shape for. */
export type GlPanel =
  | "runtime"
  | "playbooks"
  | "simulate"
  | "voices"
  | "dialer"
  | "transcripts"
  | "analytics";

export const GL_PANELS: ReadonlyArray<GlPanel> = [
  "runtime",
  "playbooks",
  "simulate",
  "voices",
  "dialer",
  "transcripts",
  "analytics",
];

/** The donor's stage ladder, in canonical progression order. */
export const STAGE_LADDER: ReadonlyArray<string> = [
  "RAPPORT",
  "CREDIBILITY",
  "DISCOVERY",
  "VALIDATION",
  "ALIGNMENT",
  "PROOF",
  "URGENCY",
  "TRIAL_CLOSE",
  "OBJECTION",
  "CLOSE",
  "FOLLOW_UP",
  "REPORTING",
];

/** What each stage is for, so the ladder reads as a story rather than a list. */
export const STAGE_INTENT: Readonly<Record<string, string>> = {
  RAPPORT: "open and get permission to talk",
  CREDIBILITY: "earn the right to be believed",
  DISCOVERY: "learn the environment",
  VALIDATION: "confirm what was learned",
  ALIGNMENT: "tie their problem to the pretext",
  PROOF: "make it concrete",
  URGENCY: "compress the decision window",
  TRIAL_CLOSE: "test willingness",
  OBJECTION: "absorb the pushback",
  CLOSE: "ask for the thing",
  FOLLOW_UP: "land it warmly",
  REPORTING: "stop and write it up",
};

/** The donor's prosody names, per `taxonomy.PROSODY_VARIATIONS`. */
export const PERSONAS: ReadonlyArray<string> = [
  "excited",
  "confident",
  "thoughtful",
  "concerned",
  "urgent",
  "soothing",
  "professional",
];

/** Terminal outcomes the ledger can hold. `in_progress` is the non-terminal one. */
export type GlOutcome = "compromised" | "abandoned" | "in_progress" | "no_answer";

/** Runtime lifecycle, from the platform's own controller. */
export type GlRuntimeState = "stopped" | "blocked" | "running";

/** A refusal from the rules-of-engagement gate, or a setup fact. Never both. */
export type GlRefusal =
  | { readonly kind: "gate"; readonly code: string; readonly reason: string; readonly rejected: readonly string[] }
  | { readonly kind: "setup"; readonly reason: string }
  | { readonly kind: "absent"; readonly reason: string };

/** A stage's role in the ladder, derived from where it sits and what it declares. */
export type GlStageRole = "trust" | "discovery" | "persuasion" | "objection" | "closure" | "reporting";

export interface GlStageRow {
  readonly stage: string;
  readonly position: number;
  readonly persona: string | null;
  readonly prompt: string | null;
  readonly successRegex: string | null;
  readonly gotoOnSuccess: string | null;
  readonly gotoOnFail: string | null;
  readonly maxCycles: number;
  readonly silentUntil: number | null;
  readonly languageHint: string | null;
  readonly psychTriggers: readonly string[];
  readonly checkinLine: string | null;
  /** The stage's declared pattern fishes for a secret, so turns here are scrubbed. */
  readonly capturesCredential: boolean;
  readonly role: GlStageRole;
  readonly intent: string;
  /** True when the stage declares a branch, i.e. the ladder is not a straight line. */
  readonly branching: boolean;
  readonly status: WorkStatus;
}

export interface GlPlaybookRow {
  readonly playbookId: string;
  readonly name: string;
  readonly author: string | null;
  readonly version: number;
  readonly culture: string | null;
  readonly description: string | null;
  readonly stageCount: number;
  readonly firstStage: string;
  readonly stages: readonly GlStageRow[];
  readonly hasBranching: boolean;
  readonly personaName: string;
  readonly techniques: ReadonlyArray<{ readonly id: string; readonly reason: string }>;
  readonly mappingSource: string;
  readonly valid: boolean;
  readonly invalidReason: string | null;
  readonly missing: readonly string[];
}

export interface GlVoiceRow {
  readonly voiceId: string;
  readonly name: string;
  readonly origin: "cloned" | "premade" | string;
  readonly createdAt: string;
  readonly sampleRef: string | null;
  readonly sampleBytes: number | null;
  readonly notes: string | null;
  readonly status: WorkStatus;
}

export interface GlSimulationStepRow {
  readonly index: number;
  readonly utterance: string;
  readonly stageBefore: string;
  readonly stageAfter: string;
  readonly success: boolean;
  readonly cyclesRemaining: number;
  readonly matchedPattern: string | null;
  readonly nextLine: string | null;
  readonly exited: boolean;
  /** True when the stage did not change — the machine is still retrying. */
  readonly held: boolean;
}

export interface GlSimulationRow {
  readonly playbookId: string;
  readonly playbookName: string;
  readonly steps: readonly GlSimulationStepRow[];
  readonly finalStage: string | null;
  readonly outcome: GlOutcome | string | null;
  readonly outcomeReason: string | null;
  readonly capturePasswords: boolean;
  readonly credentialsCaptured: number;
  readonly redactionKinds: readonly string[];
  readonly missing: readonly string[];
}

export interface GlMessageRow {
  readonly role: string;
  readonly content: string;
  readonly stage: string | null;
  readonly timestamp: string;
  readonly redactionKinds: readonly string[];
  readonly objectionType: string | null;
  readonly triggerUsed: string | null;
  readonly sentimentScore: number | null;
  readonly interestLevel: number | null;
}

export interface GlCallRow {
  readonly callId: string;
  readonly sid: string | null;
  readonly target: string;
  readonly campaign: string;
  readonly persona: string;
  readonly playbookId: string | null;
  readonly roeId: string | null;
  readonly startedAt: string;
  readonly endedAt: string | null;
  readonly outcome: GlOutcome | string | null;
  readonly capturePasswords: boolean;
  readonly credentialsCaptured: number;
  readonly notes: string | null;
  readonly messageCount: number;
  readonly finalStage: string | null;
  readonly status: WorkStatus;
  readonly messages: readonly GlMessageRow[];
}

export interface GlProviderRow {
  readonly name: string;
  readonly configured: boolean;
  readonly envVar: string;
  readonly detail: string;
  readonly status: WorkStatus;
}

export interface GlRuntimeRow {
  readonly state: GlRuntimeState;
  readonly voiceId: string | null;
  readonly voiceName: string | null;
  readonly playbookId: string | null;
  readonly playbookName: string | null;
  readonly model: string | null;
  readonly modality: string | null;
  readonly needsDeepgram: boolean | null;
  readonly needsElevenlabs: boolean | null;
  readonly capabilitySource: string | null;
  readonly wsUrl: string | null;
  readonly publicUrl: string | null;
  readonly tunnelProvider: string | null;
  readonly port: number | null;
  readonly startedAt: string | null;
  readonly mediaRouteServed: boolean;
  readonly blockers: readonly string[];
  readonly missing: readonly string[];
}