import React from "react";
import { Link } from "@tanstack/react-router";

export function UpgradeModal({
  isOpen,
  onClose,
  title = "Vyžaduje sa vyšší plán",
  message = "Táto funkcia alebo kvóta nie je dostupná vo vašom aktuálnom pláne.",
}: {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  message?: string;
}) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-sky-500/30 rounded-2xl p-6 max-w-md w-full shadow-2xl text-center space-y-4">
        <div className="w-12 h-12 rounded-full bg-sky-500/10 border border-sky-500/20 text-sky-400 flex items-center justify-center mx-auto text-xl">
          ⚡
        </div>
        <div>
          <h3 className="text-lg font-bold text-white">{title}</h3>
          <p className="text-sm text-slate-300 mt-2">{message}</p>
        </div>
        <div className="flex gap-3 justify-center pt-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-xs text-slate-400 hover:text-white"
          >
            Neskôr
          </button>
          <Link
            to="/billing"
            onClick={onClose}
            className="px-5 py-2 text-xs font-semibold bg-sky-500 hover:bg-sky-400 text-white rounded-lg transition shadow-lg shadow-sky-500/20"
          >
            Prejsť na predplatné
          </Link>
        </div>
      </div>
    </div>
  );
}
