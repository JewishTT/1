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
  { key: "specops", short: "SPECOPS", label: "SpecOps", landing: "/specops" },
];

export const NAV_SECTIONS: Record<ModuleKey, NavSection[]> = {
  osint: [
    {
      label: "COLLECT",
      items: [{ to: "/search", label: "Search", icon: "search" }],
    },
    {
      label: "INVESTIGATE",
      items: [
        // One destination. The graph of every investigation and the graph of one are the
        // same surface at two scopes, so they were never two tabs -- they were one tab
        // twice. `Investigations` opens on the tenant-wide canvas and narrows in place;
        // a URL kept for each is a URL an analyst has to remember which of the two they
        // meant, which is the opposite of what scoping is for.
        { to: "/investigations", label: "Investigations", icon: "view-graph" },
        { to: "/research-cases", label: "Research Cases", icon: "view-evidence" },
        { to: "/intel?entity=ENT-2001", label: "Entities", icon: "view-objects" },
        // The findings destination is a LIST route, not one finding's page. It used to
        // carry the literal `/findings/0`, which named no record: the detail endpoint
        // answered 404 for every click, so the one tab that claimed to open findings
        // was the one destination guaranteed not to open one. `resolveFindingsPath`
        // below turns the list into a real id once the ids are known.
        { to: "/findings", label: "Findings", icon: "view-findings" },
      ],
    },
    {
      label: "ANALYZE",
      items: [
        { to: "/science", label: "Science Console", icon: "diagram" },
        { to: "/network", label: "Network Analysis", icon: "view-analysis" },
        { to: "/hypotheses", label: "Hypotheses", icon: "list" },
        // Per-subject dossier: what is known, what was refused, what was never asked.
        // Placed with the investigative surfaces because it is the readout of a sweep.
        { to: "/dossier", label: "Dossier", icon: "view-evidence" },
        { to: "/experiments", label: "Experiments", icon: "copy" },
      ],
    },
  ],
  economic: [
    {
      label: "ECONOMIC INTELLIGENCE",
      items: [{ to: "/economic", label: "Intelligence Economy", icon: "view-analysis" }],
    },
  ],
  specops: [
    {
      label: "COUNTERINTEL",
      items: [
        // The CI/SpecOps department (Feature 027): a view within the investigation
        // workspace, reached as one canvas with internal panels. Filed under the
        // SPEC module beside Ops because it is an operations surface, but it is a
        // DIFFERENT subject from pipeline health — kill-chain emulation, phishing/SAT,
        // APT forensics, counterintelligence and social-reaction — NOT throughput or
        // worker pools. The scope note on the canvas keeps the tenant-wide honesty.
        { to: "/investigations/ci", label: "CI / SpecOps Department", icon: "view-ops" },
      ],
    },
    {
      label: "OPERATIONS",
      items: [
        { to: "/specops", label: "Pipeline Operations", icon: "activity" },
        { to: "/specops/quarantine", label: "Quarantine / DLQ", icon: "alert" },
        // Connectors is an operations surface: it registers the machinery the
        // pipeline runs on. Filed under OSINT it read as investigative, which is
        // what made a registration form look like a way to gather intelligence.
        { to: "/specops/connectors", label: "Connectors", icon: "link" },
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
  { prefix: "/economic", title: "Intelligence Economy" },
  { prefix: "/network", title: "Network & TDA analysis" },
  // Before "/investigations" so the department view is titled as itself, not as a
  // bare "Investigation": the department is a view within an investigation.
  { prefix: "/investigations/ci", title: "CI / SpecOps Department" },
  { prefix: "/research-cases", title: "Person Research Case" },
  { prefix: "/investigations", title: "Investigation" },
  { prefix: "/entities", title: "Entity" },
  { prefix: "/findings", title: "Finding" },
  { prefix: "/hypotheses", title: "Hypotheses & gain planning" },
  { prefix: "/dossier", title: "Dossier" },
  { prefix: "/experiments", title: "Reproducible experiments" },
  { prefix: "/specops/connectors", title: "Connectors & Recon Plans" },
  { prefix: "/specops/quarantine", title: "Quarantine (DLQ)" },
  { prefix: "/specops", title: "SpecOps Console" },
  { prefix: "/science", title: "Scientific review" },
  { prefix: "/search", title: "Evidence-backed search" },
  // Kept after the longer prefixes on purpose: "/ops" would otherwise swallow every
  // /ops/* destination, including this one.
  // Retired bare paths keep their titles so a bookmarked one still names what it
  // lands on after the redirect.
  { prefix: "/quarantine", title: "Quarantine (DLQ)" },
  { prefix: "/connectors", title: "Connectors & Recon Plans" },
  { prefix: "/ops", title: "SpecOps Console" },
];

export function resolveModule(pathname: string): ModuleKey {
  const segment = pathname.split("/")[1];
  // Keyed on the segment that opens the destination, not on any of the screens it
  // contains. `/specops`, `/specops/quarantine` and `/specops/connectors` are one module;
  // matching on the leaf would have put two of its three surfaces in OSINT.
  if (segment === "specops") return "specops";
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

/**
 * The findings destination resolved against the findings that actually exist.
 *
 * The nav cannot carry a finding id, because a nav entry is static and a finding id
 * is not: ids are minted per tenant by whatever produced the record. The literal
 * `/findings/0` that sat there was exactly that mistake — a hardcoded guess at an id,
 * which `GET /api/v1/findings/0` answered 404 for on every click. "0" was never a
 * finding; it was a placeholder wearing a finding's URL.
 *
 * So the nav names the LIST (`/findings`) and the resolution happens where the ids
 * are known, against the list endpoint. This is the same shape the retired
 * `InvestigationGraphRoute` used for investigations: take the head of the ordered
 * list and go there, because one real record beats one plausible id.
 *
 * Returns null when the tenant has no findings at all. That is not a reason to invent
 * an id — the caller renders the honest empty state instead, and `null` is what lets
 * it tell "nothing exists" from "something exists but I could not name it".
 */
export function resolveFindingsPath(findingIds: ReadonlyArray<string>): string | null {
  const target = findingIds.find((id) => typeof id === "string" && id.trim() !== "");
  return target === undefined ? null : `/findings/${encodeURIComponent(target)}`;
}
