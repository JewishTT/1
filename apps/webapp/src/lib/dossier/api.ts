/**
 * Dossier API client.
 *
 * Three calls, matching the three costs on the server: `enrich` reaches the outside world
 * and is slow, `getDossier` is a pure read, `listSubjects` is cheaper still. The client does
 * not merge them and does not cache: a dossier is a claim about what is known right now,
 * and a stale one shown next to a fresh "swept" button is how an analyst ends up reading
 * yesterday's absence as today's finding.
 */

import { clientFor } from "../http";
import type { Dossier, EnrichResult, SubjectSummary } from "./types";

const API_BASE = "/api/v1";

// Fourth copy of the same helper when this file was written; see lib/http.ts.
const request = clientFor(API_BASE);

export interface EnrichParams {
  subject: string;
  kind?: string;
  max_sources?: number;
  depth?: number;
}

export const dossierApi = {
  /** Run a sweep over the live catalogue and persist it. Slow by nature. */
  enrich(params: EnrichParams): Promise<EnrichResult> {
    return request<EnrichResult>("/dossier/enrich", {
      method: "POST",
      body: JSON.stringify(params),
    });
  },

  getDossier(entityRef: string): Promise<Dossier> {
    return request<Dossier>(`/dossier/${encodeURIComponent(entityRef)}`);
  },

  listSubjects(): Promise<{ subjects: SubjectSummary[] }> {
    return request<{ subjects: SubjectSummary[] }>("/dossier");
  },
};
