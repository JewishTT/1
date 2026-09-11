import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useEffect } from "react";

const navItems = [
  { to: "/search", label: "Search", icon: "🔍" },
  { to: "/investigations/0", label: "Investigations", icon: "📁" },
  { to: "/connectors", label: "Connectors", icon: "🔌" },
  { to: "/quarantine", label: "Quarantine", icon: "🗄️" },
  { to: "/ops", label: "Operations", icon: "⚙️" },
  { to: "/science", label: "Science", icon: "🧪" },
  { to: "/hypotheses", label: "Hypotheses", icon: "🧬" },
  { to: "/experiments", label: "Experiments", icon: "🔬" },
];

/**
 * Top-level workbench layout: a persistent sidebar + header + central
 * content area. Pages render inside <Outlet /> so navigation state and
 * the dark workbench aesthetic remain consistent across routes.
 */
export function Layout() {
  const location = useLocation();

  // Scroll restoration on navigation
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [location.pathname]);

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <h1 style={{ fontSize: "1.125rem", fontWeight: 700, color: "var(--c-text)" }}>
            COGNITIVE
          </h1>
          <span style={{ fontSize: "0.65rem", color: "var(--c-text-dim)" }}>OSINT Workbench</span>
        </div>

        <nav className="nav" aria-label="main navigation">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
            >
              <span className="nav-icon">{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
      </aside>

      <header className="header">
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <span style={{ fontSize: "1.25rem" }}>🕵️</span>
          <span style={{ color: "var(--c-text-2)", fontSize: "0.875rem" }}>
            {location.pathname === "/ops"
              ? "Operations"
              : location.pathname === "/science"
                ? "Scientific review"
                : location.pathname === "/hypotheses"
                  ? "Hypotheses & gain planning"
                  : location.pathname === "/experiments"
                    ? "Reproducible experiments"
                    : location.pathname === "/connectors"
                      ? "Connectors & Recon Plans"
                      : location.pathname === "/quarantine"
                        ? "Quarantine (DLQ)"
                        : location.pathname.startsWith("/search")
                          ? "Evidence-backed Search"
                          : location.pathname.startsWith("/investigations")
                            ? "Investigation"
                            : location.pathname.startsWith("/entities")
                              ? "Entity"
                              : location.pathname.startsWith("/findings")
                                ? "Finding"
                                : "Dashboard"}
          </span>
        </div>
      </header>

      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
