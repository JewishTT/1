import { useEffect, useState } from "react";

import { scienceApi } from "../lib/science/api";
import type { CoverageView, HypothesisWithCoverage, RankedOpportunity } from "../lib/science/types";
import { HypothesesPage } from "../pages/HypothesesPage";

export function HypothesisContainer() {
  const [hypotheses, setHypotheses] = useState<HypothesisWithCoverage[]>([]);
  const [plan, setPlan] = useState<RankedOpportunity[]>([]);
  const [coverage, setCoverage] = useState<CoverageView | null>(null);
  const [projectId] = useState("P-science");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async (project = projectId) => {
    setLoading(true);
    try {
      const hypRaw = await scienceApi.listHypotheses(project);
      setHypotheses(
        (hypRaw.hypotheses ?? []).map((h) => ({ ...h, evidence_count: h.evidence_count ?? 0 })),
      );
      setError(null);
      try {
        setCoverage(await scienceApi.coverage(project));
      } catch {
        setCoverage(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const register = async (project: string, text: string) => {
    try {
      await scienceApi.proposeHypothesis(project, text);
      await load(project);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const attach = async (hypothesisId: string) => {
    try {
      await scienceApi.attachEvidence(hypothesisId, {
        observation_id: `OBS-${Date.now()}`,
        direction: "supports",
        weight: 0.5,
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const discard = async (hypothesisId: string) => {
    try {
      await scienceApi.discardHypothesis(hypothesisId, "webapp", "superseded by new evidence");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const runPlan = async () => {
    try {
      const res = await scienceApi.planCollection(projectId, []);
      setPlan(
        res.plan.map((o) => ({
          opportunity_id: o.opportunity_id,
          expected_gain: o.expected_gain,
          discriminates: [],
        })),
      );
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  if (loading && hypotheses.length === 0)
    return <p data-testid="loading-view">Loading hypotheses…</p>;
  if (error) return <p data-testid="error-view">Error: {error}</p>;

  return (
    <HypothesesPage
      hypotheses={hypotheses}
      plan={plan}
      coverage={coverage}
      onRegister={register}
      onAttach={attach}
      onDiscard={discard}
      onPlan={runPlan}
      onRefresh={() => void load()}
    />
  );
}
