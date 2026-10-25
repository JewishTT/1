import { useQuery } from "@tanstack/react-query";

import { api } from "./api";

interface CaseAnalyticsPanelProps {
  caseId: string;
}

/**
 * Read-only visualization of materialized relation claims. The backend is the
 * authority for the graph and temporal projection; this component never infers an
 * edge, time interval, match or contradiction from the UI state.
 */
export function CaseAnalyticsPanel({ caseId }: CaseAnalyticsPanelProps) {
  const graph = useQuery({
    queryKey: ["research-case-graph", caseId],
    queryFn: () => api.getGraph(caseId, undefined, 1),
  });
  const timeline = useQuery({
    queryKey: ["research-case-timeline", caseId],
    queryFn: () => api.getTimeline(caseId, undefined, undefined, undefined, 100),
  });

  return (
    <div className="space-y-4">
      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold">Case relation graph</h2>
            <p className="mt-1 text-xs text-slate-500">
              Only persisted relation claims with tenant-scoped canonical entity endpoints are drawn.
              Unknown predicates and unresolved endpoints remain visible as warnings, not invented edges.
            </p>
          </div>
          {graph.data && (
            <span className="text-xs text-slate-600">
              {graph.data.nodes.length} nodes · {graph.data.edges.length} edges
            </span>
          )}
        </div>

        {graph.isLoading ? (
          <p className="mt-4 text-sm text-slate-500">Loading canonical relation projection…</p>
        ) : graph.error ? (
          <p role="alert" className="mt-4 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
            Graph projection unavailable: {graph.error instanceof Error ? graph.error.message : "request failed"}
          </p>
        ) : (
          <>
            {graph.data?.warnings.map((warning, index) => (
              <p key={`${index}-${warning}`} className="mt-2 text-xs text-amber-800">{warning}</p>
            ))}
            {graph.data?.edges.length ? (
              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 text-slate-500">
                      <th className="px-2 py-2 font-semibold">Subject</th>
                      <th className="px-2 py-2 font-semibold">Relation</th>
                      <th className="px-2 py-2 font-semibold">Object</th>
                      <th className="px-2 py-2 font-semibold">Epistemic</th>
                      <th className="px-2 py-2 font-semibold">Evidence refs</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {graph.data.edges.map((edge) => {
                      const source = graph.data?.nodes.find((node) => node.id === edge.source);
                      const target = graph.data?.nodes.find((node) => node.id === edge.target);
                      return (
                        <tr key={edge.id}>
                          <td className="px-2 py-2">
                            <div>{source?.label ?? edge.source}</div>
                            <div className="mt-1 text-slate-400">{edge.source}</div>
                          </td>
                          <td className="px-2 py-2">
                            <div>{edge.relation_type ?? edge.kind}</div>
                            <div className="mt-1 text-slate-500">{edge.review_state}</div>
                          </td>
                          <td className="px-2 py-2">
                            <div>{target?.label ?? edge.target}</div>
                            <div className="mt-1 text-slate-400">{edge.target}</div>
                          </td>
                          <td className="px-2 py-2">{edge.epistemic_state}</td>
                          <td className="px-2 py-2">
                            {edge.evidence_refs.length ? edge.evidence_refs.join(", ") : "No evidence refs stored"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="mt-4 text-sm text-slate-500">No canonical relation edge with two resolved endpoints is available yet.</p>
            )}
          </>
        )}
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <div>
          <h2 className="text-sm font-semibold">Bitemporal relation timeline</h2>
          <p className="mt-1 text-xs text-slate-500">
            Valid time and knowledge time remain separate. Events show only stored relation claims;
            unknown time bounds remain unknown.
          </p>
        </div>

        {timeline.isLoading ? (
          <p className="mt-4 text-sm text-slate-500">Loading temporal projection…</p>
        ) : timeline.error ? (
          <p role="alert" className="mt-4 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
            Timeline projection unavailable: {timeline.error instanceof Error ? timeline.error.message : "request failed"}
          </p>
        ) : timeline.data?.timeline.length ? (
          <ol className="mt-3 space-y-3">
            {timeline.data.timeline.map((item) => (
              <li key={item.claim_id} className="border-l-2 border-slate-300 pl-3 py-1">
                <div className="text-sm font-medium">{item.label}</div>
                <div className="mt-1 text-xs text-slate-600">
                  Valid: {item.valid_time.from ?? "unknown"} → {item.valid_time.until ?? "open"}
                </div>
                <div className="mt-1 text-xs text-slate-600">
                  Published: {item.source_time.published_at ?? "unknown"} · Captured/observed: {item.source_time.captured_at ?? "unknown"}
                </div>
                {item.knowledge_time && (
                  <div className="mt-1 text-xs text-slate-600">
                    Known: {item.knowledge_time.from ?? "unknown"} → {item.knowledge_time.until ?? "open"}
                  </div>
                )}
                <div className="mt-1 text-xs text-slate-500">
                  Epistemic state: {item.epistemic_state} · Claim: {item.claim_id}
                </div>
                <div className="mt-1 break-words text-xs text-slate-500">
                  Evidence: {item.evidence_refs.length ? item.evidence_refs.join(", ") : "none linked"}
                </div>
                {item.conflict_refs.length > 0 && (
                  <div className="mt-1 text-xs text-amber-800">
                    Conflict refs: {item.conflict_refs.join(", ")}
                  </div>
                )}
              </li>
            ))}
          </ol>
        ) : (
          <p className="mt-4 text-sm text-slate-500">No canonical temporal relation claims are recorded for this case.</p>
        )}
      </section>
    </div>
  );
}
