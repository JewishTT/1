import { useMemo } from "react";

import { Badge, StatusDot } from "../ui/Badge";
import { Button } from "../ui/Button";
import { EmptyState, Skeleton } from "../ui/Feedback";
import { FABRIC_COVERAGE_MISSING, fabricRows } from "./fabric";
import { useCatalogState } from "./useOpsState";
import type { FabricRow } from "./types";
import "./ops.css";

/**
 * SourceCatalog (§48).
 *
 * §48 requires SearXNG, Airbyte, Maigret, BBOT and SpiderFoot to appear as
 * ITEMS OF ONE ACQUISITION FABRIC with their real `runtime_ref` and
 * capabilities — not five bespoke cards. That is a structural requirement, and
 * it is the reason this is one table with one row shape rather than five
 * panels: a fabric is a registry, and a registry whose entries each get their
 * own layout is a list of tools wearing a registry's clothes.
 *
 * §97 AND §99 — THE MIRROR, AND WHY IT IS NOT A FETCH.
 *
 * There is no endpoint that lists acquisition runtimes. `/connectors` lists the
 * TENANT'S registered connectors, which is a different thing: a connector is a
 * policy-bound registration and a runtime is the executable behind it. A
 * catalogue built only from `/connectors` would render empty on a healthy
 * deployment whose runtimes were never registered as connectors, and an empty
 * catalogue reads as "this platform has no sources" — a false claim.
 *
 * So the catalogue is the runtime registry mirrored as data (each row naming the
 * Python module that owns it) with `/connectors` joined on top for what THIS
 * tenant runs. The mirror is the floor; the fetch is the truth about the tenant.
 * Reporting an invented client for an endpoint that does not exist was rejected:
 * that is a transport assumption in the UI, and §2 keeps it out.
 *
 * Health, last run, success rate and yield are `null` on every row today, because
 * no served endpoint reports them. `null` renders as "not served" with the
 * endpoint named, never as a zero — a success rate of 0% would be a claim about
 * a run that never happened.
 */

/** Capabilities as one inline run, not five chips — one fabric, one shape. */
function CapabilitiesCell({ row }: { row: FabricRow }) {
  return (
    <span className="ui-catalog-caps" data-testid={`catalog-caps-${row.runtimeRef}`}>
      {row.capabilities.map((capability, index) => (
        <span key={capability}>
          {index > 0 ? <span className="ui-catalog-caps-sep" aria-hidden="true"> · </span> : null}
          {capability}
        </span>
      ))}
    </span>
  );
}

function CatalogRow({ row }: { row: FabricRow }) {
  return (
    <>
      <div
        className="ui-catalog-table ui-catalog-row"
        role="row"
        data-runtime-ref={row.runtimeRef}
        data-testid={`catalog-row-${row.runtimeRef}`}
      >
        <span className="ui-catalog-cell">
          <span className="ui-catalog-source">{row.source}</span>
        </span>
        <span className="ui-catalog-cell" data-mono="true">
          {row.runtimeRef}
          <span className="ui-quar-absent">{row.executionClass}</span>
        </span>
        <span className="ui-catalog-cell" data-mono="true">
          <CapabilitiesCell row={row} />
        </span>
        <span className="ui-catalog-cell">
          <span className="ui-catalog-coverage">
            {row.coverage.map((entry) => (
              <span key={entry}>{entry}</span>
            ))}
          </span>
        </span>
        <span className="ui-catalog-cell">
          {row.health === null ? (
            <span className="ui-quar-absent" data-testid={`catalog-health-absent-${row.runtimeRef}`}>
              not served
            </span>
          ) : (
            <StatusDot status={row.health} />
          )}
        </span>
        <span className="ui-catalog-cell" data-mono="true">
          {row.version === null ? (
            <span className="ui-quar-absent">resolved at run time</span>
          ) : (
            row.version
          )}
        </span>
        <span className="ui-catalog-cell" data-mono="true">
          {row.lastRunAt === null ? (
            <span className="ui-quar-absent" data-testid={`catalog-lastrun-absent-${row.runtimeRef}`}>
              not served
            </span>
          ) : (
            row.lastRunAt
          )}
        </span>
        <span className="ui-catalog-cell" data-mono="true">
          {row.successRate === null ? (
            <span className="ui-quar-absent" data-testid={`catalog-success-absent-${row.runtimeRef}`}>
              not served
            </span>
          ) : (
            `${(row.successRate * 100).toFixed(1)} %`
          )}
        </span>
      </div>

      {/*
       * The row note carries what the row cannot. It is the one place the §48
       * table admits it is incomplete, and it says which endpoint would complete
       * it — so an operator is never left guessing whether a blank is a fault or
       * a gap.
       */}
      <div className="ui-catalog-row-note" data-testid={`catalog-note-${row.runtimeRef}`}>
        {row.connector !== null ? (
          <>
            Connector <span className="ui-mono">{row.connector.name}</span> ·{" "}
            <StatusDot status={row.connector.status} label={row.connector.rawStatus} /> · policy{" "}
            <span className="ui-mono">{row.connector.policyId}</span> ·{" "}
            {row.connector.contractCompliant ? "satisfies the AcquisitionWorker contract" : "does not satisfy the AcquisitionWorker contract"} ·{" "}
            {row.runsTotal === null ? "no run history is served" : `${row.runsTotal} run(s)`}
          </>
        ) : (
          <>
            No connector is registered for this runtime, so nothing about this tenant's use of it is known. Declared
            by <span className="ui-quar-gap-endpoint">{row.declaredBy}</span>.{" "}
            {row.gaps[0].reason.toLowerCase()}.
          </>
        )}
      </div>
    </>
  );
}

