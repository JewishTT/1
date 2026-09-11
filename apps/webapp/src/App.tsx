import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { SearchContainer } from "./containers/SearchContainer";
import { EntityViewContainer } from "./containers/EntityViewContainer";
import { FindingViewContainer } from "./containers/FindingViewContainer";
import { InvestigationContainer } from "./containers/InvestigationContainer";
import { OpsContainer } from "./containers/OpsContainer";
import { ConnectorsContainer } from "./containers/ConnectorsContainer";
import { QuarantineContainer } from "./containers/QuarantineContainer";
import { ScienceContainer } from "./containers/ScienceContainer";
import { HypothesisContainer } from "./containers/HypothesisContainer";
import { ExperimentContainer } from "./containers/ExperimentContainer";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Navigate to="/search" replace />} />
        <Route path="search" element={<SearchContainer />} />
        <Route path="investigations/:id" element={<InvestigationContainer />} />
        <Route path="entities/:id" element={<EntityViewContainer />} />
        <Route path="findings/:id" element={<FindingViewContainer />} />
        <Route path="connectors" element={<ConnectorsContainer />} />
        <Route path="quarantine" element={<QuarantineContainer />} />
        <Route path="ops" element={<OpsContainer />} />
        <Route path="science" element={<ScienceContainer />} />
        <Route path="hypotheses" element={<HypothesisContainer />} />
        <Route path="experiments" element={<ExperimentContainer />} />
      </Route>
    </Routes>
  );
}
