import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";

export function LoginPage({ onSuccess }: { onSuccess: () => void }) {
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("");
  const login = useMutation({
    mutationFn: () => api.login(email, password),
    onSuccess,
  });

  return (
    <div className="app-shell" style={{ justifyContent: "center" }}>
      <div style={{ padding: "1.5rem", maxWidth: 420, margin: "0 auto", width: "100%" }}>
        <h1 style={{ marginTop: 0 }}>Stráž</h1>
        <p style={{ color: "var(--muted)" }}>Prihlásenie operátora</p>
        <form
          className="card"
          style={{ display: "grid", gap: "0.75rem" }}
          onSubmit={(e) => {
            e.preventDefault();
            login.mutate();
          }}
        >
          <label>
            Email
            <input
              className="input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="username"
            />
          </label>
          <label>
            Heslo
            <input
              className="input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </label>
          {login.error && (
            <div style={{ color: "var(--danger)", fontSize: "0.875rem" }}>
              {(login.error as Error).message}
            </div>
          )}
          <button className="btn btn-primary" type="submit" disabled={login.isPending}>
            {login.isPending ? "Prihlasujem…" : "Prihlásiť"}
          </button>
        </form>
      </div>
    </div>
  );
}
