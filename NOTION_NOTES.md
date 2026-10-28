# STRÁŽ — bezpečné prevádzkové poznámky

## Prostredie a rozsah

Railway projekt je `dev-new`; `straz-monitoring` je názov Vercel projektu.
Frontend: https://straz-monitoring.vercel.app
API: https://straz-api-production.up.railway.app
API a worker podľa posledného runtime reportu používali commit pin. Aktuálny pin,
nasadené SHA, konfiguráciu služieb a health treba overiť cez Railway pri každom release.
Push do main sám nezaručuje nasadenie. Operátor: vlastník workspace alebo poverený release operátor.

Aktívne sú Heartbeat a InternetDB. Profily tls, http, safe, subdomain, ports,
trivy_fs, trivy_image a gitleaks sú blokované do doplnenia izolácie skenerov,
nezávisle od plateného plánu. Backendové guardy sa neodstraňujú.

## Premenné

Do dokumentácie nepatria ani čiastočné hodnoty tajomstiev či connection stringov.
Hodnoty sa nastavujú a menia iba v oprávnenom Railway prostredí.

| Meno | Hodnota |
|---|---|
| DATABASE_URL | <set in Railway> |
| REDIS_URL | <set in Railway> |
| STRAZ_ADMIN_EMAIL | <set in Railway> |
| STRAZ_ADMIN_PASSWORD | <set in Railway> |
| STRAZ_SESSION_SECRET | <set in Railway> |
| STRAZ_ENV | <set in Railway> |
| STRAZ_COOKIE_SECURE | <set in Railway> |
| STRAZ_COOKIE_SAMESITE | <set in Railway> |
| STRAZ_CORS_ORIGINS | <set in Railway> |
| APP_FRONTEND_URL | <set in Railway> |
| STRAZ_TRUSTED_PROXY_IPS | <set in Railway> |

Historické hodnoty sa považujú za kompromitované. Ich odstránenie z tejto stránky
nie je rotácia a neodstráni ich zo starých commitov. Rotácia zatiaľ čaká na povolenie.
Postup: [incident a rotácia](docs/INCIDENT_ROTATION_RUNBOOK.md).

## Dôkazy a obmedzenia

CI pokrýva migrácie PostgreSQL 16 a 18. Úspešný API test nie je browserový E2E test.
Formulácia „12/12 E2E“ sa smie použiť iba s konkrétnym browserovým testom a výstupom;
starší checklist predstavuje API kontroly, nie automatizovaný Safari/PWA test.

Produkčný JS môže obsahovať localhost fallback v TanStack závislosti. To neznamená,
že API požiadavky smerujú na localhost. Na vercel.app klient používa relatívne /api
cez first-party proxy. Proxy nezaručuje prihlásenie pri používateľom zablokovaných cookies.

DEMO: seed je idempotentný, dáta označené ako syntetické, targety sa neoverujú a skeny
sa neaktivujú. Skutočné počty a stav v produkcii treba potvrdiť autorizovaným čítaním;
táto dokumentácia sama nepotvrdzuje vykonanie seedu alebo prihlásenie admina.

[Prevádzkové overenie, zálohy, alerty a čakajúce rozhodnutia](docs/OPERATIONS_ACCEPTANCE.md).
