/**
 * `/investigations/graph` - the investigation-scoped graph, reached directly.
 *
 * The graph has always been a view *inside* an investigation rather than a page of
 * its own, which is correct for scoping but left it unreachable except by opening an
 * investigation and switching views. The tenant-wide graph at `/ops/graph` had no such
 * step, so it was the only graph anyone could get to, and it answered questions about
 * one investigation with data from all of them.
 *
 * This resolves the nav destination to the most recent investigation and selects the
 * graph view, so the scoped graph is one click away and the two are never confused.
 */

import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { useWorkspace } from "../workspace/store";

export function InvestigationGraphRoute() {
  const navigate = useNavigate();
  const setView = useWorkspace((state) => state.setView);
  const setInvestigation = useWorkspace((state) => state.setInvestigation);
  const [resolved, setResolved] = useState(false);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["investigations", "graph-target"],
    queryFn: () => api.listInvestigations(),
  });

  useEffect(() => {
    if (resolved || isLoading || isError) return;
    const investigations = data?.investigations ?? [];
    if (investigations.length === 0) {
      setResolved(true);
      return;
    }
    // Most recent first; the list is already ordered, so take the head.
    const target = investigations[0];
    setInvestigation(target.investigation_id);
    setView("graph");
    navigate(`/investigations/${target.investigation_id}`, { replace: true });
  }, [data, isLoading, isError, navigate, resolved, setInvestigation, setView]);

  if (isError) return <Navigate to="/quarantine" replace />;
  if (!resolved && investigations_empty(data)) return <Navigate to="/investigations" replace />;

  return <div data-testid="investigation-graph-resolving">Opening the investigation graph...</div>;
}

function investigations_empty(data: { investigations?: unknown[] } | undefined): boolean {
  return Array.isArray(data?.investigations) && data.investigations.length === 0;
}