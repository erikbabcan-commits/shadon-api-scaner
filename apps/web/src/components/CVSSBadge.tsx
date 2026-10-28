import { useState } from "react";
import { toast } from "@/lib/toast";

interface CVSSBadgeProps {
  score?: number | null;
  vector?: string | null;
  size?: "sm" | "md" | "lg";
  interactive?: boolean;
  onVectorChange?: (newVector: string, newScore: number) => void;
}

// CVSS v3.1 Metrics and values
const CVSS_METRICS: Record<
  string,
  {
    name: string;
    options: Record<string, { label: string; desc: string }>;
  }
> = {
  AV: {
    name: "Attack Vector (AV)",
    options: {
      N: { label: "Network", desc: "Zraniteľnosť je zneužiteľná vzdialene cez sieť (najvyššie riziko)" },
      A: { label: "Adjacent", desc: "Vyžaduje prístup k lokálnej/susediacej sieti (napr. LAN, Bluetooth)" },
      L: { label: "Local", desc: "Vyžaduje lokálny prístup alebo shell k systému" },
      P: { label: "Physical", desc: "Vyžaduje fyzický kontakt so zariadením" },
    },
  },
  AC: {
    name: "Attack Complexity (AC)",
    options: {
      L: { label: "Low", desc: "Útok nevyžaduje žiadne špeciálne podmienky ani časovanie" },
      H: { label: "High", desc: "Útok závisí od splnenia neobvyklých podmienok (race condition, tajomstvo)" },
    },
  },
  PR: {
    name: "Privileges Required (PR)",
    options: {
      N: { label: "None", desc: "Útočník nepotrebuje žiadne oprávnenia ani autentifikáciu" },
      L: { label: "Low", desc: "Vyžaduje bežný používateľský účet so základnými právami" },
      H: { label: "High", desc: "Vyžaduje administrátorské alebo privilegované práva" },
    },
  },
  UI: {
    name: "User Interaction (UI)",
    options: {
      N: { label: "None", desc: "Útok prebehne bez akejkoľvek interakcie obete" },
      R: { label: "Required", desc: "Vyžaduje akciu používateľa (napr. kliknutie na phishing odkaz)" },
    },
  },
  S: {
    name: "Scope (S)",
    options: {
      U: { label: "Unchanged", desc: "Dopad je izolovaný len na zraniteľnú komponentu" },
      C: { label: "Changed", desc: "Zraniteľnosť umožňuje prelomenie bezpečnostných hraníc do iných systémov" },
    },
  },
  C: {
    name: "Confidentiality (C)",
    options: {
      N: { label: "None", desc: "Žiadny únik dôverných dát" },
      L: { label: "Low", desc: "Čiastočný únik nekritických informácií" },
      H: { label: "High", desc: "Kompletný únik citlivých dát, databáz alebo tajomstiev" },
    },
  },
  I: {
    name: "Integrity (I)",
    options: {
      N: { label: "None", desc: "Žiadna modifikácia dát ani logiky" },
      L: { label: "Low", desc: "Možnosť obmedzenej modifikácie bez vážneho dopadu" },
      H: { label: "High", desc: "Úplná modifikácia dát, prepísanie konfigurácie alebo kódu" },
    },
  },
  A: {
    name: "Availability (A)",
    options: {
      N: { label: "None", desc: "Dostupnosť systému nie je narušená" },
      L: { label: "Low", desc: "Občasné zníženie výkonu alebo dočasné zlyhanie" },
      H: { label: "High", desc: "Úplný výpadok služby alebo Denial of Service (DoS)" },
    },
  },
};

