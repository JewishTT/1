/**
 * Obligations board — live run board (ui-spec §2.2).
 *
 * Columns: obligation, query/capability, state, source policy, cost consumed,
 * outputs, blocker, updated time. Filters by status/source/claim family.
 * Failed source returns typed status and retryability.
 */



import { Obligation } from "./api";

interface ObligationsBoardProps {
  obligations: Obligation[];
}

const STATE_CHIP: Record<string, string> = {
  NOT_PLANNED: "bg-slate-100 text-slate-600",
  POLICY_BLOCKED: "bg-red-100 text-red-800",
  BUDGET_BLOCKED: "bg-amber-100 text-amber-800",
  UNSUPPORTED: "bg-slate-200 text-slate-500",
  SOURCE_UNAVAILABLE: "bg-red-100 text-red-800",
  IN_PROGRESS: "bg-blue-100 text-blue-800",
  SEARCHED_NO_RESULT: "bg-slate-200 text-slate-600",
  OBSERVATIONS_FOUND: "bg-green-100 text-green-800",
  PARTIAL: "bg-amber-100 text-amber-800",
  QUALIFIED_ABSENCE: "bg-blue-100 text-blue-600",
  CANCELLED_STALE_SCOPE: "bg-slate-200 text-slate-500",
  FAILED: "bg-red-100 text-red-800",
};

export function ObligationsBoard({ obligations }: ObligationsBoardProps) {
  return (
    <div className="space-y-2">
      <table className="w-full text-left text-xs border-collapse border border-slate-200">
        <thead>
          <tr className="bg-slate-50 border-b border-slate-200">
            <th className="px-2 py-2 font-semibold text-slate-600">Obligation</th>
            <th className="px-2 py-2 font-semibold text-slate-600">Claim family</th>
            <th className="px-2 py-2 font-semibold text-slate-600">State</th>
            <th className="px-2 py-2 font-semibold text-slate-600">Blocker</th>
                      </tr>
        </thead>
        <tbody>
          {obligations.map((o) => (
            <tr key={o.obligation_id} className="border-b border-slate-100 hover:bg-slate-50">
              <td className="px-2 py-2 truncate max-w-[200px]">{o.question}</td>
              <td className="px-2 py-2 text-slate-600 truncate">{o.claim_family ?? o.claim_families?.join(", ") ?? "—"}</td>
              <td className="px-2 py-2">
                <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${STATE_CHIP[displayState(o.state)] ?? STATE_CHIP.NOT_PLANNED}`}>
                  {displayState(o.state)}
                </span>
              </td>
              <td className="px-2 py-2 text-slate-600 truncate">
                {o.state === "POLICY_BLOCKED" ? "Source policy blocks" : o.state === "BUDGET_BLOCKED" ? "Budget exhausted" : o.state === "SOURCE_UNAVAILABLE" ? "Source unavailable" : "—"}
              </td>

            </tr>
          ))}
        </tbody>
      </table>

    </div>
  );
}

function displayState(state: string): string {
  const normalized = state.toUpperCase();
  if (normalized === "OPEN") return "NOT_PLANNED";
  if (normalized === "SATISFIED") return "OBSERVATIONS_FOUND";
  return normalized;
}
