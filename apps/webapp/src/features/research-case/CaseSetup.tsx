import { FormEvent, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ApiError } from "../../lib/http";
import {
  api,
  ApproveCaseRequest,
  CreateCaseRequest,
  LaunchProfile,
  ResearchCase,
  SubjectAnchor,
} from "./api";

const LAUNCH_PROFILES: LaunchProfile[] = [
  "PUBLIC_PROFESSIONAL",
  "PUBLIC_ROLE_REVIEW",
  "CONSENTED_RECORDS",
  "AUTHORISED_CASE",
];
const ANCHOR_KINDS: SubjectAnchor["kind"][] = [
  "public_name",
  "orcid",
  "openalex_author_id",
  "doi_author_record",
  "official_profile_url",
];

export function CaseSetup() {
  const { caseId } = useParams<{ caseId: string }>();
  const navigate = useNavigate();
  const isEditing = Boolean(caseId);
  const [purposeCode, setPurposeCode] = useState("public_professional");
  const [purposeText, setPurposeText] = useState("");
  const [basisRef, setBasisRef] = useState("");
  const [launchProfile, setLaunchProfile] = useState<LaunchProfile>("PUBLIC_PROFESSIONAL");
  const [anchorKind, setAnchorKind] = useState<SubjectAnchor["kind"]>("public_name");
  const [anchorValue, setAnchorValue] = useState("");
  const [anchorEvidenceRef, setAnchorEvidenceRef] = useState("");
  const [jurisdictionsText, setJurisdictionsText] = useState("LV");
  const [validFrom, setValidFrom] = useState("");
  const [validUntil, setValidUntil] = useState("");
  const [precision, setPrecision] = useState<"instant" | "day" | "month" | "year" | "unknown">("unknown");
  const [claimFamiliesText, setClaimFamiliesText] = useState("public_authorship_or_publication");
  const [sourceIdsText, setSourceIdsText] = useState("crossref_works");
  const [deniedFamiliesText, setDeniedFamiliesText] = useState("");
  const [budgetRef, setBudgetRef] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [questionsText, setQuestionsText] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [initializedFor, setInitializedFor] = useState<string | null>(null);

  const caseQuery = useQuery<ResearchCase>({
    queryKey: ["research-case", caseId],
    queryFn: () => api.getCase(caseId!),
    enabled: isEditing,
  });
  const existingCase = caseQuery.data;

  useEffect(() => {
    if (!existingCase || initializedFor === existingCase.case_id) return;
    setPurposeCode(existingCase.purpose_code);
    setPurposeText(existingCase.purpose_text);
    setBasisRef(existingCase.basis_ref);
    setLaunchProfile(existingCase.launch_profile);
    setJurisdictionsText(existingCase.jurisdictions.join(", "));
    setValidFrom(existingCase.valid_time.from ?? "");
    setValidUntil(existingCase.valid_time.until ?? "");
    setPrecision(existingCase.valid_time.precision);
    setClaimFamiliesText(existingCase.claim_families.join(", "));
    setSourceIdsText(existingCase.allowed_source_ids.join(", "));
    setDeniedFamiliesText(existingCase.denied_claim_families.join(", "));
    setBudgetRef("");
    setExpiresAt(existingCase.expires_at ?? "");
    const firstAnchor = existingCase.subject_anchors[0];
    if (firstAnchor) {
      setAnchorKind(firstAnchor.kind);
      setAnchorValue(firstAnchor.value);
      setAnchorEvidenceRef(firstAnchor.evidence_ref ?? "");
    }
    setInitializedFor(existingCase.case_id);
  }, [existingCase, initializedFor]);

  const anchors = useMemo<SubjectAnchor[]>(() => [{
    kind: anchorKind,
    value: anchorValue.trim(),
    ...(anchorEvidenceRef.trim() ? { evidence_ref: anchorEvidenceRef.trim() } : {}),
  }], [anchorKind, anchorValue, anchorEvidenceRef]);

  const body = (): CreateCaseRequest => ({
    purpose_code: purposeCode.trim(),
    purpose_text: purposeText.trim(),
    basis_ref: basisRef.trim(),
    launch_profile: launchProfile,
    subject_anchors: anchors,
    jurisdictions: parseList(jurisdictionsText),
    valid_time: {
      from: validFrom.trim() || null,
      until: validUntil.trim() || null,
      precision,
    },
    claim_families: parseList(claimFamiliesText) as CreateCaseRequest["claim_families"],
    allowed_source_ids: parseList(sourceIdsText),
    denied_claim_families: parseList(deniedFamiliesText),
    budget_ref: budgetRef.trim() || undefined,
    expires_at: expiresAt.trim() || undefined,
    questions: parseList(questionsText, "\n"),
  });

  const createMutation = useMutation({
    mutationFn: (payload: CreateCaseRequest) => api.createCase(payload),
    onSuccess: (created) => navigate(`/research-cases/${encodeURIComponent(created.case_id)}`),
    onError: (error) => setFormError(formatError(error)),
  });
  const reviseMutation = useMutation({
    mutationFn: (payload: CreateCaseRequest) => api.proposeScopeRevision(caseId!, payload),
    onSuccess: () => navigate(`/research-cases/${encodeURIComponent(caseId!)}`),
    onError: (error) => setFormError(formatError(error)),
  });
  const approveMutation = useMutation({
    mutationFn: (payload: ApproveCaseRequest) => api.approveCase(caseId!, payload),
    onSuccess: () => navigate(`/research-cases/${encodeURIComponent(caseId!)}`),
    onError: (error) => setFormError(formatError(error)),
  });

  const busy = createMutation.isPending || reviseMutation.isPending || approveMutation.isPending;
  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    setFormError(null);
    const payload = body();
    if (!payload.purpose_code || !payload.purpose_text || !payload.basis_ref || !payload.subject_anchors[0]?.value) {
      setFormError("Purpose code, purpose text, authority-basis reference and a non-empty typed anchor are required.");
      return;
    }
    if (isEditing) reviseMutation.mutate(payload);
    else createMutation.mutate(payload);
  };

  if (caseQuery.isLoading) return <div className="p-6 text-sm text-slate-600">Loading case…</div>;
  if (caseQuery.error) return <div className="m-6 rounded border border-red-300 bg-white p-4 text-sm text-red-700">
    Unable to load this case. {formatError(caseQuery.error)}
  </div>;

  return (
    <main className="mx-auto max-w-4xl space-y-5 p-6">
      <header>
        <h1 className="text-xl font-semibold">{isEditing ? "Review case scope" : "Create research case"}</h1>
        <p className="mt-1 text-sm text-slate-600">
          This form records a case and its scope. Saving creates an immutable revision; it does not contact any source.
        </p>
        {existingCase && (
          <p className="mt-2 text-xs text-slate-500">
            Case {existingCase.case_id} · scope revision {existingCase.scope_revision} · {existingCase.approved ? "currently approved" : "not approved"}
          </p>
        )}
      </header>

      <form onSubmit={handleSubmit} className="space-y-5 rounded-lg border border-slate-200 bg-white p-5">
        <section className="space-y-3">
          <h2 className="font-semibold">Research question and authority</h2>
          <Field label="Purpose code">
            <input value={purposeCode} onChange={(e) => setPurposeCode(e.target.value)} required maxLength={100} className={inputClass} />
          </Field>
          <Field label="Research context / question">
            <textarea value={purposeText} onChange={(e) => setPurposeText(e.target.value)} required minLength={1} maxLength={2000} rows={3} className={inputClass} />
          </Field>
          <Field label="Authority / legal-basis reference">
            <input value={basisRef} onChange={(e) => setBasisRef(e.target.value)} required maxLength={500} className={inputClass} placeholder="Reference to the approving record or mandate" />
          </Field>
          <Field label="Launch profile">
            <select value={launchProfile} onChange={(e) => setLaunchProfile(e.target.value as LaunchProfile)} className={inputClass}>
              {LAUNCH_PROFILES.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </Field>
        </section>

        <section className="space-y-3 border-t border-slate-200 pt-4">
          <h2 className="font-semibold">Subject anchor</h2>
          <p className="text-xs text-slate-500">Use an anchor published for a professional/public context. No private contact details or credentials are requested here.</p>
          <Field label="Anchor kind">
            <select value={anchorKind} onChange={(e) => setAnchorKind(e.target.value as SubjectAnchor["kind"])} className={inputClass}>
              {ANCHOR_KINDS.map((kind) => <option key={kind} value={kind}>{kind}</option>)}
            </select>
          </Field>
          <Field label="Anchor value">
            <input value={anchorValue} onChange={(e) => setAnchorValue(e.target.value)} required className={inputClass} />
          </Field>
          <Field label="Evidence reference (optional)">
            <input value={anchorEvidenceRef} onChange={(e) => setAnchorEvidenceRef(e.target.value)} className={inputClass} />
          </Field>
        </section>

        <section className="space-y-3 border-t border-slate-200 pt-4">
          <h2 className="font-semibold">Scope and time</h2>
          <Field label="Claim families (comma separated)">
            <input value={claimFamiliesText} onChange={(e) => setClaimFamiliesText(e.target.value)} className={inputClass} />
          </Field>
          <Field label="Allowed source IDs (comma separated)">
            <input value={sourceIdsText} onChange={(e) => setSourceIdsText(e.target.value)} className={inputClass} placeholder="Source IDs from the current source policy" />
          </Field>
          <Field label="Explicitly denied claim families (comma separated)">
            <input value={deniedFamiliesText} onChange={(e) => setDeniedFamiliesText(e.target.value)} className={inputClass} />
          </Field>
          <Field label="Jurisdictions (comma separated)">
            <input value={jurisdictionsText} onChange={(e) => setJurisdictionsText(e.target.value)} className={inputClass} />
          </Field>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <Field label="Valid from (ISO date/time)">
              <input value={validFrom} onChange={(e) => setValidFrom(e.target.value)} className={inputClass} placeholder="2024-01-01" />
            </Field>
            <Field label="Valid until (ISO date/time)">
              <input value={validUntil} onChange={(e) => setValidUntil(e.target.value)} className={inputClass} />
            </Field>
            <Field label="Precision">
              <select value={precision} onChange={(e) => setPrecision(e.target.value as typeof precision)} className={inputClass}>
                {(["unknown", "instant", "day", "month", "year"] as const).map((value) => <option key={value}>{value}</option>)}
              </select>
            </Field>
          </div>
          <Field label="Questions (one per line)">
            <textarea value={questionsText} onChange={(e) => setQuestionsText(e.target.value)} rows={3} className={inputClass} />
          </Field>
        </section>

        <section className="space-y-3 border-t border-slate-200 pt-4">
          <h2 className="font-semibold">Execution controls</h2>
          <Field label="Budget reservation reference (optional; a reference alone is not a reservation)">
            <input value={budgetRef} onChange={(e) => setBudgetRef(e.target.value)} className={inputClass} />
          </Field>
          <Field label="Scope expiry (ISO date/time, optional)">
            <input value={expiresAt} onChange={(e) => setExpiresAt(e.target.value)} className={inputClass} />
          </Field>
        </section>

        {formError && <div role="alert" className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800">{formError}</div>}

        <div className="flex flex-wrap gap-2 border-t border-slate-200 pt-4">
          <button type="submit" disabled={busy} className="rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
            {busy ? "Saving…" : isEditing ? "Save new scope revision" : "Create draft case"}
          </button>
          {existingCase && !existingCase.approved && (
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setFormError(null);
                approveMutation.mutate({ scope_digest: existingCase.scope_digest, scope_revision: existingCase.scope_revision });
              }}
              className="rounded border border-blue-700 px-4 py-2 text-sm font-medium text-blue-800 disabled:opacity-50"
            >
              Approve current scope (admin)
            </button>
          )}
          {existingCase && (
            <button type="button" onClick={() => navigate(`/research-cases/${encodeURIComponent(existingCase.case_id)}`)} className="rounded border border-slate-300 px-4 py-2 text-sm">
              Cancel
            </button>
          )}
        </div>
        {existingCase && !existingCase.approved && (
          <p className="text-xs text-slate-500">Approval is a separate operation and requires an authenticated administrator. A new scope revision invalidates the previous approval.</p>
        )}
      </form>
    </main>
  );
}

function parseList(value: string, separator = ","): string[] {
  return Array.from(new Set(value.split(separator).map((item) => item.trim()).filter(Boolean)));
}

function formatError(error: unknown): string {
  if (error instanceof ApiError) return `HTTP ${error.status}: ${error.message}`;
  return error instanceof Error ? error.message : "Unknown request failure";
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="block space-y-1 text-sm"><span className="block text-slate-700">{label}</span>{children}</label>;
}

const inputClass = "w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-blue-500 focus:outline-none";
