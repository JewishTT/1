import {
  WORKSPACE_VIEWS,
  isWorkspaceView,
  type WorkspaceObjectKind,
  type WorkspaceSelection,
} from "./types";
import type { WorkspaceContextPatch } from "./store";

/**
 * URL <-> workspace context (§77).
 *
 * "the URL preserves context, e.g. `/investigations/42?view=graph&entity=ENT-182`;
 *  a refresh must not zero the workspace."
 *
 * The URL is a *projection* of the workspace context, never the source of
 * truth for anything else. It carries exactly the keys in
 * `WorkspaceContextPatch`; layout widths, density, theme and palette state are
 * deliberately absent, so a shared link never overrides how someone has
 * arranged their own screen.
 *
 * Round-tripping is total in both directions: `parse` is lenient about unknown
 * or malformed values (a hand-edited URL degrades to defaults, never throws),
 * and `build` omits defaults so the common case stays a clean path.
 */

/**
 * Query key per selectable kind: `?entity=ENT-182`.
 *
 * `Investigation` is deliberately absent. The investigation being worked is
 * addressed by the *path* (`/investigations/42`), not by a query parameter —
 * carrying it twice would give one fact two spellings and let them disagree.
 * See `WorkspaceContextPatch.investigation`, which is path-derived and is
 * neither serialised nor parsed here.
 */
const KIND_TO_PARAM: Record<Exclude<WorkspaceObjectKind, "Investigation">, string> = {
  Entity: "entity",
  Observation: "observation",
  Capture: "capture",
  Claim: "claim",
  Finding: "finding",
  AcquisitionTask: "task",
  AcquisitionRun: "run",
  Source: "source",
};

const PARAM_TO_KIND = new Map<string, WorkspaceObjectKind>(
  (Object.entries(KIND_TO_PARAM) as Array<[WorkspaceObjectKind, string]>).map(([kind, param]) => [
    param,
    kind,
  ]),
);

export const VIEW_PARAM = "view";
export const EVIDENCE_QUERY_PARAM = "q";
export const TIME_FROM_PARAM = "from";
export const TIME_TO_PARAM = "to";

/**
 * Parse a query string into a context patch. Unknown view values, unknown
 * selection params and unrecognised ids are ignored rather than throwing, so a
 * stale or hand-edited bookmark lands on a usable screen.
 */
export function parseWorkspaceSearch(search: string): WorkspaceContextPatch {
  const params = new URLSearchParams(search);
  const patch: WorkspaceContextPatch = {};

  const view = params.get(VIEW_PARAM);
  if (isWorkspaceView(view)) patch.view = view;

  const evidenceQuery = params.get(EVIDENCE_QUERY_PARAM);
  if (evidenceQuery) patch.evidenceQuery = evidenceQuery;

  const timeFrom = params.get(TIME_FROM_PARAM);
  if (timeFrom) patch.timeFrom = timeFrom;

  const timeTo = params.get(TIME_TO_PARAM);
  if (timeTo) patch.timeTo = timeTo;

  // First matching selection param wins, in the fixed order of the kinds above,
  // so `?entity=X&observation=Y` resolves deterministically.
  for (const [param, kind] of PARAM_TO_KIND) {
    const id = params.get(param);
    if (id) {
      patch.selection = { kind, id } satisfies WorkspaceSelection;
      break;
    }
  }

  return patch;
}

/**
 * Serialise a context patch to a query string (without the leading `?`).
 * Defaults are omitted: `overview` and an absent selection produce "".
 *
 * `patch.investigation` is intentionally not written — see `KIND_TO_PARAM`.
 */
export function buildWorkspaceSearch(patch: WorkspaceContextPatch): string {
  const params = new URLSearchParams();

  if (patch.view && patch.view !== "overview") params.set(VIEW_PARAM, patch.view);
  // The Investigation kind is path-addressed (see KIND_TO_PARAM), so it has no
  // query spelling; a caller that selects the investigation itself gets the
  // path handled by buildWorkspacePath instead.
  if (patch.selection && patch.selection.kind !== "Investigation") {
    params.set(KIND_TO_PARAM[patch.selection.kind], patch.selection.id);
  }
  if (patch.evidenceQuery) params.set(EVIDENCE_QUERY_PARAM, patch.evidenceQuery);
  if (patch.timeFrom) params.set(TIME_FROM_PARAM, patch.timeFrom);
  if (patch.timeTo) params.set(TIME_TO_PARAM, patch.timeTo);

  const query = params.toString();
  return query === "" ? "" : `?${query}`;
}

/**
 * Full path for the current work context: `/investigations/42?view=graph&entity=ENT-182`.
 * Used both by the address-bar sync and by "copy link to selection".
 */
export function buildWorkspacePath(investigationId: string, patch: WorkspaceContextPatch): string {
  const base = investigationId === "" ? "/investigations" : `/investigations/${investigationId}`;
  return `${base}${buildWorkspaceSearch(patch)}`;
}

/** Every view id, in canvas order — used by the command registry and tests. */
export const ALL_VIEWS = WORKSPACE_VIEWS;