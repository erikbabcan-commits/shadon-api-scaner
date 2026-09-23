import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AppShell } from "@/components/AppShell";
import { api, type Finding } from "@/lib/api";

const sevColor: Record<Finding["severity"], string> = {
  info: "var(--muted)",
  low: "var(--accent)",
  medium: "var(--warn)",
  high: "var(--danger)",
  critical: "#fb7185",
};

export function FindingsPage() {
  const qc = useQueryClient();
  const findings = useQuery({
    queryKey: ["findings", "open"],
    queryFn: () => api.findings({ status: "open" }),
    refetchInterval: 20_000,
  });

  const update = useMutation({
    mutationFn: ({ id, status }: { id: string; status: Finding["status"] }) =>
      api.updateFinding(id, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["findings"] }),
  });

  return (
    <AppShell>
      <h2 style={{ marginTop: 0 }}>Nálezy</h2>
      <div style={{ display: "grid", gap: "0.75rem" }}>
        {(findings.data ?? []).map((f) => (
          <div key={f.id} className="card">
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
              <strong style={{ color: sevColor[f.severity] }}>{f.severity}</strong>
              <span style={{ color: "var(--muted)", fontSize: "0.75rem" }}>{f.source}</span>
            </div>
            <div style={{ marginTop: 6 }}>{f.title}</div>
            {f.detail && (
              <pre
                style={{
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  color: "var(--muted)",
                  fontSize: "0.75rem",
                  marginBottom: 0,
                }}
              >
                {f.detail.slice(0, 500)}
              </pre>
            )}
            <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem" }}>
              <button
                className="btn"
                onClick={() => update.mutate({ id: f.id, status: "accepted" })}
              >
                Accept
              </button>
              <button
                className="btn"
                onClick={() => update.mutate({ id: f.id, status: "fixed" })}
              >
                Fixed
              </button>
            </div>
          </div>
        ))}
        {!findings.isLoading && (findings.data?.length ?? 0) === 0 && (
          <div className="card" style={{ color: "var(--muted)" }}>
            Žiadne otvorené nálezy.
          </div>
        )}
      </div>
    </AppShell>
  );
}
