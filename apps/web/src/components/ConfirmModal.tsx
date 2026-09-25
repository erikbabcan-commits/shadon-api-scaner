import React, { useEffect, useState } from "react";

interface ConfirmModalProps {
  isOpen: boolean;
  title: string;
  message: string;
  confirmWord?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  isDestructive?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export const ConfirmModal: React.FC<ConfirmModalProps> = ({
  isOpen,
  title,
  message,
  confirmWord,
  confirmLabel = "Potvrdiť",
  cancelLabel = "Zrušiť",
  isDestructive = false,
  onConfirm,
  onCancel,
}) => {
  const [typedWord, setTypedWord] = useState("");

  useEffect(() => {
    if (isOpen) {
      setTypedWord("");
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const isConfirmed = confirmWord ? typedWord.trim() === confirmWord.trim() : true;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in"
    >
      <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4">
        <div className="flex items-start gap-3.5">
          {isDestructive && (
            <div className="p-2.5 rounded-xl bg-rose-500/10 text-rose-400 border border-rose-500/20 shrink-0">
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
              </svg>
            </div>
          )}
          <div>
            <h3 id="confirm-modal-title" className="text-lg font-semibold text-slate-100">
              {title}
            </h3>
            <p className="text-sm text-slate-400 mt-1 leading-relaxed">
              {message}
            </p>
          </div>
        </div>

        {confirmWord && (
          <div className="space-y-2 pt-1">
            <label className="text-xs text-slate-400 block font-medium">
              Pre potvrdenie napíšte <span className="font-mono text-slate-200 select-all font-bold">"{confirmWord}"</span>:
            </label>
            <input
              type="text"
              value={typedWord}
              onChange={(e) => setTypedWord(e.target.value)}
              placeholder={confirmWord}
              autoFocus
              className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-rose-500/50"
            />
          </div>
        )}

        <div className="flex justify-end gap-3 pt-3 border-t border-slate-800/80">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white transition"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            disabled={!isConfirmed}
            onClick={onConfirm}
            className={`px-4 py-2 text-sm font-medium rounded-lg transition disabled:opacity-40 disabled:cursor-not-allowed ${
              isDestructive
                ? "bg-rose-600 text-white hover:bg-rose-500 shadow-sm shadow-rose-950"
                : "bg-sky-600 text-white hover:bg-sky-500 shadow-sm shadow-sky-950"
            }`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
};
