/**
 * Compact command-centre workspace selector.
 *
 * The active workspace stays visible in the command bar. The full route index is
 * searchable and grouped by operational domain, but only occupies the viewport
 * while the analyst is changing context.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useInRouterContext, useLocation } from "react-router-dom";

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
  onNavigate,
}: {
  item: NavItem;
  pathname: string;
  search: string;
  onNavigate: () => void;
}) {
  const active = isNavItemActive(pathname, item, search);
  return (
    <Link
      to={item.to}
      className="ui-primary-nav-link"
      data-active={active}
      aria-current={active ? "page" : undefined}
      title={item.label}
      onClick={onNavigate}
      data-testid={`nav-destination-${item.label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`}
    >
      <span className="ui-primary-nav-link-icon" aria-hidden="true">
        <Icon name={item.icon} size={15} />
      </span>
      <span className="ui-primary-nav-link-label">{item.label}</span>
      {active ? <span className="ui-primary-nav-current" aria-hidden="true" /> : null}
    </Link>
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
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);
  const normalizedQuery = query.trim().toLowerCase();

  const groups = useMemo(() => NAV_MODULES.map((module) => {
    const moduleMatches = !normalizedQuery
      || module.label.toLowerCase().includes(normalizedQuery)
      || module.short.toLowerCase().includes(normalizedQuery)
      || module.key.includes(normalizedQuery);
    const sections = NAV_SECTIONS[module.key]
      .map((section) => ({
        ...section,
        items: moduleMatches || !normalizedQuery
          ? section.items
          : section.items.filter((item) =>
              item.label.toLowerCase().includes(normalizedQuery)
              || item.to.toLowerCase().includes(normalizedQuery)
            ),
      }))
      .filter((section) =>
        section.items.length > 0
        || (normalizedQuery && section.label.toLowerCase().includes(normalizedQuery))
      );
    return { module, sections, visible: moduleMatches || sections.some((section) => section.items.length > 0) };
  }).filter((group) => group.visible), [normalizedQuery]);

  useEffect(() => {
    setOpen(false);
    setQuery("");
  }, [location.pathname, location.search]);

  useEffect(() => {
    if (!open) return;
    searchRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        setQuery("");
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  const closeDeck = () => {
    setOpen(false);
    setQuery("");
  };

  return (
    <div className="ui-primary-nav" data-testid="topnav" data-module={currentModule}>
      <button
        type="button"
        className="ui-nav-deck-trigger"
        data-testid="nav-deck-trigger"
        aria-expanded={open}
        aria-controls="nav-deck"
        onClick={() => setOpen((value) => !value)}
      >
        <span className="ui-nav-trigger-index" aria-hidden="true">
          <Icon name={MODULE_ICONS[currentModule]} size={15} />
          <span>WORKSPACE</span>
        </span>
        <span className="ui-nav-trigger-context">
          <strong>{currentModule.toUpperCase()}</strong>
          <span>{currentTitle}</span>
        </span>
        <Icon name={open ? "chevron-up" : "chevron-down"} size={14} />
      </button>

      {open ? (
        <div className="ui-nav-overlay" data-testid="nav-deck-overlay">
          <button
            type="button"
            className="ui-nav-scrim"
            aria-label="Close workspace navigation"
            onClick={closeDeck}
          />
          <section
            className="ui-nav-deck"
            id="nav-deck"
            role="dialog"
            aria-modal="true"
            aria-label="Workspace navigation"
            data-testid="nav-deck"
          >
            <header className="ui-nav-deck-head">
              <div>
                <span className="ui-nav-deck-kicker">COGNITIVE / ROUTE CONTROL</span>
                <h2>Workspace index</h2>
                <p>Choose an operational domain or open a specific work surface.</p>
              </div>
              <button type="button" className="ui-nav-deck-close" onClick={closeDeck} aria-label="Close navigation">
                <Icon name="close" size={16} />
              </button>
            </header>

            <label className="ui-nav-search">
              <Icon name="search" size={15} />
              <input
                ref={searchRef}
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search domains and workspaces…"
                aria-label="Search workspaces"
                data-testid="nav-deck-search"
              />
              <kbd>ESC</kbd>
            </label>

            {groups.length > 0 ? (
              <div className="ui-nav-deck-grid">
                {groups.map(({ module, sections }) => {
                  const active = currentModule === module.key;
                  return (
                    <section
                      className="ui-nav-domain"
                      key={module.key}
                      data-active={active}
                      aria-label={module.label}
                    >
                      <Link
                        to={module.landing}
                        className="ui-nav-domain-head"
                        data-testid={`nav-module-${module.key}`}
                        data-active={active}
                        aria-current={active ? "location" : undefined}
                        onClick={closeDeck}
                      >
                        <span className="ui-nav-domain-icon" aria-hidden="true">
                          <Icon name={MODULE_ICONS[module.key]} size={17} />
                        </span>
                        <span>
                          <small>{module.short}</small>
                          <strong>{module.label}</strong>
                        </span>
                        {active ? <span className="ui-nav-domain-marker" aria-hidden="true" /> : null}
                      </Link>

                      <div className="ui-nav-domain-sections">
                        {sections.map((section, index) => (
                          <section className="ui-primary-nav-section" key={section.label}>
                            <h3 className="ui-primary-nav-section-heading">
                              <span>{String(index + 1).padStart(2, "0")}</span>
                              {section.label}
                            </h3>
                            <nav
                              className="ui-primary-nav-section-items"
                              aria-label={`${module.key} workspaces`}
                            >
                              {section.items.map((item) => (
                                <DestinationLink
                                  key={item.to}
                                  item={item}
                                  pathname={location.pathname}
                                  search={location.search}
                                  onNavigate={closeDeck}
                                />
                              ))}
                            </nav>
                          </section>
                        ))}
                      </div>
                    </section>
                  );
                })}
              </div>
            ) : (
              <p className="ui-nav-empty" role="status">No workspaces match “{query}”.</p>
            )}

            <footer className="ui-nav-deck-foot">
              <span>ROUTE INDEX / {groups.reduce((count, group) => count + group.sections.reduce((n, section) => n + section.items.length, 0), 0).toString().padStart(2, "0")} DESTINATIONS</span>
              <span>ESC TO CLOSE</span>
            </footer>
          </section>
        </div>
      ) : null}
    </div>
  );
}
