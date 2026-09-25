import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function LoginPage({
  onSuccess,
  onSwitchToRegister,
}: {
  onSuccess: () => void;
  onSwitchToRegister?: () => void;
}) {
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("");

  const login = useMutation({
    mutationFn: () => api.login(email, password),
    onSuccess,
  });

  return (
    <div className="min-h-screen flex flex-col justify-center items-center px-4 py-12 bg-slate-950 text-slate-100 selection:bg-sky-500 selection:text-white">
      <div className="max-w-md w-full space-y-6">
        {/* Header Branding */}
        <div className="text-center space-y-2">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-sky-500/10 border border-sky-500/30 text-sky-400 mb-2 shadow-lg shadow-sky-950/40">
            <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
            </svg>
          </div>
          <h1 className="text-3xl font-extrabold text-white tracking-tight">Stráž</h1>
          <p className="text-sm text-slate-400">
            Prihlásenie operátora monitorovacieho systému
          </p>
        </div>

        {/* Login Form */}
        <div className="rounded-3xl border border-slate-800 bg-slate-900/60 p-6 sm:p-8 shadow-2xl backdrop-blur-md">
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              login.mutate();
            }}
          >
            {login.error && (
              <div className="p-3.5 rounded-xl border border-rose-500/30 bg-rose-950/30 text-rose-300 text-xs flex items-start gap-2.5 animate-shake">
                <svg className="w-4 h-4 shrink-0 text-rose-400 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>{(login.error as Error).message}</span>
              </div>
            )}

            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase tracking-wider text-slate-300 block">
                Email
              </label>
              <input
                type="email"
                required
                className="w-full px-4 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500/50 transition"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="username"
                placeholder="operator@example.com"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase tracking-wider text-slate-300 block">
                Heslo
              </label>
              <input
                type="password"
                required
                className="w-full px-4 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500/50 transition"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                placeholder="••••••••••••"
              />
            </div>

            <button
              type="submit"
              disabled={login.isPending}
              className="w-full mt-2 py-3 px-4 rounded-xl text-sm font-semibold bg-sky-600 hover:bg-sky-500 text-white shadow-lg shadow-sky-950/50 transition disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {login.isPending ? (
                <>
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>Prihlasujem…</span>
                </>
              ) : (
                "Prihlásiť sa"
              )}
            </button>
          </form>

          {onSwitchToRegister && (
            <div className="mt-6 pt-4 border-t border-slate-800/80 text-center">
              <button
                type="button"
                onClick={onSwitchToRegister}
                className="text-xs text-sky-400 hover:text-sky-300 font-medium transition"
              >
                Nemáte účet? Zaregistrujte sa
              </button>
            </div>
          )}
        </div>

        <div className="text-center text-xs text-slate-500">
          Chránené šifrovanou reláciou a rate limiterom
        </div>
      </div>
    </div>
  );
}
