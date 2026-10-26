# STRÁŽ — nezávislá bezpečnostná kontrola, 26. 10. 2026

Východiskový commit: `bda1d8f5caaf2ee73e81f1776287b747c6e530f3`.
Rozsah: iba tento repozitár, izolované testy a čítanie GitHub metadát.
Bez produkčných požiadaviek, migrácií, pushu alebo deployu.

## Prvý súhrn a plán pred opravami

1. **Vysoká:** API autentifikácia povoľuje administratívne endpointy bez scope
   (`app/deps.py`, routery). Zaviesť centrálny default-deny zoznam práv,
   session-only administráciu, kontrolu členstva a expirácií.
2. **Vysoká:** tenantové filtre zahŕňajú aplikácie s NULL organizáciou
   (`routers/apps.py`, `runs.py`, `findings.py`, `reports.py`, `ci.py`).
   Nepriradené dáta izolovať; ich priradenie vyžaduje samostatný schválený backfill.
3. **Vysoká:** Stripe bez secretu prijíma nepodpísaný JSON; súbeh/retry nie sú
   bezpečne transakčné (`services/stripe.py`). Overovanie musí zlyhať uzavreto,
   idempotencia a zmena plánu musia byť jedna transakcia.
4. **Vysoká:** SSRF kontrola potláča vlastnú výnimku a nekontroluje DNS
   (`notifications/transport.py`, `schemas.py`); ownership fallback používa
   nesúvisiaci base_url (`verify.py`). Zaviesť verejné IP, pinning, žiadne
   redirecty, správnu väzbu cieľa a negatívne testy.
5. **Vysoká:** CI môže označiť neúplný beh za úspešný; worker nezapisuje
   observations (`services/ci.py`, `worker.py`, `findings.py`). Fail closed,
   snapshoty nálezov podľa behu, chyby skenerov nesmú uzatvárať staré nálezy.
6. **Vysoká:** PWA cache API nie je oddelená podľa tenanta ani účtu
   (`apps/web/vite.config.ts`). API odpovede nesmú byť offline cacheované.
7. **Stredná:** audit helper nedostáva organizáciu/actora/IP a niektoré mutácie
   sa necommitujú (`services/audit.py`, org router, `db.py`). Opraviť kontext
   a transakcie, CSV/redakciu a testovať skutočné operácie.
8. **Stredná:** readiness hlási úspech bez Redis a vracia interné výnimky;
   rate limiter dôveruje ľubovoľnému X-Forwarded-For. Zmerať obe komponenty
   s časovým limitom, anonymné chyby, použiť overený ASGI peer.
9. **Blokery vyžadujúce samostatné rozhodnutie:** modely UUID sa rozchádzajú
   s publikovanými CHAR(36) migráciami; existujúce triggery neumožňujú FK
   kaskády. Nemeniť históriu migrácií ani aplikovať migrácie. Potrebná nová
   migrácia a skúška na obnove PostgreSQL. CLI skenery vyžadujú aj sieťovú
   izoláciu mimo aplikácie; DNS preflight sám osebe nie je rebinding ochrana.

## Threat model

Aktíva: tenantové nálezy/reporty, identita a členstvá, API kľúče, platobné
oprávnenia, webhook URL/tajomstvá, audit a deploy artefakty.
Hranice: browser → API/session; CI → scoped bearer → organizácia;
API → DB/Redis/worker; worker → nedôveryhodný cieľ/repozitár/webhook;
Stripe → podpis → transakcia; GitHub → build → nasadenie.
Predpoklad: útočník má vlastný účet alebo odcudzený obmedzený API kľúč,
kontroluje cieľové DNS/HTTP, môže opakovať webhooky a meniť obsah PR.
Kompromitácia DB vlastníka, session signing secretu alebo dôveryhodného
runnera presahuje aplikačné RBAC; vyžaduje separáciu práv a rotáciu.

## Overená architektúra a hranice

FastAPI/Pydantic API → SQLAlchemy async → PostgreSQL; ARQ worker cez Redis.
React/Vite/TanStack Query frontend a Workbox PWA; Caddy/Docker Compose,
Railway/Render/Vercel deklarácie. Relácie sú itsdangerous podpísané cookies,
nie JWT napriek staršiemu komentáru. Heslá sú Argon2. API kľúče majú SHA-256
hash a náhodný URL-safe token; webhook tajomstvá ostávajú v DB v čitateľnom
formáte a vyžadujú ochranu DB/záloh. DNS TXT a HTTP proof overujú vlastníctvo.
Je prítomných 10 profilov. Heavy mutex a automatické uzatváranie nálezov sú
zachované; uvoľnenie Redis mutexu je teraz atómové porovnanie + DELETE.

