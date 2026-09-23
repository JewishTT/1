import { useRef } from "react";
import type { ChangeEvent } from "react";

interface GraphStateBarProps {
  disabled: boolean;
  status: string | null;
  onSave: () => void;
  onRestore: () => void;
  onExport: () => void;
  onImportFile: (file: File) => void;
}

/**
 * Analyst-facing controls for the intelligence graph VIEW state: save the
 * current canvas to localStorage, restore the last saved view, and export /
 * import the deterministic JSON document (checksummed, versioned). Every
 * action is routed to the container which owns the live cytoscape core; the
 * bar is disabled while no graph is mounted.
 */
export function GraphStateBar({
  disabled,
  status,
  onSave,
  onRestore,
  onExport,
  onImportFile,
}: GraphStateBarProps) {
  const fileRef = useRef<HTMLInputElement>(null);

  const pickFile = () => fileRef.current?.click();

  const onFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) onImportFile(file);
  };

  return (
    <div className="canvas-toolbar graph-state-bar" data-testid="graph-state-bar">
      <span className="op-label">GRAPH VIEW</span>
      <button
        type="button"
        className="btn btn-sm"
        disabled={disabled}
        onClick={onSave}
        data-testid="graph-view-save"
        title="Persist the current positions/zoom/pan/selection to this browser"
      >
        SAVE VIEW
      </button>
      <button
        type="button"
        className="btn btn-sm"
        disabled={disabled}
        onClick={onRestore}
        data-testid="graph-view-restore"
        title="Re-apply the last saved view (refused if the graph topology changed)"
      >
        RESTORE
      </button>
      <button
        type="button"
        className="btn btn-sm"
        disabled={disabled}
        onClick={onExport}
        data-testid="graph-view-export"
        title="Download this view as a deterministic JSON document"
      >
        EXPORT JSON
      </button>
      <button
        type="button"
        className="btn btn-sm"
        disabled={disabled}
        onClick={pickFile}
        data-testid="graph-view-import"
        title="Load a previously exported view JSON document"
      >
        IMPORT JSON
      </button>
      <input
        ref={fileRef}
        type="file"
        accept=".json,application/json"
        hidden
        onChange={onFileChange}
        aria-label="import graph view json"
        data-testid="graph-view-import-input"
      />
      {status ? (
        <span className="status-chip" data-testid="graph-state-status">
          {status}
        </span>
      ) : null}
    </div>
  );
}