import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { AppShell } from "@/components/AppShell";
import { api } from "@/lib/api";

export function OverviewPage() {
  const overview = useQuery({
    queryKey: ["overview"],
    queryFn: api.overview,
    refetchInterval: 15_000,
  });

  const data = overview.data;

  return (
    <AppShell runningScans={data?.running_scans ?? 0}>
      <h2 style={{ marginTop: 0 }}>Prehľad</h2>
      {overview.isError && (
        <div className="card" style={{ color: "var(--danger)" }}>
          {(overview.error as Error).message}
        </div>
      )}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
          gap: "0.75rem",
          marginBottom: "1rem",
        }}
      >
        <div className="card">
          <div style={{ color: "var(--muted)", fontSize: "0.75rem" }}>Critical</div>
          <strong>{data?.open_by_severity.critical ?? 0}</strong>
        </div>
        <div className="card">
          <div style={{ color: "var(--muted)", fontSize: "0.75rem" }}>High</div>
          <strong>{data?.open_by_severity.high ?? 0}</strong>
        </div>
        <div className="card">
          <div style={{ color: "var(--muted)", fontSize: "0.75rem" }}>Cert &lt; 21d</div>
          <strong>{data?.certs_expiring_soon ?? 0}</strong>
        </div>
        <div className="card">
          <div style={{ color: "var(--muted)", fontSize: "0.75rem" }}>Bežiace skeny</div>
          <strong>{data?.running_scans ?? 0}</strong>
        </div>
      </div>

      <div style={{ display: "grid", gap: "0.75rem" }}>
        {(data?.apps ?? []).map((app) => (
          <Link
            key={app.id}
            to="/apps/$appId"
            params={{ appId: app.id }}
            style={{ textDecoration: "none", color: "inherit" }}
          >
            <div
              className="card"
              style={{ display: "flex", justifyContent: "space-between", gap: "1rem" }}
            >
              <div>
                <strong>{app.name}</strong>
                <div style={{ color: "var(--muted)", fontSize: "0.8rem" }}>{app.environment}</div>
              </div>
              <div style={{ textAlign: "right" }}>
                <span
                  className={`badge ${
                    app.last_up === true
                      ? "badge-ok"
                      : app.last_up === false
                        ? "badge-down"
                        : "badge-warn"
                  }`}
                >
                  {app.last_up === true ? "UP" : app.last_up === false ? "DOWN" : "—"}
                </span>
                <div style={{ color: "var(--muted)", fontSize: "0.75rem", marginTop: 4 }}>
                  {app.last_latency_ms != null ? `${app.last_latency_ms} ms` : ""} ·{" "}
                  {app.open_findings} nálezov
                </div>
              </div>
            </div>
          </Link>
        ))}
        {!overview.isLoading && (data?.apps.length ?? 0) === 0 && (
          <div className="card" style={{ color: "var(--muted)" }}>
            Zatiaľ žiadne aplikácie. Pridaj prvú v záložke Aplikácie.
          </div>
        )}
      </div>
    </AppShell>
  );
}
