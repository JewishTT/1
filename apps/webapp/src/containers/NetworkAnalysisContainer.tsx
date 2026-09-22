import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { api, Correlation, EntityView } from "../lib/api";
import { networkApi } from "../lib/science/api";
import type {
  CommunityResult,
  DiagramFeaturesResult,
  GraphEdgeInput,
  HypergraphResult,
  NetworkMeasuresResult,
  PhodmsResult,
  TemporalPathsResult,
} from "../lib/science/types";
import { buildTemporalSeriesFromTimeline } from "../lib/science/tdaLayer";
import { NetStatus } from "../lib/science/netStatus";
import { NetworkAnalysisPage } from "../pages/NetworkAnalysisPage";

export function NetworkAnalysisContainer() {
  const [params] = useSearchParams();
  const [entities, setEntities] = useState<Record<string, EntityView>>({});
  const [correlations, setCorrelations] = useState<Record<string, Correlation[]>>({});
  const [seeds, setSeeds] = useState<string[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const inFlight = useRef<Set<string>>(new Set());

  const [measures, setMeasures] = useState<NetStatus<NetworkMeasuresResult>>({ state: "idle" });
  const [communities, setCommunities] = useState<NetStatus<CommunityResult>>({ state: "idle" });
  const [hypergraph, setHypergraph] = useState<NetStatus<HypergraphResult>>({ state: "idle" });
  const [temporal, setTemporal] = useState<NetStatus<TemporalPathsResult>>({ state: "idle" });
  const [diagramFeatures, setDiagramFeatures] = useState<NetStatus<DiagramFeaturesResult>>({ state: "idle" });
  const [phodms, setPhodms] = useState<NetStatus<PhodmsResult>>({ state: "idle" });

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
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      inFlight.current.delete(entityId);
      setLoaded(true);
    }
  }, []);

  const addSeed = useCallback((id: string) => void materialize(id), [materialize]);
  const removeSeed = useCallback((id: string) => {
    setSeeds((prev) => prev.filter((s) => s !== id));
    setEntities((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
    setCorrelations((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
    setSelectedId((prev) => (prev === id ? null : prev));
  }, []);

  const edges: GraphEdgeInput[] = useMemo(() => {
    const out: GraphEdgeInput[] = [];
    const seen = new Set<string>();
    for (const list of Object.values(correlations)) {
      for (const c of list) {
        const src = c.candidate_a;
        const dst = c.candidate_b;
        if (!src || !dst) continue;
        const key = `${src}|${dst}`;
        if (seen.has(key)) continue;
        seen.add(key);
        out.push({ source: src, target: dst, edge_type: c.kind });
      }
    }
    return out;
  }, [correlations]);

  const activeEntity = selectedId
    ? entities[selectedId]
    : seeds.length > 0 && entities[seeds[0]]
      ? entities[seeds[0]]
      : undefined;

  // Honest series: derived from the primary entity's own observed_at timeline,
  // never fabricated (I-1/I-3). Missing temporal data -> structural_only deferral.
  const timelineSeries = useMemo(() => {
    if (!activeEntity) return undefined;
    const temporal = buildTemporalSeriesFromTimeline(activeEntity.timeline ?? []);
    return temporal.series ?? undefined;
  }, [activeEntity]);

  const runMeasures = useCallback(async () => {
    if (edges.length === 0) {
      setMeasures({ state: "error", message: "No edges — add entity seeds first." });
      return;
    }
    setMeasures({ state: "loading" });
    try {
      setMeasures({ state: "done", data: await networkApi.measures(edges) });
    } catch (err) {
      setMeasures({ state: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }, [edges]);

  const runCommunities = useCallback(async () => {
    if (edges.length === 0) {
      setCommunities({ state: "error", message: "No edges — add entity seeds first." });
      return;
    }
    setCommunities({ state: "loading" });
    try {
      setCommunities({ state: "done", data: await networkApi.communities(edges) });
    } catch (err) {
      setCommunities({ state: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }, [edges]);

  const runHypergraph = useCallback(async () => {
    const observations: Record<string, string[]> = Object.fromEntries(
      Object.entries(entities).map(([id, e]) => [
        id,
        e.evidence.map((ev) => String(ev.evidence_id ?? ev["observation_id"] ?? ev.evidence_id)),
      ]),
    );
    setHypergraph({ state: "loading" });
    try {
      setHypergraph({ state: "done", data: await networkApi.hypergraph(observations) });
    } catch (err) {
      setHypergraph({ state: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }, [entities]);

  const runTemporal = useCallback(async () => {
    const timedEdges = edges.flatMap((e, i) => [
      { source: e.source, target: e.target, t: i, edge_id: `T-${i}` },
    ]);
    setTemporal({ state: "loading" });
    try {
      setTemporal({
        state: "done",
        data: await networkApi.temporal(timedEdges, edges[0]?.source, edges[0]?.target),
      });
    } catch (err) {
      setTemporal({ state: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }, [edges]);

  const runDiagramFeatures = useCallback(async () => {
    if (!activeEntity || !timelineSeries) {
      setDiagramFeatures({ state: "error", message: "No entity or insufficient temporal data." });
      return;
    }
    setDiagramFeatures({ state: "loading" });
    try {
      setDiagramFeatures({
        state: "done",
        data: await networkApi.diagramFeatures({
          entity_id: activeEntity.entity_id,
          series: timelineSeries,
          lag: 2,
          embed_dim: 2,
          max_dim: 1,
        }),
      });
    } catch (err) {
      setDiagramFeatures({ state: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }, [activeEntity, timelineSeries]);

  const runPhodms = useCallback(async () => {
    if (!timelineSeries || timelineSeries.length === 0) {
      setPhodms({ state: "error", message: "No temporal data — building point clouds from series." });
      return;
    }
    // Honest bounded clouds: chunk the observed series into <=8-point windows,
    // at most 6 time slices (phodms persistence contract).
    const clouds: number[][][] = [];
    const window = 8;
    const times = Math.min(6, Math.max(1, Math.ceil(timelineSeries.length / window)));
    for (let i = 0; i < times; i++) {
      clouds.push([timelineSeries.slice(i * window, i * window + window)]);
    }
    setPhodms({ state: "loading" });
    try {
      setPhodms({ state: "done", data: await networkApi.phodms({ clouds }) });
    } catch (err) {
      setPhodms({ state: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }, [timelineSeries]);

  useEffect(() => {
    const raw = params.get("e");
    if (!raw) {
      setLoaded(true);
      return;
    }
    for (const id of raw.split(",").map((s) => s.trim()).filter(Boolean)) void materialize(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  if (!loaded) {
    return (
      <section data-testid="loading-view" style={{ padding: "var(--xl, 1.25rem)" }}>
        <p>Wiring the network sandbox…</p>
      </section>
    );
  }
  if (error && seeds.length === 0) {
    return (
      <section data-testid="error-view" style={{ padding: "var(--xl, 1.25rem)" }}>
        <p style={{ color: "var(--c-danger)" }}>Error: {error}</p>
        <button type="button" className="btn btn-sm" onClick={() => void materialize(seeds[0] ?? "")}>
          Retry
        </button>
      </section>
    );
  }

  return (
    <NetworkAnalysisPage
      seeds={seeds}
      entities={entities}
      edges={edges}
      selectedId={selectedId}
      timelineSeriesLen={timelineSeries?.length ?? null}
      measures={measures}
      communities={communities}
      hypergraph={hypergraph}
      temporal={temporal}
      diagramFeatures={diagramFeatures}
      phodms={phodms}
      onSelect={setSelectedId}
      onAddSeed={addSeed}
      onRemoveSeed={removeSeed}
      onRunMeasures={() => void runMeasures()}
      onRunCommunities={() => void runCommunities()}
      onRunHypergraph={() => void runHypergraph()}
      onRunTemporal={() => void runTemporal()}
      onRunDiagramFeatures={() => void runDiagramFeatures()}
      onRunPhodms={() => void runPhodms()}
    />
  );
}