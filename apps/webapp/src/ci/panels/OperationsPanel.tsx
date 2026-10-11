import { OperationsWorkspace } from "../../ops/OperationsWorkspace";
import { CiPanelShell } from "./panelParts";

/**
 * Operations panel (US1). Absorbs the existing pipeline-operations surface rather
 * than duplicating it — the department's "Operations" tab IS the platform's fabric
 * health, carried in unchanged. Scope-labelled tenant-wide so an operator never
 * reads a pipeline figure as a statement about the case in hand.
 */
export function OperationsPanel() {
  return (
    <CiPanelShell title="Pipeline operations" scope="tenant-wide" testId="ci-operations-panel">
      <OperationsWorkspace />
    </CiPanelShell>
  );
}
