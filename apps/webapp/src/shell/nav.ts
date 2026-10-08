/**
 * Navigation data, separated from both shells.
 *
 * This used to live inside `components/Layout.tsx`, which meant the destinations were
 * reachable only through the legacy shell. The UI 2.0 shell has no navigation of its
 * own, so moving the data out is what lets either shell render the same map and keeps
 * the two from drifting into different sets of destinations.
 *
 * Destinations, grouping and icon per item are carried over unchanged. Only the
 * *rendering* is new.
 */

import type { IconName } from "../ui/Icon";

export type ModuleKey = "osint" | "economic" | "specops";

export interface NavItem {
  to: string;
  label: string;
  icon: IconName;
}

export interface NavSection {
  label: string;
  items: NavItem[];
}

export interface NavModule {
  key: ModuleKey;
  short: string;
  label: string;
  /** Where the module tab goes when activated. */
  landing: string;
}

export const NAV_MODULES: NavModule[] = [
  { key: "osint", short: "OSINT", label: "Intelligence", landing: "/intel" },
  { key: "economic", short: "ECON", label: "Economics", landing: "/economic" },
  { key: "specops", short: "SPEC", label: "SpecOps", landing: "/ops" },
];

export const NAV_SECTIONS: Record<ModuleKey, NavSection[]> = {
  osint: [
    {
      label: "Intelligence",
      items: [
        { to: "/intel", label: "Intel Board", icon: "view-graph" },
        { to: "/search", label: "Search", icon: "search" },
      ],
    },
    {
      label: "Investigate",
      items: [
        { to: "/investigations", label: "Investigations", icon: "view-overview" },
        // The investigation-scoped graph. Distinct from "Tenant Graph" below, which
        // spans every investigation: two destinations whose labels both read "graph"
        // is how the tenant-wide one ended up looking like the investigation's.
        { to: "/investigations/graph", label: "Investigation Graph", icon: "view-graph" },
        { to: "/intel?entity=ENT-2001", label: "Entities", icon: "view-objects" },
        { to: "/findings/0", label: "Findings", icon: "view-findings" },
      ],
    },
    {
      label: "Science",
      items: [
        { to: "/science", label: "Science Console", icon: "diagram" },
        { to: "/network", label: "Network Analysis", icon: "view-analysis" },
        { to: "/hypotheses", label: "Hypotheses", icon: "list" },
        { to: "/experiments", label: "Experiments", icon: "copy" },
      ],
    },
    {
      label: "Acquisition",
      items: [{ to: "/connectors", label: "Connectors", icon: "link" }],
    },
  ],
  economic: [
    {
      label: "Econometriks",
      items: [{ to: "/economic", label: "Intelligence Economy", icon: "view-analysis" }],
    },
  ],
  specops: [
    {
      label: "Operations",
      items: [
        { to: "/ops", label: "SpecOps Console", icon: "activity" },
        // Tenant-wide, across every investigation. Named as such so it cannot be
        // mistaken for the investigation-scoped graph.
        { to: "/ops/graph", label: "Tenant Graph", icon: "view-graph" },
        { to: "/quarantine", label: "Quarantine / DLQ", icon: "alert" },
      ],
    },
  ],
};

/**
 * Breadcrumb titles, longest prefix first.
 *
 * Order matters and is not incidental: `/ops` is a prefix of `/ops/graph`, so a
 * naive first-match walk titles the graph page "SpecOps Console".
 */
export const NAV_TITLES: ReadonlyArray<{ prefix: string; title: string }> = [
  { prefix: "/ops/graph", title: "Tenant Graph (all investigations)" },
  { prefix: "/investigations/graph", title: "Investigation Graph" },
  { prefix: "/economic", title: "Intelligence Economy" },
  { prefix: "/network", title: "Network & TDA analysis" },
  { prefix: "/quarantine", title: "Quarantine (DLQ)" },
  { prefix: "/investigations", title: "Investigation" },
  { prefix: "/entities", title: "Entity" },
  { prefix: "/findings", title: "Finding" },
  { prefix: "/hypotheses", title: "Hypotheses & gain planning" },
  { prefix: "/experiments", title: "Reproducible experiments" },
  { prefix: "/connectors", title: "Connectors & Recon Plans" },
  { prefix: "/science", title: "Scientific review" },
  { prefix: "/search", title: "Evidence-backed search" },
  { prefix: "/ops", title: "SpecOps Console" },
  { prefix: "/intel", title: "OSINT // Intel Board" },
];

export function resolveModule(pathname: string): ModuleKey {
  const segment = pathname.split("/")[1];
  if (segment === "ops" || segment === "quarantine") return "specops";
  if (segment === "economic") return "economic";
  return "osint";
}

export function resolveTitle(pathname: string): string {
  for (const entry of NAV_TITLES) {
    if (pathname.startsWith(entry.prefix)) return entry.title;
  }
  return "Dashboard";
}

/**
 * True when `pathname` (and `search`) is the destination.
 *
 * The search matters because two destinations share a pathname: "Intel Board" is
 * `/intel` and "Entities" is `/intel?entity=ENT-2001`. react-router's own active test
 * ignores the query, so on a plain `/intel` both links would render as current. When a
 * destination declares a query, the query has to match for the link to count as
 * current, and a bare-path destination stays current on its path alone.
 */
export function isNavItemActive(pathname: string, item: NavItem, search = ""): boolean {
  const [to, query] = item.to.split("?");
  if (query !== undefined) {
    if (pathname !== to) return false;
    const wanted = new URLSearchParams(query);
    const actual = new URLSearchParams(search);
    for (const [key, value] of wanted) {
      if (actual.get(key) !== value) return false;
    }
    return true;
  }
  // A bare-path destination is current only on its own path, not on every path that
  // starts with those characters.
  if (to === "/intel") return pathname === "/intel";
  return pathname === to || pathname.startsWith(`${to}/`);
}
