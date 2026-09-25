import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { AppShell } from "@/components/AppShell";
import { EmptyState } from "@/components/EmptyState";
import { SkeletonCard, SkeletonMetric } from "@/components/Skeleton";
import { api } from "@/lib/api";
import { formatLatency } from "@/lib/format";

export function OverviewPage() {
  const overview = useQuery({
    queryKey: ["overview"],
    queryFn: api.overview,
    refetchInterval: 15_000,
  });

  const data = overview.data;

  return (
    <AppShell runningScans={data?.running_scans ?? 0}>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 tracking-tight">Prehľad</h1>
          <p className="text-sm text-slate-400 mt-1">
            Globálny stav monitorovanej infraštruktúry a bezpečnostných nálezov
          </p>
        </div>

        {overview.isError && (
          <div className="p-4 rounded-xl border border-rose-500/30 bg-rose-950/20 text-rose-300 text-sm">
            {(overview.error as Error).message}
          </div>
        )}

        {/* Metrics Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4">
          {overview.isLoading ? (
            <>
              <SkeletonMetric />
              <SkeletonMetric />
              <SkeletonMetric />
              <SkeletonMetric />
            </>
          ) : (
            <>
              <div className="rounded-2xl border border-rose-900/40 bg-linear-to-br from-rose-950/40 to-slate-900/60 p-4 space-y-1 shadow-sm">
                <div className="text-xs font-semibold uppercase tracking-wider text-rose-400">
                  Critical
                </div>
                <div className="text-2xl sm:text-3xl font-extrabold text-slate-100">
                  {data?.open_by_severity.critical ?? 0}
                </div>
                <div className="text-[11px] text-slate-400">otvorené zraniteľnosti</div>
              </div>

              <div className="rounded-2xl border border-amber-900/40 bg-linear-to-br from-amber-950/40 to-slate-900/60 p-4 space-y-1 shadow-sm">
                <div className="text-xs font-semibold uppercase tracking-wider text-amber-400">
                  High
                </div>
                <div className="text-2xl sm:text-3xl font-extrabold text-slate-100">
                  {data?.open_by_severity.high ?? 0}
                </div>
                <div className="text-[11px] text-slate-400">vysoká závažnosť</div>
              </div>

              <div className="rounded-2xl border border-sky-900/40 bg-linear-to-br from-sky-950/40 to-slate-900/60 p-4 space-y-1 shadow-sm">
                <div className="text-xs font-semibold uppercase tracking-wider text-sky-400">
                  Expirácie SSL
                </div>
                <div className="text-2xl sm:text-3xl font-extrabold text-slate-100">
                  {data?.certs_expiring_soon ?? 0}
                </div>
                <div className="text-[11px] text-slate-400">expirujú do 21 dní</div>
              </div>

              <div className="rounded-2xl border border-emerald-900/40 bg-linear-to-br from-emerald-950/40 to-slate-900/60 p-4 space-y-1 shadow-sm">
                <div className="text-xs font-semibold uppercase tracking-wider text-emerald-400">
                  Bežiace skeny
                </div>
                <div className="text-2xl sm:text-3xl font-extrabold text-slate-100">
                  {data?.running_scans ?? 0}
                </div>
                <div className="text-[11px] text-slate-400">aktívne vo fronte</div>
              </div>
            </>
          )}
        </div>

        {/* Monitored Apps Section */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-200">Aplikácie</h2>
            <Link
              to="/apps"
              className="text-xs text-sky-400 hover:text-sky-300 font-medium transition"
            >
              Všetky aplikácie →
            </Link>
          </div>

          <div className="space-y-3">
            {overview.isLoading ? (
              <>
                <SkeletonCard />
                <SkeletonCard />
              </>
            ) : (data?.apps ?? []).length === 0 ? (
              <EmptyState
                title="Žiadne monitorované aplikácie"
                description="Zatiaľ nemáte pridanú žiadnu aplikáciu. Pridajte svoju prvú službu a spustite kontrolu dostupnosti."
                action={{
                  label: "Pridať aplikáciu",
                  onClick: () => {
                    window.location.href = "/apps";
                  },
                }}
              />
            ) : (
              (data?.apps ?? []).map((app) => (
                <Link
                  key={app.id}
                  to="/apps/$appId"
                  params={{ appId: app.id }}
                  className="block rounded-2xl border border-slate-800 bg-slate-900/40 hover:bg-slate-900/80 p-4 transition shadow-sm hover:border-slate-700/80 group"
                >
                  <div className="flex items-center justify-between gap-4">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <strong className="text-base text-slate-100 group-hover:text-sky-400 transition">
                          {app.name}
                        </strong>
                        <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-300">
                          {app.environment}
                        </span>
                      </div>
                      <div className="text-xs text-slate-400 font-mono">
                        {app.open_findings === 0
                          ? "Žiadne otvorené nálezy"
                          : `${app.open_findings} ${
                              app.open_findings === 1
                                ? "otvorený nález"
                                : app.open_findings < 5
                                  ? "otvorené nálezy"
                                  : "otvorených nálezov"
                            }`}
                      </div>
                    </div>

                    <div className="text-right space-y-1.5">
                      <span
                        className={`inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-0.5 rounded-full border ${
                          app.last_up === true
                            ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                            : app.last_up === false
                              ? "bg-rose-500/10 text-rose-400 border-rose-500/30"
                              : "bg-slate-800 text-slate-400 border-slate-700"
                        }`}
                      >
                        <span
                          className={`w-1.5 h-1.5 rounded-full ${
                            app.last_up === true
                              ? "bg-emerald-400"
                              : app.last_up === false
                                ? "bg-rose-400 animate-ping"
                                : "bg-slate-500"
                          }`}
                        />
                        {app.last_up === true ? "ONLINE" : app.last_up === false ? "DOWN" : "NEZNÁMY"}
                      </span>
                      <div className="text-[11px] font-mono text-slate-400">
                        {formatLatency(app.last_latency_ms)}
                      </div>
                    </div>
                  </div>
                </Link>
              ))
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
