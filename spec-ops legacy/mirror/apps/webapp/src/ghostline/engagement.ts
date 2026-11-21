import type { WorkStatus } from "../ui/status";

/**
 * Engagement-fabric derivation (Feature 032).
 *
 * Two tiny functions, both here because the panel is not the right place for a rung
 * name and because the mapping is the kind of thing that must not drift between the
 * board and a future drill-down: `Stage` is a number on the wire and a word on screen,
 * and nothing else in the app is allowed to own that translation.
 */

/**
 * The rung name for a depth value.
 *
 * Returns `unreached` for 0 and for anything above the ladder rather than an empty
 * string — a blank label on a bar is a missing answer, and this is the one place a
 * reader is looking at "how far did they get".
 */
export function stageKeyFor(depth: number): string {
  const keys = [
    "unreached",
    "dispatched",
    "engaged",
    "landed",
    "advanced",
    "ask",
    "conceded",
    "resisted",
  ] as const;
  return keys[depth] ?? "beyond-ladder";
}

/**
 * How a subject row should read.
 *
 * Conceded and resisted are mutually exclusive by construction on the server — a
 * subject's deepest rung is one value — but both are surfaced because a supervisor
 * looking at "who keeps falling for this" and one looking at "who is reporting" want
 * opposite halves of the same board, and neither should have to filter.
 */
export function subjectDisposition(subject: {
  conceded_campaigns: readonly string[];
  resisted_campaigns: readonly string[];
}): { status: WorkStatus; label: string } {
  if (subject.conceded_campaigns.length > subject.resisted_campaigns.length) {
    return { status: "Failed", label: "conceded" };
  }
  if (subject.resisted_campaigns.length > 0) {
    return { status: "Healthy", label: "resisted" };
  }
  return { status: "Unknown", label: "no signal" };
}
