import { useEffect, type ReactNode } from "react";

import { Icon, type IconName } from "./ui/Icon";
import { Badge, StatusDot } from "./ui/Badge";
import { Button, IconButton } from "./ui/Button";
import { Popover, Tooltip } from "./ui/Overlay";
import { TopNav } from "./shell/TopNav";
import { DENSITIES, THEME_NAMES } from "./workspace/types";
import { useWorkspace } from "./workspace/store";
import { useAppearanceAttributes } from "./workspace/useAppearance";
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

  // With nothing selected there is no work state to report, so the strip is left out
  // entirely. It used to render a placeholder here, which stole width from the nav and
  // clipped "Hypotheses" down to "Hypol" — an idle caption is not worth an unreadable
  // navigation. The scope chips on the page already show that nothing is open.
  if (investigationId === null) {
    // Selection is global state (§68), not a child of an open investigation.
    // Keep the shell chrome compact when there is no investigation, but never
    // hide the global selection from the top bar.
    if (!selection) return null;
    return (
      <div className="ui-topbar-work" data-testid="work-state-bar">
        <div className="ui-topbar-investigation">
          <span className="ui-pane-title">Selection</span>
          <Badge tone="gold" role="classification" testId="topbar-selection">
            {selection.kind} {selection.id}
          </Badge>
        </div>
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
          {/* §4.2's three modes, in the canonical order the ⌘K toggle also walks. */}
          {DENSITIES.map((option) => (
            <Button
              key={option}
              size="sm"
              variant={density === option ? "primary" : "default"}
              aria-pressed={density === option}
              onClick={() => setDensity(option)}
              data-testid={`density-${option}`}
            >
              {option}
            </Button>
          ))}
        </div>
        <span className="ui-pane-title">Theme</span>
        <div className="ui-menu-row" role="group" aria-label="Theme">
          {THEME_NAMES.map((option) => (
            <Button
              key={option}
              size="sm"
              variant={theme === option ? "primary" : "default"}
              aria-pressed={theme === option}
              onClick={() => setTheme(option)}
              data-testid={`theme-${option}`}
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
  // FR-103: density and theme are DOM attributes, not Zustand-only fields.
  // Mounted here because AppShell is the outermost UI 2.0 surface and every
  // workspace, primitive and mounted view is inside it.
  const { density, theme } = useAppearanceAttributes();

  const paneVisibility = useWorkspace((state) => state.paneVisibility);
  const togglePane = useWorkspace((state) => state.togglePane);
  const setPaneVisibility = useWorkspace((state) => state.setPaneVisibility);
  const clearSelection = useWorkspace((state) => state.clearSelection);

  // Responsive pane state is reconciled, not toggled, so React StrictMode's
  // setup/cleanup replay cannot reopen a mobile drawer. Wide layouts retain the
  // operator's last explicit pane preferences; narrowing the viewport closes
  // panes that would otherwise consume the canvas.
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;

    const tablet = window.matchMedia("(max-width: 1279px)");
    const phone = window.matchMedia("(max-width: 767px)");
    const reconcile = () => {
      const current = useWorkspace.getState().paneVisibility;
      const patch: Partial<typeof current> = {};
      if (tablet.matches && current.rail) patch.rail = false;
      if (phone.matches && current.inspector) patch.inspector = false;
      if (Object.keys(patch).length > 0) setPaneVisibility(patch);
    };

    reconcile();
    tablet.addEventListener("change", reconcile);
    phone.addEventListener("change", reconcile);
    return () => {
      tablet.removeEventListener("change", reconcile);
      phone.removeEventListener("change", reconcile);
    };
  }, [setPaneVisibility]);

  const handlePaneToggle = (pane: "rail" | "inspector" | "activity") => {
    const phone =
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(max-width: 767px)").matches;

    if (phone && (pane === "rail" || pane === "inspector")) {
      const opposite = pane === "rail" ? "inspector" : "rail";
      const current = useWorkspace.getState().paneVisibility;
      if (!current[pane] && current[opposite]) setPaneVisibility({ [opposite]: false });
    }
    togglePane(pane);
  };

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
      data-density={density}
      data-theme={theme}
      data-pane-rail={paneVisibility.rail}
      data-pane-inspector={paneVisibility.inspector}
      data-pane-activity={paneVisibility.activity}
      data-testid="app-shell"
    >
      <header className="ui-topbar" role="banner" data-testid="app-shell-topbar">
        <div className="ui-topbar-main">
          <div className="ui-topbar-brand">
            <span className="ui-brand-mark" aria-hidden="true">
              <Icon name="view-ops" size={16} />
            </span>
            <span className="ui-brand">COGNITIVE</span>
            <span className="ui-meta">FIELD SYSTEMS</span>
          </div>

          <div className="ui-topbar-controls" role="group" aria-label="Shell controls">
          <PaletteButton />
          <AppearanceMenu />
          <Tooltip content={paneToggleLabel("rail")}>
            <IconButton
              icon={paneToggleIcon("rail")}
              label={paneToggleLabel("rail")}
              size="sm"
              aria-pressed={paneVisibility.rail}
              onClick={() => handlePaneToggle("rail")}
              data-testid="toggle-rail"
            />
          </Tooltip>
          <Tooltip content={paneToggleLabel("inspector")}>
            <IconButton
              icon={paneToggleIcon("inspector")}
              label={paneToggleLabel("inspector")}
              size="sm"
              aria-pressed={paneVisibility.inspector}
              onClick={() => handlePaneToggle("inspector")}
              data-testid="toggle-inspector"
            />
          </Tooltip>
          <Tooltip content={paneToggleLabel("activity")}>
            <IconButton
              icon={paneToggleIcon("activity")}
              label={paneToggleLabel("activity")}
              size="sm"
              aria-pressed={paneVisibility.activity}
              onClick={() => handlePaneToggle("activity")}
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
        </div>

        <div className="ui-topbar-navigation">
          <div className="ui-topbar-nav-label">
            <span className="ui-nav-status-mark" aria-hidden="true" />
            <span>OPERATIONS</span>
          </div>
          <TopNav />
          <div className="ui-topbar-nav-end" aria-hidden="true">SYS / 01</div>
        </div>

        <div className="ui-topbar-state">
          <WorkStateBar />
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