/** The connector registry, for the connectors that are not one of the five runtimes. */
function OtherConnectors({ connectors }: { connectors: ReturnType<typeof useCatalogState>["connectors"] }) {
  const unclaimed = connectors.filter((connector) => connector.runtimeRefHint === null);
  if (unclaimed.length === 0) return null;

  return (
    <section className="ui-ops-block" data-testid="catalog-other-connectors">
      <div className="ui-ops-block-head">
        <span className="ui-pane-title">Connectors outside the fabric</span>
        <span className="ui-ops-block-note">
          {unclaimed.length} registered · their names declare no runtime, so they are not attributed to one (§13)
        </span>
      </div>
      <div className="ui-catalog-grid" role="table" aria-label="Connectors outside the acquisition fabric">
        <div className="ui-catalog-grid ui-catalog-head" role="row">
          <span role="columnheader">Connector</span>
          <span role="columnheader">Status</span>
          <span role="columnheader">Source types</span>
          <span role="columnheader">Version</span>
          <span role="columnheader">Policy</span>
          <span role="columnheader">Contract</span>
        </div>
        {unclaimed.map((connector) => (
          <div key={connector.connectorId} className="ui-catalog-grid ui-catalog-row" role="row" data-testid={`catalog-connector-${connector.name}`}>
            <span className="ui-catalog-cell" data-mono="true">
              {connector.name}
            </span>
            <span className="ui-catalog-cell">
              <StatusDot status={connector.status} label={connector.rawStatus} />
            </span>
            <span className="ui-catalog-cell" data-mono="true">
              {connector.sourceTypes.length === 0 ? (
                <span className="ui-quar-absent">none declared</span>
              ) : (
                connector.sourceTypes.join(", ")
              )}
            </span>
            <span className="ui-catalog-cell" data-mono="true">
              {connector.version === "" ? <span className="ui-quar-absent">not reported</span> : connector.version}
            </span>
            <span className="ui-catalog-cell" data-mono="true">
              {connector.policyId}
            </span>
            <span className="ui-catalog-cell">
              {connector.contractCompliant ? "compliant" : <span className="ui-quar-blocked">not compliant</span>}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

export interface SourceCatalogProps {
  /** Set false to hold the query at pending, so a harness can capture loading. */
  enabled?: boolean;
}

export function SourceCatalog({ enabled = true }: SourceCatalogProps) {
  const server = useCatalogState(enabled);
  const rows = useMemo(() => fabricRows(server.connectors), [server.connectors]);

  if (server.loading) {
    return (
      <section className="ui-catalog ui-root" aria-label="Source catalogue" data-testid="source-catalog">
        <Skeleton rows={8} label="Loading the acquisition fabric" />
      </section>
    );
  }

  if (server.error !== null) {
    return (
      <section className="ui-catalog ui-root" aria-label="Source catalogue" data-testid="source-catalog">
        <div className="ui-inspector-error" role="alert" data-testid="catalog-error">
          <p className="ui-pane-title">The connector registry did not load</p>
          <p className="ui-body" data-testid="catalog-error-message">
            {server.error}
          </p>
          <p className="ui-body">
            Scope: <span className="ui-mono">GET /connectors</span> — this tenant's registered connectors. The fabric
            below is declared from the acquisition runtimes and is unaffected, so the rows you see are real even
            though the tenant's registrations are missing.
          </p>
          <div className="ui-insp-next-list">
            <Button size="sm" onClick={server.refetch} data-testid="catalog-error-retry">
              Retry
            </Button>
          </div>
        </div>
      </section>
    );
  }

  const claimedCount = rows.filter((row) => row.connector !== null).length;

  return (
    <section className="ui-catalog ui-root" aria-label="Source catalogue" data-testid="source-catalog">
      <header className="ui-ops-head">
        <div className="ui-ops-head-titles">
          <h2 className="ui-title" data-testid="catalog-title">
            Acquisition fabric
          </h2>
          <span className="ui-id" data-testid="catalog-subtitle">
            {rows.length} runtime(s) · one registry, one row shape (§48) · {claimedCount} with a registered connector
          </span>
        </div>
        <Badge tone={claimedCount === rows.length ? "accent" : "gold"} role="classification" testId="catalog-headline">
          {claimedCount === rows.length ? "all runtimes registered" : `${rows.length - claimedCount} unregistered`}
        </Badge>
      </header>

      <div
        className="ui-ops-block ui-scroll"
        role="table"
        aria-label="Acquisition runtimes"
        aria-rowcount={rows.length}
        data-testid="catalog-table"
      >
        <div className="ui-catalog-grid ui-catalog-head" role="row">
          <span role="columnheader">Source</span>
          <span role="columnheader">Runtime</span>
          <span role="columnheader">Capabilities</span>
          <span role="columnheader">Coverage</span>
          <span role="columnheader">Health</span>
          <span role="columnheader">Version</span>
          <span role="columnheader">Last run</span>
          <span role="columnheader">Success</span>
        </div>
        {rows.map((row) => (
          <CatalogRow key={row.runtimeRef} row={row} />
        ))}
      </div>

      <OtherConnectors connectors={server.connectors} />

      <section className="ui-ops-block" data-testid="catalog-coverage-note">
        <div className="ui-ops-block-head">
          <span className="ui-pane-title">What this catalogue cannot report</span>
          <span className="ui-ops-block-note">{FABRIC_COVERAGE_MISSING.length} named endpoint(s)</span>
        </div>
        <ul className="ui-quar-gap-list">
          {FABRIC_COVERAGE_MISSING.map((endpoint) => (
            <li key={endpoint} className="ui-quar-gap" data-testid="catalog-gap">
              <span className="ui-quar-gap-endpoint">{endpoint.split(" (")[0]}</span>
              <span>{endpoint.includes("(") ? endpoint.slice(endpoint.indexOf("(") + 1, -1) : "No endpoint exposes this."}</span>
            </li>
          ))}
        </ul>
        <p className="ui-ops-empty">
          Health, last run and success rate are unserved, so they read "not served" on every row. A 0% success rate
          would assert that runs happened and all failed; no run history is served at all, and the two must not be
          confused.
        </p>
      </section>

      {server.connectors.length === 0 ? (
        <EmptyState
          size="sm"
          icon="view-acquisition"
          title="No connector is registered for this tenant"
          description={`The five runtimes above are declared by the acquisition service and exist regardless. What is missing is this tenant's registrations: ${server.answered ? "GET /connectors answered with an empty list" : "the endpoint has not answered"}.`}
          action={
            <Button size="sm" onClick={server.refetch} data-testid="catalog-empty-retry">
              Check again
            </Button>
          }
          testId="catalog-empty"
        />
      ) : null}

      {/* Announces the row count without moving focus (§67). */}
      <span className="ui-sr-only" role="status" aria-live="polite" data-testid="catalog-live-region">
        Acquisition fabric: {rows.map((row) => row.source).join(", ")}
      </span>
    </section>
  );
}