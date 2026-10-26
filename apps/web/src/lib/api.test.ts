import { afterEach, describe, expect, it, vi } from "vitest";
import { api, request, setActiveOrgId } from "./api";
import { formatDate, formatLatency, formatTimeAgo } from "./format";

describe("API Helper Utilities", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it.each([
    { baseUrl: "", expected: "/api/apps" },
    { baseUrl: "https://api.straz.example.com", expected: "https://api.straz.example.com/api/apps" },
    { baseUrl: "https://api.straz.example.com///", expected: "https://api.straz.example.com/api/apps" },
  ])("builds API URLs with VITE_API_URL='$baseUrl'", async ({ baseUrl, expected }) => {
    // API_BASE_URL is captured at import time: load it after setting the environment.
    vi.stubEnv("VITE_API_URL", baseUrl);
    vi.resetModules();
    const { buildApiUrl } = await import("./api");
    expect(buildApiUrl("/api/apps")).toBe(expected);
    expect(buildApiUrl("api/apps")).toBe(expected);
  });
});

describe("Tenant request boundaries", () => {
  afterEach(() => {
    setActiveOrgId(null);
    vi.unstubAllGlobals();
  });

  it("preserves tenant and CSRF headers when caller supplies Headers", async () => {
    setActiveOrgId("local-org");
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await request("/api/apps", { headers: new Headers({ "X-Test": "local" }) });
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    const headers = new Headers(init.headers);
    expect(headers.get("X-Organization-Id")).toBe("local-org");
    expect(headers.get("X-Requested-With")).toBe("XMLHttpRequest");
    expect(headers.get("X-Test")).toBe("local");
    expect(init.cache).toBe("no-store");
    expect(init.credentials).toBe("include");
  });

  it("carries the selected tenant in report navigation", () => {
    setActiveOrgId("selected-org");
    expect(api.getReportHtmlUrl("local-app")).toContain("organization_id=selected-org");
    expect(api.exportAuditCsvUrl("selected-org")).toContain("organization_id=selected-org");
  });
});

describe("Formatting Utilities", () => {
  it("formats latency values cleanly", () => {
    expect(formatLatency(null)).toBe("—");
    expect(formatLatency(undefined)).toBe("—");
    expect(formatLatency(45.2)).toBe("45 ms");
    expect(formatLatency(1250)).toBe("1.25 s");
  });

  it("formats dates gracefully", () => {
    expect(formatDate(null)).toBe("—");
    const d = new Date("2026-09-25T12:00:00Z").toISOString();
    expect(formatDate(d)).toContain("25");
  });

  it("formats time ago strings in Slovak", () => {
    expect(formatTimeAgo(null)).toBe("—");
    const now = new Date().toISOString();
    expect(formatTimeAgo(now)).toBe("práve teraz");
  });
});
