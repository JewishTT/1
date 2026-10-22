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

import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "./api";
import {
  ResearchCase,
  ApproveCaseRequest,
  CloseCaseRequest,
  Obligation,
  CoverageLedger,
  CoverageItem,
} from "./api";
import { useResearchCaseView } from "./store";
import { ErrorView, LoadingView } from "../../ui/Feedback";
import { ObligationsBoard } from "./ObligationsBoard";
import { SubjectOverview } from "./SubjectOverview";
import { ClaimsTable } from "./ClaimsTable";
import { TimelineView } from "./TimelineView";
import { GraphView } from "./GraphView";
import { SourceLineageView } from "./SourceLineageView";
import { ACHMatrix } from "./ACHMatrix";
import { ReportPreview } from "./ReportPreview";
import { EvidenceInspector } from "./EvidenceInspector";
import { CoverageBar } from "./CoverageBar";

type ViewId =
  | "overview"
  | "claims"
  | "timeline"
  | "graph"
  | "sources"
  | "ach"
  | "report";

const VIEW_LABELS: Record<ViewId, string> = {
  overview: "Overview",
  claims: "Claims",
  timeline: "Timeline",
  graph: "Graph",
  sources: "Sources",
  ach: "ACH",
  report: "Report",
};

export function CasePage() {
  const { caseId } = useParams<{ caseId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { selectedTab, setSelectedTab } = useResearchCaseView();

  const { data: caseData, isLoading: caseLoading, error: caseError } = useQuery<ResearchCase>({
    queryKey: ["research-case", caseId],
    queryFn: () => api.getCase(caseId!),
    enabled: !!caseId,
  });

  const { data: coverage, isLoading: coverageLoading } = useQuery<CoverageLedger>({
    queryKey: ["research-case-coverage", caseId],
    queryFn: () => api.getCoverage(caseId!),
    enabled: !!caseId,
  });

  const approveMutation = useMutation({
    mutationFn: ({ digest, revision }: { digest: string; revision: number }) =>
      api.approveCase(caseId!, { scope_digest: digest, scope_revision: revision }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["research-case", caseId] });
    },
  });

  const closeMutation = useMutation({
    mutationFn: (body: CloseCaseRequest) => api.closeCase(caseId!, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["research-case", caseId] });
      navigate(`/research-cases/${caseId}`);
    },
  });

  if (caseLoading) return <LoadingView />;
  if (caseError || !caseData) return <ErrorView error={caseError} />;
  if (coverageLoading) return <LoadingView />;

  const obligations: Obligation[] = caseData.state === "APPROVED" || caseData.state === "RUNNING" ? [] : [];
  const coverageItems: CoverageItem[] = coverage?.items ?? [];

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
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium {policyStateChip(caseData.state)}">
            {caseData.state}
          </span>
        </div>

        <div className="flex items-center gap-2">
          {caseData.state !== "APPROVED" && caseData.state !== "RUNNING" && (
            <button
              onClick={() => {
                // Open approval flow handled by CaseSetup modal/path
                navigate(`/research-cases/${caseId}/setup`);
              }}
              className="px-3 py-1.5 text-sm font-medium bg-slate-900 text-white rounded hover:bg-slate-800"
            >
              Approve
            </button>
          )}
          {caseData.state === "RUNNING" && (
            <button
              onClick={() => api.pauseCase(caseId!).then(() => queryClient.invalidateQueries({ queryKey: ["research-case", caseId] }))}
              className="px-3 py-1.5 text-sm font-medium bg-amber-600 text-white rounded hover:bg-amber-700"
            >
              Pause
            </button>
          )}
          <button
            onClick={() => closeMutation.mutate({ disposition: "CLOSED_WITH_NO_FINDING", report: {} })}
            disabled={closeMutation.isPending}
            className="px-3 py-1.5 text-sm font-medium bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
          >
            Close
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
            {obligations.length === 0 ? (
              <div className="text-xs text-slate-500 text-center py-8">
                No obligations. Plan the case first.
              </div>
            ) : (
              <ObligationsBoard obligations={obligations} caseId={caseData.case_id} />
            )}
          </div>
        </aside>

        {/* Main view */}
        <main className="flex-1 overflow-y-auto p-6">
          {selectedTab === "overview" && <SubjectOverview caseId={caseData.case_id} />}
          {selectedTab === "claims" && <ClaimsTable caseId={caseData.case_id} />}
          {selectedTab === "timeline" && <TimelineView caseId={caseData.case_id} />}
          {selectedTab === "graph" && <GraphView caseId={caseData.case_id} />}
          {selectedTab === "sources" && <SourceLineageView caseId={caseData.case_id} />}
          {selectedTab === "ach" && <ACHMatrix caseId={caseData.case_id} />}
          {selectedTab === "report" && <ReportPreview caseId={caseData.case_id} />}

          {/* View selector tabs */}
          <div className="flex flex-wrap gap-1 border-t border-slate-200 pt-4 mt-6">
            {(["overview", "claims", "timeline", "graph", "sources", "ach", "report"] as ViewId[]).map((id) => (
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

        {/* Right: evidence inspector */}
        <aside className="w-96 border-l border-slate-200 bg-white flex flex-col overflow-hidden">
          <div className="p-4 border-b border-slate-200">
            <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wider">Evidence Inspector</h2>
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            <EvidenceInspector caseId={caseData.case_id} />
          </div>
        </aside>
      </div>

      {/* Footer: coverage */}
      <footer className="flex-shrink-0 border-t border-slate-200 bg-white px-4 py-2">
        <CoverageBar items={coverageItems} />
      </footer>
    </div>
  );
}

function policyStateChip(state: string): string {
  switch (state) {
    case "APPROVED": return "bg-green-100 text-green-800";
    case "RUNNING": return "bg-blue-100 text-blue-800";
    case "PARTIAL": return "bg-amber-100 text-amber-800";
    case "BLOCKED": return "bg-red-100 text-red-800";
    case "CLOSED": return "bg-slate-100 text-slate-800";
    default: return "bg-slate-200 text-slate-600";
  }
}
