import { useEffect, useState } from "react";

import { scienceApi } from "../lib/science/api";
import type { ExperimentRun, ReproductionResult } from "../lib/science/types";
import { ExperimentsPage } from "../pages/ExperimentsPage";

export function ExperimentContainer() {
  const [runs, setRuns] = useState<ExperimentRun[]>([]);
  const [reproductions, setReproductions] = useState<ReproductionResult[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      const res = await scienceApi.listExperiments();
      setRuns(res.runs);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const record = async () => {
    try {
      await scienceApi.recordExperiment({
        input_refs: ["OBS-" + Date.now()],
        output_refs: ["CL-" + Date.now()],
        seed: 42,
        pipeline_version: "science-fabric-0.1.0",
        tolerance: 1e-6,
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const reproduce = async (runId: string) => {
    try {
      const result = await scienceApi.reproduce(runId);
      setReproductions((prev) => [...prev, result]);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  if (error) return <p data-testid="error-view">Error: {error}</p>;
  return (
    <ExperimentsPage
      runs={runs}
      reproductions={reproductions}
      onRecord={record}
      onReproduce={reproduce}
    />
  );
}
