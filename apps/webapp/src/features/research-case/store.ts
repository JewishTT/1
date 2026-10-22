/**
 * Transient view state for the research-case workbench.
 *
 * Zustand is used only for UI-transient state (selected node, graph filters,
 * active tab). Canonical case data lives in the server and is fetched through
 * TanStack Query; it is never duplicated here.
 */

import { create } from "zustand";
import { persist, devtools } from "zustand/middleware";

export interface ResearchCaseViewState {
  selectedTab: "overview" | "claims" | "timeline" | "graph" | "sources" | "ach" | "report";
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  graphDepth: number;
  showPossibleMatch: boolean;
  epistemicFilter: ("TRUE_ONLY" | "FALSE_ONLY" | "BOTH" | "NEITHER")[];
  setSelectedTab: (tab: ResearchCaseViewState["selectedTab"]) => void;
  setSelectedNode: (id: string | null) => void;
  setSelectedEdge: (id: string | null) => void;
  setGraphDepth: (depth: number) => void;
  togglePossibleMatch: () => void;
  setEpistemicFilter: (filters: ResearchCaseViewState["epistemicFilter"]) => void;
}

const EPISTEMIC_ALL: ResearchCaseViewState["epistemicFilter"] = ["TRUE_ONLY", "FALSE_ONLY", "BOTH", "NEITHER"];

export const useResearchCaseView = create<ResearchCaseViewState>()(
  devtools(
    persist(
      (set) => ({
        selectedTab: "overview",
        selectedNodeId: null,
        selectedEdgeId: null,
        graphDepth: 1,
        showPossibleMatch: true,
        epistemicFilter: EPISTEMIC_ALL,
        setSelectedTab: (tab) => set({ selectedTab: tab }),
        setSelectedNode: (id) => set({ selectedNodeId: id }),
        setSelectedEdge: (id) => set({ selectedEdgeId: id }),
        setGraphDepth: (depth) => set({ graphDepth: depth }),
        togglePossibleMatch: set((s) => ({ showPossibleMatch: !s.showPossibleMatch })),
        setEpistemicFilter: (filters) => set({ epistemicFilter: filters }),
      }),
      { name: "research-case-view" },
    ),
  ),
);
