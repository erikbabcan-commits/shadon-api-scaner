# STRÁŽ — aktuálna projektová karta

Aktualizácia: **5. 11. 2026**. Podrobný audit: [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md).

| Oblasť | Overený stav / cieľ |
|---|---|
| Kanonický repo | erikbabcan-commits/shadon-api-scaner |
| Najpokročilejšia zdrojová vetva | main |
| Aplikačný SHA | ce12ee556b68b36d9232938b173c6cf09216ec67 |
| Dokumentačná vetva | docs/lovable-hetzner-20261105 |
| Frontend | apps/web; prenos do Lovable podľa handoffu |
| Backend | apps/api, FastAPI + ARQ; Hetzner VPS je druhý krok |
| Existujúci frontend | https://straz-monitoring.vercel.app, deployment SHA 7b0ae28 |
| Existujúci backend | https://straz-api-production.up.railway.app, runtime SHA teraz nepotvrdený |
| Stripe | Nastavenie odložené na druhý krok |

Všetkých šesť starších vetiev je zahrnutých v main. Vercel straz-security odkazuje
na ForenzDetectiv; nie je to novší scanner. GUARD a API Hub sú samostatné integrácie.

## Overené dôkazy

- [CI 40650162205](https://github.com/erikbabcan-commits/shadon-api-scaner/actions/runs/40650162205):
  127 backend testov na PG16 a rovnaká sada na PG18; 19 frontend testov; TypeScript/build a secret gate success.
- Živá readiness cez Vercel 5. 11.: HTTP 200, ready=true, DB aj Redis ok.
- Priamy backend liveness 200 a /api/auth/me bez relácie 401.
- Nevykonal sa browserový login, povolený produkčný scan, kontrola workera ani nový deploy.

## Obmedzenia

Povolené sú heartbeat a internetdb. Osem CLI profilov zostáva globálne zablokovaných.
PoC endpoint iba kontroluje prefix curl; nepreukazuje sieťové vykonanie.
Zelené CI ani health nepotvrdzujú rotáciu, backup/restore, worker SHA alebo migráciu na Hetzner.
Supabase nie je závislosť hlavného scanneru; inventár dostupného Supabase pripojenia STRÁŽ projekt nevrátil.

Notion karta: https://www.notion.so/402f2b2226ce8044b1b4e0e42738c40b
Pri synchronizácii uložiť iba tieto overené údaje a odkazy, nie credentials.
Historické tajomstvá sa považujú za kompromitované; rotácia zostáva nepotvrdená.

## Pokračovanie

[Frontend Lovable](docs/LOVABLE_FRONTEND.md),
[Hetzner backend](docs/HETZNER_BACKEND.md),
[premenné](docs/ENVIRONMENT.md),
[API](docs/API_CONTRACT.md),
[prevádzka](docs/OPERATIONS_ACCEPTANCE.md),
[rotácia](docs/INCIDENT_ROTATION_RUNBOOK.md).
