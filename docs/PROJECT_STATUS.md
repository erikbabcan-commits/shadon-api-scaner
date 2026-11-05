# STRÁŽ — výber zdroja a overený stav, 5. 11. 2026

## Rozhodnutie

Najpokročilejší overený kompletný projekt je
[erikbabcan-commits/shadon-api-scaner](https://github.com/erikbabcan-commits/shadon-api-scaner),
vetva [main](https://github.com/erikbabcan-commits/shadon-api-scaner/tree/main),
commit [ce12ee556b68b36d9232938b173c6cf09216ec67](https://github.com/erikbabcan-commits/shadon-api-scaner/commit/ce12ee556b68b36d9232938b173c6cf09216ec67).

Obsahuje frontend aj backend a zelený CI. Dokumentačná vetva `docs/lovable-hetzner-20261105`
z neho vychádza bez zmeny aplikačnej implementácie. Cieľom je Lovable frontend a Hetzner backend;
platby a vykonanie presunu patria do druhého kroku.

## Pokrytie prieskumu

Prešli sa inventáre troch GitHub pripojení a ich dostupné inštalácie, spolu **608 unikátnych repozitárov**:

| Vlastník dostupných repozitárov | Počet |
|---|---:|
| youh4ck3dme | 426 |
| ENZO7700 | 91 |
| erikbabcan-commits | 77 |
| you640 | 9 |
| kadadakaj-dev | 4 |
| NEXIFY-STUDIO | 1 |

Ide o dostupné repozitáre týchto pripojení, nie dôkaz úplnosti všetkých nepripojených účtov.
Názvy a cielené vyhľadávanie STRAZ doplnila kontrola obsahu relevantných kandidátov.
608 repozitárov neprešlo individuálnym auditom zdrojového kódu.

Vercel: prešli sa obe pripojenia a všetky vrátené projekty tímov `somnajviac` (69) a `h4ck3d` (200).
Relevantné nasadenia sa overili aj podľa Git metadát, nielen podľa názvu.

Supabase: pripojenie vrátilo jeden projekt `forzaxteligent`, žiadny potvrdený STRÁŽ projekt.
Tento výsledok nevylučuje iné nepripojené účty ani samostatné Lovable Cloud backendy.
Hlavný STRÁŽ zdroj neobsahuje Supabase klienta/migrácie; používa vlastný PostgreSQL a FastAPI auth.

Notion: prečítala sa karta [Shadon API. scanner](https://www.notion.so/402f2b2226ce8044b1b4e0e42738c40b)
a relevantný projektový inventár. Pôvodná karta z 26. 10. mala zastarané commity,
38 testov a nepreukázané tvrdenie o úplnom dokončení.

## Porovnanie všetkých siedmich vetiev

Počty sú voči `main@ce12ee5`. Všetky alternatívy majú **0 vlastných commitov navyše**.

| Vetva | HEAD | Za main | Záver |
|---|---|---:|---|
| main | ce12ee5 | 0 | Vybraný základ |
| fix/app-org-mismatch-and-spa-rewrite | a4e27b5 | 6 | Obsah už zahrnutý |
| railway/incident-remediation-20261027 | 04ee9fd | 5 | PR #4 zlúčený 27. 10. |
| fix/railway-port-and-pg18-ci | ec8be2c | 11 | PR #3 zlúčený 26. 10. |
| railway/pg-migration-008-reviewed | 2f42885 | 13 | PR #2 zlúčený 26. 10. |
| audit-fix/20261022-security-hardening | 464ab28 | 16 | Starší snapshot; nie vhodnejší release |
| release/20261026-cloud-readiness | 464ab28 | 16 | Rovnaký starší snapshot |

Nie je potrebné zlučovať historické vetvy ani prepisovať publikovanú históriu.

## Kandidáti s príbuzným názvom

| Repo alebo projekt | Nález | Rozhodnutie |
|---|---|---|
| shadon-api-scaner | FastAPI + ARQ engine, kompletná PWA, migrácie a CI | Kanonický zdroj |
| erikbabcan-commits/guard-vorkei.com | Samostatný SOC s mostom na STRÁŽ; Vercel vetva feat/straz-bridge-integration | Budúca integrácia, nie náhrada scanner backendu |
| erikbabcan-commits/api-hugger | Existujúci Lovable API Hub pre služby/hosting; obsahuje straz-bridge | Samostatná konzola, nie novšia vetva scanneru |
| Vercel straz-security | Nasadenie odkazuje na youh4ck3dme/forenz-detectiv | Nesúvisiaci obsah napriek názvu |

## Vercel — skutočné mapovanie

| Tím / projekt | Nasadený Git zdroj | SHA | Posledný zistený stav |
|---|---|---|---|
| h4ck3d / straz-monitoring | erikbabcan-commits/shadon-api-scaner, main | 7b0ae28 | READY; dpl_B23Gu7NE3bZKiJD9SoD6WQteKoLt |
| somnajviac / shadon-api-scaner | rovnaké repo, main | 7352c58 | READY; dpl_8b4Q9yiwGpbgmTKeZsDYKcMzUPQQ |
| somnajviac / web | rovnaké repo, main | 7352c58 | READY; dpl_DDKTwRrcDBUfZoXFgJQdemHnWD3a |
| h4ck3d / straz-security | youh4ck3dme/forenz-detectiv, cursor/prod-pause-monetization-933f | 4eb6c6f | READY, ale nejde o STRÁŽ scanner |
| somnajviac / guard-vorkei | erikbabcan-commits/guard-vorkei.com, feat/straz-bridge-integration | 53add96 | READY; samostatná integrácia |

Hlavná existujúca frontendová adresa je [straz-monitoring.vercel.app](https://straz-monitoring.vercel.app).
Ďalší alias je [web-flax-omega-55.vercel.app](https://web-flax-omega-55.vercel.app).
Staršie zrkadlá sú [shadon-api-scaner.vercel.app](https://shadon-api-scaner.vercel.app)
a [web-eta-eosin-61.vercel.app](https://web-eta-eosin-61.vercel.app).
READY je stav deploymentu, nie dôkaz funkčnosti všetkých používateľských tokov.

Vybraný kód je oproti `straz-monitoring@7b0ae28` o 7 commitov ďalej:
incidentná redakcia a brány, PR #4, oprava org/SPA, synchronizačný merge,
CVSS/PoC a SARIF/CSV. Návrat k starému deploymentu by tieto zmeny vynechal.

## Testy — presný pôvod dôkazu

[CI run 40650162205](https://github.com/erikbabcan-commits/shadon-api-scaner/actions/runs/40650162205),
28. 10. 2026, SHA `ce12ee5`:

| Job | Výsledok z výstupu |
|---|---|
| Secret gate | success |
| Backend PG 16, job 122688211641 | 127 passed |
| Backend PG 18, job 122688211622 | 127 passed |
| Frontend, job 122688211645 | 2 test files, 19 passed; build a TypeScript success |

Ide o rovnakých 127 backend testov v dvoch DB prostrediach, nie 254 odlišných testov.
Nie je to nová lokálna regresia ani Safari/PWA E2E. Lokálne sa zdrojový snapshot overil
proti všetkým 178 Git blob SHA pred dokumentačnými úpravami.

## Živé kontroly z 5. 11. 2026

| Kontrola | Výsledok |
|---|---|
| Vercel /healthz/readiness, 19:16:37 UTC / 20:16:37 CET | HTTP 200, ready=true, PostgreSQL ok, Redis ok |
| Priamy Railway /healthz/liveness | HTTP 200 |
| Priamy Railway /api/auth/me bez cookie | HTTP 401, Not authenticated |

Existujúce API: [straz-api-production.up.railway.app](https://straz-api-production.up.railway.app).
Railway projekt `dev-new`, služby `straz-api` a `straz-worker` sú posledný známy
prevádzkový kontext. Aktuálny runtime SHA API/workera, DB revízia, worker heartbeat,
rotácia a backup/restore sa cez tieto pripojenia nepotvrdili. Historický pin `83a25c3`
sa nesmie vydávať za aktuálne znovu overený stav.

Jedno čítanie `/api/auth/me` cez Vercel zastavila Vercel Authentication.
Preto je negatívny auth dôkaz z priameho Railway endpointu. Prehliadačový login sa nevykonal.

## Materiálne medzery pred druhým krokom

1. Osem CLI profilov zostáva globálne blokovaných do vynútenej a testovanej izolácie.
2. PoC overenie je iba textová kontrola prefixu, nie reprodukcia nálezu.
3. Lovable Git sync vytvára nové repo; existujúci GitHub monorepo sa tým priamo nepripojí.
   ZIP importer štandardne prestavuje aplikáciu a mení backend/auth, preto je potrebný
   [frontendový handoff](LOVABLE_FRONTEND.md) so zachovaním externého FastAPI.
4. Compose vyžaduje samostatné migrácie, produkčný ingress a trvalý Redis.
   Docker buildy nepoužívajú lockfile tak ako CI; pozri [Hetzner plán](HETZNER_BACKEND.md).
5. Session cookies, CORS, Safari a presný proxy trust boundary treba potvrdiť na cieľových doménach.
6. Stripe je druhý krok; Free kvóty/API-key obmedzenia sa nemenia ani neobchádzajú.
7. V strome chýba LICENSE. Historické tvrdenia o plnom NIS2 súlade/100 % pripravenosti nie sú preukázané.

## Zdroje k prenosu do Lovable

- [Oficiálny Git sync a import FAQ](https://docs.lovable.dev/integrations/github)
- [Oficiálny ZIP import a opis automatickej migrácie](https://docs.lovable.dev/features/projects/import-project)

Dokumentačná aktualizácia nemení cloudové nastavenia, DNS, dáta, relácie, worker ani platby.
