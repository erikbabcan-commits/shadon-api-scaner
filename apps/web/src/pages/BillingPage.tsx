import React, { useEffect, useState } from "react";
import { api } from "../lib/api";

export function BillingPage() {
  const [plans, setPlans] = useState<Record<string, any>>({});
  const [usage, setUsage] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  useEffect(() => {
    loadBilling();
  }, []);

  async function loadBilling() {
    setLoading(true);
    try {
      const [pData, uData] = await Promise.all([
        api.getPlans(),
        api.getUsage().catch(() => null),
      ]);
      setPlans(pData.plans);
      setUsage(uData);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }

  async function handleUpgrade(tier: string) {
    setActionLoading(tier);
    try {
      const res = await api.createCheckoutSession(tier);
      if (res.url) {
        window.location.href = res.url;
      }
    } catch (err: any) {
      alert(err.message || "Nepodarilo sa spustiť platbu.");
    } finally {
      setActionLoading(null);
    }
  }

  async function handlePortal() {
    setActionLoading("portal");
    try {
      const res = await api.createPortalSession();
      if (res.url) {
        window.location.href = res.url;
      }
    } catch (err: any) {
      alert(err.message || "Nepodarilo sa otvoriť správu predplatného.");
    } finally {
      setActionLoading(null);
    }
  }

  const currentTier = usage?.plan_tier || "free";

  return (
    <div className="max-w-5xl mx-auto space-y-8 p-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">
            Predplatné a Využitie Kvót
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Flexibilné plány pre bezpečnostný monitoring jednotlivcov, tímov aj agentúr.
          </p>
        </div>
        {usage?.subscription_status === "active" && currentTier !== "free" && (
          <button
            onClick={handlePortal}
            disabled={actionLoading === "portal"}
            className="px-4 py-2 text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-lg transition"
          >
            {actionLoading === "portal" ? "Otváram..." : "Správa platobnej karty / Faktúry"}
          </button>
        )}
      </div>

      {/* Usage statistics cards */}
      {usage && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm">
            <div className="text-xs font-medium text-slate-400 uppercase tracking-wider">
              Aktívny plán
            </div>
            <div className="text-2xl font-bold text-white mt-2 capitalize flex items-center gap-2">
              {usage.plan_name}
              <span className="text-xs px-2 py-0.5 rounded-full bg-sky-500/10 text-sky-400 border border-sky-500/20 font-medium">
                {usage.price_eur} € / mes.
              </span>
            </div>
            <div className="text-xs text-slate-400 mt-1">
              Stav: <span className="text-emerald-400">{usage.subscription_status}</span>
            </div>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm">
            <div className="text-xs font-medium text-slate-400 uppercase tracking-wider">
              Monitorované aplikácie
            </div>
            <div className="text-2xl font-bold text-white mt-2">
              {usage.apps_used} / {usage.apps_limit > 1000 ? "Neobmedzene" : usage.apps_limit}
            </div>
            <div className="w-full bg-slate-800 rounded-full h-1.5 mt-3 overflow-hidden">
              <div
                className="bg-sky-500 h-full rounded-full transition-all"
                style={{
                  width: `${Math.min(100, (usage.apps_used / (usage.apps_limit || 1)) * 100)}%`,
                }}
              />
            </div>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm">
            <div className="text-xs font-medium text-slate-400 uppercase tracking-wider">
              Vykonané skeny tento mesiac
            </div>
            <div className="text-2xl font-bold text-white mt-2">
              {usage.scans_used} / {usage.scans_limit > 1000 ? "Neobmedzene" : usage.scans_limit}
            </div>
            <div className="w-full bg-slate-800 rounded-full h-1.5 mt-3 overflow-hidden">
              <div
                className="bg-purple-500 h-full rounded-full transition-all"
                style={{
                  width: `${Math.min(100, (usage.scans_used / (usage.scans_limit || 1)) * 100)}%`,
                }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Plans pricing grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        {Object.entries(plans).map(([key, p]) => {
          const isCurrent = currentTier === key;
          const isPro = key === "pro";

          return (
            <div
              key={key}
              className={`relative bg-slate-900 border rounded-2xl p-6 flex flex-col justify-between transition-all ${
                isPro
                  ? "border-sky-500 shadow-xl shadow-sky-500/10 ring-1 ring-sky-500"
                  : isCurrent
                  ? "border-emerald-500/50"
                  : "border-slate-800 hover:border-slate-700"
              }`}
            >
              {isPro && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-0.5 rounded-full bg-sky-500 text-white font-semibold text-[10px] tracking-wide uppercase">
                  Najpopulárnejší
                </div>
              )}

              <div>
                <h3 className="text-lg font-bold text-white">{p.name}</h3>
                <div className="mt-3 flex items-baseline gap-1">
                  <span className="text-3xl font-extrabold text-white">{p.price_eur} €</span>
                  <span className="text-xs text-slate-400">/ mesiac</span>
                </div>

                <ul className="mt-6 space-y-3 text-xs text-slate-300">
                  <li className="flex items-center gap-2">
                    <span className="text-sky-400">✓</span>
                    {p.max_apps > 1000 ? "Neobmedzene appiek" : `Max ${p.max_apps} appiek`}
                  </li>
                  <li className="flex items-center gap-2">
                    <span className="text-sky-400">✓</span>
                    {p.max_scans_per_month > 1000
                      ? "Neobmedzené skeny"
                      : `${p.max_scans_per_month} skenov / mes.`}
                  </li>
                  <li className="flex items-center gap-2">
                    <span className="text-sky-400">✓</span>
                    {p.cron_schedule ? `Automatický sken: ${p.cron_schedule}` : "Iba manuálny sken"}
                  </li>
                  <li className="flex items-center gap-2">
                    <span className={p.white_label ? "text-sky-400" : "text-slate-600"}>
                      {p.white_label ? "✓" : "✗"}
                    </span>
                    White-Label PDF Reporty
                  </li>
                </ul>
              </div>

              <div className="mt-8">
                {isCurrent ? (
                  <div className="w-full py-2 text-center text-xs font-semibold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded-lg">
                    Aktuálny plán
                  </div>
                ) : (
                  <button
                    onClick={() => handleUpgrade(key)}
                    disabled={actionLoading === key || key === "free"}
                    className={`w-full py-2.5 px-4 text-xs font-semibold rounded-lg transition ${
                      isPro
                        ? "bg-sky-500 hover:bg-sky-400 text-white shadow-lg shadow-sky-500/20"
                        : "bg-slate-800 hover:bg-slate-700 text-white"
                    } disabled:opacity-50`}
                  >
                    {actionLoading === key
                      ? "Pripravujem..."
                      : key === "free"
                      ? "Základný"
                      : "Aktivovať"}
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