// Client-side exact CVSS 3.1 calculation fallback
function calculateCvss31Client(metrics: Record<string, string>): { score: number; severity: string } {
  const wAV: Record<string, number> = { N: 0.85, A: 0.62, L: 0.55, P: 0.2 };
  const wAC: Record<string, number> = { L: 0.77, H: 0.44 };
  const wPRu: Record<string, number> = { N: 0.85, L: 0.62, H: 0.27 };
  const wPRc: Record<string, number> = { N: 0.85, L: 0.68, H: 0.5 };
  const wUI: Record<string, number> = { N: 0.85, R: 0.62 };
  const wCIA: Record<string, number> = { N: 0.0, L: 0.22, H: 0.56 };

  const av = wAV[metrics.AV || "N"] ?? 0.85;
  const ac = wAC[metrics.AC || "L"] ?? 0.77;
  const sChanged = (metrics.S || "U") === "C";
  const pr = sChanged ? (wPRc[metrics.PR || "N"] ?? 0.85) : (wPRu[metrics.PR || "N"] ?? 0.85);
  const ui = wUI[metrics.UI || "N"] ?? 0.85;

  const c = wCIA[metrics.C || "N"] ?? 0;
  const i = wCIA[metrics.I || "N"] ?? 0;
  const a = wCIA[metrics.A || "N"] ?? 0;

  const iss = 1.0 - (1.0 - c) * (1.0 - i) * (1.0 - a);
  let impact: number;
  if (sChanged) {
    impact = 7.52 * (iss - 0.029) - 3.25 * Math.pow(iss - 0.02, 15);
  } else {
    impact = 6.42 * iss;
  }

  const exploitability = 8.22 * av * ac * pr * ui;

  let baseScore = 0.0;
  if (impact > 0) {
    const raw = sChanged ? Math.min(1.08 * (impact + exploitability), 10.0) : Math.min(impact + exploitability, 10.0);
    // CVSS 3.1 round up
    const intInput = Math.round(raw * 100000);
    if (intInput % 10000 === 0) {
      baseScore = intInput / 100000.0;
    } else {
      baseScore = (Math.floor(intInput / 10000) + 1) / 10.0;
    }
  }

  let severity = "info";
  if (baseScore >= 9.0) severity = "critical";
  else if (baseScore >= 7.0) severity = "high";
  else if (baseScore >= 4.0) severity = "medium";
  else if (baseScore > 0.0) severity = "low";

  return { score: baseScore, severity };
}

function parseVector(vectorStr?: string | null): Record<string, string> {
  const defaults: Record<string, string> = {
    AV: "N",
    AC: "L",
    PR: "N",
    UI: "N",
    S: "U",
    C: "N",
    I: "N",
    A: "N",
  };
  if (!vectorStr) return defaults;

  const parts = vectorStr.split("/");
  for (const part of parts) {
    const [k, v] = part.split(":");
    if (k && v && defaults[k] !== undefined) {
      defaults[k] = v.toUpperCase();
    }
  }
  return defaults;
}

function buildVector(metrics: Record<string, string>): string {
  return `CVSS:3.1/AV:${metrics.AV}/AC:${metrics.AC}/PR:${metrics.PR}/UI:${metrics.UI}/S:${metrics.S}/C:${metrics.C}/I:${metrics.I}/A:${metrics.A}`;
}