Zápis akcií org/invitations/billing má explicitný commit s auditom; API key
služby už samostatne necommitujú pred auditom. Nové HTTP transporty nepoužívajú
proxy z prostredia, nepresmerovávajú a overujú všetky DNS odpovede aj Host/SNI.
Bootstrap už neprepisuje existujúce používateľské heslo podľa env pri každom reštarte; logout zvyšuje token_version a odvolá staré session tokeny. Model API key nemá schému rotácie „in place“: rotácia je vytvoriť nový,
aktualizovať CI secret, revokovať starý. Obnova zabudnutého hesla/email identity
verification nie je implementovaná; nejde o otestovanú existujúcu funkciu.

## Zoradené nálezy a stav po oprave

Cesty nižšie odkazujú na lokálnu opravenú verziu; pôvodný stav sa dá porovnať
s uvedeným východiskovým commitom. Závažnosť opisuje dopad pred opravou.


### H01 — Vysoká — Opravené

Dôkaz: `apps/api/app/deps.py:23`.

Scoped kľúč preberal session oprávnenia autora. Ukradnutý read-only kľúč mohol meniť tím a vytvárať ďalšie kľúče. Centrálna allowlist politika kontroluje skutočnú URL/metódu, členstvo, expiráciu aj efektívny plán; všetky ostatné endpointy sú session-only. Testy read-only, prázdnych práv, revokácie, expirácií a straty členstva. Kompatibilita: session token v Bearer ani X-API-Key sa už neprijíma; API kľúč sa používa cez Bearer.

### H02 — Vysoká — Opravené; backfill čaká

Dôkaz: `apps/api/app/routers/apps.py:38`.

NULL organization_id poskytovalo globálny prístup k aplikáciám/nálezom/scanom/reportom. Podmienka NULL bola odstránená zo všetkých objektových a zoznamových endpointov. Negatívny test porovnáva vlastnú, cudziu a nepriradenú aplikáciu vrátane mutácií. Dopad opravy: nepriradené staré dáta budú neviditeľné, kým sa administratívne nepriradia; dáta sa nemažú.

### H03 — Vysoká — Opravené; live Stripe neoverené

Dôkaz: `apps/api/app/services/stripe.py:193`.

Bez secretu sa prijímal nepodpísaný webhook, deduplikácia nebola atómová a OR s NULL mohol vybrať nesúvisiaci tenant. Podpis je povinný, chýbajúci secret vracia 503, unique ON CONFLICT + zmena plánu + audit sú jedna transakcia. V live móde sa pod org zámkom načíta aktuálna subscription, takže sa nespolieha na poradie eventov; podporovaný je aj moderný parent.subscription_details invoice formát. Return URL má rovnaký origin ako nakonfigurovaný frontend; živá fakturácia bez kľúča nesimuluje úspech. Existujúca aktívna subscription sa mení cez Portal, nie druhým Checkoutom. Testy podpisu, tamperu, replay, rollbacku a payment_failed. Riziko opravy: vyžaduje správne Stripe secrets/price IDs; zle nakonfigurovaná integrácia zlyhá uzavreto.

### H04 — Vysoká — Opravené pre Python HTTP

Dôkaz: `apps/api/app/services/safe_http.py:61`.

SSRF validátor potláčal vlastnú ValueError, nekontroloval DNS a ownership fallback mohol overiť cudzí target cez base_url ovládaný útočníkom. Nový transport kontroluje všetky A/AAAA výsledky, IPv4-mapped IPv6 a verejnosť IP, pinne cieľovú IP a zachová Host/SNI. Redirecty aj env proxy sú vypnuté; proof má limit tela a musí patriť target hostu. Testy privátnych adries, zmiešaného DNS, pinningu, HMAC raw bytes a nesúvisiaceho proof hostu. HTTP/SSH git URL už nie sú povolené. CLI rebinding je samostatné H13.

### H05 — Vysoká — Opravené; reálne CLI binárky neoverené

