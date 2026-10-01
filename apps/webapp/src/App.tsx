import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { InvestigationWorkspaceRoute } from "./Workbench";
import { SearchContainer } from "./containers/SearchContainer";
import { EntityViewContainer } from "./containers/EntityViewContainer";
import { FindingViewContainer } from "./containers/FindingViewContainer";
import { InvestigationContainer } from "./containers/InvestigationContainer";
import { InvestigationListContainer } from "./containers/InvestigationListContainer";
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

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Navigate to="/intel" replace />} />
        <Route path="intel" element={<IntelligenceContainer />} />
        <Route path="economic" element={<EconomicsContainer />} />
        <Route path="network" element={<NetworkAnalysisContainer />} />
        <Route path="search" element={<SearchContainer />} />
        <Route path="investigations" element={<InvestigationListContainer />} />
        {/* UI 2.0: the legacy InvestigationContainer (with its review panel and
            edit form) stays reachable at its own path, and the investigation
            route itself now mounts the shell + workspace, with the legacy
            InvestigationPage injected into the Overview canvas (§97, §10). */}
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
      </Route>
    </Routes>
  );
}
