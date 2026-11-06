# STRÁŽ — release readiness, 6. 11. 2026

**Stav: pripravené lokálne opravy; produkčný release nie je uzavretý.**
Tento záznam neoznačuje produkciu za „AAA“ ani úplne zelenú. Úspešné lokálne
testy, historické CI a hlásenie Lovable sú odlišné dôkazy. Lovable frontend je
publikovaný a verejné API prepojenie je overené; nové backendové opravy zatiaľ
nie sú potvrdené produkčným deploymentom.

## Aktuálny backendový kandidát 8c78029

Kandidát očakáva schému **010_alert_outbox_leases**. Produkčné nasadenie ani
rotácia sa nevykonali. Staršie výsledky nižšie patria svojim uvedeným commitom.

- **255 passed, 0 skipped** na PostgreSQL 16.15 aj 18.6, Python 3.12.13 a vždy
  samostatný Redis. Súbory sa počas finálneho behu nemenili; runner to kontroluje
  hashmi pred aj po testovaní. Rozsah je SQLite API + reálne PG migrácie/locking
  + Redis + lokálny TLS receiver, nie všetky API testy na PostgreSQL.
  [Finálna matica](evidence/backend-recovery-matrix-2026-11-06.json).
- Nové plánovanie rešpektuje efektívny plán, UTC okná, kvótu a aktívne profily.
  Free nečerpá kvótu automatickým heartbeat. PG org lock a auditovaný durable
  admission bránia duplicitnému scheduler admission; nejde o globálny mutex
  pre manuálne skeny. [Presný kontrakt](SCHEDULING_AND_NOTIFICATIONS.md).
- Outbox má fenced lease, najviac 5 pokusov a obnovu po páde. Skutočný lokálny
  HTTPS test dokázal 503 → retry → 200 pri overovanom TLS, HMAC a stabilnom ID.
  Nepotvrdzuje doručenie produkčnému príjemcovi ani exactly-once záruku.
- Reálna produkčná záloha bola znovu obnovená do izolovaného Unix-only PG18
  a posunutá 008 → 010. Zachované pôvodné dáta 15 aplikačných tabuliek a audit;
  pracovná kópia bola odstránená, archív zostal súkromný a produkcia sa nemenila.
  [Dôkaz](evidence/production-restore-010-2026-11-06.json).
- Ruff 0.17.4 F/E9 prešiel, Mypy 2.4.1 prešiel 50 zdrojových súborov v predvolenom
  režime (nie strict). API/worker/legacy frontend image boli zostavené pre AMD64
  z čistého exportu kandidáta. [Buildy](evidence/container-builds-recovery-2026-11-06.json),
  [statické a lokálne kontroly](evidence/recovery-quality-checks-2026-11-06.json).
- Finálne kontajnerové overenie prešlo **34/34**: reálna DB/Redis/ARQ cesta,
  automatický scheduler run a deduplikácia opakovaného ticku, session/API-key
  hranice a startup odmietnutia 008/009/010 medzi novými a historickými image.
  Vlastné kontajnery a sieť boli odstránené. Syntetické dáta a lokálny platený
  fixture nie sú produkčný deployment ani reálna platba.
  [Dôkaz](evidence/container-runtime-recovery-2026-11-06.json).
- Child procesy majú spoločný limit výstupu 4 MiB a POSIX group cleanup pri
  timeout/cancel; 17 reálnych procesných regresií. To nenahrádza sieťovú a
  filesystem izoláciu ôsmich CLI profilov, ktoré zostávajú zablokované.

## Predchádzajúce opravy a ich overenie

- `f806cb6`: výpadok InternetDB, neplatná/čiastočná odpoveď alebo DNS chyba už
  nepredstierajú úspešný sken a neuzavrú staré high nálezy. Regresie vykonávajú
  skutočný API → worker → parser → DB → CI tok s mockovaným wire/DNS, vrátane
  rollbacku prvého úspešného IP pri zlyhaní druhého. Nových **26 testov** prešlo;
  pred opravou **13 zlyhalo**. Širší cielený výber prešiel **96/96**.
- `cadda1a` a `3777a37`: backendové JSON/HTML reporty a legacy UI už neodvodzujú
  A+100 ani právnu zhodu z nuly nálezov alebo jedného heartbeat. Zachované sú
  nálezy a technické pozorovania, limity sú zobrazené aj pri white-label reportoch.
  Rovnaká oprava primárneho frontendu je pripravená v jeho samostatnej vetve.
