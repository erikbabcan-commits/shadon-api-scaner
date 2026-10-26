import { useEffect, useState } from "react";
import { api, getActiveOrgId, type AuditLogItem, type Organization } from "../lib/api";

const CATEGORIES = [
  { label: "Všetky", filter: "" },
  { label: "Aplikácie", filter: "app." },
  { label: "Ciele & Domény", filter: "target." },
  { label: "Skeny & CI/CD", filter: "scan" },
  { label: "Tím & Prístupy", filter: "member." },
  { label: "API Kľúče", filter: "apikey." },
  { label: "Integrácie", filter: "channel." },
];

function getActionBadgeClass(action: string): string {
  if (action.includes("create") || action.includes("invite")) {
    return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
  }
  if (action.includes("delete") || action.includes("revoke") || action.includes("remove")) {
    return "bg-rose-500/10 text-rose-400 border-rose-500/20";
  }
  if (action.includes("verify") || action.includes("scan") || action.includes("ci")) {
    return "bg-sky-500/10 text-sky-400 border-sky-500/20";
  }
  if (action.includes("role") || action.includes("update") || action.includes("checkout")) {
    return "bg-amber-500/10 text-amber-400 border-amber-500/20";
  }
  return "bg-slate-800 text-slate-300 border-slate-700";
}

