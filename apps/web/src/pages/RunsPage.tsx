import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/AppShell";
import { api } from "@/lib/api";

export function RunsPage() {
  const runs = useQuery({
    queryKey: ["runs"],
    queryFn: () => api.runs(),
    refetchInterval: 5_000,
  });

  return (
    <AppShell>
      <h2 style={{ marginTop: 0 }}>Behy</h2>
      <div style={{ display: "grid", gap: "0.75rem" }}>
        {(runs.data ?? []).map((r) => (
          <div key={r.id} className="card">
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <strong>{r.profile}</strong>
              <span
                className={`badge ${
                  r.status === "done"
                    ? "badge-ok"
                    : r.status === "failed"
                      ? "badge-down"
                      : "badge-warn"
                }`}
              >
                {r.status}
              </span>
            </div>
            <div style={{ color: "var(--muted)", fontSize: "0.8rem", marginTop: 4 }}>
              app {r.app_id.slice(0, 8)} · {new Date(r.created_at).toLocaleString()}
            </div>
            {r.error && (
              <div style={{ color: "var(--danger)", fontSize: "0.8rem", marginTop: 6 }}>
                {r.error}
              </div>
            )}
          </div>
        ))}
        {!runs.isLoading && (runs.data?.length ?? 0) === 0 && (
          <div className="card" style={{ color: "var(--muted)" }}>
            Zatiaľ žiadne behy.
          </div>
        )}
      </div>
    </AppShell>
  );
}
