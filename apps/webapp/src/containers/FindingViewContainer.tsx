import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { api, FindingView, LineageNode } from "../lib/api";
import { FindingViewPage, submitReview } from "../pages/FindingViewPage";

export function FindingViewContainer() {
  const { id } = useParams<{ id: string }>();
  const [finding, setFinding] = useState<(FindingView & { tenant_id: string }) | null>(null);
  const [lineage, setLineage] = useState<LineageNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) {
      setError("Finding ID is required");
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    Promise.all([api.getFinding(id), api.findingLineage(id)])
      .then(([findingData, lineageData]) => {
        setFinding(findingData);
        setLineage(lineageData.chain);
        setError(null);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <LoadingView message="Loading finding…" />;
  if (error) return <ErrorView error={error} />;
  if (!finding) return <ErrorView error="Finding not found" />;

  return (
    <FindingViewPage
      finding={finding}
      lineage={lineage}
      reviewApi={submitReview}
    />
  );
}

function LoadingView({ message }: { message: string }) {
  return (
    <section data-testid="loading-view" style={{ padding: "var(--xl, 1.25rem)" }}>
      <p>{message}</p>
    </section>
  );
}

function ErrorView({ error }: { error: string }) {
  return (
    <section data-testid="error-view" style={{ padding: "var(--xl, 1.25rem)" }}>
      <p style={{ color: "var(--c-danger)" }}>Error: {error}</p>
    </section>
  );
}
