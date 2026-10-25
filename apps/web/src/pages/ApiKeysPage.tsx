import { useEffect, useState } from "react";
import { api, type ApiKey, type ApiKeyCreated, type AppItem, type Organization } from "../lib/api";
import { CiCodeGenerator } from "../components/CiCodeGenerator";

export const ApiKeysPage: React.FC = () => {
  const [currentOrg, setCurrentOrg] = useState<Organization | null>(null);
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [apps, setApps] = useState<AppItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // New key dialog
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [keyName, setKeyName] = useState("");
  const [selectedScopes, setSelectedScopes] = useState<string[]>(["ci:scan", "apps:read"]);
  const [creating, setCreating] = useState(false);

  // Key revealed modal
  const [createdKeyData, setCreatedKeyData] = useState<ApiKeyCreated | null>(null);
  const [copiedToken, setCopiedToken] = useState(false);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const orgs = await api.getOrgs();
      if (!orgs || orgs.length === 0) {
        setLoading(false);
        return;
      }
      const active = orgs[0];
      setCurrentOrg(active);

      const [loadedKeys, loadedApps] = await Promise.all([
        api.listApiKeys(active.id).catch(() => []),
        api.apps().catch(() => []),
      ]);

      setKeys(loadedKeys);
      setApps(loadedApps);
    } catch (err: any) {
      setError(err?.message || "Nepodarilo sa načítať API kľúče");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleCreateKey = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentOrg || !keyName.trim()) return;

    try {
      setCreating(true);
      setError(null);
      const res = await api.createApiKey(currentOrg.id, {
        name: keyName.trim(),
        scopes: selectedScopes,
      });
      setCreatedKeyData(res);
      setShowCreateModal(false);
      setKeyName("");
      // Reload list
      const updated = await api.listApiKeys(currentOrg.id);
      setKeys(updated);
    } catch (err: any) {
      setError(err?.message || "Vytvorenie kľúča zlyhalo. Skontrolujte kvótu vášho plánu.");
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteKey = async (keyId: string) => {
    if (!currentOrg) return;
    if (
      !window.confirm(
        "Naozaj chcete zrušiť tento API kľúč? Všetky CI/CD pipeline s týmto kľúčom okamžite prestanú fungovať."
      )
    ) {
      return;
    }
    try {
      await api.deleteApiKey(currentOrg.id, keyId);
      setKeys(keys.filter((k) => k.id !== keyId));
    } catch (err: any) {
      setError(err?.message || "Zrušenie kľúča zlyhalo.");
    }
  };

  const copyCreatedToken = () => {
    if (!createdKeyData) return;
    navigator.clipboard.writeText(createdKeyData.raw_key);
    setCopiedToken(true);
    setTimeout(() => setCopiedToken(false), 2000);
  };

  const isFreePlan = currentOrg?.plan_tier === "free";

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2.5">
            <svg className="w-6 h-6 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
            </svg>
            API Kľúče & DevSecOps
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Generujte automatizované tokeny pre GitHub Actions, GitLab CI alebo vlastné skripty.
          </p>
        </div>

        <button
          onClick={() => setShowCreateModal(true)}
          disabled={isFreePlan}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition ${
            isFreePlan
              ? "bg-slate-800 text-slate-500 cursor-not-allowed"
              : "bg-emerald-600 hover:bg-emerald-500 text-white shadow-sm"
          }`}
        >
          <span>+ Nový API kľúč</span>
        </button>
      </div>

      {/* Error alert */}
      {error && (
        <div className="p-4 bg-rose-950/40 border border-rose-800 rounded-xl flex items-center gap-3 text-rose-300 text-sm">
          <span>{error}</span>
        </div>
      )}

      {/* Free tier notice */}
      {isFreePlan && (
        <div className="p-4 bg-amber-950/30 border border-amber-800/80 rounded-xl flex items-start gap-3.5 text-amber-200">
          <div>
            <h4 className="text-sm font-semibold text-amber-300">API kľúče nie sú dostupné vo Free pláne</h4>
            <p className="text-xs text-amber-400/90 mt-1">
              Pre generovanie API kľúčov a integráciu do CI/CD pipeline prejdite na balík{" "}
              <strong>Starter</strong> (2 kľúče) alebo <strong>Pro</strong> (neobmedzene).
            </p>
            <a
              href="/billing"
              className="inline-block mt-2.5 text-xs font-medium text-amber-300 underline hover:text-white"
            >
              Prejsť na fakturáciu a predplatné &rarr;
            </a>
          </div>
        </div>
      )}

      {/* Keys Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-white">Aktívne API kľúče</h2>
          <span className="text-xs text-slate-400">
            Plán: <span className="uppercase text-slate-200 font-medium">{currentOrg?.plan_tier || "free"}</span>
          </span>
        </div>

        {loading ? (
          <div className="p-8 text-center text-sm text-slate-500">Načítavam API kľúče...</div>
        ) : keys.length === 0 ? (
          <div className="p-8 text-center text-sm text-slate-500">
            Zatiaľ nemáte vytvorené žiadne API kľúče.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="bg-slate-950/60 text-slate-400 uppercase tracking-wider font-semibold border-b border-slate-800">
                <tr>
                  <th className="px-6 py-3">Názov</th>
                  <th className="px-6 py-3">Prefix kľúča</th>
                  <th className="px-6 py-3">Oprávnenia (Scopes)</th>
                  <th className="px-6 py-3">Naposledy použitý</th>
                  <th className="px-6 py-3">Vytvorený</th>
                  <th className="px-6 py-3 text-right">Akcie</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {keys.map((k) => (
                  <tr key={k.id} className="hover:bg-slate-800/40 transition">
                    <td className="px-6 py-3.5 font-medium text-white">{k.name}</td>
                    <td className="px-6 py-3.5 font-mono text-slate-400">
                      {k.key_prefix}...
                    </td>
                    <td className="px-6 py-3.5">
                      <div className="flex flex-wrap gap-1">
                        {k.scopes.map((s) => (
                          <span
                            key={s}
                            className="px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-300 text-[10px]"
                          >
                            {s}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-6 py-3.5 text-slate-400">
                      {k.last_used_at ? new Date(k.last_used_at).toLocaleString("sk-SK") : "Nikdy"}
                    </td>
                    <td className="px-6 py-3.5 text-slate-400">
                      {new Date(k.created_at).toLocaleDateString("sk-SK")}
                    </td>
                    <td className="px-6 py-3.5 text-right">
                      <button
                        onClick={() => handleDeleteKey(k.id)}
                        className="px-2.5 py-1 text-slate-400 hover:text-rose-400 transition"
                        title="Zrušiť kľúč"
                      >
                        Zrušiť
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* CI/CD Generator */}
      <CiCodeGenerator apps={apps} />

      {/* Modal: Create Key */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-md w-full p-6 space-y-5 shadow-2xl">
            <h3 className="text-base font-semibold text-white">Vytvoriť nový API kľúč</h3>

            <form onSubmit={handleCreateKey} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1.5">
                  Názov kľúča
                </label>
                <input
                  type="text"
                  placeholder="napr. GitHub Actions Staging"
                  value={keyName}
                  onChange={(e) => setKeyName(e.target.value)}
                  required
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1.5">
                  Oprávnenia (Scopes)
                </label>
                <div className="space-y-2">
                  <label className="flex items-center gap-2 text-xs text-slate-300">
                    <input
                      type="checkbox"
                      checked={selectedScopes.includes("ci:scan")}
                      onChange={(e) => {
                        if (e.target.checked) setSelectedScopes([...selectedScopes, "ci:scan"]);
                        else setSelectedScopes(selectedScopes.filter((s) => s !== "ci:scan"));
                      }}
                      className="rounded bg-slate-800 border-slate-700 text-emerald-600 focus:ring-0"
                    />
                    <span>ci:scan (Spúšťanie bezpečnostných CI brán)</span>
                  </label>
                  <label className="flex items-center gap-2 text-xs text-slate-300">
                    <input
                      type="checkbox"
                      checked={selectedScopes.includes("apps:read")}
                      onChange={(e) => {
                        if (e.target.checked) setSelectedScopes([...selectedScopes, "apps:read"]);
                        else setSelectedScopes(selectedScopes.filter((s) => s !== "apps:read"));
                      }}
                      className="rounded bg-slate-800 border-slate-700 text-emerald-600 focus:ring-0"
                    />
                    <span>apps:read (Čítanie zoznamu aplikácií)</span>
                  </label>
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-3.5 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-white transition"
                >
                  Zrušiť
                </button>
                <button
                  type="submit"
                  disabled={creating || !keyName.trim()}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-medium transition disabled:opacity-50"
                >
                  {creating ? "Generujem..." : "Vygenerovať kľúč"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Display Created Key */}
      {createdKeyData && (
        <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-lg w-full p-6 space-y-5 shadow-2xl">
            <h3 className="text-base font-semibold text-white">Váš nový API kľúč bol vygenerovaný</h3>

            <div className="p-3 bg-amber-950/40 border border-amber-800/80 rounded-lg text-amber-200 text-xs leading-relaxed">
              <strong>DÔLEŽITÉ UPOZORNENIE:</strong> Tento kľúč sa zobrazuje <strong>iba teraz</strong>. Z bezpečnostných dôvodov ho v databáze neukladáme v čitateľnej podobe a už ho nebude možné znova zobraziť.
            </div>

            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-slate-400">
                API Kľúč ({createdKeyData.name})
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  readOnly
                  value={createdKeyData.raw_key}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs font-mono text-emerald-400 select-all focus:outline-none"
                />
                <button
                  onClick={copyCreatedToken}
                  className="flex items-center gap-1.5 px-3 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-medium transition"
                >
                  {copiedToken ? (
                    <span>Skopírované!</span>
                  ) : (
                    <span>Kopírovať</span>
                  )}
                </button>
              </div>
            </div>

            <div className="pt-3 border-t border-slate-800 flex justify-end">
              <button
                onClick={() => setCreatedKeyData(null)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg text-xs font-medium transition"
              >
                Rozumiem, kľúč mám bezpečne uložený
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
