import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import type cytoscape from "cytoscape";

import { api, Correlation, EntityView } from "../lib/api";
import { buildIntelGraph, stripProvenance } from "../lib/intelGraph";
import { scienceApi } from "../lib/science/api";
import type { InvariantResult } from "../lib/science/types";
import { buildTemporalSeriesFromTimeline } from "../lib/science/tdaLayer";
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
      // Observation/source/inferred nodes are not addressable entities — no-op
      // so the map keeps provenance nodes inert (I-3 honest empty).
      if (/^(OBS|SRC)-/.test(entityId)) return;
      // If the node is a non-materialised correlate, hydrate it; otherwise
      // re-fetch the neighbourhood so new edges appear live.
      void materialize(entityId);
    },
    [materialize],
  );

  const onSelect = useCallback((id: string | null) => setSelectedId(id), []);

  // ── Create / link (atomic entities as dynamic invariants) ─────────────
  const [actionNote, setActionNote] = useState<string | null>(null);
  const [linkMode, setLinkMode] = useState(false);
  const [linkSource, setLinkSource] = useState<string | null>(null);

  const toggleLink = useCallback(() => {
    setLinkMode((v) => {
      const next = !v;
      if (!next) setLinkSource(null);
      return next;
    });
  }, []);

  const clearActionNote = useCallback(() => setActionNote(null), []);

  const refreshNeighbourhood = useCallback(
    async (entityId: string) => {
      try {
        const corrData = await api.getCorrelations(entityId);
        setCorrelations((prev) => ({ ...prev, [entityId]: corrData.correlations }));
      } catch {
        // neighbourhood refresh is best-effort; keep the map intact
      }
    },
    [],
  );

  const handleCreateEntity = useCallback(
    async (name: string) => {
      const label = name.trim();
      if (!label) return;
      try {
        const res = await api.createEntity({
          canonical_identity: { account: label },
          aliases: [label],
          label,
        });
        await materialize(res.entity.entity_id);
        setActionNote(`Atomic entity created — ${res.entity.entity_id}`);
      } catch (err) {
        setActionNote(err instanceof Error ? err.message : String(err));
      }
    },
    [materialize],
  );

  const handleLinkTap = useCallback(
    async (targetId: string) => {
      if (linkSource === null) {
        setLinkSource(targetId);
        return;
      }
      const source = linkSource;
      setLinkMode(false);
      setLinkSource(null);
      if (targetId === source || /^(OBS|SRC)-/.test(targetId) || /^(OBS|SRC)-/.test(source)) {
        setActionNote("Cannot link provenance slots — pick two materialized entities");
        return;
      }
      try {
        const res = await api.linkEntities(source, {
          candidate_b: targetId,
          kind: "possible_match",
          reasons: ["analyst"],
        });
        // A correlate may stay non-materialized (no merge); hydrate if it is one.
        void materialize(targetId);
        await Promise.all([refreshNeighbourhood(source), refreshNeighbourhood(targetId)]);
        setActionNote(`Linked ${res.edge.candidate_a} ↔ ${res.edge.candidate_b} (${res.edge.kind})`);
      } catch (err) {
        setActionNote(err instanceof Error ? err.message : String(err));
      }
    },
    [linkSource, materialize, refreshNeighbourhood],
  );

  // ── Canvas controls (layout / zoom / fit) routed to the active cytoscape ──
  const cyRef = useRef<cytoscape.Core | null>(null);
  const [layoutName, setLayoutName] = useState("cose");
  const onGraphReady = useCallback((cy: cytoscape.Core) => {
    cyRef.current = cy;
    cy.on("destroy", () => {
      if (cyRef.current === cy) cyRef.current = null;
    });
  }, []);
  const onLayoutChange = useCallback((name: string) => {
    setLayoutName(name);
    const cy = cyRef.current;
    if (cy) {
      void cy
        .layout({ name, fit: true, animate: true } as cytoscape.LayoutOptions)
        .run();
    }
  }, []);
  const onZoomIn = useCallback(() => {
    const cy = cyRef.current;
    if (cy) cy.zoom(Math.min(cy.zoom() * 1.25, 3));
  }, []);
  const onZoomOut = useCallback(() => {
    const cy = cyRef.current;
    if (cy) cy.zoom(Math.max(cy.zoom() / 1.25, 0.15));
  }, []);
  const onFit = useCallback(() => {
    cyRef.current?.fit(undefined, 40);
  }, []);

  // ── TDA layer (optional overlay armable via toolbar icon) ────────────────
  const [tdaActive, setTdaActive] = useState(false);
  const [tdaLoading, setTdaLoading] = useState(false);
  const [invariants, setInvariants] = useState<Record<string, InvariantResult>>({});
  const [tdaNotes, setTdaNotes] = useState<Record<string, string>>({});
  const [provActive, setProvActive] = useState(true);

  const toggleTda = useCallback(async () => {
    if (tdaActive) {
      setTdaActive(false);
      return;
    }
    setTdaActive(true);
    setTdaLoading(true);
    setInvariants({});
    setTdaNotes({});
    const resolved: Record<string, InvariantResult> = {};
    const notes: Record<string, string> = {};
    // Honest sourcing (I-3): derive each series from the entity's own
    // observed_at timeline; entities without enough temporal data get a note,
    // never a fabricated series.
    const tasks = Object.entries(entities).flatMap(([id, entity]) => {
      const temporal = buildTemporalSeriesFromTimeline(entity.timeline ?? []);
      if (!temporal.series) {
        notes[id] = "insufficient temporal data";
        return [];
      }
      const task = scienceApi
        .invariant({ entity_id: id, series: temporal.series })
        .then((result) => {
          resolved[result.entity_id] = result;
        })
        .catch((err: unknown) => {
          notes[id] = err instanceof Error ? err.message : String(err);
        });
      return [task];
    });
    await Promise.all(tasks);
    setInvariants(resolved);
    setTdaNotes(notes);
    setTdaLoading(false);
  }, [tdaActive, entities]);

  const entityLabels = useMemo(() => {
    const labels: Record<string, string> = {};
    for (const [id, entity] of Object.entries(entities)) {
      const account = entity.canonical_identity["account"];
      labels[id] = account ? String(account) : entity.aliases[0] ?? id;
    }
    return labels;
  }, [entities]);

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

  const graph = useMemo(() => {
    const assembled = buildIntelGraph(entities, correlations);
    return provActive ? assembled : stripProvenance(assembled);
  }, [entities, correlations, provActive]);

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
      entityLabels={entityLabels}
      layoutName={layoutName}
      tdaActive={tdaActive}
      tdaLoading={tdaLoading}
      invariants={invariants}
      tdaNotes={tdaNotes}
      provActive={provActive}
      onSelect={onSelect}
      onExpand={onExpand}
      onMaterialize={materialize}
      onAddSeed={addSeed}
      onRemoveSeed={removeSeed}
      onGraphReady={onGraphReady}
      onLayoutChange={onLayoutChange}
      onZoomIn={onZoomIn}
      onZoomOut={onZoomOut}
      onFit={onFit}
      onToggleTda={toggleTda}
      onToggleProv={() => setProvActive((v) => !v)}
      linkMode={linkMode}
      linkSource={linkSource}
      actionNote={actionNote}
      onCreateEntity={handleCreateEntity}
      onLinkTap={handleLinkTap}
      onToggleLink={toggleLink}
      onDismissActionNote={clearActionNote}
    />
  );
}