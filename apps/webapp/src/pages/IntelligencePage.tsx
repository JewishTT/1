import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { Correlation, EntityView } from "../lib/api";
import { IntelGraph, IntelNode } from "../lib/intelGraph";
import { StreamEvent } from "../lib/stream";
import { IntelligenceGraph } from "../components/IntelligenceGraph";

interface Props {
  graph: IntelGraph;
  seeds: string[];
  entities: Record<string, EntityView>;
  correlations: Record<string, Correlation[]>;
  selectedId: string | null;
  feed: Array<{ id: string; event: StreamEvent; at: string }>;
  onSelect: (id: string | null) => void;
  onExpand: (id: string) => void;
  onMaterialize: (id: string) => void;
  onAddSeed: (id: string) => void;
  onRemoveSeed: (id: string) => void;
}

function nodeLabel(entity?: EntityView): string {
  if (!entity) return "";
  return String(entity.canonical_identity["account"] ?? entity.aliases[0] ?? entity.entity_id);
}

function feedText(event: StreamEvent): string {
  const d = event.data as Record<string, unknown> | null;
  if (!d) return event.event;
  switch (event.event) {
    case "entity.updated":
      return `${event.event} · ${String(d.entity_id ?? d.review_id ?? "?")} ${String(d.event ?? "")}`.trim();
    case "science.invariant":
      return `${event.event} · ${String(d.entity_id ?? "?")} digest=${String(d.digest ?? "…").slice(0, 10)}`;
    case "pipeline.advance":
      return `${event.event} · step=${String(d.step ?? "?")}`;
    default:
      return event.event;
  }
}

function IntroFeed({ feed }: { feed: Props["feed"] }) {
  return (
    <div className="intel-feed" data-testid="intel-feed">
      {feed.length > 0 ? (
        <div className="intel-feed-slider">
          {feed.map((f) => (
            <div key={f.id} className="feed-item" data-kind={f.event.event} data-testid="intel-event">
              <div className="feed-head">
                <span className="feed-kind">{f.event.event}</span>
                <span className="feed-time">{f.at.slice(11, 19)}</span>
              </div>
              <div className="feed-body">{feedText(f.event)}</div>
            </div>
          ))}
        </div>
      ) : (
        <p className="intel-feed-placeholder">— SSE link idle · awaiting pipeline events</p>
      )}
    </div>
  );
}

