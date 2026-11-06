# STRÁŽ — release readiness, 6. 11. 2026

**Stav: pripravené lokálne opravy; produkčný release nie je uzavretý.**
Tento záznam neoznačuje produkciu za „AAA“ ani úplne zelenú. Úspešné lokálne
testy, historické CI a hlásenie Lovable sú odlišné dôkazy. Zmeny zatiaľ nie sú
potvrdené novým produkčným deploymentom.

Východiskový lokálny HEAD: `c5db6aeb9ae82839444076eeebd45c5ca5f6bc9b`, vetva
`feat/straz-m2m-runs-read`. Opravy nad týmto commitom sú pripravené na review vo vetve
`codex/production-readiness-20261106`; autoritatívny výsledný commit určuje HEAD pull requestu.

## Lokálne overené tímom

| Kontrola / zmena | Výsledok a rozsah |
|---|---|
| SQLite migrácie | Opravené názvy FK constraintov v migráciách 002 a 007; doplnené regresné testy. |
| Backend | Kompletná sada s izolovaným PostgreSQL **18.6** a Redisom: **132 passed, 0 skipped**. PostgreSQL 16 pre aktuálne zmeny zatiaľ neoverený. |
| Izolácia testov | Testovacie služby po kontrolách zastavené; lokálne vývojové API a Redis zostali zdravé. Produkčná databáza sa nepoužila. |
| M2M acceptance | **4 passed** po aktualizácii cesty stagingovej šablóny. |
| Frontend | Po `npm ci`: **19 testov prešlo**, TypeScript a Vite/PWA build skončili s exit 0. |
| Frontend runtime závislosti | `seroval` v lockfile aktualizovaný **1.6.7 → 1.7.7** bez zmeny manifestu; `npm audit --omit=dev` hlási **0 nálezov**. |
| Sanitizovaná šablóna | `deploy/.env.staging.example` premenovaná na `deploy/.env.example`; secret gate nebol oslabený. |
| Secret gate | Gitleaks **8.30.1**: syntetické testy odmietnutia a redakcie prešli; čistý export aktuálnych verzovaných zdrojov vrátane úprav prešiel tree scanom. |
| Lokálny commit hook | `git config --local core.hooksPath` je `.githooks`. Hook nenahrádza CI gate. |

Ignorované lokálne `.env` súbory obsahujú súkromnú konfiguráciu a nie sú release
artefaktom. Úspešný source tree scan nepotvrdzuje rotáciu historicky uniknutých
tajomstiev ani čistotu všetkých minulých commitov.

## Zmeny build konfigurácie a zostávajúce lokálne obmedzenia

- CI je zosúladené s Node.js 22; Docker konfigurácia používa frozen `uv.lock`
  a `npm ci`. Aktuálny cloud CI beh tým ešte nie je potvrdený.
- Celkový `npm audit` hlási **5 nálezov: 2 low, 3 moderate, 0 high/critical**,
  podľa klasifikácie auditu iba vo vývojovom reťazci PWA/Workbox. Runtime audit
  s `--omit=dev` je čistý; úplný dependency audit preto stále nie je bez nálezov.
