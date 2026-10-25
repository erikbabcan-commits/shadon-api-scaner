import React, { useEffect, useState } from "react";
import { api, getActiveOrgId, Organization, setActiveOrgId } from "../lib/api";

export function OrganizationSwitcher() {
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [activeId, setActiveId] = useState<string | null>(getActiveOrgId());
  const [showModal, setShowModal] = useState(false);
  const [newOrgName, setNewOrgName] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadOrgs();
  }, []);

  async function loadOrgs() {
    try {
      const list = await api.getOrgs();
      setOrgs(list);
      if (list.length > 0 && !activeId) {
        setActiveId(list[0].id);
        setActiveOrgId(list[0].id);
      }
    } catch {
      /* ignore */
    }
  }

  function handleSelect(e: React.ChangeEvent<HTMLSelectElement>) {
    const val = e.target.value;
    if (val === "__new__") {
      setShowModal(true);
      return;
    }
    setActiveId(val);
    setActiveOrgId(val);
    window.location.reload();
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!newOrgName.trim()) return;
    setLoading(true);
    try {
      const created = await api.createOrg({ name: newOrgName.trim() });
      setNewOrgName("");
      setShowModal(false);
      setActiveId(created.id);
      setActiveOrgId(created.id);
      window.location.reload();
    } catch (err: any) {
      alert(err.message || "Chyba pri vytváraní organizácie");
    } finally {
      setLoading(false);
    }
  }

  const currentOrg = orgs.find((o) => o.id === activeId);

  return (
    <div className="flex items-center gap-2">
      <div className="relative">
        <select
          value={activeId || ""}
          onChange={handleSelect}
          className="bg-slate-800 text-white text-xs font-medium py-1.5 px-3 pr-8 rounded-lg border border-slate-700 hover:border-slate-600 focus:outline-none focus:ring-2 focus:ring-sky-500 cursor-pointer appearance-none"
        >
          {orgs.map((o) => (
            <option key={o.id} value={o.id}>
              {o.name} ({o.role})
            </option>
          ))}
          <option value="__new__">+ Nová organizácia...</option>
        </select>
        <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-slate-400 text-xs">
          ▼
        </div>
      </div>

      {showModal && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 max-w-sm w-full shadow-2xl">
            <h3 className="text-lg font-bold text-white mb-2">Vytvoriť organizáciu</h3>
            <p className="text-xs text-slate-400 mb-4">
              Zadajte názov nového tímu alebo pracovného priestoru.
            </p>
            <form onSubmit={handleCreate} className="space-y-4">
              <input
                type="text"
                required
                value={newOrgName}
                onChange={(e) => setNewOrgName(e.target.value)}
                placeholder="Napr. CyberGuard Security s.r.o."
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-sky-500"
              />
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-3 py-1.5 text-xs text-slate-400 hover:text-white"
                >
                  Zrušiť
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="px-4 py-1.5 text-xs font-semibold bg-sky-500 hover:bg-sky-400 text-white rounded-lg transition disabled:opacity-50"
                >
                  {loading ? "Vytváram..." : "Vytvoriť"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
