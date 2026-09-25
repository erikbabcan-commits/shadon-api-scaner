import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "@tanstack/react-router";
import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";
import { AppShell } from "@/components/AppShell";
import { ConfirmModal } from "@/components/ConfirmModal";
import { SkeletonCard, SkeletonTable } from "@/components/Skeleton";
import { api, type AppItem, type ScanProfile, type Target } from "@/lib/api";
import { formatLatency, formatTimeAgo } from "@/lib/format";
import { toast } from "@/lib/toast";
import { useOnline } from "@/lib/useOnline";

const SCAN_BUTTONS: Array<[ScanProfile, string, boolean]> = [
  ["heartbeat", "Heartbeat", false],
  ["tls", "TLS", true],
  ["http", "HTTP", true],
  ["safe", "Nuclei safe", true],
  ["internetdb", "InternetDB", true],
  ["subdomain", "Subfinder", true],
  ["ports", "Naabu ports", true],
  ["trivy_fs", "Trivy fs", true],
  ["trivy_image", "Trivy image", true],
  ["gitleaks", "Gitleaks", true],
];

// --- 1. Header Component ---
interface AppHeaderProps {
  app: AppItem;
}

function AppHeader({ app }: AppHeaderProps) {
  const isOnline = app.last_up === true;
  const isOffline = app.last_up === false;

  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5 rounded-2xl bg-slate-900/60 border border-slate-800">
      <div className="space-y-1">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-slate-100">{app.name}</h1>
          <span className="text-xs uppercase font-mono px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-300">
            {app.environment}
          </span>
        </div>
        <a
          href={app.base_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-sky-400 hover:underline flex items-center gap-1"
        >
          {app.base_url}
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
            />
          </svg>
        </a>
      </div>

      <div className="flex items-center gap-3 text-xs">
        <div className="px-3 py-1.5 rounded-xl bg-slate-950/80 border border-slate-800">
          <span className="text-slate-400 block text-[10px] uppercase font-medium">Stav</span>
          <span
            className={
              isOnline
                ? "text-emerald-400 font-semibold"
                : isOffline
                ? "text-rose-400 font-semibold"
                : "text-slate-400 font-semibold"
            }
          >
            {isOnline ? "ONLINE" : isOffline ? "OFFLINE" : "NEZNÁMY"}
          </span>
        </div>
        <div className="px-3 py-1.5 rounded-xl bg-slate-950/80 border border-slate-800">
          <span className="text-slate-400 block text-[10px] uppercase font-medium">Latencia</span>
          <span className="text-slate-200 font-medium font-mono">
            {formatLatency(app.last_latency_ms)}
          </span>
        </div>
        <div className="px-3 py-1.5 rounded-xl bg-slate-950/80 border border-slate-800">
          <span className="text-slate-400 block text-[10px] uppercase font-medium">
            Posledná kontrola
          </span>
          <span className="text-slate-300 font-medium">
            {formatTimeAgo(app.last_checked_at)}
          </span>
        </div>
      </div>
    </div>
  );
}

// --- 2. Security Scans Launcher ---
interface AppScansSectionProps {
  appId: string;
  hasVerified: boolean;
  online: boolean;
  onInvalidate: () => Promise<void>;
}

