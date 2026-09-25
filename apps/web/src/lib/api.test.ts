import { describe, expect, it } from "vitest";
import { buildApiUrl } from "./api";
import { formatDate, formatLatency, formatTimeAgo } from "./format";

describe("API Helper Utilities", () => {
  it("builds API URL correctly with paths", () => {
    expect(buildApiUrl("/api/apps")).toBe("/api/apps");
    expect(buildApiUrl("api/auth/me")).toBe("/api/auth/me");
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
