import { Link } from "react-router-dom";
import { GraphElement, GraphPanel } from "../components/GraphPanel";
import { TimelineView } from "../components/TimelineView";
import { burstiness, eventsPerDay } from "../lib/timing";

export interface EntityView {
  entity_id: string;
  canonical_identity: Record<string, string>;
  current_state: Record<string, unknown>;
  historical_versions: Array<Record<string, unknown>>;
  aliases: string[];
  relationships: Array<Record<string, string>>;
  supporting_assertions: string[];
  evidence: Array<{ evidence_id: string; observation_id: string; immutable: boolean }>;
  timeline: Array<{ observation_id: string; uri: string; immutable: boolean; observed_at?: string }>;
  structural_signals: Array<Record<string, unknown>>;
  correlations?: Array<{
    edge_id: string;
    candidate_a: string;
    candidate_b: string;
    kind: string;
    state: string;
  }>;
  map_points?: Array<{ lat: number; lon: number; label?: string }>;
}

interface Props {
  entity: EntityView;
  graphElements?: GraphElement[];
}

export function EntityViewPage({ entity, graphElements = [] }: Props) {
  const asserted = entity.evidence.every((e) => e.immutable);
  const timelineAt = entity.timeline.map((t) => t.observed_at ?? t.uri);
  return (
    <section data-testid="entity-view" data-entity-id={entity.entity_id}>
      <h1>
        {entity.canonical_identity["account"] ?? entity.entity_id}{" "}
        <Link
          to={`/intel?entity=${encodeURIComponent(entity.entity_id)}`}
          className="header-link"
          data-testid="intel-board-link"
        >
          ◈ OPEN IN INTEL BOARD
        </Link>
      </h1>

      <div className="panel">
        <h2>Current state</h2>
        <pre data-testid="entity-current">{JSON.stringify(entity.current_state, null, 2)}</pre>
      </div>

      <div className="panel">
        <h2>Aliases</h2>
        <ul data-testid="entity-aliases">
          {entity.aliases.length === 0 ? (
            <li>none</li>
          ) : (
            entity.aliases.map((a) => <li key={a}>{a}</li>)
          )}
        </ul>
      </div>

      <div className="nfa-scope">
        <div className="panel">
          <h2>Evidence</h2>
          <p data-testid="evidence-integrity">
            {asserted
              ? "All evidence anchored to immutable observations (I-1)."
              : "Evidence integrity broken."}
          </p>
          <ul data-testid="entity-evidence">
            {entity.evidence.map((e) => (
              <li key={e.evidence_id}>
                <code>{e.evidence_id}</code> → <code>{e.observation_id}</code>
              </li>
            ))}
          </ul>
        </div>

        <div className="panel">
          <h2>Timeline</h2>
          <TimelineView
            entries={entity.timeline.map((t) => ({
              id: t.observation_id,
              label: t.uri,
              at: t.observed_at,
            }))}
            metrics={{ burstiness: burstiness(timelineAt), events_per_day: eventsPerDay(timelineAt) }}
          />
        </div>
      </div>

      <div className="panel">
        <h2>Structural signals</h2>
        <ul data-testid="entity-signals">
          {entity.structural_signals.length === 0 ? (
            <li>none</li>
          ) : (
            entity.structural_signals.map((s, i) => (
              <li key={i}>
                {String(s.signal)}: {JSON.stringify(s)}
              </li>
            ))
          )}
        </ul>
      </div>

      {entity.correlations && entity.correlations.length > 0 && (
        <div className="panel">
          <h2>Correlations</h2>
          <p className="panel-note">
            possible_match edges exist without identity — review before resolution (FR-004).
          </p>
          <ul data-testid="entity-correlations">
            {entity.correlations.map((c) => (
              <li key={c.edge_id}>
                {c.candidate_a} — {c.kind} — {c.candidate_b} ({c.state})
              </li>
            ))}
          </ul>
        </div>
      )}

      {entity.map_points && entity.map_points.length > 0 && (
        <div className="panel">
          <h2>Map</h2>
          <ul data-testid="entity-map">
            {entity.map_points.map((p, i) => (
              <li key={i}>
                {p.label ?? "point"} — {p.lat}, {p.lon}
              </li>
            ))}
          </ul>
        </div>
      )}

      {graphElements.length > 0 && (
        <GraphPanel elements={graphElements} title="Entity neighbourhood" />
      )}
    </section>
  );
}
