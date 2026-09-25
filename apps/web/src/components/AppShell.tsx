import { Link, useRouterState } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { useOnline } from "@/lib/useOnline";
import { ToastContainer } from "./Toast";

interface TabItem {
  to: "/" | "/apps" | "/findings" | "/runs" | "/account";
  label: string;
  icon: (active: boolean) => ReactNode;
}

const tabs: TabItem[] = [
  {
    to: "/",
    label: "Prehľad",
    icon: (active) => (
      <svg
        className={`w-5 h-5 transition-transform ${active ? "scale-110" : ""}`}
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={active ? 2 : 1.5}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z"
        />
      </svg>
    ),
  },
  {
    to: "/apps",
    label: "Aplikácie",
    icon: (active) => (
      <svg
        className={`w-5 h-5 transition-transform ${active ? "scale-110" : ""}`}
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={active ? 2 : 1.5}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M5.25 14.25h13.5m-13.5 0a3 3 0 01-3-3m3 3a3 3 0 100 6h13.5a3 3 0 100-6m-16.5-3a3 3 0 013-3h13.5a3 3 0 013 3m-19.5 0a4.5 4.5 0 01.9-2.7L5.75 5.1a2.25 2.25 0 011.8-0.9h8.9a2.25 2.25 0 011.8.9l2.1 3.45a4.5 4.5 0 01.9 2.7"
        />
      </svg>
    ),
  },
  {
    to: "/findings",
    label: "Nálezy",
    icon: (active) => (
      <svg
        className={`w-5 h-5 transition-transform ${active ? "scale-110" : ""}`}
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={active ? 2 : 1.5}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"
        />
      </svg>
    ),
  },
  {
    to: "/runs",
    label: "Behy",
    icon: (active) => (
      <svg
        className={`w-5 h-5 transition-transform ${active ? "scale-110" : ""}`}
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={active ? 2 : 1.5}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.348a1.125 1.125 0 010 1.971l-11.54 6.347a1.125 1.125 0 01-1.667-.985V5.653z"
        />
      </svg>
    ),
  },
  {
    to: "/account",
    label: "Účet",
    icon: (active) => (
      <svg
        className={`w-5 h-5 transition-transform ${active ? "scale-110" : ""}`}
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={active ? 2 : 1.5}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M17.982 18.725A7.488 7.488 0 0012 15.75a7.488 7.488 0 00-5.982 2.975m11.963 0a9 9 0 10-11.963 0m11.963 0A8.966 8.966 0 0112 21a8.966 8.966 0 01-5.982-2.275M15 9.75a3 3 0 11-6 0 3 3 0 016 0z"
        />
      </svg>
    ),
  },
];

export function AppShell({
  children,
  runningScans = 0,
}: {
  children?: ReactNode;
  runningScans?: number;
}) {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const online = useOnline();

  return (
    <div className="app-shell min-h-screen flex flex-col bg-slate-950 text-slate-100 pb-20 md:pb-6">
      <header className="topbar sticky top-0 z-40 flex items-center justify-between px-4 py-3 bg-slate-950/80 backdrop-blur-md border-b border-slate-800/80">
        <div className="flex items-center gap-3">
          <Link to="/" className="flex items-center gap-2 group">
            <div className="w-8 h-8 rounded-lg bg-sky-500/10 border border-sky-500/30 flex items-center justify-center text-sky-400 group-hover:border-sky-400 transition">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
              </svg>
            </div>
            <strong className="text-base font-bold tracking-tight text-white group-hover:text-sky-400 transition">
              Stráž
            </strong>
          </Link>
          <div className="text-xs text-slate-400 border-l border-slate-800 pl-3 hidden sm:block">
            {runningScans > 0 ? (
              <span className="flex items-center gap-1.5 text-sky-400">
                <span className="w-2 h-2 rounded-full bg-sky-400 animate-ping" />
                {runningScans} {runningScans === 1 ? "bežiaci scan" : "bežiace scany"}
              </span>
            ) : (
              <span>Všetky systémy sledované</span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {runningScans > 0 && (
            <span className="sm:hidden flex items-center gap-1 text-xs text-sky-400 px-2 py-0.5 rounded-full bg-sky-500/10 border border-sky-500/20">
              <span className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-pulse" />
              {runningScans}
            </span>
          )}
          <span
            className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full border ${
              online
                ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                : "bg-rose-500/10 text-rose-400 border-rose-500/20"
            }`}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                online ? "bg-emerald-400" : "bg-rose-400"
              }`}
            />
            {online ? "Online" : "Offline"}
          </span>
        </div>
      </header>

      <main className="app-main flex-1 w-full max-w-5xl mx-auto px-4 py-6">
        {children}
      </main>

      <nav
        aria-label="Hlavná navigácia"
        className="tabbar fixed bottom-0 left-0 right-0 z-40 bg-slate-950/90 backdrop-blur-lg border-t border-slate-800/90 flex justify-around py-2 px-1 md:py-2.5 max-w-lg md:max-w-xl mx-auto md:bottom-3 md:rounded-2xl md:border shadow-2xl shadow-black/80"
      >
        {tabs.map((tab) => {
          const active =
            tab.to === "/"
              ? pathname === "/"
              : pathname === tab.to || pathname.startsWith(`${tab.to}/`);
          return (
            <Link
              key={tab.to}
              to={tab.to}
              aria-label={tab.label}
              className={`flex flex-col items-center gap-1 px-3 py-1 rounded-xl text-xs font-medium transition-all ${
                active
                  ? "text-sky-400 font-semibold"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {tab.icon(active)}
              <span className="text-[11px] leading-none">{tab.label}</span>
            </Link>
          );
        })}
      </nav>

      <ToastContainer />
    </div>
  );
}
