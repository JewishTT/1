import { useMemo, useState } from "react";

import { GraphElement, GraphPanel } from "../components/GraphPanel";

export interface SearchResult {
  doc_id: string;
  score: number;
  backends: string[];
  observation_ids: string[];
  evidence: Array<{
    backend: string;
    kind: string;
    observation: { observation_id: string; uri: string; immutable: boolean } | null;
    source_id: string | null;
    reason: string;
  }>;
}

interface Props {
  onSearch: (query: string, sourceFilter: string) => Promise<SearchResult[]>;
  graphElements?: GraphElement[];
}

function EvidenceLink({ evidence }: { evidence: SearchResult["evidence"] }) {
  return (
    <ul className="evidence-list">
      {evidence.map((e, i) => (
        <li key={`${e.backend}-${i}`} data-testid="evidence-link">
          <span className="evidence-backend">{e.backend}</span>
          {e.observation?.immutable ? " → " : " → (broken) "}
          <code>{e.observation?.observation_id ?? "?"}</code>
          <span className="evidence-uri">{e.observation?.uri}</span>
        </li>
      ))}
    </ul>
  );
}

export function SearchPage({ onSearch, graphElements = [] }: Props) {
  const [query, setQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);

  const observedRedacted = useMemo(
    () => (results.length > 0 ? results.map((r) => r.observation_ids).flat() : []),
    [results],
  );

  async function runSearch() {
    if (!query.trim()) return;
    setLoading(true);
    try {
      setResults(await onSearch(query.trim(), sourceFilter.trim()));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section data-testid="search-page">
      <h1>Evidence-backed search</h1>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void runSearch();
        }}
      >
        <input
          data-testid="query-input"
          value={query}
          placeholder="Hybrid query…"
          onChange={(e) => setQuery(e.target.value)}
        />
        <input
          data-testid="source-filter"
          value={sourceFilter}
          placeholder="source filter (comma separated)"
          onChange={(e) => setSourceFilter(e.target.value)}
        />
        <button type="submit" data-testid="search-btn" disabled={loading}>
          {loading ? "Searching…" : "Search"}
        </button>
      </form>

      {observedRedacted.length > 0 && (
        <p className="obs-count" data-testid="obs-count">
          fusions resolve to {new Set(observedRedacted).size} immutable observation(s)
        </p>
      )}

      <h2>Fused results</h2>
      {results.length === 0 ? (
        <p data-testid="no-results">{loading ? "…" : "Run a query to see fused results."}</p>
      ) : (
        <ul data-testid="result-list" className="sf-scope result-list">
          {results.map((r) => (
            <li key={r.doc_id} className="result" data-testid="result">
              <strong>{r.doc_id}</strong> <span className="score">{r.score.toFixed(3)}</span>
              <span className="backends">via {r.backends.join(" + ")}</span>
              <EvidenceLink evidence={r.evidence} />
            </li>
          ))}
        </ul>
      )}

      {graphElements.length > 0 && <GraphPanel elements={graphElements} title="Discovery graph" />}
    </section>
  );
}
