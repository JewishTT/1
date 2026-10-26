/**
 * Claims table — claims/contradictions with stable pagination and evidence refs.
 *
 * Columns: statement/predicate, object, valid interval, epistemic state,
 * evidence lineages, source type, extraction version, reviewer disposition.
 * Filters: admitted/proposed/contested/retracted, source, period, claim family.
 * "Show opposing evidence" expands support/refute links.
 */

import { useQuery } from "@tanstack/react-query";

import { api, Claim } from "./api";

interface ClaimsTableProps {
  caseId: string;
}

const EPISTEMIC_CHIP: Record<string, string> = {
  TRUE_ONLY: "bg-green-100 text-green-800",
  FALSE_ONLY: "bg-red-100 text-red-800",
  BOTH: "bg-amber-100 text-amber-800",
  NEITHER: "bg-slate-100 text-slate-600",
};

const STATE_CHIP: Record<string, string> = {
  proposed: "bg-amber-100 text-amber-800",
  admitted: "bg-green-100 text-green-800",
  contested: "bg-red-100 text-red-800",
  retracted: "bg-slate-200 text-slate-500",
  superseded: "bg-slate-200 text-slate-500",
};

export function ClaimsTable({ caseId }: ClaimsTableProps) {
  const { data, isLoading, error } = useQuery<{ case_id: string; claims: Claim[] }>({
    queryKey: ["research-case-claims", caseId],
    queryFn: () => api.listClaims(caseId),
  });

  if (isLoading) return <div className="text-xs text-slate-500">Loading claims…</div>;
  if (error) return <div className="text-xs text-red-600">Unable to load claims.</div>;

  const claims: Claim[] = data?.claims ?? [];

  return (
    <div className="rounded-lg border border-slate-200 bg-white overflow-hidden">
      <table className="w-full text-left text-xs border-collapse">
        <thead>
          <tr className="bg-slate-50 border-b border-slate-200">
            <th className="px-3 py-2 font-semibold text-slate-600">Statement</th>
            <th className="px-3 py-2 font-semibold text-slate-600">Object</th>
            <th className="px-3 py-2 font-semibold text-slate-600">Valid interval</th>
            <th className="px-3 py-2 font-semibold text-slate-600">Epistemic</th>
            <th className="px-3 py-2 font-semibold text-slate-600">State</th>
            <th className="px-3 py-2 font-semibold text-slate-600">Source</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {claims.length === 0 ? (
            <tr>
              <td colSpan={6} className="px-3 py-8 text-center text-slate-500">
                No claims yet. Run the case to extract claims from observations.
              </td>
            </tr>
          ) : (
            claims.map((c) => (
              <tr key={c.claim_id} className="hover:bg-slate-50">
                <td className="px-3 py-2 truncate max-w-[260px]">{c.subject_mention} {c.predicate}</td>
                <td className="px-3 py-2 truncate max-w-[160px]">{formatObject(c.object_payload)}</td>
                <td className="px-3 py-2 text-slate-600 truncate">
                  {c.valid_time.from ?? "—"} → {c.valid_time.until ?? "—"} ({c.valid_time.precision})
                </td>
                <td className="px-3 py-2">
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${EPISTEMIC_CHIP[c.epistemic_state ?? "NEITHER"]}`}>
                    {c.epistemic_state ?? "NOT_COMPUTED"}
                  </span>
                </td>
                <td className="px-3 py-2">
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${STATE_CHIP[c.state]}`}>
                    {c.state}
                  </span>
                </td>
                <td className="px-3 py-2 text-slate-600 truncate">{c.source_ref}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}


function formatObject(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return "[unrenderable stored object]";
  }
}
