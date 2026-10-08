import { Navigate, Route, Routes } from "react-router-dom";
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

/**
 * The shell is mounted here, at the root, rather than per-route.
 *
 * It used to be `components/Layout` - the legacy sidebar shell - wrapping every
 * route including `/investigations/:id`, which mounts the UI 2.0 workspace *with its
 * own* AppShell inside. Two shells were therefore live at once, the legacy one on
 * top, which is why the navigation looked untouched no matter how complete the UI 2.0
 * work became: the new navbar existed but was never the one anybody saw.
 *
 * `AppShell` renders `children` in `ui-shell-body`, so every legacy container still
 * mounts unchanged - only the chrome around them is now one shell.
 */
export function App() {
  return (
    <Routes>
      <Route
        path="/"
        element={
          <AppShell>
            <Routes>
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
              <Route
                path="investigations/graph"
                element={<InvestigationGraphRoute />}
              />
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
              <Route path="ops/graph" element={<SpecOpsContainer />} />
              <Route path="science" element={<ScienceContainer />} />
              <Route path="hypotheses" element={<HypothesisContainer />} />
              <Route path="experiments" element={<ExperimentContainer />} />
            </Routes>
          </AppShell>
        }
      />
    </Routes>
  );
}
