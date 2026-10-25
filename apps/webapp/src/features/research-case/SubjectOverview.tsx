/**
 * Subject overview backed by the canonical case read model.
 * No counts are inferred before claims and temporal projections are composed.
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

interface SubjectOverviewProps {
  caseId: string;
}

export function SubjectOverview({ caseId }: SubjectOverviewProps) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["research-case-subject", caseId],
    queryFn: () => api.getCase(caseId),
  });

  if (isLoading) return <div className="text-xs text-slate-500">Loading case context…</div>;
  if (error || !data) {
    return <div className="rounded border border-red-300 bg-white p-4 text-sm text-red-700">
      Unable to load case context. {error instanceof Error ? error.message : ""}
    </div>;
  }

  return (
    <div className="space-y-4">
      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="text-sm font-semibold text-slate-700">Declared research context</h2>
        <p className="mt-2 text-sm whitespace-pre-wrap">{data.purpose_text}</p>
        <dl className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
          <Field label="Case ID" value={data.case_id} />
          <Field label="Lifecycle" value={data.state} />
          <Field label="Scope revision" value={String(data.scope_revision)} />
          <Field label="Scope digest" value={data.scope_digest} />
          <Field label="Launch profile" value={data.launch_profile} />
          <Field label="Basis reference" value={data.basis_ref} />
        </dl>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="text-sm font-semibold text-slate-700">Subject anchors</h2>
        {data.subject_anchors.length === 0 ? (
          <p className="mt-2 text-sm text-amber-800">No typed subject anchor was recorded; case is not eligible for planning.</p>
        ) : (
          <ul className="mt-2 space-y-2">
            {data.subject_anchors.map((anchor, index) => (
              <li key={`${anchor.kind}-${anchor.value}-${index}`} className="rounded border border-slate-200 p-3">
                <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">{anchor.kind}</div>
                <div className="mt-1 break-all text-sm">{anchor.value}</div>
                {anchor.evidence_ref && <div className="mt-1 break-all text-xs text-slate-500">Reference: {anchor.evidence_ref}</div>}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="text-sm font-semibold text-slate-700">Declared scope</h2>
        <Field label="Claim families" value={data.claim_families.join(", ") || "None declared"} />
        <Field label="Allowed source IDs" value={data.allowed_source_ids.join(", ") || "None selected"} />
        <Field label="Jurisdictions" value={data.jurisdictions.join(", ") || "Unspecified"} />
        <Field label="Valid time" value={`${data.valid_time.from ?? "unknown"} → ${data.valid_time.until ?? "open"} (${data.valid_time.precision})`} />
        <Field label="Approval" value={data.approved ? "Approved for current digest" : "Not approved"} />
        <p className="mt-3 text-xs text-slate-500">
          Claims, affiliations, publications, contradictions and coverage are intentionally not counted here: their canonical projections are not currently composed.
        </p>
      </section>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="py-1">
      <dt className="text-xs uppercase tracking-wider text-slate-500">{label}</dt>
      <dd className="mt-1 break-words text-sm">{value}</dd>
    </div>
  );
}
