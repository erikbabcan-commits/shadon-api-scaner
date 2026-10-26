# ☁️ Návod na Nasadenie FastAPI Backendu do Cloudu & Prepojenie s Vercelom

Tento dokument poskytuje presný a overený postup, ako nasadiť backend **Stráž** (FastAPI + PostgreSQL + Redis + ARQ Background Worker) do autonómneho cloudového prostredia a prepojiť ho s produkčným **Vercel** frontendom.

---

## 🧭 Prehľad Možností Nasadenia

| Poskytovateľ | Typ | Čas nasadenia | Výhody | Odporúčané pre |
| :--- | :--- | :--- | :--- | :--- |
| **Railway** | PaaS (1-Click / CLI) | **3 minúty** | Najjednoduchšie, vstavaný Postgres & Redis, automatické SSL domény. | 🏆 Najrýchlejší štart |
| **Render** | PaaS (Blueprint) | **5 minút** | Riadené cez `render.yaml`, automatický build z GitHubu. | Stabilný PaaS |
| **VPS (Hetzner / DO)** | IaaS (Docker Compose) | **5 minút** | Plná kontrola, najnižšie náklady (€4-€7/mesiac), Caddy SSL. | Produkcia a enterprise |

---

## 🚀 Možnosť 1: Railway (Najrýchlejšie riešenie do 3 minút)

V repozitári je pripravený konfiguračný súbor [`railway.json`](../railway.json).

