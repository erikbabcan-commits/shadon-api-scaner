import type { ScanProfile } from "./api";

const availableProfiles: ReadonlySet<ScanProfile> = new Set(["heartbeat", "internetdb"]);

export function isScanProfileAvailable(profile: ScanProfile): boolean {
  return availableProfiles.has(profile);
}

export const SCANNER_AVAILABILITY_NOTICE =
  "Aktívne profily: Heartbeat a InternetDB. TLS, HTTP, Nuclei safe, Subdomain, Ports, Trivy FS, Trivy Image a Gitleaks sú dočasne nedostupné do doplnenia izolácie skenerov. Obmedzenie platí pre všetky plány aj CI/CD.";
