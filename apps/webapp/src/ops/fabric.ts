import { toWorkStatus } from "../ui/status";
import type { ConnectorEcho, FabricRow, Unavailable } from "./types";
import { unavailable } from "./types";

/**
 * The acquisition fabric (§48).
 *
 * §48 requires SearXNG, Airbyte, Maigret, BBOT and SpiderFoot to read as items
 * of ONE fabric, not five bespoke cards. That constraint is what this file is
 * for, and it has a hard consequence: every value below is the runtime's own
 * declared vocabulary, copied from the acquisition service, never a display
 * label invented here.
 *
 *   searxng      runtime_ref "searxng"          execution_class "api/http"
 *   airbyte      runtime_ref "airbyte"          execution_class "connector_protocol"
 *   bbot         runtime_ref "bbot"             execution_class "event_producing"
 *   maigret      runtime_ref "maigret"          execution_class "external_process"
 *   spiderfoot   runtime_ref "spiderfoot"       execution_class "external_process"
 *
 * `capabilities()` is the list each runtime returns, verbatim. §13 forbids
 * *inferring* the worker from capabilities, so this file reads capabilities as
 * DESCRIPTIONS of a runtime that was already resolved by `runtime_ref` — the
 * order matters and is preserved in the comments.
 *
 * WHY THE FABRIC IS A MIRROR AND NOT A FETCH (§97, §99).
 *
 * There is no endpoint that lists acquisition runtimes. `/connectors` lists the
 * TENANT'S registered connectors, which is a different thing: a connector is a
 * policy-bound registration, a runtime is the executable behind it. Rendering
 * only `/connectors` would show an empty catalogue on a healthy deployment whose
 * runtimes were never registered as connectors — which reads as "no sources
 * exist" and is a false claim about the platform.
 *
 * So the catalogue is the runtime registry mirrored as data, with `declaredBy`
 * naming the Python module that owns each row, AND whatever `/connectors`
 * actually says joined on top. The mirror is the floor; the fetch is the truth
 * about this tenant. Every gap is named in `gaps`.
 *
 * The alternative — inventing a `/runtimes` client in the frontend — was
 * rejected: it would put a transport assumption in the UI (§2) and the endpoint
 * does not exist. This is reported as an integration item.
 */

/** Where each mirrored row's truth lives. A drift in the Python is a bug here too. */
export interface FabricDeclaration {
  readonly source: string;
  readonly runtimeRef: string;
  readonly executionClass: string;
  readonly capabilities: ReadonlyArray<string>;
  readonly declaredBy: string;
  /**
   * The pinned version the Python declares, when it declares one. `null` means
   * the runtime resolves its version at run time (`airbyte` derives it from the
   * image digest; `bbot` shells out to `--version`), which is why it cannot be
   * stated here without inventing one.
   */
  readonly pinnedVersion: string | null;
  /** What this runtime is known to reach, from its own contract. */
  readonly coverage: ReadonlyArray<string>;
}

export const FABRIC_DECLARATIONS: ReadonlyArray<FabricDeclaration> = [
  {
    source: "searxng",
    runtimeRef: "searxng",
    executionClass: "api/http",
    // searxng.py:126-128 — `capabilities()` returns exactly these four.
    capabilities: ["http", "search", "json-output", "paged"],
    declaredBy: "apps/acquisition/runtime/searxng.py",
    pinnedVersion: null,
    coverage: ["search-engine results", "HTML result pages", "paged result sets"],
  },
  {
    source: "airbyte",
    runtimeRef: "airbyte",
    executionClass: "connector_protocol",
    // airbyte.py:155-156.
    capabilities: ["connector-protocol", "stdio", "streaming", "stateful", "discover"],
    declaredBy: "apps/acquisition/runtime/airbyte.py",
    pinnedVersion: null,
    coverage: ["Airbyte connector sources", "STATE checkpoints (never evidence)"],
  },
  {
    source: "bbot",
    runtimeRef: "bbot",
    executionClass: "event_producing",
    // bbot.py:165-166.
    capabilities: ["recon", "event-stream", "passive", "dns", "subdomains", "streaming"],
    declaredBy: "apps/acquisition/runtime/bbot.py",
    pinnedVersion: null,
    coverage: ["subdomain enumeration", "DNS records", "passive recon event stream"],
  },
  {
    source: "maigret",
    runtimeRef: "maigret",
    executionClass: "external_process",
    // external_tool.py:261-262 is the runtime's own list; the tool definition at
    // :582-613 pins version 0.6.6 and resource_class "medium".
    capabilities: ["process", "container-isolated", "streaming", "resource-bounded"],
    declaredBy: "apps/acquisition/runtime/external_tool.py::TOOL_DEFINITIONS.maigret",
    pinnedVersion: "0.6.6",
    coverage: ["username → site account correlation"],
  },
  {
    source: "spiderfoot",
    runtimeRef: "spiderfoot",
    executionClass: "external_process",
    // Same runtime as maigret, different tool definition: :615-650, version
    // "unpinned" in the platform, so the row says "unpinned" rather than a guess.
    capabilities: ["process", "container-isolated", "streaming", "resource-bounded"],
    declaredBy: "apps/acquisition/runtime/external_tool.py::TOOL_DEFINITIONS.spiderfoot",
    pinnedVersion: "unpinned",
    coverage: ["SpiderFoot module scans", "typed scan events"],
  },
];

