import React, { useEffect, useState } from "react";
import { api, getActiveOrgId, OrgMember, OrgRole } from "../lib/api";
import { BrandingSettings } from "../components/BrandingSettings";

export function TeamPage() {
  const [members, setMembers] = useState<OrgMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<OrgRole>("member");
  const [inviteToken, setInviteToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const orgId = getActiveOrgId();

  useEffect(() => {
    if (orgId) {
      loadMembers();
    }
  }, [orgId]);

  async function loadMembers() {
    if (!orgId) return;
    setLoading(true);
    try {
      const data = await api.getOrgMembers(orgId);
      setMembers(data);
    } catch (err: any) {
      setError(err.message || "Nepodarilo sa načítať členov tímu");
    } finally {
      setLoading(false);
    }
  }

  async function handleInvite(e: React.FormEvent) {
    e.preventDefault();
    if (!orgId || !inviteEmail.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.inviteOrgMember(orgId, {
        email: inviteEmail.trim(),
        role: inviteRole,
      });
      setInviteToken(res.token);
      setInviteEmail("");
      await loadMembers();
    } catch (err: any) {
      setError(err.message || "Pozvanie zlyhalo");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRemove(userId: string) {
    if (!orgId || !confirm("Naozaj chcete odstrániť tohto člena?")) return;
    try {
      await api.removeOrgMember(orgId, userId);
      await loadMembers();
    } catch (err: any) {
      alert(err.message || "Odstránenie zlyhalo");
    }
  }

  const inviteLink = inviteToken
    ? `${window.location.origin}/invitations/${inviteToken}`
    : null;

  return (
    <div className="max-w-5xl mx-auto space-y-8 p-6">
      <div>
        <h1 className="text-2xl font-bold text-white tracking-tight">
          Tím a Členovia Organizácie
        </h1>
        <p className="text-sm text-slate-400 mt-1">
          Spravujte prístupy, pozývajte kolegov a nastavujte roly v tomto pracovnom priestore.
        </p>
      </div>

      {error && (
        <div className="bg-rose-500/10 border border-rose-500/20 text-rose-400 px-4 py-3 rounded-lg text-sm">
          {error}
        </div>
      )}

      {/* Invite form */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-sm">
        <h2 className="text-base font-semibold text-white mb-4">
          Pozvať nového člena
        </h2>
        <form onSubmit={handleInvite} className="flex flex-wrap gap-4 items-end">
          <div className="flex-1 min-w-[240px]">
            <label className="block text-xs font-medium text-slate-300 mb-1.5">
              E-mailová adresa
            </label>
            <input
              type="email"
              required
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              placeholder="kolega@firma.sk"
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-sky-500"
            />
          </div>

          <div className="w-40">
            <label className="block text-xs font-medium text-slate-300 mb-1.5">
              Rola
            </label>
            <select
              value={inviteRole}
              onChange={(e) => setInviteRole(e.target.value as OrgRole)}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-sky-500"
            >
              <option value="member">Člen (Member)</option>
              <option value="admin">Správca (Admin)</option>
              <option value="viewer">Pozorovateľ (Viewer)</option>
            </select>
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="px-5 py-2 text-sm font-semibold bg-sky-500 hover:bg-sky-400 text-white rounded-lg transition disabled:opacity-50"
          >
            {submitting ? "Odosielam..." : "Generovať pozvánku"}
          </button>
        </form>

        {inviteLink && (
          <div className="mt-4 p-4 bg-emerald-500/10 border border-emerald-500/20 rounded-lg">
            <p className="text-xs font-semibold text-emerald-400 mb-1">
              Pozvánka úspešne vygenerovaná! Odkaz na prijatie:
            </p>
            <div className="flex items-center gap-2">
              <input
                type="text"
                readOnly
                value={inviteLink}
                className="w-full bg-slate-800 text-xs text-slate-200 px-3 py-2 rounded border border-slate-700"
              />
              <button
                type="button"
                onClick={() => {
                  navigator.clipboard.writeText(inviteLink);
                  alert("Odkaz skopírovaný do schránky!");
                }}
                className="px-3 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded whitespace-nowrap"
              >
                Kopírovať
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Members table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
        <div className="px-6 py-4 border-b border-slate-800">
          <h2 className="text-base font-semibold text-white">Aktuálni členovia</h2>
        </div>

        {loading ? (
          <div className="p-8 text-center text-slate-400 text-sm">Načítavam...</div>
        ) : members.length === 0 ? (
          <div className="p-8 text-center text-slate-400 text-sm">
            Zatiaľ žiadni ďalší členovia.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-300">
              <thead className="bg-slate-950/40 text-xs font-medium text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="px-6 py-3">E-mail</th>
                  <th className="px-6 py-3">Rola</th>
                  <th className="px-6 py-3">Člen od</th>
                  <th className="px-6 py-3 text-right">Akcie</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {members.map((m) => (
                  <tr key={m.id} className="hover:bg-slate-800/40 transition">
                    <td className="px-6 py-4 font-medium text-white">{m.email}</td>
                    <td className="px-6 py-4">
                      <span
                        className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                          m.role === "owner"
                            ? "bg-purple-500/10 text-purple-400 border border-purple-500/20"
                            : m.role === "admin"
                            ? "bg-sky-500/10 text-sky-400 border border-sky-500/20"
                            : m.role === "viewer"
                            ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                            : "bg-slate-800 text-slate-300 border border-slate-700"
                        }`}
                      >
                        {m.role}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-xs text-slate-400">
                      {new Date(m.created_at).toLocaleDateString("sk-SK")}
                    </td>
                    <td className="px-6 py-4 text-right">
                      {m.role !== "owner" && (
                        <button
                          onClick={() => handleRemove(m.user_id)}
                          className="text-xs text-rose-400 hover:text-rose-300 hover:underline"
                        >
                          Odstrániť
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* White-label branding section */}
      <BrandingSettings />
    </div>
  );
}
