import React, { useEffect, useState } from "react";
import { api, getActiveOrgId } from "../lib/api";

const PLATFORMS = [
  { id: "slack", name: "Slack", icon: "💬", desc: "Incoming Webhook do firemného Slack kanála" },
  { id: "discord", name: "Discord", icon: "🎮", desc: "Webhooks s farebnými embed kartami" },
  { id: "teams", name: "Microsoft Teams", icon: "👥", desc: "Adaptive Cards do tímových konverzácií" },
  { id: "webhook", name: "Vlastný Webhook", icon: "🔗", desc: "JSON payload s HMAC-SHA256 podpisom" },
  { id: "ntfy", name: "ntfy.sh", icon: "🔔", desc: "Push notifikácie do mobilu aj prehliadača" },
];

export function IntegrationsPage() {
  const orgId = getActiveOrgId();
  const [channels, setChannels] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [testingId, setTestingId] = useState<string | null>(null);

  // Form state
  const [platform, setPlatform] = useState("slack");
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [minSeverity, setMinSeverity] = useState("high");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (orgId) {
      loadChannels();
    }
  }, [orgId]);

  async function loadChannels() {
    if (!orgId) return;
    setLoading(true);
    try {
      const data = await api.getChannels(orgId);
      setChannels(data);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!orgId || !name.trim() || !url.trim()) return;
    setSubmitting(true);
    try {
      await api.createChannel(orgId, {
        platform,
        name: name.trim(),
        destination_url: url.trim(),
        secret_token: secret.trim() || undefined,
        min_severity: minSeverity,
      });
      setShowModal(false);
      setName("");
      setUrl("");
      setSecret("");
      await loadChannels();
    } catch (err: any) {
      alert(err.message || "Nepodarilo sa vytvoriť kanál.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleToggle(ch: any) {
    if (!orgId) return;
    try {
      await api.updateChannel(orgId, ch.id, { is_active: !ch.is_active });
      await loadChannels();
    } catch (err: any) {
      alert(err.message || "Chyba pri aktualizácii kanála.");
    }
  }

  async function handleDelete(chId: string) {
    if (!orgId || !confirm("Naozaj chcete zmazať tento notifikačný kanál?")) return;
    try {
      await api.deleteChannel(orgId, chId);
      await loadChannels();
    } catch (err: any) {
      alert(err.message || "Zmazanie zlyhalo.");
    }
  }

  async function handleTest(chId: string) {
    if (!orgId) return;
    setTestingId(chId);
    try {
      const res = await api.testChannel(orgId, chId);
      if (res.delivered) {
        alert("✓ Testovacia správa bola úspešne doručená!");
      } else {
        alert("⚠️ Cieľový server neodpovedal kladne. Skontrolujte Webhook URL.");
      }
    } catch (err: any) {
      alert(err.message || "Odoslanie testovacej správy zlyhalo.");
    } finally {
      setTestingId(null);
    }
  }

  return (
    <div className="max-w-5xl mx-auto space-y-8 p-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">
            Notifikačné Integrácie
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Okamžité upozornenia pri zistení nových zraniteľností alebo výpadku systémov.
          </p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="px-4 py-2 text-xs font-semibold bg-sky-500 hover:bg-sky-400 text-white rounded-lg transition shadow-lg shadow-sky-500/20"
        >
          + Pridať kanál
        </button>
      </div>

      {/* Channels grid */}
      {loading ? (
        <div className="p-8 text-center text-slate-400 text-sm">Načítavam kanály...</div>
      ) : channels.length === 0 ? (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-12 text-center space-y-3">
          <div className="text-3xl">🔔</div>
          <h3 className="text-base font-semibold text-white">Žiadne aktívne kanály</h3>
          <p className="text-xs text-slate-400 max-w-sm mx-auto">
            Pripojte Slack, Discord, Microsoft Teams alebo vlastný Webhook, aby váš tím nezmeškal kritické bezpečnostné udalosti.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {channels.map((ch) => {
            const plat = PLATFORMS.find((p) => p.id === ch.platform);
            return (
              <div
                key={ch.id}
                className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4 shadow-sm"
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">{plat?.icon || "📢"}</span>
                    <div>
                      <h3 className="text-sm font-bold text-white">{ch.name}</h3>
                      <div className="text-xs text-slate-400 capitalize">
                        {ch.platform} • Min. závažnosť:{" "}
                        <span className="font-semibold text-slate-300">
                          {ch.min_severity.toUpperCase()}
                        </span>
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={() => handleToggle(ch)}
                    className={`px-2 py-0.5 text-[10px] font-bold rounded-full border transition ${
                      ch.is_active
                        ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                        : "bg-slate-800 text-slate-400 border-slate-700"
                    }`}
                  >
                    {ch.is_active ? "Aktívny" : "Pozastavený"}
                  </button>
                </div>

                <div className="text-xs font-mono text-slate-400 bg-slate-950/60 p-2 rounded border border-slate-800 truncate">
                  {ch.destination_url_masked}
                </div>

                <div className="flex items-center justify-between pt-2 border-t border-slate-800/60">
                  <button
                    onClick={() => handleTest(ch.id)}
                    disabled={testingId === ch.id}
                    className="text-xs font-semibold text-sky-400 hover:text-sky-300 disabled:opacity-50"
                  >
                    {testingId === ch.id ? "Testujem..." : "Otestovať doručenie"}
                  </button>
                  <button
                    onClick={() => handleDelete(ch.id)}
                    className="text-xs text-rose-400 hover:text-rose-300"
                  >
                    Zmazať
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Add channel modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 max-w-lg w-full shadow-2xl space-y-4">
            <h3 className="text-lg font-bold text-white">Pridať notifikačný kanál</h3>

            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Platforma
                </label>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                  {PLATFORMS.map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => setPlatform(p.id)}
                      className={`p-2.5 rounded-lg border text-left text-xs transition flex items-center gap-2 ${
                        platform === p.id
                          ? "bg-sky-500/10 border-sky-500 text-white font-semibold"
                          : "bg-slate-800/60 border-slate-700 text-slate-300 hover:border-slate-600"
                      }`}
                    >
                      <span>{p.icon}</span>
                      <span>{p.name}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Názov kanála
                </label>
                <input
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Napr. #security-alerts"
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-sky-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Webhook URL (HTTPS)
                </label>
                <input
                  type="url"
                  required
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://hooks.slack.com/services/..."
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-sky-500"
                />
              </div>

              {platform === "webhook" && (
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">
                    HMAC Tajný kľúč (voliteľné)
                  </label>
                  <input
                    type="password"
                    value={secret}
                    onChange={(e) => setSecret(e.target.value)}
                    placeholder="Tajný token pre overenie X-Straz-Signature"
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-sky-500"
                  />
                </div>
              )}

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Minimálna závažnosť pre odoslanie
                </label>
                <select
                  value={minSeverity}
                  onChange={(e) => setMinSeverity(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-sky-500"
                >
                  <option value="critical">Iba Critical</option>
                  <option value="high">High & Critical (Odporúčané)</option>
                  <option value="medium">Medium, High & Critical</option>
                  <option value="info">Všetky nálezy (vrátane Info/Low)</option>
                </select>
              </div>

              <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 text-xs text-slate-400 hover:text-white"
                >
                  Zrušiť
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-5 py-2 text-xs font-semibold bg-sky-500 hover:bg-sky-400 text-white rounded-lg transition disabled:opacity-50"
                >
                  {submitting ? "Ukladám..." : "Vytvoriť kanál"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
