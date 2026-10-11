import { useCallback, useEffect, useState } from "react";

import { dossierApi } from "../lib/dossier/api";
import type {
  Discovered,
  Dossier,
  Refusal,
  SourceReport,
  SubjectSummary,
} from "../lib/dossier/types";
import { DossierPage } from "../pages/DossierPage";

const EMPTY_REPORTS: SourceReport[] = [];
const EMPTY_REFUSALS: Refusal[] = [];
const EMPTY_DISCOVERED: Discovered[] = [];
const EMPTY_KNOWN: string[] = [];

/**
 * Owns the dossier screen's state and every call that changes it.
 *
 * Two things are kept apart on purpose. A *sweep* mutates: it calls real sources and appends
 * to the stream, so it is slow, can fail per source, and must not be retried automatically.
 * A *read* is pure. Keeping them in one effect would mean a page load re-ran a sweep, and
 * re-running a sweep on every refresh is how a catalogue with 145 definitions turns a
 * navigation into minutes of outbound traffic.
 */
export function DossierContainer() {
  const [subjects, setSubjects] = useState<SubjectSummary[]>([]);
  const [dossier, setDossier] = useState<Dossier | null>(null);
  const [reports, setReports] = useState<SourceReport[]>(EMPTY_REPORTS);
  const [refusals, setRefusals] = useState<Refusal[]>(EMPTY_REFUSALS);
  const [discovered, setDiscovered] = useState<Discovered[]>(EMPTY_DISCOVERED);
  const [known, setKnown] = useState<string[]>(EMPTY_KNOWN);
  const [query, setQuery] = useState("");
  const [invariantError, setInvariantError] = useState("");
  const [sweeping, setSweeping] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadSubjects = useCallback(async () => {
    try {
      const raw = await dossierApi.listSubjects();
      setSubjects(raw.subjects);
    } catch {
      // A subject list that fails to load must not blank a dossier already on screen.
    }
  }, []);

  const open = useCallback(async (entityRef: string) => {
    setError(null);
    try {
      const loaded = await dossierApi.getDossier(entityRef);
      setDossier(loaded);
      setReports(EMPTY_REPORTS);
      setRefusals(EMPTY_REFUSALS);
      setDiscovered(EMPTY_DISCOVERED);
      setKnown(EMPTY_KNOWN);
      setInvariantError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    void loadSubjects();
  }, [loadSubjects]);

  const sweep = useCallback(
    async (subject: string, kind: string) => {
      setSweeping(true);
      setError(null);
      try {
        const result = await dossierApi.enrich({ subject, ...(kind ? { kind } : {}) });
        setQuery(result.query);
        setDossier(result.dossier);
        setReports(result.reports);
        setRefusals(result.refusals);
        setDiscovered(result.discovered);
        setKnown(result.known_attributes);
        setInvariantError(result.invariant_error);
        await loadSubjects();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setSweeping(false);
      }
    },
    [loadSubjects],
  );

  return (
    <DossierPage
      subjects={subjects}
      dossier={dossier}
      reports={reports}
      refusals={refusals}
      discovered={discovered}
      knownAttributes={known}
      query={query}
      sweeping={sweeping}
      error={error}
      invariantError={invariantError}
      onSweep={(subject, kind) => void sweep(subject, kind)}
      onOpen={(entityRef) => void open(entityRef)}
    />
  );
}
