import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { CompliancePanel } from "../components/CompliancePanel";
import type { AppCompliance } from "./api";

vi.mock("./api", () => ({
  api: {
    getAppCompliance: vi.fn(),
    getReportHtmlUrl: (appId: string) => `/api/apps/${appId}/report/html`,
  },
}));

function renderReport(hasVerifiedTarget: boolean, observations = 0) {
  const client = new QueryClient();
  const response: AppCompliance = {
    app_id: "fixture-app",
    scoring: { score: 100, grade: "A+", open_counts: { total: observations } },
    nis2_readiness: [{ id: "availability", name: "Dostupnosť", iso_ref: "ISO/IEC 27001:2022 A.8.16", status: "COMPLIANT", issues_count: observations }],
  };
  client.setQueryData(["app-compliance", "fixture-app"], response);
  const html = renderToStaticMarkup(createElement(QueryClientProvider, { client },
    createElement(CompliancePanel, { appId: "fixture-app", hasVerifiedTarget })));
  client.clear();
  return html;
}

describe("Technical audit evidence", () => {
  it.each([true, false])("never claims A+ or compliance from an old server (verified: %s)", (verified) => {
    const html = renderReport(verified);
    expect(html).toContain("Zhoda neposúdená — nedostatok dôkazov");
    expect(html).toContain("Nepotvrdzujú zhodu s NIS2 ani ISO 27001");
    expect(html).not.toContain("A+");
    expect(html).not.toContain("100 %");
    expect(html).not.toContain("COMPLIANT");
    expect(html.includes("nemá overený target")).toBe(!verified);
    expect(html).toContain('/api/apps/fixture-app/report/html');
  });

  it("preserves actual technical observations", () => {
    const html = renderReport(true, 3);
    expect(html).toContain("3 otvorených nálezov");
    expect(html).toContain("3 technických pozorovaní; zhoda neposúdená");
  });
});
