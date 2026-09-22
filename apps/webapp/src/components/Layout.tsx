import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";

type ModuleKey = "osint" | "economic" | "specops";

interface NavSection {
  label: string;
  items: Array<{ to: string; label: string; icon: string }>;
}

const MODULES: Array<{ key: ModuleKey; short: string; label: string }> = [
  { key: "osint", short: "OSINT", label: "Intelligence" },
  { key: "economic", short: "ECON", label: "Economics" },
  { key: "specops", short: "SPEC", label: "SpecOps" },
];

const NAV: Record<ModuleKey, NavSection[]> = {
  osint: [
    {
      label: "Intelligence",
      items: [
        { to: "/intel", label: "Intel Board", icon: "◈" },
        { to: "/search", label: "Search", icon: "⌕" },
      ],
    },
    {
      label: "Investigate",
      items: [
        { to: "/investigations/0", label: "Investigations", icon: "▤" },
        { to: "/intel?entity=ENT-2001", label: "Entities", icon: "◉" },
        { to: "/findings/0", label: "Findings", icon: "♦" },
      ],
    },
    {
      label: "Science",
      items: [
        { to: "/science", label: "Science Console", icon: "◈" },
        { to: "/hypotheses", label: "Hypotheses", icon: "☰" },
        { to: "/experiments", label: "Experiments", icon: "⧉" },
      ],
    },
    {
      label: "Acquisition",
      items: [{ to: "/connectors", label: "Connectors", icon: "⇅" }],
    },
  ],
  economic: [
    {
      label: "Econometriks",
      items: [{ to: "/economic", label: "Intelligence Economy", icon: "§" }],
    },
  ],
  specops: [
    {
      label: "Operations",
      items: [
        { to: "/ops", label: "SpecOps Console", icon: "⚡" },
        { to: "/quarantine", label: "Quarantine / DLQ", icon: "⏻" },
      ],
    },
  ],
};

const TITLES: Array<{ prefix: string; title: string }> = [
  { prefix: "/economic", title: "Intelligence Economy" },
  { prefix: "/ops", title: "SpecOps Console" },
  { prefix: "/quarantine", title: "Quarantine (DLQ)" },
  { prefix: "/intel", title: "OSINT // Intel Board" },
  { prefix: "/science", title: "Scientific review" },
  { prefix: "/hypotheses", title: "Hypotheses & gain planning" },
  { prefix: "/experiments", title: "Reproducible experiments" },
  { prefix: "/connectors", title: "Connectors & Recon Plans" },
  { prefix: "/investigations", title: "Investigation" },
  { prefix: "/entities", title: "Entity" },
  { prefix: "/findings", title: "Finding" },
  { prefix: "/search", title: "Evidence-backed search" },
];

function resolveModule(pathname: string): ModuleKey {
  const segments = pathname.split("/")[1];
  if (segments === "ops" || segments === "quarantine") return "specops";
  if (segments === "economic") return "economic";
  return "osint";
}

function resolveTitle(pathname: string): string {
  for (const t of TITLES) if (pathname.startsWith(t.prefix)) return t.title;
  return "Dashboard";
}

function Clock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    <span className="header-clock" data-testid="header-clock">
      {now.getUTCFullYear()}
      {pad(now.getUTCMonth() + 1)}
      {pad(now.getUTCDate())} {pad(now.getUTCHours())}:{pad(now.getUTCMinutes())}:{pad(now.getUTCSeconds())}Z
    </span>
  );
}

export function Layout() {
  const location = useLocation();
  const [module, setModule] = useState<ModuleKey>(() => resolveModule(location.pathname));

  useEffect(() => {
    setModule(resolveModule(location.pathname));
  }, [location.pathname]);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [location.pathname]);

  const sections = useMemo(() => NAV[module], [module]);

  return (
    <div className="layout" data-module={module} data-testid="nexus-shell">
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="brand-row">
            <span className="brand-mark">◈</span>
            <span className="brand-name">COGNITIVE</span>
          </div>
          <span className="brand-sub">// nexus osint workbench</span>
        </div>

        <div className="module-tabs" role="tablist" aria-label="global modules" data-testid="module-nav">
          {MODULES.map((m) => (
            <button
              key={m.key}
              type="button"
              role="tab"
              aria-selected={module === m.key}
              className="module-tab"
              data-module-tab={m.key}
              data-active={module === m.key}
              onClick={() => setModule(m.key)}
            >
              <span className="mt-dot" aria-hidden="true" />
              {m.short}
            </button>
          ))}
        </div>

        <nav className="nav" aria-label="main navigation" data-testid="section-nav">
          {sections.map((section) => (
            <div key={section.label}>
              <div className="group-label">{section.label}</div>
              {section.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
                >
                  <span className="nav-icon" aria-hidden="true">
                    {item.icon}
                  </span>
                  <span>{item.label}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-foot">
          <span className="sb-status">
            <span className="dot" aria-hidden="true" />
            NEXUS LINK: ACTIVE
          </span>
          <span>CONTROL-PLANE v0.1 · SSE 200-buf</span>
        </div>
      </aside>

      <header className="header">
        <div className="crumb">
          <b>{module.toUpperCase()}</b> / {resolveTitle(location.pathname)}
        </div>
        <div className="header-right">
          <NavLink to="/ops" className="header-link" data-testid="pulse-link">
            ⚡ POOL PULSE
          </NavLink>
          <Clock />
        </div>
      </header>

      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}