# STRÁŽ — index dokumentácie

Aktualizované 5. 11. 2026. Referenčný aplikačný kód: `main@ce12ee556b68b36d9232938b173c6cf09216ec67`.

## Aktuálne podklady

| Dokument | Obsah |
|---|---|
| [PROJECT_STATUS.md](PROJECT_STATUS.md) | Výber repozitára/vetvy, inventár pripojení, testy a živé dôkazy |
| [LOVABLE_FRONTEND.md](LOVABLE_FRONTEND.md) | Frontendový prenos, Git sync a zachovanie externého backendu |
| [HETZNER_BACKEND.md](HETZNER_BACKEND.md) | Architektúra, medzery Compose, migrácie a presun dát |
| [ENVIRONMENT.md](ENVIRONMENT.md) | Skutočné názvy premenných, dotenv, CORS, cookies a Stripe |
| [API_CONTRACT.md](API_CONTRACT.md) | Existujúce endpointy, autentifikácia, scope a obmedzenia |
| [CLOUD_DEPLOYMENT_GUIDE.md](CLOUD_DEPLOYMENT_GUIDE.md) | Rozdelenie súčasného a cieľového nasadenia |
| [OPERATIONS_ACCEPTANCE.md](OPERATIONS_ACCEPTANCE.md) | Akceptácia, zálohy, alerty, ingress a rozhodnutia |
| [INCIDENT_ROTATION_RUNBOOK.md](INCIDENT_ROTATION_RUNBOOK.md) | Koordinovaná rotácia; vykonanie ostáva nepotvrdené |
| [SECRET_SCAN.md](SECRET_SCAN.md) | Gitleaks, hook a historické tajomstvá |
| [../NOTION_NOTES.md](../NOTION_NOTES.md) | Stručná projektová karta a synchronizácia Notion |
| [../CHANGELOG.md](../CHANGELOG.md) | Vývoj a táto dokumentačná aktualizácia |

## Historické implementačné reporty

[EPIC 1](EPIC_1_REPORT.md), [EPIC 2](EPIC_2_REPORT.md), [EPIC 3](EPIC_3_REPORT.md),
[EPIC 4](EPIC_4_REPORT.md), [EPIC 5](EPIC_5_REPORT.md), [EPIC 6](EPIC_6_REPORT.md)
a [bezpečnostná kontrola z 26. 10.](SECURITY_REVIEW_2026-10-26.md) zostávajú podkladmi k pôvodnému rozsahu.
Ich historické počty testov, návrhy alebo marketingové formulácie neprepisujú aktuálny stav.
Pri rozpore platí overený kód konkrétneho SHA a aktuálne dokumenty vyššie.

Táto zmena dokumentuje prípravu. Nevykonáva migráciu produkčných dát, presun DNS, nasadenie, rotáciu ani zapnutie Stripe.