Dôkaz: `apps/api/app/services/ci.py:10`.

CI používalo staré aplikačné nálezy a dokončenie bez observations_complete. Worker teraz zapisuje per-run severity snapshoty; chýbajúci skener, timeout, neúspešný proces a poškodený JSON nedávajú clean gate. Čistý úplný run môže prejsť, critical run zlyhá. Queue outage je 503/failed, nie zdanlivo queued úspech; polling overuje aktuálne oprávnenia a uvoľňuje transakcie. Regresie wait=True čistý/critical, neúplný beh, worker úspech/zlyhanie a queue failure. Riziko: inštalácia musí obsahovať funkčné kompatibilné binárky.

### H06 — Vysoká — Opravené; staré offline klienty treba aktualizovať

Dôkaz: `apps/web/vite.config.ts:68`.

Workbox NetworkFirst ukladal autorizované odpovede bez tenant/user cache kľúča. API je NetworkOnly, server aj fetch používajú no-store a aplikácia odstraňuje starú straz-api cache. Zlúčenie vlastných Headers už nevyhadzuje tenant/CSRF hlavičky. SSE/report/CSV navigácia nesie explicitnú organizáciu a backend členstvo overuje. Testy klientských hlavičiek a tenantových export URL, build service workeru. Už nainštalovaný offline starý service worker sa neopraví, kým klient neprevezme aktualizáciu.

### H10 — Vysoká — Opravené

Dôkaz: `apps/api/app/services/organizations.py:294`.

Admin mohol pri zmene role povýšiť seba/člena na owner. Takýto update sa teraz odmieta; vlastníctvo vyžaduje samostatný workflow. Negatívny test self-promotion a existujúce RBAC testy. Transfer vlastníctva nie je v tejto oprave implementovaný.

### H12 — Vysoká — OTVORENÉ — release blocker

Dôkaz: `apps/api/app/models.py:32`.

GUID model na PostgreSQL používa natívne UUID, publikované migrácie 001–007 však vytvárajú CHAR(36). SQLite create_all testy tento nesúlad neodhalia. Migrácia 002 navyše neobsahuje predvolený tenant/backfill existujúcich appiek. Dopad: PostgreSQL bind/FK/schema chyby a staré nepriradené dáta. Nutná schválená nová migrácia po inventúre reálnej DB a skúška na izolovanej obnove; publikované migrácie sa nesmú spätne meniť. Migrácie ani DB neboli počas auditu spustené alebo upravené. Riziko opravy: konverzia UUID, FK a backfill môžu vyžadovať zámky a maintenance window.

### H13 — Vysoká — ČIASTOČNE — release blocker

Dôkaz: `apps/api/app/services/scanners.py:274`.

Externé CLI skenery/git/registry vykonávajú vlastné DNS a nemajú sieťovú izoláciu. Python IP pinning sa na tieto procesy neprenáša. Doplnil sa verejný DNS preflight, validácia legacy vstupov, zákaz private-target trust v produkcii, odstránenie HTTPX redirectov, obmedzenie git protokolov/hooks a child environment bez aplikačných tajomstiev. Útočník ovládajúci DNS však stále môže prebindovať medzi preflightom a spojením binárky. Potrebný dedikovaný non-root worker s egress filtrom/proxy, bez DB/Redis/metadátových privátnych sietí a oddelením od control plane. Zmena produkčnej topológie vyžaduje schválenie. Bez reálneho staging packet/egress testu sa tento bod nepovažuje za opravený.

### H07 — Stredná — Opravené v aplikačnej vrstve

Dôkaz: `apps/api/app/services/audit.py:44`.

Audit helper dostával system/NULL namiesto org/actora/IP a niektoré mutácie sa neuložili. Kontext sa viaže na session/API key, API použitie sa audituje, citlivé key/string/URL údaje sa redigujú. IP sa berie z ASGI peer, nie priamo zo spoofovaného X-Forwarded-For. ORM update/delete auditu sú zakázané. Regresia reálnej app mutácie, actora, tenant ID, IP, redakcie a ORM mutation. Správne IP za proxy vyžaduje presný allowlist dôveryhodných proxy na ASGI serveri; aktuálny peer môže byť adresa proxy.

### H08 — Stredná — Opravené v API; proxy konfigurácia čaká

Dôkaz: `apps/api/app/routers/health.py:37`.

