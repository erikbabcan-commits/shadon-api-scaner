# Stráž — monitoring vlastných aplikácií (PWA + VPS)

Interná konzola: **Vite/React PWA** + **FastAPI/ARQ** na Docker Compose. Skeny bežia len proti overenému inventáru (žiadny voľný vstup IP).

## Stack

- Frontend: Vite, React, TanStack Router/Query, Tailwind 4, `vite-plugin-pwa`
- API: FastAPI, SQLAlchemy 2, Argon2 sessions
- Worker: ARQ + Redis; binárky `httpx`, `tlsx`, `nuclei` (ProjectDiscovery)
- DB: PostgreSQL
- Edge: Caddy (jeden origin `/` + `/api`)

## Rýchly štart (lokálne)

Predpoklad: Docker Desktop.

```bash
cd deploy
cp ../.env.example ../.env   # ak ešte nemáš .env
docker compose up --build
```

Otvor [http://localhost:8080](http://localhost:8080)

Default login (z `.env`):

- email: `admin@example.com`
- heslo: `change-me-now`

## Flow

1. **Aplikácie** → pridaj appku (base URL).
2. Na detaile appky over target:
   - DNS TXT: `straz-verify=<token>` na hostname, alebo
   - súbor `/.well-known/straz.txt` s tokenom, alebo
   - **Trust private** ak host padá do `TRUSTED_PRIVATE_NETS` (same-VPS / LAN).
3. Spusti **Heartbeat** (funguje aj pred verify).
4. Po verify: **TLS**, **HTTP**, **Nuclei safe**.
5. Nálezy v záložke **Nálezy**; behy v **Behy**.
6. Voliteľne nastav `NTFY_TOPIC` v `.env` pre push na telefón.

## Profily skenov

| Profil | Čo robí |
|--------|---------|
| `heartbeat` | HTTP GET, status, latencia, title |
| `tls` | `tlsx` — expirácia / mismatch |
| `http` | `httpx` — dostupnosť, tech |
| `safe` | `nuclei` tagy `misconfig,exposure,ssl,tech`; bez `dos,fuzz,intrusive` |

Worker berie len `run_id` / `target_id` z DB — nie raw host z request body.

## Dev bez Docker (API + Vite)

```bash
# API
cd apps/api
python -m venv .venv
.venv\Scripts\activate
pip install .
# nastav DATABASE_URL / REDIS_URL na lokálne služby
uvicorn app.main:app --reload --port 8000

# Worker
arq app.worker.WorkerSettings

# Web
cd apps/web
npm install
npm run dev
```

Vite proxy posiela `/api` na `http://127.0.0.1:8000`.

## VPS

1. Skopíruj repo, uprav `.env` (`STRAZ_COOKIE_SECURE=true`, silné heslo/secret, `NTFY_*`).
2. Pre HTTPS nahraď `deploy/Caddyfile` variantou s doménou (Caddy automatic HTTPS) alebo daj reverse proxy pred `:8080`.
3. `docker compose -f deploy/docker-compose.yml up -d --build`

## Bezpečnosť

- Skenuj len aplikácie, ktoré vlastníš.
- Nuclei safe profil je úmyselne neintrusívny.
- Jeden ťažký sken naraz (Redis lock).
- Audit log: login, verify, run, finding update.
