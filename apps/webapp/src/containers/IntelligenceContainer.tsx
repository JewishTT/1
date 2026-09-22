import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { api, Correlation, EntityView } from "../lib/api";
import { buildIntelGraph } from "../lib/intelGraph";
import { StreamEvent, usePipelineStream } from "../lib/stream";
import { IntelligencePage } from "../pages/IntelligencePage";

interface FeedEntry {
  id: string;
  event: StreamEvent;
  at: string;
}

let feedCounter = 0;

function LoadingView({ message }: { message: string }) {
  return (
    <section data-testid="loading-view" style={{ padding: "var(--xl, 1.25rem)" }}>
      <p>{message}</p>
    </section>
  );
}

function ErrorView({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <section data-testid="error-view" style={{ padding: "var(--xl, 1.25rem)" }}>
      <p style={{ color: "var(--c-danger)" }}>Error: {error}</p>
      <button type="button" onClick={() => void onRetry()} className="btn btn-sm">
        Retry
      </button>
    </section>
  );
}

export function IntelligenceContainer() {
  const [params] = useSearchParams();
  const [seeds, setSeeds] = useState<string[]>([]);
  const [entities, setEntities] = useState<Record<string, EntityView>>({});
  const [correlations, setCorrelations] = useState<Record<string, Correlation[]>>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [feed, setFeed] = useState<FeedEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const inFlight = useRef<Set<string>>(new Set());

  const materialize = useCallback(async (entityId: string) => {
    if (inFlight.current.has(entityId)) return;
    inFlight.current.add(entityId);
    setError(null);
    try {
      const [entityData, corrData] = await Promise.all([
        api.getEntity(entityId),
        api.getCorrelations(entityId),
      ]);
      setEntities((prev) => ({ ...prev, [entityId]: entityData as EntityView }));
      setCorrelations((prev) => ({ ...prev, [entityId]: corrData.correlations }));
      setSeeds((prev) => (prev.includes(entityId) ? prev : [...prev, entityId]));
    } catch (err) {
      // Materialising a correlate whose identity is not yet in the catalog is
      // informational — surface it but keep the map intact (honest I-3).
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      inFlight.current.delete(entityId);
      setLoaded(true);
    }
  }, []);

  const addSeed = useCallback(
    (entityId: string) => {
      void materialize(entityId);
    },
    [materialize],
  );

  const removeSeed = useCallback((entityId: string) => {
    setSeeds((prev) => prev.filter((s) => s !== entityId));
    setEntities((prev) => {
      const next = { ...prev };
      delete next[entityId];
      return next;
    });
    setCorrelations((prev) => {
      const next = { ...prev };
      delete next[entityId];
      return next;
    });
    setSelectedId((prev) => (prev === entityId ? null : prev));
  }, []);

  const onExpand = useCallback(
    (entityId: string) => {
      // If the node is a non-materialised correlate, hydrate it; otherwise
      // re-fetch the neighbourhood so new edges appear live.
      void materialize(entityId);
    },
    [materialize],
  );

  const onSelect = useCallback((id: string | null) => setSelectedId(id), []);

  // Deep-link seeds: /intel?entity=ENT-2001 or ?entity=A,B
  useEffect(() => {
    const raw = params.get("entity");
    if (!raw) {
      setLoaded(true);
      return;
    }
    for (const id of raw.split(",").map((s) => s.trim()).filter(Boolean)) void materialize(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  usePipelineStream((event) => {
    setFeed((prev) => [
      { id: `ev-${feedCounter++}`, event, at: new Date().toISOString() },
      ...prev,
    ].slice(0, 9));
  });

  const graph = useMemo(
    () => buildIntelGraph(entities, correlations),
    [entities, correlations],
  );

  if (!loaded) return <LoadingView message="Wiring the intelligence map…" />;
  if (error && seeds.length === 0) return <ErrorView error={error} onRetry={() => void materialize(seeds[0] ?? "")} />;

  return (
    <IntelligencePage
      graph={graph}
      seeds={seeds}
      entities={entities}
      correlations={correlations}
      selectedId={selectedId}
      feed={feed}
      onSelect={onSelect}
      onExpand={onExpand}
      onMaterialize={materialize}
      onAddSeed={addSeed}
      onRemoveSeed={removeSeed}
    />
  );
}