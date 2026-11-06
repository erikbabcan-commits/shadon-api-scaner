import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";

export function CompliancePanel({
  appId,
  hasVerifiedTarget,
}: {
  appId: string;
  hasVerifiedTarget: boolean;
}) {
  const compliance = useQuery({
    queryKey: ["app-compliance", appId],
    queryFn: () => api.getAppCompliance(appId),
    retry: false,
  });

  if (compliance.isPending) {
    return (
      <p role="status" className="text-xs text-slate-400 p-4">
        Načítavam technické podklady...
      </p>
    );
  }

  if (compliance.isError) {
    return (
      <div
        role="alert"
        className="rounded-xl border border-amber-500/30 p-4 text-xs text-amber-200 space-y-3"
      >
        <p>Technické podklady sa nepodarilo načítať. Bezpečnosť ani zhoda neboli posúdené.</p>
        <button type="button" className="underline" onClick={() => void compliance.refetch()}>
          Skúsiť znova
        </button>
      </div>
    );
  }

  const { scoring, nis2_readiness } = compliance.data;

  return (
    <section
      aria-label="Technické podklady pre audit"
      className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-6 shadow-sm"
    >
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h3 className="text-base font-bold text-white">Technické podklady pre audit</h3>
          <p className="text-xs text-slate-400 mt-1">
            Technické pozorovania pre odborné posúdenie. Nepotvrdzujú zhodu s NIS2 ani ISO 27001.
          </p>
        </div>
        <a
          href={api.getReportHtmlUrl(appId)}
          target="_blank"
          rel="noopener noreferrer"
          className="px-4 py-2 text-xs font-semibold bg-sky-500 hover:bg-sky-400 text-white rounded-lg transition flex items-center gap-2 self-start"
        >
          Otvoriť report / tlačiť do PDF
        </a>
      </div>

      <div
        role="note"
        className="p-4 bg-slate-950/60 rounded-xl border border-amber-500/30 space-y-2"
      >
        <p className="text-sm font-bold text-amber-200">Zhoda neposúdená — nedostatok dôkazov</p>
        <p className="text-xs text-slate-300">
          {scoring.open_counts.total} otvorených nálezov. Nulový počet nálezov neznamená bezpečnú
          aplikáciu.
        </p>
        {!hasVerifiedTarget && (
          <p className="text-xs text-amber-200">
            Aplikácia nemá overený target. Najprv overte vlastníctvo cieľa.
          </p>
        )}
        <p className="text-xs text-slate-400">
          Dostupnosť aplikácie ani čiastkové skeny nepokrývajú všetky bezpečnostné kontroly. Úplný
          rozsah a aktuálnosť dôkazov nie sú overené; bezpečnostná známka sa neurčuje.
        </p>
      </div>

      <div className="space-y-3">
        <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
          Orientačné oblasti pre odborné posúdenie
        </h4>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {nis2_readiness.map((area) => (
            <div
              key={area.id}
              className="p-3 bg-slate-950/40 rounded-lg border border-slate-800 space-y-2"
            >
              <div className="text-xs font-medium text-slate-200">{area.name}</div>
              <div className="text-[10px] text-slate-500">{area.iso_ref}</div>
              <p className="text-xs text-slate-300">
                {area.issues_count > 0
                  ? `${area.issues_count} technických pozorovaní; zhoda neposúdená`
                  : "Bez doloženého posúdenia zhody"}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
