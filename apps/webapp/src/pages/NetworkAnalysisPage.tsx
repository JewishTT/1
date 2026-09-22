import { FormEvent, useState } from "react";
import { EntityView } from "../lib/api";
import type {
  CommunityResult,
  DiagramFeaturesResult,
  GraphEdgeInput,
  HypergraphResult,
  NetworkMeasuresResult,
  PhodmsResult,
  TemporalPathsResult,
} from "../lib/science/types";
import { NetStatus, NetResult } from "../lib/science/netStatus";

interface Props {
  seeds: string[];
  edges: GraphEdgeInput[];
  entities: Record<string, EntityView>;
  selectedId: string | null;
  timelineSeriesLen: number | null;
  measures: NetStatus<NetworkMeasuresResult>;
  communities: NetStatus<CommunityResult>;
  hypergraph: NetStatus<HypergraphResult>;
  temporal: NetStatus<TemporalPathsResult>;
  diagramFeatures: NetStatus<DiagramFeaturesResult>;
  phodms: NetStatus<PhodmsResult>;
  onSelect: (id: string | null) => void;
  onAddSeed: (id: string) => void;
  onRemoveSeed: (id: string) => void;
  onRunMeasures: () => void;
  onRunCommunities: () => void;
  onRunHypergraph: () => void;
  onRunTemporal: () => void;
  onRunDiagramFeatures: () => void;
  onRunPhodms: () => void;
}

function KindCard({
  title,
  icon,
  badge,
  structural,
  onRun,
  children,
}: {
  title: string;
  icon: string;
  badge?: string;
  structural?: boolean;
  onRun: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="panel" style={{ borderRadius: 10, padding: "var(--md, 0.875rem)" }}>
      <div className="intel-canvas-head" style={{ borderBottom: 0, paddingBottom: 8 }}>
        <span className="op-label">
          {icon} {title}
        </span>
        <div className="chip-row">
          {badge ? <span className="status-chip">{badge}</span> : null}
          {structural ? <span className="status-chip">STRUCTURAL-ONLY</span> : null}
          <button type="button" className="btn btn-primary btn-sm" onClick={onRun}>
            RUN
          </button>
        </div>
      </div>
      {children}
    </div>
  );
}

function nodeLabel(entity?: EntityView): string {
  if (!entity) return "";
  return String(entity.canonical_identity["account"] ?? entity.aliases[0] ?? entity.entity_id);
}

