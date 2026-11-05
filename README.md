# STRÁŽ — monitoring a API scanner

[![CI Pipeline](https://github.com/erikbabcan-commits/shadon-api-scaner/actions/workflows/ci.yml/badge.svg)](https://github.com/erikbabcan-commits/shadon-api-scaner/actions/workflows/ci.yml)

**Vybraný základ k 5. 11. 2026:** [erikbabcan-commits/shadon-api-scaner](https://github.com/erikbabcan-commits/shadon-api-scaner), vetva **main**, aplikačný commit **ce12ee556b68b36d9232938b173c6cf09216ec67** z 28. 10. 2026. Všetkých šesť ostatných existujúcich vetiev je jeho predkom. Dokumentačná vetva `docs/lovable-hetzner-20261105` vychádza z tohto commitu.

**Cieľ:** frontend upravovaný v Lovable, backend FastAPI + ARQ + PostgreSQL + Redis na Hetzner VPS. Presun infraštruktúry a nastavenie Stripe patria do druhého kroku; táto aktualizácia dokumentácie ich nevykonáva.

## Čo je overené

| Oblasť | Dôkaz a jeho hranica |
|---|---|
| Backend | 127 úspešných testov na PG 16 a tá istá sada 127 testov na PG 18 |
| Frontend | 19 testov, úspešný TypeScript a Vite build |
| Secret gate | Úspešný samostatný CI job; nepreukazuje rotáciu historických tajomstiev |
| Živá infraštruktúra | 5. 11. 2026: readiness cez Vercel HTTP 200, DB aj Redis `ok`; priamy backend liveness HTTP 200 a `/api/auth/me` bez relácie HTTP 401 |
| Nasadený frontend | Vercel `straz-monitoring` uvádza commit `7b0ae28`, starší než vybraný kód |
| Aktuálny backend/worker SHA | Neoverený; health endpoint nepreukazuje commit, migrácie ani priechod úlohy workerom |

Výsledky testov pochádzajú z [CI runu 40650162205](https://github.com/erikbabcan-commits/shadon-api-scaner/actions/runs/40650162205) na `ce12ee5`, nie z nového lokálneho spustenia ani z browserového E2E.

## Dostupné funkcie a obmedzenia

- Organizácie, členstvo, roly `owner/admin/member/viewer`, pozvánky a prepínanie workspace.
- Inventár aplikácií, overovanie cieľov, behy, nálezy, audit a alert kanály.
- **Povolené profily:** `heartbeat` a `internetdb`, podľa kvót a požiadaviek na overenie cieľa.
- **Blokované profily:** `tls`, `http`, `safe`, `subdomain`, `ports`, `trivy_fs`, `trivy_image`, `gitleaks`. Blokovanie platí aj pre platené plány, API a worker. Inštalácia binárky ani zmena plánu ho nerieši.
- CVSS v3.1, SARIF 2.1.0, formula-safe CSV a HTML report vhodný na tlač do PDF.
- **PoC endpoint nevykonáva príkaz ani sieťový test.** Kontroluje iba prefix `curl`; jeho `verified=true` a `status_code=200` nie sú dôkazom zraniteľnosti alebo HTTP odpovede cieľa.
- Scoped API kľúče a CI brána existujú. Predvolený CI profil `safe` je blokovaný; pre povolený tok musí klient uviesť vhodný profil.
- Stripe a kvóty sú v kóde, nastavenie platieb je odložené. Produkčný checkout bez kľúča vracia 503.

Mapovanie reportov na oblasti NIS2 je orientačná funkcia, nie certifikácia alebo dôkaz právneho súladu. Auditné triggery nie sú ochranou pred privilegovaným správcom databázy.

## Architektúra

| Časť | Zdroj | Úloha |
|---|---|---|
| Frontend | `apps/web` | React 19, Vite 6, TypeScript, Tailwind 4, TanStack, PWA |
| API | `apps/api/app` | Python 3.12+, FastAPI, SQLAlchemy async, podpísané HttpOnly session cookies |
| Worker | `apps/api/app/worker.py` | ARQ, Redis, naplánované a manuálne úlohy; nejde o Celery |
| Dáta | Alembic 001–009, PostgreSQL | Organizácie, nálezy, audit, kvóty a billing |
| Ingress | `deploy/Caddyfile*`, `apps/web/vercel.json` | HTTPS a smerovanie; aktuálne Vercel rewrite stále mieri na Railway |

Hlavný scanner nepotrebuje Supabase. Projekty GUARD a API Hub majú vlastné integračné mosty; ich databázy, prihlasovanie a frontend nie sú náhradou tohto backendu.

## Dokumentácia

Začni v [indexe dokumentácie](docs/README.md).

| Potreba | Dokument |
|---|---|
| Výber repozitára, vetiev a nasadení | [PROJECT_STATUS.md](docs/PROJECT_STATUS.md) |
| Prenos frontendu do Lovable | [LOVABLE_FRONTEND.md](docs/LOVABLE_FRONTEND.md) |
| Plán backendu na Hetzneri | [HETZNER_BACKEND.md](docs/HETZNER_BACKEND.md) |
| Premenné a cookies | [ENVIRONMENT.md](docs/ENVIRONMENT.md) |
| Existujúce API a scope | [API_CONTRACT.md](docs/API_CONTRACT.md) |
| Akceptácia a prevádzka | [OPERATIONS_ACCEPTANCE.md](docs/OPERATIONS_ACCEPTANCE.md) |
| Historický incident a tajomstvá | [INCIDENT_ROTATION_RUNBOOK.md](docs/INCIDENT_ROTATION_RUNBOOK.md), [SECRET_SCAN.md](docs/SECRET_SCAN.md) |

## Lokálny vývoj

Vyžaduje Python 3.12+, `uv`, Node kompatibilný s lockfile a npm. CI uvedeného commitu používalo Node 20; Docker frontend používa Node 22. Zjednotenie runtime na podporovanú LTS a reprodukovateľných Docker buildov je úloha pre druhý krok.

V API priečinku skopíruj sanitizovanú šablónu a **pred štartom súkromne vyplň** databázu, bootstrap heslo a session secret podľa [ENVIRONMENT.md](docs/ENVIRONMENT.md). Hodnoty v dotenv sú literály; shellové `$(...)` sa v nich nevykonáva.

```bash
git clone https://github.com/erikbabcan-commits/shadon-api-scaner.git
cd shadon-api-scaner
git switch main
cd apps/api
uv sync --frozen --dev
cp .env.example .env
```

Po vyplnení konfigurácie spusti PostgreSQL a Redis. Pred prvým štartom API aj workera vykonaj migrácie proti vývojovej databáze:

```bash
uv run --frozen python -m app.migrations upgrade
uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Worker v druhom termináli z `apps/api`:

```bash
uv run --frozen arq app.worker.WorkerSettings
```

Frontend v ďalšom termináli z koreňa:

```bash
cd apps/web
npm ci --ignore-scripts
npm run dev
```

Vite štandardne smeruje `/api` na `127.0.0.1:8000`; cieľ možno zmeniť cez `VITE_DEV_API_PROXY`. Samostatný proxy pre `/healthz` lokálny Vite config nedefinuje. SQLite je vhodný pre izolované testy; nepreukazuje PostgreSQL migrácie ani produkčnú prevádzku.

## Overenie zmien

```bash
cd apps/api
uv run --frozen pytest -v
```

Úplná sada má mať izolovaný PostgreSQL a Redis, vrátane `STRAZ_TEST_PG_URL` a `QUOTA_REDIS_URL`; presné nastavenie je v [.github/workflows/ci.yml](.github/workflows/ci.yml).

```bash
cd apps/web
npm test
npm run build
npx --no-install tsc --noEmit
```

Nasadenie sa uzatvára až s konkrétnymi SHA, migráciami, worker testom, backup/restore a prekliknutím loginu vrátane Safari/PWA. Zelené CI samo tieto kroky nepotvrdzuje.

## Licencia

V overenom strome nie je súbor `LICENSE`. Licenčné podmienky treba doplniť rozhodnutím vlastníka; historický MIT badge nebol dostatočný podklad.
