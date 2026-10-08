/**
 * The normalised navigation for the UI 2.0 shell.
 *
 * Why this exists: `AppShell` was built with a topbar, three resizable panes, theme
 * and density control - and no navigation at all. The only navigation in the product
 * was `components/Layout.tsx`, the legacy shell, which the router mounted *around*
 * the UI 2.0 workspace. The result was the new shell rendering underneath the old
 * navbar, so the navbar looked untouched no matter how complete the shell became.
 *
 * Three defects of the legacy navbar are fixed here rather than carried over:
 *
 * 1. The brand mark was a literal `?` - a text glyph standing in for a logo, which
 *    §3.3 forbids as iconography and which cannot take a tooltip, a stroke weight
 *    or a focus ring. It is now a drawn `Icon`.
 * 2. The footer printed a hardcoded "NEXUS LINK: ACTIVE" and a hardcoded
 *    "CONTROL-PLANE v0.1". A connection indicator that is not wired to a connection
 *    reports a state that does not exist. This component reports nothing it cannot
 *    observe.
 * 3. Several labels carried a mojibake replacement character (`\uFFFD`) where a
 *    separator belonged, left over from a cp1251 round-trip.
 */

import { NavLink, useInRouterContext, useLocation, useNavigate } from "react-router-dom";
import { useMemo } from "react";

import { Icon } from "../ui/Icon";
import {
  NAV_MODULES,
  NAV_SECTIONS,
  isNavItemActive,
  resolveModule,
  resolveTitle,
  type NavItem,
  type ModuleKey,
} from "./nav";

function ModuleTabs({ module, onSelect }: { module: ModuleKey; onSelect: (m: ModuleKey) => void }) {
  return (
    <div className="ui-nav-modules" role="tablist" aria-label="Global modules" data-testid="topnav-modules">
      {NAV_MODULES.map((m) => (
        <button
          key={m.key}
          type="button"
          role="tab"
          aria-selected={module === m.key}
          className="ui-nav-module"
          data-module={m.key}
          data-active={module === m.key}
          onClick={() => onSelect(m.key)}
        >
          {m.short}
        </button>
      ))}
    </div>
  );
}

function NavEntry({ item, pathname, search }: { item: NavItem; pathname: string; search: string }) {
  const active = isNavItemActive(pathname, item, search);
  return (
    <NavLink
      to={item.to}
      className="ui-nav-link"
      data-active={active}
      aria-current={active ? "page" : undefined}
    >
      <span className="ui-nav-icon" aria-hidden="true">
        <Icon name={item.icon} size={14} />
      </span>
      <span className="ui-nav-label">{item.label}</span>
    </NavLink>
  );
}

/**
 * Rendered inside the shell topbar. Collapsed to a horizontal strip rather than a
 * sidebar because the UI 2.0 shell owns the full viewport for rail / canvas /
 * inspector, and a second full-height column would take width the canvas needs.
 */
/**
 * A shell with no router renders no navigation.
 *
 * `AppShell` is mounted both inside the router and bare - in tests, in stories, and in
 * `WorkbenchCanvas`. Navigation is meaningless without a router, and calling
 * `useLocation` outside one throws, so the shell would be unmountable in exactly those
 * contexts. Rendering nothing is the honest result: there is nowhere to navigate *to*.
 */
export function TopNav() {
  const inRouter = useInRouterContext();
  if (!inRouter) return null;
  return <RoutedTopNav />;
}

function RoutedTopNav() {
  const location = useLocation();
  const navigate = useNavigate();
  const module = resolveModule(location.pathname);
  const sections = useMemo(() => NAV_SECTIONS[module], [module]);

  return (
    <div className="ui-topnav" data-testid="topnav">
      <ModuleTabs
        module={module}
        onSelect={(key) => {
          const target = NAV_MODULES.find((m) => m.key === key);
          if (target) navigate(target.landing);
        }}
      />

      <nav className="ui-topnav-sections" aria-label="Section navigation" data-testid="topnav-sections">
        {sections.map((section) => (
          <div key={section.label} className="ui-topnav-group">
            <span className="ui-topnav-group-label">{section.label}</span>
            <div className="ui-topnav-group-items">
              {section.items.map((item) => (
                <NavEntry key={item.to} item={item} pathname={location.pathname} search={location.search} />
              ))}
            </div>
          </div>
        ))}
      </nav>

      <div className="ui-topnav-trail">
        <span className="ui-meta">{module.toUpperCase()}</span>
        <span className="ui-topnav-sep" aria-hidden="true">
          /
        </span>
        <span className="ui-topnav-title">{resolveTitle(location.pathname)}</span>
      </div>
    </div>
  );
}
