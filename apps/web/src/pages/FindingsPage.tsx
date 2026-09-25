import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AppShell } from "@/components/AppShell";
import { EmptyState } from "@/components/EmptyState";
import { SkeletonTable } from "@/components/Skeleton";
import { api, type Finding } from "@/lib/api";
import { formatTimeAgo } from "@/lib/format";
import { toast } from "@/lib/toast";

const sevBadge: Record<Finding["severity"], string> = {
  critical: "bg-rose-500/10 text-rose-400 border-rose-500/30",
  high: "bg-orange-500/10 text-orange-400 border-orange-500/30",
  medium: "bg-amber-500/10 text-amber-400 border-amber-500/30",
  low: "bg-sky-500/10 text-sky-400 border-sky-500/30",
  info: "bg-slate-800 text-slate-300 border-slate-700",
};

export function FindingsPage() {
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>("open");

  const findings = useQuery({
    queryKey: ["findings", statusFilter],
    queryFn: () => api.findings({ status: statusFilter || undefined }),
    refetchInterval: 20_000,
  });

  const update = useMutation({
    mutationFn: ({ id, status }: { id: string; status: Finding["status"] }) =>
      api.updateFinding(id, status),
    onSuccess: (_, variables) => {
      toast.success(
        variables.status === "accepted"
          ? "Nález bol označený ako akceptované riziko"
          : "Nález bol označený ako opravený",
      );
      qc.invalidateQueries({ queryKey: ["findings"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
    },
    onError: (err: Error) => {
      toast.error(err.message || "Nepodarilo sa aktualizovať nález");
    },
  });

  return (
    <AppShell>
      <div className="space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-slate-100 tracking-tight">Bezpečnostné nálezy</h1>
            <p className="text-sm text-slate-400 mt-1">
              Detegované zraniteľnosti, slabiny a bezpečnostné upozornenia
            </p>
          </div>

          {/* Filter Pills */}
          <div className="flex items-center gap-1.5 p-1 rounded-xl bg-slate-900 border border-slate-800 self-start sm:self-auto">
            {[
              { id: "open", label: "Otvorené" },
              { id: "accepted", label: "Akceptované" },
              { id: "fixed", label: "Opravené" },
              { id: "", label: "Všetky" },
            ].map((f) => (
              <button
                key={f.id}
                onClick={() => setStatusFilter(f.id)}
                className={`px-3 py-1.5 text-xs font-medium rounded-lg transition ${
                  statusFilter === f.id
                    ? "bg-slate-800 text-sky-400 font-semibold shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {/* Findings List */}
        <div className="space-y-3">
          {findings.isLoading ? (
            <SkeletonTable rows={4} />
          ) : (findings.data ?? []).length === 0 ? (
            <EmptyState
              title="Žiadne nálezy"
              description={
                statusFilter === "open"
                  ? "Všetko je v poriadku! Neboli nájdené žiadne otvorené zraniteľnosti."
                  : "Pre zvolený filter sa nenašli žiadne záznamy."
              }
            />
          ) : (
            (findings.data ?? []).map((f) => (
              <div
                key={f.id}
                className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4 sm:p-5 space-y-3 transition hover:border-slate-700/80"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <span
                      className={`text-xs uppercase font-mono font-bold px-2.5 py-0.5 rounded-full border ${sevBadge[f.severity]}`}
                    >
                      {f.severity}
                    </span>
                    <span className="text-xs text-slate-400 font-mono">
                      zdroj: {f.source}
                    </span>
                  </div>

                  <span className="text-[11px] text-slate-500 shrink-0">
                    zistené {formatTimeAgo(f.last_seen_at)}
                  </span>
                </div>

                <div>
                  <h3 className="text-base font-semibold text-slate-100">{f.title}</h3>
                  {f.detail && (
                    <pre className="mt-2 p-3 rounded-xl bg-slate-950/80 border border-slate-800 text-xs text-slate-300 font-mono whitespace-pre-wrap break-all max-h-48 overflow-y-auto">
                      {f.detail}
                    </pre>
                  )}
                </div>

                {f.status === "open" && (
                  <div className="flex gap-2 pt-1 border-t border-slate-800/60 justify-end">
                    <button
                      disabled={update.isPending}
                      onClick={() => update.mutate({ id: f.id, status: "accepted" })}
                      className="px-3 py-1.5 text-xs font-medium rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700/50 transition disabled:opacity-50"
                    >
                      Akceptovať riziko
                    </button>
                    <button
                      disabled={update.isPending}
                      onClick={() => update.mutate({ id: f.id, status: "fixed" })}
                      className="px-3.5 py-1.5 text-xs font-medium rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white shadow-sm transition disabled:opacity-50"
                    >
                      Označiť ako opravené
                    </button>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </AppShell>
  );
}
