import { Link, useRouterState } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { useOnline } from "@/lib/useOnline";

const tabs = [
  { to: "/", label: "Prehľad" },
  { to: "/apps", label: "Aplikácie" },
  { to: "/findings", label: "Nálezy" },
  { to: "/runs", label: "Behy" },
  { to: "/account", label: "Účet" },
] as const;

export function AppShell({
  children,
  runningScans = 0,
}: {
  children: ReactNode;
  runningScans?: number;
}) {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const online = useOnline();

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <strong style={{ letterSpacing: "0.04em" }}>Stráž</strong>
          <div style={{ color: "var(--muted)", fontSize: "0.75rem" }}>
            {online ? "online" : "offline"}
            {runningScans > 0 ? ` · ${runningScans} beh` : ""}
          </div>
        </div>
        <span className={`badge ${online ? "badge-ok" : "badge-warn"}`}>
          {online ? "sieť OK" : "bez siete"}
        </span>
      </header>
      <main className="app-main">
        <div style={{ padding: "1rem", maxWidth: 960, margin: "0 auto" }}>{children}</div>
      </main>
      <nav className="tabbar">
        {tabs.map((tab) => {
          const active =
            tab.to === "/"
              ? pathname === "/"
              : pathname === tab.to || pathname.startsWith(`${tab.to}/`);
          return (
            <Link key={tab.to} to={tab.to} className={active ? "active" : ""}>
              {tab.label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
