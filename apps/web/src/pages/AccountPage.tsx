import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AppShell } from "@/components/AppShell";
import { api } from "@/lib/api";

export function AccountPage({ onLogout }: { onLogout: () => void }) {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: api.me });
  const logout = useMutation({
    mutationFn: api.logout,
    onSuccess: async () => {
      await qc.clear();
      onLogout();
    },
  });

  return (
    <AppShell>
      <h2 style={{ marginTop: 0 }}>Účet</h2>
      <div className="card" style={{ display: "grid", gap: "0.75rem" }}>
        <div>
          <div style={{ color: "var(--muted)", fontSize: "0.75rem" }}>Email</div>
          <strong>{me.data?.email ?? "…"}</strong>
        </div>
        <button
          className="btn"
          onClick={() => logout.mutate()}
          disabled={logout.isPending}
        >
          Odhlásiť
        </button>
      </div>
    </AppShell>
  );
}