export function AuditLogPage() {
  const [currentOrg, setCurrentOrg] = useState<Organization | null>(null);
  const [events, setEvents] = useState<AuditLogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [selectedCategory, setSelectedCategory] = useState("");
  const [selectedEvent, setSelectedEvent] = useState<AuditLogItem | null>(null);
  const [copiedIp, setCopiedIp] = useState<string | null>(null);

  const loadLogs = async (orgId: string) => {
    try {
      setLoading(true);
      const res = await api.getAuditLogs(orgId, { limit: 100 });
      setEvents(res.items);
      setTotal(res.total);
    } catch {
      setEvents([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    async function init() {
      try {
        const orgs = await api.getOrgs();
        if (orgs.length > 0) {
          const active = orgs.find((org) => org.id === getActiveOrgId()) ?? orgs[0];
          setCurrentOrg(active);
          if (active.role === "owner" || active.role === "admin") await loadLogs(active.id);
        }
      } catch {
        /* ignore */
      }
    }
    init();
  }, []);

  const handleCopyIp = (ip: string) => {
    navigator.clipboard.writeText(ip);
    setCopiedIp(ip);
    setTimeout(() => setCopiedIp(null), 2000);
  };

  const handleExportCsv = () => {
    if (!currentOrg) return;
    const url = api.exportAuditCsvUrl(currentOrg.id);
    window.open(url, "_blank");
  };

  const filteredEvents = selectedCategory
    ? events.filter((e) => e.action.includes(selectedCategory))
    : events;

  const isViewer = currentOrg?.role !== "owner" && currentOrg?.role !== "admin";

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2.5">
            <svg className="w-6 h-6 text-sky-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            Auditný Záznam Operácií (Audit Log)
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Nemenná forenzná auditná stopa pre inštitucionálne audity, Fortune 500 a M&A due diligence.
          </p>
        </div>

        <button
          onClick={handleExportCsv}
          disabled={isViewer || loading}
          className="flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg text-xs font-medium border border-slate-700 transition disabled:opacity-50"
        >
          <svg className="w-4 h-4 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          Exportovať CSV
        </button>
      </div>

      {/* Viewer alert */}
      {isViewer && (
        <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl text-xs text-slate-400">
          Ako pozorovateľ (Viewer) máte prístup k auditnému záznamu obmedzený. Pre zobrazenie kompletného auditu požiadajte správcu o vyššiu rolu.
        </div>
      )}

      {/* Category filter pills */}
      <div className="flex flex-wrap gap-2">
        {CATEGORIES.map((cat) => (
          <button
            key={cat.label}
            onClick={() => setSelectedCategory(cat.filter)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition border ${
              selectedCategory === cat.filter
                ? "bg-sky-600 text-white border-sky-500 shadow-sm"
                : "bg-slate-900 text-slate-400 border-slate-800 hover:text-white hover:border-slate-700"
            }`}
          >
            {cat.label}
          </button>
        ))}
      </div>

      {/* Audit Log Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-white">
            Záznam udalostí ({filteredEvents.length} z {total})
          </h2>
          <span className="text-xs text-emerald-400 flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            Ochrana nemennosti aktívna
          </span>
        </div>

        {loading ? (
          <div className="p-10 text-center text-sm text-slate-500">Načítavam auditný záznam...</div>
        ) : filteredEvents.length === 0 ? (
          <div className="p-10 text-center text-sm text-slate-500">
            Pre vybrané filtre neboli nájdené žiadne auditné udalosti.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="bg-slate-950/60 text-slate-400 uppercase tracking-wider font-semibold border-b border-slate-800">
                <tr>
                  <th className="px-6 py-3">Čas (UTC)</th>
                  <th className="px-6 py-3">Používateľ / Aktér</th>
                  <th className="px-6 py-3">Akcia</th>
                  <th className="px-6 py-3">Cieľ / Entita</th>
                  <th className="px-6 py-3">IP Adresa</th>
                  <th className="px-6 py-3 text-right">Detaily</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {filteredEvents.map((evt) => (
                  <tr key={evt.id} className="hover:bg-slate-800/40 transition">
                    <td className="px-6 py-3.5 text-slate-400 whitespace-nowrap font-mono text-[11px]">
                      {new Date(evt.created_at).toLocaleString("sk-SK")}
                    </td>
                    <td className="px-6 py-3.5 font-medium text-white max-w-[200px] truncate">
                      {evt.actor_email}
                    </td>
                    <td className="px-6 py-3.5">
                      <span
                        className={`inline-block px-2.5 py-0.5 rounded-full border text-[11px] font-medium font-mono ${getActionBadgeClass(
                          evt.action
                        )}`}
                      >
                        {evt.action}
                      </span>
                    </td>
                    <td className="px-6 py-3.5 text-slate-300">
                      {evt.entity_type && (
                        <span className="text-slate-400 mr-1.5">{evt.entity_type}:</span>
                      )}
                      <span className="font-mono text-[11px]">
                        {evt.entity_id ? `${evt.entity_id.substring(0, 16)}...` : "—"}
                      </span>
                    </td>
                    <td className="px-6 py-3.5 text-slate-400">
                      {evt.ip_address ? (
                        <button
                          onClick={() => handleCopyIp(evt.ip_address!)}
                          className="font-mono text-[11px] hover:text-white transition flex items-center gap-1"
                          title="Kopírovať IP"
                        >
                          {evt.ip_address}
                          {copiedIp === evt.ip_address && (
                            <span className="text-emerald-400 text-[10px]">✓</span>
                          )}
                        </button>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="px-6 py-3.5 text-right">
                      {(evt.detail || evt.details) && (
                        <button
                          onClick={() => setSelectedEvent(evt)}
                          className="text-sky-400 hover:text-sky-300 font-medium transition text-[11px]"
                        >
                          Zobraziť
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Details Modal */}
      {selectedEvent && (
        <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-lg w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-sm font-semibold text-white">Detail auditnej udalosti</h3>
              <button
                onClick={() => setSelectedEvent(null)}
                className="text-slate-400 hover:text-white text-xs"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <span className="text-slate-500 block mb-0.5">Akcia & ID:</span>
                <span className="font-mono text-emerald-400">
                  {selectedEvent.action} ({selectedEvent.id})
                </span>
              </div>
              <div>
                <span className="text-slate-500 block mb-0.5">Používateľský agent (User-Agent):</span>
                <span className="font-mono text-slate-300 break-all">
                  {selectedEvent.user_agent || "Neznámy"}
                </span>
              </div>
              {selectedEvent.detail && (
                <div>
                  <span className="text-slate-500 block mb-0.5">Popis / Zhrnutie:</span>
                  <span className="text-slate-300">{selectedEvent.detail}</span>
                </div>
              )}
              {selectedEvent.details && (
                <div>
                  <span className="text-slate-500 block mb-0.5">Forenzný JSON kontext:</span>
                  <pre className="p-3 bg-slate-950 rounded-lg border border-slate-800 text-slate-300 font-mono text-[11px] overflow-x-auto max-h-48 leading-relaxed">
                    {JSON.stringify(selectedEvent.details, null, 2)}
                  </pre>
                </div>
              )}
            </div>

            <div className="pt-3 border-t border-slate-800 flex justify-end">
              <button
                onClick={() => setSelectedEvent(null)}
                className="px-4 py-1.5 bg-slate-800 hover:bg-slate-700 text-white rounded-lg text-xs font-medium transition"
              >
                Zavrieť
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
