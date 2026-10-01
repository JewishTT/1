import type { ReactNode } from "react";

import type { IconName } from "./ui/Icon";
import { Badge, StatusDot } from "./ui/Badge";
import { Button, IconButton } from "./ui/Button";
import { Popover, Tooltip } from "./ui/Overlay";
import { useWorkspace } from "./workspace/store";
import { useWorkState } from "./workspace/useWorkState";

/**
 * AppShell (§5, §8, §11).
 *
 * Top bar + left rail + primary workspace + right inspector + bottom activity
 * layer. The top bar reports *work state* — which investigation, how much of
 * it, and when it last moved — not the URL breadcrumb (§11). §8 forbids a
 * decorative cockpit, so there is no gauge cluster, no fake telemetry and no
 * ornament: five readouts and the controls that change them.
 *
 * Shell chrome is deliberately thin. The top bar is 40px, the activity layer
 * 30px, and every control meets the 24px minimum target (§67).
 */

/* ── Work state readouts ─────────────────────────────────────────────── */

const NOT_AVAILABLE = "—";

/**
 * A count that the API does not expose. Renders "—" with the reason in a
 * tooltip, rather than 0 (§99: a zero is a claim, and it would be a false one).
 */
function UnavailableCount({ label, why }: { label: string; why: string }) {
  return (
    <Tooltip content={why}>
      <span className="ui-count" data-testid={`topbar-${label}`}>
        <span className="ui-count-value" data-unavailable="true">
          {NOT_AVAILABLE}
        </span>
        <span className="ui-count-label">{label}</span>
      </span>
    </Tooltip>
  );
}

function Count({ label, value }: { label: string; value: number | null }) {
  if (value === null) {
    return (
      <UnavailableCount
        label={label}
        why="The control plane exposes no per-investigation census for this object type yet."
      />
    );
  }
  return (
    <span className="ui-count" data-testid={`topbar-${label}`}>
      <span className="ui-count-value">{value}</span>
      <span className="ui-count-label">{label}</span>
    </span>
  );
}

function formatTimestamp(iso: string | null): string {
  if (iso === null) return NOT_AVAILABLE;
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toISOString().replace("T", " ").slice(0, 19) + "Z";
}

export function WorkStateBar() {
  const investigationId = useWorkspace((state) => state.investigationId);
  const work = useWorkState(investigationId);
  const selection = useWorkspace((state) => state.selection);

  if (investigationId === null) {
    return (
      <div className="ui-topbar-work">
        <span className="ui-topbar-idle">No investigation selected</span>
      </div>
    );
  }

  return (
    <div className="ui-topbar-work" data-testid="work-state-bar">
      <div className="ui-topbar-investigation">
        <span className="ui-pane-title">Investigation</span>
        {work.loading ? (
          <span className="ui-id">loading…</span>
        ) : (
          <>
            <span className="ui-topbar-name ui-truncate" data-testid="topbar-investigation-name">
              {work.investigationName ?? investigationId}
            </span>
            <StatusDot
              status={work.state}
              label={work.rawState ?? work.state}
              live={work.state === "Running"}
              testId="topbar-status"
            />
          </>
        )}
      </div>

      <div className="ui-topbar-counts">
        <Count label="objects" value={work.entityCount} />
        <Count label="observations" value={work.observationCount} />
        <Count label="findings" value={work.findingCount} />
        <Count label="sources" value={work.sourceCount} />
      </div>

      <div className="ui-topbar-meta">
        <span className="ui-count">
          <span className="ui-count-value ui-mono" data-testid="topbar-last-updated">
            {formatTimestamp(work.lastUpdated)}
          </span>
          <span className="ui-count-label">last updated</span>
        </span>
        {work.throughput !== null ? (
          <span className="ui-count">
            <span className="ui-count-value">{work.throughput.toFixed(1)}</span>
            <span className="ui-count-label">obs/s pipeline</span>
          </span>
        ) : null}
        {work.pipelineObservationCount !== null ? (
          <span className="ui-count">
            <span className="ui-count-value">{work.pipelineObservationCount}</span>
            <span className="ui-count-label">useful obs (pipeline)</span>
          </span>
        ) : null}
      </div>

      {selection ? (
        <Badge tone="gold" role="classification" testId="topbar-selection">
          {selection.kind} {selection.id}
        </Badge>
      ) : (
        <span className="ui-topbar-idle">no selection</span>
      )}
    </div>
  );
}

/* ── Top bar controls ────────────────────────────────────────────────── */