- Otvorené dev advisories: Workbox → resolver → `deepmerge` **4.3.1**
  ([GHSA-gcqx-w48m-w2h4](https://github.com/advisories/GHSA-gcqx-w48m-w2h4),
  oprava zatiaľ nevydaná); Workbox → `glob` **11.1.0**
  ([GHSA-3g3m-2fjr-6pw4](https://github.com/advisories/GHSA-3g3m-2fjr-6pw4),
  oprava **14.0.2** mimo rozsahu `^11`); `glob` → `minimatch` **10.2.6**
  ([GHSA-g3hv-75wg-m249](https://github.com/advisories/GHSA-g3hv-75wg-m249),
  oprava **11.0.1** mimo rozsahu `^10`). Neboli použité force aktualizácie
  ani neoverené overrides cez major verzie.
- Zostavenie finálnych kontajnerových image a ich runtime kontrola nie sú týmto
  záznamom potvrdené.

## Lovable — hlásenie agenta, zatiaľ bez nezávislej akceptácie

Správny projekt: [Straz Security Beacon](https://lovable.dev/projects/64e9eb25-5f23-4709-8d7f-6d0ee0fde5c9).
Publikovaná adresa: https://straz-security-beacon.lovable.app.

Lovable agent hlási nastavenú verejnú `VITE_API_URL` na
`https://straz-api-production.up.railway.app` bez `/api`, serverovú same-origin
`/api/*` proxy s CSRF kontrolou a úspešných **33 testov**, TypeScript a build.
Ide o hlásenie z preview. Root ešte nezávisle overí proxy, cookies, organizácie,
streamy a odmietnutie cudzích originov pred publikovaním. V čase poslednej
verejnej kontroly publikované Lovable `/api/auth/me` stále vracalo **404 HTML**.
Browser kontrola a publikovanie momentálne čakajú na odomknutie lokálneho Macu.

## Verejne overená produkcia

| Cesta | Pozorovaný výsledok |
|---|---|
| Railway `/healthz/liveness` | **200**. |
| Railway `/healthz/readiness` | **200**, `ready=true`; databáza aj Redis `ok`. |
| Railway `/api/auth/me`, `/api/apps`, `/api/orgs`, `/api/findings`, `/api/runs` bez relácie | **401 JSON**, `Cache-Control: no-store`; žiadne tenantové dáta nevrátené. |
| Vercel `/` a `/api/auth/me` | **200 HTML** a **401 JSON** cez existujúcu proxy. |
| Lovable `/` a `/api/auth/me` | **200 HTML** a **404 HTML**; API prepojenie ešte nie je akceptované v publikovanej verzii. |
| Railway HTTP liveness | **301** na HTTPS. Priame HTTPS API odpovede však nemali HSTS; treba overiť nasadený kód a produkčné nastavenie. |

Verejné GET kontroly nepotvrdzujú produkčné prihlásenie, cookie atribúty,
tenantové hranice, worker, Alembic head ani účinnosť proxy trust konfigurácie.
Produkčný login, skeny a notifikácie sa počas týchto read-only kontrol nevykonali.

## GitHub a prístupy

- PR **#4 je MERGED od 27. 10. 2026**. Staršie checklisty vyžadujúce jeho merge
  už neopisujú aktuálny stav. `main` na `ce12ee5` mal historicky zelené CI;
  tento výsledok sa nevzťahuje na aktuálny release diff.
- Otvorený PR **#5** blokuje billing: „The job was not started because your
  account is locked due to a billing issue.“ Nie je to zlyhanie aplikačného testu
  ani úspešne vykonaná kontrola.
- Railway CLI vracia `Unauthorized` a dashboard zobrazuje Login. Aktuálne
  nasadené SHA API/workera, commit pin, premenné a prevádzkové dôkazy preto
  neboli potvrdené.

## Podmienky pred uzavretím release

1. Doriešiť alebo výslovne akceptovať zostávajúce dev advisories, dokončiť
   kontajnerové kontroly, skontrolovať finálny diff
   a získať nový overený commit s aktuálnymi CI výsledkami vrátane PostgreSQL 16/18.
2. Nezávisle overiť Lovable preview, publikovať overenú verziu a potvrdiť
   produkčné API prepojenie aj prihlásenie/cookies v prehliadači a na iPhone.
3. Obnoviť oprávnený Railway prístup; potvrdiť projekt `dev-new`, environment
   `production`, služby, ich SHA/pin, Alembic head, worker a produkčný režim/HSTS.
4. Doložiť stav rotácie historicky kompromitovaných tajomstiev, čerstvú súkromnú
   zálohu a izolovaný restore, alerty a proxy/limiter trust boundary podľa
   [prevádzkového postupu](OPERATIONS_ACCEPTANCE.md) a
   [incidentného runbooku](INCIDENT_ROTATION_RUNBOOK.md).
5. Osem externých CLI profilov ponechať zablokovaných, kým nebude dodaná a
   overená sieťová izolácia. Existencia opravy v zdrojoch sama nepotvrdzuje nasadenie.

Finálny release záznam doplniť skutočnými nasadenými SHA, časom deploymentu,
výsledkami aktuálnych kontrol a presným zoznamom zostávajúcich obmedzení.
Hodnoty tajomstiev, cookies a produkčné osobné dáta sem nepatria.
