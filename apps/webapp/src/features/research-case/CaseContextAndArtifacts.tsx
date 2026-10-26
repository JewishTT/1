import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ResearchCase, type CaseArtifact, type ContextAmendment } from "./api";

interface CaseContextAndArtifactsProps {
  caseId: string;
  caseData: ResearchCase;
}

const amendmentKinds: ContextAmendment["kind"][] = [
  "context",
  "query_hint",
  "constraint",
  "question",
];
const invariantKinds = [
  "public_name",
  "orcid",
  "openalex_author_id",
  "doi_author_record",
  "official_profile_url",
  "public_organization",
  "publication",
  "public_role",
] as const;

export function CaseContextAndArtifacts({
  caseId,
  caseData,
}: CaseContextAndArtifactsProps) {
  const queryClient = useQueryClient();
  const [amendmentKind, setAmendmentKind] = useState<ContextAmendment["kind"]>("context");
  const [amendmentBody, setAmendmentBody] = useState("");
  const [amendmentRationale, setAmendmentRationale] = useState("");
  const [anchorKind, setAnchorKind] = useState<(typeof invariantKinds)[number]>("public_name");
  const [anchorValue, setAnchorValue] = useState("");
  const [anchorEvidence, setAnchorEvidence] = useState("");
  const [anchorNote, setAnchorNote] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [caption, setCaption] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["research-case", caseId] }),
      queryClient.invalidateQueries({ queryKey: ["research-case-coverage", caseId] }),
      queryClient.invalidateQueries({ queryKey: ["research-case-actions", caseId] }),
      queryClient.invalidateQueries({ queryKey: ["research-case-obligations", caseId] }),
      queryClient.invalidateQueries({ queryKey: ["research-case-artifacts", caseId] }),
    ]);
  };

  const artifactsQuery = useQuery({
    queryKey: ["research-case-artifacts", caseId],
    queryFn: () => api.listArtifacts(caseId),
  });

  const amendmentMutation = useMutation({
    mutationFn: () => api.appendContextAmendment(caseId, {
      body: amendmentBody.trim(),
      rationale: amendmentRationale.trim(),
      kind: amendmentKind,
    }),
    onSuccess: async () => {
      setAmendmentBody("");
      setAmendmentRationale("");
      setFormError(null);
      await refresh();
    },
    onError: (error) => setFormError(error instanceof Error ? error.message : "Could not append context amendment."),
  });

  const invariantMutation = useMutation({
    mutationFn: () => api.addDynamicInvariantAnchor(caseId, {
      kind: anchorKind,
      value: anchorValue.trim(),
      evidence_ref: anchorEvidence.trim(),
      note: anchorNote.trim(),
    }),
    onSuccess: async () => {
      setAnchorValue("");
      setAnchorEvidence("");
      setAnchorNote("");
      setFormError(null);
      await refresh();
    },
    onError: (error) => setFormError(error instanceof Error ? error.message : "Could not add invariant anchor."),
  });

  const uploadMutation = useMutation({
    mutationFn: () => {
      if (!file) throw new Error("Choose a file first.");
      return api.uploadArtifact(caseId, file, caption.trim());
    },
    onSuccess: async () => {
      setFile(null);
      setCaption("");
      setFormError(null);
      await refresh();
    },
    onError: (error) => setFormError(error instanceof Error ? error.message : "Could not upload artifact."),
  });

  const busy = amendmentMutation.isPending || invariantMutation.isPending || uploadMutation.isPending;
  const submitAmendment = (event: FormEvent) => {
    event.preventDefault();
    setFormError(null);
    if (!amendmentBody.trim()) {
      setFormError("Context amendment cannot be empty.");
      return;
    }
    amendmentMutation.mutate();
  };
  const submitInvariant = (event: FormEvent) => {
    event.preventDefault();
    setFormError(null);
    if (!anchorValue.trim()) {
      setFormError("Dynamic invariant anchor requires a value.");
      return;
    }
    invariantMutation.mutate();
  };
  const submitUpload = (event: FormEvent) => {
    event.preventDefault();
    setFormError(null);
    if (!file) {
      setFormError("Choose a file first.");
      return;
    }
    uploadMutation.mutate();
  };

  return (
    <div className="space-y-4">
      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h2 className="text-sm font-semibold text-slate-800">Context revisions</h2>
            <p className="mt-1 text-xs text-slate-500">
              Additions are append-only. A new context revision changes the scope digest and requires a fresh approval before planning or dispatch.
            </p>
          </div>
          <span className="rounded-full bg-amber-50 px-2 py-1 text-xs text-amber-800">
            Scope revision {caseData.scope_revision}
          </span>
        </div>
        <form onSubmit={submitAmendment} className="mt-4 space-y-3">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <label className="space-y-1 text-xs text-slate-600">
              <span className="block">Amendment kind</span>
              <select value={amendmentKind} onChange={(e) => setAmendmentKind(e.target.value as ContextAmendment["kind"])} className={fieldClass}>
                {amendmentKinds.map((kind) => <option key={kind} value={kind}>{kind}</option>)}
              </select>
            </label>
            <label className="space-y-1 text-xs text-slate-600 md:col-span-2">
              <span className="block">Rationale (optional)</span>
              <input value={amendmentRationale} onChange={(e) => setAmendmentRationale(e.target.value)} maxLength={2000} className={fieldClass} placeholder="Why this context addition matters" />
            </label>
          </div>
          <label className="block space-y-1 text-xs text-slate-600">
            <span className="block">Context addition</span>
            <textarea value={amendmentBody} onChange={(e) => setAmendmentBody(e.target.value)} required maxLength={4000} rows={3} className={fieldClass} placeholder="New information, query hint, constraint or question…" />
          </label>
          <button disabled={busy || !amendmentBody.trim()} className={primaryButton}>
            {amendmentMutation.isPending ? "Appending revision…" : "Append context revision"}
          </button>
        </form>
        <ol className="mt-4 space-y-2">
          {(caseData.context_amendments ?? []).map((item) => (
            <li key={item.amendment_id} className="rounded border border-slate-200 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  #{item.ordinal} · {item.kind}
                </span>
                <span className="text-xs text-slate-500">{item.created_at}</span>
              </div>
              <p className="mt-2 whitespace-pre-wrap text-sm text-slate-800">{item.body}</p>
              {item.rationale && <p className="mt-1 text-xs text-slate-500">Rationale: {item.rationale}</p>}
            </li>
          ))}
          {(caseData.context_amendments ?? []).length === 0 && (
            <li className="text-xs text-slate-500">No context amendments have been recorded.</li>
          )}
        </ol>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="text-sm font-semibold text-slate-800">Dynamic invariant anchors</h2>
        <p className="mt-1 text-xs text-slate-500">
          These are unresolved references, not admitted identities. Resolution and merge require the existing canonical review/admission path.
        </p>
        <form onSubmit={submitInvariant} className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
          <label className="space-y-1 text-xs text-slate-600">
            <span className="block">Anchor kind</span>
            <select value={anchorKind} onChange={(e) => setAnchorKind(e.target.value as (typeof invariantKinds)[number])} className={fieldClass}>
              {invariantKinds.map((kind) => <option key={kind} value={kind}>{kind}</option>)}
            </select>
          </label>
          <label className="space-y-1 text-xs text-slate-600">
            <span className="block">Anchor value</span>
            <input value={anchorValue} onChange={(e) => setAnchorValue(e.target.value)} required maxLength={1000} className={fieldClass} />
          </label>
          <label className="space-y-1 text-xs text-slate-600">
            <span className="block">Evidence reference (optional)</span>
            <input value={anchorEvidence} onChange={(e) => setAnchorEvidence(e.target.value)} maxLength={1000} className={fieldClass} />
          </label>
          <label className="space-y-1 text-xs text-slate-600">
            <span className="block">Analyst note (optional)</span>
            <input value={anchorNote} onChange={(e) => setAnchorNote(e.target.value)} maxLength={2000} className={fieldClass} />
          </label>
          <div className="md:col-span-2">
            <button disabled={busy || !anchorValue.trim()} className={primaryButton}>
              {invariantMutation.isPending ? "Adding anchor…" : "Add unresolved dynamic anchor"}
            </button>
          </div>
        </form>
        <div className="mt-4 space-y-2">
          {(caseData.dynamic_invariant_anchors ?? []).map((anchor) => (
            <div key={anchor.anchor_id} className="flex flex-wrap items-start justify-between gap-2 rounded border border-slate-200 p-3">
              <div className="min-w-0">
                <div className="break-words text-sm font-medium">{anchor.kind}: {anchor.value}</div>
                <div className="mt-1 text-xs text-slate-500">
                  {anchor.anchor_id} · added by {anchor.created_by} · {anchor.created_at}
                </div>
                {anchor.evidence_ref && <div className="mt-1 break-all text-xs text-slate-500">Evidence: {anchor.evidence_ref}</div>}
                {anchor.note && <p className="mt-1 text-xs text-slate-500">{anchor.note}</p>}
              </div>
              <span className="rounded-full bg-amber-50 px-2 py-1 text-xs text-amber-800">{anchor.state}</span>
            </div>
          ))}
          {(caseData.dynamic_invariant_anchors ?? []).length === 0 && (
            <p className="text-xs text-slate-500">No dynamic invariant anchors have been recorded.</p>
          )}
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h2 className="text-sm font-semibold text-slate-800">Static artifacts</h2>
            <p className="mt-1 text-xs text-slate-500">
              Original bytes are stored through ArtifactSink and become a Capture/Observation for the standard interpretation consumer. Upload receipt time is not represented as a source fetch time.
            </p>
          </div>
          {artifactsQuery.data && <span className="text-xs text-slate-500">{artifactsQuery.data.count} files</span>}
        </div>
        <form onSubmit={submitUpload} className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
          <label className="space-y-1 text-xs text-slate-600">
            <span className="block">Original file (25 MiB max)</span>
            <input
              type="file"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              className="block w-full rounded border border-slate-300 bg-white p-2 text-sm"
            />
            {file && <span className="block text-xs text-slate-500">{file.name} · {file.size.toLocaleString()} bytes · {file.type || "application/octet-stream"}</span>}
          </label>
          <label className="space-y-1 text-xs text-slate-600">
            <span className="block">Caption (optional)</span>
            <input value={caption} onChange={(e) => setCaption(e.target.value)} maxLength={2000} className={fieldClass} />
          </label>
          <div className="md:col-span-2">
            <button disabled={busy || !file} className={primaryButton}>
              {uploadMutation.isPending ? "Persisting raw evidence…" : "Upload immutable original"}
            </button>
          </div>
        </form>
        {artifactsQuery.isLoading && <p className="mt-4 text-xs text-slate-500">Loading artifact ledger…</p>}
        {artifactsQuery.error && (
          <p role="alert" className="mt-4 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
            Artifact ledger unavailable: {artifactsQuery.error instanceof Error ? artifactsQuery.error.message : "request failed"}
          </p>
        )}
        <div className="mt-4 space-y-2">
          {(artifactsQuery.data?.artifacts ?? []).map((artifact: CaseArtifact) => (
            <article key={artifact.artifact_id} className="rounded border border-slate-200 p-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="break-words text-sm font-medium">{artifact.filename}</div>
                  <div className="mt-1 text-xs text-slate-500">
                    {artifact.byte_length.toLocaleString()} bytes · {artifact.content_type} · {artifact.created_at ?? "timestamp unknown"}
                  </div>
                  {artifact.caption && <p className="mt-2 text-sm text-slate-700">{artifact.caption}</p>}
                  <div className="mt-2 break-all font-mono text-xs text-slate-500">SHA-256: {artifact.content_digest}</div>
                  <div className="mt-1 break-all text-xs text-slate-500">
                    Capture {artifact.capture_id} · Observation {artifact.observation_id}
                  </div>
                </div>
                <a href={artifact.download_path} className="shrink-0 text-sm font-medium text-blue-700 underline" download>
                  Download verified original
                </a>
              </div>
            </article>
          ))}
          {!artifactsQuery.isLoading && !artifactsQuery.error && (artifactsQuery.data?.artifacts ?? []).length === 0 && (
            <p className="text-xs text-slate-500">No static artifacts have been attached.</p>
          )}
        </div>
      </section>

      {formError && (
        <div role="alert" className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800">{formError}</div>
      )}
    </div>
  );
}

const fieldClass = "w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900";
const primaryButton = "rounded bg-slate-900 px-3 py-2 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50";
