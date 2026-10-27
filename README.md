# Stráž — Enterprise Bezpečnostný Monitoring & Audit Vlastných Aplikácií

> **Aktuálny rozsah služby:** aktívne sú iba Heartbeat a InternetDB. Osem CLI profilov
> (TLS, HTTP, Nuclei safe, Subdomain, Ports, Trivy FS/Image, Gitleaks) je zablokovaných
> do doplnenia izolácie, vo všetkých plánoch aj CI/CD. Nižšie opísané implementované
> funkcie nie sú dôkazom ich aktuálnej produkčnej dostupnosti.
>
> Railway projekt: **dev-new**. Vercel projekt: **straz-monitoring**. Commit pin,
> DEMO stav a produkčné kontroly potvrdzuje operátor pri release.
> Pozri [aktuálne poznámky](NOTION_NOTES.md), [incidentný postup](docs/INCIDENT_ROTATION_RUNBOOK.md)
> a [prevádzkové overenie](docs/OPERATIONS_ACCEPTANCE.md).


## Záverečný checklist operátora pred produkčným uzavretím

Tento zoznam eviduje zostávajúce kroky; nezaškrtnutá položka nie je vykonaná
ani overená. Samotné zlúčenie PR, zelené CI alebo úprava dokumentácie
nepotvrdzujú produkčné nasadenie ani rotáciu tajomstiev.

### 1. Prístupy a schválenie

- [ ] Obnoviť dostupný spôsob správy Railway: dashboard alebo autentifikované CLI.
  Chyba `402 Agent usage limit reached` sa týka limitu AI agenta; sama
  nepotvrdzuje výpadok aplikácie. Zvýšenie limitu agenta je voliteľné a môže byť spoplatnené.
- [ ] Overiť správny Railway projekt **dev-new**, environment **production**
  a služby **straz-api**, **straz-worker**, **Postgres**, **Redis**.
  Frontend patrí Vercel projektu **straz-monitoring**.
- [ ] Výslovne schváliť zlúčenie [PR #4](https://github.com/erikbabcan-commits/shadon-api-scaner/pull/4).
  Pred merge znovu skontrolovať aktuálny HEAD, diff a CI.
- [ ] Samostatne schváliť produkčnú rotáciu a nasadenie. Hodnoty tajomstiev
  nevkladať do chatu, príkazových argumentov, logov ani Gitu.

### 2. Priorita: uniknuté tajomstvá

- [ ] Pripraviť obnoviteľnú zálohu a koordinovaný servisný postup podľa
  [incidentného runbooku](docs/INCIDENT_ROTATION_RUNBOOK.md).
  Dĺžka prípadného výpadku sa negarantuje.
- [ ] Zrotovať skutočné heslo PostgreSQL roly a autentifikáciu Redisu,
  zosúladiť privátne pripojenia API aj workera a overiť odmietnutie starých údajov.
  Samotná zmena Railway premennej nemusí zmeniť heslo bežiacej databázy.
- [ ] Zmeniť heslo existujúceho administrátora v databáze bezpečným aplikačným
  postupom a zvýšiť `token_version`. Zmena `STRAZ_ADMIN_PASSWORD` sama
  nemusí aktualizovať existujúci účet.
- [ ] Vymeniť `STRAZ_SESSION_SECRET` vo všetkých relevantných inštanciách,
  overiť nové prihlásenie a odmietnutie starej relácie bez vypísania cookies.
- [ ] Zaznamenať výsledky rotácie bez hodnôt tajomstiev. História Gitu ich
  obsahuje aj po odstránení z aktuálneho stromu; voliteľný prepis histórie
  potrebuje osobitné schválenie a nenahrádza rotáciu.

### 3. Proxy a nasadenie

- [ ] Doložiť dôveryhodnú cestu klientovej IP pre Vercel → Railway → Uvicorn
  aj priamy Railway vstup. Nenastavovať `STRAZ_TRUSTED_PROXY_IPS` naslepo
  na `*` ani na celé privátne rozsahy. Overiť ochranu pred podvrhnutým
  `X-Forwarded-For` a oddelené rozpočty limiteru pre dvoch klientov.
- [ ] Overiť aktuálne commit piny služieb v Railway; pri pripnutom commite
  push do `main` sám osebe nové API ani worker nenasadí.
- [ ] Po schválení nasadiť konkrétny overený commit na API aj worker,
  skontrolovať pre-deploy migrácie a zaznamenať skutočne bežiace SHA.
- [ ] Frontend CSP ponechať v režime Report-Only, overiť prehliadač a až potom
  schváliť vynucovanie. Otestovať aj Safari/iPhone prihlásenie cez Vercel proxy.
- [ ] Osem CLI profilov ponechať zablokovaných do doplnenia a overenia
  sieťovej izolácie; dostupné ostávajú Heartbeat a InternetDB.

### 4. Akceptačné dôkazy a prevádzka

- [ ] Overiť liveness/readiness HTTP 200 s PostgreSQL aj Redis, HSTS,
  povolený/cudzí CORS origin, HTTP 401 bez relácie a bežiaci worker.
  Test blokovaného CLI profilu (očakávané 409) vykonať iba s povolením na POST.
- [ ] Read-only overiť Alembic head a PostgreSQL verziu; spočítať aplikácie
  bez organizácie pomocou [pripraveného SQL](deploy/audit-readonly.sql).
  Vlastníctvo ani dáta automaticky nemeniť.
- [ ] Doložiť zálohovací plán, retenciu a úspešnú izolovanú obnovu;
  nastaviť a otestovať alerty na neúspešné nasadenie a readiness.
- [ ] Rozhodnúť o verejnej registrácii. Odstránenie syntetického testovacieho
  účtu, backfill organizácií a iné dátové zásahy schváliť osobitne.
- [ ] Overiť označenie DEMO dát a neprítomnosť aktívnych skenov demo cieľov.
  Syntetické nálezy neprezentovať ako skutočné incidenty.
- [ ] Na každom vývojárskom klone aktivovať hook z koreňa repozitára:
  `git config --local core.hooksPath .githooks`; podľa
  [návodu](docs/SECRET_SCAN.md) zabezpečiť Gitleaks a overiť hook.
  Hook možno obísť, preto ponechať aj blokujúci CI secret gate.
- [ ] Do release záznamu uložiť SHA, výsledky CI a živých kontrol,
  zostávajúce riziká a schválenia. Tajomstvá ani osobné dáta nezapisovať.

Podrobný prevádzkový postup: [OPERATIONS_ACCEPTANCE.md](docs/OPERATIONS_ACCEPTANCE.md).

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
  * **Heslo:** nastavte vlastné silné heslo; predvolené heslo nie je produkčná konfigurácia.

---

## ⚙️ Konfigurácia Premenných Prostredia (ENV)

### Lokálny Vývoj (`apps/api/.env`)

```ini
# Databáza a Redis (v dev režime stačí lokálny SQLite)
DATABASE_URL=sqlite+aiosqlite:///./straz.db
REDIS_URL=redis://localhost:6379/0

# Administrátorský prístup
STRAZ_ADMIN_EMAIL=admin@example.invalid
STRAZ_ADMIN_PASSWORD=<set securely before use>
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
STRAZ_ADMIN_PASSWORD=<set securely before use>
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
