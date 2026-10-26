# Stráž — Enterprise Bezpečnostný Monitoring & Audit Vlastných Aplikácií

[![CI Pipeline](https://github.com/erikbabcan-commits/shadon-api-scaner/actions/workflows/ci.yml/badge.svg)](https://github.com/erikbabcan-commits/shadon-api-scaner/actions/workflows/ci.yml)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19.0-61DAFB.svg)](https://react.dev)
[![TailwindCSS](https://img.shields.io/badge/TailwindCSS-4.0-38B2AC.svg)](https://tailwindcss.com)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.7-3178C6.svg)](https://www.typescriptlang.org)
[![NIS2 Compliant](https://img.shields.io/badge/NIS2-Article%2021-success.svg)](https://digital-strategy.ec.europa.eu/en/policies/nis2-directive)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Stráž** je enterprise bezpečnostný dohľadový systém a PWA konzola pre audit, kontinuálny monitoring a riadenie rizík vlastných webových aplikácií, domén, kontajnerov a repozitárov. Skeny bežia striktne voči overenému inventáru s kryptografickou/DNS verifikáciou vlastníctva a ochranou proti zneužitiu.

---

## 🏛️ Architektúra a Prevádzkové Modely

Systém podporuje dva hlavné prevádzkové modely:

1. **Split Deploy (Odporúčaný pre SaaS / Edge):**
   * **Frontend:** Globálne distribuovaná PWA konzola na **Vercel Edge Network** ([https://straz-monitoring.vercel.app](https://straz-monitoring.vercel.app)).
   * **Backend:** Asynchrónne REST API (FastAPI) + ARQ background worker + Redis + PostgreSQL bežiace na vlastnom **VPS / Railway / Render**.
2. **All-in-One VPS (Self-hosted / On-Premise):**
   * Všetky služby vrátane Caddy reverzného proxy s automatickým Let's Encrypt SSL bežia na jedinom Docker hoste (`deploy/docker-compose.prod.yml`).

```mermaid
graph TD
    User([Používateľ / PWA Client]) -->|HTTPS| Vercel[Vercel CDN / Edge - apps/web]
    User -->|REST API + Cookies| Gateway[Caddy / Nginx Reverse Proxy]
    
    subgraph Cloud / VPS Backend
        Gateway -->|HTTP :8000| API[FastAPI Core - apps/api]
        API -->|Async ORM| DB[(PostgreSQL 16 / SQLite dev)]
        API -->|Jobs / Rate-Limit| Redis[(Redis 7)]
        
        Worker[ARQ Background Worker] -->|Fetch Jobs| Redis
        Worker -->|Audit & Findings| DB
        
        subgraph Scanners Sandbox
            Worker -->|Latency/Status| HTTPX[HTTPX & TLSX]
            Worker -->|CVE & Misconfigs| Nuclei[Nuclei Safe]
            Worker -->|Subdomény| Subfinder[Subfinder]
            Worker -->|Otvorené porty| Naabu[Naabu]
            Worker -->|Git & Image Scan| Trivy[Trivy & Gitleaks]
            Worker -->|Passive Recon| InternetDB[Shodan InternetDB]
        end
        
        Worker -->|Alerting Hub| Alerts[Slack / Discord / Teams / Webhooks / ntfy]
    end
```

---

## 🛡️ Enterprise Schopnosti & Moduly (EPIC 1 – 6)

Systém obsahuje 6 kompletne implementovaných a otestovaných modulov:

### 1. Multi-Tenancy & Tímový RBAC (EPIC 1)
* Izolácia nájomcov (Organizations/Workspaces) s podporou prepínania v UI.
* 4-úrovňový model oprávnení: `owner`, `admin`, `member`, `viewer`.
* Pozvánky do tímu cez kryptografické tokeny s expiráciou a voliteľnou rolou.
* API správy členov a rolí (`/api/orgs/{org_id}/members`).

### 2. Stripe Monetizácia & Quota Engine (EPIC 2)
* Plány predplatného: **Free** (3 skeny/mesiac), **Pro** (100 skenov/mesiac), **Enterprise** (neobmedzene).
* Integrácia Stripe Checkout & Customer Billing Portal pre správu kariet a faktúr.
* Automatická synchronizácia cez zabezpečený Stripe Webhook.
* Presné vynucovanie kvót a limitov podľa zakúpeného balíka.

### 3. Executive White-Label Report & NIS2 Compliance (EPIC 3)
* Generovanie manažérskych reportov v PDF a JSON formáte.
* Mapovanie zistení na **Článok 21 Smernice NIS2** (kybernetická bezpečnosť dodávateľského reťazca a zraniteľnosti).
* Custom Branding: Vlastné firemné logo, primárna farba a názov organizácie na reportoch.

### 4. Enterprise Alerting Hub (EPIC 4)
* Natívne formátovače pre **Slack**, **Discord**, **Microsoft Teams**, **ntfy.sh** a vlastné **Webhooky**.
* Nastavenie minimálnej úrovne závažnosti pre notifikácie (`low`, `medium`, `high`, `critical`).
* Ochrana proti **SSRF a DNS rebinding útokom** (prísna validácia cieľových IP/hostov a blokovanie privátnych sietí).
* Okamžitý test doručiteľnosti webhookov z administrátorského rozhrania.

### 5. Scoped API Kľúče & Headless CI/CD Gate (EPIC 5)
* Generovanie scoped API tokenov v bezpečnom formáte: `straz_live_<48_hex_chars>`.
* Rýchly generátor CI/CD integračných skriptov pre **GitHub Actions** a **GitLab CI**.
* Headless bezpečnostná brána: Blokovanie deploymentu pri náleze kritických zraniteľností cez CLI alebo CI pipeline (`/api/ci/gate`).

### 6. Nemenný Audit Log & Health Sondy (EPIC 6)
* **Immutable Audit Trail:** Ochrana auditných záznamov na úrovni databázy pomocou SQL triggerov (`audit_logs_immutable`). Záznamy nie je možné prepísať ani vymazať.
* **Bezpečný CSV Export:** Ochrana proti Formula Injection (znaky `=`, `+`, `-`, `@` sú bezpečne sanitované pred otvorením v Exceli).
* **Observability Sondy:** `/healthz/liveness` a `/healthz/readiness` s presným meraním latencie PostgreSQL a Redis spojení.

---

## 🚀 Rýchly Štart (Lokálny Vývoj)

### Požiadavky
* Python 3.12+ a balíčkovací manažér [uv](https://docs.astral.sh/uv/)
* Node.js 20+ a npm
* *(Voliteľné)* Docker pre kompletný stack s Redis a PostgreSQL

### 1. Spustenie lokálneho prostredia (Najrýchlejšia cesta)

```bash
# Krok 1: Klonovanie a vstup do repozitára
git clone https://github.com/erikbabcan-commits/shadon-api-scaner.git
cd shadon-api-scaner

# Krok 2: Spustenie FastAPI backendu (Terminál 1)
cd apps/api
uv sync --dev
uv run uvicorn app.main:app --port 8000

# Krok 3: Spustenie Vite frontendu (Terminál 2)
cd ../web
npm install
npm run dev
```

* **Frontend konzola:** [http://localhost:5173](http://localhost:5173)
* **Backend API Swagger:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
* **Predvolený administrátorský účet:**
  * **Email:** `admin@example.invalid`
  * **Heslo:** `heslo`

---

## ⚙️ Konfigurácia Premenných Prostredia (ENV)

### Lokálny Vývoj (`apps/api/.env`)

```ini
# Databáza a Redis (v dev režime stačí lokálny SQLite)
DATABASE_URL=sqlite+aiosqlite:///./straz.db
REDIS_URL=redis://localhost:6379/0

# Administrátorský prístup
STRAZ_ADMIN_EMAIL=admin@example.invalid
STRAZ_ADMIN_PASSWORD=heslo
STRAZ_SESSION_SECRET="$(openssl rand -hex 32)"
STRAZ_COOKIE_SECURE=false

# CORS & Routing
STRAZ_ENV=development
APP_FRONTEND_URL=http://localhost:5173
CORS_ORIGINS=["http://localhost:5173","http://localhost:8080","http://127.0.0.1:5173"]

# Stripe (testovacie kľúče)
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

### Produkčné Prostredie (VPS / Docker `.env`)

```ini
POSTGRES_USER=straz
POSTGRES_PASSWORD="$(openssl rand -hex 32)"
POSTGRES_DB=straz
DATABASE_URL=postgresql+asyncpg://straz:silne_unikatne_heslo_min_16_znakov@postgres:5432/straz
REDIS_URL=redis://redis:6379/0

STRAZ_ADMIN_EMAIL=admin@example.invalid
STRAZ_ADMIN_PASSWORD=silne_admin_heslo
STRAZ_SESSION_SECRET="$(openssl rand -hex 32)"
STRAZ_COOKIE_SECURE=true
STRAZ_ENV=production

# CORS pre Vercel
CORS_ORIGINS=["https://straz-monitoring.vercel.app","https://web-flax-omega-55.vercel.app"]

# Skenery a Limity
TRUSTED_PRIVATE_NETS=10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,127.0.0.0/8
INTERNETDB_BASE_URL=https://internetdb.shodan.io
NAABU_PORTS=21,22,25,53,80,110,143,443,445,465,587,993,995,1433,1521,3306,3389,5432,6379,8080,8443,9200
```

### Vercel Produkcia (`apps/web/.env.production` / Vercel Environment Variables)

```ini
# Nastavenie verejnej adresy backend API pre Vercel Edge frontend
VITE_API_URL=https://api.straz.vasadomena.sk
```

---

## 🧪 Testovanie & Verifikácia Kvality

Systém je krytý komplexnou sadou automatických testov:

```bash
# Spustenie backend testovacej sady (FastAPI, Auth, RBAC, Billing, Reports, Scanners, CI, Audit)
cd apps/api
uv run pytest -v

# Kontrola typov a produkčný build frontendu (Vite + React 19)
cd ../web
npx tsc --noEmit
npm run build
```

* **Stav backend testov:** 38 úspešných, 1 preskočený (Docker-only Nuclei sandbox), 0 zlyhaní.
* **Stav frontendu:** 0 TypeScript chýb, čistý produkčný bundle.

---

## 📄 Licencia

Tento projekt je distribuovaný pod licenciou MIT. Všetky práva vyhradené.