function AppScansSection({ appId, hasVerified, online, onInvalidate }: AppScansSectionProps) {
  const runScan = useMutation({
    mutationFn: (profile: ScanProfile) => api.createRun(appId, profile),
    onSuccess: async (_, profile) => {
      toast.success(`Scan "${profile}" bol úspešne zaradený do fronty`);
      await onInvalidate();
    },
    onError: (e: Error) => toast.error(e.message || "Spustenie scanu zlyhalo"),
  });

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-5 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-slate-200">Bezpečnostné skeny</h2>
        {!hasVerified && (
          <span className="text-xs text-amber-400 flex items-center gap-1">
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
            Vyžaduje aspoň 1 overený target
          </span>
        )}
      </div>

      <div className="flex flex-wrap gap-2 pt-1">
        {SCAN_BUTTONS.map(([profile, label, needsVerified]) => {
          const disabled = !online || runScan.isPending || (needsVerified && !hasVerified);
          return (
            <button
              key={profile}
              disabled={disabled}
              onClick={() => runScan.mutate(profile)}
              title={needsVerified && !hasVerified ? "Najprv overte target" : undefined}
              className="px-3 py-1.5 rounded-xl text-xs font-medium border border-slate-700/60 bg-slate-800/80 hover:bg-slate-700 text-slate-200 transition disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-sky-400" />
              {label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// --- 3. Supply Chain Settings Component ---
interface AppSupplyChainProps {
  appId: string;
  initialGitUrl: string | null;
  initialImageRef: string | null;
  online: boolean;
  onInvalidate: () => Promise<void>;
}

function AppSupplyChainSection({
  appId,
  initialGitUrl,
  initialImageRef,
  online,
  onInvalidate,
}: AppSupplyChainProps) {
  const [gitUrl, setGitUrl] = useState(initialGitUrl ?? "");
  const [imageRef, setImageRef] = useState(initialImageRef ?? "");

  useEffect(() => {
    setGitUrl(initialGitUrl ?? "");
    setImageRef(initialImageRef ?? "");
  }, [initialGitUrl, initialImageRef]);

  const saveMeta = useMutation({
    mutationFn: () =>
      api.updateApp(appId, {
        git_url: gitUrl.trim() || null,
        image_ref: imageRef.trim() || null,
      }),
    onSuccess: async () => {
      toast.success("Metadáta aplikácie boli uložené");
      await onInvalidate();
    },
    onError: (e: Error) => toast.error(e.message || "Uloženie zlyhalo"),
  });

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-5 space-y-4">
      <div>
        <h2 className="text-base font-semibold text-slate-200">Supply Chain nastavenia</h2>
        <p className="text-xs text-slate-400 mt-0.5">
          Git repozitár a Docker image pre statickú a kontajnerovú analýzu zraniteľností
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="space-y-1">
          <label className="text-xs font-medium text-slate-400 block">
            Git URL (pre Trivy fs / Gitleaks)
          </label>
          <input
            className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500/50"
            placeholder="https://github.com/..."
            value={gitUrl}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setGitUrl(e.target.value)}
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium text-slate-400 block">
            Docker Image Ref (pre Trivy image)
          </label>
          <input
            className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500/50"
            placeholder="registry.example.com/app:tag"
            value={imageRef}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setImageRef(e.target.value)}
          />
        </div>
      </div>

      <div className="flex justify-end">
        <button
          type="button"
          disabled={!online || saveMeta.isPending}
          onClick={() => saveMeta.mutate()}
          className="px-4 py-2 text-xs font-medium rounded-xl bg-sky-600 hover:bg-sky-500 text-white shadow-sm transition disabled:opacity-50"
        >
          {saveMeta.isPending ? "Ukladám…" : "Uložiť zmeny"}
        </button>
      </div>
    </div>
  );
}

// --- 4. Targets Management Component ---
interface AppTargetsProps {
  appId: string;
  targets: Target[];
  online: boolean;
  onInvalidate: () => Promise<void>;
}

function AppTargetsSection({ appId, targets, online, onInvalidate }: AppTargetsProps) {
  const [host, setHost] = useState("");

  const addTarget = useMutation({
    mutationFn: () => api.addTarget(appId, host),
    onSuccess: async () => {
      setHost("");
      toast.success("Target bol úspešne pridaný");
      await onInvalidate();
    },
    onError: (e: Error) => toast.error(e.message || "Nepodarilo sa pridať target"),
  });

  const verify = useMutation({
    mutationFn: (id: string) => api.verifyTarget(id),
    onSuccess: async () => {
      toast.success("Target bol úspešne overený!");
      await onInvalidate();
    },
    onError: (e: Error) => toast.error(e.message || "Overenie zlyhalo"),
  });

  const trust = useMutation({
    mutationFn: (id: string) => api.trustPrivate(id),
    onSuccess: async () => {
      toast.success("Target bol označený ako dôveryhodná privátna sieť");
      await onInvalidate();
    },
    onError: (e: Error) => toast.error(e.message || "Nastavenie zlyhalo"),
  });

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    toast.info("DNS záznam skopírovaný do schránky");
  };

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-5 space-y-4">
      <div>
        <h2 className="text-base font-semibold text-slate-200">Targety a domény</h2>
        <p className="text-xs text-slate-400 mt-0.5">
          Overené sieťové ciele, na ktoré je povolené spúšťať bezpečnostné testy
        </p>
      </div>

      <div className="divide-y divide-slate-800/80 rounded-xl border border-slate-800/80 overflow-hidden bg-slate-950/40">
        {targets.length === 0 ? (
          <div className="p-4 text-xs text-slate-400 text-center">
            Zatiaľ nie sú pridané žiadne targety. Pridajte prvú doménu alebo IP adresu nižšie.
          </div>
        ) : (
          targets.map((t) => (
            <div key={t.id} className="p-4 space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 font-mono text-sm text-slate-200 font-semibold">
                  {t.host}
                </div>
                <span
                  className={`text-xs px-2.5 py-0.5 rounded-full font-medium border ${
                    t.status === "verified"
                      ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                      : "bg-amber-500/10 text-amber-400 border-amber-500/30"
                  }`}
                >
                  {t.status === "verified" ? "Overený" : "Čaká na overenie"}
                </span>
              </div>

              {t.status !== "verified" && (
                <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 text-xs text-slate-400 space-y-2">
                  <div className="flex items-center justify-between">
                    <span>Pre overenie vlastníctva pridajte DNS TXT záznam:</span>
                    <button
                      type="button"
                      onClick={() => handleCopy(`straz-verify=${t.verify_token}`)}
                      className="text-sky-400 hover:text-sky-300 font-medium"
                    >
                      Kopírovať
                    </button>
                  </div>
                  <div className="font-mono text-xs select-all text-sky-300 bg-slate-950 p-2 rounded border border-slate-800">
                    straz-verify={t.verify_token}
                  </div>
                  <div className="flex gap-2 pt-1">
                    <button
                      disabled={!online || verify.isPending}
                      onClick={() => verify.mutate(t.id)}
                      className="px-3 py-1.5 text-xs font-medium rounded-lg bg-sky-600 hover:bg-sky-500 text-white transition disabled:opacity-50"
                    >
                      {verify.isPending ? "Overujem…" : "Overiť teraz"}
                    </button>
                    <button
                      disabled={!online || trust.isPending}
                      onClick={() => trust.mutate(t.id)}
                      className="px-3 py-1.5 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition disabled:opacity-50"
                    >
                      Trust Private (LAN/VPN)
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))
        )}
      </div>

      <form
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          if (host.trim()) addTarget.mutate();
        }}
        className="flex gap-2 pt-2"
      >
        <input
          required
          placeholder="Ďalší host alebo subdoména (napr. api.example.com)"
          value={host}
          onChange={(e: ChangeEvent<HTMLInputElement>) => setHost(e.target.value)}
          className="flex-1 px-3.5 py-2 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500/50"
        />
        <button
          type="submit"
          disabled={!online || addTarget.isPending}
          className="px-4 py-2 text-xs font-medium rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700/60 transition disabled:opacity-50"
        >
          {addTarget.isPending ? "Pridávam…" : "Pridať target"}
        </button>
      </form>
    </div>
  );
}

// --- 5. Danger Zone Component ---
interface AppDangerZoneProps {
  onOpenDelete: () => void;
}

function AppDangerZone({ onOpenDelete }: AppDangerZoneProps) {
  return (
    <div className="rounded-2xl border border-rose-950/40 bg-rose-950/10 p-5 flex items-center justify-between">
      <div>
        <h3 className="text-sm font-semibold text-rose-300">Zmazať aplikáciu</h3>
        <p className="text-xs text-rose-400/80 mt-0.5">
          Odstráni aplikáciu, všetky priradené targety, zistené nálezy a históriu scanov.
        </p>
      </div>
      <button
        type="button"
        onClick={onOpenDelete}
        className="px-4 py-2 text-xs font-semibold rounded-xl bg-rose-600/20 hover:bg-rose-600 text-rose-300 hover:text-white border border-rose-500/30 transition shadow-sm"
      >
        Zmazať aplikáciu…
      </button>
    </div>
  );
}

// --- 6. Main Orchestrating Page Component ---
export function AppDetailPage() {
  const params = useParams({ strict: false }) as { appId?: string };
  const appId = params.appId ?? "";
  const qc = useQueryClient();
  const online = useOnline();
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);

  const appQuery = useQuery({
    queryKey: ["app", appId],
    queryFn: () => api.app(appId),
    enabled: Boolean(appId),
  });

  const invalidate = async () => {
    await qc.invalidateQueries({ queryKey: ["app", appId] });
    await qc.invalidateQueries({ queryKey: ["apps"] });
    await qc.invalidateQueries({ queryKey: ["overview"] });
    await qc.invalidateQueries({ queryKey: ["runs"] });
    await qc.invalidateQueries({ queryKey: ["findings"] });
  };

  const deleteMutation = useMutation({
    mutationFn: () => api.deleteApp(appId),
    onSuccess: async () => {
      toast.info("Aplikácia bola zmazaná");
      await qc.invalidateQueries({ queryKey: ["apps"] });
      window.location.href = "/apps";
    },
    onError: (e: Error) => toast.error(e.message || "Zmazanie zlyhalo"),
  });

  const app = appQuery.data;
  const hasVerified = app?.targets.some((t) => t.status === "verified") ?? false;

  return (
    <AppShell>
      <div className="space-y-6">
        <Link
          to="/apps"
          className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-400 hover:text-sky-400 transition"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
          Späť na Aplikácie
        </Link>

        {appQuery.isLoading && (
          <div className="space-y-4">
            <SkeletonCard />
            <SkeletonTable rows={3} />
          </div>
        )}

        {appQuery.isError && (
          <div className="p-6 rounded-2xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-sm">
            Nepodarilo sa načítať aplikáciu. Skontrolujte svoje internetové pripojenie alebo platnosť ID.
          </div>
        )}

        {app && (
          <>
            <AppHeader app={app} />

            <AppScansSection
              appId={appId}
              hasVerified={hasVerified}
              online={online}
              onInvalidate={invalidate}
            />

            <AppSupplyChainSection
              appId={appId}
              initialGitUrl={app.git_url}
              initialImageRef={app.image_ref}
              online={online}
              onInvalidate={invalidate}
            />

            <AppTargetsSection
              appId={appId}
              targets={app.targets}
              online={online}
              onInvalidate={invalidate}
            />

            <AppDangerZone onOpenDelete={() => setIsDeleteModalOpen(true)} />

            <ConfirmModal
              isOpen={isDeleteModalOpen}
              title={`Zmazať aplikáciu "${app.name}"?`}
              message="Táto akcia je nezvratná. Budú trvalo odstránené všetky pridružené targety, história scanov a evidované nálezy."
              confirmWord={app.name}
              confirmLabel="Trvalo zmazať"
              isDestructive
              onConfirm={() => {
                setIsDeleteModalOpen(false);
                deleteMutation.mutate();
              }}
              onCancel={() => setIsDeleteModalOpen(false)}
            />
          </>
        )}
      </div>
    </AppShell>
  );
}
