# STRÁŽ — prevádzkové overenie a čakajúce rozhodnutia

Tento dokument je postup, nie potvrdenie vykonania v produkcii. Aktuálny stav
Railway služieb, backupov a tajomstiev vyžaduje oprávnený platformový prístup.

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
6. Izolovaný cieľ a dočasnú zálohu odstrániť podľa schválenej politiky. Výsledok pripojiť
   k release. Bez týchto dôkazov zostáva backup/restore **neoverený**.

## Alerty a monitoring

Po povolení platformových zmien nastaviť upozornenie na neúspešný deploy pre straz-api
aj straz-worker a reštart slučku. Readiness monitorovať HTTPS GET každých 60 s,
timeout 10 s, alarm po 3 po sebe idúcich zlyhaniach, obnova po 2 úspechoch.
Použiť `/healthz/readiness` a sledovať aj obsah ready=true; samotná liveness nestačí.
Pridať súkromný monitoring worker heartbeat/job latency/queue backlog a backup age.
Príjemcu a kanál musí určiť vlastník; bez neho sa neposiela syntetická notifikácia.
Otestovať alert na stagingovej sonde, nie vypnutím produkčnej DB alebo Redisu.
Aktuálne nastavenie, doručenie, retencia logov a RPO/RTO **neboli týmto PR potvrdené**.

## Zdroj deploya a zodpovednosť

Posledný runtime report uvádza pin commitSha na API aj workeri. Tento fakt treba znovu
overiť cez Railway konfiguráciu, nie podľa stavu GitHub main. Pri ponechanom pine push
do main nespustí automaticky nový kód. Nasadenie schváleného SHA riadi vlastník projektu
alebo poverený release operátor s prístupom do workspace. Zaznamenať SHA oboch služieb.

Automatický deploy z main zapnúť až po samostatnom schválení a vynútených CI gates
(secret-scan, backend PG 16/18, frontend). Pred tým nespúšťať neotestovaný main automaticky.
Po každom nasadení overiť health, vlastnú autorizovanú reláciu a worker zodpovedajúceho SHA.

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
