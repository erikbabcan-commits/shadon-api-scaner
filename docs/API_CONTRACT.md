# STRÁŽ — existujúca API zmluva

Referenčný kód: `main@ce12ee5`. Toto je prehľad implementovaných rout,
nie úplná náhrada OpenAPI a nie potvrdenie rovnakej verzie živého backendu.
Routery: `apps/api/app/routers/`; browser klient: `apps/web/src/lib/api.ts`.

## Autentifikácia a tenant

Browser používa podpísanú HttpOnly session cookie a `credentials: include`.
Pre POST/PATCH/DELETE zachovať `X-Requested-With: XMLHttpRequest` a dôveryhodný origin.
Zvolenú organizáciu určuje `X-Organization-Id`; pri niektorých linkových exportoch
sa používa query `organization_id`. Backend musí overiť členstvo a oprávnenie.

M2M používa **Authorization: Bearer straz_live_…**. Aktuálny kód nečíta
`X-API-Key` ako náhradnú autentifikačnú hlavičku.
Kľúč obsahuje 32 náhodných URL-safe znakov za prefixom; uložený je SHA-256 hash.
Je dostupný iba pre podporovaný platený plán, platné členstvo a explicitný zoznam rout.

Scope v tomto SHA sú `ci:scan`, `apps:read`, `findings:read`, `reports:read`.
**Scope ci:runs:read tu implementovaný nie je.** Polling CI runu vyžaduje `ci:scan`.
Svojvoľné pridanie scope do frontendu alebo databázy nerozšíri serverový route allowlist.

## Hlavné routy

| Metóda a cesta | Účel |
|---|---|
| POST /api/auth/register, /api/auth/login | Registrácia/prihlásenie; JSON email a password |
| GET /api/auth/me | Aktuálny používateľ; 401 bez relácie |
| POST /api/auth/logout | Odhlásenie |
| POST /api/auth/change-password | old_password a new_password |
| GET/POST /api/orgs | Organizácie používateľa / nová organizácia |
| GET /api/orgs/{org_id}/members | Členovia |
| POST /api/orgs/{org_id}/invitations | Pozvánka |
| PATCH/DELETE /api/orgs/{org_id}/members/{user_id} | Správa rolí a členov |
| POST /api/invitations/{token}/accept | Prijatie pozvánky |
| GET/POST /api/apps | Inventár / vytvorenie aplikácie |
| GET/PATCH/DELETE /api/apps/{app_id} | Detail a správa |
| POST /api/apps/{app_id}/targets | Pridanie cieľa |
| POST /api/targets/{target_id}/verify | Overenie vlastníctva |
| POST /api/apps/{app_id}/runs | Povolený manuálny profil |
| GET /api/runs, /api/runs/{run_id}, /api/runs/stream | Beh, detail a SSE |
| GET /api/findings, /api/findings/{finding_id} | Nálezy |
| PATCH /api/findings/{finding_id} | Stav, CVSS a PoC metadáta |
| POST /api/findings/cvss/calculate | CVSS v3.1 výpočet |
| POST /api/findings/{finding_id}/verify-poc | Iba kontrola prefixu curl; žiadna sieťová reprodukcia |
| GET /api/findings/export/sarif, /api/findings/export/csv | Export nálezov |
| GET /api/apps/{app_id}/report/html, /report/sarif, /report/csv | Rovnaký prefix aplikácie, rôzne reporty |
| GET /api/apps/{app_id}/compliance | Orientačné indikátory |
| GET/PATCH /api/orgs/{org_id}/branding | Branding |
| GET/POST /api/orgs/{org_id}/channels | Alert kanály |
| GET/POST/DELETE /api/orgs/{org_id}/api-keys[/{key_id}] | Administrácia kľúčov podľa konkrétnej routy |
| GET /api/orgs/{org_id}/audit-logs, /audit-logs/export.csv | Audit; druhá cesta má rovnaký prefix organizácie |
| GET /api/billing/plans, /api/billing/usage | Plány/spotreba |
| POST /api/billing/create-checkout-session, /customer-portal, /webhook | Posledné dve tiež pod /api/billing; nastavenie až druhý krok |
| GET /healthz/liveness, /healthz/readiness | Verejné sondy |
| GET /api/health, /api/health/ready | Legacy readiness aliasy |

Nie všetky routy v tabuľke sú povolené API kľúčom. Napríklad nové SARIF/CSV exporty
nie sú pridané do `API_KEY_ROUTES` v deps.py; `reports:read` ich automaticky neodomkne.
Pri session môže aplikácia dostupná cez druhé členstvo použiť fallback kontrolu členstva;
kontext a rolu treba overiť pre cieľový tím, nie spoliehať sa na UI.

## CI scan

`POST /api/ci/scan` prijíma `app_id`, `profile`, `fail_on`, `wait` a `timeout_seconds`.
Predvolený `profile=safe` je dnes globálne blokovaný; klient musí uviesť povolený profil
a splniť overenie cieľa, plán aj kvótu.

- `wait=false`: prijatý beh vracia 202.
- Dokončený úspešný gate: 200; prekročený prah alebo neúspešný beh: 424 podľa implementácie.
- `GET /api/ci/runs/{run_id}`: polling s `ci:scan` a tenantovou izoláciou.
- Neexistuje samostatný `/api/ci/gate` endpoint opísaný v staršom README.

## Chybové stavy a pravdivé UI

401 autentifikácia, 403 oprávnenia/scope/origin, 404 nedostupný objekt,
402 plán/kvóta, 409 globálne blokovaný profil, 429 limiter a 503 nenastavené služby
sa nemajú vo frontende preklopiť na simulovaný úspech.
Health 200 nepreukazuje worker, revíziu migrácií ani vykonanie scan profilu.

PoC endpoint vráti pri texte začínajúcom curl syntetické `verified=true` a
`status_code=200`. Aktuálna implementácia je **stub**, nie dôkaz cieľového HTTP 200.
Pred reálnou PoC validáciou treba navrhnúť izolovaný, autorizovaný vykonávací model.