/**
 * Endpoints the catalogue needs and the control plane does not expose. Named so
 * the gap is a list another pass can close rather than a blank column.
 */
export const FABRIC_COVERAGE_MISSING: ReadonlyArray<string> = [
  "GET /acquisition/runtimes (the runtime registry: runtime_ref, execution_class, capabilities, readiness)",
  "GET /acquisition/runtimes/{runtime_ref}/health (RuntimeHealth.ready + the checks dict, §17/§103)",
  "GET /acquisition/runs?runtime_ref=… (run history: started_at, finished_at, outcome)",
  "GET /sources (the Source registry itself: source_id, quality_score, yield_est, cost_per_unit)",
];

/** A fabric row with nothing known about this tenant's usage of it. */
function baseRow(declaration: FabricDeclaration): FabricRow {
  return {
    source: declaration.source,
    runtimeRef: declaration.runtimeRef,
    executionClass: declaration.executionClass,
    capabilities: declaration.capabilities,
    declaredBy: declaration.declaredBy,
    health: null,
    version: declaration.pinnedVersion,
    lastRunAt: null,
    successRate: null,
    runsTotal: null,
    coverage: declaration.coverage,
    gaps: FABRIC_GAPS,
    connector: null,
  };
}

/** The same absences on every row: they are properties of the API, not of a source. */
const FABRIC_GAPS: ReadonlyArray<Unavailable> = [
  unavailable("No endpoint reports per-runtime readiness", "GET /acquisition/runtimes/{runtime_ref}/health"),
  unavailable("No run history is served, so last run and success rate are unknown", "GET /acquisition/runs"),
  unavailable(
    "The Source registry is not exposed, so yield, cost and quality per source are unknown",
    "GET /sources",
  ),
];

/** The wire shape `/connectors` returns, narrowed to the fields the catalogue reads. */
export interface ConnectorWire {
  readonly connector_id: string;
  readonly name: string;
  readonly status: string;
  readonly version: string;
  readonly policy_id: string;
  readonly source_types: string[];
  readonly contract_compliant: boolean;
}

/** A connector echo, reduced to what the catalogue renders. */
export function connectorEcho(connector: ConnectorWire): ConnectorEcho {
  return {
    connectorId: connector.connector_id,
    name: connector.name,
    status: toWorkStatus(connector.status),
    rawStatus: connector.status,
    version: connector.version,
    policyId: connector.policy_id,
    sourceTypes: connector.source_types,
    contractCompliant: connector.contract_compliant,
    runtimeRefHint: runtimeHintFor(connector.name),
  };
}

/**
 * The fabric, joined against whatever the tenant actually registered.
 *
 * `connectors` is matched on name first and on `runtime_ref` second. The second
 * match is the one that matters for `maigret` and `spiderfoot`, whose connector
 * names in a real deployment are things like `maigret-sites` — so an exact-name
 * join alone would silently drop the two external-tool runtimes from the
 * tenant's view while the mirrored rows still listed them, and the operator would
 * see a registered connector and an unclaimed runtime side by side without being
 * told they are the same thing.
 */
export function fabricRows(connectors: ReadonlyArray<ConnectorEcho>): FabricRow[] {
  return FABRIC_DECLARATIONS.map((declaration) => {
    const connector =
      connectors.find((entry) => entry.name === declaration.source) ??
      connectors.find((entry) => entry.name.startsWith(`${declaration.source}-`)) ??
      connectors.find((entry) => entry.runtimeRefHint === declaration.runtimeRef) ??
      null;

    const row = baseRow(declaration);
    if (connector === null) return row;

    return {
      ...row,
      // The connector's own version wins over the mirrored pin: it is what THIS
      // tenant runs, and a catalogue that shows the upstream pin while the tenant
      // runs a fork is lying about the tenant.
      version: connector.version !== "" ? connector.version : row.version,
      // Coverage gains the tenant's declared source types, which are facts the
      // mirrored contract cannot know.
      coverage: connector.sourceTypes.length > 0 ? [...row.coverage, ...connector.sourceTypes] : row.coverage,
      connector,
    };
  });
}

/**
 * `maigret-sites` → `maigret`; `subdomains-http` → null.
 *
 * A connector name like `maigret-sites` implies the runtime; a name like
 * `subdomains-http` implies none of the five and must not be claimed by any of
 * them. Deriving the hint from the name rather than from capabilities is §13
 * compliant: the name is an explicit declaration, the capability list is not.
 *
 * Longest declaration first, so a future `spiderfoot-crawler` cannot be claimed
 * by a shorter-prefixed `spider` declaration added later.
 */
export function runtimeHintFor(connectorName: string): string | null {
  const normalised = connectorName.toLowerCase();
  const match = FABRIC_DECLARATIONS.find(
    (declaration) =>
      normalised === declaration.source ||
      normalised.startsWith(`${declaration.source}-`) ||
      normalised.startsWith(`${declaration.source}_`),
  );
  return match?.runtimeRef ?? null;
}

/**
 * Adapt a served connector list.
 *
 * Kept as its own function so the only place `runtimeRefHint` is computed is
 * here: one derivation, one test, and a connector cannot reach the catalogue
 * with a hint that was guessed somewhere else.
 */
export function withRuntimeHints(connectors: ReadonlyArray<ConnectorWire>): ConnectorEcho[] {
  return connectors.map(connectorEcho);
}