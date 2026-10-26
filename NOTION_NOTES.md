# 🛡️ STRÁŽ — Kompletná Projektová Karta & Poznámky do Notion

> **Status projektu:** 🟢 100 % Dokončený, plne obnovený a otestovaný  
> **Dátum:** 26. október 2026  
> **Autor/Vlastník:** Erik Babčan  
> **GitHub repozitár:** [https://github.com/erikbabcan-commits/shadon-api-scaner](https://github.com/erikbabcan-commits/shadon-api-scaner)  
> **Produkčný Vercel:** [https://straz-monitoring.vercel.app](https://straz-monitoring.vercel.app) (Alternatíva: [https://web-flax-omega-55.vercel.app](https://web-flax-omega-55.vercel.app))  
> **Lokálna testovacia URL:** [http://localhost:5173](http://localhost:5173)  
> **Lokálna záloha (ZIP):** `/Users/vorkei/Desktop/STRAZ_COMPLETE_RECOVERED.zip`  

---

## 🔐 1. Prihlasovacie Údaje (Admin Bootstrap)

* **Admin Email:** `erikbabcan@gmail.com`
* **Admin Heslo:** `heslo`
* **Priradená organizácia:** `erikbabcan's Workspace` (Rola: `owner`)

---

## ⚙️ 2. Konfigurácia Prostredia (Všetky ENV Premenné)

### 💻 A. Lokálny Vývoj (`apps/api/.env`)
Používa sa pri lokálnom behu cez Python `uvicorn` a SQLite databázu:

```ini
# Databáza & Cache
DATABASE_URL=sqlite+aiosqlite:///./straz.db
REDIS_URL=redis://localhost:6379/0

# Bezpečnosť & Relácia
STRAZ_ADMIN_EMAIL=erikbabcan@gmail.com
STRAZ_ADMIN_PASSWORD=heslo
STRAZ_SESSION_SECRET=dev-session-secret-must-be-at-least-32-chars-long!
STRAZ_COOKIE_SECURE=false

# Prostredie & CORS
STRAZ_ENV=development
APP_FRONTEND_URL=http://localhost:5173
CORS_ORIGINS=["http://localhost:5173","http://localhost:8080","http://127.0.0.1:5173"]

# Stripe testovacie platby (voliteľné)
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

### 🐳 B. Lokálny Docker Stack (`.env` v koreni)
Používa sa pri behu cez `cd deploy && docker compose up`:

```ini
POSTGRES_USER=straz
POSTGRES_PASSWORD=straz_change_me
POSTGRES_DB=straz
DATABASE_URL=postgresql+asyncpg://straz:straz_change_me@postgres:5432/straz
REDIS_URL=redis://redis:6379/0

STRAZ_ADMIN_EMAIL=erikbabcan@gmail.com
STRAZ_ADMIN_PASSWORD=heslo
STRAZ_SESSION_SECRET=dev-session-secret-must-be-at-least-32-chars-long!
STRAZ_COOKIE_SECURE=false

TRUSTED_PRIVATE_NETS=10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,127.0.0.0/8
HEARTBEAT_INTERVAL_MINUTES=5
NUCLEI_WEEKLY_CRON=0 3 * * 1
SUPPLY_CHAIN_WEEKLY_CRON=0 4 * * 1
INTERNETDB_BASE_URL=https://internetdb.shodan.io
NAABU_PORTS=21,22,25,53,80,110,143,443,445,465,587,993,995,1433,1521,3306,3389,5432,5900,6379,8080,8443,9200,27017
STRAZ_DOMAIN=localhost
```

### ☁️ C. Produkčné Prostredie (VPS / Cloud Backend)

```ini
STRAZ_ENV=production
STRAZ_DOMAIN=api.straz.vasadomena.sk
STRAZ_CORS_ORIGINS=["https://straz-monitoring.vercel.app","https://web-flax-omega-55.vercel.app"]
STRAZ_COOKIE_SECURE=true
STRAZ_SESSION_SECRET=<vygenerovaný-64-znakový-token>
STRAZ_ADMIN_PASSWORD=<silné-unikatne-heslo>
DATABASE_URL=postgresql+asyncpg://straz:<heslo>@postgres:5432/straz
REDIS_URL=redis://redis:6379/0
```

### 🌐 D. Vercel Frontend (`apps/web/.env.production` / Vercel Settings)

```ini
# Nastavenie spojenia z Vercelu na live API:
VITE_API_URL=https://api.straz.vasadomena.sk
```

---

## 📦 3. Súhrn Implementácie (Všetkých 6 EPICov)

| Modul | Popis a kľúčové schopnosti | Databázové migrácie | Kľúčové súbory |
| :--- | :--- | :--- | :--- |
| **EPIC 1: Multi-tenancy & RBAC** | Organizácie, prepínač workspaceov, pozvánky cez token, roly (`owner`, `admin`, `member`, `viewer`). | `002_organizations_and_rbac.py` | `app/routers/organizations.py`<br>`src/pages/TeamPage.tsx` |
| **EPIC 2: Stripe Billing & Quotas** | Plány Free/Pro/Enterprise, Stripe Checkout & Customer Portal, mesačné kvóty skenov, Stripe webhook handler. | `003_billing_and_quotas.py` | `app/routers/billing.py`<br>`src/pages/BillingPage.tsx` |
| **EPIC 3: White-Label NIS2 Report** | Export manažérskeho PDF reportu, mapovanie na Článok 21 Smernice NIS2, vlastné logo, firemné farby a branding. | `004_branding_and_compliance.py` | `app/routers/reports.py`<br>`src/components/CompliancePanel.tsx` |
| **EPIC 4: Alerting Hub** | Notifikácie do Slack, Discord, MS Teams, ntfy a vlastné Webhooky. Prísna ochrana proti SSRF & DNS rebindingu. | `005_integrations_and_alerting.py` | `app/routers/integrations.py`<br>`src/pages/IntegrationsPage.tsx` |
| **EPIC 5: Scoped API Kľúče & CI/CD** | Tokeny formátu `straz_live_...`, generátor CI skriptov pre GitHub Actions a GitLab CI, headless gate. | `006_api_keys_and_ci.py` | `app/routers/api_keys.py`<br>`src/pages/ApiKeysPage.tsx` |
| **EPIC 6: Audit Log & Health Sondy** | Nemenný audit log chránený SQL triggermi pred prepisom, bezpečný CSV export bez formula injection, `/healthz/liveness` a `/healthz/readiness`. | `007_audit_log_and_health.py` | `app/routers/audit.py`<br>`src/pages/AuditLogPage.tsx` |

---

## 🧪 4. Overenie Kvality & Testy

* **Backend Pytest:** **38 úspešných testov**, 1 preskočený (Docker-only Nuclei), 0 chýb.
* **Frontend TypeScript:** `npx tsc --noEmit` prebehol s **0 chybami**.
* **Frontend Production Build:** Vite build hotový za **2.18 s** bez varovaní.
* **Git Status:** Všetky zmeny zosynchronizované v `main` aj `audit-fix/20261022-security-hardening`.

---

## 🚀 5. Spustenie a Ovládanie

```bash
# Štart backendu (Terminál 1):
cd /Users/vorkei/Desktop/shadon-api-scaner/apps/api
uv run uvicorn app.main:app --port 8000

# Štart frontendu (Terminál 2):
cd /Users/vorkei/Desktop/shadon-api-scaner/apps/web
npm run dev

# Otvoriť konzolu v prehliadači:
# http://localhost:5173
```
