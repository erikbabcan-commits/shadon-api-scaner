# STRÁŽ — premenné prostredia a session

Overené voči `apps/api/app/config.py`, Docker/Compose a frontendovému klientovi na `ce12ee5`.
Súbory `.env.example` sú sanitizované šablóny, nie hotová konfigurácia.

## Backend

| Premenná | Význam / formát |
|---|---|
| DATABASE_URL | Súkromný async SQLAlchemy DSN; PostgreSQL asyncpg. postgres:// a postgresql:// sa normalizujú |
| REDIS_URL | Súkromná adresa Redisu pre API aj ARQ worker |
| STRAZ_ENV | production pri reálnom nasadení; development lokálne |
| STRAZ_ADMIN_EMAIL | Bootstrap identita; bez osobného predvyplneného účtu v šablóne |
| STRAZ_ADMIN_PASSWORD | Bootstrap heslo; existujúce DB heslo týmto nezmeníš |
| STRAZ_SESSION_SECRET | Náhodný podpisovací secret minimálne 32 znakov; v produkcii sa odmietajú krátke a change-me hodnoty |
| STRAZ_COOKIE_SECURE | true pre produkčné HTTPS |
| STRAZ_COOKIE_SAMESITE | lax pri overenej same-site/same-origin topológii; none iba pre potrebný cross-site s HTTPS |
| STRAZ_COOKIE_DOMAIN | Pri secure režime ju auth kód ignoruje a host cookie nemá Domain |
| STRAZ_COOKIE_NAME | Základ názvu cookie, predvolene straz_session; secure pridáva __Host- |
| STRAZ_SESSION_MAX_AGE | Sekundy, predvolene 14 dní; revokáciu rieši aj token_version |
| STRAZ_CORS_ORIGINS | **CSV reťazec presných originov**, napr. http://localhost:5173,http://127.0.0.1:5173 |
| APP_FRONTEND_URL | Verejný frontendový origin, dôležitý aj pre billing návraty |
| STRAZ_TRUSTED_PROXY_IPS | Shellová vstupná hodnota Uvicorn --forwarded-allow-ips; nie Pydantic setting; iba overené proxy |
| TRUSTED_PRIVATE_NETS | Zoznam CIDR pre výslovný private trust; neodblokuje CLI skenery |
| HEARTBEAT_INTERVAL_MINUTES | Predvolený interval 5 minút |
| NUCLEI_WEEKLY_CRON / SUPPLY_CHAIN_WEEKLY_CRON | Existujúce scheduler nastavenia; blokované profily zostávajú blokované |
| INTERNETDB_BASE_URL / INTERNETDB_CACHE_TTL | Pasívny zdroj a cache; predvolený TTL 86400 s |
| NTFY_URL / NTFY_TOPIC / NTFY_TOKEN | Voliteľný notifikačný kanál; token zostáva iba na backende |

`CORS_ORIGINS` nie je názov settingu tejto aplikácie.
JSON pole v `STRAZ_CORS_ORIGINS` je nesprávne: config rozdeľuje obyčajný CSV reťazec.
Nezamieňať oprávnené originy s cestou `/api`, koncovou lomkou alebo wildcardom.

Produkčná session je podpísaná HttpOnly cookie z itsdangerous, nie JWT.
S `STRAZ_COOKIE_SECURE=true` je názov `__Host-straz_session`, Path=/, Secure a bez Domain.
Cross-site `SameSite=None` nevyrieši browserom zakázané third-party cookies.

## Compose/ingress hodnoty

| Premenná | Konzument |
|---|---|
| POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB | Inicializácia PostgreSQL kontajnera; zosúladiť s DATABASE_URL |
| STRAZ_DOMAIN | Interpolácia Compose a Caddy site; samotné env_file na službe nestačí |
| ACME_EMAIL | ACME kontakt v HTTPS Caddy konfigurácii |
| BACKUP_DIR / RETENTION_DAYS | Existujúci backup skript; nastavenie a restore sú samostatné úlohy |

Zmena `POSTGRES_PASSWORD` pri už inicializovanom volume sama nerotuje databázovú rolu.
Použiť `--env-file ../.env` pre Compose interpoláciu z deploy priečinka.
Plný `docker compose config` môže vypísať tajomstvá; pre syntax použiť `config --quiet`.

## Frontend

| Premenná | Význam |
|---|---|
| VITE_API_URL | Verejný backend origin bez /api, vložený pri builde; prázdny znamená relatívne API |
| VITE_DEV_API_PROXY | Lokálny Vite proxy target, predvolene http://127.0.0.1:8000 |

Na `*.vercel.app` kód vynucuje relatívne API aj pri nastavenej VITE_API_URL.
Zmena cieľa v tomto prípade patrí do proxy rewrites. Na Lovable/custom hoste sa používa VITE_API_URL.
Žiadne DB, admin, session ani Stripe tajomstvo nesmie mať prefix VITE_.

## Stripe — až druhý krok

Skutočné názvy sú:
`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_STARTER`,
`STRIPE_PRICE_PRO`, `STRIPE_PRICE_AGENCY`.

Staršie názvy `STRIPE_PRICE_PRO_MONTHLY/YEARLY` a `STRIPE_PRICE_ENTERPRISE_*`
sa v Settings nepoužívajú. V šablónach sú aktuálne billing hodnoty prázdne.
Produkčný checkout/portal bez kľúča a webhook bez secretu vracajú 503; nejde o overené platby.
Kvóty a obmedzenia Free účtu ostávajú platné aj pri odloženom Stripe.

## Bezpečné vyplnenie

1. Súkromný .env vytvoriť iba v určenom pracovnom/serverovom prostredí s obmedzenými právami.
2. Vyplniť DSN, bootstrap email/heslo, session secret, Redis a konkrétne originy.
3. Náhodné hodnoty generovať správcom tajomstiev alebo lokálnym bezpečným generátorom.
   Do dotenv uložiť výslednú hodnotu; text `$(openssl ...)` je literál, nie spustený príkaz.
4. Do Gitu, Notion ani handoff ZIP nepridať .env, heslá, podpisové kľúče, sessions alebo DB dumpy.
5. V produkcii musí API aj worker používať zhodnú DB, Redis a schválené SHA; overiť startup a migrácie.

Izolované testy používajú navyše `STRAZ_TEST_PG_URL` a `QUOTA_REDIS_URL`.
Tieto adresy musia smerovať výlučne na testové služby podľa CI.