export function CVSSBadge({
  score,
  vector,
  size = "md",
  interactive = true,
  onVectorChange,
}: CVSSBadgeProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [metrics, setMetrics] = useState<Record<string, string>>(() => parseVector(vector));
  const [copied, setCopied] = useState(false);

  // Compute live score if modified
  const currentCalc = calculateCvss31Client(metrics);
  const displayScore = score !== undefined && score !== null ? score : currentCalc.score;
  const currentVector = vector || buildVector(metrics);

  const getSeverityStyle = (s: number) => {
    if (s >= 9.0) return "bg-rose-500/15 text-rose-300 border-rose-500/40 shadow-rose-950/20";
    if (s >= 7.0) return "bg-orange-500/15 text-orange-300 border-orange-500/40 shadow-orange-950/20";
    if (s >= 4.0) return "bg-amber-500/15 text-amber-300 border-amber-500/40 shadow-amber-950/20";
    if (s > 0.0) return "bg-sky-500/15 text-sky-300 border-sky-500/40 shadow-sky-950/20";
    return "bg-slate-800 text-slate-300 border-slate-700";
  };

  const getSeverityLabel = (s: number) => {
    if (s >= 9.0) return "CRITICAL";
    if (s >= 7.0) return "HIGH";
    if (s >= 4.0) return "MEDIUM";
    if (s > 0.0) return "LOW";
    return "NONE";
  };

  const handleCopyVector = async () => {
    try {
      await navigator.clipboard.writeText(currentVector);
      setCopied(true);
      toast.success("CVSS v3.1 vektor bol skopírovaný do schránky");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Nepodarilo sa skopírovať vektor");
    }
  };

  const handleMetricSelect = (metricKey: string, optionKey: string) => {
    const updated = { ...metrics, [metricKey]: optionKey };
    setMetrics(updated);
    const newCalc = calculateCvss31Client(updated);
    const newVec = buildVector(updated);
    if (onVectorChange) {
      onVectorChange(newVec, newCalc.score);
    }
  };

  const sizeClasses = {
    sm: "px-2 py-0.5 text-[11px] gap-1",
    md: "px-2.5 py-1 text-xs gap-1.5",
    lg: "px-3.5 py-1.5 text-sm gap-2",
  };

  return (
    <>
      <button
        type="button"
        disabled={!interactive}
        onClick={() => interactive && setIsOpen(true)}
        className={`inline-flex items-center font-mono font-semibold rounded-lg border transition ${
          sizeClasses[size]
        } ${getSeverityStyle(displayScore)} ${
          interactive ? "cursor-pointer hover:scale-[1.02] active:scale-[0.98]" : "cursor-default"
        }`}
        title="Kliknite pre zobrazenie CVSS v3.1 kalkulátora a metriky"
      >
        <span className="opacity-75 font-sans font-normal text-[10px] uppercase tracking-wider">
          CVSS
        </span>
        <span className="font-bold">{displayScore.toFixed(1)}</span>
        <span className="text-[10px] opacity-90 px-1 py-0.2 rounded bg-black/20">
          {getSeverityLabel(displayScore)}
        </span>
      </button>

      {/* Modal dialog with full CVSS v3.1 breakdown */}
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-xs">
          <div className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl bg-slate-900 border border-slate-800 p-6 shadow-2xl space-y-5">
            {/* Header */}
            <div className="flex items-start justify-between gap-4 border-b border-slate-800 pb-4">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-lg font-bold text-slate-100">
                    CVSS v3.1 Bezpečnostné skóre
                  </h3>
                  <span
                    className={`text-xs uppercase font-mono font-bold px-2.5 py-0.5 rounded-full border ${getSeverityStyle(
                      currentCalc.score
                    )}`}
                  >
                    {currentCalc.score.toFixed(1)} — {getSeverityLabel(currentCalc.score)}
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-1">
                  Štandardizovaný model závažnosti FIRST CVSS v3.1 (Common Vulnerability Scoring System)
                </p>
              </div>

              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Vector String bar */}
            <div className="flex items-center justify-between gap-3 p-3 rounded-xl bg-slate-950 border border-slate-800 font-mono text-xs">
              <span className="text-slate-300 break-all select-all">{buildVector(metrics)}</span>
              <button
                type="button"
                onClick={handleCopyVector}
                className="shrink-0 px-2.5 py-1 text-xs rounded-lg bg-slate-800 hover:bg-slate-700 text-sky-400 border border-slate-700 transition"
              >
                {copied ? "Skopírované!" : "Kopírovať vektor"}
              </button>
            </div>

            {/* 8 Base Metrics Grid */}
            <div className="space-y-4">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Základné metriky (Base Metrics)
              </h4>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {Object.entries(CVSS_METRICS).map(([key, metric]) => {
                  const activeVal = metrics[key] || Object.keys(metric.options)[0];
                  return (
                    <div
                      key={key}
                      className="p-3 rounded-xl bg-slate-950/60 border border-slate-800 space-y-2"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold text-slate-200">{metric.name}</span>
                        <span className="text-[11px] font-mono font-bold text-sky-400">
                          {key}:{activeVal}
                        </span>
                      </div>

                      <div className="flex flex-wrap gap-1.5">
                        {Object.entries(metric.options).map(([optKey, opt]) => {
                          const isSelected = activeVal === optKey;
                          return (
                            <button
                              key={optKey}
                              type="button"
                              onClick={() => handleMetricSelect(key, optKey)}
                              className={`px-2.5 py-1 rounded-lg text-xs font-medium transition ${
                                isSelected
                                  ? "bg-sky-600 text-white shadow-xs font-bold"
                                  : "bg-slate-800/80 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
                              }`}
                              title={opt.desc}
                            >
                              {opt.label} ({optKey})
                            </button>
                          );
                        })}
                      </div>

                      <p className="text-[11px] text-slate-500 italic leading-snug">
                        {metric.options[activeVal]?.desc}
                      </p>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between border-t border-slate-800 pt-4">
              <div className="text-xs text-slate-500">
                Zmena metriky interaktívne prepočítava výsledné skóre v reálnom čase.
              </div>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="px-4 py-2 text-xs font-semibold rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 transition"
              >
                Zavrieť
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
