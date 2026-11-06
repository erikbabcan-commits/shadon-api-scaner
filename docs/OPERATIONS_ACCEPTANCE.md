# STRÁŽ — prevádzkové overenie a čakajúce rozhodnutia

Tento dokument rozlišuje vykonané read-only kontroly a otvorené prevádzkové kroky.
Produkčná rotácia, reštarty a deploy vyžadujú výslovné schválenie používateľa.

## Stav overený 6. 11. 2026

- Railway CLI je prihlásené do H4CK3D's Projects / dev-new / production; API,
  worker, Postgres a Redis sú online. Verejná readiness a autentifikovaný HTTP tok
  cez Lovable sú doložené v [release zázname](RELEASE_READINESS_2026-11-06.md).
- Privátna produkčná PG 18.6 záloha revízie 008 bola obnovená do novej izolovanej
  databázy bez TCP, workera a integrácií. Zhodovalo sa 16 tabuliek zo zdrojového
  snapshotu a ochrana auditu; následný upgrade obnovenej kópie zachoval dáta 15
  aplikačných tabuliek. [Dôkaz bez obsahu dát](evidence/production-backup-restore-2026-11-06.json).
- Privátna RDB záloha Redis 8.2.11 prešla checksum kontrolou a obnovou/PING na
  izolovanom Redis 8.10.3. Nie je to dôkaz spoločného PG/Redis snapshotu ani
  zachovania rozpracovaných úloh. [Dôkaz](evidence/redis-backup-restore-2026-11-06.json).
- API aj worker stále používajú runtime `83a25c3` / schému 008; ich konfigurovaný
  source pin `8540cde` sa líši od runtime aj od release kandidáta. Žiadny z nich
  sa automaticky nepovažuje za aktuálny schválený deployment.
- Automatické zálohy, vzdialená retencia, obnova po výpadku celého počítača,
  doručené alerty, rotácia tajomstiev a produkčný upgrade 010 zostávajú otvorené.
  Lokálne súkromné zálohy nenahrádzajú off-site zálohu mimo tohto počítača.

## Read-only DB kontrola a osirelé aplikácie

Súbor `deploy/audit-readonly.sql` obsahuje transakciu READ ONLY, PostgreSQL verziu,
Alembic revíziu, počet apps s NULL organization_id a validáciu auditných FK.
Spustiť iba cez autorizované súkromné DB spojenie bez výpisu URL/hesiel.
Očakávaný head overiť cez `python -m alembic heads`; CI pokrýva PG 16 aj 18.
Aktuálna produkčná verzia a revízia sa nedajú odvodiť iba z HTTP readiness.

Politika osirelých aplikácií: zachovať izoláciu a pôvodné riadky. Pripraviť vlastnícke
mapovanie iba z existujúcich dôveryhodných dôkazov, nejednoznačné prípady dať na ručné
rozhodnutie. Najprv počty a suché vyhodnotenie, potom schválená nová dátová migrácia
so zálohou a plánom obnovy. Nepriraďovať ich automaticky prvému používateľovi alebo tímu.
Toto PR nepridáva backfill, novú schému ani produkčný dátový zápis.

## Záloha a izolovaný restore

Koordináciu API/workera pri zmene head 008 → 010 cez 009 a návrat cez novú databázu opisuje
[cutover/rollback postup](MIGRATION_008_009_CUTOVER.md). Reálna manuálna skúška
je doložená vyššie; nasledujúci postup treba zopakovať pri finálnom cutover a
previesť na schválenú automatickú retenčnú politiku.

1. V Railway overiť existujúci Postgres backup/PITR plán a podporu služby/plánu.
   Zaznamenať ID poslednej úspešnej zálohy, čas, rozsah, privátny prístup a retenciu.
   Navrhované minimum na schválenie: denná záloha, 7 dní dennej retencie a samostatná
   týždenná kópia 4 týždne; RPO 24 h a cieľ RTO 4 h. Nie sú to už nastavené hodnoty.
2. Ak záloha chýba, po povolení nastaviť provider schedule alebo chránený pg_dump.
   Existujúci deploy/backup-db.sh je určený pre Docker Compose, nie dôkaz Railway backupu.
3. Po povolení vytvoriť samostatný izolovaný restore environment/databázu. Nikdy neobnovovať
   do produkčného DSN. Pred importom porovnať identity/hosty/DB a vyžadovať, aby bol cieľ
   nový a odlišný. Prenos ani úložisko nesmú byť verejné.
4. Restore test s reálnou zálohou môže obsahovať osobné dáta: obmedziť prístupy, zakázať
   odchádzajúce integrácie, worker a scheduler, nevytvárať verejnú doménu. Výpis len počtov.
5. Overiť restore, `alembic_version`, počty a FK, audit retention/immutability v izolovanom
   cieli a API read-only dostupnosť. Zaznamenať čas obnovy a výsledky, nie obsah riadkov.
6. Izolovaný cieľ odstrániť podľa schválenej politiky, úspešný privátny archív ponechať
   počas schválenej retencie. Výsledok pripojiť k release. Neodstraňovať jedinú overenú
   obnoviteľnú zálohu v rámci cleanupu. Bez čerstvého dôkazu nemožno tvrdiť aktuálny RPO/RTO.

## Alerty a monitoring

