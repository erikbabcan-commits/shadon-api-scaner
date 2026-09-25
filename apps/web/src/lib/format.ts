export function formatLatency(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  if (ms >= 1000) {
    return `${(ms / 1000).toFixed(2)} s`;
  }
  return `${Math.round(ms)} ms`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return new Intl.DateTimeFormat("sk-SK", {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    }).format(d);
  } catch {
    return iso;
  }
}

export function formatTimeAgo(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    const diffSec = Math.floor((Date.now() - d.getTime()) / 1000);
    if (diffSec < 60) return "práve teraz";
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `pred ${diffMin} min`;
    const diffH = Math.floor(diffMin / 60);
    if (diffH < 24) return `pred ${diffH} hod`;
    const diffDays = Math.floor(diffH / 24);
    return `pred ${diffDays} dňami`;
  } catch {
    return iso;
  }
}