export function NetworkAnalysisPage(props: Props) {
  const [seedInput, setSeedInput] = useState("");

  const submit = (ev: FormEvent) => {
    ev.preventDefault();
    const raw = seedInput.trim();
    if (!raw) return;
    props.onAddSeed(raw);
    setSeedInput("");
  };

  const primaryEntity = props.selectedId
    ? props.entities[props.selectedId]
    : props.seeds.length > 0 && props.entities[props.seeds[0]]
      ? props.entities[props.seeds[0]]
      : undefined;

  return (
    <section className="intel-board" data-testid="net-board">
      <aside className="intel-seedbank" data-testid="net-seedbank">
        <div className="intel-canvas-head" style={{ borderBottom: 0 }}>
          <span className="op-label">NETWORK SANDBOX</span>
          <span className="status-chip">{props.seeds.length} SEEDS · {props.edges.length} EDGES</span>
        </div>
        <form className="seed-add" onSubmit={submit} data-testid="net-seed-form">
          <input
            type="text"
            placeholder="add entity seed… e.g. ENT-2001"
            value={seedInput}
            onChange={(e) => setSeedInput(e.target.value)}
            aria-label="seed input"
          />
          <button type="submit" className="btn btn-primary btn-sm" disabled={!seedInput.trim()}>
            +
          </button>
        </form>
        <div className="seedbank-body">
          {props.seeds.length === 0 ? (
            <p className="panel-note" data-testid="net-seed-empty">
              No seeds. Add entity ids, or deep-link <code>/network?e=ENT-2001</code>.
            </p>
          ) : (
            props.seeds.map((id) => (
              <button
                key={id}
                type="button"
                className="seed-node"
                data-selected={props.selectedId === id}
                onClick={() => props.onSelect(id)}
              >
                <span className="seed-node-name">
                  <span>{nodeLabel(props.entities[id])}</span>
                  <span className="op-label">ENTITY</span>
                </span>
                <span className="seed-actions">
                  <span
                    role="button"
                    tabIndex={0}
                    className="header-link"
                    onClick={(e) => {
                      e.stopPropagation();
                      props.onRemoveSeed(id);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.stopPropagation();
                        props.onRemoveSeed(id);
                      }
                    }}
                  >
                    REMOVE
                  </span>
                </span>
              </button>
            ))
          )}
        </div>
        <div className="seedbank-body" style={{ flex: 0, borderTop: "1px solid var(--c-border)" }}>
          <span className="op-label">PRIMARY SUBJECT</span>
          <div className="chip-row">
            <span className="status-chip">{primaryEntity ? nodeLabel(primaryEntity) : "—"}</span>
            <span className="status-chip">
              {props.timelineSeriesLen === null
                ? "NO SERIES"
                : `TL ${props.timelineSeriesLen} PTS`}
            </span>
          </div>
          <p className="panel-note">
            Series is derived honestly from the subject's own <code>observed_at</code> timeline
            (I-1/I-3) — no fabricated points.
          </p>
        </div>
      </aside>

      <div className="net-grid" data-testid="net-canvas">
        <KindCard
          title="NETWORK MEASURES"
          icon="◉"
          structural
          onRun={props.onRunMeasures}
          badge={props.edges.length > 0 ? `${props.edges.length} EDGES` : undefined}
        >
          <NetResult status={props.measures} />
          {props.measures.state === "done" && (
            <div className="net-result" data-testid="measures-result">
              <div className="chip-row">
                <span className="status-chip">n {props.measures.data.n_nodes}</span>
                <span className="status-chip">e {props.measures.data.n_edges}</span>
                <span className="status-chip">density {props.measures.data.density.toFixed(3)}</span>
                <span className="status-chip">small-world σ {props.measures.data.small_world_sigma?.toFixed(3) ?? "—"}</span>
                <span className="status-chip">assort {props.measures.data.assortativity.toFixed(3)}</span>
              </div>
              <div className="net-pair">
                <pre>{JSON.stringify(
                  {
                    avg_degree: props.measures.data.avg_degree,
                    avg_clustering: props.measures.data.avg_clustering,
                    transitivity: props.measures.data.transitivity,
                    degree_gini: props.measures.data.degree_gini,
                    power_law: props.measures.data.power_law_alpha,
                    degree_centrality: props.measures.data.degree_centrality,
                    degree_distribution: props.measures.data.degree_distribution,
                  },
                  null, 2,
                )}</pre>
              </div>
            </div>
          )}
        </KindCard>

        <KindCard title="COMMUNITIES" icon="⊕" structural onRun={props.onRunCommunities}>
          <NetResult status={props.communities} />
          {props.communities.state === "done" && (
            <div className="net-result" data-testid="communities-result">
              <div className="chip-row">
                <span className="status-chip">{props.communities.data.community_count} COMMUNITIES</span>
                <span className="status-chip">Q {props.communities.data.modularity_q.toFixed(3)}</span>
              </div>
              <div className="net-pair">
                <pre>{JSON.stringify(props.communities.data.communities, null, 2)}</pre>
              </div>
            </div>
          )}
        </KindCard>

        <KindCard title="HYPERGRAPH" icon="⋉" structural onRun={props.onRunHypergraph}>
          <NetResult status={props.hypergraph} />
          {props.hypergraph.state === "done" && (
            <div className="net-result" data-testid="hypergraph-result">
              <div className="chip-row">
                <span className="status-chip">{props.hypergraph.data.num_edges} EDGES</span>
                <span className="status-chip">order {props.hypergraph.data.order}</span>
                <span className="status-chip">avg deg {props.hypergraph.data.average_node_degree.toFixed(2)}</span>
              </div>
              <div className="net-pair">
                <pre>{JSON.stringify(
                  {
                    edge_sizes: props.hypergraph.data.edge_sizes,
                    hyperedge_sizes: props.hypergraph.data.hyperedge_sizes,
                    incidence_density: props.hypergraph.data.incidence_density,
                  },
                  null, 2,
                )}</pre>
              </div>
            </div>
          )}
        </KindCard>

        <KindCard title="TEMPORAL PATHS" icon="▸" structural onRun={props.onRunTemporal}>
          <NetResult status={props.temporal} />
          {props.temporal.state === "done" && (
            <div className="net-result" data-testid="temporal-result">
              <div className="chip-row">
                <span className="status-chip">motifs {JSON.stringify(props.temporal.data.motifs)}</span>
              </div>
              <div className="net-pair">
                <pre>{JSON.stringify(
                  {
                    distance_matrix: props.temporal.data.distance_matrix,
                    timeline: props.temporal.data.timeline,
                  },
                  null, 2,
                )}</pre>
              </div>
            </div>
          )}
        </KindCard>

        <KindCard
          title="DIAGRAM FEATURES"
          icon="◬"
          structural
          onRun={props.onRunDiagramFeatures}
          badge={props.timelineSeriesLen === null ? "INSUFFICIENT TEMPORAL DATA" : `${props.timelineSeriesLen} PTS`}
        >
          <NetResult status={props.diagramFeatures} />
          {props.diagramFeatures.state === "done" && (
            <div className="net-result" data-testid="diagram-features-result">
              <div className="chip-row">
                <span className="status-chip">provider {props.diagramFeatures.data.provider}</span>
                <span className="status-chip">digest {props.diagramFeatures.data.features_digest.slice(0, 12)}…</span>
              </div>
              <div className="net-pair">
                <pre>{JSON.stringify(props.diagramFeatures.data.features, null, 2)}</pre>
              </div>
              {props.diagramFeatures.data.drift && (
                <div className="net-pair">
                  <pre>{JSON.stringify(props.diagramFeatures.data.drift, null, 2)}</pre>
                </div>
              )}
            </div>
          )}
        </KindCard>

        <KindCard title="PHODMS INVARIANT" icon="⌗" structural onRun={props.onRunPhodms}>
          <NetResult status={props.phodms} />
          {props.phodms.state === "done" && (
            <div className="net-result" data-testid="phodms-result">
              <div className="chip-row">
                <span className="status-chip">T {props.phodms.data.n_times}</span>
                <span className="status-chip">P {props.phodms.data.n_points}</span>
                <span className="status-chip">r {props.phodms.data.n_thresholds}</span>
                <span className="status-chip">{props.phodms.data.rank_invariant.verdict}</span>
              </div>
              <div className="net-pair">
                <pre>{JSON.stringify(props.phodms.data.rank_invariant, null, 2)}</pre>
              </div>
            </div>
          )}
        </KindCard>
      </div>
    </section>
  );
}