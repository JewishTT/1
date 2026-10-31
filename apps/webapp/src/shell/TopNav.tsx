/**
 * Persistent field navigation for the UI 2.0 shell.
 *
 * Domain selection and destinations remain visible while the analyst works. The
 * workbench is the primary surface; navigation is an always-available rail, not
 * a modal deck hidden behind a single NAV button.
 */
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

const MODULE_ICONS: Record<ModuleKey, "view-ops" | "view-analysis" | "view-evidence"> = {
  osint: "view-ops",
  economic: "view-analysis",
  specops: "view-evidence",
};

function DestinationLink({
  item,
  pathname,
  search,
}: {
  item: NavItem;
  pathname: string;
  search: string;
}) {
  const active = isNavItemActive(pathname, item, search);
  return (
    <NavLink
      to={item.to}
      className="ui-primary-nav-link"
      data-active={active}
      aria-current={active ? "page" : undefined}
      title={item.label}
      data-testid={`nav-destination-${item.label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`}
    >
      <span className="ui-primary-nav-link-icon" aria-hidden="true">
        <Icon name={item.icon} size={15} />
      </span>
      <span className="ui-primary-nav-link-label">{item.label}</span>
      {active ? <span className="ui-primary-nav-current" aria-hidden="true" /> : null}
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
  const sections = NAV_SECTIONS[currentModule];

  return (
    <aside className="ui-primary-nav" data-testid="topnav" data-module={currentModule}>
      <div className="ui-primary-nav-header">
        <span className="ui-primary-nav-kicker">ROUTE INDEX / 01</span>
        <span className="ui-primary-nav-heading">FIELD DOMAINS</span>
      </div>

      <nav className="ui-primary-nav-modules" aria-label="Operational domains">
        {NAV_MODULES.map((module) => {
          const active = currentModule === module.key;
          return (
            <NavLink
              key={module.key}
              to={module.landing}
              end={module.key === "osint"}
              className="ui-primary-nav-module"
              data-active={active}
              aria-current={active ? "page" : undefined}
              title={module.label}
              data-testid={`nav-module-${module.key}`}
            >
              <span className="ui-primary-nav-module-icon" aria-hidden="true">
                <Icon name={MODULE_ICONS[module.key]} size={16} />
              </span>
              <span className="ui-primary-nav-module-copy">
                <span className="ui-primary-nav-module-code">{module.short}</span>
                <span className="ui-primary-nav-module-name">{module.label}</span>
              </span>
              {active ? <span className="ui-primary-nav-module-marker" aria-hidden="true" /> : null}
            </NavLink>
          );
        })}
      </nav>

      <div className="ui-primary-nav-divider" />

      <nav className="ui-primary-nav-destinations" aria-label={`${currentModule} workspaces`}>
        {sections.map((section, index) => (
          <section className="ui-primary-nav-section" key={section.label}>
            <h2 className="ui-primary-nav-section-heading">
              <span>{String(index + 1).padStart(2, "0")}</span>
              {section.label}
            </h2>
            <div className="ui-primary-nav-section-items">
              {section.items.map((item) => (
                <DestinationLink
                  key={item.to}
                  item={item}
                  pathname={location.pathname}
                  search={location.search}
                />
              ))}
            </div>
          </section>
        ))}
      </nav>

      <footer className="ui-primary-nav-footer">
        <span className="ui-primary-nav-kicker">ACTIVE WORKSPACE</span>
        <strong title={currentTitle}>{currentTitle}</strong>
        <span className="ui-primary-nav-footer-code">{currentModule.toUpperCase()} / ROUTED</span>
      </footer>
    </aside>
  );
}
