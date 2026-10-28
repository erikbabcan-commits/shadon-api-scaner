import { useState } from "react";
import { api } from "@/lib/api";
import { toast } from "@/lib/toast";

interface PoCViewerProps {
  pocCommand?: string | null;
  remediationPatch?: string | null;
  findingId?: string;
}

export function PoCViewer({
  pocCommand,
  remediationPatch,
  findingId,
}: PoCViewerProps) {
  const [copiedCmd, setCopiedCmd] = useState(false);
  const [copiedPatch, setCopiedPatch] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const [verificationResult, setVerificationResult] = useState<{
    verified: boolean;
    statusCode: number | null;
    executionTimeMs: number;
    output: string;
  } | null>(null);

  if (!pocCommand && !remediationPatch) {
    return null;
  }

  const handleCopyCommand = async () => {
    if (!pocCommand) return;
    try {
      await navigator.clipboard.writeText(pocCommand);
      setCopiedCmd(true);
      toast.success("Curl príkaz bol skopírovaný do schránky");
      setTimeout(() => setCopiedCmd(false), 2000);
    } catch {
      toast.error("Nepodarilo sa skopírovať príkaz");
    }
  };

  const handleCopyPatch = async () => {
    if (!remediationPatch) return;
    try {
      await navigator.clipboard.writeText(remediationPatch);
      setCopiedPatch(true);
      toast.success("Opravný patch bol skopírovaný do schránky");
      setTimeout(() => setCopiedPatch(false), 2000);
    } catch {
      toast.error("Nepodarilo sa skopírovať patch");
    }
  };

  const handleVerifyPoC = async () => {
    if (!findingId || !pocCommand) return;
    setIsVerifying(true);
    try {
      const res = await api.verifyPoc(findingId, pocCommand);
      setVerificationResult({
        verified: res.verified,
        statusCode: res.status_code,
        executionTimeMs: res.execution_time_ms,
        output: res.output,
      });
      if (res.verified) {
        toast.success("PoC reprodukcia bola úspešne overená");
      } else {
        toast.error("PoC reprodukcia zlyhala pri overení");
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Chyba pri overovaní PoC");
    } finally {
      setIsVerifying(false);
    }
  };

  return (
    <div className="space-y-4 pt-2 border-t border-slate-800/80">
      {/* PoC Curl Box */}
      {pocCommand && (
        <div className="rounded-xl bg-slate-950 border border-slate-800 overflow-hidden shadow-inner">
          <div className="flex items-center justify-between px-3.5 py-2 bg-slate-900/90 border-b border-slate-800 text-xs">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-rose-500/80"></span>
              <span className="w-2.5 h-2.5 rounded-full bg-amber-500/80"></span>
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/80"></span>
              <span className="font-semibold text-slate-300 font-mono ml-1">
                PoC Reprodukcia (curl)
              </span>
            </div>

            <div className="flex items-center gap-2">
              {findingId && (
                <button
                  type="button"
                  disabled={isVerifying}
                  onClick={handleVerifyPoC}
                  className="px-2.5 py-1 text-[11px] font-semibold rounded-lg bg-sky-950/80 hover:bg-sky-900/80 text-sky-300 border border-sky-800/60 transition disabled:opacity-50"
                >
                  {isVerifying ? "Overujem..." : "Overiť PoC"}
                </button>
              )}
              <button
                type="button"
                onClick={handleCopyCommand}
                className="px-2.5 py-1 text-[11px] font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700/60 transition"
              >
                {copiedCmd ? "Skopírované!" : "Kopírovať"}
              </button>
            </div>
          </div>

          <div className="p-3 text-xs font-mono text-emerald-300 select-all overflow-x-auto whitespace-pre-wrap break-all leading-relaxed">
            <span className="text-slate-500 select-none mr-2">$</span>
            {pocCommand}
          </div>

          {/* Verification Status Banner if verified */}
          {verificationResult && (
            <div
              className={`p-2.5 border-t text-xs font-mono flex items-center justify-between ${
                verificationResult.verified
                  ? "bg-emerald-950/20 border-emerald-900/50 text-emerald-400"
                  : "bg-rose-950/20 border-rose-900/50 text-rose-400"
              }`}
            >
              <span>
                {verificationResult.verified ? "✔ Syntax & cieľ overené" : "✖ Overenie zlyhalo"}
                {verificationResult.statusCode && ` (HTTP ${verificationResult.statusCode})`}
              </span>
              <span className="text-[11px] text-slate-400">
                {verificationResult.executionTimeMs} ms
              </span>
            </div>
          )}
        </div>
      )}

      {/* Remediation Patch Box */}
      {remediationPatch && (
        <div className="rounded-xl bg-slate-950 border border-slate-800 overflow-hidden shadow-inner">
          <div className="flex items-center justify-between px-3.5 py-2 bg-slate-900/90 border-b border-slate-800 text-xs">
            <div className="flex items-center gap-2">
              <svg className="w-4 h-4 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
              </svg>
              <span className="font-semibold text-slate-300 font-mono">
                Opravný patch (Remediation Diff)
              </span>
            </div>

            <button
              type="button"
              onClick={handleCopyPatch}
              className="px-2.5 py-1 text-[11px] font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700/60 transition"
            >
              {copiedPatch ? "Skopírované!" : "Kopírovať patch"}
            </button>
          </div>

          <div className="p-3 text-xs font-mono overflow-x-auto max-h-60 overflow-y-auto space-y-0.5 select-all">
            {remediationPatch.split("\n").map((line, idx) => {
              let lineStyle = "text-slate-400";
              if (line.startsWith("+")) {
                lineStyle = "text-emerald-300 bg-emerald-950/30 px-1 rounded-xs block";
              } else if (line.startsWith("-")) {
                lineStyle = "text-rose-400 bg-rose-950/30 px-1 rounded-xs block";
              } else if (line.startsWith("@@")) {
                lineStyle = "text-sky-400 bg-sky-950/20 px-1 rounded-xs block";
              }
              return (
                <div key={idx} className={lineStyle}>
                  {line || " "}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
