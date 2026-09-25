export type User = { id: string; email: string };

export type Target = {
  id: string;
  app_id: string;
  host: string;
  status: "pending" | "verified" | "disabled";
  verify_token: string;
  verify_method: string | null;
  trusted_private: boolean;
  created_at: string;
  verified_at: string | null;
};

export type ScanProfile =
  | "heartbeat"
  | "tls"
  | "http"
  | "safe"
  | "internetdb"
  | "subdomain"
  | "ports"
  | "trivy_fs"
  | "trivy_image"
  | "gitleaks";

export type AppItem = {
  id: string;
  name: string;
  environment: string;
  base_url: string;
  heartbeat_enabled: boolean;
  tls_enabled: boolean;
  http_enabled: boolean;
  safe_enabled: boolean;
  internetdb_enabled: boolean;
  subdomain_enabled: boolean;
  ports_enabled: boolean;
  trivy_enabled: boolean;
  gitleaks_enabled: boolean;
  git_url: string | null;
  image_ref: string | null;
  last_status_code: number | null;
  last_latency_ms: number | null;
  last_title: string | null;
  last_up: boolean | null;
  last_checked_at: string | null;
  created_at: string;
  targets: Target[];
};

export type Run = {
  id: string;
  app_id: string;
  profile: ScanProfile;
  status: "queued" | "running" | "done" | "failed";
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
};

export type Finding = {
  id: string;
  app_id: string;
  target_id: string | null;
  source: string;
  severity: "info" | "low" | "medium" | "high" | "critical";
  title: string;
  detail: string | null;
  fingerprint: string;
  status: "open" | "accepted" | "fixed";
  first_seen_at: string;
  last_seen_at: string;
  closed_at: string | null;
};

export type Overview = {
  apps: Array<{
    id: string;
    name: string;
    environment: string;
    last_up: boolean | null;
    last_status_code: number | null;
    last_latency_ms: number | null;
    last_checked_at: string | null;
    open_findings: number;
  }>;
  open_by_severity: Record<string, number>;
  certs_expiring_soon: number;
  running_scans: number;
};

const API_BASE_URL = (import.meta.env.VITE_API_URL || "").replace(/\/+$/, "");

export function buildApiUrl(path: string): string {
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  return API_BASE_URL ? `${API_BASE_URL}${cleanPath}` : cleanPath;
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = buildApiUrl(path);

  const res = await fetch(url, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "XMLHttpRequest",
      ...(init?.headers || {}),
    },
    ...init,
  });

  if (res.status === 204) {
    return undefined as T;
  }

  if (res.status === 401 && !path.includes("/auth/login") && !path.includes("/auth/me")) {
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("straz:unauthorized"));
    }
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = data.detail || JSON.stringify(data);
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }

  return res.json() as Promise<T>;
}

export const api = {
  me: () => request<User>("/api/auth/me"),
  login: (email: string, password: string) =>
    request<User>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),
  changePassword: (old_password: string, new_password: string) =>
    request<User>("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify({ old_password, new_password }),
    }),
  overview: () => request<Overview>("/api/overview"),
  apps: (params?: { limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.offset) q.set("offset", String(params.offset));
    const qs = q.toString();
    return request<AppItem[]>(`/api/apps${qs ? `?${qs}` : ""}`);
  },
  app: (id: string) => request<AppItem>(`/api/apps/${id}`),
  createApp: (body: {
    name: string;
    environment: string;
    base_url: string;
    git_url?: string | null;
    image_ref?: string | null;
  }) =>
    request<AppItem>("/api/apps", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateApp: (
    id: string,
    body: Partial<{
      name: string;
      environment: string;
      base_url: string;
      git_url: string | null;
      image_ref: string | null;
      heartbeat_enabled: boolean;
      tls_enabled: boolean;
      http_enabled: boolean;
      safe_enabled: boolean;
      internetdb_enabled: boolean;
      subdomain_enabled: boolean;
      ports_enabled: boolean;
      trivy_enabled: boolean;
      gitleaks_enabled: boolean;
    }>,
  ) =>
    request<AppItem>(`/api/apps/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deleteApp: (id: string) => request<void>(`/api/apps/${id}`, { method: "DELETE" }),
  addTarget: (appId: string, host: string) =>
    request<Target>(`/api/apps/${appId}/targets`, {
      method: "POST",
      body: JSON.stringify({ host }),
    }),
  verifyTarget: (id: string) =>
    request<Target>(`/api/targets/${id}/verify`, { method: "POST" }),
  trustPrivate: (id: string) =>
    request<Target>(`/api/targets/${id}/trust-private`, {
      method: "POST",
      body: JSON.stringify({ confirm: true }),
    }),
  runs: (params?: { appId?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    if (params?.appId) q.set("app_id", params.appId);
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.offset) q.set("offset", String(params.offset));
    const qs = q.toString();
    return request<Run[]>(`/api/runs${qs ? `?${qs}` : ""}`);
  },
  run: (id: string) => request<Run>(`/api/runs/${id}`),
  createRun: (appId: string, profile: ScanProfile) =>
    request<Run>(`/api/apps/${appId}/runs`, {
      method: "POST",
      body: JSON.stringify({ profile }),
    }),
  findings: (params?: { status?: string; app_id?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set("status_filter", params.status);
    if (params?.app_id) q.set("app_id", params.app_id);
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.offset) q.set("offset", String(params.offset));
    const qs = q.toString();
    return request<Finding[]>(`/api/findings${qs ? `?${qs}` : ""}`);
  },
  updateFinding: (id: string, status: Finding["status"]) =>
    request<Finding>(`/api/findings/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  reportClientError: (error: unknown, info?: unknown) =>
    request<void>("/api/client-errors", {
      method: "POST",
      body: JSON.stringify({
        message: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined,
        info: info ? String(info) : undefined,
        url: typeof window !== "undefined" ? window.location.href : undefined,
      }),
    }).catch(() => {
      /* ignore reporting failures */
    }),
};
