import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import { AppShell } from "./AppShell";
import { InvestigationWorkspaceRoute } from "./Workbench";
import { SearchContainer } from "./containers/SearchContainer";
import { EntityViewContainer } from "./containers/EntityViewContainer";
import { FindingViewContainer } from "./containers/FindingViewContainer";
import { InvestigationContainer } from "./containers/InvestigationContainer";
import { InvestigationListContainer } from "./containers/InvestigationListContainer";
import { InvestigationGraphRoute } from "./containers/InvestigationGraphRoute";
import { OpsContainer } from "./containers/OpsContainer";
import { ConnectorsContainer } from "./containers/ConnectorsContainer";
import { QuarantineContainer } from "./containers/QuarantineContainer";
import { ScienceContainer } from "./containers/ScienceContainer";
import { HypothesisContainer } from "./containers/HypothesisContainer";
import { ExperimentContainer } from "./containers/ExperimentContainer";
import { IntelligenceContainer } from "./containers/IntelligenceContainer";
import { EconomicsContainer } from "./containers/EconomicsContainer";
import { NetworkAnalysisContainer } from "./containers/NetworkAnalysisContainer";
import { SpecOpsContainer } from "./containers/SpecOpsContainer";
import { DossierContainer } from "./containers/DossierContainer";

/**
 * The shell is mounted here, at the root, rather than per-route.
 *
 * It used to be `components/Layout` - the legacy sidebar shell - wrapping every
 * route including `/investigations/:id`, which mounts the UI 2.0 workspace *with its
 * own* AppShell inside. Two shells were therefore live at once, the legacy one on
 * top, which is why the navigation looked untouched no matter how complete the UI 2.0
 * work became: the new navbar existed but was never the one anybody saw.
 *
 * `AppShell` renders `children`, so every legacy container still mounts unchanged -
 * only the chrome around them is now one shell.
 *
 * Why a layout route, and why it matters
 * --------------------------------------
 * This used to nest a second `<Routes>` inside a `<Route path="/">` element:
 *
 *     <Routes>
 *       <Route path="/" element={<AppShell><Routes>…</Routes></AppShell>} />
 *     </Routes>
 *
 * React Router v6 does not match `path="/"` at depth, so the parent stopped matching
 * as soon as the URL gained a segment and **every child route stopped rendering**. The
 * symptom was a blank page on every destination except `/`, with nothing in the console:
 * the router did not throw, it simply had no match, and `#root` stayed empty.
 *
 * A descendant `<Routes>` only renders when the parent path has a trailing `*`, and even
 * then the children resolve relative to the matched prefix - which turns every child path
 * into a guess about how much of the URL the splat consumed. The layout route is the
 * supported shape: `AppShell` wraps an `Outlet`, children are declared as its children,
 * and relative paths mean what they look like they mean.
 */
function ShellLayout() {
  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}

export function App() {
  return (
    <Routes>
      <Route element={<ShellLayout />}>
        <Route index element={<Navigate to="/intel" replace />} />
        <Route path="intel" element={<IntelligenceContainer />} />
        <Route path="economic" element={<EconomicsContainer />} />
        <Route path="network" element={<NetworkAnalysisContainer />} />
        <Route path="search" element={<SearchContainer />} />
        <Route path="investigations" element={<InvestigationListContainer />} />
        {/* The graph is scoped to one investigation and lives as a view inside it,
            so "Investigation Graph" resolves to the most recent investigation
            with the graph view selected. Without this the destination had no
            route and the tenant-wide graph was the only one anybody could reach,
            which is how it came to look like the investigation's own. */}
        <Route path="investigations/graph" element={<InvestigationGraphRoute />} />
        {/* UI 2.0: the legacy InvestigationContainer (with its review panel and
            edit form) stays reachable at its own path, and the investigation
            route mounts the workspace, with the legacy InvestigationPage
            injected into the Overview canvas (§97, §10). */}
        <Route path="investigations/:id" element={<InvestigationWorkspaceRoute />} />
        <Route path="investigations/:id/legacy" element={<InvestigationContainer />} />
        <Route path="entities/:id" element={<EntityViewContainer />} />
        <Route path="findings/:id" element={<FindingViewContainer />} />
        <Route path="connectors" element={<ConnectorsContainer />} />
        <Route path="quarantine" element={<QuarantineContainer />} />
        <Route path="ops" element={<OpsContainer />} />
        {/* Tenant-wide graph: every investigation at once. Filed beside the
            investigation-scoped graph because that is the level it belongs to. The old
            /ops/graph path still resolves, so an existing bookmark lands on the graph
            rather than on a redirect that looks like a dead end. */}
        <Route path="tenant-graph" element={<SpecOpsContainer />} />
        <Route path="ops/graph" element={<Navigate to="/tenant-graph" replace />} />
        <Route path="science" element={<ScienceContainer />} />
        <Route path="hypotheses" element={<HypothesisContainer />} />
        <Route path="experiments" element={<ExperimentContainer />} />
        <Route path="dossier" element={<DossierContainer />} />
        {/* Anything unrecognised lands on the board rather than on a blank page: a
            mistyped URL is a mistake, not a reason to render nothing and leave the
            analyst without a way forward. */}
        <Route path="*" element={<Navigate to="/intel" replace />} />
      </Route>
    </Routes>
  );
}
