import { useState } from "react";
import { api } from "../lib/api";

export function InvitationPage() {
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Extract token from pathname /invitations/:token
  const parts = window.location.pathname.split("/");
  const token = parts[parts.length - 1];

  async function handleAccept() {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      await api.acceptInvitation(token);
      setSuccess(true);
      setTimeout(() => {
        window.location.href = "/";
      }, 1500);
    } catch (err: any) {
      setError(err.message || "Prijatie pozvánky zlyhalo.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-slate-900 border border-slate-800 rounded-2xl p-8 text-center shadow-xl space-y-6">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-sky-500/10 text-sky-400 text-2xl font-bold">
          🛡️
        </div>

        <div>
          <h1 className="text-xl font-bold text-white">Pozvánka do Tímu Stráž</h1>
          <p className="text-sm text-slate-400 mt-2">
            Boli ste pozvaní do organizácie. Kliknutím nižšie potvrdíte prijatie a získate prístup k bezpečnostnému monitoringu.
          </p>
        </div>

        {error && (
          <div className="bg-rose-500/10 border border-rose-500/20 text-rose-400 p-3 rounded-lg text-xs text-left">
            {error}
          </div>
        )}

        {success ? (
          <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 p-4 rounded-lg text-sm font-semibold">
            ✓ Pozvánka bola úspešne prijatá! Presmerovávam na dashboard...
          </div>
        ) : (
          <button
            onClick={handleAccept}
            disabled={loading}
            className="w-full py-2.5 px-4 bg-sky-500 hover:bg-sky-400 text-white font-semibold text-sm rounded-lg transition shadow-lg shadow-sky-500/20 disabled:opacity-50"
          >
            {loading ? "Pripájam..." : "Prijať pozvánku"}
          </button>
        )}
      </div>
    </div>
  );
}
