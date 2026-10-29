/**
 * Compact workspace navigation for the UI 2.0 shell.
 *
 * The full route catalogue lives in nav.ts. This component presents it as a
 * lightweight active-workspace trigger and an accessible navigation deck so
 * the graph canvas and work-state controls keep their width.
 */
import { createPortal } from "react-dom";
import { useCallback, useEffect, useRef, useState } from "react";
import { NavLink, useInRouterContext, useLocation } from "react-router-dom";

import { Icon } from "../ui/Icon";
import {
  NAV_MODULES,
  NAV_SECTIONS,
  isNavItemActive,
  resolveModule,
  resolveTitle,
  type ModuleKey,
  type NavItem,
} from "./nav";

function NavEntry({
  item,
  pathname,
  search,
  onNavigate,
}: {
  item: NavItem;
  pathname: string;
  search: string;
  onNavigate: () => void;
}) {
  const active = isNavItemActive(pathname, item, search);
  return (
    <NavLink
      to={item.to}
      className="ui-nav-deck-link"
      data-active={active}
      aria-current={active ? "page" : undefined}
      onClick={onNavigate}
    >
      <span className="ui-nav-deck-link-icon" aria-hidden="true">
        <Icon name={item.icon} size={15} />
      </span>
      <span className="ui-nav-deck-link-label">{item.label}</span>
      {active ? <span className="ui-nav-deck-current">CURRENT</span> : null}
    </NavLink>
  );
}

export function TopNav() {
  const inRouter = useInRouterContext();
  if (!inRouter) return null;
  return <RoutedTopNav />;
}

function RoutedTopNav() {
  const location = useLocation();
  const currentModule = resolveModule(location.pathname);
  const currentTitle = resolveTitle(location.pathname);
  const currentModuleInfo = NAV_MODULES.find((item) => item.key === currentModule) ?? NAV_MODULES[0];
  const [open, setOpen] = useState(false);
  const [selectedModule, setSelectedModule] = useState<ModuleKey>(currentModule);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const sections = NAV_SECTIONS[selectedModule];
  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    if (!open) return;
    const firstDestination = document.querySelector<HTMLElement>(".ui-nav-deck-link");
    firstDestination?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        document.querySelectorAll<HTMLElement>(".ui-nav-deck button:not(:disabled), .ui-nav-deck a[href]"),
      ).filter((element) => element.offsetParent !== null || element === document.activeElement);
      if (!focusable.length) {
        event.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      triggerRef.current?.focus();
    };
  }, [open, close]);

  const portalHost = typeof document !== "undefined"
    ? document.querySelector<HTMLElement>(".ui-root[data-theme]") ?? document.body
    : null;
  const deck =
    open && portalHost
      ? createPortal(
          <div className="ui-nav-deck-layer" data-testid="nav-deck-layer">
            <button
              type="button"
              className="ui-nav-deck-scrim"
              aria-label="Close navigation"
              tabIndex={-1}
              onClick={close}
            />
            <section
              className="ui-nav-deck"
              id="ui-navigation-deck"
              role="dialog"
              aria-modal="true"
              aria-labelledby="ui-nav-deck-title"
              data-testid="nav-deck"
            >
              <header className="ui-nav-deck-header">
                <div>
                  <span className="ui-nav-deck-eyebrow">COGNITIVE / FIELD SYSTEMS</span>
                  <h2 id="ui-nav-deck-title">Navigation deck</h2>
                  <p>Choose an operational domain, then enter a workspace.</p>
                </div>
                <button type="button" className="ui-nav-deck-close" onClick={close}>
                  Close <span aria-hidden="true">×</span>
                </button>
              </header>

              <div className="ui-nav-deck-grid">
                <div className="ui-nav-deck-modules" role="group" aria-label="Operational domains">
                  <span className="ui-nav-deck-section-label">01 / DOMAIN</span>
                  {NAV_MODULES.map((module) => (
                    <button
                      key={module.key}
                      type="button"
                      className="ui-nav-deck-module"
                      data-active={selectedModule === module.key}
                      aria-pressed={selectedModule === module.key}
                      data-testid={`nav-module-${module.key}`}
                      onClick={() => setSelectedModule(module.key)}
                    >
                      <span className="ui-nav-deck-module-code">{module.short}</span>
                      <span className="ui-nav-deck-module-name">{module.label}</span>
                      <span className="ui-nav-deck-module-arrow" aria-hidden="true">↗</span>
                    </button>
                  ))}
                  <div className="ui-nav-deck-scope">
                    <span className="ui-nav-deck-section-label">ACTIVE CONTEXT</span>
                    <strong>{currentModuleInfo.short} / {currentTitle}</strong>
                    <span>Routes are grouped by domain; the current route is marked in the list.</span>
                  </div>
                </div>

                <div className="ui-nav-deck-destinations" data-testid="nav-deck-destinations">
                  <div className="ui-nav-deck-destinations-heading">
                    <span className="ui-nav-deck-section-label">02 / DESTINATIONS</span>
                    <span className="ui-nav-deck-destinations-domain">{NAV_MODULES.find((item) => item.key === selectedModule)?.label}</span>
                  </div>
                  {sections.map((section, index) => (
                    <div className="ui-nav-deck-section" key={section.label}>
                      <div className="ui-nav-deck-section-heading">
                        <span className="ui-nav-deck-section-index">{String(index + 1).padStart(2, "0")}</span>
                        <span>{section.label}</span>
                      </div>
                      <div className="ui-nav-deck-section-items">
                        {section.items.map((item) => (
                          <NavEntry
                            key={item.to}
                            item={item}
                            pathname={location.pathname}
                            search={location.search}
                            onNavigate={close}
                          />
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <footer className="ui-nav-deck-footer">
                <span>FIELD SYSTEMS / ROUTE INDEX</span>
                <span><kbd>ESC</kbd> CLOSE</span>
              </footer>
            </section>
          </div>,
          portalHost,
        )
      : null;

  return (
    <div className="ui-topnav" data-testid="topnav" data-module={currentModule} data-open={open}>
      <button
        ref={triggerRef}
        type="button"
        className="ui-nav-deck-trigger"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls="ui-navigation-deck"
        aria-label={`Open navigation. Current domain: ${currentModuleInfo.label}. Current workspace: ${currentTitle}.`}
        data-testid="nav-deck-trigger"
        onClick={() => {
          if (!open) setSelectedModule(currentModule);
          setOpen((value) => !value);
        }}
      >
        <span className="ui-nav-deck-trigger-mark" aria-hidden="true"><Icon name="view-ops" size={15} /></span>
        <span className="ui-nav-deck-trigger-copy">
          <span className="ui-nav-deck-trigger-code">{currentModuleInfo.short}</span>
          <span className="ui-nav-deck-trigger-separator" aria-hidden="true">/</span>
          <span className="ui-nav-deck-trigger-title">{currentTitle}</span>
        </span>
        <span className="ui-nav-deck-trigger-action">{open ? "CLOSE" : "NAV"} <span aria-hidden="true">{open ? "−" : "+"}</span></span>
      </button>
      {deck}
    </div>
  );
}
