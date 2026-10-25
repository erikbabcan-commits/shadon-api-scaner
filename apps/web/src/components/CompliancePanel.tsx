import { useEffect, useState } from "react";
import { api } from "../lib/api";

export function CompliancePanel({ appId }: { appId: string }) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadCompliance();
  }, [appId]);

  async function loadCompliance() {
    setLoading(true);
    try {
      const res = await api.getAppCompliance(appId);
      setData(res);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }

  function handleDownloadReport() {
    const url = api.getReportHtmlUrl(appId);
    window.open(url, "_blank");
  }

  if (loading) {
    return <div className="text-xs text-slate-400 p-4">Načítavam compliance dáta...</div>;
  }

  if (!data) return null;

  const { scoring, nis2_readiness } = data;

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-6 shadow-sm">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h3 className="text-base font-bold text-white">
            Compliance & Executive Audit Report
          </h3>
          <p className="text-xs text-slate-400 mt-1">
            Automatické posúdenie zhody s európskou smernicou NIS2 a ISO 27001.
          </p>
        </div>
        <button
          onClick={handleDownloadReport}
          className="px-4 py-2 text-xs font-semibold bg-sky-500 hover:bg-sky-400 text-white rounded-lg transition shadow-lg shadow-sky-500/20 flex items-center gap-2 self-start"
        >
          <span>📑</span>
          <span>Stiahnuť Executive Audit Report (PDF)</span>
        </button>
      </div>

      {/* Grade and score row */}
      <div className="flex items-center gap-6 p-4 bg-slate-950/60 rounded-xl border border-slate-800">
        <div
          className="w-16 h-16 rounded-xl flex items-center justify-center text-3xl font-black text-white shadow-md"
          style={{ background: scoring.color }}
        >
          {scoring.grade}
        </div>
        <div className="flex-1">
          <div className="flex justify-between items-center mb-2">
            <span className="text-sm font-bold text-white">
              Bezpečnostný Index: {scoring.score} %
            </span>
            <span className="text-xs text-slate-400">
              {scoring.open_counts.total} otvorených nálezov
            </span>
          </div>
          <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
            <div
              className="h-full rounded-full transition-all"
              style={{
                width: `${scoring.score}%`,
                background: scoring.color,
              }}
            />
          </div>
        </div>
      </div>

      {/* NIS2 checklist */}
      <div className="space-y-3">
        <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
          Oblasti európskej smernice NIS2 (Článok 21)
        </h4>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {nis2_readiness.map((area: any) => (
            <div
              key={area.id}
              className="p-3 bg-slate-950/40 rounded-lg border border-slate-800 flex items-center justify-between"
            >
              <div>
                <div className="text-xs font-medium text-slate-200">{area.name}</div>
                <div className="text-[10px] text-slate-500 mt-0.5">{area.iso_ref}</div>
              </div>
              <span
                className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                  area.status === "COMPLIANT"
                    ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                    : area.status === "WARNING"
                    ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                    : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                }`}
              >
                {area.status}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
