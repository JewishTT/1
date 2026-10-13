import { useEffect, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { findingsKey } from "../lib/queryKeys";
import { resolveFindingsPath } from "../shell/nav";
import { EmptyState, ErrorView, LoadingView } from "../ui/Feedback";
import { FindingViewContainer } from "./FindingViewContainer";

/**
 * `/findings` — the findings destination, resolved to a record that exists.
 *
 * The nav used to point at the literal `/findings/0`. That was a placeholder id in a
 * real URL: `GET /api/v1/findings/0` answers 404, so the one tab that claimed to open
 * findings was the only destination guaranteed not to open one. A nav entry is static
 * and a finding id is not — ids are minted per tenant — so the nav names the list and
 * the resolution happens here, where `listFindings()` has just named the ids.
 *
 * This is the shape the retired `InvestigationGraphRoute` used for investigations: read
 * the list, take the head, navigate there with `replace` so the placeholder does not
 * stay in the history. The list endpoint returns findings ordered by id, so the head is
 * deterministic rather than arbitrary.
 *
 * TWO CASES RESOLVE, and the rule for both is "this id names nothing, so go to one that
 * does":
 *
 *   - no id at all (`/findings`) — the nav's destination.
 *   - an id the list does not contain (`/findings/0`, and any bookmark of a record that
 *     has since been removed). The second is why this is not just a `<Route path="findings">`
 *     redirect: a bookmark is a URL somebody kept, and a kept URL that 404s is the defect
 *     being fixed. `replace` means the address bar ends up naming the finding that was
 *     actually opened, so the redirect cannot itself become a stale bookmark.
 *
 * A named id that IS in the list renders the record itself — the normal path, untouched.
 *
 * An empty tenant renders an EmptyState. It does NOT fall back to `/investigations`:
 * "there are no findings" and "here are the investigations" are different answers, and
 * substituting one for the other is how a nav item ends up quietly pointing at something
 * other than what its label says.
 */
export function FindingsRoute() {
  const { id } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const [redirectedTo, setRedirectedTo] = useState<string | null>(null);

  const { data, isPending, isError, error } = useQuery({
    queryKey: findingsKey("route"),
    queryFn: () => api.listFindings(),
    staleTime: 60_000,
  });

  const findings = data?.findings ?? [];
  const target = resolveFindingsPath(findings.map((f) => f.finding_id));
  const resolves = id === undefined || !findings.some((f) => f.finding_id === id);

  useEffect(() => {
    // `redirectedTo` guards against re-firing on a refetch, which would push a
    // duplicate entry onto the history.
    if (!resolves || redirectedTo !== null || isPending || isError) return;
    if (target === null) return;
    navigate(target, { replace: true });
    setRedirectedTo(target);
  }, [resolves, redirectedTo, isPending, isError, target, navigate]);

  if (isError) return <ErrorView error={error instanceof Error ? error.message : String(error)} />;

  if (resolves) {
    if (isPending) return <LoadingView message="Resolving findings…" />;
    if (target === null) {
      return (
        <EmptyState
          icon="view-findings"
          title="No findings recorded"
          description="This tenant has produced no findings yet. A finding is a pattern the platform detected and explained — where, what it coincides with, and which evidence supports it. Nothing is listed because nothing has been detected."
          testId="findings-empty"
        />
      );
    }
    return <Navigate to={target} replace />;
  }

  return <FindingViewContainer />;
}