### Krok 1: Vytvorenie projektu v Railway
1. Prihláste sa na [railway.app](https://railway.app).
2. Kliknite na **"New Project"** -> **"Deploy from GitHub repo"**.
3. Vyberte repozitár: `erikbabcan-commits/shadon-api-scaner`.
4. V nastaveniach služby (Service Settings):
   - **Root Directory:** `/` (alebo nechajte predvolené, `railway.json` ukazuje na `apps/api/Dockerfile`).
   - Railway automaticky použije multi-stage Dockerfile.

### Krok 2: Pridanie PostgreSQL a Redis
V rovnakom Railway projekte:
1. Kliknite na **"+ New"** -> **"Database"** -> **"Add PostgreSQL"**.
2. Kliknite na **"+ New"** -> **"Database"** -> **"Add Redis"**.
3. Railway automaticky sprístupní premenné `DATABASE_URL` a `REDIS_URL` pre backend službu!
   *(Náš backend automaticky normalizuje tvar `postgres://` na `postgresql+asyncpg://`).*

### Krok 3: Nastavenie Premenných Prostredia na Railway
V nastaveniach API služby (Variables) doplňte:

```ini
STRAZ_ENV=production
STRAZ_COOKIE_SECURE=true
STRAZ_COOKIE_SAMESITE=none
STRAZ_ADMIN_EMAIL=admin@example.invalid
STRAZ_ADMIN_PASSWORD=heslo
STRAZ_SESSION_SECRET="$(openssl rand -hex 32)"
STRAZ_CORS_ORIGINS=https://straz-monitoring.vercel.app,https://web-flax-omega-55.vercel.app
APP_FRONTEND_URL=https://straz-monitoring.vercel.app
```

### Krok 4: Vygenerovanie verejnej domény
1. V záložke **Settings** -> **Networking** kliknite na **"Generate Domain"**.
2. Získate URL v tvare: `https://shadon-api-scaner-production.up.railway.app`.

---

## 🛠️ Možnosť 2: Render (Cez pripravený Blueprint)

V repozitári je pripravený Blueprint súbor [`render.yaml`](../render.yaml).

1. Otvorte [dashboard.render.com/blueprints](https://dashboard.render.com/blueprints).
2. Kliknite **"New Blueprint Instance"**.
3. Vyberte repozitár `erikbabcan-commits/shadon-api-scaner`.
4. Render automaticky načíta `render.yaml` a vytvorí:
   - Web Service: `straz-api`
   - Background Worker: `straz-worker`
   - Managed PostgreSQL: `straz-postgres`
   - Managed Redis: `straz-redis`
5. Kliknite **"Apply"**.
6. Po dobehnutí buildu získate verejnú URL API (napr. `https://straz-api.onrender.com`).

---

## 🖥️ Možnosť 3: Vlastný VPS cez Docker Compose (Hetzner, DigitalOcean)

Pre vlastný linuxový server (Ubuntu 22.04 / 24.04):

### Krok 1: Klonovanie a príprava
```bash
# Na VPS nainštalujte Docker & Docker Compose:
curl -fsSL https://get.docker.com | sh

# Klonujte repozitár:
git clone https://github.com/erikbabcan-commits/shadon-api-scaner.git /opt/straz
cd /opt/straz
cp .env.example .env
```

### Krok 2: Úprava `.env` pre VPS
```ini
STRAZ_ENV=production
STRAZ_DOMAIN=api.vasadomena.sk
ACME_EMAIL=admin@example.invalid
STRAZ_CORS_ORIGINS=https://straz-monitoring.vercel.app,https://web-flax-omega-55.vercel.app
STRAZ_COOKIE_SECURE=true
STRAZ_COOKIE_SAMESITE=none
STRAZ_ADMIN_EMAIL=admin@example.invalid
STRAZ_ADMIN_PASSWORD=heslo
STRAZ_SESSION_SECRET="$(openssl rand -hex 32)"
POSTGRES_PASSWORD="$(openssl rand -hex 32)"
DATABASE_URL=postgresql+asyncpg://straz:silne_db_heslo_123@postgres:5432/straz
REDIS_URL=redis://redis:6379/0
```

### Krok 3: Spustenie kontajnerov s Caddy SSL
```bash
cd /opt/straz/deploy
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```
Caddy automaticky vystaví platný Let's Encrypt SSL certifikát pre `api.vasadomena.sk`.

---

## 🔗 KROK 4: Prepojenie Vercel Frontendu s Cloud Backendom

Akonáhle backend beží a máte jeho verejnú HTTPS URL (napr. `https://straz-api.up.railway.app`):

### Spôsob A: Cez Vercel CLI (Okamžite z terminálu)
```bash
cd /Users/vorkei/Desktop/shadon-api-scaner/apps/web
vercel env add VITE_API_URL production --scope h4ck3d
# Na výzvu vložte URL backendu: https://straz-api.up.railway.app
vercel deploy --prod --yes --scope h4ck3d
```

### Spôsob B: Cez Vercel Web Dashboard
1. Otvorte [vercel.com/h4ck3d/straz-monitoring/settings/environment-variables](https://vercel.com/h4ck3d/straz-monitoring/settings/environment-variables).
2. Pridajte premennú:
   * **Key:** `VITE_API_URL`
   * **Value:** `https://straz-api.up.railway.app` *(nahraďte vašou reálnou cloud URL)*
   * **Environment:** Zaškrtnite **Production**, **Preview** aj **Development**.
3. Kliknite **Save**.
4. Spustite redeploy projektu:
   - V záložke **Deployments** kliknite na tri bodky `...` pri poslednom nasadení -> **Redeploy**.

---

## 🧪 Verifikačný Kontrolný Zoznam (Overenie funkčnosti)

Po prepojení otestujte:

1. **Health Probe:**
   ```bash
   curl -i https://tvoj-backend.up.railway.app/healthz/readiness
   # Musí vrátiť HTTP 200 s latenciami databázy a redisu
   ```
2. **Web Prihlásenie:**
   - Otvorte [https://straz-monitoring.vercel.app](https://straz-monitoring.vercel.app).
   - Už sa nezobrazí žiadna 404 chyba!
   - Zadajte `admin@example.invalid` a `heslo`.
   - Prihlásenie prebehne úspešne a ste priamo v systéme bez nutnosti lokálneho počítača.
