import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function RegisterPage({
  onSuccess,
  onSwitchToLogin,
}: {
  onSuccess: () => void;
  onSwitchToLogin: () => void;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [clientError, setClientError] = useState<string | null>(null);

  const register = useMutation({
    mutationFn: () => api.register(email, password),
    onSuccess,
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setClientError(null);

    if (password.length < 8) {
      setClientError("Heslo musí mať minimálne 8 znakov.");
      return;
    }

    if (password !== confirmPassword) {
      setClientError("Heslá sa nezhodujú.");
      return;
    }

    register.mutate();
  };

  const errorMessage = clientError || (register.error ? (register.error as Error).message : null);

  return (
    <div className="min-h-screen flex flex-col justify-center items-center px-4 py-12 bg-slate-950 text-slate-100 selection:bg-sky-500 selection:text-white">
      <div className="max-w-md w-full space-y-6">
        {/* Header Branding */}
        <div className="text-center space-y-2">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-sky-500/10 border border-sky-500/30 text-sky-400 mb-2 shadow-lg shadow-sky-950/40">
            <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z"
              />
            </svg>
          </div>
          <h1 className="text-3xl font-extrabold text-white tracking-tight">Registrácia operátora</h1>
          <p className="text-sm text-slate-400">
            Vytvorte si nový účet v monitorovacom systéme Stráž
          </p>
        </div>

        {/* Register Form */}
        <div className="rounded-3xl border border-slate-800 bg-slate-900/60 p-6 sm:p-8 shadow-2xl backdrop-blur-md">
          <form className="space-y-4" onSubmit={handleSubmit}>
            {errorMessage && (
              <div className="p-3.5 rounded-xl border border-rose-500/30 bg-rose-950/30 text-rose-300 text-xs flex items-start gap-2.5 animate-shake">
                <svg
                  className="w-4 h-4 shrink-0 text-rose-400 mt-0.5"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <span>{errorMessage}</span>
              </div>
            )}

            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase tracking-wider text-slate-300 block">
                Emailová adresa
              </label>
              <input
                type="email"
                required
                className="w-full px-4 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500/50 transition"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="username"
                placeholder="novy.operator@example.com"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase tracking-wider text-slate-300 block">
                Heslo (min. 8 znakov)
              </label>
              <input
                type="password"
                required
                minLength={8}
                className="w-full px-4 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500/50 transition"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                placeholder="••••••••••••"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase tracking-wider text-slate-300 block">
                Potvrdenie hesla
              </label>
              <input
                type="password"
                required
                minLength={8}
                className="w-full px-4 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500/50 transition"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
                placeholder="••••••••••••"
              />
            </div>

            <button
              type="submit"
              disabled={register.isPending}
              className="w-full mt-2 py-3 px-4 rounded-xl text-sm font-semibold bg-sky-600 hover:bg-sky-500 text-white shadow-lg shadow-sky-950/50 transition disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {register.isPending ? (
                <>
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>Registrujem účet…</span>
                </>
              ) : (
                "Vytvoriť účet"
              )}
            </button>
          </form>

          <div className="mt-6 pt-4 border-t border-slate-800/80 text-center">
            <button
              type="button"
              onClick={onSwitchToLogin}
              className="text-xs text-sky-400 hover:text-sky-300 font-medium transition"
            >
              Už máte účet? Prihláste sa
            </button>
          </div>
        </div>

        <div className="text-center text-xs text-slate-500">
          Chránené šifrovanou reláciou a rate limiterom
        </div>
      </div>
    </div>
  );
}
