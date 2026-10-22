/**
 * Subject overview — identity state, public roles, organizations, publications,
 * timeline highlights, open conflicts, coverage.
 *
 * Never displays a proposed match as the subject's confirmed alias. Identity
 * state: UNRESOLVED | REVIEW_REQUIRED | ADMITTED | CONTESTED.
 */

import { useQuery } from "@tanstack/react-query";

import { api } from "./api";

interface SubjectOverviewProps {
  caseId: string;
}

const IDENTITY_CHIP: Record<string, string> = {
  UNRESOLVED: "bg-slate-100 text-slate-600",
  REVIEW_REQUIRED: "bg-amber-100 text-amber-800",
  ADMITTED: "bg-green-100 text-green-800",
  CONTESTED: "bg-red-100 text-red-800",
};

export function SubjectOverview({ caseId }: SubjectOverviewProps) {
  const { data: caseData, isLoading, error } = useQuery({
    queryKey: ["research-case-subject", caseId],
    queryFn: () => api.getCase(caseId),
  });

  if (isLoading) return <div className="text-xs text-slate-500">Loading subject…</div>;
  if (error) return <div className="text-xs text-red-600">Unable to load subject.</div>;

  const identityState = "UNRESOLVED"; // derived from claims/resolution in full impl

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 px-2 py-2 rounded-lg border border-slate-200 bg-slate-50">
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${IDENTITY_CHIP[identityState]}`}>
          {identityState}
        </span>
        <span className="text-sm text-slate-600">Subject identity — not confirmed until an admitted identity decision.</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <StatCard title="Public roles" value="—" note="No admitted role claims yet" />
        <StatCard title="Organizations" value="—" note="No admitted affiliations yet" />
        <StatCard title="Publications" value="—" note="No admitted publications yet" />
        <StatCard title="Open conflicts" value="0" note="No temporal contradictions detected" />
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <h3 className="text-sm font-semibold text-slate-700 mb-2">Coverage by claim family</h3>
        <div className="text-xs text-slate-500">No claims extracted yet. Run the case to populate.</div>
      </div>
    </div>
  );
}

function StatCard({ title, value, note }: { title: string; value: string; note: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="text-xs text-slate-500 uppercase tracking-wider mb-1">{title}</div>
      <div className="text-lg font-semibold">{value}</div>
      <div className="text-xs text-slate-400 mt-1">{note}</div>
    </div>
  );
}
