# Stráž — Bezpečnostný monitoring a audit vlastných aplikácií

[![CI Pipeline](https://github.com/your-org/straz/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/straz/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19.0-61DAFB.svg)](https://react.dev)
[![TailwindCSS](https://img.shields.io/badge/TailwindCSS-4.0-38B2AC.svg)](https://tailwindcss.com)

**Stráž** je produkčný bezpečnostný dohľadový systém a PWA konzola pre audit a sledovanie vlastných webových aplikácií, domén, kontajnerov a repozitárov. Skeny bežia striktne voči overenému inventáru s kryptografickou/DNS verifikáciou vlastníctva.

---

## 🏛️ Architektúra systému

Systém podporuje dva prevádzkové modely:
1. **Split Deploy (Odporúčaný):** Frontend beží globálne ako PWA na **Vercel Edge Network**, backend (FastAPI + ARQ worker + PostgreSQL + Redis) na vlastnom **VPS / Railway**.
2. **All-in-One VPS:** Všetky služby vrátane Caddy reverzného proxy a statického frontendu bežia na jedinom Docker hoste.

```mermaid
graph TD
    User([Používateľ / PWA Client]) -->|HTTPS / WSS| Vercel[Vercel CDN / Edge - apps/web]
    User -->|REST API + Cookies| Gateway[Caddy / Nginx Reverse Proxy]
    
    subgraph VPS / Cloud Backend
        Gateway -->|HTTP :8000| API[FastAPI Core - apps/api]
        API -->|Async ORM| DB[(PostgreSQL 16)]
        API -->|Enqueue Jobs / Cache| Redis[(Redis 7)]
        
        Worker[ARQ Background Worker] -->|Fetch Jobs| Redis
        Worker -->|Audit & Findings| DB
        
        subgraph Scanners Sandbox
            Worker -->|Latency/Status| HTTPX[HTTPX & TLSX]
            Worker -->|CVE & Misconfigs| Nuclei[Nuclei Safe]
            Worker -->|Subdomény| Subfinder[Subfinder]
            Worker -->|Otvorené porty| Naabu[Naabu]
            Worker -->|Git Repo & Image Scan| Trivy[Trivy & Gitleaks]
            Worker -->|Passive Recon| InternetDB[Shodan InternetDB]
        end
        
        Worker -->|Alerts| Ntfy[ntfy.sh / Self-hosted Push]
    end
```

---

## 🚀 Rýchly štart (Lokálny vývoj)

### Požiadavky
- Python 3.12+ a [uv](https://docs.astral.sh/uv/)
- Node.js 20+ a npm
- Docker Desktop / Podman

### 1. Spustenie cez Docker Compose (všetko v jednom)
```bash
cp .env.example .env
cd deploy
docker compose up --build
```
Konzola je dostupná na: **[http://localhost:8080](http://localhost:8080)**  
Predvolené prihlasovacie údaje:
- **Email:** `admin@example.com`
- **Heslo:** `change-me-now` (zmeňte v `.env` pred nasadením!)

### 2. Oddelený vývoj (lokálny backend + Vite HMR)
```bash
# Backend (Terminál 1)
cd apps/api
uv sync --dev
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000

# Background Worker (Terminál 2)
cd apps/api
uv run arq app.worker.WorkerSettings

# Frontend (Terminál 3)
cd apps/web
npm install
npm run dev
```

---

## 🌐 Produkčné nasadenie (Vercel + VPS)

### Krok 1: Nasadenie Backend-u na VPS
1. Naklonujte repozitár na VPS:
   ```bash
   git clone https://github.com/your-org/straz.git /opt/straz
   cd /opt/straz
   cp .env.example .env
   ```
2. Nastavte v `.env`:
   ```bash
   STRAZ_ENV=production
   STRAZ_DOMAIN=api.straz.vasadomena.sk
   STRAZ_CORS_ORIGINS=https://straz.vercel.app,https://straz.vasadomena.sk
   STRAZ_COOKIE_SAMESITE=none
   STRAZ_COOKIE_SECURE=true
   STRAZ_COOKIE_DOMAIN=.vasadomena.sk # Ak sú na spoločnej nadradenej doméne
   STRAZ_SESSION_SECRET=generujte-nahodny-retazec-min-32-znakov
   STRAZ_ADMIN_PASSWORD=silne-unikatne-heslo
   POSTGRES_PASSWORD=silne-db-heslo
   DATABASE_URL=postgresql+asyncpg://straz:silne-db-heslo@postgres:5432/straz
   REDIS_URL=redis://redis:6379/0
   ACME_EMAIL=admin@vasadomena.sk
   ```
3. Spustite produkčný docker stack s limitmi a Caddy:
   ```bash
   cd deploy
   docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   ```
4. Migrácie databázy sa aplikujú automaticky pri štarte kontajnera, alebo manuálne:
   ```bash
   docker compose exec api alembic upgrade head
   ```

### Krok 2: Automatické zálohovanie databázy
Pridajte denný cron job na VPS:
```bash
chmod +x /opt/straz/deploy/backup-db.sh
sudo crontab -e
# Záloha každý deň o 03:00 s rotáciou 7 dní:
0 3 * * * /opt/straz/deploy/backup-db.sh >> /var/log/straz-backup.log 2>&1
```

### Krok 3: Nasadenie Frontend-u na Vercel
1. Vytvorte nový projekt na [Vercel](https://vercel.com).
2. Prepojte Git repozitár.
3. Nastavenia projektu:
   - **Framework Preset:** Vite
   - **Root Directory:** `apps/web`
   - **Build Command:** `npm run build`
   - **Output Directory:** `dist`
4. Nastavte Environment Variables vo Vercel UI:
   - `VITE_API_URL` = `https://api.straz.vasadomena.sk`
5. Kliknite **Deploy**. Súbor `vercel.json` automaticky zabezpečí rewrites pre TanStack Router SPA smerovanie a bezpečnostné HTTP hlavičky.

---

## 🔒 Bezpečnostné mechanizmy a audity

- **Verifikácia vlastníctva:** Žiadny aktívny sken nespustíte bez overenia domény cez **DNS TXT záznam** (`straz-verify=<token>`).
- **SSRF ochrana:** Validácia privátnych IP adries a loopback rozsahov v cieľových adresách a repozitároch.
- **Argon2id + token_version:** Heslá sú hashované algoritmom Argon2. Zmena hesla automaticky inkrementuje `token_version`, čím okamžite invaliduje všetky existujúce aktívne sessions.
- **Distributed Rate Limiting:** Ochrana API endpointov cez Redis `INCR` + `EXPIRE` vzor s automatickým in-memory fallbackom a hlavičkami `X-RateLimit-*`.
- **Worker Isolation:** Binárne nástroje (`nuclei`, `naabu`, `subfinder`, `trivy`, `gitleaks`) bežia v izolovanom kontajneri s neintrusívnymi profilmi a Redis lockom.

---

## 🔍 Prehľad skenovacích profilov

| Profil | Nástroj | Účel | Požiadavka na target |
|---|---|---|---|
| `heartbeat` | Native HTTP | Dostupnosť, latencia, status kód, HTML title | Bez obmedzenia |
| `tls` | ProjectDiscovery `tlsx` | Platnosť a expirácia SSL certifikátov, SAN mismatch | Overený target |
| `http` | ProjectDiscovery `httpx` | Analýza technológií, presmerovaní, serverových hlavičiek | Overený target |
| `safe` | ProjectDiscovery `nuclei` | Neintrusívne bezpečnostné zraniteľnosti a expozície | Overený target |
| `internetdb` | Shodan InternetDB | Pasívny lookup otvorených portov a známych CVE | Overený target (verejná IP) |
| `subdomain` | ProjectDiscovery `subfinder` | Pasívna enumerácia subdomén do pending zoznamu | Overený target |
| `ports` | ProjectDiscovery `naabu` | Sken vybraných bezpečných portov (`NAABU_PORTS`) | Overený target |
| `trivy_fs` | Aqua `trivy` | Analýza zraniteľností softvérových závislostí v git clone | Git URL aplikácie |
| `trivy_image` | Aqua `trivy` | Kontajnerový sken Docker image vrstiev na CVE | Image Ref aplikácie |
| `gitleaks` | Gitleaks | Detekcia uniknutých API kľúčov, tokenov a privátnych kľúčov | Git URL aplikácie |

---

## ⚙️ Referencia premenných prostredia (`.env`)

| Premenná | Predvolená hodnota | Popis |
|---|---|---|
| `STRAZ_ENV` | `development` | Prostredie: `development`, `staging`, `production`, `testing` |
| `STRAZ_DOMAIN` | `localhost` | Primárna doména aplikácie |
| `STRAZ_CORS_ORIGINS` | `""` | Čiarkami oddelený zoznam povolených CORS originov (napr. Vercel) |
| `STRAZ_COOKIE_SAMESITE` | `lax` | SameSite atribút: `lax`, `strict`, `none` (pre cross-domain) |
| `STRAZ_COOKIE_SECURE` | `false` | V produkcii musí byť `true` (vyžaduje HTTPS) |
| `STRAZ_COOKIE_DOMAIN` | `null` | Doména pre zdieľané cookies medzi subdoménami |
| `STRAZ_SESSION_SECRET` | - | Kryptografický kľúč pre podpísané session cookies |
| `STRAZ_ADMIN_PASSWORD` | - | Počiatočné heslo administrátora |
| `DATABASE_URL` | - | Pripojovací reťazec do PostgreSQL (`postgresql+asyncpg://...`) |
| `REDIS_URL` | `redis://redis:6379/0` | Pripojenie do Redis pre ARQ worker, cache a rate-limiting |
| `NTFY_URL` | `https://ntfy.sh` | URL push notifikačného servera |
| `NTFY_TOPIC` | `""` | Názov témy pre push notifikácie na mobil |
| `VITE_API_URL` | `""` | Base URL backend API pre frontend (napr. na Verceli) |

---

## 🧪 Testovanie

Spustenie kompletnej backend testovacej sady (vyžaduje `uv`):
```bash
cd apps/api
uv run pytest -v
```

Spustenie frontend buildu a typovej kontroly:
```bash
cd apps/web
npm run build
```

---

## 📄 Licencia

Tento projekt je distribuovaný pod licenciou MIT. Viac informácií nájdete v súbore `LICENSE`.
