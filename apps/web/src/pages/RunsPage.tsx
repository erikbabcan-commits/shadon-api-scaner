import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { AppShell } from "@/components/AppShell";
import { EmptyState } from "@/components/EmptyState";
import { SkeletonTable } from "@/components/Skeleton";
import { api } from "@/lib/api";
import { formatDate, formatTimeAgo } from "@/lib/format";

export function RunsPage() {
  const runs = useQuery({
    queryKey: ["runs"],
    queryFn: () => api.runs(),
    refetchInterval: (query) => {
      // Poll faster (every 3s) if any scans are queued or running
      const hasActive = (query.state.data ?? []).some(
        (r) => r.status === "queued" || r.status === "running",
      );
      return hasActive ? 3_000 : 10_000;
    },
  });

  return (
    <AppShell>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 tracking-tight">História scanov</h1>
          <p className="text-sm text-slate-400 mt-1">
            Záznamy o vykonaných a bežiacich bezpečnostných testoch
          </p>
        </div>

        <div className="space-y-3">
          {runs.isLoading ? (
            <SkeletonTable rows={5} />
          ) : (runs.data ?? []).length === 0 ? (
            <EmptyState
              title="Žiadne zaznamenané behy"
              description="Doposiaľ neboli spustené žiadne bezpečnostné testy. Spustite scan priamo z detailu aplikácie."
              action={{
                label: "Prejsť na aplikácie",
                onClick: () => {
                  window.location.href = "/apps";
                },
              }}
            />
          ) : (
            (runs.data ?? []).map((r) => {
              const statusBadge = {
                done: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
                failed: "bg-rose-500/10 text-rose-400 border-rose-500/30",
                running: "bg-sky-500/10 text-sky-400 border-sky-500/30 animate-pulse",
                queued: "bg-amber-500/10 text-amber-400 border-amber-500/30",
              }[r.status];

              return (
                <div
                  key={r.id}
                  className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4 sm:p-5 space-y-2 hover:border-slate-700/80 transition"
                >
                  <div className="flex items-center justify-between gap-4">
                    <div className="flex items-center gap-2.5">
                      <span className="font-semibold text-base text-slate-100 uppercase tracking-wide">
                        {r.profile}
                      </span>
                      <span className="text-xs text-slate-500 font-mono">
                        ID: {r.id.slice(0, 8)}
                      </span>
                    </div>

                    <span
                      className={`text-xs uppercase font-mono font-bold px-2.5 py-0.5 rounded-full border ${statusBadge}`}
                    >
                      {r.status === "running" ? (
                        <span className="flex items-center gap-1.5">
                          <span className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-ping" />
                          Prebieha
                        </span>
                      ) : r.status === "done" ? (
                        "Dokončený"
                      ) : r.status === "failed" ? (
                        "Zlyhal"
                      ) : (
                        "V poradí"
                      )}
                    </span>
                  </div>

                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400">
                    <Link
                      to="/apps/$appId"
                      params={{ appId: r.app_id }}
                      className="text-sky-400 hover:underline"
                    >
                      Aplikácia: {r.app_id.slice(0, 8)}…
                    </Link>
                    <span>Spustené: {formatTimeAgo(r.created_at)}</span>
                    <span className="text-slate-500">({formatDate(r.created_at)})</span>
                  </div>

                  {r.error && (
                    <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-xs text-rose-300 font-mono break-all mt-2">
                      {r.error}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>
    </AppShell>
  );
}
