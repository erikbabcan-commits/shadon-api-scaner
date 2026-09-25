import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { AppShell } from "@/components/AppShell";
import { EmptyState } from "@/components/EmptyState";
import { SkeletonCard } from "@/components/Skeleton";
import { api } from "@/lib/api";
import { formatLatency } from "@/lib/format";
import { toast } from "@/lib/toast";

export function AppsListPage() {
  const qc = useQueryClient();
  const apps = useQuery({ queryKey: ["apps"], queryFn: () => api.apps() });
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("https://");
  const [environment, setEnvironment] = useState("prod");
  const [isAddingOpen, setIsAddingOpen] = useState(false);

  const create = useMutation({
    mutationFn: () => api.createApp({ name, base_url: baseUrl, environment }),
    onSuccess: async (newApp) => {
      setName("");
      setBaseUrl("https://");
      setIsAddingOpen(false);
      toast.success(`Aplikácia "${newApp.name}" bola úspešne pridaná`);
      await qc.invalidateQueries({ queryKey: ["apps"] });
      await qc.invalidateQueries({ queryKey: ["overview"] });
    },
    onError: (err: Error) => {
      toast.error(err.message || "Nepodarilo sa vytvoriť aplikáciu");
    },
  });

  return (
    <AppShell>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-100 tracking-tight">Aplikácie</h1>
            <p className="text-sm text-slate-400 mt-1">
              Správa monitorovaných systémov, URL adries a bezpečnostných cieľov
            </p>
          </div>
          <button
            onClick={() => setIsAddingOpen(!isAddingOpen)}
            className="px-4 py-2 text-sm font-medium rounded-xl bg-sky-600 hover:bg-sky-500 text-white shadow-sm transition flex items-center gap-1.5"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Pridať appku
          </button>
        </div>

        {/* Add App Collapsible Form */}
        {isAddingOpen && (
          <form
            onSubmit={(e: React.FormEvent) => {
              e.preventDefault();
              create.mutate();
            }}
            className="rounded-2xl border border-sky-500/30 bg-slate-900/60 p-5 space-y-4 shadow-xl shadow-sky-950/20 animate-fade-in"
          >
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <h2 className="text-base font-semibold text-slate-100">Nová aplikácia</h2>
              <button
                type="button"
                onClick={() => setIsAddingOpen(false)}
                className="text-slate-400 hover:text-white p-1"
              >
                ✕
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="space-y-1 sm:col-span-1">
                <label className="text-xs font-medium text-slate-300 block">Názov aplikácie</label>
                <input
                  required
                  placeholder="napr. Klient Web"
                  value={name}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setName(e.target.value)}
                  className="w-full px-3.5 py-2 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500/50"
                />
              </div>

              <div className="space-y-1 sm:col-span-1">
                <label className="text-xs font-medium text-slate-300 block">Base URL</label>
                <input
                  required
                  placeholder="https://app.example.com"
                  value={baseUrl}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setBaseUrl(e.target.value)}
                  className="w-full px-3.5 py-2 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500/50"
                />
              </div>

              <div className="space-y-1 sm:col-span-1">
                <label className="text-xs font-medium text-slate-300 block">Prostredie</label>
                <input
                  placeholder="prod, staging, dev"
                  value={environment}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setEnvironment(e.target.value)}
                  className="w-full px-3.5 py-2 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500/50"
                />
              </div>
            </div>

            {create.error && (
              <div className="p-3 text-xs text-rose-300 bg-rose-500/10 border border-rose-500/20 rounded-xl">
                {(create.error as Error).message}
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setIsAddingOpen(false)}
                className="px-4 py-2 text-xs font-medium rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 transition"
              >
                Zrušiť
              </button>
              <button
                type="submit"
                disabled={create.isPending}
                className="px-5 py-2 text-xs font-medium rounded-xl bg-sky-600 hover:bg-sky-500 text-white transition disabled:opacity-50"
              >
                {create.isPending ? "Ukladám…" : "Vytvoriť aplikáciu"}
              </button>
            </div>
          </form>
        )}

        {/* Apps List */}
        <div className="space-y-3">
          {apps.isLoading ? (
            <>
              <SkeletonCard />
              <SkeletonCard />
              <SkeletonCard />
            </>
          ) : (apps.data ?? []).length === 0 ? (
            <EmptyState
              title="Žiadne aplikácie"
              description="Zatiaľ nemáte vytvorenú žiadnu aplikáciu. Kliknite na tlačidlo vyššie pre pridanie prvej appky."
              action={{
                label: "Pridať appku",
                onClick: () => setIsAddingOpen(true),
              }}
            />
          ) : (
            (apps.data ?? []).map((app) => {
              const verified = app.targets.some((t) => t.status === "verified");
              return (
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
                      <div className="text-xs text-slate-400 font-mono flex items-center gap-2">
                        <span>{app.base_url}</span>
                        {app.last_latency_ms != null && (
                          <span className="text-slate-500">· {formatLatency(app.last_latency_ms)}</span>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <span
                        className={`text-xs px-2.5 py-0.5 rounded-full font-medium border ${
                          verified
                            ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                            : "bg-amber-500/10 text-amber-400 border-amber-500/30"
                        }`}
                      >
                        {verified ? "Verified" : "Pending target"}
                      </span>
                      <svg
                        className="w-4 h-4 text-slate-500 group-hover:text-sky-400 transition transform group-hover:translate-x-0.5"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                    </div>
                  </div>
                </Link>
              );
            })
          )}
        </div>
      </div>
    </AppShell>
  );
}
