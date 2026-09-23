import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { api } from "@/lib/api";

export function AppsListPage() {
  const qc = useQueryClient();
  const apps = useQuery({ queryKey: ["apps"], queryFn: api.apps });
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("https://");
  const [environment, setEnvironment] = useState("prod");

  const create = useMutation({
    mutationFn: () => api.createApp({ name, base_url: baseUrl, environment }),
    onSuccess: async () => {
      setName("");
      setBaseUrl("https://");
      await qc.invalidateQueries({ queryKey: ["apps"] });
      await qc.invalidateQueries({ queryKey: ["overview"] });
    },
  });

  return (
    <AppShell>
      <h2 style={{ marginTop: 0 }}>Aplikácie</h2>
      <form
        className="card"
        style={{ display: "grid", gap: "0.6rem", marginBottom: "1rem" }}
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <strong>Pridať appku</strong>
        <input
          className="input"
          placeholder="Názov"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <input
          className="input"
          placeholder="Base URL"
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          required
        />
        <input
          className="input"
          placeholder="Environment"
          value={environment}
          onChange={(e) => setEnvironment(e.target.value)}
        />
        {create.error && (
          <div style={{ color: "var(--danger)" }}>{(create.error as Error).message}</div>
        )}
        <button className="btn btn-primary" type="submit" disabled={create.isPending}>
          Uložiť
        </button>
      </form>

      <div style={{ display: "grid", gap: "0.75rem" }}>
        {(apps.data ?? []).map((app) => {
          const verified = app.targets.some((t) => t.status === "verified");
          return (
            <Link
              key={app.id}
              to="/apps/$appId"
              params={{ appId: app.id }}
              style={{ textDecoration: "none", color: "inherit" }}
            >
              <div className="card">
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <strong>{app.name}</strong>
                  <span className={`badge ${verified ? "badge-ok" : "badge-warn"}`}>
                    {verified ? "verified" : "pending"}
                  </span>
                </div>
                <div style={{ color: "var(--muted)", fontSize: "0.85rem", marginTop: 4 }}>
                  {app.base_url}
                </div>
              </div>
            </Link>
          );
        })}
      </div>
    </AppShell>
  );
}
