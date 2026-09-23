import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "@tanstack/react-router";
import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { api, type Run } from "@/lib/api";
import { useOnline } from "@/lib/useOnline";

export function AppDetailPage() {
  const params = useParams({ strict: false }) as { appId?: string };
  const appId = params.appId ?? "";
  const qc = useQueryClient();
  const online = useOnline();
  const [host, setHost] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  const app = useQuery({
    queryKey: ["app", appId],
    queryFn: () => api.app(appId),
    enabled: Boolean(appId),
  });

  const invalidate = async () => {
    await qc.invalidateQueries({ queryKey: ["app", appId] });
    await qc.invalidateQueries({ queryKey: ["apps"] });
    await qc.invalidateQueries({ queryKey: ["overview"] });
    await qc.invalidateQueries({ queryKey: ["runs"] });
  };

  const addTarget = useMutation({
    mutationFn: () => api.addTarget(appId, host),
    onSuccess: async () => {
      setHost("");
      await invalidate();
    },
  });

  const verify = useMutation({
    mutationFn: (id: string) => api.verifyTarget(id),
    onSuccess: invalidate,
    onError: (e: Error) => setMsg(e.message),
  });

  const trust = useMutation({
    mutationFn: (id: string) => api.trustPrivate(id),
    onSuccess: invalidate,
    onError: (e: Error) => setMsg(e.message),
  });

  const runScan = useMutation({
    mutationFn: (profile: Run["profile"]) => api.createRun(appId, profile),
    onSuccess: invalidate,
    onError: (e: Error) => setMsg(e.message),
  });

  const del = useMutation({
    mutationFn: () => api.deleteApp(appId),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["apps"] });
      window.location.href = "/apps";
    },
  });

  const data = app.data;
  const hasVerified = data?.targets.some((t) => t.status === "verified") ?? false;

  return (
    <AppShell>
      <Link to="/apps" style={{ color: "var(--accent)", fontSize: "0.85rem" }}>
        ← Aplikácie
      </Link>
      {app.isLoading && <p>Načítavam…</p>}
      {data && (
        <>
          <h2 style={{ marginBottom: 4 }}>{data.name}</h2>
          <div style={{ color: "var(--muted)", marginBottom: "1rem" }}>{data.base_url}</div>

          {msg && (
            <div className="card" style={{ color: "var(--danger)", marginBottom: "0.75rem" }}>
              {msg}
            </div>
          )}

          <div className="card" style={{ marginBottom: "0.75rem" }}>
            <strong>Skeny</strong>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginTop: "0.75rem" }}>
              {(
                [
                  ["heartbeat", "Heartbeat"],
                  ["tls", "TLS"],
                  ["http", "HTTP"],
                  ["safe", "Nuclei safe"],
                ] as const
              ).map(([profile, label]) => (
                <button
                  key={profile}
                  className="btn"
                  disabled={
                    !online ||
                    runScan.isPending ||
                    (profile !== "heartbeat" && !hasVerified)
                  }
                  onClick={() => {
                    setMsg(null);
                    runScan.mutate(profile);
                  }}
                  title={
                    profile !== "heartbeat" && !hasVerified
                      ? "Najprv over target"
                      : !online
                        ? "Offline"
                        : undefined
                  }
                >
                  {label}
                </button>
              ))}
            </div>
            {!hasVerified && (
              <p style={{ color: "var(--warn)", fontSize: "0.85rem", marginBottom: 0 }}>
                TLS / HTTP / Nuclei sú disabled, kým nie je aspoň jeden verified target.
              </p>
            )}
          </div>

          <div className="card" style={{ marginBottom: "0.75rem" }}>
            <strong>Targety</strong>
            <div style={{ display: "grid", gap: "0.75rem", marginTop: "0.75rem" }}>
              {data.targets.map((t) => (
                <div
                  key={t.id}
                  style={{
                    borderTop: "1px solid var(--border)",
                    paddingTop: "0.75rem",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
                    <code>{t.host}</code>
                    <span className={`badge ${t.status === "verified" ? "badge-ok" : "badge-warn"}`}>
                      {t.status}
                    </span>
                  </div>
                  {t.status !== "verified" && (
                    <div style={{ fontSize: "0.8rem", color: "var(--muted)", marginTop: 6 }}>
                      DNS TXT: <code>straz-verify={t.verify_token}</code>
                      <br />
                      alebo <code>/.well-known/straz.txt</code> s tokenom
                    </div>
                  )}
                  {t.status !== "verified" && (
                    <div style={{ display: "flex", gap: "0.5rem", marginTop: 8, flexWrap: "wrap" }}>
                      <button
                        className="btn btn-primary"
                        disabled={!online || verify.isPending}
                        onClick={() => {
                          setMsg(null);
                          verify.mutate(t.id);
                        }}
                      >
                        Overiť
                      </button>
                      <button
                        className="btn"
                        disabled={!online || trust.isPending}
                        onClick={() => {
                          setMsg(null);
                          trust.mutate(t.id);
                        }}
                      >
                        Trust private
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
            <form
              style={{ display: "flex", gap: "0.5rem", marginTop: "1rem" }}
              onSubmit={(e) => {
                e.preventDefault();
                addTarget.mutate();
              }}
            >
              <input
                className="input"
                placeholder="ďalší host / IP"
                value={host}
                onChange={(e) => setHost(e.target.value)}
                required
              />
              <button className="btn" type="submit" disabled={!online || addTarget.isPending}>
                Pridať
              </button>
            </form>
          </div>

          <button
            className="btn"
            style={{ color: "var(--danger)" }}
            onClick={() => del.mutate()}
            disabled={del.isPending}
          >
            Zmazať appku
          </button>
        </>
      )}
    </AppShell>
  );
}
