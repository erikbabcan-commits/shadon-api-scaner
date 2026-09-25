import React from "react";
import { toast, useToasts } from "../lib/toast";

export const ToastContainer: React.FC = () => {
  const toasts = useToasts();

  if (toasts.length === 0) return null;

  return (
    <div
      aria-live="polite"
      aria-atomic="true"
      className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm w-full pointer-events-none px-4"
    >
      {toasts.map((t) => {
        const bgColors = {
          success: "bg-emerald-950/90 border-emerald-500/40 text-emerald-100",
          error: "bg-rose-950/90 border-rose-500/40 text-rose-100",
          warning: "bg-amber-950/90 border-amber-500/40 text-amber-100",
          info: "bg-slate-900/90 border-sky-500/40 text-slate-100",
        }[t.type];

        const iconColors = {
          success: "text-emerald-400",
          error: "text-rose-400",
          warning: "text-amber-400",
          info: "text-sky-400",
        }[t.type];

        return (
          <div
            key={t.id}
            role="alert"
            className={`pointer-events-auto flex items-start gap-3 p-3.5 rounded-xl border backdrop-blur-md shadow-lg shadow-black/40 transition-all transform translate-y-0 ${bgColors}`}
          >
            <div className={`mt-0.5 shrink-0 ${iconColors}`}>
              {t.type === "success" && (
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              )}
              {t.type === "error" && (
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              )}
              {t.type === "warning" && (
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              )}
              {t.type === "info" && (
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              )}
            </div>

            <div className="flex-1 text-sm">
              {t.title && <div className="font-semibold text-xs tracking-wider uppercase mb-0.5">{t.title}</div>}
              <div className="leading-snug">{t.message}</div>
            </div>

            <button
              onClick={() => toast.dismiss(t.id)}
              aria-label="Zatvoriť notifikáciu"
              className="text-slate-400 hover:text-white p-1 -mr-1 -mt-1 rounded-md transition"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        );
      })}
    </div>
  );
};