Po povolení platformových zmien nastaviť upozornenie na neúspešný deploy pre straz-api
aj straz-worker a reštart slučku. Readiness monitorovať HTTPS GET každých 60 s,
timeout 10 s, alarm po 3 po sebe idúcich zlyhaniach, obnova po 2 úspechoch.
Použiť `/healthz/readiness` a sledovať aj obsah ready=true; samotná liveness nestačí.
Pridať súkromný monitoring worker heartbeat/job latency/queue backlog a backup age.
Príjemcu a kanál musí určiť vlastník; bez neho sa neposiela syntetická notifikácia.
Otestovať alert na stagingovej sonde, nie vypnutím produkčnej DB alebo Redisu.
Aktuálne nastavenie, doručenie, retencia logov a RPO/RTO **neboli týmto PR potvrdené**.

Kandidát má [obnoviteľný outbox a plánovanie](SCHEDULING_AND_NOTIFICATIONS.md),
vrátane reálneho lokálneho TLS receipt testu. Produkcia ich ešte nepoužíva.
Po cutover overiť aj vek pending/processing udalostí, počet pokusov a terminálne
failed udalosti; samotný zdravý ARQ proces nepotvrdzuje doručenie správ.

## Zdroj deploya a zodpovednosť

Konfigurácia a runtime sú oddelené identity: posledné overenie ukázalo source pin
`8540cde` a bežiace `83a25c3` na API aj workeri. Pred nasadením tieto hodnoty znovu
overiť cez Railway konfiguráciu a runtime, nie podľa stavu GitHub main. Pri ponechanom pine push
do main nespustí automaticky nový kód. Nasadenie schváleného SHA riadi vlastník projektu
alebo poverený release operátor s prístupom do workspace. Zaznamenať SHA oboch služieb.

Automatický deploy z main zapnúť až po samostatnom schválení a vynútených CI gates
(secret-scan, backend PG 16/18, frontend). Pred tým nespúšťať neotestovaný main automaticky.
Po každom nasadení overiť health, vlastnú autorizovanú reláciu a worker zodpovedajúceho SHA.

## Súkromné CLI tunely

Existujúce platné prihlásenie sa nemusí rušiť príkazom logout. `railway status` možno
volať s explicitným projektom a environment bez zmeny lokálneho linku. Pred použitím
existujúceho loopback tunela overiť jeho cieľ aj `pg_isready`; samotný počúvajúci port
nie je dôkaz zdravého DB spojenia. Cudzie tunely sa nezastavujú.

Port pre `railway connect Postgres --tunnel-only` má syntax `-P 55432`, nie
`-P 127.0.0.1:55432`. Pozor na výstup CLI: implementácia `print_tunnel_info`
vypisuje na stderr aj heslo a celé URL. Pri pravidle bez výpisu tajomstiev musí
proces použiť stdout aj stderr do DEVNULL; úspech overiť nezávisle cez pg_isready.
Verejný DB port sa nepovoľuje. Žiadne callback kódy sa neopakujú ani nekopírujú
do príkazov. [Zdroj implementácie CLI](https://github.com/railwayapp/cli/blob/master/src/commands/connect.rs).

## Proxy, klientova IP a limiter

API štart explicitne používa `--proxy-headers` a `--forwarded-allow-ips` zo shellovej
premennej STRAZ_TRUSTED_PROXY_IPS. Predvolený zoznam je prázdny: nepreberá IP z ľubovoľného
X-Forwarded-For. Nezadávať `*`. Existujúci FORWARDED_ALLOW_IPS nesmie nenápadne prepísať
explicitné nastavenie. Reálny zoznam sa musí odvodiť z overenej Railway ingress topológie.

Na stagingu overiť: nedôveryhodný peer so spoofnutým XFF nemení budget; dôveryhodný proxy
pripája/čistí pravého klienta; dva klienti majú oddelené budgety. Lokálne regresné testy
pokrývajú obe situácie. Railway/Vercel ingress a jeho ochrana hlavičiek sú zatiaľ neoverené;
pri prázdnom allowliste môže byť budget zdieľaný proxy peerom. Nevyriešiť to slepou dôverou
všetkým IP ani ľubovoľným klientskym hlavičkám. Vlastník musí schváliť overený trust boundary.

HSTS je v API pri HTTPS alebo v production (TLS ukončené na edge); HTTP dev ho nedostáva.
Frontend CSP je iba Report-Only. Po schválenom preview/staging deployi skontrolovať
konzolu pri login/logout, PWA, SSE, reportoch, obrázkoch a billing redirectoch; až po
zdokumentovanom browser teste schváliť prechod na vynucovanie. Zatiaľ nie je prepnutý.

## Registrácia a syntetický účet

Rozhodnutie vlastníka: verejná SaaS registrácia s rate limitom a prípadným email proof,
alebo uzavretý režim s konfiguráciou/allowlistom. Súčasná registrácia zostáva zachovaná,
obchodný zámer zatiaľ nie je potvrdený. Riziko otvoreného režimu: zneužitie účtov/kvót,
odosielania pozvánok a prevádzkových nákladov. Pozvánky existujúcich tímov treba zachovať.

Syntetický testovací účet a jeho workspace sa bez súhlasu nemažú. Pred prípadným zásahom
overiť identitu podľa incidentného reportu, počet členov a vlastníctvo aplikácií; nemení sa
skutočný admin ani DEMO workspace. Auditné udalosti zostávajú zachované. Použiť podporovaný
postup a overiť FK/retenciu; neodstraňovať triggery na obídenie ochrany.
