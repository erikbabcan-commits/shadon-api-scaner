import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ScannerAvailabilityNotice } from "../components/ScannerAvailabilityNotice";
import { isScanProfileAvailable } from "./scanAvailability";
import type { ScanProfile } from "./api";

describe("Scanner availability", () => {
  it.each<ScanProfile>(["heartbeat", "internetdb"])("allows %s", (profile) => {
    expect(isScanProfileAvailable(profile)).toBe(true);
  });

  it.each<ScanProfile>(["tls", "http", "safe", "subdomain", "ports", "trivy_fs", "trivy_image", "gitleaks"])(
    "marks %s unavailable", (profile) => expect(isScanProfileAvailable(profile)).toBe(false),
  );

  it("explains the restriction to users of every plan and CI/CD", () => {
    const html = renderToStaticMarkup(createElement(ScannerAvailabilityNotice));
    expect(html).toContain('role="note"');
    expect(html).toContain("Heartbeat a InternetDB");
    expect(html).toContain("všetky plány aj CI/CD");
    expect(html).toContain("izolácie skenerov");
  });
});