- Kompletná backendová sada: **175 passed, 0 skipped** pri PostgreSQL **16.15** aj
  **18.6**, Python **3.12.13**, vždy vlastné dočasné služby. Rozsah je SQLite API
  unit + skutočné PG migrácie/cutover + Redis quota, nie všetky API testy na PG.
  [Nový dôkaz s 91 hashmi](evidence/backend-quality-matrix-2026-11-06.json).
  [Verzovaný runner a presný postup](LOCAL_VERIFICATION.md) umožňujú zopakovanie.
  Zdrojové app/test súbory sa počas testov nemenili; príznak dirty tree označuje
  rozpracované release podklady. Kandidát `3777a37` má rovnaký runtime kód ako
  `318845a`, ktorý mení len zápis logov testovacieho runnera.
- Legacy frontend na Node 22: **22/22**, TypeScript a build úspešné.
- Primárny frontend má [otvorený PR #3](https://github.com/youh4ck3dme/straz-security-beacon/pull/3),
  HEAD `62db740`: reporty bez nepodloženého skóre a opravený PWA client output.
  **77/77**, TypeScript a oba reálne buildy (`.output/public` aj Lovable `dist/client`)
  prešli. Oba generujú **23 statických precache položiek** vrátane offline stránky;
  generovaný worker overuje NetworkOnly pre API/health, reporty/CSV a HTML navigácie.
  [Nové CI presného SHA](https://github.com/youh4ck3dme/straz-security-beacon/actions/runs/42202424387)
  je **SUCCESS** vrátane post-build SW validátora. [Sanitizovaný dôkaz](evidence/frontend-quality-2026-11-06.json).
  PR ešte nie je zlúčený/publikovaný; tento výsledok nenahrádza fyzický iPhone test.
- Všetky tri nové image z čistého exportu `3777a37` boli úspešne zostavené pre
  Linux AMD64; [presné image ID a Dockerfile hashe](evidence/container-builds-quality-2026-11-06.json).
  [Nový runtime tok prešiel 28/28](evidence/container-runtime-quality-2026-11-06.json):
  API → Redis → skutočný ARQ worker → PG 18.6, session/API key/tenant hranice,
  logout a nový JSON aj HTML kontrakt reportov bez vymysleného skóre. Worker/API
  sú non-root a nemajú pytest/aiosqlite. Platená fixture je iba syntetická.
  [Actual asset command prešiel 5/5](evidence/legacy-assets-quality-2026-11-06.json).
  Všetky vlastné testovacie kontajnery a sieť boli odstránené; produkcia sa nemenila.
- [Čerstvých šesť produkčných HTTPS sond](evidence/production-health-refresh-2026-11-06.json)
  opäť potvrdilo liveness/readiness 200 a unauthenticated me 401 na oboch doménach.
  Priame Railway API stále nemá HSTS, Lovable odpovede ho majú. Samotné zdravé
  sondy neznamenajú nasadenie nových opráv.

## Predchádzajúce nezávislé overenie

Nižšia tabuľka zachováva overený kontajnerový snapshot
`1e2db87cad8337da8c97b4cc3ed74a168e52c70e`. Novšie runtime opravy uvedené samostatne
vyžadujú svoje vlastné výsledky. Žiadny lokálny dôkaz neznamená produkčný deployment.

| Kontrola | Výsledok a rozsah |
|---|---|
| Backendová sada | **144 passed, 0 skipped**, samostatne pri PostgreSQL 16.15 aj 18.6, Python 3.12.13 a vlastný Redis. Sada kombinuje SQLite API unit testy s reálnymi PostgreSQL migračnými/cutover a Redis quota testami; nejde o 144 API testov na PostgreSQL. [Dôkaz a hashe súborov](evidence/backend-final-matrix-2026-11-06.json). |
| Produkčné prihlásenie | **11/11 HTTPS kontrol** cez publikovanú Lovable proxy: existujúci účet sa prihlásil, me/orgs/apps/findings/runs boli 200, náhodná nečlenská organizácia a cudzí Origin boli odmietnuté. Cookies boli Secure/HttpOnly. Ide o HTTP klienta, nie iPhone test ani test dvoch existujúcich tenantov. [Dôkaz bez identity a tokenov](evidence/production-auth-2026-11-06.json). |
| Relácia v Chrome | Následná UI kontrola na publikovanej Lovable doméne zobrazila autentifikovaný pracovný priestor vlastníka a detail jeho aplikácie. Karta zostala otvorená s aktívnou reláciou podľa požiadavky používateľa. Logout, uloženie hesla ani zmena účtu sa nevykonali. |
| Reálna produkčná záloha | Custom-format PostgreSQL 18.6 záloha revízie 008 uložená súkromne mimo Railway a Git. Obnova do izolovanej databázy porovnala všetkých 16 tabuliek s počtami z rovnakého read-only zdrojového snapshotu; audit odmietol update/delete. [Sanitizovaný dôkaz](evidence/production-backup-restore-2026-11-06.json). |
| Upgrade obnovenej kópie | Lokálny prechod skutočnej obnovenej kópie 008 → 009 zachoval počty a hashe pôvodných dát v 15 aplikačných tabuľkách; revízny riadok sa očakávane zmenil. Overené startup guardy 008/009. TCP bolo vypnuté, bez API, workera, schedulerov a integrácií. Pracovná kópia bola odstránená, privátny archív zostal zachovaný. Produkčná schéma sa nezmenila. |
| Produkčný worker | Read-only SSH priamo v kontajneri potvrdilo SHA `83a25c3`, Python 3.12.15, schému na head svojho image, jeden ARQ proces, Redis PING a čerstvý health key. Nový produkčný sken sa neenqueueoval. [Dôkaz](evidence/production-worker-2026-11-06.json). |
| Zostavenie image | API, worker a starší asset frontend úspešne zostavené pre **Linux AMD64** z čistého verzovaného exportu `1e2db87`. [Image ID a Dockerfile hashe](evidence/container-builds-2026-11-06.json). |
| Kontajnerový integračný tok | **26/26** na kandidátovi `1e2db87`: skutočný API → Redis → ARQ worker → PostgreSQL 18.6 Heartbeat, uložený výsledok, session aj API-key scope/tenant kontroly, startup guard 008/009 a platné logout cookie atribúty. Platený plán bol iba syntetická lokálna fixture; žiadna platba ani produkčný job. [Rozsah a image ID](evidence/container-runtime-2026-11-06.json). |
| Staršie asset kontajnery | **5/5**: artefakty sa skopírovali, chybný read-only cieľ zlyhal bez hlásenia úspechu. Výskyt NetworkOnly v SW nenahrádza browser cache audit. [Dôkaz](evidence/legacy-container-assets-2026-11-06.json). |
| Redis záloha | Privátny RDB export Redis 8.2.11: overený checksum, izolovaná obnova na Redis 8.10.3 s TCP vypnutým a úspešný PING. Bez workera/schedulera; nešlo o spoločný transakčný snapshot s PostgreSQL ani test zachovania rozpracovaných jobov. [Dôkaz](evidence/redis-backup-restore-2026-11-06.json). |

Pri produkčnej HTTP skúške sa vyvolalo bežné prihlásenie existujúceho účtu.
Platný logout sa nevykonal: backend zvyšuje token_version celého účtu a odhlásil
by aj ostatné zariadenia. Testovací klient iba zahodil svoju cookie; nič sa nemenilo
na účte ani hesle. Chrome relácia je následne doložená UI kontrolou; produkčný
logout, celý browser akceptačný scenár a fyzický iPhone zostávajú neoverené.

Priame backendové expiračné hlavičky `__Host-` cookies nemali Secure. Oprava v
`1e2db87` zachováva Secure, HttpOnly a SameSite aj pri odhlásení; dva regresné testy
najprv reprodukovali chybu a po oprave prešlo všetkých 10 auth testov. Požiadavky
na prefix opisuje [MDN Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie).
Táto oprava ešte nie je v produkčnom backende.

Staging Postgres health check teraz používa TCP, aby nezachytil iba dočasný init
server s Unix socketom. Kopírovanie assetov pri chybe skončí neúspešne. Starší
asset image používa Alpine **3.24.4**; pôvodná vetva 3.20 už skončila štandardnú
podporu podľa [oficiálnej tabuľky Alpine](https://alpinelinux.org/releases/).

CLI prístup funguje a jeho použitie vrátane správy SSH kľúčov používateľ výslovne schválil. Dočasný workspace SSH
kľúč vytvorený pre zálohu bol po exporte odvolaný a jeho lokálne súbory aj tunel
odstránené. Cudzie/ostatné agentové kľúče sa nemenili. Nová záloha ani autentifikácia
nepotvrdzujú rotáciu tajomstiev, automatický backup schedule, retenciu, alerty alebo
nový produkčný backend deployment. Takéto zmeny sa ešte nevykonali.

Konfigurácia zdroja API aj workera má `source.commitSha` nastavené na
`8540cde6b11da0bea95035afbb85c3f8a9ee4cf1`, zatiaľ čo posledný overený runtime
oboch je `83a25c3`. Pin, runtime a kandidát sú tri odlišné identity. Schválený
cutover musí určiť nový presný SHA pre obe služby; samotný push do main ani
`redeploy --from-source` tento rozpor bezpečne neriešia. Žiadny pin sa nemenil.

Východiskový lokálny HEAD: `c5db6aeb9ae82839444076eeebd45c5ca5f6bc9b`, vetva
`feat/straz-m2m-runs-read`. Opravy nad týmto commitom sú pripravené na review vo vetve
`codex/production-readiness-20261106`; autoritatívny výsledný commit určuje HEAD pull requestu.
Následné billing/staging opravy sú pushnuté v commite
`f263da5fb38d1cf7b01689775d5e3369bbbb0126` v
[PR #6](https://github.com/erikbabcan-commits/shadon-api-scaner/pull/6), ktorý je
otvorený a pripravený na review (`isDraft: false`). Staršie výsledky nižšie sú
priradené ku konkrétnym commitom; nenahrádzajú CI aktuálneho HEAD.

## Historické lokálne kontroly pred kandidátom 1e2db87

Nasledujúce behy patria k uvedeným starším commitom. Aktuálne vykonané kontroly
sú v tabuľke vyššie; historické počty sa nesčítavajú do nového výsledku.

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

### Dodatočné opravy stagingu a prechodu 008 → 009

Nad východiskom `1f71036` boli overené tieto nové zmeny; presné hashe testovaných
súborov a výsledky sú v [sanitizovanom dôkaze](evidence/backend-cutover-staging-2026-11-06.json).
Historický staging render v tabuľke vyššie už nie je aktuálny minimálny požiadavok:
nový overlay vyžaduje **Compose 2.30.0+** a Python **3.10+** pre launcher.

- Zdedene exportované `DATABASE_URL`/`REDIS_URL` už neprepíšu privátny staging súbor.
  `format: raw` zachová jeho doslovné URL, `!reset` odstráni pôvodné environment
  mapovanie. Launcher pred spustením overí lokálne DB/Redis ciele a zhodu DB mena,
  používateľa a hesla. Skutočný Compose render s falošnými vzdialenými shell URL prešiel.
- Stagingový launcher najprv zostaví image, zastaví staré API/worker, spustí zdravé
  závislosti a vykoná migráciu. Aplikácie spustí až po jej úspechu. Zlyhanie migrácie
  v procesnom teste ponechalo aplikácie zastavené. Tento test nie je kontajnerový beh.
- Percent-enkódované heslá DB už nevyvolajú ConfigParser interpolation chybu.
  Regresné testy CLI aj programatického Alembic vstupu najprv reprodukovali chybu
  a po oprave oba prešli; offline SQL pritom neotvára sieťové spojenie.
- **Python 3.12.13**, frozen lock, izolovaný PostgreSQL **16.15** aj **18.6**, vždy
  samostatný Redis: na každom **142 passed, 0 skipped**. Celá sada zahŕňa nové
  staging kontroly aj startup guard pre revízie 008/009, zlyhanie migrácie s
  transakčným rollbackom a regresiu straty nových polí pri downgrade.
- PostgreSQL **18.6**: custom-format záloha syntetickej 008 bola obnovená do novej
  databázy na 008, zatiaľ čo zdroj už bol na 009. Zachovali sa tri fixture riadky,
  väzba nálezu na aplikáciu aj immutable audit trigger. Archív sa po kontrole odstránil;
  testovacie služby boli zastavené. **Nešlo o produkčné dáta ani produkčný backup.**

[Koordinovaný cutover a obnova](MIGRATION_008_009_CUTOVER.md) vyžadujú zastavenie
starého API/workera pred upgrade; samotný pre-deploy hook nestačí. Starý image s
head 008 sa proti 009 nespustí. Návrat cez `downgrade` by odstránil nové polia nálezov;
preferovaný návrat používa overenú zálohu do novej databázy a zohľadní nové zápisy.
Samotná táto staršia skúška nepotvrdila finálne kontajnery ani produkčný backup.
Ich neskoršie samostatné výsledky sú v najnovšej tabuľke; cloud backend CI ostáva blokovaný.

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
- Kontajnerové buildy boli v skoršej fáze odložené pre tlak na pamäť. Po neskoršom
  sprístupnení OrbStack prešli tri AMD64 buildy aj 26 runtime kontrol na `1e2db87`.
  Sú to vykonané historické dôkazy; pri ďalšej kontrole už OrbStack socket nebol
  dostupný. Dostupnosť bežiaceho Docker engine ani build novšieho kódu sa z nich neodvodzujú.
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

Pri tejto pôvodnej verejnej kontrole sa neoverili session cookies ani iPhone.
Neskorší autentifikovaný HTTP test a Chrome relácia sú uvedené v najnovšej tabuľke.
Produkčné skeny a notifikácie sa nespúšťali. Health pravidlá v `AGENTS.md`
boli následne doplnené v samostatnom frontendovom repozitári.

### Finálny samostatný frontend

Zdrojom je súkromný [youh4ck3dme/straz-security-beacon](https://github.com/youh4ck3dme/straz-security-beacon).
[PR #1](https://github.com/youh4ck3dme/straz-security-beacon/pull/1) a
[PR #2](https://github.com/youh4ck3dme/straz-security-beacon/pull/2) sú zlúčené
merge commitmi bez prepisovania histórie. `main` je
`94694aa7d5532cda51290e51ca31201926f4752c`; jeho
[CI 42155566421](https://github.com/youh4ck3dme/straz-security-beacon/actions/runs/42155566421)
úspešne vykonalo frozen Bun install, produkčný audit, **71 testov**, TypeScript
a produkčný build. Toto je nezávislé CI frontendu na účte `youh4ck3dme`, nie
odblokovanie backendového CI na účte `erikbabcan-commits`.

Vite je **8.1.6**, Zod **4.6.6**, Vitest **4.1.12**, seroval **1.6.11**.
Produkčný audit má **0 nálezov**. Full audit má **3 vývojové nálezy**
(1 low, 2 moderate, 0 high/critical), s presnými reťazcami v frontendovom
`docs/DEPENDENCY_AUDIT.md`; neboli použité force ani nekompatibilné overrides.

Lokálny DEV má samostatný loopback upstream a nikdy implicitne nepoužije
produkciu. Hosted Lovable DEV sa rozpoznáva podľa dôveryhodných serverových
markerov `LOVABLE_SANDBOX` a `DEV_SERVER__PROJECT_PATH`, rovnako ako oficiálny
vendor config. Používa pevný HTTPS backend. Táto oprava odstránila používateľom
potvrdenú chybu 502 v náhľade bez rozhodovania podľa klientského Host headera.
Po synchronizácii a aktualizácii náhľadu IAB zobrazilo prihlásenie a preview
`/api/auth/me` zobrazilo JSON `Not authenticated`. Verejný preview endpoint
ostal chránený; jeho auth gate sa neobchádzal.

Finálny snapshot bol publikovaný cez UI s potvrdením **Your website was updated**.
Po publikovaní prešla čerstvá produkčná kontrola **12/12** o
**03:21:53 UTC, 6. 11. 2026**; podrobnosti sú v
[novom sanitizovanom dôkaze](evidence/lovable-production-final-2026-11-06.json).
IAB po reloadnutí publikovanej adresy zobrazilo prihlasovaciu obrazovku bez chyby.
Tento pôvodný test prihlasovacej obrazovky neoveroval úspešnú autentifikáciu;
neskorší HTTP test a Chrome relácia sú uvedené vyššie.

Lokálna pracovná kópia `frontend` je na rovnakom `main`, dev server počúva na
`0.0.0.0:8080`. Reálny lokálny login/me/orgs/CSRF/logout tok prešiel **7/7**
kontrolami s HttpOnly cookie a `no-store`; produkčné prihlásenie sa nepoužilo.
Po poslednej oprave je LAN readiness `ready=true` a neprihlásené auth/me je 401.

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

Samotné verejné GET kontroly nepotvrdzujú produkčné prihlásenie, cookie atribúty,
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
- Neskorší [CI beh na `d5707b9`](https://github.com/erikbabcan-commits/shadon-api-scaner/actions/runs/42184457848)
  opäť skončil billing blokom: secret gate mal nula vykonaných krokov a backend/frontend
  boli preskočené. CodeRabbit review `APPROVED` nie je náhrada testov. Používateľ
  odložil riešenie GitHub billing; nevykonal sa platený zásah ani obídenie gates.
- [CI na `83227ba`](https://github.com/erikbabcan-commits/shadon-api-scaner/actions/runs/42202345390)
  potvrdilo rovnaký billing blok aj po nových runtime opravách: secret gate
  `127840446397` má nula krokov, backend/frontend sú skipped. Nie je to
  zlyhanie vykonaného testu ani zelené backendové CI. Tento výsledok je viazaný
  na uvedený SHA; neskoršie dokumentačné commity nemenia otestovaný runtime.
- Oprávnený prístup do Railway dashboardu aj CLI funguje. Čerstvé `whoami/status`
  potvrdili workspace H4CK3D's Projects, projekt
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
  Neskoršie read-only overenie workera potvrdilo rovnaké runtime SHA `83a25c3`,
  Redis a heartbeat; dôkaz je uvedený vyššie. Nový release ani ingress konfigurácia
  sa tým nepotvrdili.

## Podmienky pred uzavretím release

1. Doriešiť alebo výslovne akceptovať zostávajúce dev advisories, pri každej ďalšej
   zmene runtime kódu obnoviť zodpovedajúce testy/buildy, skontrolovať finálny diff
   a získať nový overený commit s aktuálnymi CI výsledkami vrátane PostgreSQL 16/18.
2. Dokončiť celý browser/logout scenár, dve skutočné tenantové identity a fyzický
   iPhone; produkčné prihlásenie a cookie atribúty cez HTTP klienta aj otvorená
   autentifikovaná Chrome relácia sú už doložené v najnovšej tabuľke.
   Publikovanie, opravený Lovable náhľad, produkčné rozhranie a verejné API
   prepojenie sú overené vyššie. Lokálny HTTP login nie je produkčný login.
3. Overiť ingress trust boundary,
   HSTS a bezpečný upgrade potvrdenej revízie 008 na aktuálny head 010;
   následne overiť nasadenie aktuálnych backendových opráv a nový povolený worker beh.
   CLI aj read-only kontrola starého produkčného workera už fungujú.
4. Vykonať schválenú rotáciu historicky kompromitovaných tajomstiev, nastaviť
   automatické zálohy/retenciu, alerty a proxy/limiter trust boundary podľa
   [prevádzkového postupu](OPERATIONS_ACCEPTANCE.md) a
   [incidentného runbooku](INCIDENT_ROTATION_RUNBOOK.md).
   Čerstvá manuálna produkčná Postgres záloha a izolovaný restore sú už doložené;
   aj manuálna Redis RDB záloha s restore PING nenahrádzajú automatickú retenčnú
   politiku ani preukázané zachovanie rozpracovaného frontu pri spoločnom cutover.
5. Dodať a overiť reálnu izoláciu a funkčné spúšťanie ôsmich externých CLI profilov.
   Dovtedy musia zostať zablokované; zelené testy odmietania nie sú splnením ich
   funkčnosti. Potrebný je oddelený runner bez DB/Redis credentials, obmedzený
   filesystem/zdroje/výstup a vynútená sieťová politika; samotný Python DNS preflight nestačí.
6. Nasadiť a prevádzkovo overiť nové plan-aware plánovanie a obnoviteľný notification
   outbox. Doplniť globálny execution mutex/fencing a bezpečnú obnovu running skenov
   po páde; scheduler admission lock túto odlišnú hranicu nerieši. Potvrdiť reálne
   doručenie na určený testovací kanál po autorizácii; lokálny TLS fixture ho nenahrádza.

Finálny release záznam doplniť skutočnými nasadenými SHA, časom deploymentu,
výsledkami aktuálnych kontrol a presným zoznamom zostávajúcich obmedzení.
Hodnoty tajomstiev, cookies a produkčné osobné dáta sem nepatria.
