import React, { useState } from "react";
import type { AppItem } from "../lib/api";

interface CiCodeGeneratorProps {
  apps: AppItem[];
}

export const CiCodeGenerator: React.FC<CiCodeGeneratorProps> = ({ apps }) => {
  const [activeTab, setActiveTab] = useState<"github" | "gitlab" | "curl">("github");
  const [selectedAppId, setSelectedAppId] = useState<string>(apps[0]?.id || "<APP_ID>");
  const [failOn, setFailOn] = useState<"critical" | "high" | "medium">("high");
  const [profile, setProfile] = useState<string>("safe");
  const [copied, setCopied] = useState(false);

  const currentOrigin = typeof window !== "undefined" ? window.location.origin : "https://app.straz.sk";

  const getGitHubCode = () => {
    return `# .github/workflows/straz-security.yml
name: Stráž DevSecOps Gate
on:
  push:
    branches: [main, master, develop]
  pull_request:
    branches: [main, master]

jobs:
  security-gate:
    name: Automated Security Gate
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Source Code
        uses: actions/checkout@v4

      - name: Execute Stráž Security Gate
        env:
          STRAZ_API_KEY: \${{ secrets.STRAZ_API_KEY }}
          STRAZ_API_URL: \${{ secrets.STRAZ_API_URL || '${currentOrigin}' }}
        run: |
          echo "🚀 Spúšťam bezpečnostnú kontrolu Stráž pre aplikáciu..."
          RESPONSE=\$(curl -s -X POST "\$STRAZ_API_URL/api/ci/scan" \\
            -H "Authorization: Bearer \$STRAZ_API_KEY" \\
            -H "Content-Type: application/json" \\
            -d '{
              "app_id": "${selectedAppId}",
              "profile": "${profile}",
              "fail_on": "${failOn}",
              "wait": true,
              "timeout_seconds": 180
            }')

          echo "Výsledok analýzy:"
          echo "\$RESPONSE" | jq .

          PASSED=\$(echo "\$RESPONSE" | jq -r '.passed // false')
          if [ "\$PASSED" != "true" ]; then
            REASON=\$(echo "\$RESPONSE" | jq -r '.failure_reason // "Nájdené zraniteľnosti prekračujúce prah"')
            echo "❌ Bezpečnostná brána zlyhala: \$REASON"
            exit 1
          fi

          echo "✅ Bezpečnostná brána úspešne schválila nasadenie!"`;
  };

  const getGitLabCode = () => {
    return `# .gitlab-ci.yml
stages:
  - test
  - security

straz-security-gate:
  stage: security
  image: curlimages/curl:latest
  before_script:
    - apk add --no-cache jq
  script:
    - |
      echo "🚀 Spúšťam Stráž Security Gate..."
      RESPONSE=\$(curl -s -X POST "\${STRAZ_API_URL:-${currentOrigin}}/api/ci/scan" \\
        -H "Authorization: Bearer \$STRAZ_API_KEY" \\
        -H "Content-Type: application/json" \\
        -d '{
          "app_id": "${selectedAppId}",
          "profile": "${profile}",
          "fail_on": "${failOn}",
          "wait": true
        }')
      echo "\$RESPONSE" | jq .
      echo "\$RESPONSE" | jq -e '.passed == true' > /dev/null || (echo "❌ Zlyhanie bezpečnostnej brány!" && exit 1)
  rules:
    - if: '\$CI_PIPELINE_SOURCE == "merge_request_event"'
    - if: '\$CI_COMMIT_BRANCH == "main"'`;
  };

  const getCurlCode = () => {
    return `curl -s -X POST "${currentOrigin}/api/ci/scan" \\
  -H "Authorization: Bearer \$STRAZ_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "app_id": "${selectedAppId}",
    "profile": "${profile}",
    "fail_on": "${failOn}",
    "wait": true
  }' | jq .`;
  };

  const getCode = () => {
    if (activeTab === "github") return getGitHubCode();
    if (activeTab === "gitlab") return getGitLabCode();
    return getCurlCode();
  };

  const copyToClipboard = () => {
    navigator.clipboard.writeText(getCode());
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
      <div className="p-5 border-b border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h3 className="text-base font-semibold text-white flex items-center gap-2">
            <svg className="w-5 h-5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
            </svg>
            Interaktívny CI/CD Integrátor
          </h3>
          <p className="text-xs text-slate-400 mt-1">
            Zastavte deployment pri náleze bezpečnostných chýb v GitHub Actions alebo GitLab CI.
          </p>
        </div>

        {/* Tab selection */}
        <div className="flex bg-slate-800 p-1 rounded-lg">
          <button
            onClick={() => setActiveTab("github")}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all flex items-center gap-1.5 ${
              activeTab === "github" ? "bg-emerald-600 text-white" : "text-slate-400 hover:text-white"
            }`}
          >
            GitHub Actions
          </button>
          <button
            onClick={() => setActiveTab("gitlab")}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all flex items-center gap-1.5 ${
              activeTab === "gitlab" ? "bg-emerald-600 text-white" : "text-slate-400 hover:text-white"
            }`}
          >
            GitLab CI
          </button>
          <button
            onClick={() => setActiveTab("curl")}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all flex items-center gap-1.5 ${
              activeTab === "curl" ? "bg-emerald-600 text-white" : "text-slate-400 hover:text-white"
            }`}
          >
            cURL / Shell
          </button>
        </div>
      </div>

      {/* Selectors Bar */}
      <div className="p-4 bg-slate-950/60 border-b border-slate-800/80 grid grid-cols-1 md:grid-cols-3 gap-3">
        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1">Cieľová aplikácia</label>
          <select
            value={selectedAppId}
            onChange={(e) => setSelectedAppId(e.target.value)}
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
          >
            {apps.length === 0 ? (
              <option value="<APP_ID>">Žiadne aplikácie</option>
            ) : (
              apps.map((app) => (
                <option key={app.id} value={app.id}>
                  {app.name} ({app.id.substring(0, 8)}...)
                </option>
              ))
            )}
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1">Bezpečnostný profil</label>
          <select
            value={profile}
            onChange={(e) => setProfile(e.target.value)}
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
          >
            <option value="safe">Safe (Rýchly & Bezpečný sken)</option>
            <option value="tls">TLS & SSL Kontrola certifikátov</option>
            <option value="http">HTTP Bezpečnostné hlavičky</option>
            <option value="heartbeat">Heartbeat / Liveness</option>
            <option value="gitleaks">GitLeaks (Detekcia uniknutých kľúčov)</option>
            <option value="trivy_fs">Trivy Filesystem (CVE závislosti)</option>
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1">Zlyhať pipeline pri (Threshold)</label>
          <select
            value={failOn}
            onChange={(e) => setFailOn(e.target.value as any)}
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
          >
            <option value="critical">Zlyhať iba pri CRITICAL</option>
            <option value="high">Zlyhať pri HIGH a CRITICAL (Odporúčané)</option>
            <option value="medium">Zlyhať pri MEDIUM, HIGH a CRITICAL</option>
          </select>
        </div>
      </div>

      {/* Code Viewer */}
      <div className="relative p-4 font-mono text-xs bg-slate-950 text-slate-300 overflow-x-auto">
        <button
          onClick={copyToClipboard}
          className="absolute top-3 right-3 flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white rounded-md text-xs transition border border-slate-700 shadow"
        >
          {copied ? (
            <span className="text-emerald-400">Skopírované!</span>
          ) : (
            <span>Kopírovať</span>
          )}
        </button>
        <pre className="whitespace-pre overflow-x-auto py-2 leading-relaxed">{getCode()}</pre>
      </div>
    </div>
  );
};
