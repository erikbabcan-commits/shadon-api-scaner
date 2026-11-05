# STRÁŽ — plán backendu na Hetzner VPS

Pripravené 5. 11. 2026 pre aplikačný zdroj `main@ce12ee5`.
Presun, konfigurácia servera, Stripe aj produkčné zápisy sú druhý krok.
Existujúca Railway služba zostáva referenčným bežiacim prostredím do overeného cutoveru.

## Cieľový stack

| Komponent | Úloha |
|---|---|
| HTTPS ingress, Caddy alebo existujúci reverzný proxy | Verejné /api a /healthz, certifikát, limity a dôveryhodné proxy hlavičky |
| FastAPI, apps/api/Dockerfile | Auth, RBAC, organizácie, inventár, nálezy, reporty a CI |
| ARQ, apps/api/worker.Dockerfile | Konzument fronty a scheduler; samostatný proces so zhodným kódom |
| PostgreSQL | Trvalý volume, samostatné prihlasovanie, zálohy a restore |
| Redis | Fronta a aplikačný stav; trvalé úložisko a dohodnutá recovery politika |

Postgres a Redis nemajú verejné porty. Frontend je samostatný Lovable projekt;
jeho hosting a domény sa potvrdia spolu s [cookies a CORS](ENVIRONMENT.md).
Supabase nie je nutná závislosť hlavného scanneru. Existujúce Supabase bridge projekty
sa pripájajú samostatne, bez zmeny ich dát alebo používateľov.

## Zistené medzery existujúceho Compose

`deploy/docker-compose.yml` s produkčným overlayom je pôvodný all-in-one stack,
nie hotová backend-only Hetzner konfigurácia.

1. Caddy závisí aj od web služby, ktorá zostavuje pôvodný frontend. Pre frontend mimo VPS
   treba samostatnú backend-only konfiguráciu a API ingress.
2. API ani worker nevykonajú migráciu automaticky; pri nesprávnej revízii odmietnu štart.
3. Redis nemá definovaný trvalý volume ani výslovnú AOF konfiguráciu.
   Recreate môže stratiť frontu; ani perzistencia nenahrádza obnovovaciu/idempotentnú politiku.
4. Base porty Caddy 8080/8443 sa môžu pri merge overlayu zachovať spolu s 80/443.
   Overiť efektívny Compose, odstrániť nechcené publikované porty.
5. HTTPS Caddyfile smeruje /api a /healthz; /docs a /openapi.json nemajú vlastné API pravidlo.
   Nevydávať SPA fallback za živú OpenAPI schému.
6. Docker API/worker inštalujú závislosti cez pip z pyproject bez použitia uv.lock;
   frontend Dockerfile používa npm install. CI naopak používa frozen lockfile/npm ci.
   Pred release zostaviť reprodukovateľné obrazy a otestovať ich.
7. Dôveryhodné proxy IP sú prázdne. Nenastavovať wildcard; odvodiť presný trust boundary
   z Hetzner ingressu a overiť dvoch klientov aj spoofnuté X-Forwarded-For.
8. Zálohovací skript je dostupný, ale naplánovanie, mimovps kópia a izolovaný restore
   sa nepreukázali. Skript načítava .env shellom; používať iba dôveryhodný súkromný súbor.
9. Osem CLI profilov sa nesmie odblokovať iba preto, že je služba na VPS.
   Egress izolácia chýba v celom reťazci, nie iba v Railway.
10. Zjednotiť podporované Node runtime pre frontend a CI; nevykonať pritom nevyžiadaný framework upgrade.

Tieto body sú úlohy pre implementáciu druhého kroku. Táto dokumentačná vetva
nemodifikuje Dockerfiles, Compose, ingress ani workflow.

## Poradie realizácie v druhom kroku

1. Overiť cieľový Hetzner host, voľné prostriedky, existujúce kontajnery/proxy,
   domény a pravidlá siete. Nezameniť zdieľaný VPS s čistým serverom.
2. Overiť zálohu existujúceho PostgreSQL a restore do novej izolovanej DB.
   Zistiť skutočné Alembic revízie, orphan počty, runtime SHA API aj workera.
3. Rozhodnúť čistý štart alebo zachovanie dát. Bez rozhodnutia neduplikovať používateľov,
   organizácie ani billing identitu a nespúšťať automatický seed.
4. Pripraviť backend-only Compose s trvalým PG/Redis, privátnou sieťou,
   limity/log rotation, healthcheckmi a overeným HTTPS ingressom.
5. Súkromne pripraviť hodnoty z [ENVIRONMENT.md](ENVIRONMENT.md). Nepoužiť historické
   heslá ani literálne shellové substitúcie v dotenv. Zmenu admin bootstrap premennej
   nepovažovať za reset existujúceho účtu.
6. Zostaviť a otestovať API aj worker zo zhodného konkrétneho SHA.
7. Spustiť len databázu a Redis. Vykonať explicitnú migráciu proti správnej cieľovej DB.
8. Až po úspešnej migrácii spustiť API a worker. Očakávaný Alembic head v referenčnom
   commite je `009_cvss_and_poc_fields`; potvrdiť cez CLI aj DB, nie iba podľa názvu súboru.
9. Zapojiť neverejný testovací frontend, overiť CORS/cookies a úplný tok povoleného skenu.
10. Pri zachovaní dát: naplánovať krátke zastavenie zápisov a starého scheduleru/workera,
    finálnu zálohu/import a overenie počtov. Nespúšťať dva schedulery nad divergujúcimi DB.
    Neprenášať Redis frontu naslepo; zaevidovať nedokončené runy.
11. Až potom presmerovať schválené API domény/frontend proxy; starý backend
    uchovať ako definovaný návratový bod, bez súbežného zapisovania.
12. Nastaviť a otestovať monitoring, alerty, backup schedule a obnovu.
    Stripe zapojiť ako samostatný nadväzujúci krok s testovacími platbami a webhook idempotenciou.

## Existujúce migračné rozhranie

Po vyplnení súkromnej konfigurácie a overení cieľovej DB je príkaz aplikácie:

```bash
python -m app.migrations upgrade
python -m alembic current
python -m alembic heads
```

V lokálnom uv prostredí im predchádza `uv run --frozen`.
V pripravenej Compose konfigurácii má migrácia bežať ako jednorazová API úloha pred
spustením API/workera, nie súbežne v každej replike. Neprerábať publikované migrácie 001–009.

Pôvodný all-in-one Compose možno preskúmať z priečinka deploy cez:

```bash
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml config --quiet
```

`--quiet` overuje syntax bez vypísania dosadených tajomstiev.
Úspech neznamená opravené porty, perzistenciu, migrácie alebo backend-only topológiu.
Návod zámerne neposkytuje neoverený jednorazový produkčný `up -d`.

## Akceptačný záznam

Zaznamenať nasadené SHA API/workera/frontendu, verzie obrazov a DB, Alembic revíziu,
liveness/readiness, test skutočne dokončenej ARQ úlohy, tenantové/role hranice,
login/logout vrátane Safari, export, backup/restore a návratový postup.
HTTP 200 na health endpointe tieto oblasti nenahrádza.

Pri rollbacku po nových zápisoch nepresmerovať prevádzku na starú neaktuálnu DB.
Najprv rozhodnúť dátový návrat a konzistenciu. Starý a nový backend nesmú prijímať
nezávislé produkčné zápisy.

Súvisiace: [OPERATIONS_ACCEPTANCE.md](OPERATIONS_ACCEPTANCE.md),
[INCIDENT_ROTATION_RUNBOOK.md](INCIDENT_ROTATION_RUNBOOK.md).
