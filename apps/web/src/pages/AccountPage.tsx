import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AppShell } from "@/components/AppShell";
import { api } from "@/lib/api";
import { toast } from "@/lib/toast";

export function AccountPage({ onLogout }: { onLogout: () => void }) {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: api.me });

  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [pwdError, setPwdError] = useState<string | null>(null);

  const logout = useMutation({
    mutationFn: api.logout,
    onSuccess: async () => {
      await qc.clear();
      toast.info("Boli ste úspešne odhlásený");
      onLogout();
    },
  });

  const changePwd = useMutation({
    mutationFn: () => api.changePassword(oldPassword, newPassword),
    onSuccess: () => {
      toast.success("Heslo bolo úspešne zmenené. Ostatné relácie boli odhlásené.");
      setOldPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setPwdError(null);
    },
    onError: (err: Error) => {
      setPwdError(err.message);
      toast.error(err.message || "Nepodarilo sa zmeniť heslo");
    },
  });

  const handlePasswordSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPwdError(null);

    if (newPassword.length < 8) {
      setPwdError("Nové heslo musí mať aspoň 8 znakov.");
      return;
    }

    if (newPassword !== confirmPassword) {
      setPwdError("Nové heslo a potvrdenie sa nezhodujú.");
      return;
    }

    changePwd.mutate();
  };

  return (
    <AppShell>
      <div className="max-w-2xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 tracking-tight">Správa účtu</h1>
          <p className="text-sm text-slate-400 mt-1">
            Informácie o profile a nastavenia bezpečnosti
          </p>
        </div>

        {/* Profile Card */}
        <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 space-y-4">
          <h2 className="text-base font-semibold text-slate-200">Prihlásený používateľ</h2>
          <div className="flex items-center justify-between p-4 rounded-xl bg-slate-950/60 border border-slate-800/80">
            <div>
              <div className="text-xs font-medium text-slate-400">Emailová adresa</div>
              <div className="text-base font-medium text-slate-100 mt-0.5">
                {me.data?.email ?? "…"}
              </div>
            </div>
            <button
              onClick={() => logout.mutate()}
              disabled={logout.isPending}
              className="px-4 py-2 text-sm font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700/50 transition disabled:opacity-50"
            >
              {logout.isPending ? "Odhlasujem…" : "Odhlásiť"}
            </button>
          </div>
        </div>

        {/* Change Password Card */}
        <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 space-y-5">
          <div>
            <h2 className="text-base font-semibold text-slate-200">Zmena hesla</h2>
            <p className="text-xs text-slate-400 mt-1">
              Po úspešnej zmene hesla budú automaticky zneplatnené všetky ostatné aktívne prihlásenia.
            </p>
          </div>

          <form onSubmit={handlePasswordSubmit} className="space-y-4">
            {pwdError && (
              <div className="p-3 text-xs text-rose-300 bg-rose-500/10 border border-rose-500/20 rounded-lg">
                {pwdError}
              </div>
            )}

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-300 block">
                Pôvodné heslo
              </label>
              <input
                type="password"
                required
                value={oldPassword}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setOldPassword(e.target.value)}
                className="w-full px-3.5 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500/50"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-300 block">
                  Nové heslo (min. 8 znakov)
                </label>
                <input
                  type="password"
                  required
                  minLength={8}
                  value={newPassword}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewPassword(e.target.value)}
                  className="w-full px-3.5 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500/50"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-300 block">
                  Potvrdenie nového hesla
                </label>
                <input
                  type="password"
                  required
                  minLength={8}
                  value={confirmPassword}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setConfirmPassword(e.target.value)}
                  className="w-full px-3.5 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500/50"
                />
              </div>
            </div>

            <div className="pt-2 flex justify-end">
              <button
                type="submit"
                disabled={changePwd.isPending}
                className="px-5 py-2.5 text-sm font-medium rounded-xl bg-sky-600 hover:bg-sky-500 text-white shadow-sm transition disabled:opacity-50"
              >
                {changePwd.isPending ? "Mení sa heslo…" : "Aktualizovať heslo"}
              </button>
            </div>
          </form>
        </div>
      </div>
    </AppShell>
  );
}