function AppearanceMenu() {
  const density = useWorkspace((state) => state.density);
  const theme = useWorkspace((state) => state.theme);
  const setDensity = useWorkspace((state) => state.setDensity);
  const setTheme = useWorkspace((state) => state.setTheme);

  return (
    <Popover
      label="Appearance"
      trigger={
        <Button size="sm" variant="ghost" icon={theme === "dark" ? "moon" : "sun"}>
          {density}
        </Button>
      }
      testId="appearance-menu"
    >
      <div className="ui-menu">
        <span className="ui-pane-title">Density</span>
        <div className="ui-menu-row" role="group" aria-label="Density">
          {(["compact", "comfortable"] as const).map((option) => (
            <Button
              key={option}
              size="sm"
              variant={density === option ? "primary" : "default"}
              aria-pressed={density === option}
              onClick={() => setDensity(option)}
            >
              {option}
            </Button>
          ))}
        </div>
        <span className="ui-pane-title">Theme</span>
        <div className="ui-menu-row" role="group" aria-label="Theme">
          {(["dark", "light"] as const).map((option) => (
            <Button
              key={option}
              size="sm"
              variant={theme === option ? "primary" : "default"}
              aria-pressed={theme === option}
              onClick={() => setTheme(option)}
            >
              {option}
            </Button>
          ))}
        </div>
      </div>
    </Popover>
  );
}

function PaletteButton() {
  const setOpen = useWorkspace((state) => state.setCommandPaletteOpen);

  return (
    <Tooltip content="Command palette (⌘K)">
      <Button
        size="sm"
        variant="ghost"
        icon="command"
        iconAfter="chevron-down"
        onClick={() => setOpen(true)}
        data-testid="open-palette"
      >
        <kbd className="ui-kbd">⌘K</kbd>
      </Button>
    </Tooltip>
  );
}

/* ── The shell ───────────────────────────────────────────────────────── */

export interface AppShellProps {
  /** The centre workspace: InvestigationWorkspace owns this slot. */
  children: ReactNode;
  /** Bottom activity layer content. */
  activity?: ReactNode;
}

export function AppShell({ children, activity }: AppShellProps) {
  const paneVisibility = useWorkspace((state) => state.paneVisibility);
  const togglePane = useWorkspace((state) => state.togglePane);
  const clearSelection = useWorkspace((state) => state.clearSelection);

  const paneToggleIcon = (pane: "rail" | "inspector" | "activity"): IconName =>
    pane === "rail" ? "panel-left" : pane === "inspector" ? "panel-right" : "panel-bottom";

  const paneToggleLabel = (pane: "rail" | "inspector" | "activity"): string => {
    const state = paneVisibility[pane];
    const name = pane === "rail" ? "left context rail" : pane === "inspector" ? "right inspector" : "activity layer";
    return `${state ? "Hide" : "Show"} ${name}`;
  };

  return (
    <div
      className="ui-shell ui-root"
      data-pane-rail={paneVisibility.rail}
      data-pane-inspector={paneVisibility.inspector}
      data-pane-activity={paneVisibility.activity}
      data-testid="app-shell"
    >
      <header className="ui-topbar" role="banner" data-testid="app-shell-topbar">
        <div className="ui-topbar-brand">
          <span className="ui-brand">COGNITIVE</span>
          <span className="ui-meta">workbench</span>
        </div>

        <WorkStateBar />

        <div className="ui-topbar-controls" role="group" aria-label="Shell controls">
          <PaletteButton />
          <AppearanceMenu />
          <Tooltip content={paneToggleLabel("rail")}>
            <IconButton
              icon={paneToggleIcon("rail")}
              label={paneToggleLabel("rail")}
              size="sm"
              aria-pressed={paneVisibility.rail}
              onClick={() => togglePane("rail")}
              data-testid="toggle-rail"
            />
          </Tooltip>
          <Tooltip content={paneToggleLabel("inspector")}>
            <IconButton
              icon={paneToggleIcon("inspector")}
              label={paneToggleLabel("inspector")}
              size="sm"
              aria-pressed={paneVisibility.inspector}
              onClick={() => togglePane("inspector")}
              data-testid="toggle-inspector"
            />
          </Tooltip>
          <Tooltip content={paneToggleLabel("activity")}>
            <IconButton
              icon={paneToggleIcon("activity")}
              label={paneToggleLabel("activity")}
              size="sm"
              aria-pressed={paneVisibility.activity}
              onClick={() => togglePane("activity")}
              data-testid="toggle-activity"
            />
          </Tooltip>
          <Tooltip content="Clear the global selection (Esc)">
            <IconButton
              icon="close"
              label="Clear selection"
              size="sm"
              onClick={() => clearSelection()}
              data-testid="topbar-clear-selection"
            />
          </Tooltip>
        </div>
      </header>

      <div className="ui-shell-body">
        {children}
      </div>

      {paneVisibility.activity ? (
        <footer className="ui-activity" role="contentinfo" aria-label="Activity layer" data-testid="activity-layer">
          {activity ?? <span className="ui-activity-idle">No activity recorded in this session.</span>}
        </footer>
      ) : null}
    </div>
  );
}