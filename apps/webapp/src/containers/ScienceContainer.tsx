import { useCallback, useEffect, useState } from "react";

import { usePipelineStream } from "../lib/stream";
import { scienceApi } from "../lib/science/api";
import type { ClaimReviewView, InvariantParams, InvariantResult, RobustnessReport } from "../lib/science/types";
import { ScienceClaim, SciencePage } from "../pages/SciencePage";

const EMPTY_REVIEW: ClaimReviewView = {
  claim_id: "",
  statement: "",
  status: "",
  model_id: "",
  gates: { calibrated: false, null_model: false, robustness: false, reproduction: false },
  ladder_position: null,
  top_rung: 4,
  review_state: "review_pending",
  events: [],
};

export function ScienceContainer() {
  const [claims, setClaims] = useState<ScienceClaim[]>([]);
  const [reports, setReports] = useState<RobustnessReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [invariant, setInvariant] = useState<InvariantResult | null>(null);
  const [invariantLoading, setInvariantLoading] = useState(false);
  const [invariantError, setInvariantError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [claimsRaw, reportsRaw] = await Promise.all([
        scienceApi.listClaims(),
        scienceApi.listRobustness(),
      ]);
      const reviews = await Promise.all(
        claimsRaw.claims.map(async (claim) => {
          try {
            return await scienceApi.getReview(claim.claim_id);
          } catch {
            return { ...EMPTY_REVIEW, claim_id: claim.claim_id };
          }
        }),
      );
      const byId = new Map(reviews.map((r) => [r.claim_id, r]));
      setClaims(
        claimsRaw.claims.map((claim) => ({
          ...claim,
          review: byId.get(claim.claim_id) ?? EMPTY_REVIEW,
        })),
      );
      setReports(reportsRaw.reports);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Live reactivity: any pipeline mutation refeshes the science surface.
  usePipelineStream((event) => {
    if (event.event === "entity.updated" || event.event === "science.invariant") {
      void load();
    }
  });

  const comment = async (claimId: string, body: string) => {
    try {
      await scienceApi.comment(claimId, "webapp", body);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const runInvariant = async (params: InvariantParams) => {
    setInvariantLoading(true);
    setInvariantError(null);
    try {
      const result = await scienceApi.invariant(params);
      setInvariant(result);
    } catch (err) {
      setInvariantError(err instanceof Error ? err.message : String(err));
    } finally {
      setInvariantLoading(false);
    }
  };

  if (loading) return <p data-testid="loading-view">Loading science…</p>;
  if (error) return <p data-testid="error-view">Error: {error}</p>;

  return (
    <SciencePage
      claims={claims}
      reports={reports}
      onComment={comment}
      onRefresh={load}
      onInvariant={runInvariant}
      invariant={invariant}
      invariantLoading={invariantLoading}
      invariantError={invariantError}
    />
  );
}