Readiness vracalo 200 aj bez Redis a zverejňovalo text interných výnimiek. Obe služby majú bounded súbežné kontroly; zlyhanie ktorejkoľvek znamená 503. Chyby sú generické, liveness nemá závislosti. Staré /api/health aliasy majú rovnakú readiness sémantiku. Testy pokrývajú tri readiness URL, latencie a redakciu chýb. Caddy zatiaľ routuje iba /api/*: samostatné /healthz/* treba pred rolloutom explicitne sprístupniť v schválenom deploy configu.

### H09 — Stredná — Opravené v kóde; PG súbeh neoverený

Dôkaz: `apps/api/app/services/quota.py:86`.

Kontrola a zápis kvóty neboli serializované, cron obchádzal profilové/mesačné limity. Organizácia sa pred kontrolou zamkne SELECT FOR UPDATE; scan_usage sa účtuje aj pre scheduler pred enqueue a prežije zmazanie aplikácie. Neaktívne/neznáme/po skončení obdobia predplatné má free oprávnenia. SQLite ignoruje FOR UPDATE; reálne konkurenčné PG overenie je povinný release gate. Denné/hodinové komerčné cron cadence zostávajú neimplementované, existujúci scheduler je weekly + heartbeat.

### H11 — Stredná — Opravené; doručenie best effort

Dôkaz: `apps/api/app/services/notifications/__init__.py:99`.

Priamy ntfy a dispatcher commitovali/odosielali mimo konzistentnej scan transakcie. Nálezy teraz vytvárajú iba tenantové outbox udalosti; worker ich po commite claimne a odošle s max. 5 s na kanál a max. 8 súčasnými odoslaniami. HMAC sa počíta z presne odoslaných bajtov vrátane Unicode. Ntfy Unicode Title sa kóduje RFC 2047 podľa oficiálneho protokolu, aby ASCII HTTP hlavičky nezlyhali. Regresia rollbacku, critical filtra a wire podpisu. Nejde o exactly-once doručovanie; crash po claim môže zanechať processing záznam, vyžaduje monitoring a manuálne zosúladenie/retry politiku. Staré globálne ntfy nastavenia treba previesť na explicitné org kanály, nie zdieľať naprieč tenantmi.

### H14 — Stredná — OTVORENÉ — schema/retention policy

Dôkaz: `apps/api/alembic/versions/007_audit_log_and_health.py:71`.

Trigger 007 blokuje aj FK SET NULL/CASCADE; audit user FK v pôvodnej migrácii chýba. ORM guard je iba doplnková ochrana, DB vlastník môže triggery zmeniť. Treba novú schválenú migráciu pre FK/trigger výnimky, minimálne DB role a explicitnú politiku retencie/exportu. DB-owner kompromitáciu nemožno označiť za WORM odolnosť. Test pôvodného triggeru v sade nevykonáva publikovanú PostgreSQL migráciu.

### H15 — Stredná — OTVORENÉ — infra release gate

Dôkaz: `apps/api/worker.Dockerfile:1`.

Worker Dockerfile beží ako root, CLI archívy nemajú checksum overenie, pip/npm build nevyužíva dôsledne lockfile. Render worker má root build context, hoci COPY vyžaduje API pyproject/app; takýto build context v roote súbory nemá. Docker nie je v tomto prostredí dostupný; žiadny image build ani cloud deploy neprebehol. Pred rolloutom schváliť non-root/capabilities/egress návrh, opraviť build context, pinovať artefakty a skenovať finálne image/SBOM, nie iba lokálne dependency tree.

### H16 — Stredná — ČIASTOČNE — CI/účtové pravidlá neoverené

Dôkaz: `.github/workflows/ci.yml:48`.

Workflow používa tagy actions a latest uv, frontend job nespúšťa vitest; backend conftest prepíše DATABASE_URL na SQLite aj pri PG service v CI. Migrácie test kontroluje iba command.heads. GitHub rulesets read vrátil prázdny zoznam; branch-protection read bol 403, nie dôkaz neexistencie ochrany. Nemenené účtové pravidlá. Navrhovaný release gate je nižšie; nastavenie required checks/protection vyžaduje administratívne overenie.

### H17 — Stredná — Opravené; nejde o právny audit

Dôkaz: `apps/api/app/services/reporting.py:32`.

Branding vstupy nemali presnú validáciu a report naznačoval certifikáciu bez scan coverage. Hex farba/logo URL majú validáciu aj renderer fallback; text je HTML escaped, CSP povoľuje len presný hash tlačového skriptu a štýly. Prázdne oblasti sú WARNING, nie dokázaný COMPLIANT; JSON označuje neoverené pokrytie. CSV escape zahŕňa whitespace/control prefix a filename neobsahuje neoverený slug. Testy branding injection, CSV prefixov a neoverenej compliance. Externé HTTPS logo načítava browser; pri exporte môže prezradiť IP príjemcu loga.

### H18 — Stredná — Opravené v skripte; restore neoverené

Dôkaz: `deploy/backup-db.sh:14`.

Backup skript mal zálohy so závislosťou na umask a mohol ponechať čiastočný súbor. Používa umask 077, dočasný súbor, cleanup trap, gzip integritu a atómové publikovanie výsledku. Overené bash -n; bez Docker/DB sa backup ani restore nespustil. Šifrovaná offsite záloha, retenčná politika, RPO/RTO a reálna restore skúška sú stále povinné.

## Tajomstvá, osobné údaje a závislosti

Gitleaks 8.30.1 bol prevzatý z oficiálneho GitHub release a SHA-256 archívu bol
porovnaný s release checksums. Výstupy skenov sú redigované. Východisková
história má 7 kandidátov: 1 syntetická testovacia hodnota a 6 statických
ukážkových credentials v README/cloud návode. Ich platnosť v ľubovoľnom reálnom
nasadení nebola a nebude aktívne skúšaná. Ak boli použité ako skutočné heslá či
session secret, treba ich okamžite rotovať a odvolať staré relácie. História sa
neprepisovala. Aktuálne príklady používajú generovanie náhodných hodnôt a
neobsahujú osobný admin email; finálny source-only scan má 0 nálezov.
Toto nie je matematický dôkaz absencie všetkých tajomstiev. Existujúce cloud
secrets, serverové logy a produkčné dáta neboli čítané.

`pip-audit` zachytil certifi advisory PYSEC-2026-4320; lock sa aktualizoval na
2026.10.23. `npm audit` pôvodne hlásil fast-uri (moderate) a serialize-javascript
(low); kompatibilné lock aktualizácie ich odstránili. Finálne oba audity hlásia
0 známych zraniteľností. Toto nepokrýva OS balíky ani binárky v Docker image.

## Príkazy a výsledky overenia

| Kontrola | Presný príkaz (v zodpovedajúcom adresári) | Výsledok |
|---|---|---|
| Backend | `cd apps/api && uv sync --frozen --dev && uv run --frozen pytest -q --tb=short` | **94 passed, 1 skipped**, 82.11 s |
| Frontend testy | `cd apps/web && npm ci --ignore-scripts && npm test` | **6 passed** |
| TypeScript | `cd apps/web && npx --no-install tsc --noEmit` | exit 0 |
| Produkčný build | `cd apps/web && npm run build` | exit 0; Vite 6.4.5, PWA 0.21.2, 12 precache statických položiek |
| Základný Python lint | `uv tool run ruff check --isolated --select F,E9 apps/api/app apps/api/tests/test_hardening.py --output-format concise` | All checks passed |
| Python syntaktická kontrola | `python3 -m compileall -q apps/api/app apps/api/tests` | exit 0; nejde o statickú kontrolu typov |
| Shell | `bash -n deploy/backup-db.sh` | exit 0; backup/restore sa nespustil |
| Patch | `git diff --check` | exit 0 |
| Python dependency audit | `uv tool run --from pip-audit pip-audit --path apps/api/.venv/lib/python3.12/site-packages --format json` | 0 známych zraniteľností |
| npm dependency audit | `npm --prefix apps/web audit --json` | 0 info/low/moderate/high/critical |
| Aktuálne zdroje | `gitleaks dir SOURCE_ONLY_TREE --redact --no-banner --log-level error --report-format json` | 0 nálezov; SOURCE_ONLY_TREE obsahuje iba tracked + nové zdroje, bez .env/dependencies/cache |
| Git história | `gitleaks git REPO --redact --no-banner --log-level error --report-format json` | 7 kandidátov; klasifikácia a rotácia vyššie |

Spolu **100 úspešných testovacích scenárov + 1 preskočený**. Preskočený je
`test_real_redis_shared_budget_and_expiry`: lokálny izolovaný Redis fixture
(`QUOTA_REDIS_URL`) nie je nakonfigurovaný. Modelové Redis outage/counter testy
prešli. Žiadny zo SQLite testov sa nepovažuje za PostgreSQL migration/locking
integračný test. Úvodné širšie volanie Ruff v hostiteľskom prostredí hlásilo
315 nálezov v ďalších pravidlách; nad rámec uvedeného základného F/E9 gate
sa čistý plný lint ani striktný Python type gate necertifikuje.

`cd apps/api && uv tool run --from mypy mypy app --python-executable .venv/bin/python`
prešlo: **Success: no issues found in 45 source files** (predvolené pravidlá,
nie `--strict`). Dodatočná kontrola odhalila a opravila typy DNS odpovedí,
nezúžené optional členstvo, ntfy body/outbox premenné a Redis async command API.
Základný Redis Lua limit ostáva atómový. Striktný režim bez neanotovaných tiel
stále nie je zavedený; existujúce Any/default framework typy sa neskryli cez
nové type-ignore alebo cast obchádzanie.

Testy používajú syntetické účty, SQLite a ASGI transport; HTTP/sockets sú
blokované alebo explicitne mockované. Frontend testy sú Vitest bez plného
browser E2E. Argon2 náklady sú znížené len vo fixture pre syntetické heslá;
produkčný PasswordHasher ostáva nezmenený. Žiadny API lifespan/dev server,
`alembic upgrade`, `app.migrations upgrade`, produkčný test, GitHub push,
merge alebo deploy sa počas auditu nespustil. Staršie testy s nesprávnymi NULL
app fixtures, unsigned webhookom a externým test webhook volaním boli opravené.
Súčasťou overenia nie je performance/password-hardening benchmark.

## Odporúčaný bezpečnostný release gate

1. Povinný PR a administratívne overené required checks bez bypassu; minimálne
   contents:read; žiadne produkčné secrets pre fork PR; actions podľa immutable SHA.
2. Backend `uv sync --frozen --dev`, celý pytest, samostatný negatívny security
   suite, `ruff --isolated --select F,E9`; neskôr riadne nakonfigurovaný striktný
   typový/lint gate. Nezamieňať tento základný lint s celou sadou štýlových pravidiel.
3. Frontend `npm ci --ignore-scripts`, `npm test`, `tsc --noEmit`, `npm run build`.
   Skontrolovať výsledný SW: žiadne cachovanie credentialed API.
4. Secret scan celého PR/tree aj histórie bez vypisovania nálezov; dependency
   audit s nulovým ignorovaným high/critical, fixovať aj nižšie úrovne podľa politiky.
5. Pred release test na izolovanej PostgreSQL 16 obnove: schválená migrácia,
   backfill, downgrade/restore stratégia, FK/triggery, súbežné quota a webhook
   eventy. Skutočný Redis test rozpočtu/expirácie musí prestať byť skipped.
6. Zostaviť finálne API/worker/web image z lockov, skontrolovať build context,
   non-root používateľa, verifikované CLI checksumy a SBOM; podpísať/promoteovať
   ten istý overený digest. Žiadny produkčný build z neovereného PR/ref.
7. Autorizovaný staging smoke: cookies/CORS/CSRF, dva tenanty a všetky roly,
   scoped CI clean/fail/incomplete, Stripe test podpis+retry+out-of-order,
   DNS rebinding/redirect/egress testy s vlastnými lokálnymi fixture službami.
8. Oddelené DB/Redis siete a egress workeru; health readyness musí zlyhať pri
   DB aj Redis outage. Alerty na failed/stale outbox, queue age, scan failures,
   audit write failures; nevypisovať secrets a tokenové URL.
9. Preukázaná šifrovaná offsite záloha a obnova, schválená retencia auditu,
   nastavené RPO/RTO a dokumentovaný rollback.
10. Explicitné schválenie release až po uzavretí H12/H13 a infra blokérov;
    úspešné unit testy samy osebe nie sú schválením produkcie ani certifikáciou.

## Konkrétne ďalšie kroky vyžadujúce schválenie

- Nová migrácia (napr. 008, bez úprav 001–007): najprv read-only inventúra
  skutočných UUID/CHAR dát a väzieb; odmietnuť neplatné UUID; záloha; konverzia
  všetkých PK/FK ako jeden plán; tenant backfill podľa doloženého vlastníctva,
  nikdy nepriradiť NULL appky náhodnému používateľovi; oprava audit FK/triggerov.
  Pred aplikáciou predložiť presný SQL/maintenance/rollback plán na obnovenej DB.
- Schválená zmena worker infra: dedikovaný non-root scanner runtime a vynútený
  egress bez prístupu ku control-plane DB/Redis/metadata; povoliť iba doložené
  ciele. Opraviť Render context, Caddy probes a zapojiť immutable image build.
- GitHub admin má overiť protections/required checks; cez dostupnú integráciu
  sa ich stav nedal potvrdiť. Žiadne nastavenie účtu sa nezmenilo.

Pramene pre protokoly: oficiálne Stripe webhook docs (podpis, deduplikácia,
nespoľahlivé poradie udalostí) https://docs.stripe.com/webhooks a HTTPX transport
API https://www.python-httpx.org/advanced/transports/ a ntfy Unicode headers https://docs.ntfy.sh/publish/ . HTTPX SNI správanie je
navyše unit testované proti nainštalovanému transport API; živý TLS handshake
s fixture certifikátom a plný browser flow zostávajú staging gate.

**Verdikt: audit a bezpečné aplikačné opravy sú pripravené na recenziu.
Produkčné kritériá nie sú splnené: H12/H13 nie sú akceptované ani uzavreté.
Žiadne číselné M&A skóre ani úplná bezpečnosť sa týmto reportom necertifikujú.**

## Zmenené a nové súbory

- `README.md`
- `apps/api/app/deps.py`
- `apps/api/app/logging.py`
- `apps/api/app/main.py`
- `apps/api/app/migrations.py`
- `apps/api/app/models.py`
- `apps/api/app/rate_limit.py`
- `apps/api/app/routers/api_keys.py`
- `apps/api/app/routers/apps.py`
- `apps/api/app/routers/audit.py`
- `apps/api/app/routers/auth.py`
- `apps/api/app/routers/billing.py`
- `apps/api/app/routers/ci.py`
- `apps/api/app/routers/findings.py`
- `apps/api/app/routers/health.py`
- `apps/api/app/routers/integrations.py`
- `apps/api/app/routers/organizations.py`
- `apps/api/app/routers/reports.py`
- `apps/api/app/routers/runs.py`
- `apps/api/app/schemas.py`
- `apps/api/app/security.py`
- `apps/api/app/services/api_keys.py`
- `apps/api/app/services/audit.py`
- `apps/api/app/services/ci.py`
- `apps/api/app/services/compliance.py`
- `apps/api/app/services/findings.py`
- `apps/api/app/services/health.py`
- `apps/api/app/services/notifications/__init__.py`
- `apps/api/app/services/notifications/channels.py`
- `apps/api/app/services/notifications/formatters.py`
- `apps/api/app/services/notifications/transport.py`
- `apps/api/app/services/ntfy.py`
- `apps/api/app/services/organizations.py`
- `apps/api/app/services/quota.py`
- `apps/api/app/services/reporting.py`
- `apps/api/app/services/safe_http.py`
- `apps/api/app/services/scanners.py`
- `apps/api/app/services/stripe.py`
- `apps/api/app/services/verify.py`
- `apps/api/app/worker.py`
- `apps/api/tests/conftest.py`
- `apps/api/tests/test_api_keys.py`
- `apps/api/tests/test_audit_health.py`
- `apps/api/tests/test_billing.py`
- `apps/api/tests/test_findings.py`
- `apps/api/tests/test_hardening.py`
- `apps/api/tests/test_integrations.py`
- `apps/api/tests/test_quota_boundary.py`
- `apps/api/tests/test_runs.py`
- `apps/api/tests/test_security.py`
- `apps/api/uv.lock`
- `apps/web/package-lock.json`
- `apps/web/src/lib/api.test.ts`
- `apps/web/src/lib/api.ts`
- `apps/web/src/main.tsx`
- `apps/web/src/pages/AuditLogPage.tsx`
- `apps/web/src/pages/RunsPage.tsx`
- `apps/web/vite.config.ts`
- `deploy/backup-db.sh`
- `docs/CLOUD_DEPLOYMENT_GUIDE.md`
- `docs/SECURITY_REVIEW_2026-10-26.md`
