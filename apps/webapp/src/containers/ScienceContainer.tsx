import { useEffect, useState } from "react";

import { scienceApi } from "../lib/science/api";
import type { ClaimReviewView, RobustnessReport } from "../lib/science/types";
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

  const load = async () => {
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
  };

  useEffect(() => {
    void load();
  }, []);

  const comment = async (claimId: string, body: string) => {
    try {
      await scienceApi.comment(claimId, "webapp", body);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  if (loading) return <p data-testid="loading-view">Loading science…</p>;
  if (error) return <p data-testid="error-view">Error: {error}</p>;

  return <SciencePage claims={claims} reports={reports} onComment={comment} onRefresh={load} />;
}
