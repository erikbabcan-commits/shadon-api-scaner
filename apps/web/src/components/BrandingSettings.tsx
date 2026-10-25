import React, { useEffect, useState } from "react";
import { api, getActiveOrgId } from "../lib/api";

export function BrandingSettings() {
  const orgId = getActiveOrgId();
  const [logoUrl, setLogoUrl] = useState("");
  const [brandColor, setBrandColor] = useState("#0284c7");
  const [footerText, setFooterText] = useState("");
  const [whiteLabelEnabled, setWhiteLabelEnabled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState(false);

  useEffect(() => {
    if (orgId) {
      loadBranding();
    }
  }, [orgId]);

  async function loadBranding() {
    if (!orgId) return;
    setLoading(true);
    try {
      const b = await api.getBranding(orgId);
      setLogoUrl(b.custom_logo_url || "");
      setBrandColor(b.brand_color || "#0284c7");
      setFooterText(b.report_footer_text || "");
      setWhiteLabelEnabled(b.white_label_enabled);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!orgId) return;
    setSaving(true);
    setSavedMsg(false);
    try {
      await api.updateBranding(orgId, {
        custom_logo_url: logoUrl,
        brand_color: brandColor,
        report_footer_text: footerText,
      });
      setSavedMsg(true);
      setTimeout(() => setSavedMsg(false), 3000);
    } catch (err: any) {
      alert(err.message || "Nepodarilo sa uložiť branding.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return null;

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-5 shadow-sm">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-white">
            White-Label Nastavenia pre PDF Reporty
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Prispôsobte si logo, farbu a pätičku pre reprezentatívne klientske audity.
          </p>
        </div>
        {!whiteLabelEnabled && (
          <span className="px-2.5 py-1 text-[11px] font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20 rounded-full">
            Dostupné v pláne Pro a Agency
          </span>
        )}
      </div>

      <form onSubmit={handleSave} className="space-y-4">
        <div>
          <label className="block text-xs font-medium text-slate-300 mb-1.5">
            URL adresa loga (HTTPS)
          </label>
          <input
            type="url"
            disabled={!whiteLabelEnabled}
            value={logoUrl}
            onChange={(e) => setLogoUrl(e.target.value)}
            placeholder="https://agentura.sk/assets/logo.png"
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-sky-500 disabled:opacity-50"
          />
        </div>

        <div className="flex gap-4 items-center">
          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1.5">
              Primárna farba
            </label>
            <div className="flex items-center gap-2">
              <input
                type="color"
                disabled={!whiteLabelEnabled}
                value={brandColor}
                onChange={(e) => setBrandColor(e.target.value)}
                className="w-9 h-9 p-0.5 rounded border border-slate-700 bg-slate-800 cursor-pointer disabled:opacity-50"
              />
              <span className="text-xs font-mono text-slate-300">{brandColor}</span>
            </div>
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-300 mb-1.5">
            Text do päty reportu
          </label>
          <input
            type="text"
            disabled={!whiteLabelEnabled}
            value={footerText}
            onChange={(e) => setFooterText(e.target.value)}
            placeholder="Napr. Bezpečnostný audit vypracovala Divízia CyberSec ABC"
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-sky-500 disabled:opacity-50"
          />
        </div>

        {savedMsg && (
          <div className="text-xs font-semibold text-emerald-400">
            ✓ Nastavenia brandingu boli úspešne uložené.
          </div>
        )}

        <button
          type="submit"
          disabled={!whiteLabelEnabled || saving}
          className="px-4 py-2 text-xs font-semibold bg-sky-500 hover:bg-sky-400 text-white rounded-lg transition disabled:opacity-50"
        >
          {saving ? "Ukladám..." : "Uložiť branding"}
        </button>
      </form>
    </div>
  );
}
