# STRÁŽ — súčasné a cieľové nasadenie

Aktualizované 5. 11. 2026. Tento dokument je rozcestník, nie dôkaz presunu alebo release.

| Vrstva | Súčasný zistený stav | Cieľ druhého kroku |
|---|---|---|
| Zdroj | shadon-api-scaner/main@ce12ee5, zelený CI | Rovnaký overený aplikačný základ |
| Frontend | Vercel straz-monitoring, deployment uvádza 7b0ae28 | Vývoj v Lovable, potvrdený frontend hosting a doména |
| API/worker | Posledný známy Railway dev-new; runtime SHA zatiaľ nepotvrdený | FastAPI a ARQ na Hetzner VPS |
| Dáta | Živé readiness potvrdilo DB a Redis | Obnoviteľný PostgreSQL a trvalý Redis, kontrolovaný presun dát |
| Stripe | Kód existuje, aktívna konfigurácia neoverená | Samostatná konfigurácia a test až v druhom kroku |

## Poradie

1. [PROJECT_STATUS.md](PROJECT_STATUS.md): použiť main@ce12ee5, nie staré release vetvy alebo Vercel build.
2. [LOVABLE_FRONTEND.md](LOVABLE_FRONTEND.md): preniesť frontend a zachovať externé auth/API.
3. [HETZNER_BACKEND.md](HETZNER_BACKEND.md): opraviť backend-only Compose, ingress, perzistenciu a reprodukovateľný build.
4. [ENVIRONMENT.md](ENVIRONMENT.md): skutočné názvy premenných a doménová/cookie topológia.
5. [OPERATIONS_ACCEPTANCE.md](OPERATIONS_ACCEPTANCE.md): migrácie, dáta, backup/restore, worker a browserové overenie.
6. Až potom vykonať cutover; Stripe nastaviť samostatne, bez obchádzania kvót.

## Existujúci Railway kontext

Projekt dev-new, služby straz-api, straz-worker, PostgreSQL a Redis; pred operáciou overiť identity.
API/worker root: apps/api; Dockerfiles: Dockerfile a worker.Dockerfile.
Migrácie sú samostatný krok `python -m app.migrations upgrade`; oba procesy potom kontrolujú head.
Konfigurácie railway.api.json/railway.worker.json nie sú dôkazom ich efektívneho použitia.

Frontendové Vercel rewrites stále smerujú na Railway. Pri presune na Hetzner sa musia
vedome zmeniť vrátane /healthz, CSP Report-Only a prípadných OpenAPI ciest.
Push do Gitu nepreukazuje zmenu pripnutého Railway deploymentu.

Historická rotácia podľa [INCIDENT_ROTATION_RUNBOOK.md](INCIDENT_ROTATION_RUNBOOK.md)
zostáva nepotvrdená. Žiadny existujúci zdroj, účet ani databáza sa nemajú zrušiť pred
overeným presunom. Osem CLI profilov ostáva blokovaných na každej platforme.
