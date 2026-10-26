/**
 * Research case workbench — main page.
 *
 * Layout (ui-spec §1):
 *   header: case title | scope revision | policy state | pause/run | share/export
 *   sidebar: obligations (filters, status counts, next actions)
 *   main: Overview / Claims / Timeline / Graph / Sources / ACH / Report
 *   right: evidence inspector (selected claim/edge, source + exact span, lineage + versions)
 *   footer: coverage bar (queried / no result / unavailable / blocked / not queried)
 */

import { useParams, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "./api";
import {
  ResearchCase,
  Obligation,
  CoverageLedger,
  CaseActions,
  CompletionReport,
} from "./api";
import { useResearchCaseView } from "./store";
import { ErrorView, LoadingView } from "../../ui/Feedback";
import { ObligationsBoard } from "./ObligationsBoard";
import { SubjectOverview } from "./SubjectOverview";
import { ClaimsTable } from "./ClaimsTable";
import { CaseAnalyticsPanel } from "./CaseAnalyticsPanel";
import { CaseContextAndArtifacts } from "./CaseContextAndArtifacts";

type ViewId =
  | "overview"
  | "claims"
  | "analytics";

const VIEW_LABELS: Record<ViewId, string> = {
  overview: "Overview",
  claims: "Claims",
  analytics: "Graph & Timeline",
};

export function CasePage() {
  const { caseId } = useParams<{ caseId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { selectedTab, setSelectedTab } = useResearchCaseView();
  const [selectedActionRefs, setSelectedActionRefs] = useState<string[]>([]);
  const [runIdempotencyKey, setRunIdempotencyKey] = useState<string | null>(null);

  const { data: caseData, isLoading: caseLoading, error: caseError } = useQuery<ResearchCase>({
    queryKey: ["research-case", caseId],
    queryFn: () => api.getCase(caseId!),
    enabled: !!caseId,
  });

  const { data: coverage, error: coverageError } = useQuery<CoverageLedger>({
    queryKey: ["research-case-coverage", caseId],
    queryFn: () => api.getCoverage(caseId!),
    enabled: !!caseId,
  });

  const {
    data: obligationsData,
    isLoading: obligationsLoading,
    error: obligationsError,
  } = useQuery({
    queryKey: ["research-case-obligations", caseId],
    queryFn: () => api.listObligations(caseId!),
    enabled: !!caseId,
  });

  const { data: actionsData, isLoading: actionsLoading, error: actionsError } = useQuery<CaseActions>({
    queryKey: ["research-case-actions", caseId],
    queryFn: () => api.listActions(caseId!),
    enabled: !!caseId,
  });

  const planMutation = useMutation({
    mutationFn: () => api.planCase(caseId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["research-case-obligations", caseId] });
      queryClient.invalidateQueries({ queryKey: ["research-case-actions", caseId] });
    },
  });

  const approveActionsMutation = useMutation({
    mutationFn: (actionRefs: string[]) => api.approveActions(caseId!, actionRefs),
    onSuccess: (result) => {
      setSelectedActionRefs(result.approved_action_refs);
      queryClient.invalidateQueries({ queryKey: ["research-case-actions", caseId] });
    },
  });

  const runMutation = useMutation({
    mutationFn: (input: { actionRefs: string[]; key: string }) =>
      api.runCase(caseId!, {
        idempotency_key: input.key,
        approved_action_refs: input.actionRefs,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["research-case", caseId] });
      queryClient.invalidateQueries({ queryKey: ["research-case-actions", caseId] });
    },
  });

  const currentActions = actionsData?.actions ?? [];
  const proposedActions = currentActions.filter(
    (action) => action.status === "proposed" && action.requires_operator_approval,
  );
  const approvedActions = currentActions.filter(
    (action) => action.status === "approved" && !action.requires_operator_approval,
  );

  useEffect(() => {
    const actions = actionsData?.actions ?? [];
    const currentIds = new Set(actions.map((action) => action.action_id));
    setSelectedActionRefs((previous) => {
      const retained = previous.filter((id) => currentIds.has(id));
      if (retained.length > 0) return retained;
      const pending = actions.filter(
        (action) => action.status === "proposed" && action.requires_operator_approval,
      );
      const defaults = pending.length > 0
        ? pending
        : actions.filter((action) => action.status === "approved" && !action.requires_operator_approval);
      return defaults.map((action) => action.action_id);
    });
  }, [actionsData?.actions]);

  const latestReportId = (() => {
    const reportRef = caseData?.latest_report_ref as { report_id?: unknown } | undefined;
    return typeof reportRef?.report_id === "string" ? reportRef.report_id : null;
  })();

  const reportQuery = useQuery<CompletionReport>({
    queryKey: ["research-case-report", caseId, latestReportId],
    queryFn: () => api.getReport(caseId!, latestReportId!),
    enabled: !!caseId && !!latestReportId,
  });

  const reportMutation = useMutation({
    mutationFn: () => api.generateReport(caseId!),
    onSuccess: async (report) => {
      queryClient.setQueryData(["research-case-report", caseId, report.report_id], report);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["research-case", caseId] }),
        queryClient.invalidateQueries({ queryKey: ["research-case-coverage", caseId] }),
        queryClient.invalidateQueries({ queryKey: ["research-case-artifacts", caseId] }),
      ]);
    },
  });

  const closeMutation = useMutation({
    mutationFn: (input: { disposition: string; reportId: string }) =>
      api.closeCase(caseId!, {
        disposition: input.disposition,
        report: { report_id: input.reportId },
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["research-case", caseId] });
    },
  });

  if (caseLoading) return <LoadingView message="Loading research case…" />;
  if (caseError || !caseData) return <ErrorView error={caseError instanceof Error ? caseError.message : "Unable to load research case"} />;
  const obligations: Obligation[] = obligationsData?.obligations ?? [];

  return (
    <div className="research-case h-screen flex flex-col bg-slate-50 text-slate-900">
      {/* Header */}
      <header className="flex-shrink-0 border-b border-slate-200 bg-white px-4 py-3 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold">{caseData.purpose_text}</h1>
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800">
            Rev {caseData.scope_revision}
          </span>
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
            {caseData.launch_profile}
          </span>
          <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${policyStateChip(caseData.state)}`}>
            {caseData.state}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => navigate(`/research-cases/${caseId}/setup`)}
            className="px-3 py-1.5 text-sm font-medium bg-slate-900 text-white rounded hover:bg-slate-800"
          >
            {caseData.approved ? "Revise scope" : "Review / approve scope"}
          </button>
          {caseData.state === "APPROVED" && (
            <button
              onClick={() => planMutation.mutate()}
              disabled={planMutation.isPending}
              className="px-3 py-1.5 text-sm font-medium bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
            >
              {planMutation.isPending ? "Planning…" : "Plan case"}
            </button>
          )}
          {(caseData.state === "RUNNING" || caseData.state === "QUEUED") && (
            <button
              onClick={() => api.pauseCase(caseId!).then(() => queryClient.invalidateQueries({ queryKey: ["research-case", caseId] }))}
              className="px-3 py-1.5 text-sm font-medium bg-amber-600 text-white rounded hover:bg-amber-700"
            >
              Pause
            </button>
          )}
          <button
            onClick={() => reportMutation.mutate()}
            disabled={reportMutation.isPending || caseData.state === "CLOSED"}
            className="px-3 py-1.5 text-sm font-medium bg-indigo-700 text-white rounded hover:bg-indigo-800 disabled:opacity-50"
          >
            {reportMutation.isPending ? "Building report…" : "Generate report"}
          </button>
        </div>
      </header>

      {/* Body */}
      <div className="flex-1 overflow-hidden flex">
        {/* Sidebar: obligations */}
        <aside className="w-80 border-r border-slate-200 bg-white flex flex-col overflow-hidden">
          <div className="p-4 border-b border-slate-200">
            <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wider">Obligations</h2>
          </div>
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            {obligationsLoading ? (
              <div className="text-xs text-slate-500 text-center py-8">Loading obligations…</div>
            ) : obligationsError ? (
              <div className="text-xs text-red-700 text-center py-8">
                Obligations are unavailable: {obligationsError instanceof Error ? obligationsError.message : "request failed"}
              </div>
            ) : obligations.length === 0 ? (
              <div className="text-xs text-slate-500 text-center py-8">No declared obligations.</div>
            ) : (
              <ObligationsBoard obligations={obligations} />
            )}
          </div>
        </aside>

        {/* Main view */}
        <main className="flex-1 overflow-y-auto p-6">
          {selectedTab === "overview" && (
            <div className="space-y-4">
              <SubjectOverview caseId={caseData.case_id} />
              <CaseContextAndArtifacts caseId={caseData.case_id} caseData={caseData} />
            </div>
          )}
          {selectedTab === "claims" && <ClaimsTable caseId={caseData.case_id} />}
          {selectedTab === "analytics" && <CaseAnalyticsPanel caseId={caseData.case_id} />}
          {(reportMutation.error || reportQuery.error) && (
            <section role="alert" className="mb-4 rounded border border-red-300 bg-white p-3 text-sm text-red-700">
              Report operation failed: {(
                reportMutation.error ?? reportQuery.error
              ) instanceof Error ? (reportMutation.error ?? reportQuery.error as Error).message : "request failed"}
            </section>
          )}
          {(reportMutation.data || reportQuery.data) && (() => {
            const report = reportMutation.data ?? reportQuery.data!;
            const reportCase = report.case;
            const matchesCurrentScope = reportCase.scope_digest === caseData.scope_digest
              && reportCase.scope_revision === caseData.scope_revision;
            const closable = matchesCurrentScope && (
              report.status === "BLOCKED"
              || ((report.status === "COMPLETE" || report.status === "PARTIAL")
                && Number(report.summary.open_obligations ?? 0) === 0)
            );
            return (
              <section className="mb-4 rounded border border-slate-300 bg-white p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h2 className="font-semibold">Completion report · {report.status}</h2>
                    <p className="mt-1 text-xs text-slate-500">
                      {report.report_id} · {report.report_digest} · generated {report.generated_at}
                    </p>
                    <p className="mt-2 text-sm text-slate-700">
                      {report.summary.findings ?? 0} grounded admitted findings · {report.summary.relation_claim_candidates ?? 0} relation-claim candidates · {report.summary.open_obligations ?? 0} open obligations
                    </p>
                    {!matchesCurrentScope && (
                      <p className="mt-2 text-sm text-red-700">
                        This report is stale because the case scope has changed. Generate a new report.
                      </p>
                    )}
                  </div>
                  {closable && (
                    <button
                      onClick={() => closeMutation.mutate({ disposition: report.status as "COMPLETE" | "PARTIAL" | "BLOCKED", reportId: report.report_id })}
                      disabled={closeMutation.isPending || caseData.state === "CLOSED"}
                      className="rounded bg-red-700 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
                    >
                      {closeMutation.isPending ? "Closing…" : "Close with persisted report"}
                    </button>
                  )}
                </div>
                {closeMutation.error && (
                  <p role="alert" className="mt-3 text-sm text-red-700">
                    Close blocked: {closeMutation.error instanceof Error ? closeMutation.error.message : "request failed"}
                  </p>
                )}
                {report.findings.length > 0 ? (
                  <div className="mt-4 space-y-3">
                    <h3 className="text-sm font-semibold">Admitted, span-grounded findings</h3>
                    {report.findings.map((finding, index) => {
                      const statement = String(finding.statement ?? "Untitled finding");
                      const spans = Array.isArray(finding.evidence_spans)
                        ? finding.evidence_spans as Array<Record<string, unknown>>
                        : [];
                      return (
                        <article key={String(finding.finding_id ?? index)} className="rounded border border-slate-200 p-3">
                          <p className="text-sm font-medium">{statement}</p>
                          {spans.map((span, spanIndex) => (
                            <blockquote key={String(span.mention_id ?? spanIndex)} className="mt-2 border-l-2 border-slate-300 pl-3 text-xs text-slate-700">
                              “{String(span.exact_quote ?? span.surface ?? "No exact quote available")}”
                              <div className="mt-1 break-all text-slate-500">
                                {String(span.source_url ?? "source URL unavailable")} · {String(span.observation_id ?? "")}
                              </div>
                            </blockquote>
                          ))}
                        </article>
                      );
                    })}
                  </div>
                ) : (
                  <p className="mt-4 text-sm text-slate-600">
                    No factual finding qualifies for inclusion yet. Extracted relations remain review candidates until admitted and grounded to a verified raw-byte span.
                  </p>
                )}
                {report.relation_claims.length > 0 && (
                  <details className="mt-4">
                    <summary className="cursor-pointer text-sm font-semibold">Relation claim review queue ({report.relation_claims.length})</summary>
                    <div className="mt-2 space-y-2">
                      {report.relation_claims.map((claim, index) => (
                        <div key={String(claim.claim_id ?? index)} className="rounded bg-slate-50 p-3 text-xs">
                          <div className="font-medium">{String(claim.status ?? "unknown")} · {String(claim.predicate ?? "relation")}</div>
                          <div className="mt-1 break-words">{JSON.stringify(claim.subject)} → {JSON.stringify(claim.object)}</div>
                          <div className="mt-1 text-slate-500">{String(claim.disposition ?? "requires review")} · {String(claim.claim_id ?? "")}</div>
                        </div>
                      ))}
                    </div>
                  </details>
                )}
                <details className="mt-4">
                  <summary className="cursor-pointer text-xs font-semibold text-slate-600">Limitations and source coverage</summary>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-slate-600">
                    {report.limitations.map((limitation, index) => <li key={index}>{limitation}</li>)}
                  </ul>
                </details>
              </section>
            );
          })()}
          {planMutation.data && (
            <section className="mb-4 rounded border border-slate-300 bg-white p-4">
              <h2 className="font-semibold">Plan result: {planMutation.data.plan_state}</h2>
              <p className="mt-1 text-sm text-slate-600">
                Required capabilities: {planMutation.data.required_capabilities.join(", ") || "none declared"}.
                {planMutation.data.ready_to_dispatch ? " Runtime is ready for reviewed actions." : " Dispatch remains blocked."}
              </p>
              {planMutation.data.capability_gaps.map((gap) => (
                <div key={gap.obligation_id} className="mt-2 text-sm text-amber-800">
                  {gap.obligation_id}: {gap.claim_families?.join(", ") || gap.required?.join(", ") || "eligible source"} — {gap.detail}
                </div>
              ))}
            </section>
          )}
          {planMutation.error && (
            <div className="mb-4 rounded border border-red-300 bg-white p-3 text-sm text-red-700">
              Planning failed: {planMutation.error instanceof Error ? planMutation.error.message : "request failed"}
            </div>
          )}

          <section className="mb-4 rounded border border-slate-300 bg-white p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="font-semibold">Source-bound actions</h2>
                <p className="mt-1 text-xs text-slate-600">
                  Every action is tied to one policy-approved source, claim family, scope digest and policy digest.
                  Approval is a separate admin decision. Queueing reserves budget before publishing to Kafka.
                </p>
              </div>
              <button
                onClick={() => queryClient.invalidateQueries({ queryKey: ["research-case-actions", caseId] })}
                className="rounded border border-slate-300 px-2 py-1 text-xs"
              >
                Refresh
              </button>
            </div>
            {actionsLoading ? (
              <p className="mt-3 text-sm text-slate-500">Loading action proposals…</p>
            ) : actionsError ? (
              <p className="mt-3 text-sm text-red-700">
                Actions unavailable: {actionsError instanceof Error ? actionsError.message : "request failed"}
              </p>
            ) : currentActions.length === 0 ? (
              <p className="mt-3 text-sm text-slate-500">No current source-bound actions. Approve the scope, then select Plan case.</p>
            ) : (
              <div className="mt-3 space-y-2">
                {currentActions.map((action) => {
                  const selectable = action.status === "proposed" && action.requires_operator_approval;
                  const approved = action.status === "approved" && !action.requires_operator_approval;
                  return (
                    <label key={action.action_id} className="flex items-start gap-2 rounded border border-slate-200 p-3">
                      <input
                        type="checkbox"
                        checked={selectedActionRefs.includes(action.action_id)}
                        disabled={!selectable && !approved}
                        onChange={(event) => {
                          setRunIdempotencyKey(null);
                          setSelectedActionRefs((previous) =>
                            event.target.checked
                              ? [...new Set([...previous, action.action_id])]
                              : previous.filter((id) => id !== action.action_id)
                          );
                        }}
                        className="mt-1"
                      />
                      <span className="min-w-0 flex-1">
                        <span className="flex flex-wrap items-center gap-2">
                          <span className="text-xs font-semibold">{action.status.toUpperCase()}</span>
                          <span className="text-xs text-slate-500">{action.source_id} → {action.catalogue_source_id}</span>
                          <span className="text-xs text-slate-500">{action.claim_family ?? "claim family not declared"}</span>
                        </span>
                        <span className="mt-1 block break-all text-xs font-mono text-slate-500">{action.action_id}</span>
                        <span className="mt-1 block text-sm">{action.proposed_method}</span>
                        <span className="mt-1 block break-words text-xs text-slate-600">Query: {action.query}</span>
                      </span>
                    </label>
                  );
                })}
              </div>
            )}
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                onClick={() => approveActionsMutation.mutate(
                  selectedActionRefs.filter((id) => proposedActions.some((action) => action.action_id === id))
                )}
                disabled={
                  approveActionsMutation.isPending ||
                  selectedActionRefs.filter((id) => proposedActions.some((action) => action.action_id === id)).length === 0
                }
                className="rounded bg-indigo-700 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {approveActionsMutation.isPending ? "Approving…" : "Approve selected actions (admin)"}
              </button>
              <button
                onClick={() => {
                  const actionRefs = selectedActionRefs.filter((id) => approvedActions.some((action) => action.action_id === id));
                  if (actionRefs.length === 0) return;
                  const key = runIdempotencyKey ?? `case-run-${crypto.randomUUID()}`;
                  setRunIdempotencyKey(key);
                  runMutation.mutate({ actionRefs, key });
                }}
                disabled={
                  runMutation.isPending ||
                  selectedActionRefs.filter((id) => approvedActions.some((action) => action.action_id === id)).length === 0 ||
                  !caseData.approved
                }
                className="rounded bg-emerald-700 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {runMutation.isPending ? "Queueing…" : "Reserve budget + queue selected actions"}
              </button>
            </div>
            {approveActionsMutation.error && (
              <p role="alert" className="mt-2 text-sm text-red-700">
                Approval failed: {approveActionsMutation.error instanceof Error ? approveActionsMutation.error.message : "request failed"}
              </p>
            )}
            {runMutation.data && (
              <div className="mt-3 rounded border border-slate-200 bg-slate-50 p-3">
                <h3 className="text-sm font-semibold">Dispatch result: {runMutation.data.state}</h3>
                <p className="mt-1 break-all text-xs text-slate-600">Run ID: {runMutation.data.run_id}</p>
                <p className="mt-1 break-all text-xs text-slate-600">Idempotency key: {runMutation.data.idempotency_key}</p>
                <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(runMutation.data.dispatch ?? {}, null, 2)}</pre>
                {runMutation.data.state === "QUEUED" && (
                  <p className="mt-2 text-xs text-emerald-800">
                    Kafka acknowledged the acquisition request(s). This is queued work, not proof the worker has finished capture or extraction.
                  </p>
                )}
                {runMutation.data.state === "BLOCKED_DISPATCH" && (
                  <p className="mt-2 text-xs text-red-800">No acquisition request was acknowledged. The case remains approved.</p>
                )}
              </div>
            )}
            {runMutation.error && (
              <p role="alert" className="mt-2 text-sm text-red-700">
                Run blocked: {runMutation.error instanceof Error ? runMutation.error.message : "request failed"}
              </p>
            )}
            {planMutation.data && (
              <p className="mt-3 text-xs text-slate-600">
                Plan state: {planMutation.data.plan_state}. {planMutation.data.ready_to_dispatch
                  ? "Runtime and source policy allow reviewed actions to be queued after budget reservation."
                  : "Dispatch is blocked until the reported capability/runtime gaps are resolved."}
              </p>
            )}
            {planMutation.data?.capability_gaps.map((gap) => (
              <p key={gap.obligation_id} className="mt-2 text-xs text-amber-800">
                {gap.obligation_id}: {gap.claim_families?.join(", ") || gap.required?.join(", ") || "eligible source"} — {gap.detail}
              </p>
            ))}
          </section>

          {/* View selector tabs */}
          <div className="flex flex-wrap gap-1 border-t border-slate-200 pt-4 mt-6">
            {(["overview", "claims", "analytics"] as ViewId[]).map((id) => (
              <button
                key={id}
                onClick={() => setSelectedTab(id)}
                className={`px-3 py-2 text-sm rounded-t-lg transition ${
                  selectedTab === id
                    ? "bg-blue-600 text-white"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                {VIEW_LABELS[id]}
              </button>
            ))}
          </div>
        </main>

        {/* Evidence inspector is intentionally not rendered until a durable span reader is composed. */}
      </div>

      {/* Footer: coverage */}
      <footer className="flex-shrink-0 border-t border-slate-200 bg-white px-4 py-2">
        {coverage ? (
          <div className="text-xs text-slate-600">
            Coverage ledger: {coverage.overall_state} — {coverage.items.length} records.
          </div>
        ) : (
          <div className="text-xs text-amber-800">
            Coverage ledger unavailable{caseData.state !== "DRAFT" ? " — canonical projection is not composed" : " until an acquisition/coverage path is composed"}.
            {coverageError ? ` ${coverageError instanceof Error ? coverageError.message : "request failed"}` : ""}
          </div>
        )}
      </footer>
    </div>
  );
}

function policyStateChip(state: string): string {
  switch (state) {
    case "APPROVED": return "bg-green-100 text-green-800";
    case "RUNNING": return "bg-blue-100 text-blue-800";
    case "QUEUED": return "bg-indigo-100 text-indigo-800";
    case "PAUSED": return "bg-amber-100 text-amber-800";
    case "PARTIAL": return "bg-amber-100 text-amber-800";
    case "BLOCKED": return "bg-red-100 text-red-800";
    case "CLOSED": return "bg-slate-100 text-slate-800";
    default: return "bg-slate-200 text-slate-600";
  }
}
