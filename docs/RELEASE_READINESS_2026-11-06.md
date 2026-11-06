# STRÁŽ — release readiness, 6. 11. 2026

**Stav: pripravené lokálne opravy; produkčný release nie je uzavretý.**
Tento záznam neoznačuje produkciu za „AAA“ ani úplne zelenú. Úspešné lokálne
testy, historické CI a hlásenie Lovable sú odlišné dôkazy. Lovable frontend je
publikovaný a verejné API prepojenie je overené; nové backendové opravy zatiaľ
nie sú potvrdené produkčným deploymentom.

Východiskový lokálny HEAD: `c5db6aeb9ae82839444076eeebd45c5ca5f6bc9b`, vetva
`feat/straz-m2m-runs-read`. Opravy nad týmto commitom sú pripravené na review vo vetve
`codex/production-readiness-20261106`; autoritatívny výsledný commit určuje HEAD pull requestu.
Následné billing/staging opravy sú pushnuté v commite
`f263da5fb38d1cf7b01689775d5e3369bbbb0126` v
[PR #6](https://github.com/erikbabcan-commits/shadon-api-scaner/pull/6), ktorý je
otvorený a pripravený na review (`isDraft: false`). Staršie výsledky nižšie sú
priradené ku konkrétnym commitom; nenahrádzajú CI aktuálneho HEAD.

## Lokálne overené tímom

| Kontrola / zmena | Výsledok a rozsah |
|---|---|
| SQLite migrácie | Opravené názvy FK constraintov v migráciách 002 a 007; doplnené regresné testy. |
| Backend | Python **3.12.13** s izolovaným PostgreSQL **16.15** aj **18.6**, zakaždým s vlastným Redisom: v každej vetve **132 passed, 0 skipped**. Overené na `5a6186f`, lokálne macOS ARM64; nejde o cloud Linux CI. |
| Izolácia testov | Testovacie služby po kontrolách zastavené; lokálne vývojové API a Redis zostali zdravé. Produkčná databáza sa nepoužila. |
| Následné billing opravy | **12 passed** v cielenom M2M/billing/audit/health výbere na Python 3.14.6; ďalší beh **4 passed** s kontrolou obnovenia cached nastavení. Simulácia je default-off, produkcia ju vždy odmietne, existujúce Stripe predplatné sa nemení a úspešná simulácia audituje pôvodný/nový plán. |
| Izolovaný staging | Compose **5.7.0** config render potvrdil iba dva loopback porty a API/worker env súbor `.env.staging`; prázdna šablóna bola odmietnutá. Overlay používa `!override`, vyžaduje Compose 2.24.4+. Kontajnery sa nespustili. |
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
  záznamom potvrdené. Nainštalované sú nástroje Docker, Colima a Lima; samotná
  inštalácia nie je build image. Pre tlak na pamäť a swap sa Docker VM nespustila
  a kontajnerový build sa nevykonal.
- Vercel konektor potvrdil dve **READY preview** nasadenia presného commitu `5a6186f`:
  [shadon-api-scaner](https://shadon-api-scaner-21aq18ywc-somnajviac.vercel.app)
  a [web](https://web-5vbuxvav8-somnajviac.vercel.app). Majú `target: null`, teda nejde
  o produkčný deploy. Verejné GET vracajú 302 na Vercel SSO; aplikačné správanie
  za Deployment Protection tým ešte nebolo overené. Ochrana ani zdieľanie sa nemenili.

## Lovable — publikované prepojenie a nezávislé overenie

Správny projekt: [Straz Security Beacon](https://lovable.dev/projects/64e9eb25-5f23-4709-8d7f-6d0ee0fde5c9).
Publikovaná adresa: [straz-security-beacon.lovable.app](https://straz-security-beacon.lovable.app).

Finálny export nezávisle potvrdil verejnú `VITE_API_URL` na
`https://straz-api-production.up.railway.app` bez `/api` a bez ďalších env kľúčov.
Browser volá relatívne `/api/*`; serverová same-origin proxy používa pevný HTTPS
upstream a pred mutáciami kontroluje presný Origin aj X-Requested-With. Health
proxy povoľuje iba presné `/healthz/liveness` a `/healthz/readiness` cez GET/HEAD,
bez odovzdania cookies. Proxy prúdi telá požiadaviek a odpovedí, odovzdáva abort
signál, správne vyhodnocuje relatívne redirecty a na HTTPS dopĺňa Secure cookies.

Lovable agent v preview deklaroval **40 úspešných testov**, TypeScript a build.
Tieto cloudové výsledky sme lokálne neopakovali. Nezávisle sme vykonali skutočné
súbory finálneho exportu: **51/51** kontrol API proxy a **6/6** reálnych lokálnych
HTTP transportov na Node **22.23.4**, plus **18/18** kontrol health rout, cookies
a serverových hlavičiek na Bun **1.4.4**; spolu **75/75**. Syntetické tenantové
hlavičky a cookies nepotvrdzujú produkčné tenantové hranice ani prihlásenie.

Po publikovaní UI zobrazilo „Published“ a aktuálnu verziu. Verejná kontrola
**6. 11. 2026 o 02:32:43 UTC** cez curl s User-Agent `Mozilla/5.0` prešla
**12/12** kontrolami; podrobnosti obsahuje
[sanitizovaný JSON dôkaz](evidence/lovable-production-2026-11-06.json).
Produkčné API už vracia **401 JSON**, health **200 JSON**, cudzie/chýbajúce Origin
na logout **403** a nepovolené health metódy **405**. API/health odpovede majú
`no-store, private`; všetkých 12 odpovedí malo HSTS, nosniff, Referrer-Policy,
X-Frame-Options DENY a CSP Report-Only. CSP Report-Only na HTML zatiaľ iba
reportuje porušenia, nevynucuje túto politiku.

Bez prihlasovania sa neoverili reálne session cookies ani iPhone. Produkčné
skeny a notifikácie sa nespúšťali. V cloudovom `AGENTS.md` zostáva doplniť
poznámku o health routách; funkčné routy sú vo finálnom exporte aj produkcii.

## Verejne overená produkcia

| Cesta | Pozorovaný výsledok |
|---|---|
| Railway `/healthz/liveness` | **200**. |
| Railway `/healthz/readiness` | **200**, `ready=true`; databáza aj Redis `ok`. |
| Railway `/api/auth/me`, `/api/apps`, `/api/orgs`, `/api/findings`, `/api/runs` bez relácie | **401 JSON**, `Cache-Control: no-store`; žiadne tenantové dáta nevrátené. |
| Vercel `/` a `/api/auth/me` | **200 HTML** a **401 JSON** cez existujúcu proxy. |
| Lovable `/` a `/api/auth/me` | **200 HTML** a **401 JSON**; publikované same-origin API prepojenie overené 6. 11. 2026 o 02:32:43 UTC. |
| Lovable `/healthz/liveness`, `/healthz/readiness`, `/healthz/other` | **200 JSON**, **200 JSON** s `ready=true`, **404 JSON**; všetky `no-store, private`. |
| Lovable odmietnuté požiadavky | Logout POST bez Origin aj s cudzím Origin **403 JSON**; health POST/PUT/PATCH/DELETE/OPTIONS **405 JSON**; všetky `no-store, private`. |
| Lovable bezpečnostné hlavičky | Všetkých 12 kontrol: HSTS, nosniff, Referrer-Policy, X-Frame-Options DENY a CSP Report-Only. |
| Railway HTTP liveness | **301** na HTTPS. Priame HTTPS API odpovede však nemali HSTS; treba overiť nasadený kód a produkčné nastavenie. |

Verejné GET kontroly nepotvrdzujú produkčné prihlásenie, cookie atribúty,
tenantové hranice, worker, Alembic head ani účinnosť proxy trust konfigurácie.
Produkčný login, skeny a notifikácie sa počas týchto kontrol nevykonali; vykonané
POST/PUT/PATCH/DELETE kontroly boli výhradne požiadavky odmietnuté proxy.

## GitHub a prístupy

- PR **#4 je MERGED od 27. 10. 2026**. Staršie checklisty vyžadujúce jeho merge
  už neopisujú aktuálny stav. `main` na `ce12ee5` mal historicky zelené CI;
  tento výsledok sa nevzťahuje na aktuálny release diff.
- Otvorený PR **#5** blokuje billing: „The job was not started because your
  account is locked due to a billing issue.“ Nie je to zlyhanie aplikačného testu
  ani úspešne vykonaná kontrola.
- Rovnakú billing annotation priamo potvrdil nový
  [CI beh PR #6](https://github.com/erikbabcan-commits/shadon-api-scaner/actions/runs/42141731629)
  na `3dac520` (check `127643411379`): žiadne kroky sa nevykonali, backend a
  frontend boli preskočené. Predchádzajúci beh `42141257570` na `5a6186f` mal
  rovnaký billing blok; ani jeden nie je úspešným testovaním release.
- Aj [beh na `f263da5`](https://github.com/erikbabcan-commits/shadon-api-scaner/actions/runs/42151682188)
  skončil tým istým billing blokom: check `127676161738` mal nula krokov,
  backend a frontend boli preskočené. Na odblokovanie treba zásah vlastníka účtu.
- Oprávnený prístup do Railway dashboardu bol obnovený cez existujúce GitHub
  prihlásenie; CLI naďalej vracia `Unauthorized`. Dashboard potvrdil projekt
  `dev-new`, environment `production` a štyri online služby (API, worker,
  PostgreSQL, Redis). Aktívna karta API ukazuje starý deployment z merge PR **#3**,
  nie aktuálne opravy PR #6. Read-only konzola API potvrdila runtime SHA
  `83a25c30bdcc14021a4664bcafab5d6198745699`, Python **3.12.15**, režim
  `production`, `straz_cookie_secure=true` a `straz_cookie_samesite=none`.
  Toto nie je overenie skutočnej prihlasovacej cookie. Interpreter aplikácie je
  `/opt/venv/bin/python`; systémový Python nemá aplikačné závislosti.
  Následný výstup Railway konzoly dodaný používateľom potvrdil PostgreSQL
  **18.6 (Debian)** a revíziu **008_postgres_uuid_and_audit_fk**. Release zdroje
  obsahujú aj revíziu 009; produkčný upgrade sa počas kontroly nevykonal.
  Premenná `STRAZ_TRUSTED_PROXY_IPS` podľa tohto výstupu nie je nastavená.
  Skoršia kontrola neexistujúceho atribútu `straz_trusted_proxy_cidrs` sama
  o sebe nebola dôkazom proxy trust konfigurácie. Allowlist treba odvodiť
  od skutočného ingressu a overiť, nie nastaviť slepo na všetky adresy.
  Presné runtime SHA workera, ďalšie nastavenia a prevádzkové dôkazy zostávajú
  nezískané.

## Podmienky pred uzavretím release

1. Doriešiť alebo výslovne akceptovať zostávajúce dev advisories, dokončiť
   kontajnerové kontroly, skontrolovať finálny diff
   a získať nový overený commit s aktuálnymi CI výsledkami vrátane PostgreSQL 16/18.
2. Doplniť overenie produkčného prihlásenia/cookies v prehliadači a na iPhone.
   Publikovanie Lovable a verejné API prepojenie sú overené vyššie.
3. Cez obnovený Railway dashboard prístup overiť worker, ingress trust boundary,
   HSTS a bezpečný upgrade potvrdenej revízie 008 na aktuálny head 009;
   následne overiť nasadenie aktuálnych backendových opráv. Stav CLI prihlásenia
   zostáva nevyriešený.
4. Doložiť stav rotácie historicky kompromitovaných tajomstiev, čerstvú súkromnú
   zálohu a izolovaný restore, alerty a proxy/limiter trust boundary podľa
   [prevádzkového postupu](OPERATIONS_ACCEPTANCE.md) a
   [incidentného runbooku](INCIDENT_ROTATION_RUNBOOK.md).
5. Osem externých CLI profilov ponechať zablokovaných, kým nebude dodaná a
   overená sieťová izolácia. Existencia opravy v zdrojoch sama nepotvrdzuje nasadenie.

Finálny release záznam doplniť skutočnými nasadenými SHA, časom deploymentu,
výsledkami aktuálnych kontrol a presným zoznamom zostávajúcich obmedzení.
Hodnoty tajomstiev, cookies a produkčné osobné dáta sem nepatria.
