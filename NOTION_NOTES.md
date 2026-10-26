# 🛡️ STRÁŽ — Kompletná Projektová Karta & Dokumentácia do Notion

> **Status projektu:** 🟢 **100 % Produkčne nasadený, plne funkčný a overený**  
> **Dátum aktualizácie:** 26. október 2026  
> **Autor & Vlastník:** Erik Babčan (`erikbabcan@gmail.com`)  
> **GitHub repozitár:** [https://github.com/erikbabcan-commits/shadon-api-scaner](https://github.com/erikbabcan-commits/shadon-api-scaner) (Vetva: `main`, commit: `83a25c3`)  
> **Produkčný Frontend (Vercel):** [https://straz-monitoring.vercel.app](https://straz-monitoring.vercel.app)  
> **Produkčný Backend API (Railway):** [https://straz-api-production.up.railway.app](https://straz-api-production.up.railway.app)  
> **Interaktívna API Dokumentácia (Swagger):** [https://straz-api-production.up.railway.app/docs](https://straz-api-production.up.railway.app/docs)  
> **Lokálna záloha (ZIP):** `/Users/vorkei/Desktop/STRAZ_COMPLETE_RECOVERED.zip`  

---

## 📌 1. Živé Produkčné Adresy a Služby

| Komponent | Platforma / Projekt | URL / Identifikátor | Stav |
| :--- | :--- | :--- | :--- |
| **PWA Frontend** | Vercel (`scope: h4ck3d`, `project: straz-monitoring`) | [https://straz-monitoring.vercel.app](https://straz-monitoring.vercel.app) | 🟢 Ready (Build 12s) |
| **Alternatívny Frontend** | Vercel | [https://web-flax-omega-55.vercel.app](https://web-flax-omega-55.vercel.app) | 🟢 Povolený v CORS |
| **FastAPI Backend** | Railway (`project: dev-new`, `env: production`) | [https://straz-api-production.up.railway.app](https://straz-api-production.up.railway.app) | 🟢 Online (Port dynamically bind) |
| **Background Worker** | Railway (`straz-worker`) | ARQ Async Worker | 🟢 Online (Heartbeat & Outbox) |
| **PostgreSQL 18** | Railway (`Postgres`) | `postgres.railway.internal:5432` | 🟢 Online (Schema head: 008) |
| **Redis Cache & Queue**| Railway (`Redis`) | `redis.railway.internal:6379` | 🟢 Online (Latencia ~28ms) |
| **Liveness Sonda** | FastAPI Health Check | [https://straz-api-production.up.railway.app/healthz/liveness](https://straz-api-production.up.railway.app/healthz/liveness) | 🟢 200 OK |
| **Readiness Sonda** | DB & Redis Health Check | [https://straz-api-production.up.railway.app/healthz/readiness](https://straz-api-production.up.railway.app/healthz/readiness) | 🟢 200 OK (`ready: true`) |

---

## 🔐 2. Autentifikácia & Pracovné Priestory (Workspaces)

### 👤 Administrátorský účet (Bootstrap)
* **Email:** `erikbabcan@gmail.com`
* **Heslo (Production):** `u7ey0918wrfawdrj6coochb61ih9f6a9` *(konfigurované v Railway premenných)*
* **Lokálne vývojové heslo:** `heslo`

### 🏢 Dostupné organizácie
1. **Osobný workspace:**
   - **Názov:** `erikbabcan's Workspace`
   - **Slug:** `erikbabcans-workspace`
   - **Rola:** `owner`
   - **Účel:** Čistý produkčný workspace pre reálne monitorované systémy organizácie.
2. **Syntetický DEMO workspace:**
   - **Názov:** `[DEMO] Stráž Workspace`
   - **Slug:** `straz-golden-demo`
   - **UUID:** `5d004699-10ab-5c2e-8c68-8abb0200aa8b`
   - **Plán:** `pro`
   - **Obsah:** 
     - **3 aplikácie:** `[DEMO] E-Shop Produkcia`, `[DEMO] Klient Portál API`, `[DEMO] Interný Auth Server`
     - **10 bezpečnostných nálezov:** Critical (1), High (2), Medium (4), Low (2), Info (1)
     - **5 behov skenov:** Heartbeat, InternetDB, Safe HTTP, Port check, TLS check
     - **10 nemenných auditných logov** s kompletnou históriou operátora

---

## ⚙️ 3. Kompletná Konfigurácia Premenných Prostredia (ENV)

### ☁️ A. Railway — `straz-api` (Produkčný Web Service)
```ini
# Aplikácia & Prostredie
STRAZ_ENV=production
APP_FRONTEND_URL=https://straz-monitoring.vercel.app
STRAZ_CORS_ORIGINS=https://straz-monitoring.vercel.app,https://web-flax-omega-55.vercel.app

# Bezpečnosť relácie & Cookies
STRAZ_ADMIN_EMAIL=erikbabcan@gmail.com
STRAZ_ADMIN_PASSWORD=u7ey0918wrfawdrj6coochb61ih9f6a9
STRAZ_SESSION_SECRET=0e4u4b8lnxbpstrni6xse8hek0q85sekmxm67pzs7k45jp4iubqumsf9zkwojjti
STRAZ_COOKIE_SECURE=true
STRAZ_COOKIE_SAMESITE=none

# Databáza a Redis (Railway Private Network)
DATABASE_URL=postgresql://postgres:dDihWVVmVbSTjAccfUBxekFEylUrMWee@postgres.railway.internal:5432/railway
REDIS_URL=redis://default:gRBRsuZGArbnHaluOkTvUfhTMsbtzwLw@redis.railway.internal:6379

# Automatický port prideľovaný Railway
PORT=8080
```
> *Poznámka: Kód backendu automaticky normalizuje `postgresql://` na `postgresql+asyncpg://`, takže nehrozí nekompatibilita s async engine.*

### ⚙️ B. Railway — `straz-worker` (Background Worker Service)
```ini
# Worker zdieľa rovnaké bezpečné premenné ako API
STRAZ_ENV=production
APP_FRONTEND_URL=https://straz-monitoring.vercel.app
STRAZ_CORS_ORIGINS=https://straz-monitoring.vercel.app,https://web-flax-omega-55.vercel.app
STRAZ_ADMIN_EMAIL=erikbabcan@gmail.com
STRAZ_ADMIN_PASSWORD=u7ey0918wrfawdrj6coochb61ih9f6a9
STRAZ_SESSION_SECRET=0e4u4b8lnxbpstrni6xse8hek0q85sekmxm67pzs7k45jp4iubqumsf9zkwojjti
STRAZ_COOKIE_SECURE=true
STRAZ_COOKIE_SAMESITE=none
DATABASE_URL=postgresql://postgres:dDihWVVmVbSTjAccfUBxekFEylUrMWee@postgres.railway.internal:5432/railway
REDIS_URL=redis://default:gRBRsuZGArbnHaluOkTvUfhTMsbtzwLw@redis.railway.internal:6379
```

### 🌐 C. Vercel — `straz-monitoring` (Frontend)
```ini
# Nastavenie spojenia z Vercelu na Railway API:
VITE_API_URL=https://straz-api-production.up.railway.app
```

### 💻 D. Lokálny Vývoj (`apps/api/.env`)
```ini
DATABASE_URL=sqlite+aiosqlite:///./straz.db
REDIS_URL=redis://localhost:6379/0
STRAZ_ADMIN_EMAIL=erikbabcan@gmail.com
STRAZ_ADMIN_PASSWORD=heslo
STRAZ_SESSION_SECRET=dev-session-secret-must-be-at-least-32-chars-long!
STRAZ_COOKIE_SECURE=false
STRAZ_COOKIE_SAMESITE=lax
STRAZ_ENV=development
APP_FRONTEND_URL=http://localhost:5173
STRAZ_CORS_ORIGINS=http://localhost:5173,http://localhost:8080,http://127.0.0.1:5173
```

---

## 🏗️ 4. Architektúra & Databázové Migrácie

Všetky databázové migrácie bežia cez **Alembic** a podporujú **PostgreSQL 16 aj 18**:

| Migrácia | Názov | Kľúčové entity a funkcie |
| :--- | :--- | :--- |
| `001` | `baseline_schema` | Používatelia (`User`), aplikácie (`App`), ciele (`Target`), nálezy (`Finding`), skeny (`ScanRun`). |
| `002` | `organizations_and_rbac` | Multi-tenancy: Organizácie (`Organization`), členstvá (`OrganizationMember`), pozvánky (`Invitation`), roly (`owner`, `admin`, `member`, `viewer`). |
| `003` | `billing_and_quotas` | Stripe zákazníci, predplatné plány (Free/Pro/Enterprise), mesačné kvóty skenov, Stripe webhook event log. |
| `004` | `branding_and_compliance` | White-label reporting, firemný branding (farby, logo), mapovanie na smernicu NIS2 (Článok 21). |
| `005` | `integrations_and_alerting` | Alerting kanály: Slack, Discord, MS Teams, ntfy, vlastné webhooky, SSRF filter a ochrana DNS. |
| `006` | `api_keys_and_ci` | Scoped API tokeny (`straz_live_...`), generátor headless skriptov pre GitHub Actions a GitLab CI. |
| `007` | `audit_log_and_health` | Nemenný audit log (`AuditEvent`), PostgreSQL trigger blokujúci `UPDATE` a `DELETE`, bezpečný CSV export. |
| `008` | `postgres_uuid_and_audit_fk` | Konverzia ID na natívne PostgreSQL `UUID`, oprava audit foreign key väzieb a automatická retencia. |

---

## 🔒 5. Bezpečnostné Opatrenia (Audit Hardening)

1. **Striktná ochrana relácie (Session Cookie):**
   - V produkcii sa používa zabezpečený prefix `__Host-straz_session`.
   - Vlajky: `HttpOnly`, `Secure`, `SameSite=none`, `Path=/`, `Max-Age=1209600` (14 dní).
2. **CORS & Origin Guard:**
   - Každá mutujúca požiadavka (`POST`, `PUT`, `DELETE`, `PATCH`) musí pochádzať z autorizovaného `Origin` (`STRAZ_CORS_ORIGINS`), inak je okamžite zamietnutá kódom `403 Forbidden`.
3. **Izolácia CLI skenerov:**
   - Až do nasadenia gVisor/Firecracker sieťového pieskoviska sú externé nástroje (`nuclei`, `subfinder`, `naabu`, `tlsx`) odmietané deterministickým kódom `409 Conflict` so správou `CLI_SCANNER_UNAVAILABLE`.
4. **SSRF & DNS Rebinding Ochrana:**
   - Webhooky a notifikácie overujú ciele cez `validate_public_url()` a blokujú privátne rozsahy (RFC 1918, CGNAT, Cloud metadata IP `169.254.169.254`).
5. **Anti-Tamper Audit Log:**
   - Záznamy v `audit_logs` sú chránené SQL triggerom na úrovni databázy. Akýkoľvek pokus o ich prepísanie alebo zmazanie zlyhá na úrovni PostgreSQL.

---

## 🧪 6. Overovacie Príkazy pre Operátora

### 🚀 Lokálny beh aplikácie
```bash
# 1. Backend (FastAPI na porte 8000)
cd /Users/vorkei/Desktop/shadon-api-scaner/apps/api
uv run uvicorn app.main:app --port 8000

# 2. Frontend (Vite dev server na porte 5173)
cd /Users/vorkei/Desktop/shadon-api-scaner/apps/web
npm run dev
```

### 🔬 Spustenie testov
```bash
# Backend pytest (106 testov):
cd /Users/vorkei/Desktop/shadon-api-scaner/apps/api
uv run pytest

# Frontend type-check & testy:
cd /Users/vorkei/Desktop/shadon-api-scaner/apps/web
npm run test
npx tsc --noEmit
```

### ☁️ Správa Railway a Vercel z CLI
```bash
# Kontrola stavu Railway služieb:
railway status -p f233a228-5a2a-49b3-9be5-2cafedcb7049 -e ba5166f1-65be-4244-899c-f27080570e5f

# Posledné logy API servera:
railway logs -p f233a228-5a2a-49b3-9be5-2cafedcb7049 -e ba5166f1-65be-4244-899c-f27080570e5f -s straz-api --lines 50

# Prehľad nasadení na Verceli:
vercel ls --scope h4ck3d straz-monitoring
```

---

## 📞 7. Rýchly Kontakt & Údaje projektu

* **Vlastník:** Erik Babčan  
* **GitHub Organizácia / Účet:** `erikbabcan-commits`  
* **Vercel Tím / Scope:** `h4ck3d`  
* **Railway Workspace:** `H4CK3D's Projects` (`2b4de623-f58a-4f86-9123-fa90190c7224`)  
* **Railway Projekt:** `dev-new` (`f233a228-5a2a-49b3-9be5-2cafedcb7049`)  
* **Railway Prostredie:** `production` (`ba5166f1-65be-4244-899c-f27080570e5f`)