function IntelInspector({
  node,
  entity,
  onExpand,
  onMaterialize,
}: {
  node: IntelNode;
  entity?: EntityView;
  onExpand: (id: string) => void;
  onMaterialize: (id: string) => void;
}) {
  return (
    <aside className="intel-inspector" data-testid="intel-inspector">
      <div className="intel-inspector-head">
        <span className="op-label">Node Inspector</span>
        <span className="status-chip">{node.kind}</span>
      </div>
      <div className="intel-inspector-body">
        <div>
          <div className="op-label">IDENTITY</div>
          <div className="insp-row" data-testid="inspector-id">
            {node.label}
          </div>
        </div>
        {entity ? (
          <>
            <div>
              <div className="op-label">ALIASES</div>
              <div className="insp-row">{entity.aliases.length > 0 ? entity.aliases.join(" · ") : "—"}</div>
            </div>
            <div>
              <div className="op-label">SUPPORTING ASSERTIONS</div>
              <div className="insp-row">{entity.supporting_assertions.join(", ") || "—"}</div>
            </div>
            <div className="chip-row">
              <span className="status-chip">EV {entity.evidence.length}</span>
              <span className="status-chip">TL {entity.timeline.length}</span>
              <span className="status-chip">Σ {entity.historical_versions.length} VERSIONS</span>
            </div>
            <div>
              <div className="op-label">STRUCTURAL SIGNALS</div>
              <div className="chip-row">
                {entity.structural_signals.length === 0 ? (
                  <span className="insp-row">—</span>
                ) : (
                  entity.structural_signals.map((s, i) => (
                    <span key={i} className="status-chip">
                      {String(s["signal"] ?? s["feature_id"] ?? "signal")}
                    </span>
                  ))
                )}
              </div>
            </div>
            <div className="panel-actions">
              <button type="button" className="btn btn-primary btn-sm" onClick={() => onExpand(node.id)} data-testid="inspector-expand">
                ⧉ EXPAND NEIGHBOURHOOD
              </button>
              <Link to={`/entities/${node.id}`} className="btn btn-sm">
                OPEN ENTITY PAGE
              </Link>
            </div>
          </>
        ) : (
          <div className="panel-actions">
            <p className="panel-note">
              Correlate node — candidate not yet materialized into the atomic catalog.
            </p>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => onMaterialize(node.id)}
              data-testid="inspector-materialize"
            >
              ◉ MATERIALIZE ENTITY
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}

export function IntelligencePage({
  graph,
  seeds,
  entities,
  correlations,
  selectedId,
  feed,
  onSelect,
  onExpand,
  onMaterialize,
  onAddSeed,
  onRemoveSeed,
}: Props) {
  const [seedInput, setSeedInput] = useState("");

  const submit = (ev: FormEvent) => {
    ev.preventDefault();
    const raw = seedInput.trim();
    if (!raw) return;
    onAddSeed(raw);
    setSeedInput("");
  };

  const selectedNode = graph.nodes.find((n) => n.id === selectedId) ?? null;
  const selectedEntity = selectedId ? entities[selectedId] : undefined;

  return (
    <section className="intel-board" data-testid="intel-board">
      <aside className="intel-seedbank" data-testid="intel-seedbank">
        <div className="intel-canvas-head" style={{ borderBottom: 0 }}>
          <span className="op-label">SEED BANK</span>
          <span className="status-chip">{seeds.length} SEEDS</span>
        </div>
        <form className="seed-add" onSubmit={submit} data-testid="seed-form">
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
          {seeds.length === 0 ? (
            <p className="panel-note" data-testid="seed-empty">
              No seeds yet. Add an entity id, or a deep link
              <code> /intel?entity=ENT-2001</code> preloads the map.
            </p>
          ) : (
            seeds.map((id) => {
              const entity = entities[id];
              return (
                <button
                  key={id}
                  type="button"
                  className="seed-node"
                  data-selected={selectedId === id}
                  data-testid={`seed-node-${id}`}
                  onClick={() => onSelect(id)}
                >
                  <span className="seed-node-name">
                    <span>{entity ? nodeLabel(entity) : id}</span>
                    <span className="op-label">{entity ? "ENTITY" : "EXT"}</span>
                  </span>
                  <span className="seed-node-meta">
                    {entity ? `${entity.evidence.length} ev · ${entity.aliases.length} aliases` : "external correlate"}
                  </span>
                  <span className="seed-actions">
                    <span
                      role="button"
                      tabIndex={0}
                      className="header-link"
                      onClick={(e) => {
                        e.stopPropagation();
                        onRemoveSeed(id);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.stopPropagation();
                          onRemoveSeed(id);
                        }
                      }}
                    >
                      REMOVE
                    </span>
                  </span>
                </button>
              );
            })
          )}
        </div>
        <div className="seedbank-body" data-testid="correlation-taxonomy" style={{ flex: 0, borderTop: "1px solid var(--c-border)" }}>
          <span className="op-label">NEIGHBOURHOOD</span>
          <div className="chip-row">
            {Object.values(correlations).flat().length === 0 ? (
              <span className="panel-note">No correlation edges yet.</span>
            ) : (
              Object.values(correlations)
                .flat()
                .map((c) => (
                  <span key={c.edge_id} className="status-chip">
                    {c.kind} · {c.collective_score.toFixed(2)}
                  </span>
                ))
            )}
          </div>
        </div>
      </aside>

      <div className="intel-canvas" data-testid="intel-canvas">
        <div className="intel-canvas-head">
          <span className="op-label">INTELLIGENCE MAP — LIVE LINK ANALYSIS</span>
          <span className="status-chip">
            {graph.nodes.length} NODES · {graph.edges.length} EDGES
          </span>
        </div>
        <div className="intel-canvas-body">
          {graph.nodes.length === 0 ? (
            <div className="intel-empty" data-testid="intel-empty">
              <span style={{ fontSize: 22 }}>◈</span>
              <p>Graph is empty — add a seed to ignite the intelligence map.</p>
            </div>
          ) : (
            <IntelligenceGraph
              graph={graph}
              selectedId={selectedId}
              onSelect={onSelect}
              onExpand={onExpand}
            />
          )}
          {selectedNode && <IntelInspector node={selectedNode} entity={selectedEntity} onExpand={onExpand} onMaterialize={onMaterialize} />}
          <div className="intel-legend">
            <span>
              <b style={{ color: "#22d3ee" }}>●</b> ENTITY
            </span>
            <span>
              <b style={{ color: "#f0a832" }}>□</b> CORRELATE
            </span>
            <span>
              <b style={{ color: "#a78bfa" }}>▲</b> RELATED
            </span>
          </div>
        </div>
        <IntroFeed feed={feed} />
      </div>
    </section>
  );
}